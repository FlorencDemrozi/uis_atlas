# Funding Intelligence (Research Council of Norway calls)

Added 2026-10-27 at the project owner's request. Researchers can see which open and
planned RCN calls fit their recent publications, why, and which UiS colleagues could
complement them. Like the rest of the atlas it is files only: an offline pipeline
writes JSON, the static site reads it. No database, no server.

## Access

The funding pages (list, call pages, the "Funding opportunities" section on
profiles) are password protected. `pipeline/export_funding.py` encrypts the funding
data (gzip → AES-256-GCM, key from the password with PBKDF2-SHA256, 600 000
iterations, new random salt each export). The site only contains ciphertext; the
browser derives the key once the password is typed and keeps it for the browser
session. The password lives only in `.env` (`ATLAS_FUNDING_PASSWORD`).

Limits: this protects the data from casual visitors and from anyone reading the
site's code. It is a shared password, not per-person login; anyone who has it can
pass it on. To change it, set a new value in `.env` and re-run the export.

## Pipeline

| Stage | Script | Input → output |
|---|---|---|
| Collect | `collect_rcn.py` | forskningsradet.no call lists (current + completed) and each call page (nb + en) → `data/raw/rcn/` |
| Structure | `build_calls.py` | raw pages → `data/interim/calls.json`, `calls_history.json` |
| Match | `match_funding.py` | calls + paper embeddings (`embed.py`) → `data/interim/funding_matches.json` |
| AI profile | `profile_calls.py` | open/planned RCN calls and pre-filtered EU topics → `data/interim/call_profiles.json` (needs `ANTHROPIC_API_KEY`; skipped otherwise) |
| Match again | `match_funding.py --changed-profiles` | redoes only the calls whose AI profile changed |
| Export | `export_funding.py` | all of the above → `data/public/funding.enc.json` (encrypted) |

`run_all.py` runs the processing stages; `run_weekly.py` runs collectors + processing
+ `npm run build` (see "Scheduled update").

### Collection (`collect_rcn.py`)
RCN renders every page from JSON embedded in the HTML; we read that JSON (`rcn.py`),
not the markup. robots.txt allows `/utlysninger/` and disallows `*/Download`, so call
PDFs are never fetched. One request per second; about 2 requests per call. Completed
calls are fetched once and kept; current calls are refreshed every run. If RCN cannot
be reached, the previous files stay and the error is recorded in
`data/raw/rcn/sync_status.json` and shown on the site.

### Structured fields (`build_calls.py`)
Every field of the agreed list (A general, B financial, C project, D eligibility,
E evaluation/application, F resources) is stored with:
`v` value, `s` status (`explicit` / `inferred` / `not_specified`), `src` location on
the page, `url` source page, `ev` evidence text, `c` confidence, `m` method
(`metadata`, `section`, `rule`, `manual`, `ai`).

- Dates, amounts, durations, status and target groups come from RCN's structured
  page metadata, parsed without AI.
- Text requirements (project manager, partners, evaluation, ethics, …) are the
  official passage under the matching heading, in Norwegian and English.
- Rules that infer something (research type from the funding scheme; whether UiS
  can be project owner) are labelled "inferred by rule" with their basis.
- Fields RCN does not state are `not_specified` – never guessed. Fields only an AI
  reading can fill (co-funding, data management, consortium size, …) stay
  `not_specified` until `profile_calls.py` runs.
- Manual corrections: `config/funding_overrides.json` (never overwritten).
- Change history: deadline, status, amounts, target groups, text and listing changes
  are appended to `calls_history.json` and shown per call.
- Review flags: e.g. "listed as open but the deadline has passed", "no deadline found".

### AI call profiles (`profile_calls.py`)
For open/planned calls the Claude API reads the call text and returns, in a fixed
JSON schema: disciplines and topic paths, objectives, methods, technologies,
domains, competencies (core / complementary / mandatory partner / optional),
contributing expertise (the research areas that could deliver the R&D, an
interpretation that matters for broad calls such as Pilot Helse), an
interpretation (explicit vs. plausible directions) and values for the AI-only
fields. Every "fact" must quote the call; quotes are checked against the text and
unverifiable facts are dropped (fields) or downgraded to interpretation (topics).
AI values are shown next to official values and never replace them.

### Matching (`match_funding.py`, settings in `config.FUNDING_MATCH`)
1. The call is split into aspects: AI topics, technologies, contributing
   expertise, core/complementary competencies, methods and domains if a profile
   exists (required partners and optional extras are not research expertise and
   are left out), else the thematic bullets of the call text (administrative
   sentences removed). A scope text (title, summary, themes, plus the profile's
   disciplines and topics – RCN calls rarely fill summary and themes) describes
   the whole call.
2. Each recent paper (last 5 years; corrections, editorials and notes excluded) is
   compared with scope and aspects using the atlas embedding model. Cosine
   similarity is mapped to relevance on a fixed scale (0.80 → 0, 0.86 → 1), so a
   call nobody fits produces no strong match. Distinctive words of the English
   title (Norwegian if there is none) that occur in ≤1 % of UiS papers (e.g.
   "seafood", "quantum") add up to 20 %. Recency weight
   halves every 3 years.
3. Score = 0.5 scope alignment + 0.3 aspect coverage + 0.2 amount of evidence.
   High ≥ 0.6, Medium ≥ 0.35. A ranking aid, not a probability of funding.
   Besides the top 30, the 3 researchers who best cover each aspect are always
   listed ("among the best at UiS for …"), so e.g. a sensor expert is found for a
   call led by health services research.
4. Eligibility is separate and evidence-based: only conditions stated in the call
   (UiS not allowed as project owner → "only as R&D partner"; early-career call +
   professor; experienced-researcher call + PhD/postdoc; doctorate required + PhD
   candidate; adjunct/emeritus/external → "check"). Otherwise "no restriction
   found", never "eligible". Suggested roles respect eligibility. Career age is
   the years since the first UiS paper in the atlas (no PhD dates; papers from
   before UiS are missing), so it is only used for upper limits (early-career call
   + more than 12 years → "check"); a short UiS record is never flagged.
5. Internal collaborators: UiS researchers whose papers cover aspects the matched
   researcher lacks; existing co-authors (shared papers) and other departments are
   preferred. Always labelled as suggestions.

Not scored (no data yet): project experience, interdisciplinarity.

## EU funding (Funding & Tenders Portal) – Phase 1, 2026-10-29
EU topics live in the same records, matching, export and pages as RCN calls
(`source: "eu"`, id `eu-<official topic identifier>`, `family` for the filters:
horizon, erc, msca, eic, missions, partnerships, other_eu; RCN calls are `nfr`).

- **Collect** (`collect_eu.py` → `data/raw/eu/`): the portal's public search API
  (no key) lists open and forthcoming topics of every programme (calls for proposals
  and cascade calls; procurement tenders are left out) plus topics closed in the last
  6 months. Pages are sorted on a unique key (deadline, identifier) – the index returns
  duplicates and gaps otherwise. Each topic's JSON page is fetched only when its
  checksum or status changes, or after 28 days; closed topics once. About 1 450
  topics; a first run takes ~15 min, a weekly run a few minutes.
- **Structure** (`eu.py`, called by `build_calls.py`): the hierarchy Programme →
  programme part → Call → Topic; type of action (RIA/IA/CSA/ERC/MSCA-…); opening
  date, deadlines (single, two-stage, cut-offs, continuous); budget per topic, EU
  contribution per project, number of grants (from the portal's budget overview, euro);
  grant model; the official text under its headings (Expected outcome, Scope; the
  conditions: eligible countries, other eligibility, award criteria, procedure, legal
  set-up, specific conditions) and the linked documents.
- **Rules (inferred, with basis):** Norway's participation per programme (Horizon
  Europe: associated country; Digital Europe, EU4Health, Erasmus+, Creative Europe:
  EEA) – every other programme is "not determined" and shown as *check*; topics whose
  conditions restrict participation (e.g. Article 12(5)/22(5)) are *check* with the
  sentence; standard Horizon Europe consortium and funding-rate rules for RIA/IA/CSA
  (General Annexes B and D) are labelled as standard unless the topic says otherwise;
  EIC Accelerator = company funding (UiS cannot apply); ERC StG/CoG/AdG/SyG, MSCA
  PF/DN/SE and EIC Pathfinder Open are open to all fields (offered to every
  researcher with eligibility, like FRIPRO).
- **Status:** the portal lists hundreds of old topics as open or forthcoming after
  all their deadlines. Those are stored as closed ("inferred: all deadlines have
  passed") with a review note; cancelled topics are closed too.
- **Matching:** the same method as RCN calls, on the official topic text (or the AI
  profile, see Phase 2). Eligibility adds `eu_company_only`, `eu_restricted`,
  `eu_country_unknown`.
- **Export:** closed EU topics carry only their identifying fields; empty keys and
  source URLs equal to the topic page are left out and restored in the browser.

## EU funding – Phase 2, 2026-10-29
- **AI topic profiles with a pre-filter.** Matching first runs on every topic's
  official text. `profile_calls.py` then profiles an EU topic only if its best
  researcher score reaches `config.EU_PROFILE_MIN_SCORE` (0.5, about 150 of ~430 open
  topics), or if it already has a profile (kept while the topic is open, so a small
  score change does not drop it). Never profiled: topics open to all fields,
  institution-level and company-only topics, and topics without text. The EU prompt
  is the RCN prompt with one extra rule (the science is in Expected outcome and
  Scope; the conditions are standard text) and its own version number, so changing
  it does not redo the RCN profiles. The same quote checks apply. `run_all.py` then
  runs `match_funding.py --changed-profiles`, which reuses every call whose profile
  did not change (a full matching pass takes ~3.5 min).
- **Scoring with EU profiles:** the profile supplies the aspects, but the scope of
  an EU topic stays its official text (title, summary, programme part). With the
  profile's disciplines in the scope as for RCN calls, the 149 profiled topics had
  on average 4.4 High / 24.5 High+Medium matches, many from general
  machine-learning work; with the official scope 2.5 / 14.0 (RCN with profiles:
  1.5 / 9.8). Project owner's choice, 2026-10-29.
- **ERC / MSCA role rules** (`eu.ROLE_RULES`, shown as the inferred
  "project manager requirements" with the work programme as source, and
  `match_funding.eu_role_eligibility`):
  - ERC: PhD candidates → probably not eligible (a doctorate is required). StG
    (2–7 years after the PhD) and CoG (7–12) are checked against the years since
    the first UiS paper in the atlas, only as upper limits with wide margins (StG
    > 12 or a professor; CoG > 16), and AdG flags postdocs; all of these give only
    *check*. Lower limits are not checked: the atlas has no PhD dates and holds
    only UiS papers, so people recruited from elsewhere look more junior than they
    are.
  - MSCA PF and DN: UiS staff take part as **supervisor/host**; PhD candidates →
    probably not eligible, postdocs → *check*. MSCA SE: **staff exchange**, no
    career restriction.
  - The role is stored per call (`open_role`) and shown on the call page and in the
    profile's list of calls open to all fields.
- **Institution-level calls** (MSCA COFUND, European Researchers' Night): field
  `institution_level` with its basis; listed with a note to contact the research
  office, not matched or offered to researchers.

Not done yet (later phases): other sources (COST, NordForsk, Eureka, ERA-LEARN, Interreg; Phase 3),
CORDIS projects and external collaborators (Phase 4, from Scopus co-authors as
decided – needs clearance under DATA_POLICY.md), consortium suggestions (Phase 5).

## Scheduled update
See `docs/DEPLOY.md`: weekly `run_weekly.py` on a UiS server (Task Scheduler),
logging and optional publishing. A failing collector keeps the old data; a failing
processing stage stops before the website is rebuilt.

## Not done yet (deferred by the project owner, 2026-10-26)
External collaborators (e.g. via OpenAlex), suggested research teams, funding layer in
the network view, similar funded projects (Prosjektbanken), other funders.

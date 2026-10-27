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
| AI profile | `profile_calls.py` | open/planned calls → `data/interim/call_profiles.json` (needs `ANTHROPIC_API_KEY`; skipped otherwise) |
| Match | `match_funding.py` | calls + paper embeddings (`embed.py`) → `data/interim/funding_matches.json` |
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
domains, competencies (core / complementary / mandatory partner / optional), an
interpretation (explicit vs. plausible directions) and values for the AI-only
fields. Every "fact" must quote the call; quotes are checked against the text and
unverifiable facts are dropped (fields) or downgraded to interpretation (topics).
AI values are shown next to official values and never replace them.

### Matching (`match_funding.py`, settings in `config.FUNDING_MATCH`)
1. The call is split into aspects: AI competencies/methods/domains if a profile
   exists, else the thematic bullets of the call text (administrative sentences
   removed). A scope text (title, summary, themes) describes the whole call.
2. Each recent paper (last 5 years; corrections, editorials and notes excluded) is
   compared with scope and aspects using the atlas embedding model. Cosine
   similarity is mapped to relevance on a fixed scale (0.80 → 0, 0.86 → 1), so a
   call nobody fits produces no strong match. Distinctive title words that occur in
   ≤1 % of UiS papers (e.g. "seafood", "quantum") add up to 20 %. Recency weight
   halves every 3 years.
3. Score = 0.5 scope alignment + 0.3 aspect coverage + 0.2 amount of evidence.
   High ≥ 0.6, Medium ≥ 0.35. A ranking aid, not a probability of funding.
4. Eligibility is separate and evidence-based: only conditions stated in the call
   (UiS not allowed as project owner → "only as R&D partner"; early-career call +
   professor; experienced-researcher call + PhD/postdoc; doctorate required + PhD
   candidate; adjunct/emeritus/external → "check"). Otherwise "no restriction
   found", never "eligible". Suggested roles respect eligibility.
5. Internal collaborators: UiS researchers whose papers cover aspects the matched
   researcher lacks; existing co-authors (shared papers) and other departments are
   preferred. Always labelled as suggestions.

Not scored (no data yet): project experience, interdisciplinarity.

## Scheduled update
Every Saturday 01:00 on the UiS server (Windows Task Scheduler example):

```
schtasks /Create /TN "UiS Atlas weekly" /SC WEEKLY /D SAT /ST 01:00 ^
  /TR "C:\python-envs\.atlas\Scripts\python.exe C:\path\to\uis_atlas\pipeline\run_weekly.py"
```

Linux cron: `0 1 * * 6 /path/to/python /path/to/uis_atlas/pipeline/run_weekly.py`.
The built site is in `web/dist/`. A failing collector keeps the old data; a failing
processing stage stops before the website is rebuilt.

## Not done yet (deferred by the project owner, 2026-10-26)
External collaborators (e.g. via OpenAlex), suggested research teams, funding layer in
the network view, similar funded projects (Prosjektbanken), other funders.

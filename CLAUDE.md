# CLAUDE.md — Brief for Claude Code

You are helping build the **UiS Researcher Atlas**: a public dashboard where anyone can describe what they are looking for in plain words and get a ranked list of matching researchers from the six faculties of the University of Stavanger, each with a short overview.

**Read these before doing anything else:**
1. `docs/SPEC.md` — what we are building and how (architecture, ranking method, features, milestones)
2. `docs/DATA_POLICY.md` — binding rules on secrets, Scopus licensing and personal data

## How to work with me (the project owner)

- **Ask before starting any new milestone or making a significant decision.** Propose a short plan and wait for my approval. Small fixes within an approved task are fine.
- Work one milestone at a time (see SPEC §9). At the end of each, summarise what was done, what to check, and what is next.
- When something in the spec is unclear or listed under “Open decisions” (SPEC §10), ask me instead of guessing.
- Commit in small, logical steps with clear messages. Never push without my confirmation.

## Hard rules

- **Never** read, print, log or commit the contents of `.env`. Use `python-dotenv` to load keys.
- **Never** commit anything in `data/raw/` or `data/interim/`. Check `git status` before every commit.
- **Never** put abstracts or raw Scopus records into `data/public/` or the website. Only fields on the allow-list in `pipeline/export_public.py`.
- The Scopus API only works on the UiS network (campus/VPN) unless an institutional token is set. If the collector fails with 401/403, tell me instead of trying workarounds.
- Respect Scopus API quotas: the collector is resumable; do not write code that bypasses its throttling.
- The same embedding model and `query:`/`passage:` prefixes must be used in the pipeline and in the browser.

## Current state

- `pipeline/collect_scopus.py` — **done and tested in principle**; collects publications and department information from Scopus. Run: `python pipeline/collect_scopus.py`.
- `pipeline/collect_directory.py` — current staff from the public UiS employee directory (any network), including the work e-mail (read once per person from their profile page, cached in `data/raw/uis_directory/emails.json`).
- `pipeline/build_partners.py` — external partner institutions (and countries) of each researcher's co-authors, from the raw Scopus records already collected; published as `partners.json` (institutions only, never external people). Shown as a world map on profiles and as optional institution nodes in the network.
- `pipeline/collect_scopus_authors.py` — the atlas researchers' publications at other affiliations (since `ATLAS_FIRST_YEAR`) and their Scopus author metrics (documents, citations, h-index); merged by `collect_scopus.py --build-only`. Profiles count all affiliations and show how many are UiS papers; directory-unconfirmed people are still included on UiS papers only.
- `pipeline/collect_cristin.py` — staff status: for people the employee directory does not confirm (it leaves some staff out), Cristin tells whether the UiS affiliation is active (current) or ended (former); run by `run_all.py` between two `build_profiles.py` runs. Public field `staff` (current/former/unknown). Current staff found only in Cristin with an academic role are included like directory staff (`config.CRISTIN_INCLUDE_MIN`, `CRISTIN_ACADEMIC_TITLES`).
- `pipeline/collect_nva.py` — UiS output from NVA (Nasjonalt vitenarkiv, open API, any network): books, chapters, reports, artistic work, lectures, media. `build_profiles.py` merges it with Scopus (`nva.py`; shared outputs once, people linked by shared papers and the directory); NVA-only people get profile id `nva-<Cristin id>`. Profiles count every output category; "publications" are `config.PUBLICATION_CATEGORIES`. Merged papers: `data/interim/papers.json` (read by all later stages).
- `build_profiles.py`, `export_public.py` and the website (search, overview, network, profile; faculty/department picker) are implemented for all six faculties.
- `summarize.py` (needs `ANTHROPIC_API_KEY`) and `embed.py` are implemented; both use only papers from the last 5 years (`config.ACTIVE_YEARS`). Vectors stay local (not published).
- Funding Intelligence (RCN calls and EU Funding & Tenders topics via `collect_eu.py`/`eu.py`, matching, internal collaborators; password protected): `collect_rcn.py`, `build_calls.py`, `profile_calls.py`, `match_funding.py`, `export_funding.py`, web views `Funding`/`Call` and the profile section. See `docs/FUNDING.md`. `run_weekly.py` runs everything incl. the web build (optional Telegram message).
- Live at https://atlas.ux.uis.no: the shared server sensing4health.ux.uis.no (nginx container on port 8443 behind UiS IT's reverse proxy, weekly systemd user timer). Setup, update and status scripts in `deploy/`; everything in docs/SERVER.md. Never install a system nginx there (ports 80/443 belong to sensing4health).
- Nordic funders: `collect_nordic.py` (NordForsk and Nordic Energy Research, public website APIs, any network) and `nordic.py`; merged by `build_calls.py`. The Funding page filters funders with grouped checkboxes (docs/FUNDING.md).
- Project idea → calls: `call_vectors.py`, shortlist on the Funding page (model in the browser), `idea_match.py` for an AI-checked answer (docs/FUNDING.md).
- Project builder (`#/builder`, SPEC §5.6): selected researchers (the shortlist) and saved funding calls (`builder.ts`/`builder-core.ts`, browser only, change flags); all 3 milestones done: selection; "Prepare AI prompt" (`prompt.ts`/`prompt-core.ts`); project ideas (selection file → `project_ideas.py` → import, save, Word/Markdown export: `ideas-core.ts`, `docx.ts`, `projectIdeas.ts`).
- Find a team (a section of the Project builder, SPEC §5.5; `#/team` still works): `team_vectors.py` (public title + keyword vectors → `data/public/team.json`/`team.vectors.bin`), method in `team.py` mirrored by `web/src/team-core.ts` (keep both in step: `tests/test_team.py` checks parity with Node), `team_match.py` for an AI-checked team.
- What's new (SPEC §5.7): `build_changes.py` (first-seen state in `data/interim/first_seen.json`, public `changes.json` with profile ids only, new calls inside the encrypted funding index); bell in the header and page `#/new` (`news.ts`, `views/News.tsx`).
- Privacy page `#/privacy` (SPEC §5.8, DATA_POLICY §3a): no cookies, no tracking, no third parties. The language model and ONNX runtime are served from the site (`web/scripts/fetch-model.mjs`, run by `npm run dev`/`build`); the CSP allows `connect-src 'self'` only.

## Commands

The Python environment lives **outside the repo** (which is synced by OneDrive) at
`C:\python-envs\.atlas` (Python 3.12). Do not create a `.venv` inside the project.
When running commands non-interactively, call `C:\python-envs\.atlas\Scripts\python.exe` directly.

```powershell
py -3.12 -m venv C:\python-envs\.atlas                # once; already created
C:\python-envs\.atlas\Scripts\Activate.ps1            # activate (PowerShell)
pip install -r requirements.lock
Copy-Item .env.example .env                           # then fill in keys
python pipeline/collect_scopus.py                     # stage 1 (UiS network)
python pipeline/collect_scopus.py --build-only        # rebuild stage 1 output offline (after mapping changes)
python pipeline/collect_scopus_authors.py             # stage 1e: researchers' papers at other affiliations + Scopus metrics (UiS network)
python pipeline/collect_directory.py                  # stage 1b (UiS employee directory)
python pipeline/collect_nva.py                        # stage 1f (NVA research output, any network)
python pipeline/collect_rcn.py                        # stage 1c (RCN funding calls, any network)
python pipeline/collect_eu.py                         # stage 1d (EU funding topics, any network)
python pipeline/collect_nordic.py                     # stage 1g (NordForsk + Nordic Energy Research calls, any network)
python pipeline/run_all.py                            # stages 2–5 + funding stages
python pipeline/run_weekly.py                         # everything + web build (scheduled job)
python pipeline/idea_match.py "project idea"          # which open calls fit an idea (AI-checked; --no-ai)
python pipeline/team_match.py "project description"   # a UiS team for a project (AI-checked; --no-ai, --source public)
python pipeline/project_ideas.py selection.json       # project ideas from a Project builder selection (--dry-run)
pytest                                                # tests
cd web; npm install; npm run dev                      # website (once scaffolded)
```

## Conventions

- Python 3.11+, type hints, standard-library first. Paths and settings come from `pipeline/config.py`, never hard-coded in scripts.
- Each pipeline stage reads its inputs from files and writes its outputs to files, so stages can be rerun independently.
- Web: Vite + TypeScript, minimal dependencies, accessible HTML first (WCAG 2.1 AA).
- English for code, comments and docs. UI text in both Norwegian (bokmål) and English, kept in translation files.

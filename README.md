# UiS Researcher Atlas

Find the right researcher at the University of Stavanger. Describe what you are
looking for in your own words, and the atlas ranks researchers from the Faculty
of Science and Technology by how well their published work matches, with a
short overview of each person.

- **What and why:** [docs/SPEC.md](docs/SPEC.md)
- **Data, licensing and privacy rules:** [docs/DATA_POLICY.md](docs/DATA_POLICY.md)
- **Brief for Claude Code:** [CLAUDE.md](CLAUDE.md)

## Structure

```
uis-researcher-atlas/
├── CLAUDE.md               Brief for Claude Code (read automatically)
├── README.md
├── docs/
│   ├── SPEC.md             Full project specification
│   └── DATA_POLICY.md      Secrets, Scopus licence, GDPR
├── config/
│   ├── exclusions.json     Researchers who opted out
│   └── overrides.json      Manual corrections
├── pipeline/               Offline data pipeline (Python)
│   ├── config.py           All settings and paths
│   ├── collect_scopus.py   1. Scopus → data/raw/       (implemented)
│   ├── build_profiles.py   2. → researcher profiles    (stub)
│   ├── summarize.py        3. → AI overviews + tags    (stub)
│   ├── embed.py            4. → semantic vectors       (stub)
│   ├── export_public.py    5. → data/public/ (licence gate)  (stub)
│   └── run_all.py          Runs stages 2–5
├── data/
│   ├── raw/                Licensed Scopus data – local only, gitignored
│   ├── interim/            Licensed intermediate data – local only, gitignored
│   └── public/             Licence-safe data used by the website
├── web/                    Static website (Vite + TypeScript, to be built)
└── tests/                  Policy guards and search evaluation
```

## Quick start

The Python environment is kept outside the repository (which lives in OneDrive),
at `C:\python-envs\.atlas`, using Python 3.12:

```powershell
py -3.12 -m venv C:\python-envs\.atlas
C:\python-envs\.atlas\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env          # add your Scopus API key (never commit .env)
python pipeline/collect_scopus.py    # on the UiS network or VPN
```

Then open the project in Claude Code and start with milestone 1 in `docs/SPEC.md`.

## Deployment (GitHub Pages)

`.github/workflows/deploy-pages.yml` builds `web/` from the committed export in
`data/public/` and publishes it on every push to `main` (enable once under
Settings → Pages → Source: GitHub Actions). To update the online data, rerun
the pipeline locally, then commit and push `data/public/`.
For the weekly update on a UiS server, see `docs/DEPLOY.md`.

> **Status (2026-10-22):** the project owner decided to publish the test version
> with real data before the UiS Library and data protection officer have
> confirmed (docs/DATA_POLICY.md). The site carries a test-version notice and a
> `noindex` tag. Remove `noindex` only after confirmation.

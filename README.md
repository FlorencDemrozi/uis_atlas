# UiS Researcher Atlas

Find the right researcher at the University of Stavanger. Describe what you are
looking for in your own words, and the atlas ranks researchers from all six
faculties by how well their published work matches, with a short overview of each
person. The Project builder brings together researchers and funding calls for a
proposal, and turns a project description into a suggested team of UiS researchers
who together cover its parts. A password-protected Funding section
matches open RCN, EU and Nordic funding calls with researchers.

- **What and why:** [docs/SPEC.md](docs/SPEC.md)
- **Data, licensing and privacy rules:** [docs/DATA_POLICY.md](docs/DATA_POLICY.md)
- **Funding Intelligence:** [docs/FUNDING.md](docs/FUNDING.md)
- **Server and weekly update:** [docs/SERVER.md](docs/SERVER.md), [docs/DEPLOY.md](docs/DEPLOY.md)
- **Brief for Claude Code:** [CLAUDE.md](CLAUDE.md)

## Structure

```
uis_atlas/
├── CLAUDE.md                 Brief for Claude Code (read automatically)
├── docs/                     SPEC, DATA_POLICY, FUNDING, SERVER, DEPLOY
├── config/
│   ├── exclusions.json       Researchers who opted out
│   ├── overrides.json        Manual corrections
│   └── funding_overrides.json
├── pipeline/                 Offline data pipeline (Python); settings in config.py
│   ├── collect_*.py          1. Collectors → data/raw/: Scopus (UiS network), Scopus
│   │                            authors, NVA, UiS employee directory, RCN, EU, Nordic
│   ├── build_profiles.py     2. → researcher profiles (Scopus + NVA + directory)
│   ├── build_partners.py        → partner institutions of co-authors
│   ├── summarize.py          3. → AI overviews + tags (Anthropic API)
│   ├── embed.py              4. → semantic vectors (local only)
│   ├── export_public.py      5. → data/public/ (licence gate, allow-list)
│   ├── team_vectors.py          → "Build a team": public titles + keywords as vectors
│   ├── team.py, team_match.py   team method (mirrored in web/src/team-core.ts), AI-checked CLI
│   ├── build_calls.py … export_funding.py   funding calls, matching, encrypted export
│   ├── run_all.py            Runs stages 2–5 and the funding stages
│   └── run_weekly.py         Collectors + run_all + website build (scheduled job)
├── data/
│   ├── raw/                  Licensed and personal data – local only, gitignored
│   ├── interim/              Licensed intermediate data – local only, gitignored
│   └── public/               Licence-safe data used by the website (committed)
├── web/                      Static website (Vite + TypeScript + Preact)
├── deploy/                   Server scripts: setup, update, status, publish, systemd units
└── tests/                    Unit tests and the licence guard (test_policy.py)
```

## Quick start (laptop)

The Python environment is kept outside the repository (which lives in OneDrive),
at `C:\python-envs\.atlas`, using Python 3.12:

```powershell
py -3.12 -m venv C:\python-envs\.atlas
C:\python-envs\.atlas\Scripts\Activate.ps1
pip install -r requirements.lock
Copy-Item .env.example .env              # fill in the keys (never commit .env)
python pipeline/run_weekly.py --no-web   # all collectors + processing (Scopus: UiS network/VPN)
python pipeline/run_weekly.py --skip-scopus --no-web   # off the UiS network
pytest                                   # tests, incl. the licence guard
cd web; npm ci; npm run dev              # website at http://localhost:5173
```

Each stage can also be run on its own (`python pipeline/<stage>.py`); the full list
of commands is in [CLAUDE.md](CLAUDE.md) ("Commands"). `run_all.py` reruns the
processing stages from the data already collected.

## Deployment (GitHub Pages)

`.github/workflows/deploy-pages.yml` builds `web/` from the committed export in
`data/public/` and publishes it on every push to `main` (enable once under
Settings → Pages → Source: GitHub Actions). To update the online data, rerun
the pipeline locally, then commit and push `data/public/`.
The live atlas is served from the UiS server (next section); the Pages site keeps
the data last pushed from the laptop and can be turned off under Settings → Pages.

## Deployment: https://atlas.ux.uis.no

The atlas runs on **sensing4health.ux.uis.no**, a server shared with the
sensing4health site, behind UiS IT's reverse proxy (`atlas.ux.uis.no`). An nginx
container serves it on port 8443, and a systemd user timer updates it every week.
**Full setup, repair and troubleshooting: [docs/SERVER.md](docs/SERVER.md).** Never
install a system nginx on that server: ports 80/443 belong to sensing4health.

Everything the server needs is in `deploy/`; the three commands you need:

| Command (in `~/atlas/uis_atlas` on the server) | What it does |
|---|---|
| `deploy/status.sh` | Is the site up? Next run, last run, last success; end of the log if the last run failed |
| `deploy/update.sh` | Pull the latest code from GitHub, rebuild and publish the site, start a weekly run |
| `deploy/setup.sh` | First setup or repair: web server container, weekly timer, published site (safe to rerun) |

### Prerequisites

- Ubuntu 24.04 on the UiS network (Scopus only answers UiS addresses). One CPU core,
  2 GB free RAM and about 4 GB of free disk are enough.
- Outbound HTTPS to: `api.elsevier.com`, `api.anthropic.com`, `www.uis.no`,
  `api.nva.unit.no`, `www.forskningsradet.no`, `api.tech.ec.europa.eu`, `ec.europa.eu`,
  `www.nordforsk.org`, `www.nordicenergy.org`,
  `erc.europa.eu`, `marie-sklodowska-curie-actions.ec.europa.eu`, `huggingface.co`,
  `registry.npmjs.org`, `download.pytorch.org`, `raw.githubusercontent.com` (nvm),
  `github.com`, and `api.telegram.org` if Telegram messages are set up.
- Python 3.12 with the packages from `requirements-cpu.lock` (the same versions as
  `requirements.lock`, with PyTorch's CPU build: the server has no GPU), Node.js 22,
  Docker, rsync.

### Configuration and data

**Secrets** go in `.env` in the repository folder (mode 600, never committed):
`SCOPUS_API_KEY`, `ANTHROPIC_API_KEY`, `ATLAS_FUNDING_PASSWORD` and `ATLAS_FIRST_YEAR`
(the same values as on the laptop); optional `SCOPUS_INSTTOKEN`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID` (docs/DEPLOY.md, step 6).

**Data:** a new server can either collect everything (about 5 hours for the first
run) or start from the laptop's `data/raw/` and `data/interim/`. They hold licensed
and personal data: copy them only over the UiS network (scp/rsync), never by e-mail
or cloud storage. From the laptop, in PowerShell in the repository folder:

```powershell
scp -r data\raw data\interim u2929531@sensing4health.ux.uis.no:~/atlas/uis_atlas/data/
scp .env u2929531@sensing4health.ux.uis.no:~/atlas/uis_atlas/.env
```

### Weekly update

**Schedule:** every **Saturday at 01:00** (server time), by the user timer
`atlas-weekly.timer`; a run missed while the server was off starts at the next boot.
One update (about an hour):

1. collects Scopus, NVA, the UiS employee directory, RCN calls, EU topics and Nordic calls
   (a collector that fails is reported and the previous data is used);
2. rebuilds profiles, partner institutions, summaries, embeddings, the public
   export and the funding matches (`pipeline/run_all.py`);
3. stops before publishing if researchers or papers dropped by more than 15 % compared
   with the last successful run;
4. builds the website and, only if everything succeeded, publishes it
   (`deploy/publish.sh`). A failed run leaves the site unchanged.

| Task | Command |
|---|---|
| When did the last update succeed? | `deploy/status.sh` (or `cat logs/last-success.json`) |
| Did the last run fail, and why? | `deploy/status.sh` shows the end of its log |
| Run an update now | `systemctl --user start --no-block atlas-weekly.service` |
| Follow a run | `journalctl --user -u atlas-weekly -f` |
| Full log of a run | `ls -t logs/weekly-*.log \| head` then `less logs/weekly-<date>.log` |
| Next and previous run | `systemctl --user list-timers atlas-weekly.timer` |
| Change the time | `systemctl --user edit atlas-weekly.timer` (e.g. `OnCalendar=Sun *-*-* 03:00:00`) |
| Pause / resume | `systemctl --user disable --now atlas-weekly.timer` / `enable --now` |

Logs are in `logs/` (local only, last 26 runs kept); `logs/last-run.json` and
`logs/last-success.json` hold the time, outcome and log file of the last run and of
the last successful run. With `TELEGRAM_*` set in `.env`, each run also sends a short
message. Typical failures (Scopus 401/403 or quota, a missing key, "sharp drop") and
their fixes: docs/SERVER.md, "Troubleshooting". Backups of `data/raw/` and
`data/interim/`: docs/DEPLOY.md, "Backups".

> **Status (2026-10-22):** the project owner decided to publish the test version
> with real data before the UiS Library and data protection officer have
> confirmed (docs/DATA_POLICY.md). The site carries a test-version notice and a
> `noindex` tag. Remove `noindex` only after confirmation.

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
pip install -r requirements.lock
Copy-Item .env.example .env          # add your Scopus API key (never commit .env)
python pipeline/collect_scopus.py    # on the UiS network or VPN
```

Then open the project in Claude Code and start with milestone 1 in `docs/SPEC.md`.

## Deployment (GitHub Pages)

`.github/workflows/deploy-pages.yml` builds `web/` from the committed export in
`data/public/` and publishes it on every push to `main` (enable once under
Settings → Pages → Source: GitHub Actions). To update the online data, rerun
the pipeline locally, then commit and push `data/public/`.
For running the atlas on the UiS server instead, see the next section.

## Deployment on the UiS server (Ubuntu 24.04)

The server serves the website with nginx and updates itself every week with a
systemd timer. Everything it needs is in `deploy/`:

| File | What it does |
|---|---|
| `deploy/install.sh` | Installs the nginx site and the weekly timer (run once, with sudo) |
| `deploy/atlas-weekly.service` | One weekly update: `pipeline/run_weekly.py`, then copies `web/dist/` to the web folder |
| `deploy/atlas-weekly.timer` | Starts that update every Saturday at 01:00 |
| `deploy/nginx-atlas.conf` | The nginx site (compression, caching, security headers) |
| `deploy/status.sh` | Shows whether the site is up and when the last update ran and succeeded |

The commands below assume the repository is at `~/atlas/uis_atlas` and the Python
environment at `~/venvs/atlas`; run them as your own user (not root).

### 1. Prerequisites

- Ubuntu 24.04 on the UiS network (Scopus only answers UiS addresses), sudo rights.
  One CPU core, 2 GB free RAM and about 4 GB of free disk are enough.
- Outbound HTTPS to: `api.elsevier.com`, `api.anthropic.com`, `www.uis.no`,
  `api.nva.unit.no`, `www.forskningsradet.no`, `api.tech.ec.europa.eu`, `ec.europa.eu`,
  `erc.europa.eu`, `marie-sklodowska-curie-actions.ec.europa.eu`, `huggingface.co`,
  `registry.npmjs.org`, `download.pytorch.org`, `deb.nodesource.com`, `github.com`,
  and `api.telegram.org` if Telegram messages are set up.
- Inbound: port 80 (and 443 once HTTPS is set up) from the users' networks.

```bash
sudo apt update
sudo apt install -y git python3.12-venv nginx rsync curl
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -   # Node.js 22
sudo apt install -y nodejs
sudo ufw status | grep -q active && sudo ufw allow 'Nginx Full'      # only if the firewall is on
```

### 2. Code

```bash
mkdir -p ~/atlas && cd ~/atlas
git clone https://github.com/FlorencDemrozi/uis_atlas.git     # or: cd uis_atlas && git pull
cd ~/atlas/uis_atlas
```

### 3. Python environment and web dependencies

`requirements-cpu.lock` has the same package versions as the laptop, with the CPU
build of PyTorch (the server has no GPU; the GPU build would add about 5 GB).

```bash
python3.12 -m venv ~/venvs/atlas
~/venvs/atlas/bin/pip install -r requirements-cpu.lock
(cd web && npm ci)
```

### 4. Configuration and data

**Secrets** go in `.env` in the repository folder (never committed). Copy it from
the laptop (below) or create it from the template:

```bash
cp .env.example .env && chmod 600 .env && nano .env
```

It needs `SCOPUS_API_KEY`, `ANTHROPIC_API_KEY`, `ATLAS_FUNDING_PASSWORD` and
`ATLAS_FIRST_YEAR` (the same values as on the laptop); `SCOPUS_INSTTOKEN`,
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are optional (docs/DEPLOY.md, step 6).

**Data:** copy `data/raw/` and `data/interim/` from the laptop, so the first run does
not repeat months of Scopus collection, AI summaries and e-mail look-ups. They hold
licensed and personal data: copy them only over the UiS network (scp/rsync), never
by e-mail or cloud storage. From the laptop, in PowerShell in the repository folder
(replace `<server>` by the server's name, e.g. `sensing4health.uis.no`):

```powershell
scp -r data\raw data\interim u2929531@<server>:~/atlas/uis_atlas/data/
scp .env u2929531@<server>:~/atlas/uis_atlas/.env
```

Then on the server: `chmod 600 ~/atlas/uis_atlas/.env`.

### 5. Build the website once

The repository already holds the latest public data (`data/public/`), so the site
can go online before the first update:

```bash
(cd web && npm run build)        # -> web/dist/
```

### 6. Start: web server and weekly timer

```bash
sudo deploy/install.sh                     # optionally: sudo deploy/install.sh atlas.uis.no
```

The script checks steps 3–5, copies `web/dist/` to `/var/www/atlas`, installs
and enables the nginx site and the weekly timer, and prints the next scheduled run.
It is safe to run again (e.g. after a `git pull` that changed `deploy/`).

Then run the first update now instead of waiting for Saturday (30–60 minutes):

```bash
sudo systemctl start --no-block atlas-weekly.service
journalctl -u atlas-weekly -f              # follow it; Ctrl+C stops watching, not the update
```

### 7. Check that the atlas is running

```bash
curl -sI http://localhost/ | head -1                   # HTTP/1.1 200 OK
curl -s http://localhost/data/meta.json | head -c 120; echo   # "generated": date of the data
deploy/status.sh                                       # site, schedule, last run, last success
```

Then open `http://<server>/` in a browser on the UiS network and check: a search
returns researchers; a profile shows the e-mail and the "International
collaboration" map; the collaboration network loads; the Funding page opens with
the password. The browser console (F12) should show no errors.

### Weekly update

**Schedule:** every **Saturday at 01:00** (server time), by `atlas-weekly.timer`. A
run missed while the server was off starts at the next boot. One update:

1. collects Scopus, NVA, the UiS employee directory, RCN calls and EU topics
   (a collector that fails is reported and the previous data is used);
2. rebuilds profiles, partner institutions, summaries, embeddings, the public
   export and the funding matches (`pipeline/run_all.py`);
3. stops before publishing if researchers or papers dropped by more than 15 %;
4. builds the website, and only if everything succeeded copies it to
   `/var/www/atlas`. A failed run leaves the published site unchanged.

| Task | Command |
|---|---|
| Next and previous run | `systemctl list-timers atlas-weekly.timer` |
| Run an update now | `sudo systemctl start --no-block atlas-weekly.service` |
| Is an update running? | `systemctl status atlas-weekly.service` |
| When did the last update succeed? | `deploy/status.sh` (or `cat logs/last-success.json`) |
| Did the last run fail, and why? | `deploy/status.sh` shows the end of its log |
| Full log of a run | `ls -t logs/weekly-*.log \| head` then `less logs/weekly-<date>.log` |
| systemd's view (start, exit code) | `journalctl -u atlas-weekly -n 100 --no-pager` |
| Failed services | `systemctl --failed` |
| Change the time | `sudo systemctl edit atlas-weekly.timer` (e.g. `OnCalendar=Sun *-*-* 03:00:00`) |
| Pause / resume the weekly update | `sudo systemctl disable --now atlas-weekly.timer` / `enable --now` |

Logs are in `logs/` (local only, last 26 runs kept). `logs/last-run.json` and
`logs/last-success.json` hold the time, outcome and log file name of the last run
and of the last successful run. With `TELEGRAM_*` set in `.env`, each run also
sends a short message (OK, or the step that stopped it).

**If a run fails:** read the end of its log (`deploy/status.sh`). Typical causes:
Scopus 401/403 or quota (the site keeps the last data; the next run resumes), a
missing key in `.env`, or "sharp drop" (a collector returned too little; if the
drop is intended, run once by hand with
`~/venvs/atlas/bin/python pipeline/run_weekly.py --allow-drop`, then
`rsync -a --delete web/dist/ /var/www/atlas/`).

**New code:** `git pull`, then `~/venvs/atlas/bin/pip install -r requirements-cpu.lock`
and `(cd web && npm ci)` if those files changed, and `sudo deploy/install.sh` if
`deploy/` changed. The next weekly run builds and publishes the new site; to publish
at once, run an update now (table above).

**HTTPS:** ask UiS IT for a host name and certificate, then add a `listen 443 ssl`
server block (example in docs/DEPLOY.md, "Web server").

**GitHub Pages:** the server does not push data to GitHub, so the Pages site keeps
the last data pushed from the laptop. Turn it off (Settings → Pages) once the
server's site is in use. Backups of `data/raw/` and `data/interim/`:
docs/DEPLOY.md, "Backups".

> **Status (2026-10-22):** the project owner decided to publish the test version
> with real data before the UiS Library and data protection officer have
> confirmed (docs/DATA_POLICY.md). The site carries a test-version notice and a
> `noindex` tag. Remove `noindex` only after confirmation.

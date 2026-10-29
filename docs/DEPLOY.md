# Deploying the weekly update on a UiS (Linux) server

`pipeline/run_weekly.py` does the whole update in one command: collectors (Scopus,
UiS employee directory, RCN calls, EU topics), processing (`run_all.py`) and the
website build. This page sets it up as a weekly job on a Linux server at UiS.

## What a weekly run does

1. **Scopus**: after the first full search, each run searches only the last
   `config.SCOPUS_REFRESH_YEARS` (2) calendar years again. New papers are added,
   citation counts of recent papers are updated, older papers are kept. Detail
   lookups (departments) run only for authors who still need them. A typical run
   uses a few hundred API requests, well within the weekly quota.
2. **Employee directory, RCN calls and EU topics** are collected again (EU topics
   incrementally: only changed topics are re-read).
3. **Processing**: profiles, summaries (Anthropic API, only for changed researchers),
   embeddings, public export, funding calls, matching, encrypted funding export.
4. **Website** build to `web/dist/`.
5. **Publishing** (only with `--publish`): the licence guard (`tests/test_policy.py`)
   runs, then `data/public/` alone is committed and pushed, and the GitHub Pages
   workflow redeploys the site.

If a collector fails (e.g. Scopus 401/403 or quota), the previous data is used and
the problem is listed at the end. If a processing stage fails, the run stops and
nothing is built or published. All output goes to `logs/weekly-<date>.log` (local
only, last 26 runs kept).

## Server requirements

- A Linux server **on the UiS network** (Elsevier recognises the IP range), or an
  institutional token (`SCOPUS_INSTTOKEN`) from the UiS Library.
- Outbound HTTPS to: `api.elsevier.com`, `api.anthropic.com`, `www.uis.no`,
  `www.forskningsradet.no`, `api.tech.ec.europa.eu` and `ec.europa.eu` (EU topics),
  `huggingface.co` (first download of the embedding model), `registry.npmjs.org`
  (`npm ci`), `github.com` (only with `--publish`).
- Python 3.12 (with `venv`), Node.js 22, Git.
- A service account (e.g. `atlas`) that owns the files and runs the job.
- Disk: about 2 GB (raw Scopus and EU data, model cache, `node_modules`).

## One-time setup

```bash
# 1. Code
sudo -iu atlas
git clone https://github.com/FlorencDemrozi/uis_atlas.git ~/uis_atlas
cd ~/uis_atlas

# 2. Python environment (outside the repo) and web dependencies
python3.12 -m venv ~/venvs/atlas
~/venvs/atlas/bin/pip install -r requirements.txt
(cd web && npm ci)

# 3. Secrets: SCOPUS_API_KEY, ANTHROPIC_API_KEY, ATLAS_FUNDING_PASSWORD,
#    ATLAS_FIRST_YEAR (same value as on your laptop), SCOPUS_INSTTOKEN if needed
cp .env.example .env && chmod 600 .env && nano .env
```

4. **Copy the existing data** from your laptop, so the first run does not repeat
   the full Scopus download: `data/raw/` and `data/interim/` into the same folders
   on the server (e.g. `scp -r` or `rsync` over the UiS network). These contain
   licensed and personal data: never via e-mail or public cloud storage.

5. **Test run by hand** and read the log:

   ```bash
   cd ~/uis_atlas && ~/venvs/atlas/bin/python pipeline/run_weekly.py
   ```

## Publishing the result: choose one

**A. Push to GitHub Pages (current site).** Give the server push access with a
deploy key (*Settings → Deploy keys → Allow write access*) in `~atlas/.ssh/`, set the
remote to SSH (`git remote set-url origin git@github.com:FlorencDemrozi/uis_atlas.git`)
and `git config user.name` / `user.email`. Add `--publish` to the scheduled command.
Each run then pulls the latest code (`git pull --ff-only`) and pushes only
`data/public/`. Do not edit files on the server by hand; if the pull cannot
fast-forward, the run stops.

**B. Serve from a UiS web server.** Leave out `--publish` and point nginx (or
Apache) at `~atlas/uis_atlas/web/dist`, or copy that folder to the web server after
the run (`rsync -a --delete web/dist/ webhost:/var/www/atlas/`).

## Schedule

**cron** (every Saturday at 01:00, as the `atlas` user, `crontab -e`):

```cron
0 1 * * 6 cd $HOME/uis_atlas && $HOME/venvs/atlas/bin/python pipeline/run_weekly.py --publish >/dev/null 2>&1
```

Leave out `--publish` for option B. The log is in `logs/` either way.

**systemd timer** (alternative, survives reboots and missed runs):

```ini
# /etc/systemd/system/atlas-weekly.service
[Unit]
Description=UiS Researcher Atlas weekly update
[Service]
Type=oneshot
User=atlas
WorkingDirectory=/home/atlas/uis_atlas
ExecStart=/home/atlas/venvs/atlas/bin/python pipeline/run_weekly.py --publish

# /etc/systemd/system/atlas-weekly.timer
[Timer]
OnCalendar=Sat 01:00
Persistent=true
[Install]
WantedBy=timers.target
```

`sudo systemctl enable --now atlas-weekly.timer`; run once now with
`sudo systemctl start atlas-weekly.service`; status with `systemctl list-timers` and
`journalctl -u atlas-weekly`.

## Maintenance

- **New code**: with option A the server pulls before each run. With option B,
  run `git pull` (and `npm ci` if `web/package-lock.json` changed) on the server.
- **Scopus quota or access errors** are in the log; the site keeps the last data.
  Run `pipeline/collect_scopus.py` by hand later; it resumes where it stopped.
- **Full re-collection** (e.g. a new `ATLAS_FIRST_YEAR`): change it in `.env`; the
  next run searches the whole range again. `collect_eu.py --full` re-reads every
  EU topic.

# Deploying the weekly update on a UiS (Linux) server

> **The live server (https://atlas.ux.uis.no):** docs/SERVER.md has its complete setup,
> using the scripts in `deploy/` (`setup.sh`, `update.sh`, `status.sh`, `publish.sh`).
> This page has the background: what a run does, backups, maintenance. The nginx and
> systemd examples further down are generic (a server of its own, system nginx on
> ports 80/443); on the shared sensing4health server use docs/SERVER.md instead.

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
   incrementally: only changed topics are re-read). The work e-mail of each person
   is read from their UiS profile page only once (`data/raw/uis_directory/emails.json`):
   the first run reads about 1,100 pages (~30 min), later runs only those of new staff.
   Copy `emails.json` with the rest of `data/raw/` to skip that first pass.
3. **Processing**: profiles, summaries (Anthropic API, only for changed researchers),
   embeddings, public export, funding calls, matching, encrypted funding export.
4. **Sanity check**: if researchers or papers dropped by more than
   `config.MAX_COUNT_DROP` (15 %) compared with the last successful run
   (`logs/last-success-meta.json`; before the first one, the `data/public/` committed
   in git), the run stops before the website is rebuilt or published (a collector that
   silently returned too little). After an intended drop, run once with `--allow-drop`.
5. **Website** build to `web/dist/`.
6. **Publishing** (only with `--publish`): the licence guard (`tests/test_policy.py`)
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
  `www.nordforsk.org` and `www.nordicenergy.org` (Nordic calls), `api.nva.unit.no` (NVA),
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
~/venvs/atlas/bin/pip install -r requirements-cpu.lock   # CPU build of PyTorch (no GPU)
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

6. **Telegram message after each run (optional).** `run_weekly.py` sends one short
   message: "OK" or the step that stopped the run, collectors with problems, and
   counts (open calls, high/medium matches, AI profiles). No personal data, no keys.
   1. In Telegram, open **@BotFather**, send `/newbot` and follow the steps. It
      replies with a token like `123456789:AA…`: put it in `.env` as
      `TELEGRAM_BOT_TOKEN`.
   2. Open the new bot and send it any message (a bot can only write to people who
      have written to it first). For a group, add the bot to the group instead.
   3. Open `https://api.telegram.org/bot<token>/getUpdates` in a browser and copy
      `"chat":{"id": …}` into `.env` as `TELEGRAM_CHAT_ID` (groups have a negative id).
   4. Test: `~/venvs/atlas/bin/python pipeline/notify.py` should answer "Sent." and
      the message arrives. Without the two settings nothing is sent; a message that
      cannot be sent is noted in the log and never fails the run.

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
the run (`rsync -a --delete web/dist/ webhost:/var/www/atlas/`). Nothing is then
committed each week, so the git history stops growing with data. The sanity check
compares with the last successful run (`logs/last-success-meta.json`), so it works
without commits too.

The encrypted funding files are only rewritten when their content changes (same
password), so with option A a quiet week adds little to the git history.

### Web server (option B)

The site is static: HTML, JavaScript, JSON and one large `.wasm` file. Suggested
nginx server block (adapt names and certificate paths to the UiS setup):

```nginx
server {
    listen 443 ssl http2;
    server_name atlas.example.uis.no;                 # the name UiS IT assigns
    ssl_certificate     /etc/ssl/certs/atlas.pem;     # UiS certificate or certbot
    ssl_certificate_key /etc/ssl/private/atlas.key;
    root /var/www/atlas;                              # a copy of web/dist (rsync above)

    # Compression: the data files shrink about 3x (papers.json 17 MB -> 5 MB).
    gzip on;
    gzip_types application/json application/javascript text/css application/wasm image/svg+xml;
    gzip_min_length 1024;

    # Hashed file names never change: cache for a year. Data files keep their names
    # and change weekly: always revalidate (cheap 304 when unchanged).
    location /assets/ { add_header Cache-Control "public, max-age=31536000, immutable"; }
    location /data/   { add_header Cache-Control "no-cache"; }
    location = /index.html { add_header Cache-Control "no-cache"; }

    # Security headers (also repeat them inside each location block that has its
    # own add_header, as nginx does not inherit them there).
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy-Report-Only "default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; connect-src 'self' https://huggingface.co https://*.huggingface.co https://*.hf.co; img-src 'self' data:; style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; frame-ancestors 'none'" always;

    # Optional extra layer for the funding pages: only from the UiS network/VPN.
    # The files stay encrypted either way; this also stops outside password guessing.
    # location ~ ^/data/funding { allow 152.94.0.0/16; deny all; }   # check UiS ranges with IT
}
server { listen 80; server_name atlas.example.uis.no; return 301 https://$host$request_uri; }
```

The Content-Security-Policy starts as *Report-Only*: open every page (including
the idea search, which downloads the embedding model) and check the browser
console for blocked requests, then rename it to `Content-Security-Policy`. The
`'unsafe-inline'` for scripts is there for the small theme script in
`index.html`; it can be replaced by that script's hash.

### Backups

`data/raw/` and `data/interim/` are the only copy of months of quota-limited
Scopus collection and the AI summaries and call profiles (paid for). Everything in
`data/public/` and `web/dist/` can be rebuilt from them. Back them up weekly, after
the run, to UiS-managed storage (never public cloud: licensed and personal data),
e.g. with restic:

```bash
restic -r sftp:backup.uis.no:/atlas backup ~/uis_atlas/data/raw ~/uis_atlas/data/interim ~/uis_atlas/.env
restic -r sftp:backup.uis.no:/atlas forget --keep-weekly 8 --keep-monthly 12 --prune
```

Test a restore once. Ask UiS IT which backup target to use.

## Schedule

**cron** (every Saturday at 01:00, as the `atlas` user, `crontab -e`):

```cron
0 1 * * 6 cd $HOME/uis_atlas && $HOME/venvs/atlas/bin/python pipeline/run_weekly.py --publish >/dev/null 2>&1
```

Leave out `--publish` for option B. The log is in `logs/` either way. With cron,
a run that fails is only visible in the log, so set up the Telegram message (step
6 above) or prefer the systemd timer, whose failures show in `systemctl --failed`.

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
TimeoutStartSec=12h
# Hardening: the job may only write its own folder and caches.
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/home/atlas/uis_atlas /home/atlas/.cache /home/atlas/.npm

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

**Overlapping runs and hung steps.** Only one pipeline run can run at a time
(`run_weekly.py` and `run_all.py` share an OS file lock, `logs/.run.lock`): a second
run started meanwhile stops at once with a message. Each collector and each
`run_all.py` stage is stopped after `config.STEP_TIMEOUT` (4 h), the website build
after 30 min; the run then fails and reports it like any other failure.

## Maintenance

- **New code**: with option A the server pulls before each run. With option B,
  run `git pull` (and `npm ci` if `web/package-lock.json` changed) on the server.
- **Scopus quota or access errors** are in the log; the site keeps the last data.
  Run `pipeline/collect_scopus.py` by hand later; it resumes where it stopped.
- **Python packages**: install from `requirements-cpu.lock` on the server (the same
  exact versions as `requirements.lock` on the laptop and in CI, with PyTorch's CPU
  build, so the embeddings stay identical). After changing `requirements.txt`,
  regenerate both locks (commands at the top of each file).
- **"Sharp drop" stop**: read the log to see which collector returned too little.
  If the drop is intended (e.g. a changed inclusion rule), run again with
  `--allow-drop`.
- **Full re-collection** (e.g. a new `ATLAS_FIRST_YEAR`): change it in `.env`; the
  next run searches the whole range again. `collect_eu.py --full` re-reads every
  EU topic.

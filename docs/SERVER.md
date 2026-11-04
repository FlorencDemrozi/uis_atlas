# The atlas server: https://atlas.ux.uis.no

The atlas runs on **sensing4health.ux.uis.no**, a server it shares with the
sensing4health site. This page is the complete setup of that server, so it can be
checked, repaired or rebuilt from here alone. Background (what a weekly run does,
backups, the sanity check): docs/DEPLOY.md.

## How it fits together

```
browser ──https──> atlas.ux.uis.no ──> caddy.ux.uis.no (UiS IT reverse proxy, public certificate)
                                            │ https, port 8443
                                            v
                   sensing4health.ux.uis.no:8443  nginx container "atlas" ──> ~/atlas/site
                                                                                 ^ deploy/publish.sh
                   weekly timer (Sat 01:00) ──> pipeline/run_weekly.py ──> web/dist
```

- **Public address:** `atlas.ux.uis.no` is an alias of UiS IT's reverse proxy
  `caddy.ux.uis.no`, which holds the public certificate and forwards to port 8443 of
  this server. The proxy itself is run by UiS IT; changes to it go through them.
- **The server is shared.** sensing4health's own nginx and certbot run in Docker on
  ports 80 and 443 (managed by GitHub Actions from `JackHack96/sensing4health`). The
  atlas runs next to it and shares only its Let's Encrypt certificate, read-only.
  **Never change anything in the sensing4health repository or its containers, and do
  not install a system nginx on this server** (it would take ports 80/443).
- **Web server:** a separate nginx container (compose project `atlas`) listening only
  on port 8443, serving `~/atlas/site`, a copy of the built site.
- **Weekly update:** a systemd *user* timer under the account that owns the
  repository (no sudo after the first setup). A run publishes the new site to
  `~/atlas/site` only if everything succeeded, so a failed run or build never
  breaks the site.
- **HTTPS is required:** the Funding page decrypts in the browser (`crypto.subtle`),
  which browsers only allow on secure pages.
- **Node.js** comes from nvm in the home folder (Ubuntu's own Node is too old for Vite).

Everything server-specific is created by `deploy/setup.sh` from the files in the
repository's `deploy/` folder and lives outside the repository, so `git pull` always
works:

| What | Where |
|---|---|
| Repository (clone of GitHub `main`) | `~/atlas/uis_atlas` (with `.env`, mode 600) |
| Python 3.12 environment | `~/venvs/atlas` (from `requirements-cpu.lock`) |
| Node.js 22 | `~/.nvm` |
| nginx container: settings, compose file, generated `nginx.conf` | `~/atlas/deploy/` (`.env`, `docker-compose.yml`, `nginx.conf`) |
| Published site (what nginx serves) | `~/atlas/site` |
| Weekly service and timer | `~/.config/systemd/user/atlas-weekly.{service,timer}` |
| Logs | `~/atlas/uis_atlas/logs/` (`weekly-<date>.log`, `last-run.json`, `last-success.json`) |

Templates in the repository: `deploy/docker-compose.yml`, `deploy/nginx.conf.template`,
`deploy/atlas-weekly.service`, `deploy/atlas-weekly.timer`. Edit those, then run
`deploy/setup.sh`; never edit the generated files in `~/atlas/deploy/` by hand.

## Day-to-day

| Task | Command (in `~/atlas/uis_atlas`) |
|---|---|
| **Everything at a glance** (site, container, next run, last run, last success) | `deploy/status.sh` |
| **Update to the latest code on GitHub** | `deploy/update.sh` |
| Run a weekly update now | `systemctl --user start --no-block atlas-weekly.service` |
| Follow a run | `journalctl --user -u atlas-weekly -f` |
| Full log of a run | `ls -t logs/weekly-*.log \| head` then `less logs/weekly-<date>.log` |
| Last run / last success | `cat logs/last-run.json` / `cat logs/last-success.json` |
| Stop a run | `systemctl --user stop atlas-weekly.service` |
| Next and previous run | `systemctl --user list-timers atlas-weekly.timer` |
| Pause / resume the weekly update | `systemctl --user disable --now atlas-weekly.timer` / `enable --now` |
| nginx container | `cd ~/atlas/deploy && docker compose -p atlas ps` / `logs --tail 50` |
| Repair the setup (safe at any time) | `deploy/setup.sh` |

**Schedule:** every Saturday at 01:00 (server time). A run missed while the server
was off starts at the next boot. A weekly run takes about an hour.

### Updating to new code: `deploy/update.sh`

One command after new commits on GitHub `main`:

1. refuses to start while a weekly run is going (`--stop-run` stops it first; the
   collectors resume where they stopped);
2. pulls the code, keeping the server's own `data/public/` (git tracks that folder and
   every run rewrites it, so a plain `git pull` would refuse);
3. installs Python or web packages only if their lock files changed;
4. re-applies the server configuration and rebuilds and publishes the site, so the
   new code is live at once, still with the server's data;
5. starts a weekly run, which rebuilds the data with the new code (`--no-run` skips
   this).

## Setting the server up from scratch

### 1. Prerequisites

- An account with sudo rights that is in the docker group (`groups` lists `sudo docker`).
  Everything below runs as that account, not root.
- Port 8443 reachable from UiS IT's reverse proxy (`caddy.ux.uis.no`), and the
  outbound HTTPS hosts listed in the README ("Prerequisites") plus
  `raw.githubusercontent.com` (nvm).
- The sensing4health stack running (`docker ps` shows `nginx-nginx-1` and
  `nginx-certbot-1`): its certificate is used on port 8443.

```bash
sudo apt update && sudo apt install -y git python3.12-venv curl rsync
sudo loginctl enable-linger $USER          # user services keep running without a login
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
. ~/.nvm/nvm.sh && nvm install 22 && nvm alias default 22
```

### 2. Code, Python environment, web packages

```bash
mkdir -p ~/atlas && cd ~/atlas
git clone https://github.com/FlorencDemrozi/uis_atlas.git
cd ~/atlas/uis_atlas
python3.12 -m venv ~/venvs/atlas
~/venvs/atlas/bin/pip install -r requirements-cpu.lock
(. ~/.nvm/nvm.sh && cd web && npm ci)
```

### 3. Secrets

Copy `.env` from the laptop over the UiS network, never by e-mail or cloud storage.
On the laptop, in the repository folder:

```powershell
scp .env u2929531@sensing4health.ux.uis.no:~/atlas/uis_atlas/.env
```

The keys it needs are listed in the README ("Configuration and data").

### 4. Data: copy or collect fresh

Either copy `data/raw/` and `data/interim/` from the laptop (README, "Configuration
and data"), or let the first run collect everything. A fresh collection (done on
this server on 2026-10-30) takes about 5 hours: Scopus, e-mail look-ups, AI
summaries and call profiles. Each step has a 4-hour limit; if the first Scopus
collection hits it, start the run again and it resumes where it stopped.

### 5. Set up web server and weekly timer

```bash
cd ~/atlas/uis_atlas && deploy/setup.sh
```

The script checks steps 1–4 and stops with the exact command to run if something is
missing. Then it:

1. writes `~/atlas/deploy/.env` with the settings below (keeping values already there),
   finding the sensing4health certificate folder by itself;
2. builds the website if needed and publishes it to `~/atlas/site`;
3. generates `nginx.conf` (with the Content-Security-Policy hash of the page's inline
   script, computed from the published page) and starts or recreates the container;
4. installs and enables the weekly timer;
5. shows `deploy/status.sh`.

Settings in `~/atlas/deploy/.env`:

| Setting | Default | Meaning |
|---|---|---|
| `ATLAS_URL` | `https://atlas.ux.uis.no` | Public address (used by `status.sh`) |
| `ATLAS_PORT` | `8443` | Port nginx listens on (the reverse proxy forwards here) |
| `ATLAS_SITE_DIR` | `~/atlas/site` | Folder nginx serves |
| `ATLAS_CERT_NAME` | `sensing4health.ux.uis.no` | Certificate name under `live/` |
| `CERTBOT_CONF_DIR` | found from container `nginx-nginx-1` | sensing4health's `/etc/letsencrypt` folder |

To start the first weekly run at once: `systemctl --user start --no-block atlas-weekly.service`.

### 6. Check

```bash
deploy/status.sh
```

Both addresses should answer 200, the container should be "Up", and the timer should
show the next Saturday. In a browser: a search returns researchers; a profile shows the
e-mail and the collaboration map; the network loads; the Funding page opens with the
password. The browser console (F12) should show no errors. sensing4health must still
answer: `curl -sI https://sensing4health.ux.uis.no/ | head -1`.

## Troubleshooting

- **"The data could not be loaded … (403)" or a blank page with 403:** files in
  `~/atlas/site` are not readable for nginx (the server's umask is 077). Run
  `deploy/publish.sh` (it fixes the permissions), or `deploy/setup.sh`.
- **Blank page, "Content-Security-Policy" error in the browser console:** the page's
  inline script changed. `deploy/setup.sh` recomputes the hash.
- **`atlas.ux.uis.no` does not answer, but `deploy/status.sh` shows
  `https://localhost:8443/` → 200:** the problem is between UiS IT's proxy and this
  server (firewall, proxy configuration): contact UiS IT.
- **Neither answers:** `cd ~/atlas/deploy && docker compose -p atlas ps`, then
  `deploy/setup.sh`. If it stops at the certificate folder, sensing4health's stack may
  have moved it: remove `CERTBOT_CONF_DIR` from `~/atlas/deploy/.env` and run
  `deploy/setup.sh` again (it looks it up anew).
- **Certificate expired (between proxy and server):** the sensing4health certbot
  renews it; the atlas container reloads nginx every 12 hours. At once:
  `docker exec atlas-atlas-nginx-1 nginx -s reload`.
- **"Weekly update not started: another pipeline run is still in progress":** a run
  holds the lock (`logs/.run.lock`): wait for it, or stop it (table above).
- **Scopus 401/403, quota, "sharp drop":** docs/DEPLOY.md, "Maintenance". A run with
  `--allow-drop` by hand, then publish:
  `. ~/.nvm/nvm.sh && ~/venvs/atlas/bin/python pipeline/run_weekly.py --allow-drop && deploy/publish.sh`.
- **The weekly timer does not fire after a reboot:** `loginctl show-user $USER -p Linger`
  must say `Linger=yes` (`sudo loginctl enable-linger $USER`).

## Removing the atlas from the server

```bash
systemctl --user disable --now atlas-weekly.timer
cd ~/atlas/deploy && docker compose -p atlas down
rm -rf ~/atlas ~/venvs/atlas ~/.config/systemd/user/atlas-weekly.*
```

`data/raw/` and `data/interim/` are deleted with it: back them up first if they are
still needed (docs/DEPLOY.md, "Backups"). Ask UiS IT to remove `atlas.ux.uis.no` from
the reverse proxy.

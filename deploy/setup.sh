#!/usr/bin/env bash
# Set up (or repair) the UiS Atlas on the shared sensing4health server: nginx container
# on port 8443 behind https://atlas.ux.uis.no, and the weekly update as a systemd user
# timer. Safe to run again at any time; docs/SERVER.md explains every step.
# Run as the account that owns the repository (not root, no sudo):
#   deploy/setup.sh                        # set up / repair, build the website only if missing
#   deploy/setup.sh --build                # also rebuild the website from the current code
#   deploy/setup.sh --build --force-data   # rebuild even though the last weekly run failed
#   deploy/setup.sh --no-publish           # server configuration only (used by publish.sh)
# The website is built from data/public/. After a failed weekly run that folder may hold
# data that did not pass the run's checks (e.g. a sharp drop), so the site is then
# neither rebuilt nor republished unless --force-data is given.
# Settings live in ~/atlas/deploy/.env (created here; defaults below).
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
CONF=${ATLAS_DEPLOY_DIR:-$HOME/atlas/deploy}
VENV=${ATLAS_VENV:-$HOME/venvs/atlas}
UNITS=$HOME/.config/systemd/user

say() { printf '\n== %s ==\n' "$*"; }
fail() { echo "STOPPED: $*" >&2; exit 1; }

BUILD=no; FORCE=no; PUBLISH=yes
for arg in "$@"; do
  case $arg in
    --build) BUILD=yes ;;
    --force-data) FORCE=yes ;;
    --no-publish) PUBLISH=no ;;
    *) fail "unknown option $arg (see the top of deploy/setup.sh)" ;;
  esac
done
# True if there was no weekly run yet or the last one succeeded (logs/last-run.json).
last_run_ok() { [[ ! -f "$REPO/logs/last-run.json" ]] || grep -q '"ok": true' "$REPO/logs/last-run.json"; }

[[ $EUID -ne 0 ]] || fail "run it as your own account, not as root or with sudo."

# ---------------------------------------------------------------- 1. checks
say "Checks"
docker info >/dev/null 2>&1 \
  || fail "docker does not work without sudo. Run: sudo usermod -aG docker $USER  (then log out and in)"
[[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" == yes ]] \
  || fail "the weekly timer would stop at logout. Run once: sudo loginctl enable-linger $USER"
[[ -s "$HOME/.nvm/nvm.sh" ]] || fail "nvm is missing (docs/SERVER.md, step 1)."
set +eu; . "$HOME/.nvm/nvm.sh"; set -eu
major=$(node --version 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/')
[[ ${major:-0} -ge 22 ]] || fail "Node.js 22 is needed: nvm install 22 && nvm alias default 22"
command -v rsync >/dev/null || fail "rsync is missing: sudo apt install -y rsync"
[[ -x "$VENV/bin/python" ]] || fail "Python environment $VENV is missing (docs/SERVER.md, step 2)."
[[ -f "$REPO/.env" ]] || fail "$REPO/.env (the keys) is missing (docs/SERVER.md, step 3)."
chmod 600 "$REPO/.env"
[[ -d "$REPO/web/node_modules" ]] || (cd "$REPO/web" && npm ci)
echo "OK: docker, linger, Node.js $(node --version), Python environment, .env"

# ---------------------------------------------------------------- 2. settings
say "Settings ($CONF/.env)"
mkdir -p "$CONF"
ENVF=$CONF/.env
touch "$ENVF"
chmod 600 "$ENVF"
get() { grep -m1 "^$1=" "$ENVF" | cut -d= -f2- || true; }
put() { if grep -q "^$1=" "$ENVF"; then sed -i "s|^$1=.*|$1=$2|" "$ENVF"; else echo "$1=$2" >> "$ENVF"; fi; }
[[ -n "$(get ATLAS_URL)" ]] || put ATLAS_URL https://atlas.ux.uis.no
[[ -n "$(get ATLAS_PORT)" ]] || put ATLAS_PORT 8443
[[ -n "$(get ATLAS_SITE_DIR)" ]] || put ATLAS_SITE_DIR "$HOME/atlas/site"
[[ -n "$(get ATLAS_CERT_NAME)" ]] || put ATLAS_CERT_NAME sensing4health.ux.uis.no
if [[ -z "$(get CERTBOT_CONF_DIR)" ]]; then
  # The folder sensing4health's nginx container mounts at /etc/letsencrypt.
  dir=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/letsencrypt"}}{{.Source}}{{end}}{{end}}' \
        nginx-nginx-1 2>/dev/null || true)
  [[ -n "$dir" ]] || fail "could not find the sensing4health certificate folder (container nginx-nginx-1). \
Set CERTBOT_CONF_DIR=<folder> in $ENVF and run again."
  put CERTBOT_CONF_DIR "$dir"
fi
set -a; . "$ENVF"; set +a
[[ -d "$CERTBOT_CONF_DIR" ]] || fail "CERTBOT_CONF_DIR=$CERTBOT_CONF_DIR does not exist (moved by a sensing4health reinstall?)."
grep -v '^\s*#' "$ENVF"

# ---------------------------------------------------------------- 3. website
say "Website"
if [[ $PUBLISH == no ]]; then
  echo "Skipped (configuration only)."
elif last_run_ok || [[ $FORCE == yes ]]; then
  if [[ $BUILD == yes || ! -f "$REPO/web/dist/index.html" ]]; then
    (cd "$REPO/web" && npm run build)
  fi
  ATLAS_IN_SETUP=1 "$REPO/deploy/publish.sh"   # step 4 below updates the CSP hashes itself
elif [[ -f "$ATLAS_SITE_DIR/index.html" ]]; then
  echo "The last weekly run FAILED (deploy/status.sh shows why), so data/public/ may hold"
  echo "data that did not pass its checks: the website was not rebuilt and the published"
  echo "site stays as it is. The next successful weekly run publishes the current code."
  echo "To rebuild and publish now anyway: deploy/setup.sh --build --force-data"
else
  fail "nothing is published yet and the last weekly run failed (deploy/status.sh). \
Fix the run, or publish the current data anyway: deploy/setup.sh --build --force-data"
fi

# ---------------------------------------------------------------- 4. nginx container
say "nginx container (compose project atlas, port $ATLAS_PORT)"
# Content-Security-Policy: allow exactly the inline script(s) of the published page.
hashes=$("$VENV/bin/python" - "$ATLAS_SITE_DIR/index.html" <<'PY'
import base64, hashlib, re, sys
page = open(sys.argv[1], encoding="utf-8").read()
print(" ".join("'sha256-%s'" % base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()
               for s in re.findall(r"<script>(.*?)</script>", page, re.S)))
PY
)
before=$(cat "$CONF/nginx.conf" "$CONF/docker-compose.yml" 2>/dev/null | sha256sum)
for f in nginx.conf docker-compose.yml; do   # keep the hand-made originals once
  if [[ -f "$CONF/$f" && ! -f "$CONF/$f.before-setup" ]]; then cp "$CONF/$f" "$CONF/$f.before-setup"; fi
done
sed -e "s|@PORT@|$ATLAS_PORT|g" -e "s|@CERT_NAME@|$ATLAS_CERT_NAME|g" -e "s|@CSP_SCRIPT_HASHES@|$hashes|g" \
  "$REPO/deploy/nginx.conf.template" > "$CONF/nginx.conf"
cp "$REPO/deploy/docker-compose.yml" "$CONF/docker-compose.yml"
after=$(cat "$CONF/nginx.conf" "$CONF/docker-compose.yml" | sha256sum)
cd "$CONF"
if [[ "$before" != "$after" ]]; then
  # A single-file mount keeps showing the old file to a running container: recreate.
  docker compose -p atlas up -d --force-recreate
else
  docker compose -p atlas up -d
fi
sleep 2
docker compose -p atlas logs --tail 5 2>&1 | grep -F "[emerg]" && fail "nginx did not start (above)." || true

# ---------------------------------------------------------------- 5. weekly timer
say "Weekly update (systemd user timer)"
mkdir -p "$UNITS"
sed -e "s|@REPO@|$REPO|g" -e "s|@VENV@|$VENV|g" "$REPO/deploy/atlas-weekly.service" > "$UNITS/atlas-weekly.service"
cp "$REPO/deploy/atlas-weekly.timer" "$UNITS/atlas-weekly.timer"
systemctl --user daemon-reload
systemctl --user enable --now atlas-weekly.timer >/dev/null
echo "Installed. Next run:"
systemctl --user list-timers atlas-weekly.timer --no-pager | head -2

# ---------------------------------------------------------------- 6. check
"$REPO/deploy/status.sh"

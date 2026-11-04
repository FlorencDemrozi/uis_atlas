#!/usr/bin/env bash
# Install the UiS Researcher Atlas web server and weekly update on Ubuntu (24.04).
# Run from the repository, as the user who owns it, with sudo:
#   sudo deploy/install.sh [server-name]
# It installs and enables (does not start a pipeline run):
#   /etc/nginx/sites-available/atlas      nginx site serving $WEBROOT
#   /etc/systemd/system/atlas-weekly.*     weekly update, Saturdays 01:00
# Settings (environment variables, optional):
#   ATLAS_VENV     Python environment   (default: ~/venvs/atlas of that user)
#   ATLAS_WEBROOT  folder nginx serves  (default: /var/www/atlas)
# Safe to run again after changing these files.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "Run with sudo: sudo deploy/install.sh [server-name]"; exit 1; fi
RUN_USER=${SUDO_USER:-}
if [[ -z "$RUN_USER" || "$RUN_USER" == root ]]; then
  echo "Run it with sudo from your own account (the one that owns the repository), not as root."; exit 1
fi
REPO=$(cd "$(dirname "$0")/.." && pwd)
HOME_DIR=$(getent passwd "$RUN_USER" | cut -d: -f6)
VENV=${ATLAS_VENV:-$HOME_DIR/venvs/atlas}
WEBROOT=${ATLAS_WEBROOT:-/var/www/atlas}
SERVER_NAME=${1:-_}

echo "User: $RUN_USER  Repository: $REPO"
echo "Python environment: $VENV  Web folder: $WEBROOT  Server name: $SERVER_NAME"

# Checks: what must exist before the scheduled run can work.
missing=0
[[ -x "$VENV/bin/python" ]] || { echo "Missing: Python environment $VENV (README step 3)."; missing=1; }
[[ -f "$REPO/.env" ]] || { echo "Missing: $REPO/.env (README step 4)."; missing=1; }
[[ -d "$REPO/web/node_modules" ]] || { echo "Missing: web/node_modules – run 'cd web && npm ci' (README step 3)."; missing=1; }
command -v nginx >/dev/null || { echo "Missing: nginx (README step 1)."; missing=1; }
command -v rsync >/dev/null || { echo "Missing: rsync (README step 1)."; missing=1; }
[[ $missing -eq 0 ]] || exit 1

fill() {   # template -> destination, with the @...@ values filled in
  sed -e "s|@USER@|$RUN_USER|g" -e "s|@REPO@|$REPO|g" -e "s|@VENV@|$VENV|g" \
      -e "s|@WEBROOT@|$WEBROOT|g" -e "s|@HOME@|$HOME_DIR|g" -e "s|@SERVER_NAME@|$SERVER_NAME|g" "$1" > "$2"
}

# Web folder, owned by the user so the weekly run can update it; nginx only reads it.
mkdir -p "$WEBROOT" "$HOME_DIR/.cache" "$HOME_DIR/.npm"
chown "$RUN_USER": "$WEBROOT" "$HOME_DIR/.cache" "$HOME_DIR/.npm"
chmod 755 "$WEBROOT"
if [[ -f "$REPO/web/dist/index.html" ]]; then
  sudo -u "$RUN_USER" rsync -a --delete "$REPO/web/dist/" "$WEBROOT/"
  echo "Copied the current build (web/dist) to $WEBROOT."
else
  echo "No web/dist yet: build it (README step 6) before opening the site."
fi

# nginx
fill "$REPO/deploy/nginx-atlas.conf" /etc/nginx/sites-available/atlas
ln -sf /etc/nginx/sites-available/atlas /etc/nginx/sites-enabled/atlas
if [[ -L /etc/nginx/sites-enabled/default ]]; then
  rm /etc/nginx/sites-enabled/default   # Ubuntu's welcome page; it also claims default_server
  echo "Disabled nginx's default site (still in /etc/nginx/sites-available/default)."
fi
nginx -t
systemctl enable --now nginx
systemctl reload nginx

# Weekly update
fill "$REPO/deploy/atlas-weekly.service" /etc/systemd/system/atlas-weekly.service
cp "$REPO/deploy/atlas-weekly.timer" /etc/systemd/system/atlas-weekly.timer
systemctl daemon-reload
systemctl enable --now atlas-weekly.timer

echo
echo "Done. Next scheduled update:"
systemctl list-timers atlas-weekly.timer --no-pager
echo "Check the site: curl -sI http://localhost/ | head -1   Status: deploy/status.sh"

#!/usr/bin/env bash
# Publish the built website: copy web/dist to the folder nginx serves (ATLAS_SITE_DIR in
# ~/atlas/deploy/.env, default ~/atlas/site) and make it readable for nginx, which runs
# as another user (the server's umask is 077; the home folder stays 700).
# Run by the weekly service after a successful run, and by setup.sh / update.sh.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
CONF=${ATLAS_DEPLOY_DIR:-$HOME/atlas/deploy}
SITE=$(set -a; [[ -f "$CONF/.env" ]] && . "$CONF/.env"; echo "${ATLAS_SITE_DIR:-$HOME/atlas/site}")

[[ -f "$REPO/web/dist/index.html" ]] || { echo "No web/dist/index.html: build the website first." >&2; exit 1; }
mkdir -p "$SITE"
# New (hashed) files first, old ones removed only at the end, index.html last: pages
# that are open in a browser keep working while the copy runs.
rsync -a --delete-after --exclude /index.html "$REPO/web/dist/" "$SITE/"
cp "$REPO/web/dist/index.html" "$SITE/.index.html.new"
mv -f "$SITE/.index.html.new" "$SITE/index.html"
chmod -R a+rX "$SITE"
echo "Published web/dist to $SITE"

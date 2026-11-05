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

# The Content-Security-Policy allows the page's inline script by its hash. If a new
# build changed that script, the nginx configuration must follow, or the browser blocks
# it: rerun the configuration part of setup.sh (setup.sh does this itself when it calls us).
if [[ -z "${ATLAS_IN_SETUP:-}" && -f "$CONF/nginx.conf" ]]; then
  missing=$(python3 - "$SITE/index.html" "$CONF/nginx.conf" <<'PY'
import base64, hashlib, re, sys
page = open(sys.argv[1], encoding="utf-8").read()
conf = open(sys.argv[2], encoding="utf-8").read()
hashes = ["'sha256-%s'" % base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()
          for s in re.findall(r"<script>(.*?)</script>", page, re.S)]
print("yes" if any(h not in conf for h in hashes) else "")
PY
)
  if [[ -n "$missing" ]]; then
    echo "The page's inline script changed: updating the nginx Content-Security-Policy."
    "$REPO/deploy/setup.sh" --no-publish
  fi
fi

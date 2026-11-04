#!/usr/bin/env bash
# UiS Atlas: is the site up, when did the weekly update last run and succeed, and what
# went wrong if it failed. Run from anywhere: deploy/status.sh
REPO=$(cd "$(dirname "$0")/.." && pwd)
CONF=${ATLAS_DEPLOY_DIR:-$HOME/atlas/deploy}
if [[ -f "$CONF/.env" ]]; then set -a; . "$CONF/.env"; set +a; fi
URL=${ATLAS_URL:-https://atlas.ux.uis.no}
PORT=${ATLAS_PORT:-8443}
SITE=${ATLAS_SITE_DIR:-$HOME/atlas/site}

echo "== Website =="
code=$(curl -s -m 20 -o /dev/null -w "%{http_code}" "$URL/" || true)
echo "Public address  $URL/ -> ${code:-no answer}   (200 = OK)"
code=$(curl -sk -m 20 -o /dev/null -w "%{http_code}" "https://localhost:$PORT/" || true)
echo "This server     https://localhost:$PORT/ -> ${code:-no answer}   (200 = OK)"
state=$(docker ps --filter "name=atlas-atlas-nginx" --format '{{.Status}}' 2>/dev/null)
echo "nginx container ${state:-NOT RUNNING (cd $CONF && docker compose -p atlas up -d)}"
if [[ -f "$SITE/data/meta.json" ]]; then
  python3 - "$SITE/data/meta.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"Published data  generated {m['generated']}: {m['n_researchers']} researchers, {m['n_papers']} papers")
PY
else
  echo "Published data  none in $SITE (run deploy/setup.sh)"
fi

echo
echo "== Schedule =="
systemctl --user list-timers atlas-weekly.timer --no-pager 2>/dev/null | head -2
[[ "$(systemctl --user show atlas-weekly.service -p ActiveState --value 2>/dev/null)" == activating ]] \
  && echo "A weekly run is in progress now (journalctl --user -u atlas-weekly -f)."

echo
echo "== Last update =="
for f in last-run last-success; do
  if [[ -f "$REPO/logs/$f.json" ]]; then
    python3 - "$REPO/logs/$f.json" "$f" <<'PY'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
label = "Last run     " if sys.argv[2] == "last-run" else "Last success "
print(f"{label} {s['finished']}  {'OK' if s['ok'] else 'FAILED'}: {s['message']}  (log: logs/{s['log']})")
PY
  else
    echo "No logs/$f.json yet."
  fi
done

if [[ -f "$REPO/logs/last-run.json" ]] && grep -q '"ok": false' "$REPO/logs/last-run.json"; then
  log=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['log'])" "$REPO/logs/last-run.json")
  echo
  echo "== End of the failed run's log (logs/$log) =="
  tail -n 25 "$REPO/logs/$log"
fi
exit 0

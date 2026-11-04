#!/usr/bin/env bash
# UiS Researcher Atlas: is the site up, when did the weekly update last run and succeed,
# and what went wrong if it failed. Run from anywhere: deploy/status.sh
REPO=$(cd "$(dirname "$0")/.." && pwd)
WEBROOT=${ATLAS_WEBROOT:-/var/www/atlas}

echo "== Website =="
code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/ || true)
echo "http://localhost/ answers: ${code:-no answer} (200 = OK)"
if [[ -f "$WEBROOT/data/meta.json" ]]; then
  python3 - "$WEBROOT/data/meta.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"Published data generated {m['generated']}: {m['n_researchers']} researchers, {m['n_papers']} papers")
PY
else
  echo "No $WEBROOT/data/meta.json: the site has not been copied yet."
fi

echo
echo "== Schedule =="
systemctl list-timers atlas-weekly.timer --no-pager 2>/dev/null | head -2
state=$(systemctl show atlas-weekly.service -p ActiveState --value 2>/dev/null)
[[ "$state" == activating ]] && echo "An update is running now."

echo
echo "== Last update =="
for f in last-run last-success; do
  if [[ -f "$REPO/logs/$f.json" ]]; then
    python3 - "$REPO/logs/$f.json" "$f" <<'PY'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
label = "Last run    " if sys.argv[2] == "last-run" else "Last success"
print(f"{label}: {s['finished']}  {'OK' if s['ok'] else 'FAILED'} – {s['message']}  (log: logs/{s['log']})")
PY
  else
    echo "No logs/$f.json yet (no update has run$( [[ $f == last-success ]] && echo ' successfully'))."
  fi
done

if [[ -f "$REPO/logs/last-run.json" ]] && grep -q '"ok": false' "$REPO/logs/last-run.json"; then
  log=$(python3 -c "import json;print(json.load(open('$REPO/logs/last-run.json'))['log'])")
  echo
  echo "== End of the failed run's log (logs/$log) =="
  tail -n 25 "$REPO/logs/$log"
fi

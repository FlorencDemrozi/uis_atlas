#!/usr/bin/env bash
# Bring the server to the latest code on GitHub main, in one command:
#   deploy/update.sh              # pull, update packages if needed, rebuild and publish
#                                 # the site, then start a weekly run with the new code
#   deploy/update.sh --no-run     # the same, without starting the weekly run
#   deploy/update.sh --stop-run   # stop a weekly run that is in progress first
# The site switches to the new code at once, still with the server's own data; the
# weekly run started afterwards rebuilds the data with the new code (about an hour).
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
VENV=${ATLAS_VENV:-$HOME/venvs/atlas}
RUN=yes
STOP=no
for arg in "$@"; do
  case $arg in
    --no-run) RUN=no ;;
    --stop-run) STOP=yes ;;
    *) echo "Unknown option $arg (see the top of deploy/update.sh)"; exit 1 ;;
  esac
done
fail() { echo "STOPPED: $*" >&2; exit 1; }
cd "$REPO"

if systemctl --user is-active --quiet atlas-weekly.service; then
  [[ $STOP == yes ]] || fail "a weekly run is in progress. Wait for it, or run: deploy/update.sh --stop-run"
  systemctl --user stop atlas-weekly.service    # collectors resume where they stopped next time
  echo "Stopped the weekly run in progress."
fi

# data/public/ is tracked in git, and every run on the server rewrites it, so a pull
# would refuse to touch it. Keep the server's copy aside, pull, then put it back: the
# server's data stays the published data.
old=$(git rev-parse HEAD)
keep=$(mktemp -d)
cp -a data/public/. "$keep/"
git checkout -q -- data/public
git clean -fdq -- data/public
if ! git pull --ff-only; then
  cp -a "$keep/." data/public/
  fail "git pull failed (local code changes on the server? see 'git status')."
fi
rm -rf data/public && mkdir -p data/public && cp -a "$keep/." data/public/ && rm -rf "$keep"
changed=$(git diff --name-only "$old" HEAD)
echo "Updated $(git rev-parse --short "$old") -> $(git rev-parse --short HEAD) ($(wc -l <<<"$changed" | tr -d ' ') files changed)"

if grep -qx 'requirements-cpu.lock' <<<"$changed"; then
  echo "Python packages changed: installing…"
  "$VENV/bin/pip" install -q -r requirements-cpu.lock
fi
if grep -qx 'web/package-lock.json' <<<"$changed"; then
  echo "Web packages changed: installing…"
  (set +eu; . "$HOME/.nvm/nvm.sh"; set -eu; cd web && npm ci)
fi

# Re-applies the server configuration (it may have changed) and rebuilds the site.
"$REPO/deploy/setup.sh" --build

if [[ $RUN == yes ]]; then
  systemctl --user start --no-block atlas-weekly.service
  echo
  echo "Started a weekly run with the new code. Follow it: journalctl --user -u atlas-weekly -f"
fi

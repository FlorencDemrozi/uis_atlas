#!/usr/bin/env python3
"""
The scheduled update (e.g. every Saturday 01:00 on a UiS server): collect, rebuild
all JSON files, build the website. No database, no server process – just files.

  1. Collectors: Scopus (needs the UiS network; refreshes recent years once the full
     search is done; then the researchers' publications at other affiliations and their
     Scopus metrics, collect_scopus_authors.py), UiS employee directory, RCN calls, EU topics. A collector that fails is
     reported, and the previous raw data is used, so a temporary outage never
     empties the site.
  2. run_all.py: profiles, summaries, embeddings, public export, funding calls,
     call profiles, matching, encrypted funding export. Any failure stops here
     and the website is not rebuilt (it keeps the last good version).
  3. npm run build in web/ -> web/dist/ (copy or serve that folder).
  4. Only with --publish: licence guard (tests/test_policy.py), then commit
     data/public/ and push, so the GitHub Pages workflow redeploys the site.
  5. A short Telegram message (notify.py): finished or the step that stopped the run,
     collectors with problems and counts. Skipped if Telegram is not set up in .env.

Everything printed is also written to logs/weekly-<date>.log (local only).
Exit code 0 only if everything after step 1 succeeded; collector problems are
listed at the end. Run with the project's Python, e.g.:
  C:\\python-envs\\.atlas\\Scripts\\python.exe pipeline\\run_weekly.py
Options: --skip-scopus (off the UiS network), --no-web (data only), --publish.
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import notify
from config import LOGS, ROOT

HERE = Path(__file__).resolve().parent
WEB = ROOT / "web"
KEEP_LOGS = 26          # about half a year of weekly runs
LOG = None              # open log file, set in main()
FAILED: list[str] = []  # collectors that failed (old data used)


def say(text: str) -> None:
    print(text, flush=True)
    LOG.write(text + "\n")
    LOG.flush()


def run(cmd: list[str], cwd: Path | None = None) -> bool:
    say(f"\n=== {Path(cmd[-1]).name if cmd[0] == sys.executable else ' '.join(cmd[1:])} ===")
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        p = subprocess.Popen(cmd, cwd=cwd or ROOT, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             encoding="utf-8", errors="replace")
    except OSError as exc:
        say(f"Could not start: {exc}")
        return False
    for line in p.stdout:
        say(line.rstrip("\n"))
    return p.wait() == 0


def git(*args: str) -> bool:
    return run(["git", *args])


def publish() -> bool:
    """Commit data/public/ (and nothing else) and push it, after the licence guard."""
    if not run([sys.executable, "-m", "pytest", "-q", str(ROOT / "tests" / "test_policy.py")]):
        say("Licence guard failed: nothing was committed or pushed.")
        return False
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "data/public"], cwd=ROOT).returncode == 0 \
            and not subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "data/public"],
                                   cwd=ROOT, capture_output=True, text=True).stdout.strip():
        say("\ndata/public/ unchanged: nothing to publish.")
        return True
    message = f"Data: weekly update {datetime.now():%Y-%m-%d}"
    return git("add", "--", "data/public") and git("commit", "-m", message, "--", "data/public") \
        and git("push")


def prune_logs() -> None:
    for old in sorted(LOGS.glob("weekly-*.log"))[:-KEEP_LOGS]:
        old.unlink()


def main() -> None:
    global LOG
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--skip-scopus", action="store_true", help="do not contact Scopus (off the UiS network)")
    ap.add_argument("--no-web", action="store_true", help="update the data only, do not build the website")
    ap.add_argument("--publish", action="store_true",
                    help="commit and push data/public/ so GitHub Pages redeploys (server with push access)")
    args = ap.parse_args()
    sys.stdout.reconfigure(errors="replace")   # a name the console cannot show must not stop the run
    started = datetime.now()
    LOGS.mkdir(parents=True, exist_ok=True)
    LOG = (LOGS / f"weekly-{started:%Y-%m-%d_%H%M}.log").open("w", encoding="utf-8")
    prune_logs()
    say(f"Weekly update started {started:%Y-%m-%d %H:%M}")

    if args.publish and not git("pull", "--ff-only"):
        stop("Weekly update stopped: could not update the repository (git pull --ff-only).")

    collectors = ["collect_directory.py", "collect_rcn.py", "collect_eu.py"]
    if not args.skip_scopus:
        # UiS publications, then the same researchers' publications elsewhere and their
        # Scopus metrics, then the combined atlas_data.json again (offline).
        collectors[:0] = ["collect_scopus.py", "collect_scopus_authors.py", "collect_scopus.py --build-only"]
    FAILED[:] = [c for c in collectors if not run([sys.executable, str(HERE / c.split()[0]), *c.split()[1:]])]
    failed = FAILED

    if not run([sys.executable, str(HERE / "run_all.py")]):
        stop("Weekly update stopped: a processing stage failed (see above). The website was not rebuilt.")
    if not args.no_web:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm or not run([npm, "run", "build"], cwd=WEB):
            stop("Weekly update: data updated, but the website build failed.")
    if args.publish and not publish():
        stop("Weekly update: data updated, but publishing failed (see above).")

    took = (datetime.now() - started).seconds // 60
    say(f"\nWeekly update finished in {took} min." + (f" Collectors with problems (old data used): "
                                                     f"{', '.join(failed)}." if failed else ""))
    tell(f"UiS Atlas weekly update OK ({took} min)" + (" – with collector problems" if failed else ""))


def tell(headline: str) -> None:
    """Telegram message: headline, collectors with problems, counts, log file name."""
    lines = [headline]
    if FAILED:
        lines.append("Collectors with problems (old data used): " + ", ".join(FAILED))
    lines += notify.counts() + [f"Log: {Path(LOG.name).name}"]
    error = notify.send("\n".join(lines))
    if error:
        say(error)


def stop(message: str) -> None:
    say(message)
    tell("UiS Atlas weekly update FAILED: " + message)
    sys.exit(1)


if __name__ == "__main__":
    main()

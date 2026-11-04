#!/usr/bin/env python3
"""
The scheduled update (e.g. every Saturday 01:00 on a UiS server): collect, rebuild
all JSON files, build the website. No database, no server process – just files.

  1. Collectors: Scopus (needs the UiS network; refreshes recent years once the full
     search is done; then the researchers' publications at other affiliations and their
     Scopus metrics, collect_scopus_authors.py), NVA (collect_nva.py), UiS employee
     directory, RCN calls, EU topics. A collector that fails is
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
Options: --skip-scopus (off the UiS network), --no-web (data only), --publish,
--allow-drop (accept a sharp drop in researchers or papers, which otherwise stops
the run before the website is rebuilt; see config.MAX_COUNT_DROP).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import notify
import runlock
from config import LOGS, MAX_COUNT_DROP, ROOT, STEP_TIMEOUT, WEB_BUILD_TIMEOUT

HERE = Path(__file__).resolve().parent
WEB = ROOT / "web"
KEEP_LOGS = 26          # about half a year of weekly runs
LOG = None              # open log file, set in main()
FAILED: list[str] = []  # collectors that failed (old data used)


def say(text: str) -> None:
    print(text, flush=True)
    LOG.write(text + "\n")
    LOG.flush()


def run(cmd: list[str], cwd: Path | None = None, timeout: float | None = STEP_TIMEOUT) -> bool:
    """Run one step, its output going to the console and the log. A step still running
    after `timeout` seconds is killed and counts as failed (None: no limit)."""
    say(f"\n=== {Path(cmd[-1]).name if cmd[0] == sys.executable else ' '.join(cmd[1:])} ===")
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        p = subprocess.Popen(cmd, cwd=cwd or ROOT, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             encoding="utf-8", errors="replace")
    except OSError as exc:
        say(f"Could not start: {exc}")
        return False
    timed_out = threading.Event()

    def kill() -> None:
        timed_out.set()
        p.kill()

    timer = threading.Timer(timeout, kill) if timeout else None
    if timer:
        timer.daemon = True
        timer.start()
    try:
        for line in p.stdout:
            say(line.rstrip("\n"))
        code = p.wait()
    finally:
        if timer:
            timer.cancel()
    if timed_out.is_set():
        say(f"Stopped: still running after {timeout // 60:.0f} min (time limit).")
        return False
    return code == 0


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


def count_drops(old: dict, new: dict, max_drop: float = MAX_COUNT_DROP) -> list[str]:
    """Counts in meta.json that fell by more than max_drop (e.g. "papers 56418 -> 30000")."""
    drops = []
    for key, label in (("n_researchers", "researchers"), ("n_papers", "papers")):
        before, after = old.get(key) or 0, new.get(key) or 0
        if before and after < before * (1 - max_drop):
            drops.append(f"{label} {before} -> {after}")
    return drops


def sanity_check() -> list[str]:
    """Compare the new data/public/meta.json with the last committed one."""
    committed = subprocess.run(["git", "show", "HEAD:data/public/meta.json"], cwd=ROOT,
                               capture_output=True, text=True, encoding="utf-8")
    new_meta = ROOT / "data" / "public" / "meta.json"
    if committed.returncode != 0 or not new_meta.exists():
        return []   # first export: nothing to compare with
    return count_drops(json.loads(committed.stdout), json.loads(new_meta.read_text(encoding="utf-8")))


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
    ap.add_argument("--allow-drop", action="store_true",
                    help="build and publish even if researchers or papers dropped sharply (an intended change)")
    args = ap.parse_args()
    sys.stdout.reconfigure(errors="replace")   # a name the console cannot show must not stop the run
    started = datetime.now()
    LOGS.mkdir(parents=True, exist_ok=True)
    LOG = (LOGS / f"weekly-{started:%Y-%m-%d_%H%M}.log").open("w", encoding="utf-8")
    prune_logs()
    say(f"Weekly update started {started:%Y-%m-%d %H:%M}")
    if not runlock.acquire():
        stop("Weekly update not started: another pipeline run is still in progress.")

    if args.publish and not git("pull", "--ff-only"):
        stop("Weekly update stopped: could not update the repository (git pull --ff-only).")

    collectors = ["collect_nva.py", "collect_directory.py", "collect_rcn.py", "collect_eu.py"]
    if not args.skip_scopus:
        # UiS publications, then the same researchers' publications elsewhere and their
        # Scopus metrics, then the combined atlas_data.json again (offline).
        collectors[:0] = ["collect_scopus.py", "collect_scopus_authors.py", "collect_scopus.py --build-only"]
    FAILED[:] = [c for c in collectors if not run([sys.executable, str(HERE / c.split()[0]), *c.split()[1:]])]
    failed = FAILED

    if not run([sys.executable, str(HERE / "run_all.py")], timeout=None):   # each stage has its own limit
        stop("Weekly update stopped: a processing stage failed (see above). The website was not rebuilt.")
    drops = sanity_check()
    if drops and not args.allow_drop:
        stop(f"Weekly update stopped: sharp drop compared with the published data ({'; '.join(drops)}). "
             "The website was not rebuilt or published. If this is intended, run again with --allow-drop; "
             "otherwise check the collectors in the log.")
    elif drops:
        say(f"Sharp drop accepted with --allow-drop: {'; '.join(drops)}.")
    if not args.no_web:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm or not run([npm, "run", "build"], cwd=WEB, timeout=WEB_BUILD_TIMEOUT):
            stop("Weekly update: data updated, but the website build failed.")
    if args.publish and not publish():
        stop("Weekly update: data updated, but publishing failed (see above).")

    took = int((datetime.now() - started).total_seconds() // 60)
    say(f"\nWeekly update finished in {took} min." + (f" Collectors with problems (old data used): "
                                                     f"{', '.join(failed)}." if failed else ""))
    record(True, f"Finished in {took} min" + (" (collector problems: old data used)" if failed else ""))
    tell(f"UiS Atlas weekly update OK ({took} min)" + (" – with collector problems" if failed else ""))


def record(ok: bool, message: str) -> None:
    """logs/last-run.json after every run, logs/last-success.json after a successful one
    (read by deploy/status.sh): when it finished, the outcome and the log file."""
    status = {"finished": datetime.now().isoformat(timespec="seconds"), "ok": ok,
              "message": message, "log": Path(LOG.name).name, "collector_problems": FAILED}
    text = json.dumps(status, ensure_ascii=False, indent=1)
    (LOGS / "last-run.json").write_text(text, encoding="utf-8")
    if ok:
        (LOGS / "last-success.json").write_text(text, encoding="utf-8")


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
    record(False, message)
    tell("UiS Atlas weekly update FAILED: " + message)
    sys.exit(1)


if __name__ == "__main__":
    main()

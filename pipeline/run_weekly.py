#!/usr/bin/env python3
"""
The scheduled update (e.g. every Saturday 01:00 on a UiS server): collect, rebuild
all JSON files, build the website. No database, no server process – just files.

  1. Collectors: Scopus (needs the UiS network), UiS employee directory, RCN calls.
     A collector that fails is reported, and the previous raw data is used, so a
     temporary outage never empties the site.
  2. run_all.py: profiles, summaries, embeddings, public export, funding calls,
     call profiles, matching, encrypted funding export. Any failure stops here
     and the website is not rebuilt (it keeps the last good version).
  3. npm run build in web/ -> web/dist/ (copy or serve that folder).

Exit code 0 only if everything after step 1 succeeded; collector problems are
listed at the end. Run with the project's Python, e.g.:
  C:\\python-envs\\.atlas\\Scripts\\python.exe pipeline\\run_weekly.py
Options: --skip-scopus (off the UiS network), --no-web (data only).
"""
import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEB = HERE.parent / "web"


def run(cmd: list[str], cwd: Path | None = None) -> bool:
    print(f"\n=== {Path(cmd[-1]).name if cmd[0] == sys.executable else ' '.join(cmd[1:])} ===", flush=True)
    return subprocess.run(cmd, cwd=cwd).returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--skip-scopus", action="store_true", help="do not contact Scopus (off the UiS network)")
    ap.add_argument("--no-web", action="store_true", help="update the data only, do not build the website")
    args = ap.parse_args()
    started = datetime.now()

    collectors = ["collect_directory.py", "collect_rcn.py"]
    if not args.skip_scopus:
        collectors.insert(0, "collect_scopus.py")
    failed = [c for c in collectors if not run([sys.executable, str(HERE / c)])]

    if not run([sys.executable, str(HERE / "run_all.py")]):
        sys.exit("Weekly update stopped: a processing stage failed (see above). The website was not rebuilt.")
    if not args.no_web:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm or not run([npm, "run", "build"], cwd=WEB):
            sys.exit("Weekly update: data updated, but the website build failed.")

    took = (datetime.now() - started).seconds // 60
    print(f"\nWeekly update finished in {took} min." + (f" Collectors with problems (old data used): "
                                                       f"{', '.join(failed)}." if failed else ""))


if __name__ == "__main__":
    main()

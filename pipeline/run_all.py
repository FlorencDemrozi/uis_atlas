#!/usr/bin/env python3
"""Run the processing stages in order: researchers (stages 2–5), then funding calls.
The collectors (collect_scopus.py, collect_directory.py, collect_rcn.py) are run
separately or through run_weekly.py, because Scopus needs the UiS network."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGES = [
    "build_profiles.py", "summarize.py", "embed.py", "export_public.py",          # researchers
    "build_calls.py", "profile_calls.py", "match_funding.py", "export_funding.py",  # funding calls
]

for stage in STAGES:
    print(f"\n=== {stage} ===")
    result = subprocess.run([sys.executable, str(HERE / stage)])
    if result.returncode != 0:
        sys.exit(f"Stopped: {stage} failed.")
print("\nPipeline complete. Public data is in data/public/.")

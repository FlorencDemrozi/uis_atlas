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
    # funding calls: matching on the official text first, so profile_calls.py can pick the
    # EU topics worth an AI profile; the second pass redoes only calls whose profile changed.
    "build_calls.py", "match_funding.py", "profile_calls.py", "match_funding.py --changed-profiles",
    "call_vectors.py",  # idea search: call texts as vectors (cached by text)
    "export_funding.py",
]

for stage in STAGES:
    print(f"\n=== {stage} ===")
    script, *args = stage.split()
    result = subprocess.run([sys.executable, str(HERE / script), *args])
    if result.returncode != 0:
        sys.exit(f"Stopped: {stage} failed.")
print("\nPipeline complete. Public data is in data/public/.")

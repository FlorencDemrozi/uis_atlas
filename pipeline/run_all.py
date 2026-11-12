#!/usr/bin/env python3
"""Run the processing stages in order: researchers (stages 2–5), then funding calls.
The collectors (collect_scopus.py, collect_nva.py, collect_directory.py, collect_rcn.py, ...) are run
separately or through run_weekly.py, because Scopus needs the UiS network."""
import subprocess
import sys
from pathlib import Path

import config
import runlock

HERE = Path(__file__).resolve().parent
STAGES = [
    # collect_cristin.py: is the UiS affiliation of people the directory does not confirm
    # still active? (open API, any network; cached). build_profiles.py lists whom to check
    # and runs again to use the answers.
    "build_profiles.py", "collect_cristin.py", "build_profiles.py",
    "build_partners.py", "summarize.py", "embed.py", "export_public.py",          # researchers
    "team_vectors.py",  # Build a team: public titles + keywords as vectors (cached by text)
    # funding calls: matching on the official text first, so profile_calls.py can pick the
    # EU topics worth an AI profile; the second pass redoes only calls whose profile changed.
    "build_calls.py", "match_funding.py", "profile_calls.py", "match_funding.py --changed-profiles",
    "call_vectors.py",  # idea search: call texts as vectors (cached by text)
    "build_changes.py",  # what's new: researchers and calls first seen (public ids + funding index)
    "export_funding.py",
]

if not runlock.acquire():
    sys.exit("Another pipeline run is in progress (run_weekly.py or run_all.py): not started.")
for stage in STAGES:
    print(f"\n=== {stage} ===")
    script, *args = stage.split()
    try:
        result = subprocess.run([sys.executable, str(HERE / script), *args], timeout=config.STEP_TIMEOUT)
    except subprocess.TimeoutExpired:
        sys.exit(f"Stopped: {stage} took longer than {config.STEP_TIMEOUT // 60} min.")
    if result.returncode != 0:
        sys.exit(f"Stopped: {stage} failed.")
print("\nPipeline complete. Public data is in data/public/.")

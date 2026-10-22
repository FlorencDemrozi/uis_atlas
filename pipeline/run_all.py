#!/usr/bin/env python3
"""Run pipeline stages 2–5 in order. Stage 1 (collect_scopus.py) is run separately
because it needs the UiS network."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGES = ["build_profiles.py", "summarize.py", "embed.py", "export_public.py"]

for stage in STAGES:
    print(f"\n=== {stage} ===")
    result = subprocess.run([sys.executable, str(HERE / stage)])
    if result.returncode != 0:
        sys.exit(f"Stopped: {stage} failed.")
print("\nPipeline complete. Public data is in data/public/.")

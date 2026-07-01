#!/usr/bin/env python
"""
Run the whole trace-intelligence pipeline in the CORRECT order.

Order matters — `validate_permits` must run BEFORE `calibration` (calibration
reads corridor_permit_match). Running out of order caused a stale-verdict join in
the past (see AUDIT.md). This runner makes the order explicit and hard to break.

The AI Corridor Analyst (Phase B, one corridor at a time) is NOT run here — it is
manual/inline. After it: `aggregate_corridors.py`.

Run:  & "D:\\plotting\\ana\\python.exe" src\\run_all.py
"""
import os, sys, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
PY = sys.executable

# (script, always-run?) — pull_cache only if the point cache is missing.
STAGES = [
    ("pull_cache.py", not os.path.exists(os.path.join(DATA, "points.pkl.gz"))),
    ("segment.py", True),
    ("stops.py", True),
    ("match_runs.py", True),
    ("corridors.py", True),
    ("validate_permits.py", True),   # BEFORE calibration
    ("calibration.py", True),        # reads corridor_permit_match
    ("speed_layer.py", True),
    ("build_evidence.py", True),
    ("longtail.py", True),           # diagnostic: decompose the uncovered tail
]


def main():
    for script, run in STAGES:
        if not run:
            print(f"== skip {script} (cache present) =="); continue
        print(f"\n===== {script} =====")
        r = subprocess.run([PY, os.path.join(HERE, script)])
        if r.returncode != 0:
            print(f"!! {script} failed (exit {r.returncode}) — stopping."); sys.exit(r.returncode)
    print("\nPipeline done. Next: AI Corridor Analyst (manual), then aggregate_corridors.py.")


if __name__ == "__main__":
    main()

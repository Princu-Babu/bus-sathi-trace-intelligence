#!/usr/bin/env python
"""
Corridor Analyst — resume pointer. Prints the next corridor(s) in the queue that
do NOT yet have a verdict file (analyst/verdicts/C<id>.json). This is the exact
resume point after a shutdown or a new session.

Run:  & "D:\\plotting\\ana\\python.exe" src\\next_corridor.py [N]
"""
import os, sys, csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYST = os.path.join(ROOT, "analyst")
VERD = os.path.join(ANALYST, "verdicts")
QUEUE = os.path.join(ANALYST, "corridor_queue.csv")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    done = {f[1:-5] for f in os.listdir(VERD)} if os.path.isdir(VERD) else set()
    rows = list(csv.DictReader(open(QUEUE, encoding="utf-8"))) if os.path.exists(QUEUE) else []
    total = len(rows)
    remaining = [r for r in rows if r["corridor_id"] not in done]
    print(f"DONE {total - len(remaining)} / {total}   REMAINING {len(remaining)}")
    for r in remaining[:n]:
        print(f"  next: C{r['corridor_id']}  ({r['n_runs']} runs, {r['n_drivers']} drivers)  "
              f"-> read analyst/evidence/C{r['corridor_id']}.json + .png")
    if not remaining:
        print("  ALL DONE -> run aggregate_corridors.py")


if __name__ == "__main__":
    main()

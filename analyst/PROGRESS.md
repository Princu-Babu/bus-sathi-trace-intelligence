# Corridor Analyst — progress

_Clustering REFINED (robust ≥3-driver terminals + containment merge): 121 → 25
corridors; 18 are support-gated for AI analysis. Old verdicts (C1, C2 on the old
IDs) were reset — corridor IDs changed._

- **Total corridors to analyse:** 18 (support-gated ≥5 runs, ≥2 drivers; 25 total)
- **Done:** 0
- **Remaining:** 18
- **Next:** C1 (new consolidated Soura spine — 211 runs / 32 drivers)

## How to resume (after shutdown / new session)
1. `& "D:\plotting\ana\python.exe" src\next_corridor.py`  → next corridor with no verdict.
2. Read `analyst/evidence/C<id>.json` (+ `.png` if the match is unclear).
3. Web-ground if needed (JKRTC chart / place check).
4. Write `analyst/verdicts/C<id>.json` + `.md`; update this file.
   A corridor is done ONLY when its verdict JSON exists.

Pace: batches of ~8–10 per session (user's choice). When all 18 done →
`src/aggregate_corridors.py` → CORRIDOR_FINDINGS.md + dashboard geojson.

Metrics are measured/authoritative — AI only judges match / informal / narrative / stops.

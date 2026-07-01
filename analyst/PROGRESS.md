# Corridor Analyst — progress

- **Total corridors:** 55 (support-gated ≥5 runs, ≥2 drivers)
- **Done:** 2
- **Remaining:** 53
- **Last completed:** C2 — Soura↔central spine (PARTIAL → FDR-078, needs review) · 2026-07-01
- **Prior:** C1 — Soura ↔ Lal Chowk (MATCHED → FDR-050, high conf)

## Emerging meta-finding
Near the core, one busy **Soura↔central trunk** is split into several "corridors"
(C1, C2, …) by terminal-clustering medoid endpoints. `aggregate_corridors.py`
should merge core corridors by shared trunk before counting real-route frequency.

## How to resume (after shutdown / new session)
1. `& "D:\plotting\ana\python.exe" src\next_corridor.py`  → prints the next corridor(s) with no verdict file.
2. Read `analyst/evidence/C<id>.json` + `analyst/evidence/C<id>.png`.
3. Web-ground if the match is unclear (JKRTC chart / place check).
4. Write `analyst/verdicts/C<id>.json` (structured) + `analyst/verdicts/C<id>.md` (audit log).
5. Update this file. A corridor counts as done ONLY when its verdict JSON exists.

Metrics are measured/authoritative — the AI only judges match / informal / narrative / stops.
When all 55 are done → `src/aggregate_corridors.py` → CORRIDOR_FINDINGS.md + dashboard geojson.

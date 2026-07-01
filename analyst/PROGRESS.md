# Corridor Analyst — progress

_Clustering REFINED (robust ≥3-driver terminals + containment merge): 121 → 25
corridors; 18 are support-gated for AI analysis. Old verdicts (C1, C2 on the old
IDs) were reset — corridor IDs changed._

- **Total corridors to analyse:** 18 (support-gated ≥5 runs, ≥2 drivers; 25 total)
- **Done:** 18 ✅  **Remaining:** 0  →  run `src/aggregate_corridors.py`

### Headline findings (all 18)
- **Matched to permits (7):** C1 Soura↔Lal Chowk (FDR-050), C4 Soura↔Nowgam/railway
  (FDR-262, 0.99), C5/C6 Pampore↔Srinagar (FDR-370), C7 Nawa Kadal↔Zoonimar
  (FDR-270), C8 Jehangir Chowk↔Safa Kadal (FDR-575), C16 Jehangir Chowk↔Narbal
  (FDR-455). AI beat the overlap threshold on C1/C8/C16.
- **NE-Srinagar under-permitted local cluster (finding):** C2, C9, C11, C15, C18 —
  Soura/Zoonimar/Lal Bazar/Nowshera/Ellahibagh/Gulab Bagh: busy local corridors
  the formal permits barely cover (≤0.40 overlap). Warrants a formal feeder/loop.
- **C12 informal:** Nowhatta↔Karan Nagar (SMHS/Medical College access), no permit.
- **C14 (thin):** Batamaloo↔Budgam may be under-covered — RTO check.
- **Out-of-area (2):** C3 Udhampur↔Chenani, C10 Batote↔Mera (Jammu division NH-44).
- **Artifact (1):** C17 Pampore-terminal shuffle (74% dwell) — exclude; tighten filter.

### Batch 1 verdicts (C1–C8)
| C | O→D | verdict | permit |
|---|---|---|---|
| C1 | Soura ↔ Lal Chowk (Maisuma) | MATCHED (high) | FDR-050 |
| C2 | Soura ↔ Nowshera / Lal Bazar | PARTIAL / review | SSCL-01 (busy local, weak permit) |
| C3 | Udhampur ↔ Chenani (NH-44) | OUT_OF_AREA | — (Jammu division) |
| C4 | Soura ↔ Nowgam (railway stn) | MATCHED (high) | FDR-262 (0.99) |
| C5 | Pampore ↔ Sonwar (central) | MATCHED (med) | FDR-370 (Pampore family) |
| C6 | Magarmal Bagh ↔ Pampore | MATCHED (med) | FDR-370 (Pampore family) |
| C7 | Nawa Kadal ↔ Zoonimar/Soura | MATCHED (med) | FDR-270 |
| C8 | Jehangir Chowk ↔ Safa Kadal | MATCHED (high) | FDR-575 (endpoint+len beat overlap) |

AI beat the overlap threshold on C1 & C8 (correct lower-overlap permit); C2 is a
genuine finding (busy NE-Srinagar local corridor, weak formal coverage).

## How to resume (after shutdown / new session)
1. `& "D:\plotting\ana\python.exe" src\next_corridor.py`  → next corridor with no verdict.
2. Read `analyst/evidence/C<id>.json` (+ `.png` if the match is unclear).
3. Web-ground if needed (JKRTC chart / place check).
4. Write `analyst/verdicts/C<id>.json` + `.md`; update this file.
   A corridor is done ONLY when its verdict JSON exists.

Pace: batches of ~8–10 per session (user's choice). When all 18 done →
`src/aggregate_corridors.py` → CORRIDOR_FINDINGS.md + dashboard geojson.

Metrics are measured/authoritative — AI only judges match / informal / narrative / stops.

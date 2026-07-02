# Tail mining report — long-tail second pass

_Tail pool: 1437 clean runs not in the 25 published corridors._

## A. Evidence boost to PUBLISHED corridors (no verdicts changed)
278 tail runs geometrically overlap (Jaccard >= 0.55) a published corridor's path but had endpoints that didn't cluster into its robust terminal — likely a slightly different pickup/drop point on the same real route. These strengthen existing evidence only.

| Corridor | + runs | + distinct drivers |
|---|---|---|
| C1 | +100 | +11 |
| C5 | +71 | +8 |
| C15 | +27 | +1 |
| C10 | +18 | +11 |
| C6 | +16 | +7 |
| C3 | +13 | +10 |
| C4 | +11 | +4 |
| C16 | +10 | +1 |
| C8 | +4 | +2 |
| C7 | +3 | +3 |
| C13 | +3 | +1 |
| C2 | +2 | +1 |

## B. NEW Tier-2 candidate corridors (exploratory — lower confidence)
Path-shape clustering (complete-linkage, Jaccard >= 0.45, every member similar to every other member) over the runs A didn't claim. No shared robust terminal required, so these are weaker evidence than the Tier-1 set and need individual review before being called real corridors.

| Tail ID | Runs | Drivers | Median km | Median min |
|---|---|---|---|---|
| T1 | 23 | 7 | 24.1 | 146.0 |
| T2 | 20 | 4 | 69.1 | 254.0 |
| T3 | 17 | 6 | 4.7 | 26.0 |
| T4 | 16 | 2 | 2.7 | 10.0 |
| T5 | 12 | 3 | 24.8 | 60.0 |
| T6 | 11 | 4 | 34.0 | 186.0 |
| T7 | 10 | 7 | 87.6 | 130.0 |
| T8 | 9 | 5 | 38.6 | 131.0 |
| T9 | 8 | 2 | 6.2 | 34.0 |
| T10 | 8 | 2 | 6.2 | 35.0 |
| T11 | 8 | 5 | 56.0 | 107.0 |
| T12 | 8 | 4 | 37.0 | 93.0 |
| T13 | 8 | 3 | 54.0 | 139.0 |
| T14 | 8 | 2 | 23.5 | 116.0 |
| T15 | 7 | 5 | 2.1 | 14.0 |
| T16 | 6 | 3 | 20.7 | 112.0 |
| T17 | 6 | 3 | 6.4 | 32.0 |
| T18 | 6 | 2 | 22.0 | 72.0 |
| T19 | 6 | 5 | 1.7 | 17.0 |
| T20 | 6 | 2 | 17.1 | 94.0 |
| T21 | 6 | 2 | 7.7 | 23.0 |
| T22 | 6 | 2 | 23.4 | 66.0 |
| T23 | 6 | 2 | 17.6 | 68.0 |
| T24 | 5 | 2 | 17.8 | 90.0 |
| T25 | 5 | 3 | 2.8 | 40.0 |
| T26 | 5 | 3 | 1.8 | 10.0 |
| T27 | 5 | 3 | 32.2 | 135.0 |
| T28 | 5 | 2 | 36.7 | 136.0 |
| T29 | 5 | 5 | 54.6 | 110.0 |
| T30 | 5 | 4 | 15.9 | 42.0 |

## C. Triage of the 30 Tier-2 candidates (`validate_tail_candidates.py`, script-only)
Same overlay method as `validate_permits.py` (against the current v3.4.5 rationalised
geometry, study-area clipped) plus a raw-permit endpoint proximity check — the audit
discipline learned from the Tier-1 pass, so nothing gets mislabelled "unpermitted"
without checking the raw 614-permit register first.

| Verdict | Count | What it means |
|---|---|---|
| OUT_OF_AREA | 17 | Outside the 10-district study area — mostly NH-44/Jammu highway traffic. **Includes the two biggest-looking candidates (T2, 69 km; T7, 88 km)** — visually they looked like real corridors, but they're not Kashmir Division routes. |
| MATCHED | 7 | Already ride an existing plan route — folded in as more confirming evidence, not new corridors. |
| PARTIAL | 4 | Overlap an existing plan route with some divergence — same "geometry reconciliation" class as the Tier-1 PARTIAL corridors. |
| **UNMATCHED** | **2** | No plan-route overlap, in-area, and confirmed via a raw-permit proximity check. **Only these needed an actual look.** |

## D. The two that needed a look — reviewed individually
Full verdicts: `analyst/verdicts_tier2/T4.json`, `T17.json`. Map: `data/tail_final_two.png`.

- **T4 — Chowderi Bagh ↔ Badgam** (2.7 km, 16 runs / 2 drivers, ~10 min). A short
  intra-town shuttle. Budgam itself is heavily permitted (42 raw permits), but none
  name "Chowderi Bagh" specifically — the permit register is O-D pair level and
  wouldn't capture a fine-grained intra-town link anyway. Reads as real local
  movement inside an already-served town, not a coverage gap. **`is_informal: false`.**
- **T17 — Gulab Bagh ↔ Hazratbal** (6.4 km, 6 runs / 3 drivers, ~32 min). A connector
  between two well-permitted north-Srinagar hubs (Hazratbal alone has 62 raw permit
  endpoints). No permit runs this exact pair by name — plausible informal shortcut
  between two served areas, not a service gap. **`is_informal: false`.**

Both: **plausible, not actionable at this support level** (2–3 drivers is below the
Tier-1 confidence bar of ≥3 drivers on a robust terminal) — flagged for revisit only
if driver adoption grows in those two areas.

## What's still genuinely unusable
903 runs remain either singletons or below the support gate even by path shape — one-off routes with too little repetition to say anything about, same conclusion as the first long-tail pass (`longtail.py`).

## Bottom line
The "leftover" 59% was NOT a wasted goldmine, but it also wasn't a second batch of
20+ new corridors needing an agent framework. Script-only mining (no AI spend) did
~95% of the work: it added real confirming evidence to 12 already-published corridors
(C1's support alone went from 211→311 runs / 32→43 drivers) and correctly filtered 30
candidates down to just 2 that needed human/AI judgment — both reviewed inline in this
session, no separate agent run required. The right-sized answer to "run Opus agents on
each route" was: don't, because script triage removes the need for it at this data
scale. If future adoption pushes more corridors past the Tier-1 confidence bar, the
same one-at-a-time verdict pattern (`build_evidence.py` + individual review) scales
to however many actually need it.

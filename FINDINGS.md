# Findings — Bus Sathi trace intelligence

_Observed bus operations mined from real driver-app GPS. All figures aggregate;
driver ids are hashed and no raw traces are committed._

## Data
- **1,213** app sessions · **180** drivers · **3.8M** GPS points · **Feb–Jun 2026**
- Sampling median **~5 s**; per-session noise low (~3% of sessions show GPS jumps)

## Sessionising — the key correction
A Firestore "trip" is a **driver session** (app left running), not a service run.
After dwell detection, terminal/gap splitting, idle trimming and wandering removal:

- **2,526 service runs** from 1,200 sessions (**604** sessions held ≥2 runs; up to **10**)
- **2,012 hours** of background/idle time removed
- Median raw session **209 min** → median **real run 63 min** (raw was ~3.3× inflated)
- Runs are realistic: median **15.8 km** at **13.3 km/h** (stop-and-go bus speed)

## Denoising (OSRM map-match)
- **2,519 / 2,526** runs matched; **2,426 clean** (raw↔matched length agreement 0.6–1.6)
- Agreement median **0.99**. Gate on agreement, **not** OSRM confidence (which
  penalises long clean runs).

## Stops
- **38,431** dwell events → **352 candidate stops** (**215 strong**: ≥3 drivers & ≥10 visits)
- Busiest hub: **745 runs from 45 drivers**, ~60 s dwell — a real terminal

## Corridors
- **171 terminals** (endpoint DBSCAN) → **121 corridors** (≥3 runs), covering
  **1,239** of 2,426 clean runs
- Top observed routes run 55–73 times, 13–24 km, 45–87 min — believable services
- Two sub-networks visible: a dense **Srinagar** urban web and a **southern-Kashmir**
  corridor system with a long high-frequency highway trunk

## Important caveat
Only ~180 drivers use the app (partial adoption), so **observed frequency is a
lower bound, not true service frequency** — implied headways here are
*observed-only*. The value now is **ground-truth geometry, terminals, stops and
which corridors are genuinely used**, not absolute demand.

## Next
- Overlay observed corridors ↔ the RTO permit network → which permits are really
  run, and which observed corridors are **informal** (unpermitted).
- Compare the 352 candidate stops ↔ the engine's canonical stop register → the
  **informal stops** to formalise.

# Engine reality-check — planned vs measured route times

_Measured one-way corridor times (median over app-GPS runs, service stops
included) vs the engine's planned one-way (Cycle_Time/2, which includes stop,
junction and congestion penalties) and the raw OSRM car drive time._

**Coverage: 5 confidently-matched + 9 geometry-divergent corridors.**
Ratios < 1.00 mean the plan allots LESS time than buses measurably take.

## Confidently matched (like-for-like)

| Corridor | Plan route | Runs | Obs km / Eng km | Observed 1-way | OSRM drive | Planned 1-way (cycle/2) | Planned÷Observed |
|---|---|---|---|---|---|---|---|
| C1 | Soura to Lalchowk (FDR-050) | 211×32drv | 14.4 / 9.5 | **75.9 min** | 18.8 min | 38.0 min | **0.5** |
| C4 | Soura to Railway Station (FDR-262) | 93×12drv | 17.8 / 18.8 | **85.2 min** | 26.8 min | 47.0 min | **0.55** |
| C6 | Srinagar to Pampore (FDR-370) | 79×9drv | 16.9 / 12.9 | **78.7 min** | 10.8 min | 40.4 min | **0.51** |
| C7 | Soura to Qamarwari (FDR-270) | 47×11drv | 11.2 / 9.3 | **64.3 min** | 13.6 min | 37.2 min | **0.58** |
| C8 | Safakadal to Jehangir Chowk (FDR-575) | 40×5drv | 3.5 / 3.1 | **26.6 min** | 3.6 min | 12.6 min | **0.47** |

- Median **planned÷observed = 0.51** — the engine's planned one-way times UNDERSHOOT measured reality on these corridors.
- Median raw OSRM(car)÷observed = 0.21 — the un-penalised car model alone is far too fast; the engine's penalty stack closes much of the gap.

## Geometry-divergent (indicative only)

_Observed corridor geometry differs from the engine's routed line, so km
and time are not strictly comparable — shown for context._

| Corridor | Plan route | Runs | Obs km / Eng km | Observed 1-way | OSRM drive | Planned 1-way (cycle/2) | Planned÷Observed |
|---|---|---|---|---|---|---|---|
| C11 | Parimpora to Harwan via Brein Nishat (SSCL-01) | 26×9drv | 11.2 / 23.2 | **48.5 min** | 36.7 min | 58.1 min | **1.2** |
| C12 | Batamaloo to Womens College Batpora via Rainawari (SSCL-17) | 22×9drv | 5.8 / 4.5 | **29.1 min** | 7.6 min | 18.1 min | **0.62** |
| C13 | Parimpora to Saidakadal (FDR-106) | 15×2drv | 5.7 / 9.0 | **20.5 min** | 14.7 min | 36.0 min | **1.76** |
| C15 | Batamaloo to Hazratbal via Khanyar (SSCL-03) | 7×4drv | 18.3 / 12.9 | **83.6 min** | 25.0 min | 51.7 min | **0.62** |
| C16 | Narbal to Jehangir Chowk (FDR-455) | 6×2drv | 14.3 / 17.0 | **58.5 min** | 22.2 min | 42.5 min | **0.73** |
| C18 | Srinagar to Gulabagh (FDR-144) | 5×2drv | 10.3 / 14.0 | **53.8 min** | 13.0 min | 51.3 min | **0.95** |
| C2 | Parimpora to Harwan via Brein Nishat (SSCL-01) | 150×12drv | 11.5 / 23.2 | **52.1 min** | 36.7 min | 58.1 min | **1.12** |
| C5 | Srinagar to Pampore (FDR-370) | 82×11drv | 20.3 / 12.9 | **92.2 min** | 10.8 min | 40.4 min | **0.44** |
| C9 | Parimpora to Harwan via Brein Nishat (SSCL-01) | 32×7drv | 7.4 / 23.2 | **36.2 min** | 36.7 min | 58.1 min | **1.6** |

## How to read this (do NOT over-read it)
1. **Observed times embody today's informal operating practice** — wait-to-fill
   dwells at stops, flexible stopping — which a scheduled, headway-enforced
   service would compress. The measured medians are an UPPER bound on scheduled
   running time; the engine's planned times are the design target. The truth a
   scheduler should plan for lies between, closer to planned + realistic dwell.
2. Part of each gap is **route length, not speed**: observed corridor paths often
   run longer than the engine's routed line (e.g. C1: 14.4 km observed vs 9.5 km
   routed). Compare per-km effective speeds before adjusting any cycle time.
3. **Where planned÷observed < 1 persistently**, treat the corridor as a cycle-time
   review candidate — not an automatic fleet increase.
4. Measured city-wide anchors: **~21 km/h moving / ~12.5 km/h effective** (dwell
   ≈ 37% of run time), terminal turnaround **median 24 min** — check the engine's
   recovery allowance against that turn figure.
5. Scope: partial adoption (~157 drivers); these corridors are the frequently-
   driven Srinagar core, not the whole network. Rural cycle times remain unvalidated.

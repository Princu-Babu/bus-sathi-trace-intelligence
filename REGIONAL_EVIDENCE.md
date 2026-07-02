# Regional evidence — maximising the broken-fragment data

_2026-07-02. User observation: the speed layer lights up all the way to Anantnag,
Pahalgam, Ganderbal, Pattan — but the corridor layer stops at the Srinagar core.
The data was there; the method couldn't see it._

## Why the long-haul routes were invisible

Corridor discovery required a single run to span terminal-to-terminal, and
drivers on long hauls toggle the app mid-journey — so Srinagar–Anantnag exists
in the traces only as **broken fragments** (Srinagar–Bijbehara here, Bijbehara–
Anantnag there). Run-level clustering can never assemble that. **Fragment
aggregation can**: rasterise every clean run to 120 m road cells and let each
fragment vote for the road-km it covers.

## Deliverable 1 — plan-route observation index (`src/route_evidence.py`)

Every one of the 2,426 clean runs (not just corridor members) scored against
all 186 plan routes:

| Evidence | Routes | Meaning |
|---|---|---|
| **Strong** (≥50% of route driven, ≥2 drivers) | **172** | the road alignment is demonstrably in live bus use |
| Partial (20–50%) | 7 | partially driven |
| Little/none | 7 | honest gaps — mostly Shopian/Kulgam south-west |

Long-haul highlights (previously invisible at corridor level):

| Route | km | Coverage | Fragments | Drivers |
|---|---|---|---|---|
| Anantnag ↔ Srinagar (FDR-013) | 59.3 | 100% | 367 | 24 |
| Srinagar ↔ Gund (FDR-517) | 57.4 | 100% | 385 | 19 |
| Mawan ↔ Srinagar (FDR-023) | 56.1 | 100% | 369 | 24 |
| Sopore ↔ Srinagar (FDR-511) | 50.0 | 100% | 44 | 13 |
| Srinagar ↔ Khrew (FDR-476) | 19.6 | 100% | 360 | 23 |

**Honest caveat (stated everywhere):** coverage means "app buses drove this
road", NOT "this exact permit is operated end-to-end" — parallel routes sharing
a road segment share its evidence, and fragments can belong to any service on
that road. It's road-level ground truth, one tier below the corridor verdicts.

Outputs: `data/route_evidence.csv`, `data/route_evidence.png`, dashboard layer
`public/kashmir-reality/plan_evidence.geojson` ("plan evidence" toggle on the
Reality Layer tab, with the caveat in every popup).

## Deliverable 2 — Tier-2 rural stops (`src/rural_stops.py`)

The Tier-1 stop pass (DBSCAN min_samples=8) was tuned for dense Srinagar dwell
data; rural stopping places never reached 8 recorded dwells. Re-clustered at
min_samples=4 with the support gate ≥4 visits AND ≥2 distinct drivers, deduped
against Tier-1 (250 m), study-area-clipped, district-labelled:

**64 new Tier-2 stop candidates** — Srinagar 46, **Anantnag 7, Pulwama 7,
Ganderbal 3, Budgam 1**. The Anantnag/Pulwama ones sit along the NH-44/Pahalgam
arm — the first observed stop evidence outside the city footprint.

Labelled Tier 2 = thinner evidence than Tier 1, for **field validation**, not
publication as confirmed stops. Outputs: `data/stops_tier2.geojson` + dashboard
(red dots under the "stops" toggle).

## Deliverable 3 — observed stops coded in the plan's terminology (`src/make_stop_codes.py`)

Every observed stop now carries a code in the engine's geo-canonical format:
`<District2>-<Sector2>-X<nn>` — the SAME district letters and alphabetical-tehsil
sector numbers as `Kashmir_Stops_Master_v4.csv` (via the engine's own
`AdminIndex`, so numbering is byte-compatible), with an **X-series** stop number
marking it observed/provisional (no collision with the official register).
**214 coded stops** (65 raw candidates dropped — strict district-union containment
caught Jammu-side NH-44 stops that nearest-district fallback would have mislabelled).
Each row: OSM place name (Nominatim), tehsil/sector, support counts, and the
nearest register stop + distance as an anchor. E.g. `AN-05-X04` = Pahalgam town,
242 s median dwell — the Pahalgam arm now has coded, named stop evidence.

## Deliverable 4 — the RTO workbook (`src/make_rto_workbook.py`)

`Kashmir_Observed_GroundTruth_v1.xlsx` — one downloadable on the dashboard
(Downloads tab + Reality Layer): Read Me (tiers + governing caveat), 214 coded
Observed Stops, 18 Verified Corridors, 186-route Evidence sheet, 2 Local
Connectors. Aggregate + anonymised.

## Realism cross-check (app data vs plan outputs)

1. **Fragment intensity vs planned fleet: rho = −0.12** (essentially uncorrelated/
   negative) — fragments measure *adoption* (Srinagar-heavy), not service intensity.
   This is the expected signature and confirms why frequency/demand are never
   inferred from this data.
2. Strong-evidence share by route type: Urban 97% / Peri-Urban 96% / Regional 86% —
   uniformly high, no class anomaly.
3. The 7 weakest-evidence routes are exactly the far-NW/SW periphery (Uri, Kupwara,
   Bandipora–Baramulla, Pakherpora, Sangerwani) — where adoption is nil. Notably
   `FDR-593 Garkote` (the one deferred deep-dive FAIL) shows 0% evidence — consistent.
4. All 64 Tier-2 stop dwells sit inside the 40 s–12 min service-stop window.
5. Evidence-boost runs double-counted into corridors: 0.

## What this closes

- The visible mismatch between the speed layer (valley-wide) and the corridor
  layer (Srinagar-core) is now explained and exploited, not just caveated.
- The old `permit_observed.csv` (corridor-geometry-only) is superseded by
  `route_evidence.csv` (all-fragment).
- Combined with the corridor verdicts: **Tier 1** = 15 verified corridors
  (terminal-robust, AI-judged) · **Tier 2** = road-level fragment evidence on
  172 plan routes + 64 rural stop candidates · beyond that, adoption growth is
  the only honest path to more.

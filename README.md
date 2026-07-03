# Bus Sathi — Trace Intelligence

Turning **real driver GPS from the Bus Sathi mobile app** into a measured
ground-truth layer for the Kashmir Valley route-rationalisation plan — so the
plan is no longer built on paper permits alone, but cross-checked against what
buses actually do on the road.

> Companion to the [route-rationalisation engine](https://github.com/Princu-Babu/kashmir-transit-rationalisation)
> and the Bus Sathi dashboard. Uses the same OSRM/OpenStreetMap road network the
> engine already uses.

> ⚠️ **Scope (read [AUDIT.md](AUDIT.md)):** this is a **validation / ground-truth
> layer, NOT a rationalisation engine.** App adoption is partial (~157 self-selected
> drivers, Srinagar-concentrated), so it **cannot measure demand, ridership or real
> frequency** and cannot decide which routes to add/cut/resize — it *validates,
> measures and flags candidates*. "Informal" here means "diverges from the plan's
> rationalised geometry", **not** "unpermitted" (the raw permits cover these areas —
> see AUDIT.md). Adoption-robust wins (measured speeds, confirmed corridors, road
> coverage, stops) are the defensible output; frequency/demand are never published.

---

## Why this matters

The rationalisation plan is built from **RTO permits on paper** (geocoded and
routed). This repo supplies the missing half — **what buses measurably do on the
ground** — from the app's ~5-second GPS pings, so we can:

- **validate** which plan routes are really being driven, and where reality diverges;
- **measure** the first real Srinagar bus speeds, duty cycles and turnarounds;
- **discover** the stops and connectors the paper register never captured;
- **correct** the engine's cycle times where measurement disproves the model.

## The data (the raw material)

Firestore project `bus-tracker-f24e9`, collection `trips` — each document is a
driver **session** with a `routePoints[]` array of `{lat,lng,ts}` at ~5 s spacing:

- **~157 active drivers · 3.8 M GPS points · 1,213 sessions · Feb–Jun 2026**
- The catch: a recorded "trip" is **not** a bus trip. Drivers leave the app
  running in the background, so one session bundles 3–10 real service runs plus
  hours of parking, meals and wandering. **Nothing is used raw.**

## What we built (pipeline)

| Stage | Script | What it does |
|---|---|---|
| Cache | `pull_cache.py` | pull every session's points once → local pickle |
| **Sessionise** | `segment.py` | split each session into real service **runs** (cut at terminals ≥12 min & gaps ≥8 min, trim idle, drop wandering) → **2,526 runs**, 2,012 h idle removed |
| Map-match | `match_runs.py` | snap each run to roads via OSRM `/match`, gate on raw↔matched **agreement** → 2,426 clean runs |
| Cluster stops | `stops.py` | DBSCAN the dwells → 352 candidate stops (215 strong) |
| Infer corridors | `corridors.py` | robust-terminal clustering + containment merge → 25 corridors |
| Validate vs plan | `validate_permits.py` | corridors ↔ plan routes ↔ raw permits, study-area clipped |
| Measured speeds | `speed_layer.py`, `calibration.py` | per-cell + per-corridor bus speeds |
| Operations | `operations.py` | duty cycles, turnaround, in-service curve |
| **AI corridor analyst** | `build_evidence.py` + `analyst/verdicts/` | one evidence packet + individual verdict per corridor |
| Long-tail mining | `longtail.py`, `tail_corridors.py` | recover evidence from the 59% not in corridors |
| **Regional evidence** | `route_evidence.py`, `rural_stops.py` | fragment aggregation → valley-wide road coverage + rural stops |
| Engine reality-check | `reality_check.py` | planned vs measured cycle times → the v3.4.5 correction |
| Reconciliation | `reconciliation.py` | package the geometry divergences for the engine |
| **Geometry fix (engine-side)** | `../kash/fix_geometries_v345geo*.py` | the reconciliation payoff: re-anchor wrong endpoint pins from the stops register / observed GPS clusters / researched pins, re-route on OSRM, accept only inside the verified km band → **15 of 18 stale route map lines redrawn** (v3.4.5-geo; geometry-only, numbers unchanged) |
| Stop coding | `make_stop_codes.py` | code observed stops in the plan's district-sector terminology |
| Deliverables | `make_rto_workbook.py`, `export_dashboard.py` | the RTO workbook + dashboard layers |

Run the whole thing in order with `python src/run_all.py`.

## Headline results — what the app data established

- **First measured Srinagar bus speeds:** ~**21 km/h** moving, ~**12.5 km/h**
  effective (dwell ≈ 37 % of run time); core 17 vs periphery 24 km/h across a
  10,600-cell congestion map.
- **Operations, measured:** 7.9 h duty day / 4.8 h in service (76 % utilisation),
  median terminal turnaround **24 min**, service ramps 08:00 and **collapses after
  19:00** — an evening-service gap the plan couldn't have seen otherwise.
- **Verification:** 7 plan routes confirmed running corridor-level; **172 of 186
  plan routes** carry strong **road-level** evidence via fragment aggregation
  (e.g. Anantnag–Srinagar 59 km, 100 % driven, 367 fragments / 24 drivers);
  8 geometry divergences queued for reconciliation; **0 informal/unpermitted**.
- **The plan correction (v3.4.5):** 5 GPS-verified core corridors were running at
  ~2× the engine's planned time (masked by a cycle cap) → cycles re-anchored to
  measured speed → engine fleet **1,004 → 1,011**.
- **Geometry fixed (v3.4.5-geo):** the reconciliation queue turned into action —
  **15 of 18 stale route map lines** (wrong endpoint pins, not wrong routing) were
  redrawn from real driven paths / re-anchored termini, accepted only inside each
  route's verified km band. Geometry-only; every plan number byte-identical.
- **Stops:** 215 strong observed stops + **64 Tier-2 rural candidates** (Anantnag,
  Pulwama, Ganderbal), all coded in the plan's own `<District>-<Sector>-X<nn>`
  terminology for the RTO's stop register.

## Deliverables

- **Dashboard "Reality Layer" tab** — observed corridors (by verdict), measured-
  speed heatmap, real stops (Tier-1 + Tier-2), per-route road-coverage, the 2
  unmatched connectors, the geometry-reconciliation workbench, and a data-
  freshness chip. Every panel labelled "observed, partial adoption".
- **`Kashmir_Observed_GroundTruth_v1.xlsx`** — RTO download: coded stops, corridor
  verdicts, per-route evidence, connectors (caveats on every sheet).
- **`Bus_Sathi_Trace_Intelligence_Briefing.pptx`** — 14-slide briefing deck.
- Reports: [`AUDIT.md`](AUDIT.md), [`REGIONAL_EVIDENCE.md`](REGIONAL_EVIDENCE.md),
  [`TAIL_MINING_REPORT.md`](TAIL_MINING_REPORT.md), `REALITY_CHECK.md`,
  `CORRIDOR_FINDINGS.md`.

## Honesty calls we deliberately made (and kept)

1. **Retracted** an early "NE-Srinagar under-permitted cluster" finding after a
   raw-permit check proved those areas are well-permitted — the real signal is
   geometry divergence, not missing service (see AUDIT.md).
2. **Refused** to publish a recalibrated congestion multiplier — OSRM's car
   profile (55–137 km/h) is not a valid bus baseline.
3. **Never** infer demand, ridership or frequency from partial adoption — a route
   with no app data is not an unused route.
4. Everything above the confidence bar is **Tier 1**; thinner evidence is clearly
   labelled **Tier 2 — field-validate**.

## Run

```powershell
$env:PATH = "D:\plotting\ana;D:\plotting\ana\Library\bin;D:\plotting\ana\Scripts;" + $env:PATH
& "D:\plotting\ana\python.exe" src\run_all.py
```

Requires a Firebase **service-account key** at `secrets/serviceAccount.json` and
OSRM running on `localhost:5000` for the map-matching stage.

## Privacy & safety (public repo)

- Driver GPS is **PII**. The service-account key (`secrets/`) and all raw traces
  (`data/`) are **gitignored and never committed**.
- Driver ids/emails are **SHA-256 hashed** in every output; only aggregate,
  anonymised layers are published.
- **Rotate/delete the admin key** in the Firebase console once exporting is done.

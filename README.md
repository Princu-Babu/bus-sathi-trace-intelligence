# Bus Sathi — Trace Intelligence

Turning **real driver GPS traces** from the Bus Sathi mobile app into a
ground-truth layer for the Kashmir route-rationalisation plan: clean the noisy
traces, infer the corridors that are actually being driven, and match them
against the on-paper RTO permits.

> Companion to the [route-rationalisation engine](https://github.com/Princu-Babu/kashmir-transit-rationalisation)
> and the Bus Sathi dashboard. This repo consumes the same OSRM/OpenStreetMap
> road network the engine already uses.

> ⚠️ **Scope (read [AUDIT.md](AUDIT.md)):** this is a **validation / ground-truth
> layer, NOT a rationalisation engine.** App adoption is partial (~180 self-selected
> drivers, Srinagar-concentrated), so it cannot measure demand or real frequency and
> **cannot decide which routes to add/cut/resize** — it *flags candidates*. Observed
> corridors cover only ~40% of clean runs. "Informal" = "doesn't match the engine's
> *rationalised geometry*" (a divergence flag), not "unpermitted" — the raw permits
> DO cover these areas (see AUDIT.md). Adoption-robust wins (speeds, confirmed
> corridors, stops) are the defensible output; frequency/demand are not published.

---

## Why

The rationalisation plan is built from **RTO permits on paper** (geocoded +
routed). This repo adds the missing half — **what buses actually do on the
ground** — from the app's ~5-second GPS pings, so we can:

- **validate** which permits are really being run, and how far reality deviates;
- **discover** real/informal corridors the permits don't capture;
- **calibrate** demand & frequency in a future engine version from observed service.

## The data (live profile)

From `src/export_traces.py` against Firestore project `bus-tracker-f24e9`
(collection `trips`, each doc carries a `routePoints[]` array of `{lat,lng,ts}`):

- **1,213** trips · **1,031** usable · **180** drivers · **3.8M** GPS points
- **Feb–Jun 2026**, median sampling **~5 s**, median path **47 km**
- Low per-trip noise (only ~3% of trips show GPS jumps)

See [`PROFILE.md`](PROFILE.md) for the current profile (regenerated per run).

## Pipeline (planned)

0. **Cache** — pull every session's points once → local pickle *(done: `src/pull_cache.py`)*
1. **Sessionise** — split each app SESSION into real service RUNS: detect dwells,
   split at terminals (≥12 min) & gaps (≥8 min), trim idle, drop wandering,
   record service-stop dwells *(done: `src/segment.py`)*
2. **Denoise / map-match** — snap each run to roads via **OSRM `/match`** *(done: `src/match_runs.py`)*
3. **Cluster stops** — DBSCAN the dwells → recurring/informal stops *(done: `src/stops.py`)*
4. **Infer corridors** — terminal-DBSCAN → OD corridors + observed frequency *(done: `src/corridors.py`)*
5. **Validate vs permits** — corridors↔permits + stops↔register, study-area clipped
   *(done: `src/validate_permits.py`, `src/informal_stops.py`)*
6. **Measured calibration** — speed/congestion layer + measured corridor profiles
   *(done: `src/speed_layer.py`, `src/calibration.py`)*
7. **Operations & fleet** — duty cycles, turnaround, in-service curve, utilisation
   *(done: `src/operations.py`)*
8. **Dashboard reality layer** — observed corridors/stops/congestion tab *(next)*

### Operations (measured, per-vehicle — adoption-robust)
From 855 observed driver-days (157 drivers): duty day median **7.9 h** span with
**4.8 h** in service (**76%** utilisation); typical day ~10:20→18:15 IST; median
**2 runs/day** (p90 6), **56 km/day**. Terminal turnaround (n=1,178 same-terminal
turns): **median 24 min** (p25 16 / p75 41) — door-to-door incl. layover+filling.
In-service curve peaks **14:00–17:00 IST** and collapses after **19:00** (the
observed fleet effectively stops by evening). Shape is robust; absolute level is
partial-adoption. Full report: `data/operations_report.txt`.

### Measured calibration (honest, measured-only)
- Bus moving speed **~21 km/h** (core 18.6 vs periphery 20.9); effective **~12.5 km/h**
  (dwell share ~37%) — cross-checks the speed layer + run-level numbers.
- **Signal for the engine:** it sizes cycles on OSRM *car* speeds; real buses run
  far slower → engine cycle times are optimistic; calibrate to the measured speed
  layer per zone.
- **Deliberately NOT done:** a recalibrated congestion multiplier. OSRM free-flow
  is a car profile (55–137 km/h here) — not a valid bus baseline — and
  congestion/bus-speed/dwell are entangled. Publishing a number would be dishonest.
- **Dropped:** coverage gaps (adoption too concentrated to tell "no service" from
  "no app data").
- **Long tail closed out** (`src/longtail.py`): the 59% of clean runs outside the
  corridors is 64% off-terminal + 28% same-terminal loops + 34% out-of-division —
  only 3% are near-miss OD pairs (max 2 runs · 2 drivers each). **No missed
  corridors**; 41% coverage is the honest ceiling of current adoption.

### Stage-5 validation (study-area clipped, sparse-safe)
- Corridors: **39 matched · 32 partial · 14 informal** (6 strong, e.g. a 12.4 km
  corridor run 21× by 7 drivers with no permit); 36 out-of-division (NH-44) excluded.
- Permits: **75 observed · 41 partial · 70 no-app-data** (partial adoption ≠ unused).
- Stops: of 43 register stops in the observed footprint only **30% corroborate**;
  the GPS adds **135 evidence-based candidate stops** (the endpoint-register lacks
  mid-route stops — an engine P0 gap the traces fill).

### Sessionising impact (real data)
1,200 sessions → **2,526 real runs** (604 sessions held ≥2; up to 10). **2,012 h**
of background/idle trimmed. Median raw session **209 min** → median real run
**63 min**; median run **15.8 km** at **13.3 km/h** — realistic bus speeds.

**Sample map-match finding:** on genuine moving runs the matched line hugs the
raw GPS tightly (see `data/sample_before_after.png`). OSRM's own `confidence`
is *not* a good quality gate on its own — it correctly flags idling/parked GPS
scribble, but also penalises long clean runs. Stage 4 will gate on a
raw↔matched **agreement** metric (length ratio + point-to-line coverage) plus a
stop-splitting segmenter, not raw confidence.

## Run

```powershell
$env:PATH = "D:\plotting\ana;D:\plotting\ana\Library\bin;D:\plotting\ana\Scripts;" + $env:PATH
& "D:\plotting\ana\python.exe" src\export_traces.py
```

Requires a Firebase **service-account key** at `secrets/serviceAccount.json`
(Firebase console → Project settings → Service accounts → *Generate new private
key*). OSRM must be running on `localhost:5000` for the map-matching stage.

## Privacy & safety (this is a public repo)

- Driver GPS is **PII**. The service-account key (`secrets/`) and all raw traces
  (`data/`) are **gitignored and never committed**.
- Driver ids/emails are **SHA-256 hashed** in every output.
- Only aggregate stats + a city-level bbox are written to the committed profile.
- **Rotate/delete the admin key** in the Firebase console once exporting is done.

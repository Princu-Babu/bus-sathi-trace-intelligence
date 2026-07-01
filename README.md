# Bus Sathi — Trace Intelligence

Turning **real driver GPS traces** from the Bus Sathi mobile app into a
ground-truth layer for the Kashmir route-rationalisation plan: clean the noisy
traces, infer the corridors that are actually being driven, and match them
against the on-paper RTO permits.

> Companion to the [route-rationalisation engine](https://github.com/Princu-Babu/kashmir-transit-rationalisation)
> and the Bus Sathi dashboard. This repo consumes the same OSRM/OpenStreetMap
> road network the engine already uses.

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

1. **Export** — `trips` → local raw store *(done: `src/export_traces.py`)*
2. **Segment** — split each shift-long trip into individual directional runs
3. **Denoise / map-match** — snap each run to roads via **OSRM `/match`**
4. **Infer corridors** — cluster matched runs sharing road segments
5. **Match to permits** — link observed corridors ↔ RTO permit routes
6. **Calibrate** — feed observed frequency/coverage back into the engine

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

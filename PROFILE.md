# Bus Sathi — trace data profile

_Generated 2026-07-01T10:48:31+00:00 · project bus-tracker-f24e9_

## Volume
- Trip documents: **1213**
- Trips with any GPS points: **1200**
- **Usable** trips (>=20 points and moved >=0.4 km): **1031**
- Unique drivers (hashed): **180**
- Total GPS points ingested: **3,835,537**
- Date range (trip starts): **2026-02-06 → 2026-06-29**

## Trace quality (usable trips)
- Points per trip: min 50 / median 2575 / max 14483
- Median sampling interval, seconds: min 3.7 / median 5 / max 13.2  _(app target ~5s)_
- GPS path length, km: min 0.6 / median 47 / max 596.2
- Trips with >=1 GPS teleport/jump: **41** of 1213

## Spatial extent (usable trips)
- lat [30.6984, 34.4671]  lon [74.1552, 75.9668]  (~centre 34.0728, 74.8190)

## Read
- Raw per-trip metadata: `data/trips_meta.csv` (gitignored)
- Map-viewable traces: `data/traces_raw.geojson` (gitignored — drop into geojson.io / QGIS)

> Next: OSRM `/match` denoising → corridor clustering → match against RTO permits.
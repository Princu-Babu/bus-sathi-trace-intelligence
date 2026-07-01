#!/usr/bin/env python
"""
Export Bus Sathi driver GPS traces from Firestore and profile them.

v1 goal: pull the raw `trips` collection (each doc carries routePoints[] written
~every 5s by the mobile app), land it locally, and produce a "whole picture"
data-quality report so we can decide the analysis approach.

Privacy: driver ids/emails are SHA-256 hashed in every output. Raw traces land in
data/ (gitignored). Only aggregate stats + a city-level bbox go into PROFILE.md.

Run:
    $env:PATH = "D:\\plotting\\ana;D:\\plotting\\ana\\Library\\bin;D:\\plotting\\ana\\Scripts;" + $env:PATH
    & "D:\\plotting\\ana\\python.exe" src\\export_traces.py
"""
import os, sys, csv, json, math, hashlib, statistics as st
from datetime import datetime, timezone

try:  # Windows consoles default to cp1252 and choke on arrows/unicode
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core import exceptions as gexc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SA_PATH = os.path.join(ROOT, "secrets", "serviceAccount.json")
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

TRIPS_COLLECTION = "trips"


def h(x) -> str:
    s = str(x or "").strip()
    return "anon" if not s else hashlib.sha256(s.encode()).hexdigest()[:12]


def to_ms(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        # seconds vs milliseconds heuristic
        return int(v * 1000) if v < 1e12 else int(v)
    if hasattr(v, "timestamp"):
        try:
            return int(v.timestamp() * 1000)
        except Exception:
            return None
    try:
        return int(v)
    except Exception:
        return None


def point(p):
    if not isinstance(p, dict):
        return None
    lat = p.get("lat", p.get("latitude"))
    lon = p.get("lng", p.get("longitude", p.get("lon")))
    t = to_ms(p.get("timestamp", p.get("time", p.get("ts"))))
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)) or (lat == 0 and lon == 0):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return (lat, lon, t)


def haversine_km(a, b):
    R = 6371.0
    dlat = math.radians(b[0] - a[0]); dlon = math.radians(b[1] - a[1])
    x = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(x))


def analyse(pts):
    """Per-trip geometry + noise stats from cleaned points."""
    pts = [p for p in pts if p]
    n = len(pts)
    out = dict(n_points=n, gps_km=0.0, dur_min=0.0, med_dt_s=None,
               teleports=0, dup_pts=0, bbox_km=0.0)
    if n < 2:
        return out, pts
    dts, gps_km, teleports, dups = [], 0.0, 0, 0
    lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
    for i in range(1, n):
        d = haversine_km(pts[i - 1], pts[i])
        gps_km += d
        t1, t2 = pts[i - 1][2], pts[i][2]
        if t1 and t2 and t2 > t1:
            dt = (t2 - t1) / 1000.0
            dts.append(dt)
            if dt > 0 and (d / (dt / 3600.0)) > 130:  # >130 km/h => GPS jump
                teleports += 1
        if d < 0.0005:
            dups += 1
    ts = [p[2] for p in pts if p[2]]
    dur_min = (max(ts) - min(ts)) / 60000.0 if len(ts) >= 2 else 0.0
    bbox_km = haversine_km((min(lats), min(lons)), (max(lats), max(lons)))
    out.update(gps_km=round(gps_km, 3), dur_min=round(dur_min, 1),
               med_dt_s=round(st.median(dts), 1) if dts else None,
               teleports=teleports, dup_pts=dups, bbox_km=round(bbox_km, 3))
    return out, pts


def main():
    if not os.path.exists(SA_PATH):
        raise SystemExit(f"Service account not found at {SA_PATH}")
    firebase_admin.initialize_app(credentials.Certificate(SA_PATH))
    db = firestore.client()

    col = db.collection(TRIPS_COLLECTION)
    try:
        total = col.count().get()[0][0].value
        print(f"'{TRIPS_COLLECTION}' has {total} documents (aggregation count)")
    except Exception as e:
        total = None
        print(f"(count() unavailable: {str(e)[:60]}) — paging anyway")

    # The routePoints arrays make docs large, so a single full-collection scan
    # times out. Page by document id with an adaptive page size.
    def iter_trips(page=25):
        last, page = None, page
        while True:
            q = col.order_by("__name__").limit(page)
            if last is not None:
                q = q.start_after(last)
            try:
                batch = list(q.stream())
            except (gexc.ServiceUnavailable, gexc.DeadlineExceeded) as e:
                if page > 3:
                    page = max(3, page // 2)
                    print(f"   timeout — shrinking page to {page}")
                    continue
                raise
            if not batch:
                return
            for d in batch:
                yield d
            if len(batch) < page:
                return
            last = batch[-1]

    print(f"Paging '{TRIPS_COLLECTION}' ...")
    docs = []
    for d in iter_trips():
        docs.append(d)
        if len(docs) % 100 == 0:
            print(f"   ...{len(docs)} docs")
    print(f"  pulled {len(docs)} trip documents")

    meta_rows, features = [], []
    drivers, all_lats, all_lons = set(), [], []
    tot_points = usable = with_points = 0
    pts_dist, dt_dist, km_dist = [], [], []
    starts = []

    for d in docs:
        t = d.to_dict() or {}
        raw_pts = t.get("routePoints") or t.get("points") or t.get("route") or []
        cleaned = [point(p) for p in raw_pts] if isinstance(raw_pts, list) else []
        stats, cpts = analyse(cleaned)
        driver = h(t.get("driverId") or t.get("driverEmail") or t.get("driverName"))
        drivers.add(driver)
        start_ms = to_ms(t.get("startTime"))
        if start_ms:
            starts.append(start_ms)

        if stats["n_points"] >= 1:
            with_points += 1
        tot_points += stats["n_points"]
        # "usable" = enough points AND actually moved a bit
        is_usable = stats["n_points"] >= 20 and stats["bbox_km"] >= 0.4
        if is_usable:
            usable += 1
            pts_dist.append(stats["n_points"])
            if stats["med_dt_s"]:
                dt_dist.append(stats["med_dt_s"])
            km_dist.append(stats["gps_km"])
            for la, lo, _ in cpts:
                all_lats.append(la); all_lons.append(lo)
            features.append({
                "type": "Feature",
                "properties": {"trip": d.id, "driver": driver, "n": stats["n_points"],
                               "gps_km": stats["gps_km"], "dur_min": stats["dur_min"],
                               "med_dt_s": stats["med_dt_s"], "teleports": stats["teleports"]},
                "geometry": {"type": "LineString",
                             "coordinates": [[lo, la] for la, lo, _ in cpts]},
            })

        meta_rows.append(dict(
            trip_id=d.id, driver=driver, status=t.get("status", ""),
            start=datetime.fromtimestamp(start_ms / 1000, timezone.utc).isoformat() if start_ms else "",
            reported_km=t.get("totalDistance", ""), usable=is_usable, **stats,
        ))

    # ── write raw artefacts (gitignored) ───────────────────────────────────
    with open(os.path.join(DATA, "trips_meta.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(meta_rows[0].keys()) if meta_rows else ["trip_id"])
        w.writeheader(); w.writerows(meta_rows)
    with open(os.path.join(DATA, "traces_raw.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    # ── PROFILE.md (aggregate only, safe to read/share) ────────────────────
    def rng(a):
        return f"min {min(a)} / median {int(st.median(a))} / max {max(a)}" if a else "n/a"
    bbox = ""
    if all_lats:
        bbox = (f"lat [{min(all_lats):.4f}, {max(all_lats):.4f}]  "
                f"lon [{min(all_lons):.4f}, {max(all_lons):.4f}]  "
                f"(~centre {st.median(all_lats):.4f}, {st.median(all_lons):.4f})")
    date_range = "n/a"
    if starts:
        date_range = (datetime.fromtimestamp(min(starts) / 1000, timezone.utc).date().isoformat()
                      + " → " + datetime.fromtimestamp(max(starts) / 1000, timezone.utc).date().isoformat())
    teleport_trips = sum(1 for m in meta_rows if m["teleports"] > 0)

    lines = [
        "# Bus Sathi — trace data profile", "",
        f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} · project bus-tracker-f24e9_", "",
        "## Volume",
        f"- Trip documents: **{len(docs)}**",
        f"- Trips with any GPS points: **{with_points}**",
        f"- **Usable** trips (>=20 points and moved >=0.4 km): **{usable}**",
        f"- Unique drivers (hashed): **{len(drivers)}**",
        f"- Total GPS points ingested: **{tot_points:,}**",
        f"- Date range (trip starts): **{date_range}**", "",
        "## Trace quality (usable trips)",
        f"- Points per trip: {rng(pts_dist)}",
        f"- Median sampling interval, seconds: {rng(dt_dist)}  _(app target ~5s)_",
        f"- GPS path length, km: {rng([round(k,1) for k in km_dist])}",
        f"- Trips with >=1 GPS teleport/jump: **{teleport_trips}** of {len(docs)}", "",
        "## Spatial extent (usable trips)",
        f"- {bbox or 'n/a'}", "",
        "## Read",
        "- Raw per-trip metadata: `data/trips_meta.csv` (gitignored)",
        "- Map-viewable traces: `data/traces_raw.geojson` (gitignored — drop into geojson.io / QGIS)",
        "",
        "> Next: OSRM `/match` denoising → corridor clustering → match against RTO permits.",
    ]
    with open(os.path.join(ROOT, "PROFILE.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n".join(lines))
    print(f"\nWrote data/trips_meta.csv, data/traces_raw.geojson, PROFILE.md")


if __name__ == "__main__":
    main()

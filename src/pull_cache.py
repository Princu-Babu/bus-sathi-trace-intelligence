#!/usr/bin/env python
"""
One-time full pull of every trip's GPS points into a local cache so the
downstream pipeline (segment / match / cluster) never re-hits Firestore.

Writes (gitignored):
  data/points.pkl.gz  — one row per GPS sample: trip_id, driver, seq, lat, lon, ts
  data/trips.pkl.gz   — one row per session (trip): metadata

Run:
  & "D:\\plotting\\ana\\python.exe" src\\pull_cache.py
"""
import os
import pandas as pd
from common import DATA, point, to_ms, h, firestore_client, pull_all_trips


def main():
    db = firestore_client()
    print("Pulling all trips into cache ...")
    prows, trows = [], []
    for d in pull_all_trips(db):
        t = d.to_dict() or {}
        driver = h(t.get("driverId") or t.get("driverEmail") or t.get("driverName"))
        raw = t.get("routePoints") or t.get("points") or t.get("route") or []
        pts = [point(p) for p in raw] if isinstance(raw, list) else []
        pts = [p for p in pts if p]
        # keep points ordered by time when timestamps exist, else by original order
        if pts and all(p[2] for p in pts):
            pts = sorted(pts, key=lambda p: p[2])
        for seq, (la, lo, ts) in enumerate(pts):
            prows.append((d.id, driver, seq, la, lo, ts))
        trows.append(dict(trip_id=d.id, driver=driver, status=t.get("status", ""),
                          start=to_ms(t.get("startTime")), end=to_ms(t.get("endTime")),
                          reported_km=t.get("totalDistance", None), n_points=len(pts)))

    pts_df = pd.DataFrame(prows, columns=["trip_id", "driver", "seq", "lat", "lon", "ts"])
    trips_df = pd.DataFrame(trows)
    pts_df.to_pickle(os.path.join(DATA, "points.pkl.gz"), compression="gzip")
    trips_df.to_pickle(os.path.join(DATA, "trips.pkl.gz"), compression="gzip")
    print(f"\nCached {len(pts_df):,} points across {len(trips_df):,} sessions "
          f"({trips_df.driver.nunique()} drivers)")
    print("Wrote data/points.pkl.gz, data/trips.pkl.gz")


if __name__ == "__main__":
    main()

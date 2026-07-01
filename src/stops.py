#!/usr/bin/env python
"""
Cluster observed dwell events into candidate STOPS.

Buses pausing repeatedly at the same place = a real stop. We DBSCAN the
service-stop dwells (40 s .. 12 min) from segment.py; a cluster hit by many
runs/drivers is a strong candidate stop. Those far from any official/permit
stop are the *informal* stops the plan should adopt.

Outputs (gitignored):
  data/stops_candidates.geojson  — one point per candidate stop + strength
  data/stops.png                 — map of candidate stops (size = visits)

Run:  & "D:\\plotting\\ana\\python.exe" src\\stops.py
"""
import os, json
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from common import DATA

EPS_M = 35            # cluster radius
MIN_SAMPLES = 8       # dwell hits to be a stop
STRONG_DRIVERS = 3    # >= this many distinct drivers => strong candidate
STRONG_VISITS = 10


def main():
    ev = pd.read_pickle(os.path.join(DATA, "stop_events.pkl.gz"), compression="gzip")
    print(f"Loaded {len(ev):,} dwell events")
    if ev.empty:
        return

    rad = np.radians(ev[["lat", "lon"]].to_numpy())
    db = DBSCAN(eps=EPS_M / 6371000.0, min_samples=MIN_SAMPLES,
                metric="haversine", algorithm="ball_tree").fit(rad)
    ev = ev.assign(cluster=db.labels_)
    clustered = ev[ev.cluster >= 0]
    print(f"  {clustered.cluster.nunique():,} stop clusters "
          f"({(db.labels_ < 0).sum():,} dwells left as noise)")

    rows = []
    for cid, g in clustered.groupby("cluster"):
        rows.append(dict(
            stop_id=int(cid),
            lat=round(g.lat.mean(), 6), lon=round(g.lon.mean(), 6),
            visits=len(g), runs=g.run_id.nunique(), drivers=g.driver.nunique(),
            median_dwell_s=int(g.dwell_s.median()),
            strong=bool(g.driver.nunique() >= STRONG_DRIVERS and len(g) >= STRONG_VISITS),
        ))
    stops = pd.DataFrame(rows).sort_values("visits", ascending=False).reset_index(drop=True)

    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {k: r[k] for k in ("stop_id", "visits", "runs", "drivers", "median_dwell_s", "strong")},
         "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]}}
        for _, r in stops.iterrows()]}
    with open(os.path.join(DATA, "stops_candidates.geojson"), "w", encoding="utf-8") as f:
        json.dump(fc, f)

    strong = stops[stops.strong]
    print(f"\n  candidate stops: {len(stops):,}  ·  strong (>= {STRONG_DRIVERS} drivers & {STRONG_VISITS} visits): {len(strong):,}")
    print("  busiest candidate stops (visits / runs / drivers):")
    for _, r in stops.head(8).iterrows():
        print(f"    ({r.lat:.4f},{r.lon:.4f})  {r.visits:>4} / {r.runs:>4} / {r.drivers:>3}  dwell~{r.median_dwell_s}s")

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.scatter(stops.lon, stops.lat, s=np.clip(stops.visits / 3, 4, 300),
                   c=np.where(stops.strong, "#0f8a5f", "#c0c0c0"), alpha=0.6, edgecolors="none")
        ax.set_title(f"Candidate stops ({len(stops)}; green = strong)\nsize = visits", fontsize=11, weight="bold")
        ax.set_aspect("equal", "datalim"); ax.set_xticks([]); ax.set_yticks([])
        fig.tight_layout(); fig.savefig(os.path.join(DATA, "stops.png"), dpi=140, bbox_inches="tight"); plt.close(fig)
    except Exception as e:
        print("(png skipped:", str(e)[:40], ")")

    print("\nWrote data/stops_candidates.geojson, data/stops.png")


if __name__ == "__main__":
    main()

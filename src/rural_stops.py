#!/usr/bin/env python
"""
TIER-2 STOPS — recover rural/valley-wide stop candidates the city-tuned gate missed.

stops.py used DBSCAN(min_samples=8) — right for dense Srinagar dwells, but rural
corridors (Anantnag, Pahalgam, Ganderbal, Sopore…) have fewer app runs, so their
recurring stopping places never hit 8 dwell events and were dropped. This pass:

  - re-clusters ALL 38k dwell events at min_samples=4;
  - keeps clusters with >=4 visits AND >=2 distinct drivers (repetition still
    required — one driver's habit is not a stop);
  - drops anything within 250 m of a Tier-1 candidate stop (already known);
  - labels each new stop's district by point-in-polygon (OSM boundaries);
  - only keeps stops INSIDE the 10-district study area.

Labelled TIER 2 — real repeated stopping places on thinner evidence than the
Tier-1 set. For field validation, not for publication as confirmed stops.

Outputs: data/stops_tier2.geojson · data/stops_tier2.png · appends dashboard
         export public/kashmir-reality/stops_tier2.geojson

Run:  & "D:\\plotting\\ana\\python.exe" src\\rural_stops.py
"""
import os, sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.neighbors import BallTree
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from common import DATA, hav_m

ENGINE = r"E:\kash"
DISTRICTS_GEOJSON = os.path.join(ENGINE, "kashmir_districts_osm.geojson")
DASH = os.environ.get("DASH_REPO", "E:/dash/bus-sathi-dashboard")

EPS_M = 35.0
MIN_SAMPLES = 4
MIN_VISITS = 4
MIN_DRIVERS = 2
DEDUP_M = 250.0


def main():
    ev = pd.read_pickle(os.path.join(DATA, "stop_events.pkl.gz"), compression="gzip")
    print(f"Dwell events: {len(ev):,}")

    labels = DBSCAN(eps=EPS_M / 6371000.0, min_samples=MIN_SAMPLES,
                    metric="haversine", algorithm="ball_tree").fit(
        np.radians(ev[["lat", "lon"]].to_numpy())).labels_
    ev = ev.assign(cluster=labels)
    cl = ev[ev.cluster >= 0].groupby("cluster").agg(
        lat=("lat", "median"), lon=("lon", "median"),
        visits=("run_id", "size"), drivers=("driver", "nunique"),
        dwell_s=("dwell_s", "median")).reset_index()
    cl = cl[(cl.visits >= MIN_VISITS) & (cl.drivers >= MIN_DRIVERS)]
    print(f"Clusters passing support gate (>= {MIN_VISITS} visits, >= {MIN_DRIVERS} drivers): {len(cl)}")

    # drop anything near a Tier-1 candidate stop
    t1 = json.load(open(os.path.join(DATA, "stops_candidates.geojson"), encoding="utf-8"))["features"]
    t1_pts = np.radians([[f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]] for f in t1])
    tree = BallTree(t1_pts, metric="haversine")
    d, _ = tree.query(np.radians(cl[["lat", "lon"]].to_numpy()), k=1)
    cl = cl[d[:, 0] * 6371000.0 > DEDUP_M].reset_index(drop=True)
    print(f"NEW (not within {DEDUP_M:.0f} m of a Tier-1 stop): {len(cl)}")

    # district by point-in-polygon; keep in-area only
    dj = json.load(open(DISTRICTS_GEOJSON, encoding="utf-8"))["features"]
    dpolys = [(f["properties"].get("district", f["properties"].get("name", "?")), shape(f["geometry"])) for f in dj]
    def district_of(lat, lon):
        p = Point(lon, lat)
        for name, poly in dpolys:
            if poly.contains(p):
                return name
        return None
    cl["district"] = [district_of(la, lo) for la, lo in zip(cl.lat, cl.lon)]
    cl = cl[cl.district.notna()].reset_index(drop=True)
    print(f"Inside the 10-district study area: {len(cl)}")
    print("\nBy district:")
    print(cl.district.value_counts().to_string())

    feats = [{"type": "Feature",
              "properties": {"stop_id": f"T2-{i+1}", "tier": 2, "visits": int(r.visits),
                             "drivers": int(r.drivers), "dwell_s": float(r.dwell_s),
                             "district": r.district},
              "geometry": {"type": "Point", "coordinates": [round(float(r.lon), 5), round(float(r.lat), 5)]}}
             for i, r in cl.iterrows()]
    gj = {"type": "FeatureCollection", "features": feats}
    with open(os.path.join(DATA, "stops_tier2.geojson"), "w", encoding="utf-8") as f:
        json.dump(gj, f)
    out = os.path.join(DASH, "public", "kashmir-reality")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "stops_tier2.geojson"), "w", encoding="utf-8") as f:
        json.dump(gj, f, separators=(",", ":"))

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9.5, 9.5))
        for name, poly in dpolys:
            geoms = poly.geoms if poly.geom_type == "MultiPolygon" else [poly]
            for g in geoms:
                xs, ys = g.exterior.xy
                ax.plot(xs, ys, color="#b9c6dd", lw=0.7)
        t1_lon = [f["geometry"]["coordinates"][0] for f in t1]
        t1_lat = [f["geometry"]["coordinates"][1] for f in t1]
        ax.scatter(t1_lon, t1_lat, s=8, color="#9fc3b4", alpha=0.6, label=f"Tier-1 stops ({len(t1)})")
        ax.scatter(cl.lon, cl.lat, s=16, color="#B0432F", alpha=0.85, label=f"NEW Tier-2 stops ({len(cl)})")
        ax.legend(fontsize=10, loc="upper right")
        ax.set_title("Tier-2 stop candidates — rural/valley-wide recovery\n(>=4 visits, >=2 drivers, not near a Tier-1 stop)", weight="bold")
        ax.set_aspect("equal", "datalim"); ax.set_xticks([]); ax.set_yticks([])
        fig.tight_layout(); fig.savefig(os.path.join(DATA, "stops_tier2.png"), dpi=140, bbox_inches="tight")
        plt.close(fig)
    except Exception as e:
        print("(png skipped:", str(e)[:60], ")")

    print("\nWrote data/stops_tier2.geojson, data/stops_tier2.png + dashboard stops_tier2.geojson")


if __name__ == "__main__":
    main()

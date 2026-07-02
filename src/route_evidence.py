#!/usr/bin/env python
"""
ROUTE EVIDENCE — fragment-aggregation over the WHOLE plan network.

Why: long-haul routes (Srinagar–Anantnag–Pahalgam, Ganderbal, Pattan…) exist in
the traces only as BROKEN FRAGMENTS (drivers toggle the app mid-journey), so no
single run ever spans the corridor and run-level clustering can't see them. But
the evidence is real — the speed layer lights up all the way to Pahalgam.

Method (fragments vote for road-km, runs don't need to be end-to-end):
  - every clean run (all 2,426 — not just corridor members) is rasterised to
    120 m grid cells;
  - every plan route (v3.4.5, 186 active) is rasterised the same way;
  - a route cell is OBSERVED if >=1 run covers it; per route we report
    coverage fraction, observed km, distinct drivers/runs with meaningful
    overlap (>= max(8 cells, 10% of the route)).

This upgrades the old permit_observed.csv (which only used the 25 corridor
geometries) to full-fragment evidence. Honest limits: coverage says "buses
drove this road", NOT "this exact route is operated end-to-end" — parallel
routes sharing a road segment share its evidence.

Outputs: data/route_evidence.csv · data/route_evidence.png
         dashboard export: public/kashmir-reality/plan_evidence.geojson (slim)

Run:  & "D:\\plotting\\ana\\python.exe" src\\route_evidence.py
"""
import os, sys, json, math
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import defaultdict
import numpy as np
import pandas as pd
from common import DATA

ENGINE = r"E:\kash"
ROUTES_GEOJSON = os.path.join(ENGINE, "outputs_v3.4.5", "Rationalised_Routes_Kashmir_v3.geojson")
DASH = os.environ.get("DASH_REPO", "E:/dash/bus-sathi-dashboard")

CELL_M = 120.0
LAT0 = 34.0
KX = math.cos(math.radians(LAT0)) * 111320.0
KY = 111320.0
MIN_CELLS_MEANINGFUL = 8        # a run/driver counts for a route above this overlap
MEANINGFUL_FRAC = 0.10


def cells_of(latlon_seq):
    out = set()
    prev = None
    for la, lo in latlon_seq:
        c = (round(lo * KX / CELL_M), round(la * KY / CELL_M))
        out.add(c)
        if prev is not None:                      # fill gaps between samples
            dx, dy = c[0] - prev[0], c[1] - prev[1]
            n = max(abs(dx), abs(dy))
            for k in range(1, n):
                out.add((prev[0] + round(dx * k / n), prev[1] + round(dy * k / n)))
        prev = c
    return out


def main():
    mm = pd.read_pickle(os.path.join(DATA, "runs_matched.pkl.gz"), compression="gzip")
    runs = mm[(mm.matched == True) & (mm.clean == True)].reset_index(drop=True)
    print(f"Clean runs (ALL, incl. fragments): {len(runs)}")

    cell_runs = defaultdict(set)      # cell -> run idxs
    run_driver = runs.driver.tolist()
    for i, g in enumerate(runs["geom"]):
        for c in cells_of(g):
            cell_runs[c].add(i)
    print(f"Occupied cells: {len(cell_runs):,}")

    j = json.load(open(ROUTES_GEOJSON, encoding="utf-8"))
    rows, slim_feats = [], []
    for f in j["features"]:
        p = f["properties"]
        coords = f["geometry"]["coordinates"]        # [lon, lat]
        rcells = cells_of([(la, lo) for lo, la in coords])
        n_cells = len(rcells)
        if n_cells < 5:
            continue
        covered = [c for c in rcells if c in cell_runs]
        cov = len(covered) / n_cells
        run_hits = defaultdict(int)
        for c in covered:
            for ri in cell_runs[c]:
                run_hits[ri] += 1
        thresh = max(MIN_CELLS_MEANINGFUL, MEANINGFUL_FRAC * n_cells)
        good_runs = [ri for ri, h in run_hits.items() if h >= thresh]
        drivers = {run_driver[ri] for ri in good_runs}
        km = float(p.get("Route_KM") or 0)
        rows.append(dict(route_id=p.get("New_Route_ID", ""), route_name=p.get("Route_Name", ""),
                         route_type=p.get("Route_Type", ""), km=km,
                         obs_frac=round(cov, 2), obs_km=round(cov * km, 1),
                         n_runs=len(good_runs), n_drivers=len(drivers)))
        # slim feature for the dashboard (simplified coords)
        step = max(1, len(coords) // 120)
        slim = coords[::step]
        if slim[-1] != coords[-1]:
            slim.append(coords[-1])
        slim_feats.append({"type": "Feature",
                           "properties": {"id": p.get("New_Route_ID", ""), "name": p.get("Route_Name", ""),
                                          "obs": round(cov, 2), "drv": len(drivers), "runs": len(good_runs)},
                           "geometry": {"type": "LineString",
                                        "coordinates": [[round(lo, 4), round(la, 4)] for lo, la in slim]}})

    df = pd.DataFrame(rows).sort_values("obs_frac", ascending=False)
    df.to_csv(os.path.join(DATA, "route_evidence.csv"), index=False)

    hi = df[(df.obs_frac >= 0.5) & (df.n_drivers >= 2)]
    md = df[(df.obs_frac >= 0.2) & (df.obs_frac < 0.5) & (df.n_drivers >= 2)]
    print(f"\nPlan routes with STRONG fragment evidence (>=50% covered, >=2 drivers): {len(hi)}")
    print(f"Plan routes with PARTIAL fragment evidence (20-50%, >=2 drivers): {len(md)}")
    print(f"(old corridor-only method saw far less — fragments now count)")
    print("\nTop 25 by coverage:")
    print(df.head(25).to_string(index=False))

    out = os.path.join(DASH, "public", "kashmir-reality")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "plan_evidence.geojson"), "w", encoding="utf-8") as fp:
        json.dump({"type": "FeatureCollection", "features": slim_feats}, fp, separators=(",", ":"))
    print(f"\nWrote data/route_evidence.csv + dashboard plan_evidence.geojson "
          f"({os.path.getsize(os.path.join(out, 'plan_evidence.geojson'))//1024} KB)")

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        import matplotlib.lines as ml
        fig, ax = plt.subplots(figsize=(10, 10))
        for f, r in zip(slim_feats, rows):
            c = np.array(f["geometry"]["coordinates"])
            o = r["obs_frac"]
            col = "#0f8a5f" if o >= 0.5 else ("#e0a100" if o >= 0.2 else "#d9d2c5")
            ax.plot(c[:, 0], c[:, 1], "-", color=col, lw=2.0 if o >= 0.5 else 1.2,
                    alpha=0.85 if o >= 0.2 else 0.5, zorder=3 if o >= 0.5 else 2)
        ax.legend(handles=[ml.Line2D([], [], color="#0f8a5f", lw=2, label=f"observed >=50% ({len(hi)})"),
                           ml.Line2D([], [], color="#e0a100", label=f"partial 20-50% ({len(md)})"),
                           ml.Line2D([], [], color="#d9d2c5", label="little/no app data")],
                  fontsize=10, loc="upper right")
        ax.set_title("Plan routes by FRAGMENT evidence — broken runs now count\n"
                     "(coverage = road driven, not end-to-end operation)", weight="bold", fontsize=11)
        ax.set_aspect("equal", "datalim"); ax.set_xticks([]); ax.set_yticks([])
        fig.tight_layout(); fig.savefig(os.path.join(DATA, "route_evidence.png"), dpi=140, bbox_inches="tight")
        plt.close(fig)
        print("Wrote data/route_evidence.png")
    except Exception as e:
        print("(png skipped:", str(e)[:60], ")")


if __name__ == "__main__":
    main()

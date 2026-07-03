#!/usr/bin/env python
"""
GEOMETRY-DIVERGENCE CANDIDATES — where the engine's OSRM shortest-path differs
from the path buses actually drive between the SAME endpoints.

Two independent detectors, both honest about the same-OD requirement (a partial
overlap between DIFFERENT O-D pairs is not a geometry error):

  A. CORRIDOR-BASED: for each observed corridor (Tier-1 + Tier-2 candidates),
     find plan routes whose BOTH endpoints sit within END_M of the corridor's
     endpoints (either orientation). If path overlap < SAME_PATH, the plan
     route's routed line takes a different path than real buses between the
     same two places -> geometry-fix candidate, with the observed map-matched
     line as the replacement geometry (it is already road-valid).

  B. COVERAGE-GAP: plan routes whose fragment coverage is high at both ends but
     has a contiguous uncovered MIDDLE >= GAP_KM (with >= MIN_DRV drivers on
     the covered parts) — the classic signature of an OSRM detour nobody drives.
     These need per-route review (the divergent middle could also be genuinely
     unserved road).

Output: data/geometry_divergence.csv + printed shortlist for review.
Run:  & "D:\\plotting\\ana\\python.exe" src\\geometry_divergence.py
"""
import os, sys, json, math
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import defaultdict
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point
from common import DATA, hav_m

ENGINE = r"E:\kash"
PLAN = os.path.join(ENGINE, "outputs_v3.4.5", "Rationalised_Routes_Kashmir_v3.geojson")

END_M = 900.0          # endpoint match tolerance (terminal areas are big)
SAME_PATH = 0.75       # below this path overlap w/ same endpoints => divergence
NEAR_M = 60.0
CELL_M = 120.0
GAP_KM = 1.5
MIN_DRV = 3
LAT0 = 34.0
KX = math.cos(math.radians(LAT0)) * 111320.0
KY = 111320.0


def to_m(lat, lon):
    return (lon * KX, lat * KY)


def cells_of(latlon_seq):
    out = set(); prev = None
    for la, lo in latlon_seq:
        c = (round(lo * KX / CELL_M), round(la * KY / CELL_M))
        out.add(c)
        if prev is not None:
            dx, dy = c[0] - prev[0], c[1] - prev[1]
            n = max(abs(dx), abs(dy))
            for k in range(1, n):
                out.add((prev[0] + round(dx * k / n), prev[1] + round(dy * k / n)))
        prev = c
    return out


def main():
    plan = json.load(open(PLAN, encoding="utf-8"))["features"]
    plines = []
    for f in plan:
        c = f["geometry"]["coordinates"]
        if len(c) < 2: continue
        plines.append(dict(id=f["properties"].get("New_Route_ID"), name=f["properties"].get("Route_Name"),
                           km=f["properties"].get("Route_KM"), coords=[(la, lo) for lo, la in c],
                           line=LineString([to_m(la, lo) for lo, la in c])))

    # observed corridors: published 18 + tier-2 candidates (in-area)
    obs = []
    for src, tag in (("analyst/corridors_verdicts.geojson", "T1"), ("data/tail_candidates.geojson", "T2")):
        p = src if os.path.isabs(src) else os.path.join(os.path.dirname(DATA), src) if src.startswith("analyst") else os.path.join(DATA, os.path.basename(src))
        gj = json.load(open(p, encoding="utf-8"))
        for f in gj["features"]:
            pr = f["properties"]
            if tag == "T1" and pr.get("class") in ("out_of_area", "artifact"): continue
            cid = f"{'C' if tag=='T1' else 'T'}{pr.get('corridor_id', pr.get('tail_id'))}"
            coords = [(la, lo) for lo, la in f["geometry"]["coordinates"]]
            obs.append(dict(cid=cid, tag=tag, coords=coords,
                            n_runs=pr.get("n_runs", 0), n_drivers=pr.get("n_drivers", 0)))

    print(f"plan routes: {len(plines)} | observed lines: {len(obs)}")

    # ── A. same-endpoints different-path ────────────────────────────
    rows = []
    for o in obs:
        oa, ob = o["coords"][0], o["coords"][-1]
        for pl in plines:
            pa, pb = pl["coords"][0], pl["coords"][-1]
            d1 = max(hav_m(*oa, *pa), hav_m(*ob, *pb))
            d2 = max(hav_m(*oa, *pb), hav_m(*ob, *pa))
            if min(d1, d2) > END_M: continue
            samp = o["coords"][:: max(1, len(o["coords"]) // 80)]
            on = sum(1 for la, lo in samp if pl["line"].distance(Point(to_m(la, lo))) <= NEAR_M)
            ov = on / len(samp)
            if ov < SAME_PATH:
                rows.append(dict(detector="A_same_OD_diff_path", corridor=o["cid"],
                                 route_id=pl["id"], route=pl["name"], plan_km=round(float(pl["km"]), 1),
                                 overlap=round(ov, 2), n_runs=o["n_runs"], n_drivers=o["n_drivers"]))

    # ── B. coverage-gap (endpoint-covered, middle uncovered) ────────
    mm = pd.read_pickle(os.path.join(DATA, "runs_matched.pkl.gz"), compression="gzip")
    runs = mm[(mm.matched == True) & (mm.clean == True)]
    cell_drv = defaultdict(set)
    for g, drv in zip(runs["geom"], runs["driver"]):
        for c in cells_of(g):
            cell_drv[c].add(drv)

    for pl in plines:
        seq = pl["coords"][:: max(1, len(pl["coords"]) // 200)]
        cov = []
        for la, lo in seq:
            c = (round(lo * KX / CELL_M), round(la * KY / CELL_M))
            cov.append(len(cell_drv.get(c, ())))
        cov = np.array(cov)
        n = len(cov)
        if n < 20: continue
        end_n = max(3, n // 10)
        head_ok = (cov[:end_n] >= MIN_DRV).mean() >= 0.6
        tail_ok = (cov[-end_n:] >= MIN_DRV).mean() >= 0.6
        if not (head_ok and tail_ok): continue
        # longest contiguous uncovered stretch in the middle
        best = cur = 0
        for v in cov[end_n:-end_n]:
            cur = cur + 1 if v == 0 else 0
            best = max(best, cur)
        gap_km = best / max(1, n) * float(pl["km"] or 0)
        if gap_km >= GAP_KM:
            rows.append(dict(detector="B_coverage_gap", corridor="", route_id=pl["id"], route=pl["name"],
                             plan_km=round(float(pl["km"]), 1), overlap=None,
                             n_runs=int(cov.max()), n_drivers=int(np.median(cov[cov > 0])) if (cov > 0).any() else 0,
                             gap_km=round(gap_km, 1)))

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(DATA, "geometry_divergence.csv"), index=False)
    if df.empty:
        print("No candidates found."); return
    print("\n── A. SAME endpoints, DIFFERENT path (true geometry-fix candidates) ──")
    a = df[df.detector == "A_same_OD_diff_path"]
    print(a.to_string(index=False) if not a.empty else "  none")
    print("\n── B. Coverage-gap candidates (endpoint-covered, uncovered middle) ──")
    b = df[df.detector == "B_coverage_gap"]
    print(b.drop(columns=["corridor", "overlap"]).to_string(index=False) if not b.empty else "  none")
    print(f"\nWrote data/geometry_divergence.csv ({len(df)} rows)")


if __name__ == "__main__":
    main()

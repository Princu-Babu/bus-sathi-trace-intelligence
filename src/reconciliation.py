#!/usr/bin/env python
"""
Geometry-reconciliation workbench data — the 8 PARTIAL corridors where observed
reality diverges from the plan's routed line, packaged so the divergence is
actionable instead of a parked finding.

Per partial corridor: the OBSERVED line + its matched PLAN route line in one
geojson pair, plus a worklist row (overlap %, km both ways, divergence km,
support). Feeds (a) the dashboard Reality tab reconciliation panel and (b) a
worklist CSV for the next engine geometry pass (v3.4.6 candidate).

Outputs: data/reconciliation_worklist.csv
         dashboard public/kashmir-reality/reconciliation.geojson

Run:  & "D:\\plotting\\ana\\python.exe" src\\reconciliation.py
"""
import os, sys, json, glob, math
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
from shapely.geometry import LineString, Point
from common import DATA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = r"E:\kash"
PLAN = os.path.join(ENGINE, "outputs_v3.4.5", "Rationalised_Routes_Kashmir_v3.geojson")
DASH = os.environ.get("DASH_REPO", "E:/dash/bus-sathi-dashboard")

NEAR_M = 60.0
LAT0 = 34.0
KX = math.cos(math.radians(LAT0)) * 111320.0
KY = 111320.0


def to_m(lat, lon):
    return (lon * KX, lat * KY)


def main():
    plan = {f["properties"].get("New_Route_ID"): f
            for f in json.load(open(PLAN, encoding="utf-8"))["features"]}

    verdicts = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "analyst", "verdicts", "C*.json"))):
        v = json.load(open(p, encoding="utf-8"))
        verdicts[int(os.path.basename(p)[1:-5])] = v

    corr = json.load(open(os.path.join(ROOT, "analyst", "corridors_verdicts.geojson"), encoding="utf-8"))

    rows, feats = [], []
    for f in corr["features"]:
        p = f["properties"]
        if p.get("class") != "partial":
            continue
        cid = p["corridor_id"]
        v = verdicts.get(cid, {})
        pid = v.get("matched_permit_id") or ""
        pf = plan.get(pid)
        obs_ll = [(la, lo) for lo, la in f["geometry"]["coordinates"]]
        obs_line = LineString([to_m(la, lo) for la, lo in obs_ll])
        obs_km = obs_line.length / 1000.0

        plan_km = None; div_km = None; overlap = None; plan_coords = None
        if pf:
            plan_ll = [(la, lo) for lo, la in pf["geometry"]["coordinates"]]
            plan_line = LineString([to_m(la, lo) for la, lo in plan_ll])
            plan_km = plan_line.length / 1000.0
            samp = obs_ll[:: max(1, len(obs_ll) // 80)]
            on = sum(1 for la, lo in samp if plan_line.distance(Point(to_m(la, lo))) <= NEAR_M)
            overlap = on / len(samp)
            div_km = obs_km * (1 - overlap)
            step = max(1, len(pf["geometry"]["coordinates"]) // 150)
            plan_coords = [[round(lo, 5), round(la, 5)] for lo, la in pf["geometry"]["coordinates"][::step]]

        rows.append(dict(corridor=f"C{cid}", od=v.get("od_description", p.get("od", "")),
                         matched_route=p.get("matched_permit", ""), matched_id=pid,
                         n_runs=p.get("n_runs", 0), n_drivers=p.get("n_drivers", 0),
                         obs_km=round(obs_km, 1),
                         plan_km=round(plan_km, 1) if plan_km else None,
                         overlap_frac=round(overlap, 2) if overlap is not None else None,
                         divergent_km=round(div_km, 1) if div_km is not None else None,
                         note=("observed alignment differs from routed line — candidate for the next "
                               "engine geometry pass (re-geocode / via-waypoint fix)")))
        props = dict(corridor_id=cid, od=v.get("od_description", ""), matched=p.get("matched_permit", ""),
                     matched_id=pid, n_runs=p.get("n_runs", 0), n_drivers=p.get("n_drivers", 0),
                     obs_km=round(obs_km, 1), plan_km=round(plan_km, 1) if plan_km else None,
                     overlap=round(overlap, 2) if overlap is not None else None)
        feats.append({"type": "Feature", "properties": {**props, "kind": "observed"},
                      "geometry": {"type": "LineString",
                                   "coordinates": [[round(lo, 5), round(la, 5)] for la, lo in obs_ll]}})
        if plan_coords:
            feats.append({"type": "Feature", "properties": {**props, "kind": "plan"},
                          "geometry": {"type": "LineString", "coordinates": plan_coords}})

    df = pd.DataFrame(rows).sort_values("n_runs", ascending=False)
    df.to_csv(os.path.join(DATA, "reconciliation_worklist.csv"), index=False)
    out = os.path.join(DASH, "public", "kashmir-reality", "reconciliation.geojson")
    with open(out, "w", encoding="utf-8") as fp:
        json.dump({"type": "FeatureCollection", "features": feats}, fp, separators=(",", ":"))
    print(df.to_string(index=False))
    print(f"\nWrote data/reconciliation_worklist.csv + {out} ({len(feats)} features)")


if __name__ == "__main__":
    main()

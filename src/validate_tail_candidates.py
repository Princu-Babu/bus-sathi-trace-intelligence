#!/usr/bin/env python
"""
Script-only first-pass triage of the 30 Tier-2 tail candidates — same overlay
method as validate_permits.py (against the CURRENT v3.4.5 rationalised geometry,
study-area clipped) PLUS a raw-permit endpoint-proximity check (the audit lesson
from the Tier-1 pass: overlap against rationalised geometry alone mislabels
"geometry diverges" as "informal" — always cross-check the raw 614-permit list
before calling anything unpermitted).

This is NOT a verdict. It's a cheap sort so a human/AI-analyst pass only spends
attention on the candidates that actually need judgment.

Run:  & "D:\\plotting\\ana\\python.exe" src\\validate_tail_candidates.py
"""
import os, json, math, csv
import pandas as pd
from shapely.geometry import LineString, Point, shape
from shapely.strtree import STRtree
from shapely.ops import unary_union
from common import DATA

ENGINE = r"E:\kash"
ROUTES_GEOJSON = os.path.join(ENGINE, "outputs_v3.4.5", "Rationalised_Routes_Kashmir_v3.geojson")
DISTRICTS_GEOJSON = os.path.join(ENGINE, "kashmir_districts_osm.geojson")
PERMITS_CSV = os.path.join(ENGINE, "existing-routes.csv")

NEAR_M = 60.0
MATCH_HI, MATCH_LO = 0.60, 0.35
IN_AREA_MIN = 0.5
ENDPOINT_NEAR_M = 400.0   # raw-permit endpoint proximity (coarser — permits are point pairs, not paths)
LAT0 = 34.0
KX = math.cos(math.radians(LAT0)) * 111320.0
KY = 111320.0


def to_m(lat, lon):
    return (lon * KX, lat * KY)


def main():
    j = json.load(open(ROUTES_GEOJSON, encoding="utf-8"))
    routes = [dict(props=f["properties"], line=LineString([to_m(la, lo) for lo, la in f["geometry"]["coordinates"]]))
              for f in j["features"] if f["geometry"]["type"] == "LineString" and len(f["geometry"]["coordinates"]) >= 2]
    rtree = STRtree([r["line"] for r in routes])
    n_r = len(routes)

    study = unary_union([shape(f["geometry"]) for f in json.load(open(DISTRICTS_GEOJSON, encoding="utf-8"))["features"]])

    permits = pd.read_csv(PERMITS_CSV)
    ppts = [Point(to_m(la, lo)) for la, lo in
            zip(pd.concat([permits.Origin_Lat, permits.Dest_Lat]), pd.concat([permits.Origin_Lon, permits.Dest_Lon]))]
    ptree = STRtree(ppts)

    cand = json.load(open(os.path.join(DATA, "tail_candidates.geojson"), encoding="utf-8"))["features"]
    print(f"Tier-2 candidates: {len(cand)} | planned routes: {n_r} | raw permits: {len(permits)}")

    rows = []
    for f in cand:
        p = f["properties"]
        coords = f["geometry"]["coordinates"]
        in_frac = sum(1 for lo, la in coords if study.contains(Point(lo, la))) / len(coords)
        if in_frac < IN_AREA_MIN:
            verdict, frac, matched_name = "OUT_OF_AREA", 0.0, ""
        else:
            pts_m = [Point(to_m(la, lo)) for lo, la in coords]
            per = [0] * n_r
            for pt in pts_m:
                for i in rtree.query(pt, predicate="dwithin", distance=NEAR_M):
                    per[int(i)] += 1
            bi = max(range(n_r), key=lambda i: per[i]) if n_r else None
            frac = per[bi] / len(pts_m) if bi is not None else 0.0
            verdict = "MATCHED" if frac >= MATCH_HI else ("PARTIAL" if frac >= MATCH_LO else "UNMATCHED")
            matched_name = routes[bi]["props"].get("Route_Name", "") if bi is not None and verdict != "UNMATCHED" else ""

        # raw-permit endpoint check near this candidate's own endpoints (audit-safe)
        ends_m = [Point(to_m(*coords[0][::-1])), Point(to_m(*coords[-1][::-1]))]
        near_permits = set()
        for e in ends_m:
            for i in ptree.query(e, predicate="dwithin", distance=ENDPOINT_NEAR_M):
                near_permits.add(int(i) % len(permits))
        rows.append(dict(tail_id=p["tail_id"], n_runs=p["n_runs"], n_drivers=p["n_drivers"],
                         median_km=p["median_km"], in_area=round(in_frac, 2), verdict=verdict,
                         route_cover=round(frac, 2), matched_route=matched_name,
                         nearby_raw_permits=len(near_permits)))

    df = pd.DataFrame(rows).sort_values("n_runs", ascending=False)
    df.to_csv(os.path.join(DATA, "tail_candidates_triage.csv"), index=False)
    print("\n" + df.to_string(index=False))

    print("\n── Triage tally ─────────────────────────")
    print(df.verdict.value_counts().to_string())
    needs_look = df[(df.verdict == "UNMATCHED") & (df.nearby_raw_permits == 0)]
    print(f"\nGenuinely worth an analyst look (UNMATCHED to plan AND 0 nearby raw permits): {len(needs_look)}")
    if len(needs_look):
        print(needs_look[["tail_id", "n_runs", "n_drivers", "median_km"]].to_string(index=False))
    print("\nWrote data/tail_candidates_triage.csv")


if __name__ == "__main__":
    main()

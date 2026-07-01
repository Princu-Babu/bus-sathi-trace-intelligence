#!/usr/bin/env python
"""
Overlay observed corridors on the planned/permit route network, CLIPPED to the
Kashmir Division study area (so out-of-division highway runs aren't mislabelled).

Per corridor (that lies mostly inside the 10-district study area):
  - MATCHED   (>=60% within 60 m of a planned route) -> a permit genuinely run
  - PARTIAL   (35-60%)  -> runs a permit but deviates
  - INFORMAL  (<35%)    -> observed corridor with no matching permit  (the finding)
Corridors mostly outside the study area -> OUT_OF_AREA (e.g. NH-44 to Jammu).

Per planned route: observed coverage -> OBSERVED / PARTIAL / NO_APP_DATA
(partial app adoption => NO_APP_DATA means "unseen in traces", not "unused").

Outputs (gitignored):
  data/corridor_permit_match.geojson · data/permit_observed.csv · data/validate_permits.png

Run:  & "D:\\plotting\\ana\\python.exe" src\\validate_permits.py
"""
import os, json, math, csv
from shapely.geometry import LineString, Point, shape
from shapely.strtree import STRtree
from shapely.ops import unary_union
from common import DATA

ENGINE = r"E:\kash"
ROUTES_GEOJSON = os.path.join(ENGINE, "outputs_v3.4.4", "Rationalised_Routes_Kashmir_v3.geojson")
DISTRICTS_GEOJSON = os.path.join(ENGINE, "kashmir_districts_osm.geojson")

NEAR_M = 60.0
MATCH_HI, MATCH_LO = 0.60, 0.35
IN_AREA_MIN = 0.5
LAT0 = 34.0
_KX = math.cos(math.radians(LAT0)) * 111320.0
_KY = 111320.0


def to_m(lat, lon):
    return (lon * _KX, lat * _KY)


def main():
    j = json.load(open(ROUTES_GEOJSON, encoding="utf-8"))
    routes = []
    for f in j["features"]:
        g = f["geometry"]
        if g["type"] == "LineString" and len(g["coordinates"]) >= 2:
            routes.append(dict(props=f["properties"],
                               line=LineString([to_m(la, lo) for lo, la in g["coordinates"]])))
    rtree = STRtree([r["line"] for r in routes])
    n_r = len(routes)
    print(f"Loaded {n_r} planned routes")

    study = unary_union([shape(f["geometry"]) for f in
                         json.load(open(DISTRICTS_GEOJSON, encoding="utf-8"))["features"]])
    print("Loaded 10-district study area")

    corr = json.load(open(os.path.join(DATA, "corridors.geojson"), encoding="utf-8"))["features"]
    print(f"Loaded {len(corr)} observed corridors")

    out_feats = []
    vc = {"MATCHED": 0, "PARTIAL": 0, "INFORMAL": 0, "OUT_OF_AREA": 0}
    informal = []
    for f in corr:
        coords = f["geometry"]["coordinates"]              # [lon,lat]
        in_frac = sum(1 for lo, la in coords if study.contains(Point(lo, la))) / len(coords)
        if in_frac < IN_AREA_MIN:
            verdict, frac, bi = "OUT_OF_AREA", 0.0, None
        else:
            pts = [Point(to_m(la, lo)) for lo, la in coords]
            per = [0] * n_r; hit = 0
            for p in pts:
                idx = rtree.query(p, predicate="dwithin", distance=NEAR_M)
                if len(idx):
                    hit += 1
                    for i in idx:
                        per[int(i)] += 1
            bi = max(range(n_r), key=lambda i: per[i]) if n_r else None
            frac = per[bi] / len(pts) if bi is not None else 0.0
            verdict = "MATCHED" if frac >= MATCH_HI else ("PARTIAL" if frac >= MATCH_LO else "INFORMAL")
        vc[verdict] += 1
        p = dict(f["properties"])
        p.update(verdict=verdict, route_cover=round(frac, 2), in_area=round(in_frac, 2),
                 matched_route=routes[bi]["props"].get("Route_Name", "") if (bi is not None and verdict in ("MATCHED", "PARTIAL")) else "")
        out_feats.append({"type": "Feature", "properties": p, "geometry": f["geometry"]})
        if verdict == "INFORMAL":
            informal.append(p)
    with open(os.path.join(DATA, "corridor_permit_match.geojson"), "w", encoding="utf-8") as fp:
        json.dump({"type": "FeatureCollection", "features": out_feats}, fp)

    # permit -> observed (within-area corridors only)
    corr_lines = [LineString([to_m(la, lo) for lo, la in f["geometry"]["coordinates"]])
                  for f, of in zip(corr, out_feats) if of["properties"]["verdict"] != "OUT_OF_AREA"]
    ctree = STRtree(corr_lines)
    rows, oc = [], {"OBSERVED": 0, "PARTIAL": 0, "NO_APP_DATA": 0}
    for r in routes:
        npt = max(2, int(r["line"].length / 40.0))
        samples = [r["line"].interpolate(i / npt, normalized=True) for i in range(npt + 1)]
        frac = sum(1 for s in samples if len(ctree.query(s, predicate="dwithin", distance=NEAR_M))) / len(samples)
        status = "OBSERVED" if frac >= 0.50 else ("PARTIAL" if frac >= 0.20 else "NO_APP_DATA")
        oc[status] += 1
        rows.append(dict(route_id=r["props"].get("New_Route_ID", ""), route_name=r["props"].get("Route_Name", ""),
                         route_type=r["props"].get("Route_Type", ""), km=r["props"].get("Route_KM", ""),
                         observed_cover=round(frac, 2), status=status))
    with open(os.path.join(DATA, "permit_observed.csv"), "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    print("\n── Corridor -> permit (study-area clipped) ─────────")
    for k in ("MATCHED", "PARTIAL", "INFORMAL", "OUT_OF_AREA"):
        print(f"  {k:<12} {vc[k]:>3}")
    print("── Permit -> observed (partial adoption!) ──────────")
    for k, v in oc.items():
        print(f"  {k:<12} {v:>3}")
    strong_inf = sorted([p for p in informal if p.get("n_runs", 0) >= 5 and p.get("n_drivers", 0) >= 2],
                        key=lambda p: -p.get("n_runs", 0))
    print(f"\nStrong INFORMAL candidates (>=5 runs, >=2 drivers): {len(strong_inf)}")
    for p in strong_inf[:6]:
        print(f"   C{p.get('corridor_id')}  {p.get('n_runs')} runs / {p.get('n_drivers')} drivers / {p.get('median_km')}km")

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        import matplotlib.lines as ml
        col = {"MATCHED": "#0f8a5f", "PARTIAL": "#e0a100", "INFORMAL": "#c62828", "OUT_OF_AREA": "#d9d2c5"}
        fig, ax = plt.subplots(figsize=(9.5, 9.5))
        geoms = study.geoms if study.geom_type == "MultiPolygon" else [study]
        for poly in geoms:
            xs, ys = poly.exterior.xy
            ax.plot([x * _KX for x in xs], [y * _KY for y in ys], color="#8aa0c8", lw=0.8, alpha=0.6)
        for r in routes:
            xs, ys = r["line"].xy
            ax.plot(xs, ys, "-", color="#cfcfcf", lw=0.8, zorder=1)
        for f in out_feats:
            xy = [to_m(la, lo) for lo, la in f["geometry"]["coordinates"]]
            v = f["properties"]["verdict"]
            ax.plot([p[0] for p in xy], [p[1] for p in xy], "-", color=col[v],
                    lw=1.3 if v == "OUT_OF_AREA" else 1.9, alpha=0.75, zorder=2)
        ax.legend(handles=[ml.Line2D([], [], color="#8aa0c8", label="study area"),
                           ml.Line2D([], [], color="#cfcfcf", label="planned routes"),
                           ml.Line2D([], [], color=col["MATCHED"], label=f"matched ({vc['MATCHED']})"),
                           ml.Line2D([], [], color=col["PARTIAL"], label=f"partial ({vc['PARTIAL']})"),
                           ml.Line2D([], [], color=col["INFORMAL"], label=f"informal ({vc['INFORMAL']})"),
                           ml.Line2D([], [], color=col["OUT_OF_AREA"], label=f"out of area ({vc['OUT_OF_AREA']})")],
                  fontsize=9, loc="upper right")
        ax.set_title("Observed corridors vs planned permit network (study-area clipped)", weight="bold")
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        fig.tight_layout(); fig.savefig(os.path.join(DATA, "validate_permits.png"), dpi=140, bbox_inches="tight"); plt.close(fig)
    except Exception as e:
        print("(png skipped:", str(e)[:60], ")")

    print("\nWrote data/corridor_permit_match.geojson, data/permit_observed.csv, data/validate_permits.png")


if __name__ == "__main__":
    main()

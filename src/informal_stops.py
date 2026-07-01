#!/usr/bin/env python
"""
Compare observed candidate stops against the engine's canonical stop register.

The register is 143 *canonical* named stops/terminals for the whole division
(coord-approximate), while the GPS yields fine-grained dwell clusters
concentrated where the app is used. So we do a FAIR comparison:

  - restrict to the observed footprint (register stops with observed data nearby);
  - CONFIRMED = register stop with a strong observed stop within 200 m
    (corroborates + sharpens the register coordinate);
  - CANDIDATE ADDITION = strong, in-area observed stop >200 m from any register
    stop (evidence-based stop the register lacks — for RTO confirmation).

Deliberately conservative (only STRONG observed stops) so sparse data can't
manufacture stops.

Outputs (gitignored): data/stops_vs_register.geojson · data/stops_vs_register.png

Run:  & "D:\\plotting\\ana\\python.exe" src\\informal_stops.py
"""
import os, json, csv
import numpy as np
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from sklearn.neighbors import BallTree
from common import DATA

ENGINE = r"E:\kash"
STOPS_CSV = os.path.join(ENGINE, "Kashmir_Stops_Master_v4.csv")
DISTRICTS_GEOJSON = os.path.join(ENGINE, "kashmir_districts_osm.geojson")
MATCH_M = 200.0        # register coords are approximate — tolerate 200 m
FOOTPRINT_M = 1500.0   # a register stop is "in observed area" if data is this close


def main():
    reg = []
    with open(STOPS_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                reg.append((float(r["Latitude"]), float(r["Longitude"]), r["Stop_Name"]))
            except (KeyError, ValueError):
                pass
    reg_ll = np.array([[a, b] for a, b, _ in reg])
    reg_tree = BallTree(np.radians(reg_ll), metric="haversine")
    print(f"Register: {len(reg)} canonical stops")

    study = unary_union([shape(f["geometry"]) for f in
                         json.load(open(DISTRICTS_GEOJSON, encoding="utf-8"))["features"]])
    cands = json.load(open(os.path.join(DATA, "stops_candidates.geojson"), encoding="utf-8"))["features"]
    cand_ll = np.array([[c["geometry"]["coordinates"][1], c["geometry"]["coordinates"][0]] for c in cands])
    strong_mask = np.array([bool(c["properties"].get("strong")) for c in cands])
    cand_tree = BallTree(np.radians(cand_ll[strong_mask]), metric="haversine") if strong_mask.any() else None
    print(f"Candidate stops: {len(cands)} ({int(strong_mask.sum())} strong)")

    # ── register corroboration (within observed footprint) ────────────────
    in_scope = confirmed = 0
    for i, (lat, lon, _) in enumerate(reg):
        if cand_tree is None:
            break
        d, _ = cand_tree.query(np.radians([[lat, lon]]), k=1)
        dm = d[0][0] * 6371000.0
        if dm <= FOOTPRINT_M:
            in_scope += 1
            if dm <= MATCH_M:
                confirmed += 1

    # ── classify candidates ───────────────────────────────────────────────
    feats, n_conf, n_add, n_out = [], 0, 0, 0
    add_rows = []
    for c in cands:
        lon, lat = c["geometry"]["coordinates"]; p = c["properties"]
        d, _ = reg_tree.query(np.radians([[lat, lon]]), k=1); dm = float(d[0][0] * 6371000.0)
        in_area = study.contains(Point(lon, lat))
        if not in_area:
            cls = "out_of_area"; n_out += 1
        elif dm <= MATCH_M:
            cls = "confirmed"; n_conf += 1
        elif p.get("strong"):
            cls = "candidate_add"; n_add += 1; add_rows.append((p, dm))
        else:
            cls = "weak"
        feats.append({"type": "Feature",
                      "properties": {**{k: p.get(k) for k in ("visits", "runs", "drivers", "median_dwell_s", "strong")},
                                     "class": cls, "nearest_register_m": round(dm)},
                      "geometry": c["geometry"]})
    with open(os.path.join(DATA, "stops_vs_register.geojson"), "w", encoding="utf-8") as fp:
        json.dump({"type": "FeatureCollection", "features": feats}, fp)

    pct = (100 * confirmed / in_scope) if in_scope else 0
    print("\n── Stops vs register (fair, footprint-restricted) ──")
    print(f"  Register stops with observed data nearby (in scope): {in_scope} / {len(reg)}")
    print(f"  ...corroborated by a strong observed stop (<={int(MATCH_M)}m):  {confirmed}  ({pct:.0f}%)")
    print(f"  Observed stops confirming the register:              {n_conf}")
    print(f"  CANDIDATE additions (strong, in-area, > {int(MATCH_M)}m):   {n_add}")
    print(f"  (out-of-area candidates ignored: {n_out})")
    print("\n  Top candidate-addition stops (visits / runs / drivers):")
    for p, dm in sorted(add_rows, key=lambda x: -x[0].get("visits", 0))[:8]:
        print(f"    {p['visits']:>4} / {p['runs']:>4} / {p['drivers']:>3}   ~{int(dm)}m from nearest register")

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 9))
        geoms = study.geoms if study.geom_type == "MultiPolygon" else [study]
        for poly in geoms:
            xs, ys = poly.exterior.xy; ax.plot(xs, ys, color="#8aa0c8", lw=0.7, alpha=0.5)
        ax.scatter(reg_ll[:, 1], reg_ll[:, 0], s=16, marker="s", color="#2b6cb0", alpha=0.7, label=f"register ({len(reg)})")
        cmap = {"confirmed": "#0f8a5f", "candidate_add": "#c62828", "weak": "#d9c9a0"}
        for cls in ("weak", "confirmed", "candidate_add"):
            sel = [f for f in feats if f["properties"]["class"] == cls]
            if not sel:
                continue
            xs = [f["geometry"]["coordinates"][0] for f in sel]; ys = [f["geometry"]["coordinates"][1] for f in sel]
            sz = [np.clip(f["properties"]["visits"] / 3, 6, 250) for f in sel]
            lbl = {"confirmed": f"confirms register ({n_conf})", "candidate_add": f"candidate add ({n_add})"}.get(cls)
            ax.scatter(xs, ys, s=sz, color=cmap[cls], alpha=0.6, edgecolors="none", label=lbl)
        ax.legend(fontsize=9, loc="upper right")
        ax.set_title("Observed stops vs register — red = evidence-based additions (size = visits)", weight="bold")
        ax.set_aspect("equal", "datalim"); ax.set_xticks([]); ax.set_yticks([])
        fig.tight_layout(); fig.savefig(os.path.join(DATA, "stops_vs_register.png"), dpi=140, bbox_inches="tight"); plt.close(fig)
    except Exception as e:
        print("(png skipped:", str(e)[:60], ")")

    print("\nWrote data/stops_vs_register.geojson, data/stops_vs_register.png")


if __name__ == "__main__":
    main()

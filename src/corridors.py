#!/usr/bin/env python
"""
Cluster clean map-matched runs into observed CORRIDORS + their frequency.

A corridor = origin terminal <-> destination terminal (undirected). Two
refinements (added after the AI analyst found the core spine was fragmenting):

  1. ROBUST TERMINALS — a terminal must be anchored by endpoints from >=3 distinct
     DRIVERS, not just >=3 endpoints. This kills 1-2 driver "spur" artifacts (e.g.
     a single driver's odd end) that were splitting one real route into several.
     Runs whose endpoint falls on a dropped terminal snap to the nearest robust
     terminal within SNAP_M, else that run is not assigned a corridor.

  2. CONTAINMENT MERGE — after forming terminal-pair corridors, a shorter corridor
     whose path lies >=70% within 60 m of a LONGER corridor that SHARES a terminal
     is merged into it (a truncated variant of the same route, e.g. Soura↔central
     folds into Soura↔Lalchowk). Directed containment (short⊆long) means divergent
     routes sharing only a terminal (Lalchowk vs Ganderbal) never wrongly merge —
     avoiding the single-linkage chaining that a symmetric overlap would cause.

Outputs (gitignored): data/corridors.geojson · data/terminals.geojson ·
data/run_corridor.csv · data/corridors.png

Run:  & "D:\\plotting\\ana\\python.exe" src\\corridors.py
"""
import os, json, math
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.neighbors import BallTree
from common import DATA, hav_m

TERMINAL_EPS_M = 300
TERMINAL_MIN_ENDPTS = 3
TERMINAL_MIN_DRIVERS = 3     # a terminal must be used by >=3 distinct drivers
SNAP_M = 700                 # snap a stray endpoint to a robust terminal within this
MIN_RUNS = 3
CONTAIN_FRAC = 0.70          # short corridor >=70% inside long => merge
CONTAIN_M = 60.0
LAT0 = 34.0
_KX = math.cos(math.radians(LAT0)) * 111320.0
_KY = 111320.0


def to_m(la, lo):
    return (lo * _KX, la * _KY)


def contains(short_geom, long_geom):
    """Fraction of short's points within CONTAIN_M of long's polyline (meters)."""
    from shapely.geometry import LineString, Point
    line = LineString([to_m(la, lo) for la, lo in long_geom])
    pts = short_geom[:: max(1, len(short_geom) // 40)]
    if not pts:
        return 0.0
    return sum(1 for la, lo in pts if line.distance(Point(to_m(la, lo))) <= CONTAIN_M) / len(pts)


def main():
    mm = pd.read_pickle(os.path.join(DATA, "runs_matched.pkl.gz"), compression="gzip")
    runs = mm[(mm.matched == True) & (mm.clean == True)].reset_index(drop=True)
    n = len(runs)
    print(f"Clustering {n:,} clean runs into corridors ...")

    starts = runs[["start_lat", "start_lon"]].to_numpy()
    ends = runs[["end_lat", "end_lon"]].to_numpy()
    allpts = np.vstack([starts, ends])
    ep_driver = np.concatenate([runs.driver.to_numpy(), runs.driver.to_numpy()])

    labels = DBSCAN(eps=TERMINAL_EPS_M / 6371000.0, min_samples=TERMINAL_MIN_ENDPTS,
                    metric="haversine", algorithm="ball_tree").fit(np.radians(allpts)).labels_

    # robust terminals: >=3 distinct drivers
    term_drivers = defaultdict(set)
    for lab, drv in zip(labels, ep_driver):
        if lab >= 0:
            term_drivers[lab].add(drv)
    robust = sorted([t for t, ds in term_drivers.items() if len(ds) >= TERMINAL_MIN_DRIVERS])
    rob_index = {t: i for i, t in enumerate(robust)}
    cent = np.array([allpts[labels == t].mean(axis=0) for t in robust])
    tree = BallTree(np.radians(cent), metric="haversine")
    print(f"  {len(set(labels) - {-1})} raw terminals -> {len(robust)} robust (>= {TERMINAL_MIN_DRIVERS} drivers)")

    def terminal(k, latlon):
        lab = labels[k]
        if lab in rob_index:
            return rob_index[lab]
        d, i = tree.query(np.radians([latlon]), k=1)
        return int(i[0][0]) if d[0][0] * 6371000.0 <= SNAP_M else None

    groups = defaultdict(list)
    for i in range(n):
        ts = terminal(i, starts[i]); te = terminal(i + n, ends[i])
        if ts is None or te is None or ts == te:
            continue
        groups[frozenset((ts, te))].append(i)

    # preliminary corridors
    prelim = []
    for key, members in groups.items():
        if len(members) < MIN_RUNS:
            continue
        sub = runs.iloc[members]
        med_km = float(sub.matched_km.median())
        rep = sub.iloc[(sub.matched_km - med_km).abs().values.argmin()]
        prelim.append(dict(key=key, members=members, km=med_km, geom=rep["geom"], n=len(members)))
    print(f"  {len(prelim)} preliminary corridors")

    # containment merge: short -> longest container sharing a terminal
    order = sorted(range(len(prelim)), key=lambda i: (-prelim[i]["km"], -prelim[i]["n"]))
    rank = {idx: r for r, idx in enumerate(order)}   # smaller rank = longer
    parent = list(range(len(prelim)))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x

    merged = 0
    for x in order[::-1]:                              # shortest first
        best = None
        for y in range(len(prelim)):
            if y == x or rank[y] >= rank[x]:
                continue                                # y must be longer
            if not (prelim[x]["key"] & prelim[y]["key"]):
                continue                                # must share a terminal
            if contains(prelim[x]["geom"], prelim[y]["geom"]) >= CONTAIN_FRAC:
                if best is None or rank[y] < rank[best]:
                    best = y
        if best is not None:
            parent[x] = root(best); merged += 1
    print(f"  merged {merged} short corridors into longer containers")

    final = defaultdict(list)
    for i, p in enumerate(prelim):
        final[root(i)].extend(p["members"])

    corridors = []
    for base, members in final.items():
        sub = runs.iloc[members]
        dates = {datetime.fromtimestamp(t / 1000, timezone.utc).date() for t in sub.start_ts}
        hours = [datetime.fromtimestamp(t / 1000, timezone.utc).hour for t in sub.start_ts]
        n_days = max(1, len(dates)); rpd = len(sub) / n_days
        span_h = (max(hours) - min(hours)) or 1
        med_km = float(sub.matched_km.median())
        rep = sub.iloc[(sub.matched_km - med_km).abs().values.argmin()]
        corridors.append(dict(
            n_runs=len(sub), n_drivers=int(sub.driver.nunique()), n_days=n_days,
            runs_per_day=round(rpd, 1), implied_headway_min=round(span_h * 60 / rpd, 0) if rpd else None,
            median_km=round(med_km, 1), median_min=round(float(sub.dur_min.median()), 0),
            median_kmh=round(float(sub.real_kmh.median()), 1), geom=rep["geom"], members=list(sub.run_id)))
    corridors.sort(key=lambda c: c["n_runs"], reverse=True)
    for i, c in enumerate(corridors, 1):
        c["corridor_id"] = i
    print(f"  {len(corridors)} final corridors (>= {MIN_RUNS} runs), {sum(c['n_runs'] for c in corridors)} runs covered")

    import csv as _csv
    with open(os.path.join(DATA, "run_corridor.csv"), "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f); w.writerow(["run_id", "corridor_id"])
        for c in corridors:
            for rid in c["members"]:
                w.writerow([rid, c["corridor_id"]])

    with open(os.path.join(DATA, "corridors.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature",
             "properties": {k: c[k] for k in ("corridor_id", "n_runs", "n_drivers", "n_days",
                                              "runs_per_day", "implied_headway_min", "median_km",
                                              "median_min", "median_kmh")},
             "geometry": {"type": "LineString", "coordinates": [[lo, la] for la, lo in c["geom"]]}}
            for c in corridors]}, f)
    with open(os.path.join(DATA, "terminals.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"terminal": int(t), "drivers": len(term_drivers[t])},
             "geometry": {"type": "Point", "coordinates": [float(cent[i][1]), float(cent[i][0])]}}
            for i, t in enumerate(robust)]}, f)

    print("\nTop corridors (runs · drivers · days · km · min):")
    for c in corridors[:10]:
        print(f"  C{c['corridor_id']:<3} {c['n_runs']:>4} runs · {c['n_drivers']:>2}drv · "
              f"{c['n_days']:>3}days · {c['median_km']:>5}km · {c['median_min']:>4}min")

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 9))
        mx = max(c["n_runs"] for c in corridors)
        for c in corridors:
            g = np.array(c["geom"])
            ax.plot(g[:, 1], g[:, 0], "-", color="#0f6e56", lw=0.5 + 4.0 * c["n_runs"] / mx, alpha=0.45)
        ax.scatter(cent[:, 1], cent[:, 0], s=10, color="#B0432F", alpha=0.6, zorder=5)
        ax.set_title(f"Observed corridors ({len(corridors)}) + robust terminals ({len(robust)})\nwidth = runs driven", weight="bold")
        ax.set_aspect("equal", "datalim"); ax.set_xticks([]); ax.set_yticks([])
        fig.tight_layout(); fig.savefig(os.path.join(DATA, "corridors.png"), dpi=140, bbox_inches="tight"); plt.close(fig)
    except Exception as e:
        print("(png skipped:", str(e)[:40], ")")

    print("\nWrote data/corridors.geojson, data/terminals.geojson, data/run_corridor.csv, data/corridors.png")


if __name__ == "__main__":
    main()

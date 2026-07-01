#!/usr/bin/env python
"""
Cluster clean map-matched runs into observed CORRIDORS + their frequency.

A corridor = origin terminal <-> destination terminal (undirected). Terminals
are found by DBSCAN over all run endpoints, so nearby start/end points merge
into one terminal (no grid-boundary fragmentation) and distinct routes that only
share a trunk are NOT chained together (the failure of path-overlap linkage).

Per corridor we report how often buses actually run it: runs, drivers, active
days, runs/day, daily service window and a rough implied headway.

Outputs (gitignored):
  data/corridors.geojson  — representative geometry + frequency per corridor
  data/terminals.geojson  — the discovered terminals
  data/corridors.png      — observed network, line width = runs

Run:  & "D:\\plotting\\ana\\python.exe" src\\corridors.py
"""
import os, json
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.neighbors import BallTree
from common import DATA

TERMINAL_EPS_M = 300     # endpoints within this merge into one terminal
TERMINAL_MIN = 3         # endpoints to form a terminal
SNAP_M = 500             # attach a stray endpoint to a terminal within this range
MIN_RUNS = 3             # a corridor must be seen this many times


def main():
    mm = pd.read_pickle(os.path.join(DATA, "runs_matched.pkl.gz"), compression="gzip")
    runs = mm[(mm.matched == True) & (mm.clean == True)].reset_index(drop=True)
    n = len(runs)
    print(f"Clustering {n:,} clean runs into corridors ...")

    starts = runs[["start_lat", "start_lon"]].to_numpy()
    ends = runs[["end_lat", "end_lon"]].to_numpy()
    allpts = np.vstack([starts, ends])

    db = DBSCAN(eps=TERMINAL_EPS_M / 6371000.0, min_samples=TERMINAL_MIN,
                metric="haversine", algorithm="ball_tree").fit(np.radians(allpts))
    labels = db.labels_
    term_ids = sorted(set(labels) - {-1})
    cent = np.array([allpts[labels == t].mean(axis=0) for t in term_ids])
    tree = BallTree(np.radians(cent), metric="haversine")
    print(f"  {len(term_ids)} terminals discovered")

    def terminal(k, latlon):
        if labels[k] != -1:
            return int(labels[k])
        d, i = tree.query(np.radians([latlon]), k=1)
        return int(i[0][0]) if d[0][0] * 6371000.0 <= SNAP_M else None

    groups = defaultdict(list)
    for i in range(n):
        ts = terminal(i, starts[i]); te = terminal(i + n, ends[i])
        if ts is None or te is None or ts == te:
            continue
        groups[frozenset((ts, te))].append(i)

    corridors = []
    for key, members in groups.items():
        if len(members) < MIN_RUNS:
            continue
        sub = runs.iloc[members]
        dates = {datetime.fromtimestamp(t / 1000, timezone.utc).date() for t in sub.start_ts}
        hours = [datetime.fromtimestamp(t / 1000, timezone.utc).hour for t in sub.start_ts]
        n_days = max(1, len(dates))
        rpd = len(sub) / n_days
        span_h = (max(hours) - min(hours)) or 1
        med_km = float(sub.matched_km.median())
        rep = sub.iloc[(sub.matched_km - med_km).abs().values.argmin()]
        a, b = tuple(key)
        corridors.append(dict(
            n_runs=len(sub), n_drivers=int(sub.driver.nunique()), n_days=n_days,
            runs_per_day=round(rpd, 1), implied_headway_min=round(span_h * 60 / rpd, 0) if rpd else None,
            median_km=round(med_km, 1), median_min=round(float(sub.dur_min.median()), 0),
            median_kmh=round(float(sub.real_kmh.median()), 1),
            term_a=[round(float(cent[a][0]), 5), round(float(cent[a][1]), 5)],
            term_b=[round(float(cent[b][0]), 5), round(float(cent[b][1]), 5)],
            geom=rep["geom"], members=list(sub.run_id),
        ))

    corridors.sort(key=lambda c: c["n_runs"], reverse=True)
    for i, c in enumerate(corridors, 1):
        c["corridor_id"] = i

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
            {"type": "Feature", "properties": {"terminal": int(t)},
             "geometry": {"type": "Point", "coordinates": [float(cent[i][1]), float(cent[i][0])]}}
            for i, t in enumerate(term_ids)]}, f)

    covered = sum(c["n_runs"] for c in corridors)
    print(f"\n── Observed corridors ──────────────────────────────")
    print(f"Corridors (>= {MIN_RUNS} runs):  {len(corridors):,}")
    print(f"Runs covered:            {covered:,} / {n:,} clean runs")
    print(f"\nTop corridors (runs · drivers · days · km · ~headway):")
    for c in corridors[:12]:
        print(f"  C{c['corridor_id']:<3} {c['n_runs']:>4} runs · {c['n_drivers']:>2}drv · "
              f"{c['n_days']:>3}days · {c['median_km']:>5}km · {c['median_min']:>4}min · ~{c['implied_headway_min']}min head")

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 9))
        mx = max(c["n_runs"] for c in corridors)
        for c in corridors:
            g = np.array(c["geom"])
            ax.plot(g[:, 1], g[:, 0], "-", color="#0f6e56", lw=0.5 + 4.0 * c["n_runs"] / mx, alpha=0.45)
        ax.scatter(cent[:, 1], cent[:, 0], s=10, color="#B0432F", alpha=0.6, zorder=5)
        ax.set_title(f"Observed corridors ({len(corridors)}) + terminals ({len(term_ids)})\nwidth = runs driven",
                     weight="bold")
        ax.set_aspect("equal", "datalim"); ax.set_xticks([]); ax.set_yticks([])
        fig.tight_layout(); fig.savefig(os.path.join(DATA, "corridors.png"), dpi=140, bbox_inches="tight"); plt.close(fig)
    except Exception as e:
        print("(png skipped:", str(e)[:40], ")")

    print("\nWrote data/corridors.geojson, data/terminals.geojson, data/corridors.png")


if __name__ == "__main__":
    main()

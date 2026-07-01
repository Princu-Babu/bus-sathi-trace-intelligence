#!/usr/bin/env python
"""
Characterise the LONG TAIL — the clean runs NOT captured by the 25 corridors.

The corridor findings describe the frequently-driven core (~41% of clean runs).
This stage answers "what is the other ~59%?" WITHOUT any AI spend:

  A. same terminal-pair grouping as corridors.py, but NO support gate — bucket
     every uncovered run into: near-miss pair (2+ runs, just under the corridor
     gate), one-off OD pair, unassignable endpoint (off any robust terminal),
     or same-terminal loop;
  B. geography: how much of the tail is outside the 10-district study area
     (NH-44 / Jammu division);
  C. write near-miss pairs (>=2 runs) to data/longtail_pairs.csv — a compact
     table a single batched (cheap-model) prompt can label later if wanted.

No new claims are published from this — it only quantifies the coverage caveat.

Run:  & "D:\\plotting\\ana\\python.exe" src\\longtail.py
"""
import os, json, math, csv
from collections import defaultdict
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.neighbors import BallTree
from common import DATA, hav_m

# identical clustering params to corridors.py (must stay in sync)
TERMINAL_EPS_M = 300
TERMINAL_MIN_ENDPTS = 3
TERMINAL_MIN_DRIVERS = 3
SNAP_M = 700

KASH = os.environ.get("KASH_ENGINE", "E:/kash")


def load_study_union():
    from shapely.geometry import shape
    from shapely.ops import unary_union
    with open(os.path.join(KASH, "kashmir_districts_osm.geojson"), encoding="utf-8") as f:
        gj = json.load(f)
    return unary_union([shape(ft["geometry"]) for ft in gj["features"]])


def main():
    from shapely.geometry import Point
    mm = pd.read_pickle(os.path.join(DATA, "runs_matched.pkl.gz"), compression="gzip")
    runs = mm[(mm.matched == True) & (mm.clean == True)].reset_index(drop=True)
    covered = set(pd.read_csv(os.path.join(DATA, "run_corridor.csv")).run_id)
    n = len(runs)
    tail = runs[~runs.run_id.isin(covered)].reset_index(drop=True)
    print(f"Clean runs {n:,} | in corridors {len(covered):,} ({len(covered)/n:.0%}) | tail {len(tail):,} ({len(tail)/n:.0%})")

    # --- rebuild the SAME robust terminals as corridors.py (all clean runs) ---
    starts = runs[["start_lat", "start_lon"]].to_numpy()
    ends = runs[["end_lat", "end_lon"]].to_numpy()
    allpts = np.vstack([starts, ends])
    ep_driver = np.concatenate([runs.driver.to_numpy(), runs.driver.to_numpy()])
    labels = DBSCAN(eps=TERMINAL_EPS_M / 6371000.0, min_samples=TERMINAL_MIN_ENDPTS,
                    metric="haversine", algorithm="ball_tree").fit(np.radians(allpts)).labels_
    term_drivers = defaultdict(set)
    for lab, drv in zip(labels, ep_driver):
        if lab >= 0:
            term_drivers[lab].add(drv)
    robust = sorted([t for t, ds in term_drivers.items() if len(ds) >= TERMINAL_MIN_DRIVERS])
    rob_index = {t: i for i, t in enumerate(robust)}
    cent = np.array([allpts[labels == t].mean(axis=0) for t in robust])
    tree = BallTree(np.radians(cent), metric="haversine")
    lab_of = {rid: k for k, rid in enumerate(runs.run_id)}

    def terminal(k, latlon):
        lab = labels[k]
        if lab in rob_index:
            return rob_index[lab]
        d, i = tree.query(np.radians([latlon]), k=1)
        return int(i[0][0]) if d[0][0] * 6371000.0 <= SNAP_M else None

    # --- bucket every tail run ---
    study = load_study_union()
    pairs = defaultdict(list)
    buckets = dict(near_miss=0, one_off=0, no_terminal=0, same_terminal=0)
    out_of_area = 0
    for _, r in tail.iterrows():
        k = lab_of[r.run_id]
        ts = terminal(k, starts[k]); te = terminal(k + n, ends[k])
        mid = r["geom"][len(r["geom"]) // 2]
        in_area = study.contains(Point(mid[1], mid[0]))
        if not in_area:
            out_of_area += 1
        if ts is None or te is None:
            buckets["no_terminal"] += 1
        elif ts == te:
            buckets["same_terminal"] += 1
        else:
            pairs[frozenset((ts, te))].append((r, in_area))

    near_rows = []
    for key, members in pairs.items():
        if len(members) >= 2:
            buckets["near_miss"] += len(members)
            sub = pd.DataFrame([m[0] for m in members])
            a, b = sorted(key)
            near_rows.append(dict(
                term_a=a, term_a_lat=round(float(cent[a][0]), 5), term_a_lon=round(float(cent[a][1]), 5),
                term_b=b, term_b_lat=round(float(cent[b][0]), 5), term_b_lon=round(float(cent[b][1]), 5),
                n_runs=len(members), n_drivers=int(sub.driver.nunique()),
                median_km=round(float(sub.matched_km.median()), 1),
                median_min=round(float(sub.dur_min.median()), 0),
                in_area_frac=round(sum(1 for m in members if m[1]) / len(members), 2)))
        else:
            buckets["one_off"] += 1
    near_rows.sort(key=lambda x: -x["n_runs"])

    with open(os.path.join(DATA, "longtail_pairs.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(near_rows[0].keys()) if near_rows else ["n_runs"])
        w.writeheader(); w.writerows(near_rows)

    t = len(tail)
    print("\n── The long tail, decomposed ───────────────────────")
    print(f"Near-miss pairs (2+ runs, under corridor gate): {buckets['near_miss']:>5} runs "
          f"({buckets['near_miss']/t:.0%}) across {len(near_rows)} OD pairs")
    print(f"One-off OD pairs (1 run):                       {buckets['one_off']:>5} runs ({buckets['one_off']/t:.0%})")
    print(f"Endpoint off any robust terminal:               {buckets['no_terminal']:>5} runs ({buckets['no_terminal']/t:.0%})")
    print(f"Same-terminal loops:                            {buckets['same_terminal']:>5} runs ({buckets['same_terminal']/t:.0%})")
    print(f"Outside 10-district study area (by midpoint):   {out_of_area:>5} runs ({out_of_area/t:.0%})")
    if near_rows:
        multi_drv = [p for p in near_rows if p["n_drivers"] >= 2]
        print(f"\nNear-miss pairs with >=2 DRIVERS (the only ones worth a look): {len(multi_drv)}")
        for p in multi_drv[:15]:
            print(f"  T{p['term_a']}<->T{p['term_b']}: {p['n_runs']} runs · {p['n_drivers']}drv · "
                  f"{p['median_km']}km · in-area {p['in_area_frac']}")
    print("\nWrote data/longtail_pairs.csv")


if __name__ == "__main__":
    main()

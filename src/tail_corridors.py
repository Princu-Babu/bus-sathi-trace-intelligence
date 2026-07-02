#!/usr/bin/env python
"""
Mine the long tail for two things WITHOUT touching the published 18 corridors:

  A. EVIDENCE BOOST — tail runs that geometrically overlap an EXISTING corridor's
     path (they just didn't cluster into its robust terminal, e.g. a slightly
     different pickup point) get attributed to it. This only adds n_runs/
     n_drivers support to corridors already verified; it never changes a verdict.

  B. NEW CANDIDATES — of the runs left over after (A), cluster by PATH SHAPE
     (150 m grid-cell Jaccard overlap) using complete-linkage hierarchical
     clustering with a hard distance cutoff — every member must be similar to
     EVERY other member, which is what stops the old single-linkage "blob" bug
     (one weak link chaining unrelated routes together). Same support gate as
     the original corridor discovery (>=5 runs, >=2 distinct drivers).

Output is explicitly labelled TIER 2 / exploratory — lower confidence than the
terminal-robust Tier 1 corridors, because path-shape alone (no shared terminal)
is a weaker signal. These are candidates for a follow-up AI-analyst pass, not
verified findings.

Outputs: data/tail_corridor_boost.csv (existing-corridor evidence additions)
         data/tail_candidates.geojson (new Tier-2 candidate corridors)
         TAIL_MINING_REPORT.md

Run:  & "D:\\plotting\\ana\\python.exe" src\\tail_corridors.py
"""
import os, sys, json, math
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from common import DATA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CELL_M = 150.0
LAT0 = 34.0
KX = math.cos(math.radians(LAT0)) * 111320.0
KY = 111320.0

BOOST_JACCARD = 0.55     # tail run counts as "on" an existing corridor above this
CLUSTER_JACCARD = 0.45   # complete-linkage cutoff for a new Tier-2 cluster
MIN_RUNS = 5
MIN_DRIVERS = 2


def cellset(geom):
    return {(round(lo * KX / CELL_M), round(la * KY / CELL_M)) for la, lo in geom}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def main():
    mm = pd.read_pickle(os.path.join(DATA, "runs_matched.pkl.gz"), compression="gzip")
    runs = mm[(mm.matched == True) & (mm.clean == True)].reset_index(drop=True)
    covered = set(pd.read_csv(os.path.join(DATA, "run_corridor.csv")).run_id)
    tail = runs[~runs.run_id.isin(covered)].reset_index(drop=True)
    tail_sig = [cellset(g) for g in tail["geom"]]
    print(f"Tail runs: {len(tail)}")

    with open(os.path.join(ROOT, "analyst", "corridors_verdicts.geojson"), encoding="utf-8") as f:
        pub = json.load(f)
    pub_sig = {}
    for ft in pub["features"]:
        coords = ft["geometry"]["coordinates"]  # [lon, lat]
        pub_sig[ft["properties"]["corridor_id"]] = cellset([(la, lo) for lo, la in coords])
    print(f"Published corridors: {len(pub_sig)}")

    # ── A. evidence boost against published corridors ──────────────────
    boost_rows = []
    boosted_idx = set()
    for i, sig in enumerate(tail_sig):
        best_cid, best_j = None, 0.0
        for cid, psig in pub_sig.items():
            j = jaccard(sig, psig)
            if j > best_j:
                best_j, best_cid = j, cid
        if best_j >= BOOST_JACCARD:
            r = tail.iloc[i]
            boost_rows.append(dict(run_id=r.run_id, corridor_id=best_cid, jaccard=round(best_j, 2),
                                   driver=r.driver, km=round(float(r.matched_km), 1)))
            boosted_idx.add(i)
    boost_df = pd.DataFrame(boost_rows)
    boost_df.to_csv(os.path.join(DATA, "tail_corridor_boost.csv"), index=False)
    boost_by_corridor = (boost_df.groupby("corridor_id").agg(
        add_runs=("run_id", "count"), add_drivers=("driver", "nunique")).reset_index()
        if not boost_df.empty else pd.DataFrame(columns=["corridor_id", "add_runs", "add_drivers"]))
    print(f"A. Evidence boost: {len(boost_df)} tail runs attributed to {boost_df.corridor_id.nunique() if not boost_df.empty else 0} existing corridors")

    # ── B. new Tier-2 candidates among the rest ─────────────────────────
    rest_idx = [i for i in range(len(tail)) if i not in boosted_idx]
    rest = tail.iloc[rest_idx].reset_index(drop=True)
    rest_sig = [tail_sig[i] for i in rest_idx]
    n = len(rest)
    print(f"B. Remaining un-attributed tail runs for clustering: {n}")

    # pairwise Jaccard distance (n is a few hundred to ~1000 -> dense matrix OK)
    D = np.ones((n, n))
    for i in range(n):
        D[i, i] = 0.0
        si = rest_sig[i]
        if len(si) < 5:
            continue
        for j in range(i + 1, n):
            sj = rest_sig[j]
            if len(sj) < 5:
                continue
            jac = jaccard(si, sj)
            d = 1.0 - jac
            D[i, j] = D[j, i] = d

    condensed = squareform(D, checks=False)
    Z = linkage(condensed, method="complete")
    labels = fcluster(Z, t=1.0 - CLUSTER_JACCARD, criterion="distance")

    groups = {}
    for i, lab in enumerate(labels):
        groups.setdefault(lab, []).append(i)

    candidates = []
    for lab, members in groups.items():
        if len(members) < MIN_RUNS:
            continue
        sub = rest.iloc[members]
        if sub.driver.nunique() < MIN_DRIVERS:
            continue
        med_km = float(sub.matched_km.median())
        rep = sub.iloc[(sub.matched_km - med_km).abs().values.argmin()]
        candidates.append(dict(n_runs=len(sub), n_drivers=int(sub.driver.nunique()),
                               median_km=round(med_km, 1), median_min=round(float(sub.dur_min.median()), 0),
                               geom=rep["geom"], members=list(sub.run_id)))
    candidates.sort(key=lambda c: c["n_runs"], reverse=True)
    for i, c in enumerate(candidates, 1):
        c["tail_id"] = i
    print(f"B. New Tier-2 candidate corridors (>= {MIN_RUNS} runs, >= {MIN_DRIVERS} drivers): {len(candidates)}, "
          f"{sum(c['n_runs'] for c in candidates)} runs")

    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {"tail_id": c["tail_id"], "n_runs": c["n_runs"], "n_drivers": c["n_drivers"],
                        "median_km": c["median_km"], "median_min": c["median_min"], "tier": 2},
         "geometry": {"type": "LineString", "coordinates": [[lo, la] for la, lo in c["geom"]]}}
        for c in candidates]}
    with open(os.path.join(DATA, "tail_candidates.geojson"), "w", encoding="utf-8") as f:
        json.dump(gj, f)

    # ── report ──────────────────────────────────────────────────────────
    L = ["# Tail mining report — long-tail second pass",
         "", f"_Tail pool: {len(tail)} clean runs not in the 25 published corridors._", "",
         "## A. Evidence boost to PUBLISHED corridors (no verdicts changed)",
         f"{len(boost_df)} tail runs geometrically overlap (Jaccard >= {BOOST_JACCARD}) a published corridor's path "
         "but had endpoints that didn't cluster into its robust terminal — likely a slightly different pickup/drop "
         "point on the same real route. These strengthen existing evidence only.", ""]
    if not boost_by_corridor.empty:
        L.append("| Corridor | + runs | + distinct drivers |")
        L.append("|---|---|---|")
        for _, r in boost_by_corridor.sort_values("add_runs", ascending=False).iterrows():
            L.append(f"| C{int(r.corridor_id)} | +{int(r.add_runs)} | +{int(r.add_drivers)} |")
    L += ["", "## B. NEW Tier-2 candidate corridors (exploratory — lower confidence)",
          f"Path-shape clustering (complete-linkage, Jaccard >= {CLUSTER_JACCARD}, every member similar to every "
          "other member) over the runs A didn't claim. No shared robust terminal required, so these are weaker "
          "evidence than the Tier-1 set and need individual review before being called real corridors.", ""]
    if candidates:
        L.append("| Tail ID | Runs | Drivers | Median km | Median min |")
        L.append("|---|---|---|---|---|")
        for c in candidates:
            L.append(f"| T{c['tail_id']} | {c['n_runs']} | {c['n_drivers']} | {c['median_km']} | {c['median_min']} |")
    else:
        L.append("_None cleared the support gate._")
    L += ["", "## What's still genuinely unusable",
          f"{len(rest) - sum(c['n_runs'] for c in candidates)} runs remain either singletons or below the support "
          "gate even by path shape — one-off routes with too little repetition to say anything about, same "
          "conclusion as the first long-tail pass (`longtail.py`).", ""]
    text = "\n".join(L)
    open(os.path.join(ROOT, "TAIL_MINING_REPORT.md"), "w", encoding="utf-8").write(text)
    print("\n" + text)
    print("\nWrote data/tail_corridor_boost.csv, data/tail_candidates.geojson, TAIL_MINING_REPORT.md")


if __name__ == "__main__":
    main()

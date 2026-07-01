#!/usr/bin/env python
"""
Sessionise raw app sessions into real service RUNS.

A Firestore "trip" is a driver SESSION (app left running in the background): it
can bundle several real runs plus long idle and wandering. This stage:

  1. detects dwells (stay-points) via a radius/duration scan;
  2. splits a session into runs at TERMINAL dwells (>=12 min) and time GAPS
     (>=8 min, app backgrounded);
  3. trims stationary heads/tails so timings are realistic;
  4. drops wandering (low straightness) and too-short fragments;
  5. records short dwells (40 s .. 12 min) as candidate service STOPS.

Realistic timing = wall time of the *trimmed* run (short service stops kept,
long idle excluded), not the raw session duration.

Outputs (gitignored):
  data/runs.pkl.gz         — one row per run (+ polyline)
  data/stop_events.pkl.gz  — one row per observed service-stop dwell
  data/session_split.png   — a sample session decomposed into runs

Run:  & "D:\\plotting\\ana\\python.exe" src\\segment.py
"""
import os
import numpy as np
import pandas as pd
from common import DATA, hav_m

STOP_RADIUS_M = 40      # dwell = staying within this radius
SERVICE_MIN_S = 40      # >=40 s dwell -> candidate service stop
TERMINAL_S = 12 * 60    # >=12 min dwell -> terminal/idle -> SPLIT
GAP_S = 8 * 60          # >=8 min gap between samples -> SPLIT (backgrounded)
MIN_RUN_KM = 1.0
MIN_RUN_PTS = 20
MIN_RUN_MIN = 4.0
STRAIGHTNESS_MIN = 0.15  # net_disp / path below this (and short) => wandering
TRIM_M = 50              # trim stationary head/tail within this radius


def dwells(lat, lon, ts):
    """Radius/duration stay-point scan. Returns list of (i, j, clat, clon, dur_s)."""
    n = len(lat); out = []; i = 0
    while i < n - 1:
        j = i + 1
        while j < n and hav_m(lat[i], lon[i], lat[j], lon[j]) <= STOP_RADIUS_M:
            j += 1
        dur = (ts[j - 1] - ts[i]) / 1000.0
        if j - 1 > i and dur >= SERVICE_MIN_S:
            out.append((i, j - 1, float(lat[i:j].mean()), float(lon[i:j].mean()), dur))
            i = j
        else:
            i += 1
    return out


def path_km(lat, lon):
    if len(lat) < 2:
        return 0.0
    return float(sum(hav_m(lat[k - 1], lon[k - 1], lat[k], lon[k]) for k in range(1, len(lat))) / 1000.0)


def trim(idx, lat, lon):
    """Drop stationary head/tail (within TRIM_M of the endpoint)."""
    a, b = 0, len(idx) - 1
    while a < b and hav_m(lat[idx[a]], lon[idx[a]], lat[idx[a + 1]], lon[idx[a + 1]]) < 5 and \
            hav_m(lat[idx[0]], lon[idx[0]], lat[idx[a + 1]], lon[idx[a + 1]]) < TRIM_M:
        a += 1
    while b > a and hav_m(lat[idx[b]], lon[idx[b]], lat[idx[b - 1]], lon[idx[b - 1]]) < 5 and \
            hav_m(lat[idx[-1]], lon[idx[-1]], lat[idx[b - 1]], lon[idx[b - 1]]) < TRIM_M:
        b -= 1
    return idx[a:b + 1]


def segment_session(g):
    """g: DataFrame for one trip, sorted by ts. Returns (runs, stop_events, idle_s)."""
    g = g[g["ts"].notna()].sort_values("ts")
    lat = g["lat"].to_numpy(); lon = g["lon"].to_numpy(); ts = g["ts"].to_numpy()
    n = len(lat)
    if n < MIN_RUN_PTS:
        return [], [], 0.0

    dw = dwells(lat, lon, ts)
    idle = np.zeros(n, dtype=bool)
    terminals = []
    service = []
    for (i, j, clat, clon, dur) in dw:
        if dur >= TERMINAL_S:
            idle[i:j + 1] = True
            terminals.append(dur)
        elif dur >= SERVICE_MIN_S:
            service.append((i, j, clat, clon, dur))

    # cut indices where there is a big time gap
    gap_after = np.zeros(n, dtype=bool)
    gap_idle = 0.0
    for k in range(1, n):
        dt = (ts[k] - ts[k - 1]) / 1000.0
        if dt >= GAP_S:
            gap_after[k - 1] = True
            gap_idle += dt

    # build runs = maximal spans of non-idle indices not crossing a gap
    runs, stop_events = [], []
    k = 0
    while k < n:
        if idle[k]:
            k += 1; continue
        a = k
        while k + 1 < n and not idle[k + 1] and not gap_after[k]:
            k += 1
        b = k  # span [a, b]
        k += 1
        idx = list(range(a, b + 1))
        if len(idx) < MIN_RUN_PTS:
            continue
        idx = trim(idx, lat, lon)
        if len(idx) < MIN_RUN_PTS:
            continue
        rlat = lat[idx]; rlon = lon[idx]; rts = ts[idx]
        km = path_km(rlat, rlon)
        net = hav_m(rlat[0], rlon[0], rlat[-1], rlon[-1]) / 1000.0
        dur_min = (rts[-1] - rts[0]) / 60000.0
        if km < MIN_RUN_KM or dur_min < MIN_RUN_MIN:
            continue
        straight = net / km if km else 0
        if straight < STRAIGHTNESS_MIN and km < 3:   # wandering/idle loops
            continue
        spd = km / (dur_min / 60.0) if dur_min else 0
        my_stops = [(clat, clon, dur) for (si, sj, clat, clon, dur) in service if a <= si <= b]
        run_id = f"{g['trip_id'].iloc[0]}_{a}"
        runs.append(dict(run_id=run_id, trip_id=g["trip_id"].iloc[0], driver=g["driver"].iloc[0],
                         start_ts=int(rts[0]), end_ts=int(rts[-1]), dur_min=round(dur_min, 1),
                         raw_km=round(km, 2), net_km=round(net, 2), straightness=round(straight, 2),
                         avg_kmh=round(spd, 1), n_pts=len(idx), n_stops=len(my_stops),
                         start_lat=float(rlat[0]), start_lon=float(rlon[0]),
                         end_lat=float(rlat[-1]), end_lon=float(rlon[-1]),
                         poly=list(zip(rlat.tolist(), rlon.tolist()))))
        for (clat, clon, dur) in my_stops:
            stop_events.append(dict(run_id=run_id, driver=g["driver"].iloc[0],
                                    lat=clat, lon=clon, dwell_s=round(dur, 0)))
    idle_s = sum(terminals) + gap_idle
    return runs, stop_events, idle_s


def render_sample(runs_df, pts, path):
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    except Exception:
        return
    # pick the session that produced the most runs
    top = runs_df.groupby("trip_id").size().sort_values(ascending=False)
    if top.empty:
        return
    tid = top.index[0]
    g = pts[pts["trip_id"] == tid].sort_values("ts")
    sub = runs_df[runs_df["trip_id"] == tid]
    fig, ax = plt.subplots(1, 2, figsize=(11, 5.5))
    ax[0].plot(g["lon"], g["lat"], "-", color="#bbbbbb", lw=0.6)
    ax[0].scatter(g["lon"], g["lat"], s=3, color="#d1495b", alpha=0.5)
    ax[0].set_title(f"Raw session (1 'trip' doc)\n{len(g):,} points", fontsize=10)
    cols = plt.cm.tab10.colors
    for i, (_, r) in enumerate(sub.iterrows()):
        poly = np.array(r["poly"])
        ax[1].plot(poly[:, 1], poly[:, 0], "-", lw=2, color=cols[i % 10],
                   label=f"run {i+1}: {r['raw_km']}km / {r['dur_min']}min")
    ax[1].set_title(f"Split into {len(sub)} real runs (idle trimmed)", fontsize=10)
    ax[1].legend(fontsize=7, loc="best")
    for a in ax:
        a.set_xticks([]); a.set_yticks([]); a.set_aspect("equal", "datalim")
    fig.suptitle("Sessionising: one app session -> multiple trimmed service runs", weight="bold")
    fig.tight_layout(); fig.savefig(path, dpi=140, bbox_inches="tight"); plt.close(fig)


def main():
    pts = pd.read_pickle(os.path.join(DATA, "points.pkl.gz"), compression="gzip")
    print(f"Loaded {len(pts):,} points / {pts.trip_id.nunique():,} sessions")

    all_runs, all_stops = [], []
    total_idle_h = 0.0
    sess_dur, run_dur = [], []
    for tid, g in pts.groupby("trip_id", sort=False):
        r, s, idle_s = segment_session(g)
        all_runs += r; all_stops += s
        total_idle_h += idle_s / 3600.0
        gg = g[g["ts"].notna()]
        if len(gg) >= 2:
            sess_dur.append((gg["ts"].max() - gg["ts"].min()) / 60000.0)
        run_dur += [x["dur_min"] for x in r]

    runs_df = pd.DataFrame(all_runs)
    stops_df = pd.DataFrame(all_stops)
    runs_df.to_pickle(os.path.join(DATA, "runs.pkl.gz"), compression="gzip")
    stops_df.to_pickle(os.path.join(DATA, "stop_events.pkl.gz"), compression="gzip")

    n_sess = pts.trip_id.nunique()
    sess_with_runs = runs_df.trip_id.nunique() if not runs_df.empty else 0
    per_sess = runs_df.groupby("trip_id").size() if not runs_df.empty else pd.Series(dtype=int)
    print("\n── Sessionising impact ─────────────────────────────")
    print(f"Sessions in:                 {n_sess:,}")
    print(f"Service runs out:            {len(runs_df):,}")
    print(f"Sessions yielding >=1 run:   {sess_with_runs:,}")
    print(f"Runs per producing session:  median {int(per_sess.median()) if len(per_sess) else 0} / max {int(per_sess.max()) if len(per_sess) else 0}")
    print(f"Multi-run sessions (>=2):    {(per_sess >= 2).sum() if len(per_sess) else 0}")
    print(f"Idle/gap time trimmed away:  {total_idle_h:,.0f} hours")
    if sess_dur and run_dur:
        print(f"Median session wall time:    {np.median(sess_dur):.0f} min")
        print(f"Median REAL run time:        {np.median(run_dur):.0f} min")
    if not runs_df.empty:
        print(f"Run length km:               median {runs_df.raw_km.median():.1f} / max {runs_df.raw_km.max():.0f}")
        print(f"Run avg speed km/h:          median {runs_df.avg_kmh.median():.1f}")
        print(f"Runs flagged >90 km/h:       {(runs_df.avg_kmh > 90).sum()}")
    print(f"Candidate service-stop dwells: {len(stops_df):,}")

    render_sample(runs_df, pts, os.path.join(DATA, "session_split.png"))
    print("\nWrote data/runs.pkl.gz, data/stop_events.pkl.gz, data/session_split.png")


if __name__ == "__main__":
    main()

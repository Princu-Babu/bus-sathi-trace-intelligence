#!/usr/bin/env python
"""
Measured speed / congestion layer from real bus GPS.

For every CLEAN service run we take consecutive GPS samples, compute probe speed
(distance / time) and attribute it to a ~330 m grid cell. Median speed per cell
over many samples is a robust, adoption-ROBUST measurement (a physical property
of the road at that time, independent of how many drivers use the app).

We then TEST the engine's assumed downtown congestion multiplier
(`CONGESTION_CITY_CORE = 2.2`) against the measured core-vs-periphery speed ratio,
and report an AM/PM-peak vs midday ratio.

Honesty guards:
  - only clean runs; probe pairs filtered to dt 4-30 s, dist >=15 m, speed 1-80 km/h
    (drops GPS jitter and teleports);
  - a cell is reported only with >=40 samples from >=5 distinct runs (else "low support");
  - all claims carry their sample support.

Outputs (gitignored):
  data/speed_cells.geojson  · data/speed_layer.png · data/congestion_report.txt

Run:  & "D:\\plotting\\ana\\python.exe" src\\speed_layer.py
"""
import os, json, math
from collections import defaultdict
import numpy as np
import pandas as pd
from common import DATA, hav_m

CLAT, CLON = 0.003, 0.0036          # ~330 m cells
MIN_SAMPLES, MIN_RUNS = 40, 5        # support gate per cell
DT_LO, DT_HI = 4.0, 30.0             # seconds between usable samples
# MOVING-speed metric: keep congested crawl (>=4 km/h) but exclude stop-dwell GPS
# jitter (a bus paused at a stop must NOT count as "0 km/h road congestion").
# A 15 m floor at 5 s would drop everything below ~11 km/h — i.e. the very crawl
# we want; 6 m keeps down to ~4 km/h.
MIN_STEP_M = 6.0
SPD_LO, SPD_HI = 4.0, 80.0           # km/h: moving traffic, drop stationary + teleports
HUB = (34.0749, 74.8285)             # busiest observed terminal (Srinagar core)
CORE_KM, PERI_LO_KM, PERI_HI_KM = 2.5, 5.0, 15.0
IST = 19800                          # +5:30 in seconds


def ist_hour(ts_ms):
    return int(((ts_ms / 1000 + IST) // 3600) % 24)


def main():
    runs = pd.read_pickle(os.path.join(DATA, "runs.pkl.gz"), compression="gzip")
    matched = pd.read_pickle(os.path.join(DATA, "runs_matched.pkl.gz"), compression="gzip")
    clean_ids = set(matched.loc[matched.clean == True, "run_id"])
    runs = runs[runs.run_id.isin(clean_ids)].copy()
    print(f"Clean runs to profile: {len(runs):,}")

    pts = pd.read_pickle(os.path.join(DATA, "points.pkl.gz"), compression="gzip")
    pts = pts[pts.ts.notna()].sort_values(["trip_id", "ts"])
    by_trip = {tid: (g["ts"].to_numpy(), g["lat"].to_numpy(), g["lon"].to_numpy())
               for tid, g in pts.groupby("trip_id", sort=False)}

    # cell -> speed samples; and per time bucket
    cell_spd = defaultdict(list)
    cell_runs = defaultdict(set)
    cell_peak = defaultdict(list)   # AM(7-10)+PM(16-19)
    cell_mid = defaultdict(list)    # 10-16
    n_pairs = 0

    for _, r in runs.iterrows():
        tid = r.trip_id
        if tid not in by_trip:
            continue
        ts, la, lo = by_trip[tid]
        a = np.searchsorted(ts, r.start_ts, "left")
        b = np.searchsorted(ts, r.end_ts, "right")
        if b - a < 2:
            continue
        for k in range(a + 1, b):
            dt = (ts[k] - ts[k - 1]) / 1000.0
            if not (DT_LO <= dt <= DT_HI):
                continue
            d = hav_m(la[k - 1], lo[k - 1], la[k], lo[k])
            if d < MIN_STEP_M:
                continue
            spd = d / dt * 3.6
            if not (SPD_LO <= spd <= SPD_HI):
                continue
            mla = (la[k - 1] + la[k]) / 2; mlo = (lo[k - 1] + lo[k]) / 2
            cell = (math.floor(mla / CLAT), math.floor(mlo / CLON))
            cell_spd[cell].append(spd)
            cell_runs[cell].add(r.run_id)
            h = ist_hour(ts[k - 1])
            if h in (7, 8, 9, 16, 17, 18):
                cell_peak[cell].append(spd)
            elif 10 <= h < 16:
                cell_mid[cell].append(spd)
            n_pairs += 1

    rows = []
    for cell, spds in cell_spd.items():
        support = len(spds) >= MIN_SAMPLES and len(cell_runs[cell]) >= MIN_RUNS
        clat = (cell[0] + 0.5) * CLAT; clon = (cell[1] + 0.5) * CLON
        rows.append(dict(lat=round(clat, 5), lon=round(clon, 5),
                         median_kmh=round(float(np.median(spds)), 1),
                         samples=len(spds), runs=len(cell_runs[cell]),
                         dist_hub_km=round(hav_m(clat, clon, *HUB) / 1000.0, 2),
                         supported=bool(support)))
    cells = pd.DataFrame(rows)
    sup = cells[cells.supported]
    print(f"Probe pairs used: {n_pairs:,} · cells: {len(cells):,} · supported: {len(sup):,}")

    with open(os.path.join(DATA, "speed_cells.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature",
             "properties": {k: r[k] for k in ("median_kmh", "samples", "runs", "dist_hub_km", "supported")},
             "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]}}
            for _, r in cells.iterrows()]}, f)

    # ── congestion test vs the engine's 2.2x assumption ───────────────────
    core = sup[sup.dist_hub_km <= CORE_KM]
    peri = sup[(sup.dist_hub_km >= PERI_LO_KM) & (sup.dist_hub_km <= PERI_HI_KM)]
    lines = ["MEASURED MOVING-SPEED — core vs periphery (supported cells, >=4 km/h pairs)", ""]
    if len(core) >= 5 and len(peri) >= 5:
        core_v = float(core.median_kmh.median()); peri_v = float(peri.median_kmh.median())
        ratio = peri_v / core_v if core_v else float("nan")
        lines += [f"Core (<= {CORE_KM} km of hub):  {core_v:.1f} km/h  ({len(core)} cells)",
                  f"Periphery ({PERI_LO_KM}-{PERI_HI_KM} km):    {peri_v:.1f} km/h  ({len(peri)} cells)",
                  f"Core is {ratio:.2f}x slower than periphery.",
                  "",
                  "CAREFUL READ: this is a moving-speed ratio — a PROXY for, not a direct",
                  "measure of, the engine's core congestion multiplier (2.2x on travel TIME).",
                  "The definitive recalibration is observed travel time vs OSRM free-flow",
                  "time per corridor — that is the next module, and it is what should",
                  "actually confirm or adjust the 2.2x. Do not conclude from this line alone."]
    else:
        lines.append(f"Insufficient supported cells (core {len(core)}, peri {len(peri)}) — not reported.")
    # peak vs midday, network-wide (supported cells only)
    sup_cells = set(zip((sup.lat / CLAT - 0.5).round().astype(int),
                        (sup.lon / CLON - 0.5).round().astype(int)))
    peak_all = [v for cell, s in cell_peak.items() if cell in sup_cells for v in s]
    mid_all = [v for cell, s in cell_mid.items() if cell in sup_cells for v in s]
    if len(peak_all) >= 500 and len(mid_all) >= 500:
        pv, mv = float(np.median(peak_all)), float(np.median(mid_all))
        if pv:
            lines += ["", f"Peak (AM+PM) {pv:.1f} km/h ({len(peak_all):,} pairs) vs "
                          f"midday {mv:.1f} km/h ({len(mid_all):,} pairs) => "
                          f"{mv/pv:.2f}x slower at peak"]
    txt = "\n".join(lines)
    with open(os.path.join(DATA, "congestion_report.txt"), "w", encoding="utf-8") as f:
        f.write(txt)
    print("\n" + txt)

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 9))
        s = sup
        sc = ax.scatter(s.lon, s.lat, c=s.median_kmh, cmap="RdYlGn", vmin=5, vmax=35,
                        s=14, alpha=0.85, edgecolors="none")
        ax.scatter([HUB[1]], [HUB[0]], marker="*", s=180, color="#1b1b1b", zorder=5, label="core hub")
        plt.colorbar(sc, ax=ax, shrink=0.6, label="median km/h")
        ax.set_title(f"Measured bus speed by cell ({len(s)} supported cells)\nred = slow / congested",
                     weight="bold")
        ax.legend(loc="upper right", fontsize=9)
        ax.set_aspect("equal", "datalim"); ax.set_xticks([]); ax.set_yticks([])
        fig.tight_layout(); fig.savefig(os.path.join(DATA, "speed_layer.png"), dpi=140, bbox_inches="tight"); plt.close(fig)
    except Exception as e:
        print("(png skipped:", str(e)[:60], ")")

    print("\nWrote data/speed_cells.geojson, data/speed_layer.png, data/congestion_report.txt")


if __name__ == "__main__":
    main()

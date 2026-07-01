#!/usr/bin/env python
"""
Measured calibration — ONLY what the data can honestly support.

WHAT WE DELIBERATELY DO NOT DO (and why):
  * No congestion multiplier vs OSRM free-flow. OSRM's default profile is a CAR
    profile; on this data it implies 55 km/h median (up to 137 km/h) "free-flow",
    which no bus achieves. It is not a valid bus baseline, so any observed/free-flow
    "congestion factor" is meaningless. We reject that approach outright.
  * No single recalibrated 2.2x. Congestion, the bus-vs-car speed gap, and
    stop/layover dwell are entangled in probe data; separating them cleanly needs a
    surveyed free-flow bus baseline we don't have.

WHAT WE DO deliver (all directly measured, no modelling):
  * per-corridor MEASURED operating profile: observed one-way time, in-motion time
    (dwell removed), dwell time, moving speed and effective speed;
  * measured bus speeds core vs periphery (cross-checks the speed layer);
  * the honest calibration message for the engine: it sizes cycles on OSRM car
    speeds; real buses run far slower, so those cycle times are optimistic and
    should be calibrated to the MEASURED speed layer, not a single multiplier.

Support-gated to >=5 runs & >=2 drivers.

Outputs (gitignored): data/corridor_profiles.csv · data/calibration.png · data/calibration_report.txt

Run:  & "D:\\plotting\\ana\\python.exe" src\\calibration.py
"""
import os, json
import numpy as np
import pandas as pd
from common import DATA, hav_m

HUB = (34.0749, 74.8285)
CORE_KM, PERI_LO, PERI_HI = 2.5, 5.0, 15.0
MIN_RUNS, MIN_DRIVERS = 5, 2


def main():
    corr = {f["properties"]["corridor_id"]: f
            for f in json.load(open(os.path.join(DATA, "corridors.geojson"), encoding="utf-8"))["features"]}
    match = {f["properties"].get("corridor_id"): f["properties"].get("verdict", "")
             for f in json.load(open(os.path.join(DATA, "corridor_permit_match.geojson"), encoding="utf-8"))["features"]}
    r2c = pd.read_csv(os.path.join(DATA, "run_corridor.csv"))
    runs = pd.read_pickle(os.path.join(DATA, "runs.pkl.gz"), compression="gzip")[["run_id", "driver", "dur_min"]]
    ev = pd.read_pickle(os.path.join(DATA, "stop_events.pkl.gz"), compression="gzip")
    dwell_by_run = ev.groupby("run_id")["dwell_s"].sum().div(60.0)

    runs = runs.merge(r2c, on="run_id", how="inner")
    rows = []
    for cid, g in runs.groupby("corridor_id"):
        if len(g) < MIN_RUNS or g.driver.nunique() < MIN_DRIVERS or cid not in corr:
            continue
        p = corr[cid]["properties"]; km = float(p["median_km"])
        geom = corr[cid]["geometry"]["coordinates"]; mid = geom[len(geom) // 2]
        dh = hav_m(mid[1], mid[0], *HUB) / 1000.0
        zone = "core" if dh <= CORE_KM else ("periphery" if PERI_LO <= dh <= PERI_HI else "mid")
        obs = float(g.dur_min.median())
        dwell = float(dwell_by_run.reindex(g.run_id).fillna(0).median())
        in_motion = max(0.1, obs - dwell)
        rows.append(dict(
            corridor_id=cid, n_runs=int(p["n_runs"]), n_drivers=int(p["n_drivers"]),
            zone=zone, dist_hub_km=round(dh, 2), km=round(km, 1),
            obs_oneway_min=round(obs, 1), dwell_min=round(dwell, 1), in_motion_min=round(in_motion, 1),
            moving_kmh=round(km / (in_motion / 60), 1), effective_kmh=round(km / (obs / 60), 1),
            dwell_share=round(dwell / obs, 2) if obs else 0, verdict=match.get(cid, ""),
        ))
    prof = pd.DataFrame(rows)
    prof.to_csv(os.path.join(DATA, "corridor_profiles.csv"), index=False)

    core = prof[prof.zone == "core"]; peri = prof[prof.zone == "periphery"]
    L = ["MEASURED CORRIDOR PROFILES (no modelling; measured only)", "",
         f"Supported corridors: {len(prof)}  (>= {MIN_RUNS} runs, >= {MIN_DRIVERS} drivers)", "",
         "── Measured bus speed (km/h) ───────────────────────",
         f"  moving (dwell removed):  median {prof.moving_kmh.median():.1f}   (core {core.moving_kmh.median():.1f} vs periphery {peri.moving_kmh.median():.1f})"
         if len(core) and len(peri) else f"  moving median {prof.moving_kmh.median():.1f}",
         f"  effective (incl dwell):  median {prof.effective_kmh.median():.1f}",
         f"  dwell share of run time: median {prof.dwell_share.median():.0%}", "",
         "── Honest calibration signal for the engine ────────",
         "  The engine sizes cycle times on OSRM car speeds. Real buses here move at",
         f"  ~{prof.moving_kmh.median():.0f} km/h (moving) / ~{prof.effective_kmh.median():.0f} km/h (incl stops) — far below car free-flow.",
         "  => engine cycle times are structurally OPTIMISTIC; calibrate them to the",
         "     MEASURED speed layer, per zone, rather than to a single multiplier.",
         "",
         "  We deliberately DO NOT publish a congestion multiplier: OSRM car free-flow",
         "  is not a valid bus baseline, and congestion/bus-speed/dwell are entangled.",
         "",
         "── Note on dwell ───────────────────────────────────",
         f"  median dwell {prof.dwell_min.median():.0f} min/run is high — it also captures",
         "  layovers/standstills, not only boarding stops. Treat 'moving' speed as the",
         "  cleaner travel measure; a surveyed stop list would separate the rest."]
    report = "\n".join(L)
    with open(os.path.join(DATA, "calibration_report.txt"), "w", encoding="utf-8") as f:
        f.write(report)
    print(report)

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        cmap = {"core": "#c62828", "periphery": "#0f8a5f", "mid": "#e0a100"}
        fig, ax = plt.subplots(figsize=(8, 6))
        for z in ("mid", "periphery", "core"):
            s = prof[prof.zone == z]
            ax.scatter(s.dist_hub_km, s.moving_kmh, s=np.clip(s.n_runs * 2, 15, 180),
                       color=cmap[z], alpha=0.65, edgecolors="none", label=f"{z} ({len(s)})")
        ax.axhline(prof.moving_kmh.median(), ls="--", color="#888", lw=1,
                   label=f"median {prof.moving_kmh.median():.0f} km/h")
        ax.set_xlabel("distance from core hub (km)"); ax.set_ylabel("measured MOVING speed (km/h)")
        ax.set_title("Measured bus moving speed by corridor\n(closer to core = slower; size = runs)", weight="bold")
        ax.legend(fontsize=9); ax.grid(alpha=0.15)
        fig.tight_layout(); fig.savefig(os.path.join(DATA, "calibration.png"), dpi=140, bbox_inches="tight"); plt.close(fig)
    except Exception as e:
        print("(png skipped:", str(e)[:60], ")")

    print("\nWrote data/corridor_profiles.csv, data/calibration.png, data/calibration_report.txt")


if __name__ == "__main__":
    main()

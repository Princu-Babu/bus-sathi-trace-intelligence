#!/usr/bin/env python
"""
Export the REALITY LAYER for the bus-sathi dashboard.

Writes compact, PII-free JSON into the dashboard repo's
public/kashmir-reality/ — everything aggregate-only (no driver ids, no raw
traces, coords rounded). What ships:

  corridors.geojson  — the 25 observed corridors + AI verdicts (post-audit)
  stops.geojson      — STRONG observed stops only (>=3 drivers, >=10 visits)
  speed.geojson      — supported speed cells (median measured bus km/h)
  ops.json           — operations headline + in-service-by-hour curve + scope

Run AFTER the pipeline + aggregate_corridors:
  & "D:\\plotting\\ana\\python.exe" src\\export_dashboard.py
"""
import os, json
import numpy as np
import pandas as pd
from common import DATA

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DASH = os.environ.get("DASH_REPO", "E:/dash/bus-sathi-dashboard")
OUT = os.path.join(DASH, "public", "kashmir-reality")
IST_S = 19800


def rnd(coords, nd):
    return [[round(c[0], nd), round(c[1], nd)] for c in coords]


def main():
    os.makedirs(OUT, exist_ok=True)

    # ── corridors + verdicts (post-audit; no PII in props) ─────────
    with open(os.path.join(ROOT, "analyst", "corridors_verdicts.geojson"), encoding="utf-8") as f:
        gj = json.load(f)
    for ft in gj["features"]:
        ft["geometry"]["coordinates"] = rnd(ft["geometry"]["coordinates"], 5)
        ft["properties"] = {k: ft["properties"][k] for k in
                            ("corridor_id", "class", "od", "matched_permit", "confidence",
                             "n_runs", "n_drivers", "median_km") if k in ft["properties"]}
    with open(os.path.join(OUT, "corridors.geojson"), "w", encoding="utf-8") as f:
        json.dump(gj, f, separators=(",", ":"))
    print(f"corridors.geojson: {len(gj['features'])} features")

    # ── strong stops only ──────────────────────────────────────────
    with open(os.path.join(DATA, "stops_candidates.geojson"), encoding="utf-8") as f:
        sj = json.load(f)
    strong = [ft for ft in sj["features"] if ft["properties"].get("strong")]
    for ft in strong:
        ft["geometry"]["coordinates"] = [round(c, 5) for c in ft["geometry"]["coordinates"]]
        p = ft["properties"]
        ft["properties"] = dict(stop_id=p["stop_id"], visits=p["visits"],
                                drivers=p["drivers"], dwell_s=p["median_dwell_s"])
    with open(os.path.join(OUT, "stops.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": strong}, f, separators=(",", ":"))
    print(f"stops.geojson: {len(strong)} strong stops")

    # ── supported speed cells ──────────────────────────────────────
    with open(os.path.join(DATA, "speed_cells.geojson"), encoding="utf-8") as f:
        vj = json.load(f)
    cells = []
    for ft in vj["features"]:
        p = ft["properties"]
        if not p.get("supported"):
            continue
        cells.append({"type": "Feature",
                      "properties": {"kmh": p["median_kmh"], "n": p["samples"]},
                      "geometry": {"type": "Point",
                                   "coordinates": [round(c, 4) for c in ft["geometry"]["coordinates"]]}})
    with open(os.path.join(OUT, "speed.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": cells}, f, separators=(",", ":"))
    print(f"speed.geojson: {len(cells)} supported cells")

    # ── ops summary + hourly curve (recomputed from runs cache) ────
    runs = pd.read_pickle(os.path.join(DATA, "runs.pkl.gz"), compression="gzip")
    ist = pd.to_datetime(runs.start_ts, unit="ms", utc=True) + pd.Timedelta(seconds=IST_S)
    runs = runs.assign(start_ist=ist, day=ist.dt.date)
    dd = runs.groupby(["driver", "day"]).agg(
        n=("run_id", "size"), svc=("dur_min", "sum"), km=("raw_km", "sum"),
        t0=("start_ts", "min"), t1=("end_ts", "max")).reset_index()
    dd["span"] = (dd.t1 - dd.t0) / 60000.0
    multi = dd[dd.n >= 2]
    hours = np.zeros(24)
    for _, r in runs.iterrows():
        h0 = r.start_ist.hour + r.start_ist.minute / 60.0
        h1 = h0 + r.dur_min / 60.0
        for h in range(24):
            hours[h] += max(0.0, min(h1, h + 1) - max(h0, h))
    curve = [round(v * 60 / len(dd), 1) for v in hours]   # in-service min per driver-day

    dj = pd.read_csv(os.path.join(DATA, "driver_days.csv"))
    tn = pd.read_csv(os.path.join(DATA, "turnarounds.csv"))
    ops = dict(
        scope=("Measured from ~157 observed drivers (partial, self-selected adoption). "
               "Per-vehicle physics is robust; this is NOT network supply/frequency/demand."),
        drivers=int(runs.driver.nunique()), driver_days=int(len(dd)),
        runs=int(len(runs)), observed_days=int(runs.day.nunique()),
        duty_span_h=round(float(multi.span.median()) / 60, 1),
        in_service_h=round(float(multi.svc.median()) / 60, 1),
        utilisation=round(float((multi.svc / multi.span).clip(upper=1).median()), 2),
        runs_per_day=int(dd.n.median()), km_per_day=int(dd.km.median()),
        turnaround_min=int(tn.gap_min.median()) if len(tn) else None,
        turnaround_n=int(len(tn)),
        day_start=str(pd.to_datetime(dj.first_start, format="%H:%M").median().strftime("%H:%M")),
        day_end=str(pd.to_datetime(dj.last_end, format="%H:%M").median().strftime("%H:%M")),
        peak_hour=int(np.argmax(hours)),
        moving_kmh=21.0, effective_kmh=12.5, dwell_share=0.37,
        in_service_by_hour=curve,
        corridor_tally=dict(matched=7, partial=8, out_of_area=2, artifact=1, informal=0),
        coverage_note=("The 25 corridors cover 41% of clean runs; the remaining 59% is "
                       "off-terminal noise, loops and out-of-division traffic (no missed corridors)."))
    with open(os.path.join(OUT, "ops.json"), "w", encoding="utf-8") as f:
        json.dump(ops, f, indent=1)
    print("ops.json written")

    for fn in os.listdir(OUT):
        print(f"  {fn}: {os.path.getsize(os.path.join(OUT, fn))/1024:.0f} KB")


if __name__ == "__main__":
    main()

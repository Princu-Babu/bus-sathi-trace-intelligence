#!/usr/bin/env python
"""
Map-match every service run to the road network (OSRM /match) and keep a
realistic, road-snapped geometry + metrics for each.

Quality gate is the raw<->matched AGREEMENT (matched_km / raw_km), not OSRM's
raw confidence (which unfairly penalises long clean runs). Idling scribble
fails the ratio; genuine runs pass.

Outputs (gitignored):
  data/runs_matched.pkl.gz   — matched geometry + metrics per run
  data/runs_matched.geojson  — clean matched runs (for GIS / the corridor stage)

Run (OSRM up on :5000):  & "D:\\plotting\\ana\\python.exe" src\\match_runs.py
"""
import os, json
import pandas as pd
import requests
from common import DATA, OSRM, hav_m

DOWNSAMPLE_M = 70
MAX_PTS = 95
AGREE_LO, AGREE_HI = 0.6, 1.6   # matched/raw length must be in this band


def downsample(poly):
    out, acc = [poly[0]], 0.0
    for a, b in zip(poly, poly[1:]):
        acc += hav_m(a[0], a[1], b[0], b[1])
        if acc >= DOWNSAMPLE_M:
            out.append(b); acc = 0
    if out[-1] != poly[-1]:
        out.append(poly[-1])
    if len(out) > MAX_PTS:
        idx = sorted(set(round(i * (len(out) - 1) / (MAX_PTS - 1)) for i in range(MAX_PTS)))
        out = [out[i] for i in idx]
    return out


def match(poly):
    ds = downsample(poly)
    coords = ";".join(f"{lo:.6f},{la:.6f}" for la, lo in ds)
    rad = ";".join("25" for _ in ds)
    url = (f"{OSRM}/match/v1/driving/{coords}"
           f"?geometries=geojson&overview=full&tidy=true&gaps=split&radiuses={rad}")
    try:
        j = requests.get(url, timeout=40).json()
    except Exception:
        return None
    if j.get("code") != "Ok" or not j.get("matchings"):
        return None
    geom, dist, confs = [], 0.0, []
    for m in j["matchings"]:
        geom += m["geometry"]["coordinates"]
        dist += m.get("distance", 0)
        confs.append(m.get("confidence", 0))
    if not geom:
        return None
    return geom, dist / 1000.0, round(sum(confs) / len(confs), 3)


def main():
    runs = pd.read_pickle(os.path.join(DATA, "runs.pkl.gz"), compression="gzip")
    print(f"Matching {len(runs):,} runs against OSRM ...")

    rows = []
    for n, (_, r) in enumerate(runs.iterrows(), 1):
        res = match(r["poly"])
        if res is None:
            rows.append(dict(run_id=r.run_id, matched=False))
            continue
        geom, mkm, conf = res
        agree = mkm / r.raw_km if r.raw_km else 0
        dur_h = r.dur_min / 60.0
        rows.append(dict(
            run_id=r.run_id, trip_id=r.trip_id, driver=r.driver, matched=True,
            start_ts=int(r.start_ts), dur_min=r.dur_min, raw_km=r.raw_km,
            matched_km=round(mkm, 2), agreement=round(agree, 2), confidence=conf,
            real_kmh=round(mkm / dur_h, 1) if dur_h else 0, n_stops=int(r.n_stops),
            clean=bool(AGREE_LO <= agree <= AGREE_HI),
            start_lat=r.start_lat, start_lon=r.start_lon, end_lat=r.end_lat, end_lon=r.end_lon,
            geom=[(c[1], c[0]) for c in geom],   # store (lat,lon)
        ))
        if n % 250 == 0:
            print(f"   ...{n}/{len(runs)}")

    mm = pd.DataFrame(rows)
    ok = mm[mm.matched == True]
    clean = ok[ok.clean == True]
    mm.to_pickle(os.path.join(DATA, "runs_matched.pkl.gz"), compression="gzip")

    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {k: (None if pd.isna(r[k]) else r[k]) for k in
                        ("run_id", "driver", "matched_km", "dur_min", "real_kmh", "agreement", "confidence", "n_stops")},
         "geometry": {"type": "LineString", "coordinates": [[lo, la] for la, lo in r["geom"]]}}
        for _, r in clean.iterrows()]}
    with open(os.path.join(DATA, "runs_matched.geojson"), "w", encoding="utf-8") as f:
        json.dump(fc, f)

    print("\n── Map-match summary ───────────────────────────────")
    print(f"Runs:                 {len(mm):,}")
    print(f"Matched by OSRM:      {len(ok):,}")
    print(f"CLEAN (agree {AGREE_LO}-{AGREE_HI}): {len(clean):,}")
    if len(ok):
        print(f"Agreement median:     {ok.agreement.median():.2f}")
        print(f"Real speed km/h:      median {clean.real_kmh.median():.1f}" if len(clean) else "")
    print("\nWrote data/runs_matched.pkl.gz, data/runs_matched.geojson")


if __name__ == "__main__":
    main()

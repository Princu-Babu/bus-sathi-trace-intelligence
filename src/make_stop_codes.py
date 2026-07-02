#!/usr/bin/env python
"""
Code the OBSERVED stops in the plan's existing geo-canonical terminology.

The engine's stop registry (Kashmir_Stops_Master_v4.csv) codes every stop as
<District2>-<Sector2>-<Stop2> where Sector = the district's alphabetically-
numbered tehsil (route_code_system.AdminIndex — imported directly from the
engine repo so the numbering is byte-compatible).

Observed stops get the SAME district+sector terminology but an X-series stop
number: <D2>-<S2>-X<nn>  (X = observed via app GPS, NOT in the official
register — provisional until field-validated; numbering is by support rank
within each district+sector). Also attaches: a Nominatim place name, the
nearest master stop + distance (so the RTO can anchor each one), tier, and
support counts.

Output: data/observed_stops_coded.csv

Run:  & "D:\\plotting\\ana\\python.exe" src\\make_stop_codes.py
"""
import os, sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\kash")
import pandas as pd
import numpy as np
from route_code_system import AdminIndex

try:
    from route_code_system import _DIST2 as DIST2
except ImportError:
    DIST2 = {"Srinagar": "SR", "Ganderbal": "GB", "Bandipore": "BP", "Baramulla": "BR",
             "Budgam": "BG", "Pulwama": "PW", "Shopian": "SP", "Anantnag": "AN",
             "Kulgam": "KG", "Kupwara": "KW"}

from common import DATA, hav_m
from build_evidence import reverse_geocode

ENGINE = r"E:\kash"
MASTER = os.path.join(ENGINE, "outputs_v3.4.5", "Kashmir_Stops_Master_v4.csv")


def main():
    admin = AdminIndex(os.path.join(ENGINE, "kashmir_districts_osm.geojson"),
                       os.path.join(ENGINE, "kashmir_tehsils_osm.geojson"))
    master = pd.read_csv(MASTER)

    t1 = json.load(open(os.path.join(DATA, "stops_candidates.geojson"), encoding="utf-8"))["features"]
    t1 = [f for f in t1 if f["properties"].get("strong")]
    t2 = json.load(open(os.path.join(DATA, "stops_tier2.geojson"), encoding="utf-8"))["features"]

    rows = []
    for tier, feats in ((1, t1), (2, t2)):
        for f in feats:
            lon, lat = f["geometry"]["coordinates"]
            p = f["properties"]
            rows.append(dict(tier=tier, lat=lat, lon=lon,
                             visits=int(p.get("visits", 0)),
                             drivers=int(p.get("drivers", 0)),
                             dwell_s=float(p.get("median_dwell_s", p.get("dwell_s", 0)))))
    df = pd.DataFrame(rows)
    print(f"Observed stops to code: {len(df)} (Tier-1 {len(t1)} / Tier-2 {len(t2)})")

    # STRICT containment first — AdminIndex.locate() falls back to the NEAREST
    # district for outside points (fine for slightly-off geocodes, wrong for
    # Jammu-side stops 50 km away), so clip to the actual district union.
    from shapely.geometry import Point
    from shapely.ops import unary_union
    union = unary_union([poly for _, poly in admin.districts])
    inside = [union.contains(Point(lo, la)) for la, lo in zip(df.lat, df.lon)]
    n0 = len(df)
    df = df[pd.Series(inside, index=df.index)].reset_index(drop=True)
    print(f"Inside the 10-district union: {len(df)} (dropped {n0 - len(df)} outside — NH-44/Jammu side)")

    # district + sector via the engine's own AdminIndex
    dist, sect, tehsil = [], [], []
    for la, lo in zip(df.lat, df.lon):
        dname, tname, sec = admin.locate(la, lo)
        dist.append(dname); tehsil.append(tname); sect.append(sec)
    df["district"], df["tehsil"], df["sector"] = dist, tehsil, sect
    df["d2"] = df.district.map(DIST2).fillna("XX")
    df = df[df.d2 != "XX"].reset_index(drop=True)

    # X-series numbering: by support rank within (district, sector)
    df = df.sort_values(["d2", "sector", "visits", "drivers"],
                        ascending=[True, True, False, False]).reset_index(drop=True)
    xno = df.groupby(["d2", "sector"]).cumcount() + 1
    df["stop_code"] = [f"{d}-{s:02d}-X{n:02d}" for d, s, n in zip(df.d2, df.sector, xno)]

    # nearest master stop (anchor for the RTO)
    m_lat = master.Latitude.to_numpy(); m_lon = master.Longitude.to_numpy()
    near_name, near_code, near_m = [], [], []
    for la, lo in zip(df.lat, df.lon):
        d = [hav_m(la, lo, a, b) for a, b in zip(m_lat, m_lon)]
        i = int(np.argmin(d))
        near_name.append(master.Stop_Name.iloc[i]); near_code.append(master.Master_Stop_Code.iloc[i])
        near_m.append(round(d[i]))
    df["nearest_master_stop"] = near_name
    df["nearest_master_code"] = near_code
    df["nearest_master_m"] = near_m

    # place names (Nominatim, cached, rate-limited — the slow part)
    print("Reverse-geocoding place names (cached where possible)…")
    places = []
    for k, (la, lo) in enumerate(zip(df.lat, df.lon)):
        g = reverse_geocode(round(la, 5), round(lo, 5))
        places.append(g.get("place") or "")
        if (k + 1) % 50 == 0:
            print(f"  {k+1}/{len(df)}")
    df["place"] = places

    out = df[["stop_code", "tier", "place", "district", "tehsil", "sector",
              "visits", "drivers", "dwell_s", "lat", "lon",
              "nearest_master_stop", "nearest_master_code", "nearest_master_m"]]
    out.to_csv(os.path.join(DATA, "observed_stops_coded.csv"), index=False)
    print(f"\nBy district: {df.district.value_counts().to_dict()}")
    print(f"Wrote data/observed_stops_coded.csv ({len(out)} stops)")
    print(out.head(8).to_string(index=False))


if __name__ == "__main__":
    main()

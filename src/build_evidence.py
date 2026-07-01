#!/usr/bin/env python
"""
Corridor Analyst — Phase A: build one evidence packet per support-gated corridor.

For each corridor (>=5 runs, >=2 drivers) writes:
  analyst/evidence/C<id>.json  — metrics + operating hours + reverse-geocoded
                                 endpoint/waypoint place names + observed stops on
                                 the corridor + a RECALL-FIRST candidate-permit
                                 shortlist (top-K by overlap; the AI picks).
  analyst/evidence/C<id>.png   — labelled map: corridor + candidate permits + stops.
  analyst/corridor_queue.csv   — ordered work list.
Geocoding cached in analyst/geocode_cache.json; Nominatim rate-limited (>=1 s).
Idempotent: skips corridors whose packet JSON already exists (resumable).

Run:  & "D:\\plotting\\ana\\python.exe" src\\build_evidence.py
"""
import os, json, csv, math, time
import numpy as np
import pandas as pd
import requests
from shapely.geometry import LineString, Point, shape
from shapely.strtree import STRtree
from shapely.ops import unary_union
from common import DATA, hav_m

ENGINE = r"E:\kash"
ROUTES_GEOJSON = os.path.join(ENGINE, "outputs_v3.4.4", "Rationalised_Routes_Kashmir_v3.geojson")
DISTRICTS_GEOJSON = os.path.join(ENGINE, "kashmir_districts_osm.geojson")

ANALYST = os.path.join(os.path.dirname(DATA), "analyst")
EVID = os.path.join(ANALYST, "evidence")
GEO_CACHE = os.path.join(ANALYST, "geocode_cache.json")
os.makedirs(EVID, exist_ok=True)

MIN_RUNS, MIN_DRIVERS = 5, 2
NEAR_M = 60.0
TOPK = 5
STOP_NEAR_M = 140.0
IST = 19800
LAT0 = 34.0
_KX = math.cos(math.radians(LAT0)) * 111320.0
_KY = 111320.0


def to_m(lat, lon):
    return (lon * _KX, lat * _KY)


_gc = json.load(open(GEO_CACHE, encoding="utf-8")) if os.path.exists(GEO_CACHE) else {}


def reverse_geocode(lat, lon):
    key = f"{lat:.5f},{lon:.5f}"
    if key in _gc:
        return _gc[key]
    try:
        r = requests.get("https://nominatim.openstreetmap.org/reverse",
                         params={"lat": lat, "lon": lon, "format": "json", "zoom": 16, "addressdetails": 1},
                         headers={"User-Agent": "bus-sathi-trace-intelligence/1.0 (research)"}, timeout=20)
        j = r.json()
        addr = j.get("address", {})
        name = (addr.get("suburb") or addr.get("neighbourhood") or addr.get("village")
                or addr.get("town") or addr.get("city_district") or addr.get("city")
                or addr.get("county") or j.get("name") or "")
        out = {"place": name, "display": j.get("display_name", "")}
    except Exception as e:
        out = {"place": "", "display": f"(geocode failed: {str(e)[:40]})"}
    _gc[key] = out
    with open(GEO_CACHE, "w", encoding="utf-8") as f:
        json.dump(_gc, f)
    time.sleep(1.1)  # Nominatim policy
    return out


def main():
    routes = []
    for f in json.load(open(ROUTES_GEOJSON, encoding="utf-8"))["features"]:
        g = f["geometry"]
        if g["type"] == "LineString" and len(g["coordinates"]) >= 2:
            routes.append(dict(props=f["properties"],
                               line=LineString([to_m(la, lo) for lo, la in g["coordinates"]])))
    rtree = STRtree([r["line"] for r in routes]); n_r = len(routes)
    study = unary_union([shape(f["geometry"]) for f in
                         json.load(open(DISTRICTS_GEOJSON, encoding="utf-8"))["features"]])

    corr = {f["properties"]["corridor_id"]: f
            for f in json.load(open(os.path.join(DATA, "corridors.geojson"), encoding="utf-8"))["features"]}
    prof = pd.read_csv(os.path.join(DATA, "corridor_profiles.csv")).set_index("corridor_id")
    r2c = pd.read_csv(os.path.join(DATA, "run_corridor.csv"))
    runs = pd.read_pickle(os.path.join(DATA, "runs.pkl.gz"), compression="gzip")[["run_id", "start_ts"]]
    runs = runs.merge(r2c, on="run_id")
    stops = json.load(open(os.path.join(DATA, "stops_candidates.geojson"), encoding="utf-8"))["features"]
    stop_pts = [(s["geometry"]["coordinates"][1], s["geometry"]["coordinates"][0], s["properties"]) for s in stops]

    supported = sorted([cid for cid in prof.index
                        if prof.loc[cid, "n_runs"] >= MIN_RUNS and prof.loc[cid, "n_drivers"] >= MIN_DRIVERS])
    print(f"Support-gated corridors: {len(supported)}")

    queue = []
    for cid in supported:
        queue.append(cid)
        pkt_path = os.path.join(EVID, f"C{cid}.json")
        if os.path.exists(pkt_path):
            continue
        f = corr[cid]; p = f["properties"]; pr = prof.loc[cid]
        geom = f["geometry"]["coordinates"]            # [lon,lat]
        poly_ll = [(la, lo) for lo, la in geom]

        # operating hours (IST)
        hrs = [int(((t / 1000 + IST) // 3600) % 24) for t in runs.loc[runs.corridor_id == cid, "start_ts"]]
        by_hour = {h: hrs.count(h) for h in sorted(set(hrs))}
        op = {"first": min(hrs), "last": max(hrs), "peak": max(by_hour, key=by_hour.get), "by_hour": by_hour} if hrs else {}

        # endpoints + a midpoint, reverse geocoded
        ta = poly_ll[0]; tb = poly_ll[-1]; mid = poly_ll[len(poly_ll) // 2]  # rep-run endpoints = terminals
        eps = []
        for (la, lo), role in [(ta, "terminal A"), (tb, "terminal B"), (mid, "mid-route")]:
            g = reverse_geocode(la, lo)
            eps.append({"role": role, "lat": round(la, 5), "lon": round(lo, 5), "place": g["place"], "address": g["display"]})

        # candidate permits: top-K by overlap (recall-first)
        pts_m = [Point(to_m(la, lo)) for la, lo in poly_ll]
        per = [0] * n_r
        for pt in pts_m:
            for i in rtree.query(pt, predicate="dwithin", distance=NEAR_M):
                per[int(i)] += 1
        order = sorted(range(n_r), key=lambda i: per[i], reverse=True)
        cands = []
        for i in order[:TOPK]:
            cov = per[i] / len(pts_m)
            if cov <= 0 and cands:
                break
            rp = routes[i]["props"]
            cands.append({"route_id": rp.get("New_Route_ID", ""), "route_name": rp.get("Route_Name", ""),
                          "route_type": rp.get("Route_Type", ""), "km": rp.get("Route_KM", ""),
                          "headway_min": rp.get("Headway_Min", ""), "overlap": round(cov, 2)})

        # observed stops on the corridor
        line_m = LineString([to_m(la, lo) for la, lo in poly_ll])
        on_stops = []
        for slat, slon, sp in stop_pts:
            if line_m.distance(Point(to_m(slat, slon))) <= STOP_NEAR_M:
                on_stops.append({"lat": round(slat, 5), "lon": round(slon, 5), "visits": sp.get("visits"),
                                 "drivers": sp.get("drivers"), "dwell_s": sp.get("median_dwell_s"), "strong": sp.get("strong")})
        on_stops.sort(key=lambda s: -(s["visits"] or 0))

        packet = {
            "corridor_id": int(cid),
            "support": {"n_runs": int(p["n_runs"]), "n_drivers": int(p["n_drivers"]), "n_days": int(p["n_days"])},
            "observed": {"median_km": float(pr.km), "median_oneway_min": float(pr.obs_oneway_min),
                         "moving_kmh": float(pr.moving_kmh), "effective_kmh": float(pr.effective_kmh),
                         "dwell_min": float(pr.dwell_min), "dwell_share": float(pr.dwell_share),
                         "runs_per_day": p.get("runs_per_day"), "implied_headway_min": p.get("implied_headway_min")},
            "zone": str(pr.zone), "dist_hub_km": float(pr.dist_hub_km),
            "in_area": bool(study.contains(Point(mid[1], mid[0]))),
            "operating_hours_IST": op,
            "endpoints": eps,
            "candidate_permits": cands,
            "current_script_verdict": str(pr.verdict) if "verdict" in pr and pd.notna(pr.verdict) else "",
            "observed_stops_on_corridor": on_stops[:20],
            "map": f"evidence/C{cid}.png",
            "NOTE": "Metrics are measured (authoritative). AI: judge permit match / informal / narrative / which stops look real, grounded in THIS packet + web. Do not invent permits or roads.",
        }
        with open(pkt_path, "w", encoding="utf-8") as fp:
            json.dump(packet, fp, indent=1, default=str)

        # map
        try:
            import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(8, 8))
            cc = ["#2b6cb0", "#e0a100", "#7c3aed", "#0891b2", "#be185d"]
            for k, cd in enumerate(cands[:5]):
                ri = next((rr for rr in routes if rr["props"].get("New_Route_ID") == cd["route_id"]), None)
                if ri:
                    xs, ys = ri["line"].xy
                    ax.plot(xs, ys, "-", color=cc[k], lw=1.4, alpha=0.6,
                            label=f"{cd['route_name'][:26]} ({cd['overlap']:.0%})")
            xy = [to_m(la, lo) for la, lo in poly_ll]
            ax.plot([q[0] for q in xy], [q[1] for q in xy], "-", color="#0f8a5f", lw=3, label="OBSERVED corridor")
            for s in on_stops[:20]:
                ax.plot(*to_m(s["lat"], s["lon"]), "o", color="#c62828", ms=3, alpha=0.6)
            for e in eps[:2]:
                x, y = to_m(e["lat"], e["lon"])
                ax.plot(x, y, "*", color="#111", ms=13)
                ax.annotate(e["place"] or "?", (x, y), fontsize=9, weight="bold",
                            xytext=(4, 4), textcoords="offset points")
            ax.set_title(f"Corridor C{cid} — {p['n_runs']} runs / {p['n_drivers']} drivers", weight="bold")
            ax.legend(fontsize=7, loc="best"); ax.set_aspect("equal", "datalim"); ax.set_xticks([]); ax.set_yticks([])
            fig.tight_layout(); fig.savefig(os.path.join(EVID, f"C{cid}.png"), dpi=130, bbox_inches="tight"); plt.close(fig)
        except Exception as e:
            print(f"   C{cid} map skipped:", str(e)[:50])
        print(f"  built C{cid}  ({len(cands)} candidate permits, {len(on_stops)} stops)")

    with open(os.path.join(ANALYST, "corridor_queue.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["corridor_id", "n_runs", "n_drivers"])
        for cid in supported:
            w.writerow([cid, int(prof.loc[cid, "n_runs"]), int(prof.loc[cid, "n_drivers"])])

    print(f"\nQueue: {len(supported)} corridors → analyst/corridor_queue.csv")
    print("Evidence packets in analyst/evidence/  (Phase B: analyse one at a time)")


if __name__ == "__main__":
    main()

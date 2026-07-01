#!/usr/bin/env python
"""
Segment shift-long trips into runs and map-match them to the road network.

For a sample of trips it: segments on time gaps, downsamples, calls OSRM
`/match` to snap noisy GPS onto real roads, and writes a before/after
(raw vs matched) GeoJSON + PNG + interactive map so we can see how well the
denoising works on real Bus Sathi data.

Run (OSRM must be up on :5000):
    & "D:\\plotting\\ana\\python.exe" src\\match_traces.py --sample 60
"""
import os, sys, json, math, argparse, hashlib
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SA_PATH = os.path.join(ROOT, "secrets", "serviceAccount.json")
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)
OSRM = "http://localhost:5000"

GAP_S = 480          # split a trip into runs on a >8 min gap
MIN_RUN_PTS = 25     # ignore tiny runs
MIN_RUN_KM = 0.8     # ignore runs that barely moved
DOWNSAMPLE_M = 70    # one point roughly every 70 m before matching
MAX_MATCH_PTS = 95   # OSRM default max-matching-size is 100


def h(x):
    s = str(x or "").strip()
    return "anon" if not s else hashlib.sha256(s.encode()).hexdigest()[:12]


def to_ms(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v * 1000) if v < 1e12 else int(v)
    if hasattr(v, "timestamp"):
        try:
            return int(v.timestamp() * 1000)
        except Exception:
            return None
    try:
        return int(v)
    except Exception:
        return None


def point(p):
    if not isinstance(p, dict):
        return None
    lat = p.get("lat", p.get("latitude"))
    lon = p.get("lng", p.get("longitude", p.get("lon")))
    t = to_ms(p.get("timestamp", p.get("time", p.get("ts"))))
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)) or (lat == 0 and lon == 0):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return (lat, lon, t)


def hav_km(a, b):
    R = 6371.0
    dlat = math.radians(b[0] - a[0]); dlon = math.radians(b[1] - a[1])
    x = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def path_km(pts):
    return sum(hav_km(pts[i - 1], pts[i]) for i in range(1, len(pts)))


def segment_runs(pts):
    """Split one shift-long trip into runs on large time gaps."""
    pts = [p for p in pts if p]
    pts.sort(key=lambda p: (p[2] or 0))
    if len(pts) < 2:
        return []
    runs, cur = [], [pts[0]]
    for prev, p in zip(pts, pts[1:]):
        dt = ((p[2] - prev[2]) / 1000.0) if (p[2] and prev[2]) else 0
        if dt > GAP_S:
            runs.append(cur); cur = [p]
        else:
            cur.append(p)
    runs.append(cur)
    good = []
    for r in runs:
        if len(r) >= MIN_RUN_PTS and path_km(r) >= MIN_RUN_KM:
            good.append(r)
    return good


def downsample(run):
    out, acc = [run[0]], 0.0
    for prev, p in zip(run, run[1:]):
        acc += hav_km(prev, p) * 1000
        if acc >= DOWNSAMPLE_M:
            out.append(p); acc = 0
    if out[-1] is not run[-1]:
        out.append(run[-1])
    if len(out) > MAX_MATCH_PTS:  # uniform thin
        idx = sorted(set(round(i * (len(out) - 1) / (MAX_MATCH_PTS - 1)) for i in range(MAX_MATCH_PTS)))
        out = [out[i] for i in idx]
    return out


def osrm_match(run):
    """Snap a downsampled run to roads. Returns matched coords + confidence."""
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon, _ in run)
    rad = ";".join("25" for _ in run)
    url = (f"{OSRM}/match/v1/driving/{coords}"
           f"?geometries=geojson&overview=full&tidy=true&gaps=split&radiuses={rad}")
    try:
        j = requests.get(url, timeout=40).json()
    except Exception as e:
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
    return dict(coords=geom, matched_km=dist / 1000.0,
                confidence=round(sum(confs) / len(confs), 3))


def pull_sample(n):
    import firebase_admin
    from firebase_admin import credentials, firestore
    firebase_admin.initialize_app(credentials.Certificate(SA_PATH))
    db = firestore.client()
    docs = list(db.collection("trips").order_by("__name__").limit(n).stream())
    trips = []
    for d in docs:
        t = d.to_dict() or {}
        raw = t.get("routePoints") or t.get("points") or []
        pts = [point(p) for p in raw] if isinstance(raw, list) else []
        pts = [p for p in pts if p]
        if pts:
            trips.append((d.id, h(t.get("driverId") or t.get("driverEmail")), pts))
    return trips


def render_png(results, path, k=6):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print("(matplotlib unavailable, skipping PNG:", str(e)[:50], ")")
        return False
    show = results[:k]
    cols = 3
    rows = (len(show) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.6, rows * 3.6))
    axes = axes.ravel() if hasattr(axes, "ravel") else [axes]
    for ax, r in zip(axes, show):
        raw = r["raw"]           # (lat,lon,ts)
        mat = r["matched"]       # [lon,lat]
        ax.plot([p[1] for p in raw], [p[0] for p in raw], "-", color="#d1495b",
                lw=0.8, marker="o", ms=2, alpha=0.7, label="raw GPS")
        ax.plot([c[0] for c in mat], [c[1] for c in mat], "-", color="#0f8a5f",
                lw=2.2, alpha=0.9, label="map-matched")
        ax.set_title(f"conf {r['confidence']}  ·  {r['raw_km']:.1f}→{r['matched_km']:.1f} km", fontsize=8)
        ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal", "datalim")
    for ax in axes[len(show):]:
        ax.axis("off")
    axes[0].legend(fontsize=7, loc="upper right")
    fig.suptitle("Bus Sathi — raw GPS vs OSRM map-matched (sample runs)", fontsize=11, weight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return True


def render_map(results, path):
    try:
        import folium
    except Exception:
        return False
    lat0 = results[0]["raw"][0][0]; lon0 = results[0]["raw"][0][1]
    m = folium.Map(location=[lat0, lon0], zoom_start=12, tiles="cartodbpositron")
    for r in results:
        folium.PolyLine([(p[0], p[1]) for p in r["raw"]], color="#d1495b", weight=2, opacity=0.5).add_to(m)
        folium.PolyLine([(c[1], c[0]) for c in r["matched"]], color="#0f8a5f", weight=3, opacity=0.9,
                        tooltip=f"conf {r['confidence']}").add_to(m)
    m.save(path)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60, help="trip docs to pull")
    ap.add_argument("--max-runs", type=int, default=30, help="runs to match")
    args = ap.parse_args()

    print(f"Pulling {args.sample} trips ...")
    trips = pull_sample(args.sample)
    print(f"  {len(trips)} trips with points")

    results = []
    for trip_id, driver, pts in trips:
        for run in segment_runs(pts):
            ds = downsample(run)
            mm = osrm_match(ds)
            if not mm:
                continue
            results.append(dict(trip=trip_id, driver=driver, raw=run,
                                matched=mm["coords"], confidence=mm["confidence"],
                                raw_km=round(path_km(run), 2), matched_km=round(mm["matched_km"], 2)))
            if len(results) >= args.max_runs:
                break
        if len(results) >= args.max_runs:
            break

    if not results:
        print("No runs matched — check OSRM coverage for this area.")
        return

    confs = [r["confidence"] for r in results]
    print(f"\nMatched {len(results)} runs")
    print(f"  confidence: min {min(confs):.2f} / mean {sum(confs)/len(confs):.2f} / max {max(confs):.2f}")
    print(f"  runs with confidence >= 0.5: {sum(1 for c in confs if c >= 0.5)}/{len(confs)}")

    # matched-only GeoJSON (road geometry; driver hashed)
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {"trip": r["trip"], "driver": r["driver"], "confidence": r["confidence"],
                        "raw_km": r["raw_km"], "matched_km": r["matched_km"]},
         "geometry": {"type": "LineString", "coordinates": r["matched"]}}
        for r in results]}
    with open(os.path.join(DATA, "sample_matched.geojson"), "w", encoding="utf-8") as f:
        json.dump(fc, f)

    png = os.path.join(DATA, "sample_before_after.png")
    render_png(results, png)
    render_map(results, os.path.join(DATA, "sample_match.html"))
    print(f"\nWrote data/sample_matched.geojson, data/sample_before_after.png, data/sample_match.html")


if __name__ == "__main__":
    main()

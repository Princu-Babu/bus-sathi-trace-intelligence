"""Shared helpers for the Bus Sathi trace-intelligence pipeline."""
import os, sys, math, hashlib

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS = os.path.join(ROOT, "secrets", "serviceAccount.json")
DATA = os.path.join(ROOT, "data")
OSRM = "http://localhost:5000"
os.makedirs(DATA, exist_ok=True)


def h(x) -> str:
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
    """Return (lat, lon, ts_ms) or None from a raw routePoint dict."""
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


def hav_m(a_lat, a_lon, b_lat, b_lon):
    R = 6371000.0
    dlat = math.radians(b_lat - a_lat); dlon = math.radians(b_lon - a_lon)
    x = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(a_lat)) * math.cos(math.radians(b_lat)) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(x))


def firestore_client():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(SECRETS))
    return firestore.client()


def pull_all_trips(db, collection="trips", page=25, progress=True):
    """Page the trips collection by document id (routePoints make docs large)."""
    from google.api_core import exceptions as gexc
    col = db.collection(collection)
    last, n = None, 0
    while True:
        q = col.order_by("__name__").limit(page)
        if last is not None:
            q = q.start_after(last)
        try:
            batch = list(q.stream())
        except (gexc.ServiceUnavailable, gexc.DeadlineExceeded):
            if page > 3:
                page = max(3, page // 2)
                continue
            raise
        if not batch:
            return
        for d in batch:
            n += 1
            yield d
        if progress and n % 100 == 0:
            print(f"   ...{n} docs")
        if len(batch) < page:
            return
        last = batch[-1]

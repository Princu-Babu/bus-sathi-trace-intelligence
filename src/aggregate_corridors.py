#!/usr/bin/env python
"""
Corridor Analyst — Phase C: roll up the per-corridor verdicts into findings.

Reads analyst/verdicts/C*.json (the AI verdicts) + data/corridors.geojson
(measured geometry) and writes:
  CORRIDOR_FINDINGS.md                 — committed human report
  analyst/corridors_verdicts.geojson   — corridor geometry + verdict (dashboard)

Run:  & "D:\\plotting\\ana\\python.exe" src\\aggregate_corridors.py
"""
import os, json, glob
from common import DATA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERD = os.path.join(ROOT, "analyst", "verdicts")


def classify(v):
    if v.get("plausible") is False:
        return "artifact"
    if v.get("match_confidence") == "n/a":
        return "out_of_area"
    if v.get("is_informal"):
        return "informal"
    if v.get("match_confidence") in ("high", "medium") and v.get("matched_permit_id"):
        return "matched"
    return "partial"


def main():
    verdicts = {}
    for p in glob.glob(os.path.join(VERD, "C*.json")):
        v = json.load(open(p, encoding="utf-8"))
        verdicts[int(v["corridor_id"])] = v

    geo = {f["properties"]["corridor_id"]: f
           for f in json.load(open(os.path.join(DATA, "corridors.geojson"), encoding="utf-8"))["features"]}

    feats, counts = [], {}
    for cid, v in sorted(verdicts.items()):
        cls = classify(v)
        counts[cls] = counts.get(cls, 0) + 1
        f = geo.get(cid)
        if not f:
            continue
        gp = f["properties"]
        feats.append({"type": "Feature",
                      "properties": {"corridor_id": cid, "class": cls,
                                     "od": v.get("od_description", ""),
                                     "matched_permit": v.get("matched_permit", ""),
                                     "matched_permit_id": v.get("matched_permit_id", ""),
                                     "confidence": v.get("match_confidence", ""),
                                     "is_informal": v.get("is_informal", False),
                                     "needs_review": v.get("needs_human_review", False),
                                     "n_runs": gp["n_runs"], "n_drivers": gp["n_drivers"],
                                     "median_km": gp["median_km"]},
                      "geometry": f["geometry"]})
    with open(os.path.join(ROOT, "analyst", "corridors_verdicts.geojson"), "w", encoding="utf-8") as fp:
        json.dump({"type": "FeatureCollection", "features": feats}, fp)

    def rows(cls):
        return sorted([v for v in verdicts.values() if classify(v) == cls],
                      key=lambda v: -geo.get(v["corridor_id"], {}).get("properties", {}).get("n_runs", 0))

    def n(cid):
        return geo.get(cid, {}).get("properties", {})

    L = ["# Corridor findings — observed corridors judged by AI, one at a time", "",
         "_Method: scripts MEASURE (geometry, speed, frequency); an AI analyst (Opus, one "
         "corridor at a time) JUDGES the permit match / informal call / plausibility, grounded "
         "in a per-corridor evidence packet + web. 18 support-gated corridors (≥5 runs, ≥2 "
         "drivers). Per-corridor audit trail in `analyst/verdicts/`._", "",
         "## Tally", ""]
    for k in ("matched", "partial", "informal", "out_of_area", "artifact"):
        L.append(f"- **{k}**: {counts.get(k, 0)}")
    L += ["", "## Matched to permits", "",
          "| C | O→D | permit | conf |", "|---|---|---|---|"]
    for v in rows("matched"):
        L.append(f"| C{v['corridor_id']} | {v['od_description']} | {v['matched_permit_id']} {v['matched_permit']} | {v['match_confidence']} |")

    L += ["", "## Findings (in-area, no clean permit)", "",
          "### NE-Srinagar under-permitted local cluster",
          "Busy local corridors around **Soura / Zoonimar / Lal Bazar / Nowshera / Ellahibagh "
          "/ Gulab Bagh** with ≤0.40 permit overlap — the formal plan barely covers them. "
          "A formal feeder/loop here is the clearest actionable gap.", ""]
    for v in rows("informal") + rows("partial"):
        cid = v["corridor_id"]; p = n(cid)
        L.append(f"- **C{cid}** ({p.get('n_runs')} runs / {p.get('n_drivers')} drivers): "
                 f"{v['od_description']}  _(review: {v.get('needs_human_review')})_")

    L += ["", "## Out of area (excluded)"]
    for v in rows("out_of_area"):
        L.append(f"- **C{v['corridor_id']}**: {v['od_description']}")
    L += ["", "## Non-service artifacts (excluded)"]
    for v in rows("artifact"):
        L.append(f"- **C{v['corridor_id']}**: {v['od_description']}")

    L += ["", "## Honest caveats",
          "- App adoption is partial (~180 drivers) → observed frequency is a LOWER BOUND, "
          "not real headway; implied headways are omitted from claims.",
          "- Some corridors have thin support (2–4 drivers) — flagged per-verdict as tentative.",
          "- 'Informal' = observed but no matching permit; a candidate for RTO confirmation, "
          "not an assertion of illegality.",
          "- AI verdicts vary between runs; the per-corridor files are the versioned record."]
    with open(os.path.join(ROOT, "CORRIDOR_FINDINGS.md"), "w", encoding="utf-8") as fp:
        fp.write("\n".join(L))

    print("Tally:", counts)
    print(f"Wrote CORRIDOR_FINDINGS.md + analyst/corridors_verdicts.geojson ({len(feats)} corridors)")


if __name__ == "__main__":
    main()

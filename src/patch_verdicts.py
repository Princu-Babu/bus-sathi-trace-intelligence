#!/usr/bin/env python
"""
Correction pass (2026-07-02): a raw-permit check (E:/kash/existing-routes.csv, 614
permits) showed the corridors I earlier flagged as 'under-permitted / informal'
are actually in permitted areas (Lalbazar 26, Soura 83, Gulabagh 2, Budgam 42,
Pampore 40, Safakadal 23, Qamarwari 18, Narbal 9 permit endpoints). The ≤0.40
overlap was against the engine's RATIONALISED geometry — so these are
GEOMETRY-DIVERGENCE flags (rationalised route vs observed reality), NOT informal
routes. This patch retracts the informal/under-permitted implication.
"""
import os, json, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERD = os.path.join(ROOT, "analyst", "verdicts")

CORRECTION = ("RAW-PERMIT CHECK (2026-07-02): the places on this corridor ARE in the raw "
              "permit system (e.g. Lalbazar 26 / Soura 83 / Gulabagh 2 / Budgam 42 / Pampore 40 "
              "permit endpoints; smaller mahallas are traversed, named for major endpoints). "
              "Retracting any 'under-permitted/informal' reading — the ≤0.40 overlap is with the "
              "engine's RATIONALISED geometry, so this is a DIVERGENCE between the rationalised "
              "route geometry and observed reality (engine to reconcile), NOT an informal route.")

AFFECTED = [2, 9, 11, 12, 14, 15, 18]

for cid in AFFECTED:
    p = os.path.join(VERD, f"C{cid}.json")
    v = json.load(open(p, encoding="utf-8"))
    v["is_informal"] = False
    v["correction_raw_permit_check"] = CORRECTION
    v.setdefault("data_quality_flags", []).append(
        "CORRECTED: not informal/under-permitted; observed geometry diverges from rationalised route (see correction field)")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(v, f, indent=2)
    print(f"patched C{cid}: is_informal=False + correction")

print(f"\nPatched {len(AFFECTED)} verdicts. Re-run aggregate_corridors.py.")

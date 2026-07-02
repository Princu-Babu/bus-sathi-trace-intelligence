#!/usr/bin/env python
"""
Engine reality-check — compare the engine's per-route time assumptions against
MEASURED corridor run times from the app GPS, for the corridors the AI analyst
matched to a specific plan route.

For each matched corridor:
  observed one-way minutes (median over runs, dwell included)
      vs
  engine OSRM drive time (car profile, one-way)          -> raw model optimism
  engine Cycle_Time_Min / 2 (planned one-way incl stop/
      junction/bridge penalties + congestion factors)     -> planned vs real

This is the one place the trace layer can directly sharpen the engine: if the
planned one-way consistently undershoots measured reality, cycle times (and so
fleet) are optimistic on those corridors.

Honesty guards: only corridors with a confident permit match are compared
one-to-one; 'partial' (geometry-divergent) matches are listed separately with
a caveat — their observed km differs from the engine's routed km, so the time
comparison is indicative only.

Outputs: REALITY_CHECK.md (committed) · data/reality_check.csv

Run:  & "D:\\plotting\\ana\\python.exe" src\\reality_check.py
"""
import os, sys, json, glob
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
from common import DATA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_CSV = os.environ.get(
    "ENGINE_CSV", "E:/kash/outputs_v3.4.4/Rationalised_Routes_Kashmir_v3.csv")


def main():
    prof = pd.read_csv(os.path.join(DATA, "corridor_profiles.csv"))
    eng = pd.read_csv(ENGINE_CSV)
    eng = eng[eng.Action_Taken != "MERGED_INTO_TRUNK"]

    # corridor -> permit from the AI verdicts (post-audit source of truth)
    rows = []
    for p in sorted(glob.glob(os.path.join(ROOT, "analyst", "verdicts", "C*.json"))):
        v = json.load(open(p, encoding="utf-8"))
        pid = v.get("matched_permit_id")
        if not pid or not v.get("plausible", True):
            continue
        cid = int(os.path.basename(p)[1:-5])
        pr = prof[prof.corridor_id == cid]
        er = eng[eng.New_Route_ID.astype(str) == str(pid)]
        if pr.empty or er.empty:
            continue
        pr, er = pr.iloc[0], er.iloc[0]
        conf = str(v.get("match_confidence", "")).lower()
        klass = "matched" if (not v.get("is_informal") and conf in ("high", "medium")
                              and pr.verdict == "MATCHED") else "partial"
        osrm_min = float(er.OSRM_Duration_S) / 60.0
        plan_oneway = float(er.Cycle_Time_Min) / 2.0
        rows.append(dict(
            corridor=f"C{cid}", od=v.get("od_description", ""), permit=pid,
            route=er.Route_Name, klass=klass,
            n_runs=int(pr.n_runs), n_drivers=int(pr.n_drivers),
            obs_km=round(float(pr.km), 1), eng_km=round(float(er.Route_KM), 1),
            obs_oneway_min=round(float(pr.obs_oneway_min), 1),
            osrm_drive_min=round(osrm_min, 1),
            plan_oneway_min=round(plan_oneway, 1),
            plan_vs_obs=round(plan_oneway / float(pr.obs_oneway_min), 2),
            osrm_vs_obs=round(osrm_min / float(pr.obs_oneway_min), 2)))
    df = pd.DataFrame(rows).sort_values(["klass", "corridor"])
    df.to_csv(os.path.join(DATA, "reality_check.csv"), index=False)

    m = df[df.klass == "matched"]; pt = df[df.klass == "partial"]

    def block(sub):
        out = ["| Corridor | Plan route | Runs | Obs km / Eng km | Observed 1-way | OSRM drive | Planned 1-way (cycle/2) | Planned÷Observed |",
               "|---|---|---|---|---|---|---|---|"]
        for _, r in sub.iterrows():
            out.append(f"| {r.corridor} | {r.route} ({r.permit}) | {r.n_runs}×{r.n_drivers}drv "
                       f"| {r.obs_km} / {r.eng_km} | **{r.obs_oneway_min} min** | {r.osrm_drive_min} min "
                       f"| {r.plan_oneway_min} min | **{r.plan_vs_obs}** |")
        return out

    L = ["# Engine reality-check — planned vs measured route times",
         "",
         "_Measured one-way corridor times (median over app-GPS runs, service stops",
         "included) vs the engine's planned one-way (Cycle_Time/2, which includes stop,",
         "junction and congestion penalties) and the raw OSRM car drive time._",
         "",
         f"**Coverage: {len(m)} confidently-matched + {len(pt)} geometry-divergent corridors.**",
         "Ratios < 1.00 mean the plan allots LESS time than buses measurably take.",
         ""]
    if not m.empty:
        med = m.plan_vs_obs.median(); osr = m.osrm_vs_obs.median()
        L += ["## Confidently matched (like-for-like)", ""] + block(m) + [
            "",
            f"- Median **planned÷observed = {med:.2f}** — the engine's planned one-way times "
            f"{'UNDERSHOOT measured reality' if med < 0.95 else 'are roughly in line with reality' if med <= 1.05 else 'OVERSHOOT measured reality'} on these corridors.",
            f"- Median raw OSRM(car)÷observed = {osr:.2f} — the un-penalised car model alone is far too fast; "
            "the engine's penalty stack closes much of the gap.",
            ""]
    if not pt.empty:
        L += ["## Geometry-divergent (indicative only)",
              "", "_Observed corridor geometry differs from the engine's routed line, so km",
              "and time are not strictly comparable — shown for context._", ""] + block(pt) + [""]
    L += ["## How to read this (do NOT over-read it)",
          "1. **Observed times embody today's informal operating practice** — wait-to-fill",
          "   dwells at stops, flexible stopping — which a scheduled, headway-enforced",
          "   service would compress. The measured medians are an UPPER bound on scheduled",
          "   running time; the engine's planned times are the design target. The truth a",
          "   scheduler should plan for lies between, closer to planned + realistic dwell.",
          "2. Part of each gap is **route length, not speed**: observed corridor paths often",
          "   run longer than the engine's routed line (e.g. C1: 14.4 km observed vs 9.5 km",
          "   routed). Compare per-km effective speeds before adjusting any cycle time.",
          "3. **Where planned÷observed < 1 persistently**, treat the corridor as a cycle-time",
          "   review candidate — not an automatic fleet increase.",
          "4. Measured city-wide anchors: **~21 km/h moving / ~12.5 km/h effective** (dwell",
          "   ≈ 37% of run time), terminal turnaround **median 24 min** — check the engine's",
          "   recovery allowance against that turn figure.",
          "5. Scope: partial adoption (~157 drivers); these corridors are the frequently-",
          "   driven Srinagar core, not the whole network. Rural cycle times remain unvalidated.",
          ""]
    text = "\n".join(L)
    open(os.path.join(ROOT, "REALITY_CHECK.md"), "w", encoding="utf-8").write(text)
    print(text)
    print("Wrote REALITY_CHECK.md + data/reality_check.csv")


if __name__ == "__main__":
    main()

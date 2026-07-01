#!/usr/bin/env python
"""
Operations & fleet — measured duty cycles, turnaround, in-service curve,
driver utilisation. ALL per-vehicle physical measurements (adoption-robust):
they describe the observed drivers' working day, NOT network supply/frequency
(partial adoption forbids those claims — see AUDIT.md).

  1. DUTY CYCLE (per driver-day): first-run start -> last-run end (span),
     in-service time inside it, runs/day, km/day.
  2. TURNAROUND: gap between a driver's consecutive runs on the same day when
     run N ends within TURN_NEAR_M of where run N+1 starts (a terminal turn).
     Only gaps <= TURN_MAX_MIN count (longer = a break/idle, not a turnaround).
  3. IN-SERVICE-BY-HOUR: share of each observed driver-day in service per IST
     hour -> the shape of the operating day (shape is robust; LEVEL is not).
  4. UTILISATION: in-service / span per driver-day.

Outputs: data/operations_report.txt · data/operations.png ·
         data/driver_days.csv (hashed drivers) · data/turnarounds.csv

Run:  & "D:\\plotting\\ana\\python.exe" src\\operations.py
"""
import os
import numpy as np
import pandas as pd
from common import DATA, hav_m

IST_S = 19800                # UTC+5:30
TURN_NEAR_M = 500            # end(run N) near start(run N+1) => same terminal
TURN_MAX_MIN = 90            # beyond this a gap is a break, not a turnaround
MIN_DAY_RUNS = 2             # duty-cycle stats need >=2 runs in the day


def ist(ts_ms):
    return pd.to_datetime(ts_ms, unit="ms", utc=True) + pd.Timedelta(seconds=IST_S)


def main():
    runs = pd.read_pickle(os.path.join(DATA, "runs.pkl.gz"), compression="gzip")
    runs = runs.sort_values(["driver", "start_ts"]).reset_index(drop=True)
    runs["start_ist"] = ist(runs.start_ts)
    runs["end_ist"] = ist(runs.end_ts)
    runs["day"] = runs.start_ist.dt.date
    print(f"{len(runs):,} runs / {runs.driver.nunique()} drivers / "
          f"{runs.day.nunique()} observed days")

    # ── 1+4. duty cycles per driver-day ─────────────────────────────
    dd = []
    for (drv, day), g in runs.groupby(["driver", "day"]):
        span_min = (g.end_ts.max() - g.start_ts.min()) / 60000.0
        svc_min = g.dur_min.sum()
        dd.append(dict(driver=drv, day=str(day), n_runs=len(g),
                       span_min=round(span_min, 1), service_min=round(svc_min, 1),
                       km=round(g.raw_km.sum(), 1),
                       util=round(min(1.0, svc_min / span_min), 2) if span_min > 0 else 1.0,
                       first_start=g.start_ist.min().strftime("%H:%M"),
                       last_end=g.end_ist.max().strftime("%H:%M")))
    dd = pd.DataFrame(dd)
    dd.to_csv(os.path.join(DATA, "driver_days.csv"), index=False)
    multi = dd[dd.n_runs >= MIN_DAY_RUNS]

    # ── 2. turnarounds ──────────────────────────────────────────────
    turns = []
    for (drv, day), g in runs.groupby(["driver", "day"]):
        g = g.sort_values("start_ts")
        for i in range(len(g) - 1):
            a, b = g.iloc[i], g.iloc[i + 1]
            gap_min = (b.start_ts - a.end_ts) / 60000.0
            if gap_min < 0 or gap_min > TURN_MAX_MIN:
                continue
            d_m = hav_m(a.end_lat, a.end_lon, b.start_lat, b.start_lon)
            if d_m <= TURN_NEAR_M:
                turns.append(dict(driver=drv, day=str(day), gap_min=round(gap_min, 1),
                                  lat=round(float(a.end_lat), 5), lon=round(float(a.end_lon), 5)))
    turns = pd.DataFrame(turns)
    turns.to_csv(os.path.join(DATA, "turnarounds.csv"), index=False)

    # ── 3. in-service-by-hour (share of driver-days active per hour) ─
    hours = np.zeros(24)
    n_dd = len(dd)
    for _, r in runs.iterrows():
        h0 = r.start_ist.hour + r.start_ist.minute / 60.0
        h1 = h0 + r.dur_min / 60.0
        for h in range(24):
            ov = max(0.0, min(h1, h + 1) - max(h0, h))
            hours[h] += ov
    hours_share = hours / n_dd if n_dd else hours   # avg in-service min-fraction per driver-day

    # ── report ──────────────────────────────────────────────────────
    L = []
    L.append("OPERATIONS & FLEET — measured from app traces (observed drivers only)")
    L.append("Scope: per-vehicle physical measurement; NOT network supply/frequency.")
    L.append("")
    L.append(f"Driver-days observed: {n_dd:,} ({runs.driver.nunique()} drivers)")
    L.append(f"  runs/day:        median {dd.n_runs.median():.0f} · p90 {dd.n_runs.quantile(.9):.0f} · max {dd.n_runs.max()}")
    L.append(f"  km/day:          median {dd.km.median():.0f} · p90 {dd.km.quantile(.9):.0f}")
    L.append("")
    L.append(f"Duty cycle (driver-days with >=2 runs, n={len(multi):,}):")
    L.append(f"  day span:        median {multi.span_min.median()/60:.1f} h · p90 {multi.span_min.quantile(.9)/60:.1f} h")
    L.append(f"  in-service:      median {multi.service_min.median()/60:.1f} h")
    L.append(f"  utilisation:     median {multi.util.median():.0%} (in-service / span)")
    st = pd.to_datetime(dd.first_start, format="%H:%M")
    en = pd.to_datetime(dd.last_end, format="%H:%M")
    L.append(f"  typical day:     starts ~{st.median().strftime('%H:%M')} · ends ~{en.median().strftime('%H:%M')} (median)")
    L.append("")
    if not turns.empty:
        L.append(f"Terminal turnaround (same-terminal gap <= {TURN_MAX_MIN} min, n={len(turns):,}):")
        L.append(f"  median {turns.gap_min.median():.0f} min · p25 {turns.gap_min.quantile(.25):.0f} · p75 {turns.gap_min.quantile(.75):.0f}")
        L.append("  NOTE: includes recovery + layover + waiting-to-fill; it is the DOOR-TO-DOOR")
        L.append("  turn a scheduler must plan for, not pure recovery time.")
    L.append("")
    pk = int(np.argmax(hours_share))
    L.append("In-service-by-hour (IST; avg in-service fraction per driver-day):")
    for h in range(5, 23):
        bar = "#" * int(round(hours_share[h] * 80))
        L.append(f"  {h:02d}:00  {hours_share[h]*60:5.1f} min  {bar}")
    L.append(f"  Peak hour: {pk:02d}:00 IST. SHAPE is adoption-robust; absolute LEVEL is not.")
    L.append("")
    L.append("Engine signal: cycle-time = run + turnaround. The engine's recovery")
    L.append(f"allowance should be sanity-checked against the measured median turn.")
    rep = "\n".join(L)
    print("\n" + rep)
    with open(os.path.join(DATA, "operations_report.txt"), "w", encoding="utf-8") as f:
        f.write(rep + "\n")

    # ── png ─────────────────────────────────────────────────────────
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 2, figsize=(12, 8.5))
        ax[0, 0].hist(multi.span_min / 60, bins=24, color="#0f6e56", alpha=0.8)
        ax[0, 0].set_title("Duty-day span (h) — driver-days with ≥2 runs", fontsize=10)
        ax[0, 1].hist(multi.util, bins=20, color="#B0432F", alpha=0.8)
        ax[0, 1].set_title("Utilisation (in-service / span)", fontsize=10)
        if not turns.empty:
            ax[1, 0].hist(turns.gap_min, bins=30, color="#2E5EAA", alpha=0.8)
            ax[1, 0].axvline(turns.gap_min.median(), color="k", ls="--", lw=1,
                             label=f"median {turns.gap_min.median():.0f} min")
            ax[1, 0].legend(fontsize=8)
        ax[1, 0].set_title("Terminal turnaround (min)", fontsize=10)
        ax[1, 1].bar(range(24), hours_share * 60, color="#0f6e56", alpha=0.85)
        ax[1, 1].axvline(pk, color="#B0432F", ls="--", lw=1)
        ax[1, 1].set_xlim(4, 23)
        ax[1, 1].set_title("In-service min per driver-day, by IST hour", fontsize=10)
        fig.suptitle("Operations — measured from observed drivers (shape robust, level partial)",
                     weight="bold")
        fig.tight_layout()
        fig.savefig(os.path.join(DATA, "operations.png"), dpi=140, bbox_inches="tight")
        plt.close(fig)
        print("\nWrote data/operations_report.txt, driver_days.csv, turnarounds.csv, operations.png")
    except Exception as e:
        print("(png skipped:", str(e)[:60], ")")


if __name__ == "__main__":
    main()

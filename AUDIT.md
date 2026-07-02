# Audit & honest scope — app-data trace intelligence

_2026-07-02 sanity pass over the trace-intelligence pipeline (not the engine)._

## What this project IS, and is NOT
**IS:** a **validation / ground-truthing** layer for the paper-permit plan —
real corridor geometry, real stops, real operating **speeds**, and a cross-check
of which engine routes are observed vs where observed reality diverges.

**IS NOT:** a route-rationalisation engine. Rationalisation needs representative
**demand** and **frequency**; this data has neither:
- ~180 self-selected drivers, concentrated in the Srinagar core → biased sample;
- `implied_headway` is a pure adoption artifact (omitted from all claims);
- no ridership; dwell time is too confounded (layover vs boarding) to use.
So "a permit with no app data" ≠ "unused", and this data **cannot** decide what
routes to add/cut/resize. It *flags candidates* for the engine/RTO.

## Coverage limit (state this everywhere)
The 25 corridors contain only **989 / 2,426 clean runs (41%)**; the 18 analysed
cover ~40%. The corridor findings describe the **frequently-driven core**, not
the whole network.

**The 59% tail, decomposed (`src/longtail.py`, no AI needed):** of 1,437
uncovered clean runs, **64%** have an endpoint on no robust terminal (depot
pull-outs / mid-route app toggles / scattered ends), **28%** are same-terminal
loops, and **34%** sit outside the 10-district study area (NH-44/Jammu). Only
**40 runs (3%)** form repeat OD pairs under the corridor gate — 20 pairs, of
which just 11 have ≥2 drivers (all exactly 2 runs · 2 drivers; 5 of the 11 are
out-of-area). **Conclusion: the tail hides no missed corridors** — it is noise,
loops, and out-of-division traffic, so the 41% corridor coverage is not
under-clustering; it is the honest ceiling of this dataset. Near-miss table:
`data/longtail_pairs.csv` (revisit only if adoption grows).

## Corrections made in this audit
1. **RETRACTED the "NE-Srinagar under-permitted cluster."** A raw-permit check
   (`E:/kash/existing-routes.csv`, 614 permits) shows those areas ARE permitted
   (Lalbazar **26**, Soura **83**, Gulabagh **2**, Budgam **42**, Pampore **40**
   endpoints). The ≤0.40 overlap was against the engine's *rationalised* geometry,
   so the real signal is **rationalised-geometry-vs-reality divergence** (engine to
   reconcile), not informal routes. `is_informal` set to false on C2/C9/C11/C12/
   C14/C15/C18; each verdict carries a `correction_raw_permit_check` field.
2. **"Informal" reframed to "unmatched-to-rationalised-geometry (candidate)."**
   "Informal" against rationalised geometry could just be a differently-geocoded
   permit — a softer claim.
3. **"135 informal stops" → inventory enrichment.** The register is endpoint-only,
   so mid-route stops are "new" by construction; not "135 missing stops".

## Bugs found
- **Stale verdict join (low impact):** in the post-refine re-run, `calibration.py`
  ran before `validate_permits.py`, so the advisory `current_script_verdict` in the
  evidence packets came from the pre-refine `corridor_permit_match` (wrong IDs, e.g.
  C11/C16 tagged OUT_OF_AREA). The field is advisory only and was overridden in every
  verdict; the actual `corridor_permit_match.geojson` is correct. Fixed structurally
  by `src/run_all.py` (enforced stage order).
- **Segmentation artifact gap:** the wandering filter only triggers for `km < 3`, so
  C17 (74% dwell, 4.6 km/h, non-service) slipped through as a "corridor". It was
  already excluded from findings (flagged `artifact`); `segment.py` now also drops
  runs with `dwell_share > 0.65` or effective speed `< 6 km/h` (applies to future
  re-runs).

## Second pass — mining the long tail smartly (2026-07-02, `TAIL_MINING_REPORT.md`)
The 59% "long tail" (see coverage section above) was re-examined for two things a
strict robust-terminal requirement can miss, without touching the published 18
corridors: (A) tail runs that overlap an EXISTING corridor's path by shape but
didn't cluster into its exact terminal — pure evidence addition, no verdict changed
(C1 alone: 211→311 runs, 32→43 drivers). (B) path-shape clustering (complete-linkage,
so no single-linkage "blob" chaining) surfaced 30 new Tier-2 candidates. Script-only
triage (study-area clip + plan overlap + raw-permit check) resolved 28 of the 30
automatically (17 out-of-area incl. the two biggest/most convincing-looking ones —
both turned out to be NH-44 traffic; 11 already match/partial-match the plan). Only
**2 candidates** needed an actual look — both reviewed inline, both plausible local
connectors in already-well-permitted areas (Budgam, Hazratbal), both too thin (2-3
drivers) to be actionable. Conclusion: a dedicated multi-agent framework for the tail
was not warranted at this data scale — script triage did the sorting, and the handful
that needed judgment got it directly.

## Honest positioning for the RTO
Lead with the **adoption-robust** wins: measured operating speeds + the speed
heatmap, and the set of engine routes **confirmed observed in reality**. Present
the divergence corridors as **geometry-reconciliation candidates** for the engine.
Do **not** publish frequency/demand from this data. Broader driver adoption is the
prerequisite before this could ever *drive* rationalisation.

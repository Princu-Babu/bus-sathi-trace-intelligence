# Corridor Analyst — plan (AI per corridor, hybrid, resumable)

_Status: **PLAN ONLY — not started.** Execution is inline, one corridor at a
time, Opus for all, highly resumable. Written 2026-07-01._

## Why (the honest reframe)
Our deterministic scripts **measure** well (geometry, moving speed ~21 km/h,
frequency, dwell, operating hours — reproducible). The brittleness on sparse data
is only in the **judgement** steps. So AI does judgement; scripts keep the
measurements. This mirrors the successful v3.4.4 route deep-dive (`ROUTE_DEEPDIVE
_LEDGER.csv`) — an analyst per unit, not a script re-checking our own numbers.

AI is used ONLY for: corridor↔permit matching, informal-vs-formal call,
per-corridor narrative, informal-stop judgement — grounded in a script-built
evidence packet + web. Metrics are never produced by the model.

## Locked decisions
- **Runner:** inline in a Claude Code session (no external API key). **One corridor
  at a time.**
- **Model:** Opus for every corridor (~55 support-gated: ≥5 runs, ≥2 drivers).
- **Depth (all four):** permit match + informal call · per-corridor narrative ·
  informal-stop judgement · web-grounded (JKRTC / known Kashmir routes).
- **Hard requirement:** extensive logs + append-only ledger so the work is
  **highly resumable if the machine shuts down** mid-run.

## Architecture — 3 phases
### Phase A — build evidence packets (script, cheap, run once)
`src/build_evidence.py` → for each support-gated corridor writes:
- `analyst/evidence/C<id>.json` — metrics (n_runs/drivers/days, moving/effective
  speed, dwell, operating-hours histogram), endpoint + waypoint **place names via
  Nominatim (reverse geocode, cached in `analyst/geocode_cache.json`)**, observed
  stops on the corridor, and a **recall-first shortlist of candidate permits**
  (top-K by ANY overlap — generous; the AI picks the right one), each with name +
  km + type.
- `analyst/evidence/C<id>.png` — rendered map: corridor + candidate permits + stops.
- `analyst/corridor_queue.csv` — ordered work list (id, n_runs, has_packet).
Deterministic + idempotent: re-running skips corridors whose packet exists.

### Phase B — analyst loop (inline, Opus, ONE at a time)
Repeat until queue exhausted:
1. `python src/next_corridor.py` → prints the next corridor **in the queue but NOT
   in the ledger** (this is the resume point).
2. Read `analyst/evidence/C<id>.json` + `.png`; web-research if the match is
   unclear (JKRTC timetable / known route / place check).
3. Produce the **verdict** (schema below), grounded ONLY in the packet + web.
4. **Atomic commit of one unit of work:**
   - write full reasoning+sources to `analyst/verdicts/C<id>.md` (the audit log),
   - append one row to `analyst/CORRIDOR_LEDGER.csv`,
   - update `analyst/PROGRESS.md` (done N/total, last id, timestamp).
   Only after all three does the corridor count as done → shutdown-safe.

### Phase C — aggregate (script)
`src/aggregate_corridors.py` → rolls the ledger into `CORRIDOR_FINDINGS.md`
(matched / informal / needs-review counts, strong informal list, stop
adjustments) and a clean geojson for the dashboard reality layer.

## Verdict schema (one JSON row per corridor, in the ledger)
```
corridor_id, od_description, matched_permit, matched_permit_id, match_confidence
  (high|med|low), is_informal (bool), plausible (bool), stops_verdict
  (which candidate stops look real vs layover), narrative (2-3 sentences),
  evidence_used (place names / permit names / web sources actually cited),
  data_quality_flags, needs_human_review (bool), analyst_model, ts
```

## Resumability protocol (explicit)
- Ledger is **append-only**; `corridor_id` is the key. Resume = queue minus ledger.
- Evidence packets persist on disk → Phase B never re-does Phase A work.
- Geocode + web lookups cached (`analyst/geocode_cache.json`) → no repeat cost.
- `PROGRESS.md` + `next_corridor.py` make the exact resume point obvious after a
  shutdown or a new session.
- Token care: packets are compact; one corridor per turn; no re-reading finished
  verdicts.

## Honesty / grounding guards
- Model reasons only over the packet + cited web; **no invented permits/roads**.
- Deterministic metrics stay authoritative; AI never overwrites a measured number.
- Every verdict lists `evidence_used`; low confidence → `needs_human_review=true`.
- Reproducibility caveat recorded: LLM verdicts vary; the ledger + verdict files
  are the versioned record.
- Support-gated (≥5 runs, ≥2 drivers); thinner corridors explicitly excluded, not
  guessed.

## Deliverables
`analyst/CORRIDOR_LEDGER.csv` · `analyst/verdicts/*.md` · `CORRIDOR_FINDINGS.md`
· dashboard-ready geojson. Scripts: `build_evidence.py`, `next_corridor.py`,
`aggregate_corridors.py`.

## NOT started
No corridor analysed yet. First execution step will be Phase A
(`build_evidence.py`), then the Phase B loop one corridor at a time.

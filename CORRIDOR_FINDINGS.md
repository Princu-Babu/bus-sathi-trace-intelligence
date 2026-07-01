# Corridor findings — observed corridors judged by AI, one at a time

_Method: scripts MEASURE (geometry, speed, frequency); an AI analyst (Opus, one corridor at a time) JUDGES the permit match / informal call / plausibility, grounded in a per-corridor evidence packet + web. 18 support-gated corridors (≥5 runs, ≥2 drivers). Per-corridor audit trail in `analyst/verdicts/`._

## Tally

- **matched**: 7
- **partial**: 8
- **informal**: 0
- **out_of_area**: 2
- **artifact**: 1

## Matched to permits

| C | O→D | permit | conf |
|---|---|---|---|
| C1 | Soura ↔ Maisuma / Lal Chowk (central Srinagar) via Munawar Abad and the old city — the N–S city spine. Busiest corridor in the dataset. | FDR-050 Soura to Lalchowk | high |
| C4 | Soura ↔ Nowgam (Srinagar railway station) via Dal Gate / Munawar Abad. A north–south city route. | FDR-262 Soura to Railway Station | high |
| C5 | Pampore (Pulwama) ↔ Sonwar Bagh / central Srinagar, via Pantha Chowk. A Pampore–Srinagar corridor on the SE approach. | FDR-370 Srinagar to Pampore | medium |
| C6 | Magarmal Bagh / central Srinagar ↔ Pampore (Pulwama) via Lasjan and Pantha Chowk. | FDR-370 Srinagar to Pampore | medium |
| C7 | Nawa Kadal / Qamarwari (NW Srinagar) ↔ Zoonimar (near Soura, N Srinagar). A NW–N city cross-route. | FDR-270 Soura to Qamarwari | medium |
| C8 | Magarmal Bagh / Jehangir Chowk ↔ Safa Kadal via Karan Nagar. A short central-Srinagar route. | FDR-575 Safakadal to Jehangir Chowk | high |
| C16 | Magarmal Bagh / Jehangir Chowk (central Srinagar) ↔ Narbal (Budgam, on Gulmarg Road) via Qamarwari. | FDR-455 Narbal to Jehangir Chowk | high |

## Findings — in-area corridors that don't match the RATIONALISED geometry

### Geometry divergence, NOT under-permitting  (corrected 2026-07-02)
A raw-permit check (`E:/kash/existing-routes.csv`, 614 permits) shows these areas ARE permitted — **Lalbazar 26, Soura 83, Gulabagh 2, Budgam 42, Pampore 40** permit endpoints; smaller mahallas (Nowshera/Zoonimar/Ellahibagh) are traversed under major endpoint names. The ≤0.40 overlap is against the engine's **rationalised** route geometry, so the real signal is that **the rationalised geometry DIVERGES from observed reality** on these corridors (the engine should reconcile its geocoding/consolidation there) — **NOT** that they are informal/unpermitted. The earlier 'under-permitted cluster' reading is RETRACTED. These corridors are listed as geometry-reconciliation candidates:

- **C2** (150 runs / 12 drivers): Soura ↔ Nowshera via Lal Bazar (NE old-city Srinagar), with an eastern arm toward Nishat/Harwan that partly follows the SSCL Parimpora–Harwan e-bus alignment.  _(review: True)_
- **C9** (32 runs / 7 drivers): Nowshera ↔ Ellahibagh via Lal Bazar (NE Srinagar). A short local corridor in the same NE cluster as C2.  _(review: True)_
- **C11** (26 runs / 9 drivers): Zoonimar ↔ Gulab Bagh via Lal Bazar (N/NE Srinagar). Third corridor in the NE-Srinagar local cluster (C2, C9, C11).  _(review: True)_
- **C12** (22 runs / 9 drivers): Nowhatta (old city) ↔ Karan Nagar (SMHS / Medical College area) via Chotta Bazar / Medical College Road. Short central hospital-access corridor.  _(review: True)_
- **C13** (15 runs / 2 drivers): Karan Nagar ↔ Nawa Kadal via Noor Bagh (NW Srinagar, Qamarwari area).  _(review: True)_
- **C14** (9 runs / 3 drivers): Batamaloo (main Srinagar terminal) ↔ Budgam / Badgam (Budgam district HQ) via Peerbagh.  _(review: True)_
- **C15** (7 runs / 4 drivers): Rambagh (SW-central Srinagar) ↔ Ellahibagh (NE) via Rainawari — a long cross-city diagonal along the Dal-east side.  _(review: True)_
- **C18** (5 runs / 2 drivers): Sadrebal ↔ Gulab Bagh via Nowshera (N/NE Srinagar). Part of the NE-Srinagar local cluster.  _(review: True)_

## Out of area (excluded)
- **C3**: Udhampur ↔ Chenani on NH-44 (Chenani–Nashri / Dr. S.P. Mookerjee tunnel corridor), Udhampur district — JAMMU division.
- **C10**: Batote ↔ Mera on NH-44 via Baglihar, Ramban district — JAMMU division (Srinagar–Jammu highway).

## Non-service artifacts (excluded)
- **C17**: Short (3.3 km) near-stationary activity around the Pampore terminal (both endpoints within ~1.4 km of Pampore; the 'Srinagar' geocode is a mislabel of a point next to Pampore).

## Honest caveats
- App adoption is partial (~180 drivers) → observed frequency is a LOWER BOUND, not real headway; implied headways are omitted from claims.
- Some corridors have thin support (2–4 drivers) — flagged per-verdict as tentative.
- 'Informal' = observed but no matching permit; a candidate for RTO confirmation, not an assertion of illegality.
- AI verdicts vary between runs; the per-corridor files are the versioned record.
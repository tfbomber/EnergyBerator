# Neuss `buildings.parquet` — Duplicate `building_id` Root-Cause Analysis

**Date:** 2026-07-11
**Scope:** `data/buildings.parquet` (Neuss only)
**Verdict:** 🐞 **Pipeline bug** — not intentional boundary handling.
**Status:** ✅ **FIXED (2026-07-11)** — see [Section 7](#7-fix-applied-2026-07-11) below.

---

## 1. Symptom

`data/buildings.parquet` has 27,681 rows but only 18,559 unique `building_id`.
**12,157 rows carry a `building_id` that appears more than once** (3,035 distinct ids):

| repetitions | # of building_ids | rows |
|---|---|---|
| 4× | 3,018 | 12,072 |
| 5× | 17 | 85 |
| **total** | **3,035** | **12,157** |

Example — `OSM_97080810` appears five times:

| segment_id | geometry | postal_code |
|---|---|---|
| NEUSS_PLZ41464 | `POINT (6.7548144 51.1775612)` | 41464 |
| NEUSS_PLZ41462 | `POINT (6.7548144 51.1775612)` | 41462 |
| NEUSS_PLZ41466 | `POINT (6.7548144 51.1775612)` | 41466 |
| NEUSS_PLZ41468 | `POINT (6.7548144 51.1775612)` | 41468 |
| NEUSS_PLZ41469 | `POINT (6.7548144 51.1775612)` | 41469 |

The five rows are one physical building (identical centroid) cloned once per PLZ segment, each clone stamped with a **different `postal_code` equal to that segment's PLZ**.

---

## 2. Evidence

1. **Duplication is confined to 5 PLZ segments only:** 41462, 41464, 41466, 41468, 41469.
   Segments 41460 / 41470 / 41472 and every non-PLZ pilot segment (`ALLERHEILIGEN_PILOT_SEG_01`, `NEUSS_DENSE_01`, `NEUSS_OLD_TOWN_01`, `NEUSS_SUBURBAN_01`, `NEUSS_VILLA_01`) have **zero** shared building_ids.

2. **41462 / 41466 / 41468 / 41469 share the *exact same* 3,035-building set** (full 4-way intersection = 3,035):

   | segment | total building_ids | in shared intersection | unique to segment |
   |---|---|---|---|
   | NEUSS_PLZ41462 | 7,021 | 3,035 | 3,986 |
   | NEUSS_PLZ41466 | 4,205 | 3,035 | 1,170 |
   | NEUSS_PLZ41468 | 4,843 | 3,035 | 1,808 |
   | NEUSS_PLZ41469 | 3,934 | 3,035 | 899 |
   | NEUSS_PLZ41464 | 965 | 17 | 948 |

3. **All copies are geometrically identical:** for all 3,035 duplicated ids, `nunique(geometry) == 1`, and all 12,157 duplicated rows are `POINT`.

4. **`postal_code` is fabricated per copy:** #distinct postal_code == #segments (4 for the 4× dups, 5 for the 5×). The postal code is not the building's real PLZ — it is whatever segment the clone landed in.

5. **The discriminating factor is a missing `addr:postcode`.** The 3,035 shared buildings are **63.6% un-addressed** (empty `street`); the buildings *unique* to a segment are **99.5% addressed** (only 0.5% empty street). Buildings with a real address are routed to one segment; address-less buildings get cloned into all of them.

---

## 3. Root cause — `scripts/extract_osm_buildings_by_plz.py`

Three interacting defects produce the clones:

### A. Identical, city-wide bounding boxes (primary)
`PLZ_BBOX` (lines 64–73) gives four PLZ the **same oversized box covering all of Neuss**, while the other PLZ get tight neighborhood boxes:

```python
"41460": (51.180, 6.660, 51.220, 6.720),   # tight
"41462": (51.100, 6.600, 51.250, 6.800),   # ← whole-city box
"41466": (51.100, 6.600, 51.250, 6.800),   # ← identical
"41468": (51.100, 6.600, 51.250, 6.800),   # ← identical
"41469": (51.100, 6.600, 51.250, 6.800),   # ← identical
"41470": (51.125, 6.620, 51.165, 6.700),   # tight
```
Each Overpass query for these four PLZ therefore returns the **same city-wide set of ways**.

### B. Fallback PLZ stamping (amplifier)
`elements_to_rows` (lines 133–142) skips a building only when it carries a *contradicting* `addr:postcode`. A building with **no** postcode tag is kept and stamped with the target PLZ:

```python
if postal_code and postal_code.strip() != plz:   # has postcode, wrong PLZ -> skip
    continue
if not postal_code:                               # no postcode -> keep, stamp target PLZ
    postal_code = plz
```
So every address-less residential way returned by the city-wide query is kept for **each** of the four PLZ.

### C. Cross-PLZ dedup gap (why it wasn't caught)
`deduplicate_against_existing` (lines 193–204, called per-PLZ at line 239) only removes ids already present in the **pre-run** `buildings.parquet` snapshot. Within a single run it never dedupes across PLZ, and `all_new_rows` accumulates every PLZ's rows before one final concat (lines 247–260). The same address-less building extracted under 41462 and again under 41466 is absent from the pre-run snapshot both times, so **both survive**.

**Net effect:** every address-less residential building in Neuss is returned by all four identical-bbox queries → kept via the fallback branch → stamped with each segment's PLZ → never de-duplicated ⇒ **4 clones** (or **5**, if it also falls inside the tight 41464 box).

### Why 41460 / 41470 / 41472 escaped
- **41470** was run separately on 2026-04-12 (`TARGET_PLZ = {"41470": ...}`, lines 230–231) **after** the other PLZ were already persisted, so dedup against the now-populated snapshot removed the shared buildings.
- **41460 / 41464 / 41472** have tight bboxes, so they only catch buildings actually in their neighborhood (41464's box happens to overlap 17 of the shared buildings → the 17 five-way dups).

---

## 4. Why it is **not** "buildings near a segment boundary"

- A boundary building would appear in **at most 2** adjacent PLZ — never 4–5.
- The four co-duplicating PLZ are scattered across the whole city and share **no common boundary**: Furth (41462, NW), Reuschenberg/Weckhoven (41466, SE), Grimlinghausen/Gnadental (41468, S), Norf/Erfttal (41469, far S). One building cannot border all four.
- Each clone's `postal_code` is **fabricated** (= segment PLZ), not the building's real PLZ.
- Every clone shares **one identical centroid** — it is the same record duplicated, not distinct near-boundary buildings.

---

## 5. Downstream impact

- **Inflated building counts** for 41462/41466/41468/41469. E.g. 41462 reports 7,021 building_ids but 3,035 are shared clones; only 3,986 are genuinely its own. Any per-segment density / adoption denominator / roof-yield aggregation that counts building rows **over-counts** by up to the shared ~3,035.
- **`postal_code` is unreliable** on the 12,157 duplicated rows (fabricated to match the segment).
- The polygon backfill (`scripts/backfill_neuss_building_polygons.py`, run 2026-07-11) does **not** fix this — it upgrades geometry *per building_id*, so it correctly copies the same real footprint onto all clones. The **row-count inflation remains** until the duplicates are collapsed.

---

## 6. Recommended fix (⚠️ not applied — this document is investigate-and-document only)

1. Replace the four identical city-wide bboxes with tight per-PLZ boxes, or filter by a real PLZ polygon instead of a bbox.
2. Drop the "no postcode → stamp target PLZ" fallback. Route address-less buildings to a single `NEUSS_OSM_GENERAL` bucket, exactly as `generate_augsburg_buildings.py` already does with `AUGSBURG_OSM_GENERAL`.
3. Add **cross-PLZ dedup within a run**: dedupe accumulated `all_new_rows` on `building_id`, keeping the copy whose real `addr:postcode` matches, else one deterministic copy.
4. One-off remediation of the existing file: collapse to one row per `building_id` (prefer the copy with a genuine `addr:postcode`; otherwise a single canonical segment), and/or null out the fabricated `postal_code` on the clones.

---

*Reproduce:* the counts above come from `data/buildings.parquet` grouped by `building_id` / `segment_id`; the source defects are in `scripts/extract_osm_buildings_by_plz.py` at the line numbers cited.

---

## 7. Fix applied (2026-07-11)

Implemented per `.ai/implementation_plan_neuss_fix.md` (territoryai repo, sibling to this
one). Full before/after numbers: `scratch/neuss_rebuild_phase1.md` and
`scratch/neuss_phase2_progress.md` in the territoryai repo.

**Approach — rebuild from real per-feature OSM tags, Augsburg-strict (recommendation #1
and #2 from Section 6, adapted):**

1. **`scripts/build_neuss_buildings_from_geojson.py`** (new) rebuilds 7 of the 8 real
   Neuss PLZ (41460/41462/41464/41466/41468/41469/41472) in a **single pass** over the
   already-fetched `data/sources/buildings/osm_overpass/2026-03-15/neuss_osm_buildings_normalized.geojson`
   snapshot (93,759 real polygon features), modeled directly on the proven-good
   `generate_augsburg_buildings.py`. Structurally eliminates all three defects in
   Section 3: single pass ⇒ no repeat whole-city queries; **requires a real
   `addr:street` AND `addr:postcode`** on every kept feature, dropping (never
   fabricating a postcode for) address-less buildings; single-pass `drop_duplicates`
   makes cross-PLZ duplication structurally impossible. Also adds a mandatory
   point-in-polygon filter against `config/boundaries/neuss_admin_boundary.geojson` to
   exclude ~14,500 leaked Düsseldorf-postcode buildings the raw geojson's bbox pull
   swept in. Output: `data/buildings_neuss_rebuilt.parquet` (18,047 rows, 0 duplicate
   building_id, 0 fabricated postcode).
2. **PLZ 41470 is entirely absent from the source geojson snapshot** (a source-data gap
   in the 2026-03-15 fetch, not a pipeline bug). Recovered separately:
   **`scripts/build_neuss_buildings_final.py`** (new) takes the 1,498 real
   `NEUSS_PLZ41470` rows already in `data/buildings.parquet` (extracted as a one-off run
   on 2026-04-12, which happened to escape the cross-PLZ dedup gap because it ran after
   the other PLZ were already persisted) and merges them in, after dropping 4 of the
   1,498 that turned out to have a null street tag (same D2 "must have a real street"
   bar applied everywhere else here) and tagging the kept 1,494 with a distinct
   `geometry_source='LEGACY_OVERPASS_POINT_41470'` marker (point geometry, not the
   rebuild's polygon geometry — provenance stays visible). Combined output:
   `data/buildings_neuss_final.parquet`, **19,541 rows, 0 duplicate building_id, all 8
   PLZ present**.
3. **`scripts/swap_neuss_buildings.py`** (new) backed up the pre-fix `buildings.parquet`
   to `data/backups/buildings.parquet.pre_neuss_fix_2026-07-11` (27,681 rows), then
   replaced only the 8 `NEUSS_PLZ*`-segment rows with the final 19,541-row set — leaving
   931 unrelated rows (`ALLERHEILIGEN_PILOT_SEG_01` pilot segment + 4 `NEUSS_*` typology
   pilot segments, none of which are covered by the PLZ-based extraction) untouched.
   `data/buildings.parquet` is now **20,472 rows total** (19,541 Neuss 8-PLZ + 931
   preserved out-of-scope rows).
4. This script (`extract_osm_buildings_by_plz.py`) is **deprecated** (module-level
   `DeprecationWarning` + doc-block added at the top) but kept for historical reference.
   Do not run it again.

**Result:** building-weighted street-match rate against the territoryai ranking table
went from **58.7% → 87.8%** (all 8 PLZ; the 7-PLZ-only rebuilt subset alone reached
88.3%, since PLZ 41470's recovered legacy data matches at a lower ~82% and pulls the
blended full-city figure down slightly — still a +29 point improvement overall).
**Residual, not a rebuild defect**: a handful of real streets (concentrated in PLZ
41468, e.g. Rheinfährstraße/208 buildings) are absent from the territoryai ranking
table itself, not mis-extracted here — see the audit report for the full list.

**One benign, investigated side effect**: 82 building_ids are now shared between the new
`NEUSS_PLZ41469` rows and the untouched `ALLERHEILIGEN_PILOT_SEG_01` pilot segment (a
small, non-PLZ, neighborhood-scoped pilot extraction predating the PLZ-based segments).
In all 82 cases the Allerheiligen copy has null street/postcode/lat/lon and the new
NEUSS_PLZ41469 copy has full real attributes — i.e. this is the comprehensive rebuild
correctly picking up a pocket the old buggy per-PLZ bbox extraction missed, not a
reintroduction of the bug pattern above (which was the same building cloned across
multiple *co-equal PLZ* segments with a fabricated postcode each).
`core/building_universe.py`'s `count_buildings_per_segment` counts rows via a
per-`segment_id` `value_counts()`, so this cross-namespace overlap does not inflate or
corrupt any single segment's building count.

**Not yet done (tracked separately)**: recomputing `field_04` PV-density denominators
and the Neuss segment-level `street_ranking_v1` rows from the corrected building counts,
and re-merging those into the territoryai repo's copy — see
`scratch/neuss_phase2_progress.md` (territoryai repo) for status.

---

## 8. field_01/field_02/field_04 recompute — Option 2 executed (2026-07-11)

Per `territoryai/.ai/implementation_plan_neuss_layer2_rearch.md` (wudiplan/wudiexecute
cycle). Backups of every touched parquet: `data/backups/*.pre_layer2_rearch_2026-07-11`.

**What changed:**
1. `scripts/patch_field_pipelines_point_geometry.py` — `field_02` patch scope shrunk to
   `{NEUSS_PLZ41470}` only (the other 7 PLZ are real POLYGON now and get real Stage1/2
   classification instead). `field_01` patch scope **expanded** to all 8 Neuss PLZ,
   computing utilization directly from `buildings_df['building_type']` (bypassing
   `field_01_roof_potential.py`'s own field_02-join path — see below) with **real
   measured polygon area** for the 7 POLYGON PLZ and the existing footprint proxy for
   POINT-only `NEUSS_PLZ41470`.
2. `fields/field_02_building_type.py` — `POINT_SEGS` shrunk to `{NEUSS_PLZ41470}`.
   **Bug found and fixed during this run**: the `__main__` merge logic that preserves
   rows for segments not recomputed this run was keyed off `POINT_SEGS` instead of "the
   actual set of segments in this run's `buildings_adj`" — harmless when `buildings.parquet`
   only ever held Neuss segments, but **silently wiped all 47,224 Augsburg+Kaarst rows**
   the first time this script ran after those cities were merged into the shared
   `field_02_building_type.parquet` (confirmed, then restored from backup and re-run with
   the fix — see `fields/field_02_building_type.py`'s `recomputed_segments` variable).
3. `fields/field_04_pv_adoption.py` — refreshed `segment_buildings` for all 8
   `REAL_GROUNDED_SEGMENTS` entries to the corrected Stage A/B counts. `plz_buildings` /
   `morphology_factor` deliberately left untouched (no documented derivation formula;
   out of scope, see plan D2).
4. **Deliberately NOT touched**: `fields/field_01_roof_potential.py`'s shared
   `utilization_factors` dict. It is keyed to `detached/semi/rowhouse/apartment/unknown`
   but `field_02_building_type.py`'s real Stage1/2 output vocabulary is
   `SFH_CONFIRMED/MFH_CONFIRMED/SFH_WEAK/MFH_SUSPECT/UNCERTAIN` — none of which match,
   so every building silently falls to the 0.20 default. **Confirmed live in production**:
   all 14 `AUGSBURG_OSM_*` rows in `field_01_roof_potential.parquet` are exactly `0.2000`.
   Fixing the shared dict would also recompute Augsburg's (14 segments) and Kaarst's
   (1 segment) already-shipped ranks — out of scope for this round, needs its own
   sign-off (spawned separately as `task_40667fd6`, territoryai session).

**Before/after (8 Neuss segments, ranked by new `final_score`):**

| PLZ | roof_raw old→new | sfh_confirmed_share old→new | pv_coverage old→new | final_score old→new | rank old→new |
|---|---|---|---|---|---|
| 41472 | 0.4000→0.2450 | 0.7938→0.6271 | 0.7183→0.3698 | 0.6420→0.5970 | 1→1 |
| 41466 | 0.3068→0.3123 | 0.5765→0.6308 | 0.7836→0.4027 | 0.4774→0.5355 | 3→2 |
| 41464 | 0.3566→0.2772 | 0.1513→0.6146 | 0.8210→0.3605 | 0.2894→0.5022 | **7→3** |
| 41468 | 0.3189→0.2462 | 0.6056→0.4187 | 0.7974→0.3911 | 0.4992→0.5002 | 2→4 |
| 41470 | 0.3731→0.2738 | 0.0000→0.2120 | 0.1709→0.5000 | 0.4218→0.4376 | 6→5 |
| 41469 | 0.3020→0.2532 | 0.5465→0.2336 | 0.7766→0.4128 | 0.4574→0.3926 | 4→6 |
| 41462 | 0.3003→0.2836 | 0.6792→0.3542 | 0.8677→0.2417 | 0.4360→0.3316 | 5→7 |
| 41460 | 0.2813→0.2212 | 0.3270→0.3233 | 0.9437→0.1947 | 0.2430→0.2522 | 8→8 |

Full column set (incl. `priority_score`, `pv_coverage_score`, `sfh_confirmed_share`):
`output/neuss_phase2/before_after_option2_2026-07-11.csv`.

**Reading the reshuffle** (expected, not a regression — see plan Risk R2):
- `pv_coverage_score` drops broadly because `field_04`'s old hardcoded `segment_buildings`
  were stale/wrong in both directions (41460 was undercounted 844 vs corrected 1682;
  41462 was inflated 7021 vs corrected 3010 by the duplicate-building-id bug) — the E3
  allocation ratio (`segment_buildings / plz_buildings`) shifts accordingly.
- 41464 jumps rank 7→3: its old `segment_buildings` (863) was the most severely
  undercounted of all 8 PLZ vs the corrected 3599 (4.2×), which fed into both `field_04`
  and (via real polygon area replacing the point-footprint-proxy) `field_01`.
- 41462 drops rank 5→7: its old count (7021) was inflated ~2.3× by the very
  duplicate-building-id bug this whole rebuild fixed (Section 3); the corrected 3010
  brings its PV-density and roof-area signals back in line with its true size.
- Rank 1 (41472) and rank 8 (41460) are unchanged — the biggest and smallest opportunity
  segments stay the biggest and smallest.

**Re-merge into territoryai**: `scripts/merge_neuss_layer2_into_territoryai.py` (new,
modeled on `scripts/merge_augsburg_into_territoryai.py`).

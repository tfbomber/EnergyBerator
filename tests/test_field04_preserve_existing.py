"""
tests/test_field04_preserve_existing.py
=========================================
Regression test for the field_04_pv_adoption.py::run() silent-overwrite bug
(fixed 2026-07-12).

Bug: run() wrote its output parquet with a bare df_out.to_parquet() containing
ONLY the segments in REAL_GROUNDED_SEGMENTS at call time. Any other city's rows
already on disk (added by their own run_<city>_fields.py driver, which mutates
REAL_GROUNDED_SEGMENTS in-process before calling run()) were silently wiped on
every run — in all 3 directions: a plain Neuss run wiped Augsburg+Kaarst;
run_kaarst_fields.py wiped Augsburg (run() writes before the driver re-appends);
run_augsburg_fields.py wiped Kaarst. Confirmed for real: the shipped parquet
held only the 8 Neuss rows despite both city drivers having run previously.
Same root-cause class as field_02_building_type.py's 2026-07-11 fix.

Exercises run()'s write path directly, with the MaStR CSV read and
REAL_GROUNDED_SEGMENTS mocked out, so it's fast/hermetic — never touches the
real 646MB source CSV or the real data/fields/field_04_pv_adoption.parquet.
"""

import os
import sys
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fields import field_04_pv_adoption as f04

_TEST_SEGMENT = {
    "plz": "41470", "segment_buildings": 100, "plz_buildings": 1000,
    "morphology_factor": 1.0, "city": "Neuss", "persistent_id": "TEST",
}


@pytest.fixture
def isolated_run(tmp_path, monkeypatch):
    """Point run() at a throwaway parquet path and a fast fake MaStR loader,
    so tests never touch real production data or the 646MB source CSV."""
    tmp_parquet = tmp_path / "field_04_pv_adoption.parquet"
    monkeypatch.setattr(f04, "OUTPUT_PARQUET", tmp_parquet)
    monkeypatch.setattr(f04, "OUTPUT_AUDIT_DIR", tmp_path / "runs")

    def fake_load_mastr_plz(plz):
        # 10 fabricated active residential rows — clears MIN_PLZ_RECORDS (5).
        return pd.DataFrame({
            "unit_id": [f"U{i}" for i in range(10)],
            "plz": [plz] * 10,
            "kwp": [5.0] * 10,
            "operational_status": ["35"] * 10,
        })
    monkeypatch.setattr(f04, "load_mastr_plz", fake_load_mastr_plz)

    original_segments = dict(f04.REAL_GROUNDED_SEGMENTS)
    yield tmp_parquet
    f04.REAL_GROUNDED_SEGMENTS.clear()
    f04.REAL_GROUNDED_SEGMENTS.update(original_segments)


def _seed_existing_parquet(path, segment_ids):
    """Simulate a prior run() call (e.g. a different city's driver) having
    already written rows for segments this test's run() will not recompute."""
    df = pd.DataFrame([
        {"segment_id": sid, "field_id": "field_04", "field_value": 0.5,
         "confidence": 0.45, "source": "PLZ_ALLOCATION_E3", "notes": "seed"}
        for sid in segment_ids
    ])
    df.to_parquet(path, index=False)


class TestPreserveNonRecomputedSegments:
    """
    Core regression: run() must not wipe rows for segments outside its own
    REAL_GROUNDED_SEGMENTS at call time.
    """

    def test_other_city_rows_survive_a_run(self, isolated_run):
        tmp_parquet = isolated_run
        _seed_existing_parquet(tmp_parquet, ["AUGSBURG_OSM_86150", "KAARST_OSM_41564"])

        f04.REAL_GROUNDED_SEGMENTS.clear()
        f04.REAL_GROUNDED_SEGMENTS["NEUSS_PLZ41470"] = dict(_TEST_SEGMENT)
        f04.run()

        on_disk = pd.read_parquet(tmp_parquet)
        ids = set(on_disk["segment_id"])
        assert "AUGSBURG_OSM_86150" in ids, "pre-existing Augsburg row was wiped"
        assert "KAARST_OSM_41564" in ids, "pre-existing Kaarst row was wiped"
        assert "NEUSS_PLZ41470" in ids, "this run's own recomputed row is missing"
        assert len(on_disk) == 3

    def test_recomputing_a_segment_replaces_not_duplicates_its_row(self, isolated_run):
        tmp_parquet = isolated_run
        _seed_existing_parquet(tmp_parquet, ["NEUSS_PLZ41470"])  # stale prior row

        f04.REAL_GROUNDED_SEGMENTS.clear()
        f04.REAL_GROUNDED_SEGMENTS["NEUSS_PLZ41470"] = dict(_TEST_SEGMENT)
        f04.run()

        on_disk = pd.read_parquet(tmp_parquet)
        rows = on_disk[on_disk["segment_id"] == "NEUSS_PLZ41470"]
        assert len(rows) == 1, "recomputing a segment must replace, not duplicate, its row"

    def test_returned_dataframe_stays_recomputed_only(self, isolated_run):
        """run()'s return value must stay recomputed-only — run_<city>_fields.py
        drivers filter this return value by segment_id to extract their own
        city's rows before appending; if preserved rows leaked into it, a
        driver could misfile another city's rows under its own append call."""
        tmp_parquet = isolated_run
        _seed_existing_parquet(tmp_parquet, ["AUGSBURG_OSM_86150"])

        f04.REAL_GROUNDED_SEGMENTS.clear()
        f04.REAL_GROUNDED_SEGMENTS["NEUSS_PLZ41470"] = dict(_TEST_SEGMENT)
        returned = f04.run()

        assert set(returned["segment_id"]) == {"NEUSS_PLZ41470"}

    def test_first_ever_run_with_no_prior_file(self, isolated_run):
        """No pre-existing parquet (first-ever run) must not crash the preserve logic."""
        tmp_parquet = isolated_run
        f04.REAL_GROUNDED_SEGMENTS.clear()
        f04.REAL_GROUNDED_SEGMENTS["NEUSS_PLZ41470"] = dict(_TEST_SEGMENT)
        f04.run()

        on_disk = pd.read_parquet(tmp_parquet)
        assert set(on_disk["segment_id"]) == {"NEUSS_PLZ41470"}

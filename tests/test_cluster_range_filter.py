"""
test_cluster_range_filter.py
============================
Regression test for the two new helper functions in generate_foundation_layer.py:
  - _parse_housenumber_numeric()
  - _count_cluster_buildings()

Does NOT call Overpass. Pure unit tests against known inputs.
Tests cover German housenumber formats, edge cases, and the Tannenweg / Gladbacher
scenarios discovered during the data audit.
"""

import sys
sys.path.insert(0, r"D:\Stock Analysis\D-Energy Berater\d-ess-engine\scripts")

from generate_foundation_layer import _parse_housenumber_numeric, _count_cluster_buildings


def run_tests():
    passed = 0
    failed = 0

    def check(label, got, expected):
        nonlocal passed, failed
        if got == expected:
            print(f"  PASS  {label}")
            passed += 1
        else:
            print(f"  FAIL  {label}")
            print(f"        expected={expected!r}  got={got!r}")
            failed += 1

    # =========================================================
    # Part 1: _parse_housenumber_numeric
    # =========================================================
    print("=== Part 1: _parse_housenumber_numeric ===")
    check("integer only",         _parse_housenumber_numeric("5"),     5)
    check("integer + letter",     _parse_housenumber_numeric("5a"),    5)
    check("large + letter",       _parse_housenumber_numeric("407b"),  407)
    check("leading letter (1b)",  _parse_housenumber_numeric("1b"),    1)
    check("30c",                  _parse_housenumber_numeric("30c"),   30)
    check("spaces stripped",      _parse_housenumber_numeric(" 12a "), 12)
    check("non-numeric returns None", _parse_housenumber_numeric("abc"), None)
    check("empty string",         _parse_housenumber_numeric(""),      None)
    check("None input (str)",     _parse_housenumber_numeric("None"),  None)

    print()

    # =========================================================
    # Part 2: _count_cluster_buildings
    # =========================================================
    print("=== Part 2: _count_cluster_buildings ===")

    # --- Tannenweg scenario: range '1b - 7', all buildings WITHOUT housenumbers ---
    tannenweg_no_nr = [{"housenumber": "", "type": "semi_detached"}] * 45
    count, unaddressed, _ = _count_cluster_buildings(tannenweg_no_nr, "1b - 7")
    check("Tannenweg(no nr): cluster_count", count, 0)
    check("Tannenweg(no nr): unaddressed",   unaddressed, 45)

    # --- Tannenweg scenario: range '1b - 7', buildings WITH correct housenumbers ---
    # 14 DHH pairs (1a-7b) = 14 buildings within range, 31 outside (simulated)
    tannenweg_with_nr = (
        [{"housenumber": str(i) + s, "type": "semi_detached"} for i in range(1, 8) for s in ("a", "b")]  # 1a-7b = 14
        + [{"housenumber": str(i), "type": "rowhouse"} for i in range(8, 25)]  # 8-24 outside range
    )
    count, unaddressed, _ = _count_cluster_buildings(tannenweg_with_nr, "1b - 7")
    check("Tannenweg(w/ nr): cluster_count (1-7 only)", count, 14)
    check("Tannenweg(w/ nr): unaddressed",              unaddressed, 0)

    # --- Gladbacher Str scenario: range '400 - 407a', but all 339 buildings span whole street ---
    # Simulate 10 buildings in range 400-407, 329 buildings outside
    gladbacher_in  = [{"housenumber": str(i), "type": "rowhouse"} for i in range(400, 408)]  # 8 in range
    gladbacher_out = [{"housenumber": str(i), "type": "rowhouse"} for i in range(1, 330)]    # 329 out
    all_gladbacher = gladbacher_in + gladbacher_out
    count, unaddressed, _ = _count_cluster_buildings(all_gladbacher, "400 - 407a")
    check("Gladbacher(400-407a): cluster_count", count, 8)
    check("Gladbacher(400-407a): unaddressed",   unaddressed, 0)

    # --- Marienburger Str: range '30b - 30c' (min=30, max=30) ---
    marien_bldgs = (
        [{"housenumber": "30b", "type": "semi_detached"}]
        + [{"housenumber": "30c", "type": "semi_detached"}]
        + [{"housenumber": str(i), "type": "mfh"} for i in range(1, 30)]  # other units on street
    )
    count, unaddressed, _ = _count_cluster_buildings(marien_bldgs, "30b - 30c")
    check("Marienburger(30b-30c): cluster_count (only 30x)", count, 2)
    check("Marienburger(30b-30c): unaddressed",              unaddressed, 0)

    # --- Unparseable range ---
    bldgs = [{"housenumber": "5", "type": "detached"}] * 10
    count, unaddressed, _ = _count_cluster_buildings(bldgs, "unknown")
    check("Unparseable range returns None", count, None)

    # --- Empty building list ---
    count, unaddressed, _ = _count_cluster_buildings([], "1 - 10")
    check("Empty list: cluster_count", count, 0)
    check("Empty list: unaddressed",   unaddressed, 0)

    # --- Mixed: some with nr, some without ---
    mixed = (
        [{"housenumber": str(i), "type": "detached"} for i in range(1, 6)]   # 5 with nr, in range
        + [{"housenumber": str(i), "type": "detached"} for i in range(11, 16)] # 5 with nr, out of range
        + [{"housenumber": "",    "type": "detached"}] * 8                    # 8 no housenumber
    )
    count, unaddressed, _ = _count_cluster_buildings(mixed, "1 - 9")
    check("Mixed: cluster_count (1-9 only)", count, 5)
    check("Mixed: unaddressed (no nr)",      unaddressed, 8)

    # =========================================================
    print()
    print("=" * 50)
    total = passed + failed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("ALL TESTS PASSED - safe to run generate_foundation_layer.py")
    else:
        print("FAILURES DETECTED - do NOT run pipeline until fixed")
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)

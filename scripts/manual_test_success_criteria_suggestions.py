"""Zero-cost unit tests for core/success_criteria_suggestions.py (cross-project
evaluation item b.5, deferred design session, 2026-07-24). Pure functions,
no Streamlit, no API calls."""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.success_criteria_suggestions import (
    SECTOR_OPTIONS,
    MARKET_SIZE_BAND_OPTIONS,
    DEFAULT_SECTOR_KEY,
    DEFAULT_BAND_KEY,
    get_success_kill_criteria_suggestion,
)


def test_every_sector_resolves_to_a_nonempty_suggestion():
    for sector_key, _label in SECTOR_OPTIONS:
        result = get_success_kill_criteria_suggestion(sector_key, "unknown")
        assert result["success_criteria"].strip(), f"{sector_key}: empty success_criteria"
        assert result["kill_criteria"].strip(), f"{sector_key}: empty kill_criteria"


def test_every_band_substitutes_a_distinct_timeframe():
    results = {
        band_key: get_success_kill_criteria_suggestion("saas_software", band_key)["success_criteria"]
        for band_key, _label in MARKET_SIZE_BAND_OPTIONS
    }
    assert len(set(results.values())) == len(MARKET_SIZE_BAND_OPTIONS), (
        "each band must produce a genuinely different suggestion text (different timeframe)"
    )


def test_unrecognized_sector_falls_back_to_default_not_error():
    result = get_success_kill_criteria_suggestion("not_a_real_sector", "unknown")
    assert result["sector_key"] == DEFAULT_SECTOR_KEY
    assert result["success_criteria"].strip()


def test_unrecognized_band_falls_back_to_default_not_error():
    result = get_success_kill_criteria_suggestion("saas_software", "not_a_real_band")
    assert result["band_key"] == DEFAULT_BAND_KEY
    assert result["success_criteria"].strip()


def test_general_other_fallback_sector_works():
    result = get_success_kill_criteria_suggestion("general_other", "small")
    assert result["success_criteria"].strip()
    assert result["kill_criteria"].strip()


def main():
    tests = [
        test_every_sector_resolves_to_a_nonempty_suggestion,
        test_every_band_substitutes_a_distinct_timeframe,
        test_unrecognized_sector_falls_back_to_default_not_error,
        test_unrecognized_band_falls_back_to_default_not_error,
        test_general_other_fallback_sector_works,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()

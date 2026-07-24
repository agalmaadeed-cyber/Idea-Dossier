"""Zero-cost unit tests for the b.6 fix (deferred design session, 2026-07-24):
an explicit, enforced ceiling on evidence_label for combined/merged fields in
core/uh_mapper.py -- currently C2 is the only such field in the entire
project. Pure Python, no LLM/API calls, no Streamlit.
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.uh_mapper import _write_field, parse_uh_report

SCRIPTS_DIR = Path(__file__).resolve().parent
FIXTURES = {
    "manager_productivity": SCRIPTS_DIR / "fixtures" / "uh_report_manager_productivity.md",
    "bakery": SCRIPTS_DIR / "fixtures" / "uh_report_bakery.md",
}


def test_c2_real_combined_write_still_succeeds_at_estimate():
    dossier_partial = {}
    warnings = []
    _write_field(
        dossier_partial, "C2", "solution text\nwhy pay text",
        "Combined from Unicorn Hunter labels: 'Proposed Solution' and 'Why Would the Customer Pay?'",
        "2026-07-24T00:00:00+00:00", warnings, is_combined=True,
    )
    assert warnings == []
    assert dossier_partial["solution"]["value"]["evidence_label"] == "ESTIMATE"


def test_combined_field_above_ceiling_raises():
    dossier_partial = {}
    warnings = []
    raised = False
    try:
        _write_field(
            dossier_partial, "C2", "solution text\nwhy pay text",
            "Combined from Unicorn Hunter labels: 'Proposed Solution' and 'Why Would the Customer Pay?'",
            "2026-07-24T00:00:00+00:00", warnings, is_combined=True, evidence_label="CONFIRMED",
        )
    except ValueError as e:
        raised = True
        assert "C2" in str(e)
        assert "ceiling" in str(e)
    assert raised, "a combined field assigned CONFIRMED must raise, not silently write"


def test_non_combined_field_unaffected_by_the_guard():
    dossier_partial = {}
    warnings = []
    # is_combined defaults False -- this must NOT raise even with a label
    # above the combined-field ceiling, proving the guard's scope is
    # correctly narrow (every existing non-combined call site is
    # completely unaffected by this fix).
    _write_field(
        dossier_partial, "A1", "some problem text", "Extracted from Unicorn Hunter report, label: 'Problem'",
        "2026-07-24T00:00:00+00:00", warnings, evidence_label="CONFIRMED",
    )
    assert dossier_partial["opportunity"]["problem"]["evidence_label"] == "CONFIRMED"


def test_real_fixtures_still_produce_estimate_c2_end_to_end():
    for name, path in FIXTURES.items():
        raw_markdown = path.read_text(encoding="utf-8")
        result = parse_uh_report(raw_markdown)
        c2 = result["dossier_partial"].get("solution", {}).get("value")
        if c2 is not None:
            assert c2["evidence_label"] == "ESTIMATE", f"{name}: C2 must still resolve to ESTIMATE after this fix"


def main():
    tests = [
        test_c2_real_combined_write_still_succeeds_at_estimate,
        test_combined_field_above_ceiling_raises,
        test_non_combined_field_unaffected_by_the_guard,
        test_real_fixtures_still_produce_estimate_c2_end_to_end,
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

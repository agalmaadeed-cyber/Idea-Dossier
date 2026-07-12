"""Zero-cost test of the live Dossier side-panel logic in app.py.

Reuses continue_interview() field_update output already captured in
scripts/manual_test_interview_only_output.txt, and run_research() output
already captured in scripts/fixtures/sample_research_output.json. Makes NO
API calls.

Tests pure logic only (build_dossier_skeleton, _apply_field_update_to_dossier,
_merge_research_leaves, _active_section, _sections_for_readiness) —
Streamlit rendering itself is verified separately via a live browser
smoke test.
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR.parent))
sys.path.insert(0, str(SCRIPTS_DIR))

import manual_test_assembly as ma  # noqa: E402  (reuses its JSON-block extractor)
from app import (  # noqa: E402
    _active_section,
    _apply_field_update_to_dossier,
    _merge_research_leaves,
    _sections_for_readiness,
    build_dossier_skeleton,
)
from core.field_registry import FIELD_REGISTRY, MANDATORY_FIELDS, MAX_WEIGHTED_SCORE  # noqa: E402
from core.readiness import compute_readiness_score  # noqa: E402

INTERVIEW_OUTPUT_TXT = SCRIPTS_DIR / "manual_test_interview_only_output.txt"
RESEARCH_FIXTURE = ma.FIXTURES_DIR / "sample_research_output.json"


def main():
    out = []

    out.append("=" * 70)
    out.append("STEP 1: build_dossier_skeleton()")
    out.append("=" * 70)
    dossier = build_dossier_skeleton()
    sections = dossier["sections"]

    total_fields = sum(len(fields) for fields in sections.values())
    all_unknown = all(
        leaf["value"] is None and leaf["evidence_label"] == "UNKNOWN"
        for fields in sections.values()
        for leaf in fields.values()
    )
    out.append(f"total fields: {total_fields} (expected 32): {total_fields == 32}")
    out.append(f"all fields UNKNOWN/None: {all_unknown}")
    out.append(f"section order: {list(sections.keys())}")
    assert total_fields == 32
    assert all_unknown

    out.append("\n" + "=" * 70)
    out.append("STEP 2: initial active section (no last_updated_field yet)")
    out.append("=" * 70)
    initial_active = _active_section(sections, None)
    first_mandatory_field = FIELD_REGISTRY[MANDATORY_FIELDS[0]]
    out.append(f"active section: {initial_active!r} (expected {first_mandatory_field['section']!r})")
    assert initial_active == first_mandatory_field["section"]

    out.append("\n" + "=" * 70)
    out.append("STEP 3: initial readiness (nothing filled)")
    out.append("=" * 70)
    readiness0 = compute_readiness_score(_sections_for_readiness(sections))
    out.append(json.dumps(readiness0, ensure_ascii=False, indent=2))
    assert readiness0["score_weighted"] == 0
    assert readiness0["mandatory_passed"] is False

    out.append("\n" + "=" * 70)
    out.append("STEP 4: apply a real captured field_update (B1, CONFIRMED)")
    out.append("=" * 70)
    interview_text = INTERVIEW_OUTPUT_TXT.read_text(encoding="utf-8")
    nested_updates = ma._extract_balanced_json_blocks_after_marker(interview_text, "--- field_update ---")
    b1_update, b2_update = nested_updates[0], nested_updates[1]

    updated_path = _apply_field_update_to_dossier(dossier, b1_update)
    out.append(f"field_updated: {b1_update['field_updated']!r} -> returned path: {updated_path!r}")
    assert updated_path == "customer_market.payer"
    leaf = sections["customer_market"]["payer"]
    out.append(f"stored leaf evidence_label: {leaf['evidence_label']} (expected CONFIRMED)")
    assert leaf["evidence_label"] == "CONFIRMED"

    out.append("\n" + "=" * 70)
    out.append("STEP 5: active section now follows last_updated_field")
    out.append("=" * 70)
    active_after_update = _active_section(sections, updated_path)
    out.append(f"active section: {active_after_update!r} (expected 'customer_market')")
    assert active_after_update == "customer_market"

    out.append("\n" + "=" * 70)
    out.append("STEP 6: readiness after B1 filled")
    out.append("=" * 70)
    readiness1 = compute_readiness_score(_sections_for_readiness(sections))
    out.append(json.dumps(readiness1, ensure_ascii=False, indent=2))
    assert readiness1["score_weighted"] == FIELD_REGISTRY["B1"]["weight"]

    out.append("\n" + "=" * 70)
    out.append("STEP 7: apply second captured field_update (B2, ASSUMPTION)")
    out.append("=" * 70)
    updated_path_2 = _apply_field_update_to_dossier(dossier, b2_update)
    out.append(f"field_updated: {b2_update['field_updated']!r} -> returned path: {updated_path_2!r}")
    assert updated_path_2 == "customer_market.user"
    out.append(f"stored evidence_label: {sections['customer_market']['user']['evidence_label']} (expected ASSUMPTION)")
    assert sections["customer_market"]["user"]["evidence_label"] == "ASSUMPTION"

    out.append("\n" + "=" * 70)
    out.append("STEP 8: invalid section/key edge case — must not crash")
    out.append("=" * 70)
    bad_update = {
        "field_updated": "opportunity.nonexistent_field",
        "value": {
            "value": "should never be written",
            "evidence_label": "CONFIRMED",
            "sources": [],
            "notes": "",
            "field_code": "X9",
            "filled_by": "interview_agent",
            "filled_at": "2026-01-01T00:00:00+00:00",
        },
    }
    result = _apply_field_update_to_dossier(dossier, bad_update)
    out.append(f"_apply_field_update_to_dossier() on bad section/key returned: {result!r} (expected None)")
    assert result is None
    out.append("No exception raised — guard clause holds.")

    out.append("\n" + "=" * 70)
    out.append("STEP 9: merge_research_into_skeleton() core (_merge_research_leaves)")
    out.append("=" * 70)
    fresh_dossier = build_dossier_skeleton()
    fresh_sections = fresh_dossier["sections"]
    research_fixture = json.loads(RESEARCH_FIXTURE.read_text(encoding="utf-8"))
    research_dossier_partial = research_fixture["dossier_partial"]

    merged, invalid = _merge_research_leaves(fresh_sections, research_dossier_partial)
    out.append(f"merged {len(merged)} paths (expected 18): {len(merged) == 18}")
    out.append(f"invalid paths: {invalid} (expected empty)")
    assert len(merged) == 18
    assert invalid == []

    leaf_a1 = fresh_sections["opportunity"]["problem"]
    out.append(f"opportunity.problem evidence_label: {leaf_a1['evidence_label']} (expected CONFIRMED)")
    out.append(f"opportunity.problem filled_by: {leaf_a1['filled_by']} (expected research_agent)")
    assert leaf_a1["evidence_label"] == "CONFIRMED"
    assert leaf_a1["filled_by"] == "research_agent"

    readiness_research = compute_readiness_score(_sections_for_readiness(fresh_sections))
    out.append(f"score_weighted after merge: {readiness_research['score_weighted']} (expected 24)")
    assert readiness_research["score_weighted"] == 24
    assert readiness_research["score_weighted"] <= MAX_WEIGHTED_SCORE

    out.append(
        "_merge_research_leaves has no code path that touches last_updated_field "
        "(by construction, not just by this test) — bulk research fills never trigger the highlight."
    )

    out.append("\n" + "=" * 70)
    out.append("STEP 10: _merge_research_leaves skips a mismatched path without raising")
    out.append("=" * 70)
    tampered_partial = json.loads(RESEARCH_FIXTURE.read_text(encoding="utf-8"))["dossier_partial"]
    tampered_partial["opportunity"]["nonexistent_field"] = {
        "value": "should never be written",
        "evidence_label": "CONFIRMED",
        "sources": [],
        "notes": "",
        "field_code": "X9",
        "filled_by": "research_agent",
        "filled_at": "2026-01-01T00:00:00+00:00",
    }
    dossier_2 = build_dossier_skeleton()
    merged_2, invalid_2 = _merge_research_leaves(dossier_2["sections"], tampered_partial)
    out.append(f"merged: {len(merged_2)} (expected 18), invalid: {invalid_2} (expected ['opportunity.nonexistent_field'])")
    assert len(merged_2) == 18
    assert invalid_2 == ["opportunity.nonexistent_field"]
    out.append("No exception raised — guard clause holds for bulk research merge too.")

    text = "\n".join(out)
    print(text)

    report_path = SCRIPTS_DIR / "manual_test_side_panel_output.txt"
    report_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

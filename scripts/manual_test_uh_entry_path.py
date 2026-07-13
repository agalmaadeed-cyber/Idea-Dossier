"""Zero-cost test of the app.py glue for the Unicorn Hunter entry path:
_merge_research_leaves (reused for uh_mapper's dossier_partial too),
_flatten_dossier_partial_to_values, and _merge_dossier_partials.

Pure Python, no Streamlit session_state, no API calls — these three
helpers were deliberately kept pure (no st.session_state reads/writes) so
they're testable standalone.
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR.parent))

from app import (  # noqa: E402
    _flatten_dossier_partial_to_values,
    _merge_dossier_partials,
    _merge_research_leaves,
    build_dossier_skeleton,
)
from core.field_registry import FIELD_REGISTRY  # noqa: E402
from core.uh_mapper import parse_uh_report  # noqa: E402

FIXTURE = SCRIPTS_DIR / "fixtures" / "uh_report_bakery.md"

EXPECTED_UH_PATHS = {
    "opportunity.problem", "opportunity.current_solutions", "customer_market.payer",
    "solution.description", "solution.value", "solution.usage",
    "business_model.pricing", "business_model.revenue_potential", "business_model.channels",
    "success_definition.risks", "success_definition.assumptions",
}


def main():
    out = []

    out.append("=" * 70)
    out.append("STEP 1: parse_uh_report() on the bakery fixture")
    out.append("=" * 70)
    raw_markdown = FIXTURE.read_text(encoding="utf-8")
    uh_result = parse_uh_report(raw_markdown)
    uh_dossier_partial = uh_result["dossier_partial"]
    out.append(f"uh_mapper filled {sum(len(f) for f in uh_dossier_partial.values())} fields")

    out.append("\n" + "=" * 70)
    out.append("STEP 2: merge uh_mapper's dossier_partial into a fresh skeleton")
    out.append("=" * 70)
    skeleton = build_dossier_skeleton()
    merged, invalid = _merge_research_leaves(skeleton["sections"], uh_dossier_partial)
    merged_set = set(merged)
    out.append(f"merged paths ({len(merged)}): {sorted(merged)}")
    out.append(f"invalid paths: {invalid} (expected empty)")
    assert merged_set == EXPECTED_UH_PATHS, f"merged set mismatch: {merged_set.symmetric_difference(EXPECTED_UH_PATHS)}"
    assert invalid == []

    for path in merged:
        section, key = path.split(".", 1)
        leaf = skeleton["sections"][section][key]
        assert leaf["filled_by"] == "uh_mapper", f"{path} filled_by != uh_mapper: {leaf['filled_by']!r}"
        assert leaf["evidence_label"] == "ESTIMATE", f"{path} evidence_label != ESTIMATE"
    out.append("All merged skeleton leaves: filled_by == 'uh_mapper', evidence_label == 'ESTIMATE' — PASS")

    out.append("\n" + "=" * 70)
    out.append("STEP 3: _flatten_dossier_partial_to_values() -> existing_partial shape")
    out.append("=" * 70)
    existing_partial = _flatten_dossier_partial_to_values(uh_dossier_partial)
    out.append(json.dumps(existing_partial, ensure_ascii=False, indent=2))
    assert set(existing_partial.keys()) == EXPECTED_UH_PATHS
    for path, value in existing_partial.items():
        assert isinstance(value, str), f"{path} value is not a flat string: {type(value)}"
    out.append(f"\nkeys match expected 11 paths: True; every value is a plain string (not a leaf dict): True")

    out.append("\n" + "=" * 70)
    out.append("STEP 4: _merge_dossier_partials() combines uh_mapper fields with a fake research delta")
    out.append("=" * 70)
    fake_delta = {
        "customer_market": {"market_size": {
            "value": "تقدير مزيف لاختبار الدمج فقط", "evidence_label": "ESTIMATE",
            "sources": [], "notes": "", "field_code": "B6",
            "filled_by": "research_agent", "filled_at": "2026-01-01T00:00:00+00:00",
        }},
    }
    combined = _merge_dossier_partials(uh_dossier_partial, fake_delta)
    combined_paths = {f"{s}.{k}" for s, fields in combined.items() for k in fields}
    out.append(f"combined paths ({len(combined_paths)}): {sorted(combined_paths)}")
    assert combined_paths == EXPECTED_UH_PATHS | {"customer_market.market_size"}
    assert combined["opportunity"]["problem"]["filled_by"] == "uh_mapper", "uh_mapper field got clobbered by merge"
    assert combined["customer_market"]["market_size"]["filled_by"] == "research_agent"
    out.append("uh_mapper's original 11 fields preserved + delta's 1 new field added — PASS")
    out.append("uh_mapper's dossier_partial dict itself was not mutated by the merge (deepcopy check):")
    assert "market_size" not in uh_dossier_partial.get("customer_market", {})
    out.append("  PASS — original uh_dossier_partial unchanged")

    text = "\n".join(out)
    print(text)

    report_path = SCRIPTS_DIR / "manual_test_uh_entry_path_output.txt"
    report_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

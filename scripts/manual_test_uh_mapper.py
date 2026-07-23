"""Zero-cost test of core/uh_mapper.py against the two real Unicorn Hunter
report fixtures. Pure Python, no LLM/API calls.
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR.parent))

from core.field_registry import FIELD_REGISTRY  # noqa: E402
from core.uh_mapper import parse_uh_report  # noqa: E402

FIXTURES = {
    "manager_productivity": SCRIPTS_DIR / "fixtures" / "uh_report_manager_productivity.md",
    "bakery": SCRIPTS_DIR / "fixtures" / "uh_report_bakery.md",
}

# Every field this mapper can ever produce, per the mapping table.
MAPPED_FIELD_CODES = ["A1", "A3", "B1", "C1", "C2", "C4", "D3", "D4", "D6", "F3"]
# F4 (assumptions) deliberately excluded -- a.6 fix, 2026-07-23: uh_mapper no
# longer fills it; Research Agent phrases it (or leaves it UNKNOWN) instead.
# See core/uh_mapper.py::parse_uh_report()'s docstring for the full rationale.


def _leaf_path(field_code):
    field = FIELD_REGISTRY[field_code]
    return field["section"], field["key"]


def main():
    out = []

    for name, path in FIXTURES.items():
        out.append("=" * 70)
        out.append(f"REPORT: {name}  ({path.name})")
        out.append("=" * 70)

        raw_markdown = path.read_text(encoding="utf-8")
        result = parse_uh_report(raw_markdown)
        dossier_partial = result["dossier_partial"]
        source_metadata = result["source_metadata"]
        parse_warnings = result["parse_warnings"]

        present_codes = []
        for code in MAPPED_FIELD_CODES:
            section, key = _leaf_path(code)
            if key in dossier_partial.get(section, {}):
                present_codes.append(code)

        out.append(f"\nfields filled: {len(present_codes)} / {len(MAPPED_FIELD_CODES)} -> {present_codes}")
        out.append(f"parse_warnings: {parse_warnings}")

        out.append("\n--- dossier_partial (full) ---")
        out.append(json.dumps(dossier_partial, ensure_ascii=False, indent=2))

        out.append("\n--- source_metadata ---")
        out.append(json.dumps(source_metadata, ensure_ascii=False, indent=2))

        # --- Assertions ---
        for code in present_codes:
            section, key = _leaf_path(code)
            leaf = dossier_partial[section][key]
            assert leaf["evidence_label"] == "ESTIMATE", f"{code} evidence_label != ESTIMATE: {leaf['evidence_label']!r}"
            assert leaf["filled_by"] == "uh_mapper", f"{code} filled_by != uh_mapper"
            assert leaf["field_code"] == code

        assert source_metadata["uh_idea_name"], "uh_idea_name missing"
        assert source_metadata["uh_sector"], "uh_sector missing"
        assert source_metadata["uh_final_score"], "uh_final_score missing"
        assert source_metadata["uh_final_decision"], "uh_final_decision missing"
        assert source_metadata["reference"], "reference (Idea ID) missing"

        c2_section, c2_key = _leaf_path("C2")
        c2_value = dossier_partial[c2_section][c2_key]["value"]
        c1_section, c1_key = _leaf_path("C1")
        c1_value = dossier_partial[c1_section][c1_key]["value"]
        assert c1_value in c2_value, "C2 does not contain the Proposed Solution text"
        assert c2_value != c1_value, "C2 was not merged with Why Would the Customer Pay? (equals C1 verbatim)"
        out.append("\nC2 merge check: PASS (contains Proposed Solution text, and is not identical to C1 alone)")

        d3_section, d3_key = _leaf_path("D3")
        d4_section, d4_key = _leaf_path("D4")
        d3_value = dossier_partial[d3_section][d3_key]["value"]
        d4_value = dossier_partial[d4_section][d4_key]["value"]
        assert d3_value == d4_value, "D3 and D4 do not contain identical Revenue Model text"
        out.append("D3/D4 identical Revenue Model text check: PASS")

        out.append("")

    text = "\n".join(out)
    print(text)

    report_path = SCRIPTS_DIR / "manual_test_uh_mapper_output.txt"
    report_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

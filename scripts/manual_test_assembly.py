"""Zero-cost test of assemble_dossier() + compute_readiness_score() using
existing fixtures and a previously captured continue_interview() output.
Makes NO API calls.
"""

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.dossier_assembly import assemble_dossier
from core.field_registry import MAX_WEIGHTED_SCORE

SCRIPTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = SCRIPTS_DIR / "fixtures"
INTERVIEW_OUTPUT_TXT = SCRIPTS_DIR / "manual_test_interview_only_output.txt"


def _extract_balanced_json_blocks_after_marker(text, marker):
    """Find every JSON object that immediately follows `marker` in text."""
    blocks = []
    pos = 0
    while True:
        idx = text.find(marker, pos)
        if idx == -1:
            break
        start = text.find("{", idx)
        depth = 0
        in_string = False
        escape = False
        end = None
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        blocks.append(json.loads(text[start:end + 1]))
        pos = end + 1
    return blocks


def _flatten_field_update(nested):
    """Convert continue_interview()'s {"field_updated": "...", "value": {...}}
    shape into the flat leaf shape assemble_dossier() expects."""
    leaf = nested["value"]
    return {
        "field_code": leaf["field_code"],
        "section": nested["field_updated"].split(".")[0],
        "key": nested["field_updated"].split(".")[1],
        "value": leaf["value"],
        "evidence_label": leaf["evidence_label"],
        "sources": leaf["sources"],
        "notes": leaf["notes"],
        "filled_by": leaf["filled_by"],
        "filled_at": leaf["filled_at"],
    }


def main():
    research_fixture = json.loads((FIXTURES_DIR / "sample_research_output.json").read_text(encoding="utf-8"))
    dossier_partial = research_fixture["dossier_partial"]
    research_gap_map = research_fixture["gap_map"]

    interview_text = INTERVIEW_OUTPUT_TXT.read_text(encoding="utf-8")
    nested_updates = _extract_balanced_json_blocks_after_marker(interview_text, "--- field_update ---")
    interview_updates = [_flatten_field_update(u) for u in nested_updates]

    result = assemble_dossier(
        dossier_partial=dossier_partial,
        interview_updates=interview_updates,
        dossier_id="DS-TEST-001",
        source_type="external",
        language="ar",
        research_gap_map=research_gap_map,
    )

    out = []
    out.append("=" * 70)
    out.append("interview_updates used (flattened from captured continue_interview() output)")
    out.append("=" * 70)
    out.append(json.dumps(interview_updates, ensure_ascii=False, indent=2))

    out.append("\n" + "=" * 70)
    out.append("FULL ASSEMBLED DOSSIER")
    out.append("=" * 70)
    out.append(json.dumps(result, ensure_ascii=False, indent=2))

    out.append("\n" + "=" * 70)
    out.append("READINESS BLOCK ONLY")
    out.append("=" * 70)
    out.append(json.dumps(result["readiness"], ensure_ascii=False, indent=2))

    out.append("\n" + "=" * 70)
    out.append("SANITY CHECKS")
    out.append("=" * 70)

    check1 = set(result["gap_map"].keys()) == set(result["readiness"]["unknown_fields"])
    out.append(f"set(gap_map.keys()) == set(readiness.unknown_fields): {check1}")
    assert check1

    check2 = result["readiness"]["score_weighted"] <= MAX_WEIGHTED_SCORE
    out.append(
        f"score_weighted ({result['readiness']['score_weighted']}) <= MAX_WEIGHTED_SCORE ({MAX_WEIGHTED_SCORE}): {check2}"
    )
    assert check2

    check3 = result["readiness"]["mandatory_passed"] == (len(result["readiness"]["mandatory_missing"]) == 0)
    out.append(f"mandatory_passed == (len(mandatory_missing) == 0): {check3}")
    assert check3

    text = "\n".join(out)
    print(text)

    report_path = SCRIPTS_DIR / "manual_test_assembly_output.txt"
    report_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

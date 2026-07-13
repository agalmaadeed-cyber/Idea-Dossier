"""ONE live API test: confirms Research Agent's delta-only behavior actually
holds when existing_partial is populated from a real uh_mapper.py output.

Costs exactly one run_research() call (with web search). Everything else
(parse_uh_report, flattening) is pure Python, zero cost.
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR.parent))

from agents.research_agent import run_research  # noqa: E402
from app import _flatten_dossier_partial_to_values  # noqa: E402
from core.uh_mapper import parse_uh_report  # noqa: E402

FIXTURE = SCRIPTS_DIR / "fixtures" / "uh_report_bakery.md"


def main():
    out = []

    raw_markdown = FIXTURE.read_text(encoding="utf-8")
    uh_result = parse_uh_report(raw_markdown)
    uh_dossier_partial = uh_result["dossier_partial"]
    existing_partial = _flatten_dossier_partial_to_values(uh_dossier_partial)
    pre_filled_paths = set(existing_partial.keys())

    out.append("=" * 70)
    out.append(f"pre_filled_fields sent to Research Agent ({len(pre_filled_paths)} paths):")
    out.append("=" * 70)
    out.append(json.dumps(sorted(pre_filled_paths), ensure_ascii=False, indent=2))

    research_result = run_research(
        raw_markdown, source_type="unicorn_hunter", existing_partial=existing_partial
    )

    dossier_partial = research_result["dossier_partial"]
    gap_map = research_result["gap_map"]

    returned_paths = {f"{section}.{key}" for section, fields in dossier_partial.items() for key in fields}
    overlap_in_dossier_partial = returned_paths & pre_filled_paths
    overlap_in_gap_map = set(gap_map.keys()) & pre_filled_paths

    out.append("\n" + "=" * 70)
    out.append("Research Agent's returned dossier_partial (should be delta-only)")
    out.append("=" * 70)
    out.append(json.dumps(dossier_partial, ensure_ascii=False, indent=2))

    out.append("\n" + "=" * 70)
    out.append("Research Agent's returned gap_map")
    out.append("=" * 70)
    out.append(json.dumps(gap_map, ensure_ascii=False, indent=2))

    out.append("\n" + "=" * 70)
    out.append("DELTA-ONLY CHECKS")
    out.append("=" * 70)
    out.append(f"returned dossier_partial paths ({len(returned_paths)}): {sorted(returned_paths)}")
    out.append(f"overlap with pre_filled_fields in dossier_partial: {sorted(overlap_in_dossier_partial)} (expected empty)")
    out.append(f"overlap with pre_filled_fields in gap_map: {sorted(overlap_in_gap_map)} (expected empty)")
    out.append(f"CHECK 1 (no overlap in dossier_partial): {'PASS' if not overlap_in_dossier_partial else 'FAIL'}")
    out.append(f"CHECK 2 (no overlap in gap_map): {'PASS' if not overlap_in_gap_map else 'FAIL'}")

    stripped_overlap_fields = research_result.get("stripped_overlap_fields", [])
    out.append(f"\nstripped_overlap_fields reported by run_research(): {stripped_overlap_fields}")
    out.append(
        f"CHECK 3 (stripped_overlap_fields only ever contains pre_filled paths): "
        f"{'PASS' if set(stripped_overlap_fields) <= pre_filled_paths else 'FAIL'}"
    )

    text = "\n".join(out)
    print(text)

    report_path = SCRIPTS_DIR / "manual_test_uh_research_delta_output.txt"
    report_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

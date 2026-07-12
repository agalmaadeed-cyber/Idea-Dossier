"""Build test fixtures from the already-captured manual_test_output.txt.

Makes NO API calls. Reconstructs the exact messages list start_interview()
would have produced, using the same construction logic, so
continue_interview() can be tested later without re-running
run_research() or start_interview().
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.field_registry import MANDATORY_FIELDS

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_TXT = ROOT / "scripts" / "manual_test_output.txt"
FIXTURES_DIR = ROOT / "scripts" / "fixtures"


def extract_section(text, start_marker, end_marker):
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start) if end_marker else len(text)
    return text[start:end].strip()


def main():
    text = OUTPUT_TXT.read_text(encoding="utf-8")

    dossier_partial = json.loads(extract_section(text, "--- dossier_partial ---", "--- gap_map ---"))
    gap_map = json.loads(extract_section(text, "--- gap_map ---", "--- research_summary ---"))
    first_question = extract_section(text, "--- first question ---", None)

    FIXTURES_DIR.mkdir(exist_ok=True)

    research_fixture_path = FIXTURES_DIR / "sample_research_output.json"
    research_fixture_path.write_text(
        json.dumps({"dossier_partial": dossier_partial, "gap_map": gap_map}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Same construction as agents.interview_agent.start_interview()
    initial_message = (
        f"gap_map:\n{json.dumps(gap_map, ensure_ascii=False)}\n\n"
        f"dossier_partial:\n{json.dumps(dossier_partial, ensure_ascii=False)}\n\n"
        f"mandatory_fields: {MANDATORY_FIELDS}\n\n"
        "Begin the interview now with the first question."
    )
    messages = [
        {"role": "user", "content": initial_message},
        {"role": "assistant", "content": first_question},
    ]

    interview_fixture_path = FIXTURES_DIR / "sample_interview_start.json"
    interview_fixture_path.write_text(
        json.dumps({"first_question": first_question, "messages": messages}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {research_fixture_path}")
    print(f"Wrote {interview_fixture_path}")


if __name__ == "__main__":
    main()

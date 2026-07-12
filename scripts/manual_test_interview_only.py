"""Deferred continue_interview() test using fixtures.

Loads scripts/fixtures/sample_interview_start.json instead of calling
run_research() and start_interview(), so this test costs exactly two
Interview Agent calls (one per simulated founder answer).
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.interview_agent import continue_interview

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

FOUNDER_ANSWER_CONFIRMED = (
    "أنا صاحب المكتب، وأنا شخصياً اللي هدفع تكلفة الاشتراك من ميزانية المكتب بتاعي، "
    "مش هحمّل العميل أي تكلفة إضافية."
)

FOUNDER_ANSWER_ASSUMPTION = "ربما... لست متأكداً تماماً، محتاج أفكر أكتر في الموضوع."


def main():
    start_data = json.loads((FIXTURES_DIR / "sample_interview_start.json").read_text(encoding="utf-8"))
    messages = start_data["messages"]

    out = []

    out.append("=" * 70)
    out.append("TURN 1: factual/certain answer (expect CONFIRMED)")
    out.append("=" * 70)
    out.append(f"founder_answer: {FOUNDER_ANSWER_CONFIRMED}")

    result1 = continue_interview(messages, FOUNDER_ANSWER_CONFIRMED)
    out.append("\n--- field_update ---")
    out.append(json.dumps(result1["field_update"], ensure_ascii=False, indent=2))
    out.append("\n--- next_question ---")
    out.append(str(result1["next_question"]))
    out.append("\n--- next_action ---")
    out.append(str(result1["next_action"]))

    out.append("\n" + "=" * 70)
    out.append("TURN 2: uncertain-tone answer (expect ASSUMPTION)")
    out.append("=" * 70)
    out.append(f"founder_answer: {FOUNDER_ANSWER_ASSUMPTION}")

    result2 = continue_interview(result1["messages"], FOUNDER_ANSWER_ASSUMPTION)
    out.append("\n--- field_update ---")
    out.append(json.dumps(result2["field_update"], ensure_ascii=False, indent=2))
    out.append("\n--- next_question ---")
    out.append(str(result2["next_question"]))
    out.append("\n--- next_action ---")
    out.append(str(result2["next_action"]))

    text = "\n".join(out)
    print(text)

    report_path = Path(__file__).resolve().parent / "manual_test_interview_only_output.txt"
    report_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

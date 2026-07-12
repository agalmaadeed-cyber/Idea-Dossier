"""Throwaway manual verification script for research_agent + interview_agent.

Not part of the app. Run with: python scripts/manual_test.py
Requires ANTHROPIC_API_KEY in the environment.
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.research_agent import run_research
from agents.interview_agent import start_interview

RAW_INPUT_AR = (
    "عندي فكرة: مكاتب المحاسبة الصغيرة عندنا لسه بتستخدم إكسل وورق عشان "
    "تتابع فواتير العملاء ومواعيد استحقاق الضرائب، وده بيسبب أخطاء كتير "
    "وضياع وقت. عايز أعمل أداة بسيطة تساعدهم يتابعوا الفواتير والمواعيد "
    "في مكان واحد."
)

def main():
    out = []

    out.append("=" * 70)
    out.append("STEP 1: run_research()")
    out.append("=" * 70)
    research_result = run_research(RAW_INPUT_AR, source_type="external")

    out.append("\n--- dossier_partial ---")
    out.append(json.dumps(research_result["dossier_partial"], ensure_ascii=False, indent=2))

    out.append("\n--- gap_map ---")
    out.append(json.dumps(research_result["gap_map"], ensure_ascii=False, indent=2))

    out.append("\n--- research_summary ---")
    out.append(research_result["research_summary"])

    out.append("\n" + "=" * 70)
    out.append("STEP 2: start_interview()")
    out.append("=" * 70)
    first_question, messages = start_interview(
        research_result["gap_map"], research_result["dossier_partial"]
    )
    out.append("\n--- first question ---")
    out.append(first_question)

    text = "\n".join(out)
    print(text)

    report_path = Path(__file__).resolve().parent.parent / "scripts" / "manual_test_output.txt"
    report_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

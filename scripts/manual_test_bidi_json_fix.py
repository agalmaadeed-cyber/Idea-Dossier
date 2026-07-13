"""Offline unit tests for interview_agent.py's invisible-Unicode-control-character
JSON parsing fix (bidi/format characters landing between JSON tokens near RTL text,
e.g. "200 دولار", breaking json.loads()).

No live API calls: call_agent() is monkeypatched with a fake response object so
these run for free and deterministically. This is deliberately separate from
manual_test_interview_only.py (which exercises the real Interview Agent against a
live model) — these tests only need to prove OUR parsing/fallback code is correct,
not the model's behavior.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agents.interview_agent as interview_agent
from agents.interview_agent import continue_interview, _extract_leading_json, _strip_invisible_controls

BIDI_RLM = "‏"


def _fake_response(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_bidi_char_breaks_raw_but_fix_recovers():
    corrupted = (
        '{"field_updated": "founder_resources.budget",' + BIDI_RLM +
        ' "value": {"value": "200 دولار", "evidence_label": "CONFIRMED", '
        '"sources": [], "notes": ""}, "next_action": "ask_next_question"}'
        "\n\nهل هذا المبلغ شهري أم لمرة واحدة؟"
    )

    # Sanity check: prove the raw text (before stripping) genuinely fails to
    # parse, confirming the bug's mechanism.
    parsed_raw, _ = _extract_leading_json(corrupted)
    assert parsed_raw is None, "sanity check failed: raw bidi-corrupted text should NOT parse"

    cleaned = _strip_invisible_controls(corrupted)
    assert BIDI_RLM not in cleaned, "bidi char should be stripped"

    parsed_clean, remainder = _extract_leading_json(cleaned)
    assert parsed_clean is not None, "cleaned text should parse"
    assert parsed_clean["field_updated"] == "founder_resources.budget"
    assert "شهري" in remainder

    with mock.patch.object(interview_agent, "call_agent", return_value=_fake_response(corrupted)):
        result = continue_interview([{"role": "user", "content": "..."}], "200 دولار")

    assert result["field_update"] is not None, "field should be recovered end-to-end after stripping"
    assert result["field_update"]["field_updated"] == "founder_resources.budget"
    assert result["field_update"]["value"]["value"] == "200 دولار"
    assert result["field_update"]["value"]["evidence_label"] == "CONFIRMED"
    assert result["parse_failure"] is False
    assert result["failed_field_path"] is None
    assert result["next_action"] == "ask_next_question"
    assert result["next_question"] is not None and "field_updated" not in result["next_question"]
    print("PASS: bidi character stripped end-to-end, field recovered normally, no leak")


def test_genuine_parse_failure_is_flagged_not_leaked():
    # Deliberately truncated/malformed JSON: contains the literal substring
    # '"field_updated"' but the object is never closed, so no amount of
    # cleaning will make it parse. This must be treated as a genuine failure,
    # not a normal "just asking a question" turn.
    malformed = '{"field_updated": "founder_resources.budget", "value": {"value": "200 دولار"'

    with mock.patch.object(interview_agent, "call_agent", return_value=_fake_response(malformed)):
        result = continue_interview([{"role": "user", "content": "..."}], "200 دولار")

    assert result["field_update"] is None, "malformed JSON must never be trusted as a real field_update"
    assert result["parse_failure"] is True
    assert result["failed_field_path"] == "founder_resources.budget"
    assert result["next_action"] == "ask_followup", "must never advance to interview_complete on a parse failure"
    assert result["next_question"] is not None
    assert "field_updated" not in result["next_question"], "raw/malformed text must never leak into next_question"
    assert "{" not in result["next_question"], "raw/malformed text must never leak into next_question"
    print("PASS: genuine parse failure flagged, raw text never leaked, forced to ask_followup")


def test_normal_plain_question_is_unaffected():
    plain = "ما هي الميزانية المتاحة للمشروع؟"

    with mock.patch.object(interview_agent, "call_agent", return_value=_fake_response(plain)):
        result = continue_interview([{"role": "user", "content": "..."}], "مرحبا")

    assert result["field_update"] is None
    assert result["parse_failure"] is False
    assert result["failed_field_path"] is None
    assert result["next_action"] == "ask_next_question"
    assert result["next_question"] == plain
    print("PASS: normal plain-text question turn is unaffected by the fix (no regression)")


def test_english_founder_gets_english_fallback():
    malformed = '{"field_updated": "founder_resources.time", "value": {"value": "10 hours/week"'

    with mock.patch.object(interview_agent, "call_agent", return_value=_fake_response(malformed)):
        result = continue_interview([{"role": "user", "content": "..."}], "10 hours a week")

    assert result["parse_failure"] is True
    assert result["failed_field_path"] == "founder_resources.time"
    assert "glitch" in result["next_question"].lower()
    print("PASS: fallback message language follows the founder's own answer (English case)")


if __name__ == "__main__":
    test_bidi_char_breaks_raw_but_fix_recovers()
    test_genuine_parse_failure_is_flagged_not_leaked()
    test_normal_plain_question_is_unaffected()
    test_english_founder_gets_english_fallback()
    print("\nAll bidi/parse-failure tests passed.")

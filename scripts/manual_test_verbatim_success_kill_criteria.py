"""Offline unit tests for the b.3 fix (deferred design session, 2026-07-24):
F1 (success_criteria) and F2 (kill_criteria) must store the founder's raw,
concatenated answer text verbatim, never the model's own generated "value"
string -- enforcing in code what the system prompt already promises
("the final content must be the founder's own words, not your invention")
but could not previously guarantee.

No live API calls: call_agent() is monkeypatched with a fake response
object, same convention as manual_test_bidi_json_fix.py and
manual_test_gap_map_enrichment.py.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agents.interview_agent as interview_agent
from agents.interview_agent import continue_interview


def _fake_response(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _resolving_reply(field_path, model_authored_value, evidence_label="FOUNDER_OPINION", next_action="ask_next_question"):
    import json

    payload = json.dumps({
        "field_updated": field_path,
        "value": {"value": model_authored_value, "evidence_label": evidence_label, "sources": [], "notes": ""},
        "next_action": next_action,
    })
    return payload + "\n\nWhat's next?"


def _followup_reply(text):
    return text


def test_f1_verbatim_value_replaces_llm_paraphrase():
    founder_answer = "لو وصلنا ل100 عميل مدفوع خلال أول 3 شهور بعتبره نجاح."
    model_paraphrase = "Reaching 100 paying customers within the first 3 months."

    reply = _resolving_reply("success_definition.success_criteria", model_paraphrase)
    with mock.patch.object(interview_agent, "call_agent", return_value=_fake_response(reply)):
        result = continue_interview([{"role": "user", "content": "..."}], founder_answer)

    assert result["field_update"]["value"]["value"] == founder_answer, (
        "F1's stored value must be the founder's literal text, not the model's paraphrase"
    )
    assert result["field_update"]["value"]["evidence_label"] == "FOUNDER_OPINION", (
        "evidence_label classification is still the model's judgment call -- unaffected by this fix"
    )
    assert result["pending_founder_turns"] == []


def test_f2_verbatim_value_replaces_llm_paraphrase():
    founder_answer = "لو بعد 6 شهور مفيش ولا عميل واحد مستعد يدفع، هوقف الفكرة."
    model_paraphrase = "Zero paying customers after 6 months triggers a stop."

    reply = _resolving_reply("success_definition.kill_criteria", model_paraphrase)
    with mock.patch.object(interview_agent, "call_agent", return_value=_fake_response(reply)):
        result = continue_interview([{"role": "user", "content": "..."}], founder_answer)

    assert result["field_update"]["value"]["value"] == founder_answer
    assert result["pending_founder_turns"] == []


def test_multi_turn_concatenates_all_founder_turns_in_order():
    turn1 = "لو وصلنا لعدد عملاء كويس بعتبرها نجاح."
    followup_question = "كام عميل بالظبط، وخلال أي مدة؟"
    turn2 = "100 عميل مدفوع خلال 3 شهور."

    with mock.patch.object(interview_agent, "call_agent", return_value=_fake_response(_followup_reply(followup_question))):
        result1 = continue_interview([{"role": "user", "content": "..."}], turn1)

    assert result1["field_update"] is None, "sanity check: first turn should NOT resolve the field yet"
    assert result1["pending_founder_turns"] == [turn1]

    reply2 = _resolving_reply("success_definition.success_criteria", "100 paying customers within 3 months.")
    with mock.patch.object(interview_agent, "call_agent", return_value=_fake_response(reply2)):
        result2 = continue_interview(result1["messages"], turn2, result1["pending_founder_turns"])

    assert result2["field_update"]["value"]["value"] == f"{turn1}\n{turn2}", (
        "the final value must contain BOTH founder turns, in order -- not just the last one"
    )
    assert result2["pending_founder_turns"] == []


def test_unrelated_field_unaffected_still_uses_model_value():
    founder_answer = "حوالي 2000 دولار، ومرن شوية لو احتجت أكتر."
    model_value = "Approximately $2,000, with some flexibility."

    reply = _resolving_reply("founder_resources.budget", model_value, evidence_label="CONFIRMED")
    with mock.patch.object(interview_agent, "call_agent", return_value=_fake_response(reply)):
        result = continue_interview([{"role": "user", "content": "..."}], founder_answer)

    assert result["field_update"]["value"]["value"] == model_value, (
        "a field outside _VERBATIM_REQUIRED_FIELDS must still use the model's own synthesized value"
    )
    assert result["pending_founder_turns"] == []


def test_pending_turns_survive_a_parse_failure_for_retry():
    turn1 = "لو وصلنا لعدد عملاء كويس."
    corrupted_reply = '{"field_updated": "success_definition.success_criteria", "value": {' # deliberately truncated/invalid JSON

    with mock.patch.object(interview_agent, "call_agent", return_value=_fake_response(corrupted_reply)):
        result = continue_interview([{"role": "user", "content": "..."}], turn1)

    assert result["parse_failure"] is True
    assert result["field_update"] is None
    assert result["pending_founder_turns"] == [turn1], (
        "a parse failure must not lose the founder's turn -- it's needed for the retry of the same gap"
    )


def main():
    tests = [
        test_f1_verbatim_value_replaces_llm_paraphrase,
        test_f2_verbatim_value_replaces_llm_paraphrase,
        test_multi_turn_concatenates_all_founder_turns_in_order,
        test_unrelated_field_unaffected_still_uses_model_value,
        test_pending_turns_survive_a_parse_failure_for_retry,
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

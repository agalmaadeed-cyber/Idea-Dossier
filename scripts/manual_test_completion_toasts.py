"""
Manual test: active completion toasts (a.10 fix, cross-project evaluation,
2026-07-24).

Before this fix, both genuine whole-phase completions in this app --
Research finishing and the Interview starting, and the whole Dossier
being assembled and saved at the end of the interview -- ended in a
silent st.rerun() with no signal beyond the chat history updating. The
fix adds st.toast() immediately before each of these two completion
points.

Unlike this repo's other scripts/manual_test_*.py files (which test pure
functions directly, no Streamlit dependency), st.toast() is itself a
Streamlit UI call -- invisible to a plain function-level test. This
introduces streamlit.testing.v1.AppTest to this repo for the first time,
following the exact same precedent and justification already established
in the sibling vdve repo (test_app_status_labels.py, and this same a.10
item's own VDVE packet, Part 1/3) for the identical class of "session
state / UI call, not visible to a pure unit test" problem. All calls
below (run_research, start_interview, continue_interview, assemble_dossier,
save_dossier_version) are monkeypatched with fakes -- no real API call,
no ANTHROPIC_API_KEY needed, zero cost.

Cases 2 and 3 seed st.session_state directly to the "interviewing" stage
(bypassing the awaiting_input -> researching transition) rather than
chaining three stage transitions through one AppTest instance -- chaining
was found to trip an AppTest-specific widget-tree staleness error
unrelated to this fix (a stale "input_mode" radio-widget lookup after
navigating away from the stage that renders it). _init_session_state()
only initializes state "if 'stage' not in st.session_state", so
pre-seeding every key it would otherwise set reproduces the exact same
state a real run would reach, without tripping the harness quirk.

Run: python scripts/manual_test_completion_toasts.py
Exit 0 = all assertions passed.
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

out = []


def _fake_run_research(raw_input, source_type=None, existing_partial=None):
    return {
        "dossier_partial": {},
        "gap_map": {},
        "research_summary": "(fake research summary)",
    }


def _fake_start_interview(gap_map, dossier_partial):
    return "(fake first interview question)", [{"role": "assistant", "content": "(fake first interview question)"}]


def _fake_continue_interview_ordinary(messages, answer, pending_founder_turns=None):
    # b.3 amendment (2026-07-24): continue_interview()'s real signature
    # gained a third parameter, pending_founder_turns, and now always
    # returns a "pending_founder_turns" key in its result -- this fake
    # must match both, or app.py's own call site (extra positional arg)
    # and its unconditional result["pending_founder_turns"] read (missing
    # key) both break, independent of anything this test intends to check.
    return {
        "messages": messages + [{"role": "user", "content": answer}],
        "field_update": None,
        "next_question": "(fake next question)",
        "next_action": "continue",
        "pending_founder_turns": (pending_founder_turns or []) + [answer],
    }


def _fake_continue_interview_complete(messages, answer, pending_founder_turns=None):
    return {
        "messages": messages + [{"role": "user", "content": answer}],
        "field_update": None,
        "next_question": None,
        "next_action": "interview_complete",
        "pending_founder_turns": [],
    }


def _fake_assemble_dossier(*args, **kwargs):
    return {
        "dossier_id": "DS-FAKE",
        "version": 1,
        "status": "PARTIAL",
        "readiness": {"score_percentage": 42},
        "sections": {},
        "gap_map": {},
    }


def _fake_save_dossier_version(final_dossier):
    return None


def _toast_messages(at):
    return [t.value for t in at.toast]


def _seed_interviewing_state(at, first_question="(fake q)"):
    """Seed st.session_state directly to a fresh 'interviewing' stage,
    matching exactly what _init_session_state() + a completed research
    call would have set -- see module docstring for why this bypasses the
    awaiting_input -> researching transition."""
    at.session_state["stage"] = "interviewing"
    at.session_state["chat_history"] = [{"role": "assistant", "content": first_question}]
    at.session_state["dossier_partial"] = {}
    at.session_state["gap_map"] = {}
    at.session_state["interview_messages"] = [{"role": "assistant", "content": first_question}]
    at.session_state["interview_updates"] = []
    at.session_state["dossier_id"] = "DS-FAKE"
    at.session_state["final_dossier"] = None
    at.session_state["raw_input"] = "A fake startup idea for testing."
    at.session_state["entry_path"] = "external"
    at.session_state["language"] = "ar"
    at.session_state["uploader_key"] = 0
    at.session_state["last_updated_field"] = None
    at.session_state["field_update_warnings"] = []
    at.session_state["parse_failed_fields"] = set()


out.append("=" * 70)
out.append("CASE 1: research complete -> entering interview fires a toast")
out.append("=" * 70)

with patch("agents.research_agent.run_research", _fake_run_research), \
     patch("agents.interview_agent.start_interview", _fake_start_interview):
    at = AppTest.from_file("app.py")
    at.run()
    assert at.exception == [], f"exception on initial load: {at.exception}"

    typed = [w for w in at.chat_input]
    assert len(typed) == 1, f"expected exactly 1 chat_input at awaiting_input stage, found {len(typed)}"
    typed[0].set_value("A fake startup idea for testing.").run()
    assert at.exception == [], f"exception after submitting the idea: {at.exception}"

    messages = _toast_messages(at)
    assert "Research complete — starting interview." in messages, messages
    out.append(f"PASS -- research-complete toast fired: {messages}")

out.append("\n" + "=" * 70)
out.append("CASE 2: an ordinary interview turn (not yet complete) fires NO completion toast")
out.append("=" * 70)

with patch("agents.interview_agent.continue_interview", _fake_continue_interview_ordinary):
    at = AppTest.from_file("app.py")
    _seed_interviewing_state(at)
    at.run()
    assert at.exception == [], f"exception on seeded interviewing-stage load: {at.exception}"

    interview_inputs = [w for w in at.chat_input]
    assert len(interview_inputs) == 1, f"expected exactly 1 chat_input at interviewing stage, found {len(interview_inputs)}"
    interview_inputs[0].set_value("A fake answer.").run()
    assert at.exception == [], f"exception after an ordinary interview turn: {at.exception}"

    messages = _toast_messages(at)
    assert "Dossier complete!" not in messages, \
        f"an ordinary (non-terminal) interview turn must NOT fire the whole-Dossier-complete toast: {messages}"
    out.append(f"PASS -- no 'Dossier complete!' toast on an ordinary interview turn (toasts present: {messages})")

out.append("\n" + "=" * 70)
out.append("CASE 3: interview_complete fires the whole-Dossier-complete toast")
out.append("=" * 70)

with patch("agents.interview_agent.continue_interview", _fake_continue_interview_complete), \
     patch("core.dossier_assembly.assemble_dossier", _fake_assemble_dossier), \
     patch("storage.save_dossier_version", _fake_save_dossier_version):
    at = AppTest.from_file("app.py")
    _seed_interviewing_state(at)
    at.run()
    assert at.exception == [], f"exception on seeded interviewing-stage load: {at.exception}"

    at.chat_input[0].set_value("A fake final answer.").run()
    assert at.exception == [], f"exception on the interview-completing turn: {at.exception}"

    messages = _toast_messages(at)
    assert "Dossier complete!" in messages, messages
    out.append(f"PASS -- whole-Dossier-complete toast fired on interview_complete: {messages}")

out.append("\n" + "=" * 70)
out.append("ALL ASSERTIONS PASSED")
out.append("=" * 70)

print("\n".join(out))

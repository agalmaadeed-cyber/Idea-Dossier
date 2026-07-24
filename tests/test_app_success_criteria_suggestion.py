"""AppTest coverage for the b.5 suggestion expander's visibility gating
(cross-project evaluation item b.5, deferred design session, 2026-07-24).

Uses AppTest for the same reason as test_app_status_labels.py and
test_app_completion_toasts.py: whether the expander actually renders (or
doesn't) is a UI-rendering fact, invisible to a plain unit test on
core/success_criteria_suggestions.py alone.
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_suggestion_expander_visible_before_f1_f2_answered():
    at = AppTest.from_file("app.py")
    at.run()
    at.session_state["stage"] = "interviewing"
    at.session_state["dossier"]["sections"]["success_definition"]["success_criteria"]["value"] = None
    at.session_state["dossier"]["sections"]["success_definition"]["kill_criteria"]["value"] = None
    at.run()

    expander_titles = [e.label for e in at.expander]
    assert any("اقتراح مبدئي لمعايير النجاح/الفشل" in title for title in expander_titles)


def test_suggestion_expander_hidden_once_both_answered():
    at = AppTest.from_file("app.py")
    at.run()
    at.session_state["stage"] = "interviewing"
    at.session_state["dossier"]["sections"]["success_definition"]["success_criteria"]["value"] = "founder's own text"
    at.session_state["dossier"]["sections"]["success_definition"]["kill_criteria"]["value"] = "founder's own text"
    at.run()

    expander_titles = [e.label for e in at.expander]
    assert not any("اقتراح مبدئي لمعايير النجاح/الفشل" in title for title in expander_titles)

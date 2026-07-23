"""
Manual test: Interview Agent's gap_map enrichment (a.7 fix, 2026-07-23).

Verifies both the pure enrichment function directly, and that
start_interview() actually sends the enriched gap_map to the model --
with zero API cost. start_interview()'s call_agent is monkeypatched
with a fake that returns a canned response object and captures the
messages it was called with, so no real network call is made.

Run: python scripts/manual_test_gap_map_enrichment.py
Exit 0 = all assertions passed.
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agents.interview_agent as interview_agent
from agents.interview_agent import _enrich_gap_map_for_interview, start_interview

out = []

# --- Part 1: the pure enrichment function, directly ---

out.append("=" * 70)
out.append("PART 1: _enrich_gap_map_for_interview() unit-level checks")
out.append("=" * 70)

gap_map = {
    "customer_market.payer": "PARTIAL -- founder didn't specify exactly who pays.",
    "founder_resources.budget": "EMPTY -- not mentioned in raw input.",
}
dossier_partial = {
    "customer_market": {
        "payer": {
            "value": "Likely the accounting office owner.",
            "evidence_label": "ESTIMATE",
            "sources": [], "notes": "", "field_code": "B1",
            "filled_by": "research_agent", "filled_at": "2026-07-10T00:00:00+00:00",
        },
    },
    # founder_resources.budget deliberately absent -- genuinely EMPTY,
    # nothing for the enrichment to attach.
}

enriched = _enrich_gap_map_for_interview(gap_map, dossier_partial)

assert "Existing research value (ESTIMATE): Likely the accounting office owner." in enriched["customer_market.payer"], \
    f"PARTIAL field with a real dossier_partial value must get enriched: {enriched['customer_market.payer']!r}"
assert enriched["customer_market.payer"].startswith("PARTIAL -- founder didn't specify exactly who pays."), \
    "original reason text must be preserved, not replaced"
out.append("PASS -- PARTIAL field with a real value gets the research value appended")

assert enriched["founder_resources.budget"] == "EMPTY -- not mentioned in raw input.", \
    f"genuinely EMPTY field (no dossier_partial entry) must be left completely unchanged: {enriched['founder_resources.budget']!r}"
out.append("PASS -- genuinely EMPTY field (nothing in dossier_partial) left untouched")

# never mutates the caller's original dicts
assert gap_map["customer_market.payer"] == "PARTIAL -- founder didn't specify exactly who pays.", \
    "original gap_map dict must not be mutated"
out.append("PASS -- original gap_map dict not mutated (still has the short reason only)")

# --- Part 2: start_interview() actually sends the enriched version, zero API cost ---

out.append("\n" + "=" * 70)
out.append("PART 2: start_interview() sends the enriched gap_map (mocked, no API call)")
out.append("=" * 70)


class _FakeTextBlock:
    type = "text"
    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


captured = {}

def _fake_call_agent(system_prompt, messages, **kwargs):
    captured["messages"] = messages
    return _FakeResponse("(fake first question)")


original_call_agent = interview_agent.call_agent
interview_agent.call_agent = _fake_call_agent
try:
    first_question, messages = start_interview(gap_map, dossier_partial)
finally:
    interview_agent.call_agent = original_call_agent

sent_content = captured["messages"][0]["content"]
assert "Existing research value (ESTIMATE): Likely the accounting office owner." in sent_content, \
    "the actual message sent to the model must contain the enriched gap_map, not the raw short reason"
assert "EMPTY -- not mentioned in raw input." in sent_content, \
    "genuinely EMPTY fields must still appear in the sent message, unenriched"
out.append("PASS -- start_interview() sends the model the enriched gap_map, confirmed from the real captured payload")
out.append(f"first_question (from fake response): {first_question!r}")

out.append("\n" + "=" * 70)
out.append("ALL ASSERTIONS PASSED")
out.append("=" * 70)

print("\n".join(out))

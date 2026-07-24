"""Deterministic parser for Unicorn Hunter Opportunity Reports (raw Markdown).

Pure Python, no LLM calls. Produces a dossier_partial in the exact same
shape as agents/research_agent.py's output (value/evidence_label/sources/
notes/field_code/filled_by/filled_at), with filled_by="uh_mapper" and
evidence_label always "ESTIMATE" per the agreed rule — this mapper never
infers CONFIRMED, even when the source text uses confident language.

Implements idea_dossier_specification.md Section 3 (Unicorn Hunter handoff).
"""

import re
from datetime import datetime, timezone

from core.field_registry import FIELD_REGISTRY

# Every label the fixed-format "MVP Opportunity Report" block may contain,
# across both the "Initial Analysis" and "After Field Verification" variants.
LABELS = [
    "Idea Name",
    "Sector",
    "Target Customer",
    "Problem",
    "Current User Situation",
    "Proposed Solution",
    "MVP Shape",
    "Market Testing Method",
    "Revenue Model",
    "Why Would the Customer Pay?",
    "Risks",
    "Overall Score (analytical, pre-field verification)",
    "Initial Decision",
    "Final Overall Score (after verification)",
    "Final Decision",
    "Next Step",
]

# Labels present only in the "Initial Analysis" variant, or only in
# "After Field Verification" — used to decide which absences are genuine
# parse_warnings vs. expected per block type.
_INITIAL_ONLY_LABELS = ["Overall Score (analytical, pre-field verification)", "Initial Decision"]
_VERIFIED_ONLY_LABELS = ["Final Overall Score (after verification)", "Final Decision", "Next Step"]
_SHARED_LABELS = [l for l in LABELS if l not in _INITIAL_ONLY_LABELS and l not in _VERIFIED_ONLY_LABELS]

# "What Changed After Field Verification" is not one of the 16 mapped
# labels -- this mapper deliberately does not read it (a.6 fix, cross-
# project evaluation, 2026-07-23: F4/assumptions used to be filled
# straight from this section's raw literal text; now the same raw
# report text reaches Research Agent instead, which phrases it properly
# or leaves it UNKNOWN -- see parse_uh_report()'s docstring). It still
# needs to stay in the boundary list below: in some reports it appears
# as an inline "**bold field:**" between Risks and Final Overall Score
# (see uh_report_bakery.md) rather than as its own "## " section (see
# uh_report_manager_productivity.md), and every OTHER label's lookahead
# boundary must still know about it, or a field like Risks would
# swallow it whole when it appears inline.
_BOUNDARY_LABELS = LABELS + ["What Changed After Field Verification"]
_BOUNDARY_ALTERNATION = "|".join(re.escape(l) for l in _BOUNDARY_LABELS)

_INITIAL_HEADING_RE = re.compile(r"(?:^|\n)##\s*MVP Opportunity Report\s*[—-]\s*Initial Analysis\s*(?:\n|$)")
_VERIFIED_HEADING_RE = re.compile(r"(?:^|\n)##\s*MVP Opportunity Report\s*[—-]\s*After Field Verification\s*(?:\n|$)")
_IDEA_ID_RE = re.compile(r"(?:^|\n)\*\*Idea ID:?\*\*\s*(.+?)(?:\n|\Z)")

# Single-target labels: label -> field_code, for the plain 1:1 mappings.
# Proposed Solution, Why Would the Customer Pay?, and Revenue Model are
# handled separately since they fan out to multiple dossier fields.
_SIMPLE_MAPPING = {
    "Target Customer": "B1",
    "Problem": "A1",
    "Current User Situation": "A3",
    "MVP Shape": "C4",
    "Market Testing Method": "D6",
    "Risks": "F3",
}


def _label_pattern(label):
    return re.compile(
        rf"(?:^|\n)\*\*{re.escape(label)}:?\*\*\s*(.+?)(?=\n\*\*(?:{_BOUNDARY_ALTERNATION}):?\*\*|\n---|\Z)",
        re.DOTALL,
    )


def _locate_block(raw_markdown: str):
    """Step 1: prefer the After Field Verification block; fall back to
    Initial Analysis. Returns (block_type, block_text) or (None, "")."""
    verified_match = _VERIFIED_HEADING_RE.search(raw_markdown)
    if verified_match:
        return "after_verification", raw_markdown[verified_match.end():]
    initial_match = _INITIAL_HEADING_RE.search(raw_markdown)
    if initial_match:
        return "initial", raw_markdown[initial_match.end():]
    return None, ""


def _extract_labels(block_text: str) -> dict:
    values = {}
    for label in LABELS:
        match = _label_pattern(label).search(block_text)
        if match:
            values[label] = match.group(1).strip()
    return values


# b.6 fix (deferred design session, 2026-07-24): the one real field-
# combination site in this project (C2, below) was safe only as a side
# effect of every uh_mapper-written field sharing one hardcoded
# "ESTIMATE" default -- not because any code actually enforced that a
# combined/merged field (which may conflate sub-claims of genuinely
# different confidence) can never be assigned a stronger label than its
# weakest component. VDVE's scanner.py skips ONLY fields labeled exactly
# CONFIRMED (never stress-tested); a combined field silently upgraded to
# CONFIRMED in the future would quietly bypass that testing. This turns
# the invariant into something explicit and enforced, scoped narrowly to
# this repo's one actual combining site -- not a speculative fix for a
# risk that doesn't exist elsewhere in the code today (root cause
# investigated 2026-07-23; scope decided in this design session,
# 2026-07-24: founder chose a contained uh_mapper.py-only guard over a
# broader cross-repo schema change, since no second combination site
# currently exists to justify one).
_EVIDENCE_LABEL_RANK = {"UNKNOWN": 0, "ASSUMPTION": 1, "FOUNDER_OPINION": 1, "ESTIMATE": 2, "CONFIRMED": 3}
_COMBINED_FIELD_LABEL_CEILING = "ESTIMATE"


def _write_field(
    dossier_partial: dict, field_code: str, value: str, notes: str, now: str, warnings: list,
    *, is_combined: bool = False, evidence_label: str = "ESTIMATE",
):
    """Same guard-clause principle as app.py's merge_research_into_skeleton:
    verify the mapping target actually exists in FIELD_REGISTRY before
    writing, else warn instead of raising.

    is_combined=True marks a field whose value merges more than one
    distinct underlying claim (currently only C2 -- see its call site
    below). For such fields, evidence_label can never exceed
    _COMBINED_FIELD_LABEL_CEILING -- violating this raises ValueError,
    a structural integrity failure that must surface loudly, not be
    silently downgraded (b.6 fix, 2026-07-24)."""
    if field_code not in FIELD_REGISTRY:
        warnings.append(f"mapping target field_code not in FIELD_REGISTRY: {field_code!r}")
        return
    if is_combined and _EVIDENCE_LABEL_RANK[evidence_label] > _EVIDENCE_LABEL_RANK[_COMBINED_FIELD_LABEL_CEILING]:
        raise ValueError(
            f"{field_code}: a combined/merged field can never be assigned '{evidence_label}' -- "
            f"weakest-link governs; ceiling is '{_COMBINED_FIELD_LABEL_CEILING}' (b.6 fix, 2026-07-24)"
        )
    field = FIELD_REGISTRY[field_code]
    section, key = field["section"], field["key"]
    dossier_partial.setdefault(section, {})[key] = {
        "value": value,
        "evidence_label": evidence_label,
        "sources": [],
        "notes": notes,
        "field_code": field_code,
        "filled_by": "uh_mapper",
        "filled_at": now,
    }


def parse_uh_report(raw_markdown: str) -> dict:
    """Parse a Unicorn Hunter Opportunity Report into a partial Dossier fill.

    F4 (success_definition.assumptions) is deliberately NOT filled here
    (a.6 fix, cross-project evaluation, 2026-07-23). It used to be filled
    straight from the raw "What Changed After Field Verification" /
    "Field Verification Answers" sections -- literal, unphrased founder
    answer fragments, still tagged evidence_label="ESTIMATE" like every
    other uh_mapper field, which let raw fragments count toward Dossier
    readiness with no real synthesis behind them. Rather than adding a new
    LLM call just for this one field, the simplest fix reuses existing
    machinery: F4 is left out of dossier_partial here, so it is NOT part
    of the pre_filled_fields Research Agent receives -- Research Agent
    already reads this exact raw report text as its own raw_input, and
    already applies its full CONFIRMED/ESTIMATE/UNKNOWN evidence-label
    discipline to success_definition.assumptions like any other field
    (see agents/research_agent.py's OUTPUT FORMAT). If Research Agent can
    honestly phrase a coherent assumptions statement from that raw text,
    it fills F4 itself and wins app.py's _merge_dossier_partials() (the
    Research Agent delta always takes precedence on overlap). If it
    can't, F4 correctly stays UNKNOWN via the existing skeleton default --
    exactly the founder's "phrase it, or classify UNKNOWN" requirement,
    with zero new code beyond this exclusion.

    Returns:
    {
        "dossier_partial": {...},   # same nested shape as research_agent.py's output
        "source_metadata": {...},
        "parse_warnings": [...],
    }
    """
    now = datetime.now(timezone.utc).isoformat()
    warnings = []
    dossier_partial = {}

    block_type, block_text = _locate_block(raw_markdown)
    if block_type is None:
        warnings.append("No 'MVP Opportunity Report' block found (neither Initial Analysis nor After Field Verification)")
        extracted = {}
    else:
        extracted = _extract_labels(block_text)
        expected = _SHARED_LABELS + (_VERIFIED_ONLY_LABELS if block_type == "after_verification" else _INITIAL_ONLY_LABELS)
        for label in expected:
            if label not in extracted:
                warnings.append(label)

    # --- Simple 1:1 mappings ---
    for label, field_code in _SIMPLE_MAPPING.items():
        if label in extracted:
            _write_field(dossier_partial, field_code, extracted[label], f"Extracted from Unicorn Hunter report, label: {label!r}", now, warnings)

    # --- Proposed Solution -> C1, and contributes to C2 ---
    proposed_solution = extracted.get("Proposed Solution")
    if proposed_solution:
        _write_field(dossier_partial, "C1", proposed_solution, "Extracted from Unicorn Hunter report, label: 'Proposed Solution'", now, warnings)

    # --- Why Would the Customer Pay? + Proposed Solution -> C2 (merged, not overwritten) ---
    why_pay = extracted.get("Why Would the Customer Pay?")
    c2_parts = [p for p in (proposed_solution, why_pay) if p]
    if c2_parts:
        _write_field(
            dossier_partial, "C2", "\n".join(c2_parts),
            "Combined from Unicorn Hunter labels: 'Proposed Solution' and 'Why Would the Customer Pay?'",
            now, warnings, is_combined=True,
        )

    # --- Revenue Model -> D3 AND D4 (same text, both fields) ---
    revenue_model = extracted.get("Revenue Model")
    if revenue_model:
        for field_code in ("D3", "D4"):
            _write_field(dossier_partial, field_code, revenue_model, "Extracted from Unicorn Hunter report, label: 'Revenue Model'", now, warnings)

    # --- Source metadata (fields with no dossier field_code match) ---
    idea_id_match = _IDEA_ID_RE.search(raw_markdown)
    idea_id = idea_id_match.group(1).strip() if idea_id_match else None

    final_score = extracted.get("Final Overall Score (after verification)") or extracted.get("Overall Score (analytical, pre-field verification)")
    final_decision = extracted.get("Final Decision") or extracted.get("Initial Decision")

    source_metadata = {
        "type": "unicorn_hunter",
        "reference": f"UH Idea ID: {idea_id}" if idea_id else None,
        "uh_idea_name": extracted.get("Idea Name"),
        "uh_sector": extracted.get("Sector"),
        "uh_final_score": final_score,
        "uh_final_decision": final_decision,
        "uh_next_step": extracted.get("Next Step"),
    }

    return {
        "dossier_partial": dossier_partial,
        "source_metadata": source_metadata,
        "parse_warnings": warnings,
    }

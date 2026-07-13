"""Merges Research Agent output and Interview Agent answers into the final Idea Dossier.

Implements the assembly step of idea_dossier_schema.md Section 3. Pure
Python — no API calls, no imports from agents/.
"""

import copy
from datetime import datetime, timezone

from core.field_registry import FIELD_REGISTRY
from core.readiness import compute_readiness_score


def assemble_dossier(dossier_partial: dict, interview_updates: list, dossier_id: str,
                      source_type: str, language: str, version: int = 1,
                      research_gap_map: dict = None, source: dict = None,
                      parse_failed_fields: set = None) -> dict:
    """Assemble the full Dossier from Research Agent's partial result plus
    the interview's field updates.

    interview_updates: list of flat leaf dicts, each with field_code,
    section, key, value, evidence_label, sources, notes, filled_by,
    filled_at (the shape produced by normalizing continue_interview()'s
    per-turn field_update results over a full interview).

    research_gap_map: Research Agent's original gap_map (keyed by
    "section.key", as it comes out of run_research()), used to carry over
    its reasons for fields the interview also left unresolved.

    source: pre-built source metadata dict (e.g. uh_mapper's richer
    source_metadata for Unicorn Hunter entries) used as-is in place of
    the {"type": source_type, "reference": None} default.

    parse_failed_fields: "section.key" paths where continue_interview() saw
    the model attempt a field update but the JSON genuinely failed to parse
    (interview_agent.py's parse_failure case). Still unresolved fields here
    are labeled distinctly from a normal EMPTY gap, since the founder DID
    answer — the app failed to record it — rather than the field being
    intentionally skipped or never reached.
    """
    sections = copy.deepcopy(dossier_partial)
    research_gap_map = research_gap_map or {}
    parse_failed_fields = parse_failed_fields or set()

    for update in interview_updates:
        field_code = update.get("field_code")
        if field_code not in FIELD_REGISTRY:
            raise ValueError(f"interview_updates entry has unknown field_code: {field_code!r}")

        field = FIELD_REGISTRY[field_code]
        section, key = field["section"], field["key"]

        leaf = {
            "value": update["value"],
            "evidence_label": update["evidence_label"],
            "sources": update["sources"],
            "notes": update["notes"],
            "field_code": field_code,
            "filled_by": update["filled_by"],
            "filled_at": update["filled_at"],
        }
        sections.setdefault(section, {})[key] = leaf

    gap_map = {}
    for field_code, field in FIELD_REGISTRY.items():
        section, key = field["section"], field["key"]
        if key in sections.get(section, {}):
            continue
        field_path = f"{section}.{key}"
        if field_path in parse_failed_fields:
            gap_map[field_code] = "PARSE_FAILURE — founder answered but the response failed to parse; needs re-asking"
        else:
            gap_map[field_code] = research_gap_map.get(field_path, "EMPTY — not resolved during interview")

    readiness = compute_readiness_score(sections)

    now = datetime.now(timezone.utc).isoformat()

    return {
        "dossier_id": dossier_id,
        "version": version,
        "created_at": now,
        "updated_at": now,
        "source": source if source is not None else {"type": source_type, "reference": None},
        "language": language,
        "sections": sections,
        "gap_map": gap_map,
        "readiness": readiness,
        "status": readiness["status"],
    }

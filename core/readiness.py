"""Pure readiness scoring for the Idea Dossier — no LLM calls.

Implements idea_dossier_schema.md Section 4. core.field_registry remains
the single source of truth for field weights and mandatory fields; nothing
here duplicates that data.
"""

from datetime import datetime, timezone

from core.field_registry import FIELD_REGISTRY, MANDATORY_FIELDS, MAX_WEIGHTED_SCORE


def _is_present(field_code, sections):
    field = FIELD_REGISTRY[field_code]
    return field["key"] in sections.get(field["section"], {})


def compute_readiness_score(sections: dict, threshold: float = 0.70) -> dict:
    """Compute the readiness score for a Dossier's assembled sections dict."""
    present_codes = {code for code in FIELD_REGISTRY if _is_present(code, sections)}

    score_weighted = sum(FIELD_REGISTRY[code]["weight"] for code in present_codes)
    score_percentage = round(score_weighted / MAX_WEIGHTED_SCORE * 100)

    mandatory_missing = [code for code in MANDATORY_FIELDS if code not in present_codes]
    mandatory_passed = len(mandatory_missing) == 0

    unknown_fields = [code for code in FIELD_REGISTRY if code not in present_codes]

    status = "ready" if mandatory_passed and score_percentage >= threshold * 100 else "enriching"

    return {
        "score_weighted": score_weighted,
        "score_percentage": score_percentage,
        "mandatory_passed": mandatory_passed,
        "mandatory_missing": mandatory_missing,
        "unknown_fields": unknown_fields,
        "threshold": threshold,
        "status": status,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

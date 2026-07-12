"""Single source of truth for all 32 Idea Dossier fields.

This registry implements Section 1 of idea_dossier_schema.md. Every other
module (dossier assembly, readiness scoring, agents, storage) must import
field definitions from here — the registry must never be duplicated in
another file.
"""

FIELD_REGISTRY = {
    "A1": {"section": "opportunity", "key": "problem", "mandatory": True, "weight": 3},
    "A2": {"section": "opportunity", "key": "who_faces_it", "mandatory": False, "weight": 1},
    "A3": {"section": "opportunity", "key": "current_solutions", "mandatory": False, "weight": 1},
    "A4": {"section": "opportunity", "key": "why_insufficient", "mandatory": False, "weight": 1},
    "A5": {"section": "opportunity", "key": "why_now", "mandatory": False, "weight": 1},
    "B1": {"section": "customer_market", "key": "payer", "mandatory": True, "weight": 3},
    "B2": {"section": "customer_market", "key": "user", "mandatory": False, "weight": 1},
    "B3": {"section": "customer_market", "key": "decision_maker", "mandatory": False, "weight": 1},
    "B4": {"section": "customer_market", "key": "beneficiary", "mandatory": False, "weight": 1},
    "B5": {"section": "customer_market", "key": "geography", "mandatory": False, "weight": 1},
    "B6": {"section": "customer_market", "key": "market_size", "mandatory": False, "weight": 1},
    "B7": {"section": "customer_market", "key": "competitors", "mandatory": False, "weight": 1},
    "C1": {"section": "solution", "key": "description", "mandatory": True, "weight": 3},
    "C2": {"section": "solution", "key": "value", "mandatory": False, "weight": 1},
    "C3": {"section": "solution", "key": "differentiation", "mandatory": False, "weight": 1},
    "C4": {"section": "solution", "key": "usage", "mandatory": False, "weight": 1},
    "C5": {"section": "solution", "key": "complexity", "mandatory": False, "weight": 1},
    "D1": {"section": "business_model", "key": "who_pays", "mandatory": False, "weight": 1},
    "D2": {"section": "business_model", "key": "for_what", "mandatory": False, "weight": 1},
    "D3": {"section": "business_model", "key": "pricing", "mandatory": False, "weight": 1},
    "D4": {"section": "business_model", "key": "revenue_potential", "mandatory": False, "weight": 1},
    "D5": {"section": "business_model", "key": "initial_cost", "mandatory": False, "weight": 1},
    "D6": {"section": "business_model", "key": "channels", "mandatory": False, "weight": 1},
    "E1": {"section": "founder_resources", "key": "expertise", "mandatory": False, "weight": 1},
    "E2": {"section": "founder_resources", "key": "budget", "mandatory": True, "weight": 3},
    "E3": {"section": "founder_resources", "key": "time", "mandatory": True, "weight": 3},
    "E4": {"section": "founder_resources", "key": "partners", "mandatory": False, "weight": 1},
    "E5": {"section": "founder_resources", "key": "assets", "mandatory": False, "weight": 1},
    "F1": {"section": "success_definition", "key": "success_criteria", "mandatory": True, "weight": 3},
    "F2": {"section": "success_definition", "key": "kill_criteria", "mandatory": True, "weight": 3},
    "F3": {"section": "success_definition", "key": "risks", "mandatory": False, "weight": 1},
    "F4": {"section": "success_definition", "key": "assumptions", "mandatory": False, "weight": 1},
}

MANDATORY_FIELDS = [code for code, f in FIELD_REGISTRY.items() if f["mandatory"]]
MAX_WEIGHTED_SCORE = sum(f["weight"] for f in FIELD_REGISTRY.values())

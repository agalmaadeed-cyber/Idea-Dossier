"""Research Agent: converts raw idea text into a partially-filled, evidence-labeled Dossier."""

import json
import re
from datetime import datetime, timezone

from agents import call_agent
from core.field_registry import FIELD_REGISTRY

RESEARCH_AGENT_SYSTEM_PROMPT = """You are the Research Agent for Idea Dossier, a system that converts a raw
business idea or an Opportunity Report into a structured, evidence-labeled
Idea Dossier.

Your job covers three internal steps in a single pass:
1. Parse & Map — read the raw input and distribute its content across the
   Dossier's six sections (Opportunity, Customer & Market, Solution,
   Business Model, Founder & Resources, Success Definition).
2. Gap Analysis — classify every field as FILLED, PARTIAL, or EMPTY.
3. Web Research Pass — use the Web Search Tool to fill PARTIAL/EMPTY fields
   that are researchable (market size, competitors, pricing, timing signals).

INPUT
You will receive one of two input types:
- source_type = "unicorn_hunter": a full Opportunity Report text, following
  Unicorn Hunter's known structure (Problem Card, Solutions table,
  Evaluation report).
- source_type = "external": free-form text — a founder's note, a partner's
  proposal, or any unstructured idea description.

If source_type = "unicorn_hunter", apply this mapping before anything else:
- Problem Card sections -> Opportunity Definition (A1-A5) and Customer &
  Market (B1-B4)
- Report "Proposed Solution" + solutions table -> Solution (C1-C5)
- Report "Revenue Model" -> Business Model (D1-D6, partial)
- Report "Risks" -> Success Definition (F3)
- verification_rounds history -> Success Definition (F4, prior evidence)

If source_type = "external", extract whatever is explicitly present into the
same six sections. Do not force-fit vague text into a field — leave it EMPTY
if the input does not address it.

GAP ANALYSIS RULE
For every one of the Dossier's fields (see the full field list below),
assign exactly one status:
- FILLED — present and clear in the raw input
- PARTIAL — present but incomplete, vague, or needs external verification
- EMPTY — not addressed at all in the raw input

WEB RESEARCH RULE — MANDATORY
For every PARTIAL or EMPTY field that is researchable in principle (market
size, competitors, pricing benchmarks, timing/trend evidence), you MUST use
the Web Search Tool. Never rely on your own memory or training data for
market claims. This mirrors Unicorn Hunter's Agent 1 rule: research is not
optional.

Fields that are NOT researchable by web search — because they depend on the
founder personally — must be left EMPTY and listed in the gap_map for the
Interview Agent. Never guess these:
- founder_resources.expertise, budget, time, partners, assets
- success_definition.success_criteria, kill_criteria

EVIDENCE CLASSIFICATION — MANDATORY, EXACT RULE
You may only use three labels in this pass: CONFIRMED, ESTIMATE, UNKNOWN.
(ASSUMPTION and FOUNDER_OPINION are reserved for the Interview Agent and the
founder's own input — never assign them yourself.)

- CONFIRMED: the claim is directly and explicitly supported by one of:
  an official market research report (e.g. Statista, McKinsey, government or
  sector reports), an official company source (pricing page, annual report,
  press release), or a credible news source attributing a specific figure to
  a named origin. A verifiable source reference (link or named source + date)
  is REQUIRED in the "sources" field. No reference means no CONFIRMED label,
  regardless of how certain the claim seems.

- ESTIMATE: the claim is a computed or inferred conclusion built from partial
  or multiple sources, not a direct quote from one authoritative source
  (e.g. a market size approximated by combining several figures, a price
  range inferred from comparable products). The assumptions behind the
  estimate MUST be stated explicitly in the "notes" field.

- UNKNOWN: research found nothing usable — no figure, no trend, no partial
  source. Leave the field empty and record it in gap_map. Do NOT fill it
  with general knowledge or a plausible-sounding guess that was not
  produced by an actual search in this session.

Decisive test before labeling:
- If you can honestly write "According to [named source], the value is X" ->
  CONFIRMED.
- If you can honestly write "Based on [combined sources/calculation], the
  value is estimated around X" -> ESTIMATE.
- If you cannot honestly write either sentence -> UNKNOWN.

LANGUAGE
Respond in the same language as the raw input (Arabic input -> Arabic
output text values; English input -> English output text values). This
applies to human-readable text inside field values. JSON keys, evidence
labels, and status values always stay in English exactly as specified in
this prompt, regardless of input language.

OUTPUT FORMAT — JSON ONLY, NO PREAMBLE, NO MARKDOWN FENCES
Return exactly this structure:

{
  "dossier_partial": {
    "opportunity": {
      "problem": { "value": "...", "evidence_label": "...", "sources": [], "notes": "" },
      "who_faces_it": { ... },
      "current_solutions": { ... },
      "why_insufficient": { ... },
      "why_now": { ... }
    },
    "customer_market": {
      "payer": { ... }, "user": { ... }, "decision_maker": { ... },
      "beneficiary": { ... }, "geography": { ... }, "market_size": { ... },
      "competitors": { ... }
    },
    "solution": {
      "description": { ... }, "value": { ... }, "differentiation": { ... },
      "usage": { ... }, "complexity": { ... }
    },
    "business_model": {
      "who_pays": { ... }, "for_what": { ... }, "pricing": { ... },
      "revenue_potential": { ... }, "initial_cost": { ... }, "channels": { ... }
    },
    "founder_resources": {
      "expertise": { ... }, "budget": { ... }, "time": { ... },
      "partners": { ... }, "assets": { ... }
    },
    "success_definition": {
      "success_criteria": { ... }, "kill_criteria": { ... },
      "risks": { ... }, "assumptions": { ... }
    }
  },
  "gap_map": {
    "<field.path>": "EMPTY | PARTIAL — short reason, in the response language"
  },
  "research_summary": "Two sentences: how many fields were filled by
    research, and an honest note on source quality — same spirit as
    Unicorn Hunter's Input Quality Signal."
}

Only include a field object for fields with status FILLED or PARTIAL-with-
research-result. Fields left EMPTY should NOT appear inside dossier_partial —
they should appear ONLY in gap_map, so the Interview Agent knows exactly
what remains."""

_REVERSE_LOOKUP = {(f["section"], f["key"]): code for code, f in FIELD_REGISTRY.items()}


def _extract_text(response):
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")


def _extract_json_object(text):
    """Extract a JSON object from text that may contain preamble prose
    and/or markdown code fences around the JSON block (defensive: models
    sometimes narrate their search steps before the JSON despite
    instructions not to)."""
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        end = None
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        if end is not None:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        start = text.find("{", start + 1)

    return None


def _inject_metadata(dossier_partial):
    now = datetime.now(timezone.utc).isoformat()
    for section, fields in dossier_partial.items():
        for key, leaf in fields.items():
            if not isinstance(leaf, dict):
                continue
            field_code = _REVERSE_LOOKUP.get((section, key))
            if field_code:
                leaf["field_code"] = field_code
            leaf["filled_by"] = "research_agent"
            leaf["filled_at"] = now


def run_research(raw_input: str, source_type: str = "external") -> dict:
    """Call the Research Agent once and return a parsed, metadata-enriched result.

    Uses the Anthropic web_search tool (type: web_search_20250305,
    name: web_search, max_uses: 5) — same pattern as Unicorn Hunter's Agent 1.
    """
    user_message = f"source_type: {source_type}\n\nRAW INPUT:\n{raw_input}"

    response = call_agent(
        system_prompt=RESEARCH_AGENT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        max_tokens=8192,
    )

    raw_text = _extract_text(response)
    parsed = _extract_json_object(raw_text)

    if parsed is None:
        raise RuntimeError(
            "Research Agent returned text that could not be parsed as JSON.\n\n"
            f"Raw response text:\n{raw_text}"
        )

    dossier_partial = parsed.get("dossier_partial", {})
    _inject_metadata(dossier_partial)

    return {
        "dossier_partial": dossier_partial,
        "gap_map": parsed.get("gap_map", {}),
        "research_summary": parsed.get("research_summary", ""),
    }

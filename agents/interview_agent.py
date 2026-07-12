"""Interview Agent: asks the founder targeted, one-at-a-time questions about gaps Research Agent could not resolve."""

import json
import re
from datetime import datetime, timezone

from agents import call_agent
from core.field_registry import FIELD_REGISTRY, MANDATORY_FIELDS

INTERVIEW_AGENT_SYSTEM_PROMPT = """You are the Interview Agent for Idea Dossier. Research Agent has already
filled what it could from research. Your job is to ask the founder,
one question at a time, only about the gaps research could not resolve.

CONTEXT YOU RECEIVE AT THE START OF THE CONVERSATION
- gap_map: fields marked EMPTY or PARTIAL by Research Agent, each with a
  short reason.
- dossier_partial: everything Research Agent already filled, for reference.
  Use it to make your questions specific and informed. If a field is
  PARTIAL with a research estimate, mention that estimate and ask the
  founder to confirm, correct, or add to it — do not ask as if nothing
  was found.
- mandatory_fields: A1, B1, C1, F1, F2, E2, E3 (Problem, Target Customer,
  Solution, Success Criteria, Kill Criteria, Budget, Time Availability).

QUESTION ORDER — MANDATORY
Ask about gap_map fields in this priority:
1. Any mandatory_fields field still EMPTY or PARTIAL, in the order listed
   above.
2. All remaining non-mandatory gap_map fields, grouped by section
   (Opportunity -> Customer & Market -> Solution -> Business Model ->
   Founder & Resources -> Success Definition) for a natural conversation
   flow.
Never skip ahead to a non-mandatory field while a mandatory field is still
unresolved.

ONE QUESTION AT A TIME — MANDATORY
Ask exactly one question per turn. Wait for the founder's answer before
asking the next question. Do not batch multiple questions into one message.

If an answer is vague, incomplete, or you cannot confidently classify it,
ask ONE targeted follow-up question before moving to the next gap. Do not
move on with a low-quality answer just to keep pace.

Success criteria and kill criteria (F1, F2) can NEVER be inferred, guessed,
or suggested by you as if they were the founder's own conclusion. You may
help the founder articulate their answer (e.g. "what result in the first
90 days would make you call this a success?"), but the final content must
be the founder's own words, not your invention.

ANSWER CLASSIFICATION — MANDATORY, EXACT RULE
Every founder answer gets exactly one of these three labels (you never use
CONFIRMED/ESTIMATE/UNKNOWN in this agent — those are Research Agent's
labels only):

- CONFIRMED: the answer describes a factual, present reality the founder
  has direct, certain knowledge of about themselves or their venture
  (e.g. "I already have a signed partnership with X", "I have $20,000
  allocated for this"). The founder is the only possible authoritative
  source for facts about themselves — no external reference is required
  for this label in this agent.

- FOUNDER_OPINION: the answer is a confident judgment, estimate, or
  opinion the founder holds about something external (the market,
  customers, pricing) that cannot be independently verified by nature
  (e.g. "I believe customers will pay $50/month", "I have 5 years of
  relevant experience"). This is the default label for most
  Founder & Resources and Success Definition answers.

- ASSUMPTION: the founder explicitly signals their own uncertainty
  (e.g. "I think this might work but haven't tested it", "maybe two
  weeks, not sure"). Never upgrade an uncertain answer to
  FOUNDER_OPINION just because it sounds confident in tone — if the
  founder states uncertainty, respect it exactly as ASSUMPTION.

Decisive test before labeling:
- Is this a fact about the founder's own present situation, stated with
  certainty? -> CONFIRMED.
- Is this a confident judgment about something external? -> FOUNDER_OPINION.
- Did the founder signal doubt or uncertainty? -> ASSUMPTION.

LANGUAGE
Converse in the same language as the founder's input. Field values and
your questions follow the founder's language; JSON keys and evidence
labels always stay in English exactly as specified in this prompt.

OUTPUT FORMAT — TWO MODES

Mode 1 — asking a question (most turns):
Return plain conversational text only: the single question, in the
founder's language. No JSON in this mode.

Mode 2 — after receiving and classifying an answer:
Return exactly this JSON structure for the field just answered, so the
application can update the live Dossier panel immediately:

{
  "field_updated": "<field.path>",
  "value": { "value": "...", "evidence_label": "CONFIRMED | FOUNDER_OPINION | ASSUMPTION", "sources": [], "notes": "" },
  "next_action": "ask_next_question | ask_followup | interview_complete"
}

If next_action is "ask_next_question" or "ask_followup", follow this JSON
immediately with the next question in plain text, in the same turn.

If all gap_map fields (mandatory and non-mandatory) have been resolved —
either answered or explicitly left UNKNOWN by founder choice — set
next_action to "interview_complete" and do not ask anything further.

FOUNDER MAY DECLINE A FIELD
If the founder explicitly says they don't know or don't want to answer a
non-mandatory field, label it UNKNOWN (not ASSUMPTION — UNKNOWN means "not
provided", ASSUMPTION means "provided but uncertain") and move to the next
gap. Mandatory fields cannot be declined this way for F1/F2 (success/kill
criteria) — gently explain why these specifically need the founder's own
answer before moving on, but do not force an answer beyond one gentle
re-ask."""

_REVERSE_LOOKUP = {(f["section"], f["key"]): code for code, f in FIELD_REGISTRY.items()}


def _extract_text(response):
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")


def _extract_leading_json(text):
    """Find the first balanced JSON object in text, respecting quoted strings.

    Returns (parsed_dict, remainder_text) if a valid JSON object is found,
    otherwise (None, text).
    """
    start = text.find("{")
    if start == -1:
        return None, text

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

    if end is None:
        return None, text

    candidate = text[start:end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None, text

    # The model sometimes wraps the JSON in a ```json ... ``` fence despite
    # the prompt not asking for one; strip a leftover closing fence marker
    # so it doesn't leak into the next question text.
    remainder = text[end + 1:].strip()
    remainder = re.sub(r"^```\s*", "", remainder).strip()
    return parsed, remainder


def start_interview(gap_map: dict, dossier_partial: dict) -> tuple:
    """Start the interview and return (first_question_text, messages)."""
    initial_message = (
        f"gap_map:\n{json.dumps(gap_map, ensure_ascii=False)}\n\n"
        f"dossier_partial:\n{json.dumps(dossier_partial, ensure_ascii=False)}\n\n"
        f"mandatory_fields: {MANDATORY_FIELDS}\n\n"
        "Begin the interview now with the first question."
    )
    messages = [{"role": "user", "content": initial_message}]

    response = call_agent(system_prompt=INTERVIEW_AGENT_SYSTEM_PROMPT, messages=messages)
    reply_text = _extract_text(response)

    updated_messages = messages + [{"role": "assistant", "content": reply_text}]
    return reply_text, updated_messages


def continue_interview(messages: list, founder_answer: str) -> dict:
    """Send the founder's answer, classify it, and return the next question."""
    messages = messages + [{"role": "user", "content": founder_answer}]

    response = call_agent(system_prompt=INTERVIEW_AGENT_SYSTEM_PROMPT, messages=messages)
    reply_text = _extract_text(response)

    messages = messages + [{"role": "assistant", "content": reply_text}]

    parsed, remainder = _extract_leading_json(reply_text)

    field_update = None
    next_action = "ask_next_question"
    next_question = None

    if parsed is not None and "field_updated" in parsed:
        field_path = parsed["field_updated"]
        section, _, key = field_path.partition(".")
        field_code = _REVERSE_LOOKUP.get((section, key))

        value = parsed.get("value", {})
        if field_code:
            value["field_code"] = field_code
        value["filled_by"] = "interview_agent"
        value["filled_at"] = datetime.now(timezone.utc).isoformat()

        field_update = {"field_updated": field_path, "value": value}
        next_action = parsed.get("next_action", "ask_next_question")
        next_question = remainder if remainder and next_action != "interview_complete" else None
    else:
        next_question = reply_text.strip() or None

    return {
        "field_update": field_update,
        "next_question": next_question,
        "next_action": next_action,
        "messages": messages,
    }

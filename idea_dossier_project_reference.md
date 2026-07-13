# Idea Dossier — Project Reference Document
**For use in MVP Studio project conversations**
**Last updated:** July 2026
**Status:** Lite phase complete · Iterate phase goals #2 and #3 complete · Goal #1 (Supabase) pending

---

## 1. Project Overview

**Project Name:** Idea Dossier
**Type:** Internal multi-agent AI system, second project in MVP Studio (VDVE — Venture Development & Validation Engine, Stage 1)
**Purpose:** Enrich an idea (from Unicorn Hunter or raw founder input) into a structured, evidence-labeled Dossier that serves as the formal input contract for the Theoretical Validation Cycle.
**Repository:** `github.com/agalmaadeed-cyber/Idea-Dossier`, branch `master`

**Core Philosophy:** A Dossier is not a report — it organizes claims so they can be tested. Every field carries an evidence label. Machine-readable first (JSON), rendered Markdown second. Deterministic code over LLM judgment wherever a decision can be made without ambiguity.

---

## 2. System Architecture

### Two-Agent Pipeline + Deterministic Mapper

| Component | File | Role |
|---|---|---|
| UH Mapper | `core/uh_mapper.py` | Deterministic (no LLM) regex-based extraction from a Unicorn Hunter Opportunity Report Markdown file. Sole source of truth for UH-report field extraction. |
| Research Agent | `agents/research_agent.py` | Web-search-grounded gap filling. Accepts optional `existing_partial` — when provided, operates in delta-only mode (never restates pre-filled fields; a deterministic post-filter guarantees this regardless of model compliance). |
| Interview Agent | `agents/interview_agent.py` | One-question-at-a-time founder interview for gaps research cannot resolve. Classifies each answer as CONFIRMED / FOUNDER_OPINION / ASSUMPTION. |
| Assembly | `core/dossier_assembly.py` | Pure Python. Merges all sources into the final Dossier, computes readiness, accepts an optional pre-built `source` dict (see Section 5). |
| Readiness | `core/readiness.py` | Weighted scoring: mandatory fields ×3, soft fields ×1, max 46, 70% threshold (placeholder, uncalibrated). |
| Storage | `storage/db.py` | SQLite, full-snapshot versioning. Supabase migration not yet started. |
| UI | `app.py` | Streamlit chat flow with a live Dossier side panel. |

### Two Entry Paths

```
External raw idea ──────────────────────────► Research Agent ──► Interview Agent ──► Dossier
Unicorn Hunter report (.md upload/paste) ──► UH Mapper ──► Research Agent (delta-only) ──► Interview Agent ──► Dossier
```

The founder chooses explicitly at the start screen (Source Selector) — the system never infers source type from file content.

---

## 3. Key Design Decisions & Rationale (Iterate Phase)

### Decision 1 — Live Side Panel is Session-State-Driven, Storage-Agnostic
`st.session_state.dossier` is eagerly initialized as a full 32-field skeleton (every field `UNKNOWN`) from `core/field_registry.py`, built once per session (guarded). The panel reads only from this in-memory state, never directly from storage — this keeps the panel logic fully decoupled from the eventual SQLite → Supabase migration.

### Decision 2 — Every Field Write Passes Through a Guard Clause
Whether the source is Interview Agent's `field_update`, Research Agent's `dossier_partial`, or UH Mapper's `dossier_partial`, every write validates that `section`/`key` actually exist in `FIELD_REGISTRY` before writing. Invalid paths are logged to `field_update_warnings`, never crash the session, never silently create stray keys.

**Rationale:** Trusting any single source (even schema-aligned deterministic code) to never produce a malformed path is not an assumption this project makes — every write is validated structurally, not just trusted by design.

### Decision 3 — Evidence-Label Icons Are Never Merged
Five distinct icons (✅ CONFIRMED · 📊 ESTIMATE · 🗣️ FOUNDER_OPINION · ⚠️ ASSUMPTION · ❓ UNKNOWN), no visual collapsing of similar-confidence labels — collapsing icons would be an unlogged "upgrade" of evidence, which the project's evidence-classification principle forbids even visually.

### Decision 4 — UH Report Parsing Is 100% Deterministic, Single-Source
`uh_mapper.py` extracts exclusively from the UH report's fixed-format `## MVP Opportunity Report — Initial Analysis` / `After Field Verification` block (`**Label:** value` pattern) — never from the free-form Discovery Agent Output or Problem Card sections, which vary structurally between reports (confirmed via inspection of real UH report fixtures). All UH-mapped fields receive `evidence_label = "ESTIMATE"` unconditionally, with no attempt to infer `CONFIRMED` from source text — upgrading classification requires a human or a dedicated verification step, never a string match.

Fields with no Dossier field_code equivalent (idea name, sector, UH score, UH decision, next step) are captured as rich `source` metadata rather than discarded (see Section 5).

### Decision 5 — Research Agent's `source_type=="unicorn_hunter"` Branch Was Retired, Not Extended
The original prompt branch that asked the LLM to independently parse UH reports was removed entirely once `uh_mapper.py` existed, avoiding two independent, non-communicating paths to the same fields. `source_type="unicorn_hunter"` is retained as a signal, but its behavior is now driven by the presence of `existing_partial`, not by re-parsing raw UH text.

### Decision 6 — Delta-Only Output Is Enforced in Code, Not Just in the Prompt
Live testing proved prompt instructions alone are insufficient: Research Agent restated a pre-filled field (`success_definition.risks`) in two independent live runs despite an explicit "never restate" instruction. A deterministic post-filter (`_strip_prefilled_overlap()`) now unconditionally strips any field already present in `existing_partial` from the model's output, regardless of what the model returns. The prompt instruction is retained as a search-budget optimization, not as the safety guarantee.

**This is the single most important operating lesson from the Iterate phase:** prompt compliance is not a structural guarantee anywhere in this system. Deterministic code-level enforcement is required wherever correctness matters, confirmed by live-testing every such assumption before trusting it.

---

## 4. UH Report → Dossier Field Mapping (as implemented)

| UH Report Label | Dossier Field | Notes |
|---|---|---|
| Target Customer | B1 (payer) | |
| Problem | A1 | |
| Current User Situation | A3 | |
| Proposed Solution | C1 | |
| MVP Shape | C4 | |
| Market Testing Method | D6 | |
| Revenue Model | D3 **and** D4 | Same text written to both |
| Why Would the Customer Pay? | Merged into C2 alongside Proposed Solution text | Newline-separated, never overwrites |
| Risks | F3 | |
| What Changed After Field Verification + Field Verification Answers | F4 | Combined if both present |
| Idea Name, Sector, Score, Decision, Next Step | `source` metadata (not a Dossier field) | See Section 5 |

Fields not covered (A5, B2–B7, C3, C5, D1, D2, D5, E1–E5, F1, F2) surface via `gap_map`, filled by Research Agent (delta) and Interview Agent.

Extraction rule: uses `After Field Verification` block if present in the report, else falls back to `Initial Analysis`. Boundary detection stops only at the known set of target labels (not any bold text), to correctly capture multi-paragraph fields containing their own embedded bold sub-headings.

---

## 5. `source` Object — Final Schema (as implemented)

```json
// External entry path
"source": { "type": "external", "reference": null }

// Unicorn Hunter entry path
"source": {
    "type": "unicorn_hunter",
    "reference": "UH Idea ID: <n>",
    "uh_idea_name": "...",
    "uh_sector": "...",
    "uh_final_score": "...",
    "uh_final_decision": "...",
    "uh_next_step": "..."
}
```

`assemble_dossier()` accepts an optional `source: dict` parameter and uses it as-is when provided (built from `st.session_state.dossier["source"]`, itself set from `uh_mapper`'s output at merge time); falls back to the minimal external shape otherwise. This was a real bug fixed during Iterate (see Section 7) — the rich metadata was originally computed correctly but silently discarded before reaching the persisted Dossier.

---

## 6. Tech Stack

| Component | Choice | Notes |
|---|---|---|
| LLM | Anthropic API — claude-sonnet-4-6 | |
| Web Search | Anthropic Web Search Tool | `type: web_search_20250305`, max_uses: 5, Research Agent only |
| UI | Streamlit | Chat flow + `st.sidebar` live panel |
| Storage (current) | SQLite local | `storage/db.py`, full snapshots |
| Storage (planned) | Supabase — independent project, no shared DB with Unicorn Hunter | Iterate goal #1, not started |
| Hosting (current) | Local only | |
| Hosting (planned) | Streamlit Cloud | After Supabase migration |

---

## 7. Bugs Found and Fixed During Iterate Phase

| Bug | Discovery Method | Fix |
|---|---|---|
| Research Agent output never merged into panel skeleton | Manual review during Live Side Panel build | `merge_research_into_skeleton()` |
| `dossier_partial` from Research Agent invisible in panel until Interview touched the same field | Live browser test | `merge_research_into_skeleton()` called right after research completes |
| Research Agent restated a pre-filled field despite prompt instruction (delta-only violated) | Live API test, reproduced twice | `_strip_prefilled_overlap()` — deterministic code-level filter |
| `assemble_dossier()` hardcoded `source_type="external"` regardless of actual entry path | Manual end-to-end test inspecting the final persisted JSON (`DS-74843AED`) | Fixed to use `st.session_state.entry_path` |
| Rich UH `source_metadata` computed correctly but never passed into `assemble_dossier()`, silently discarded | Same manual end-to-end inspection | `assemble_dossier()` now accepts an optional pre-built `source` dict |

**Key lesson:** every one of these bugs was invisible to isolated unit/component tests and only surfaced via full live end-to-end walkthroughs. This is now a standing practice for this project — a component being individually correct does not guarantee the integrated flow is correct.

---

## 8. Non-Negotiable Constraints (Inherited from MVP Studio)

1. All code, prompts, variable names, comments, and UI strings in English only.
2. Conversation and explanation in Arabic; technical terms stay in English as-is.
3. Architecture before code — every design decision debated with options/tradeoffs before implementation.
4. One decision at a time.
5. Deterministic code over LLM judgment wherever correctness can be guaranteed without ambiguity — and every such assumption is live-tested before being trusted, not just prompt-engineered and assumed correct.
6. Fixture-based testing as the default to avoid repeated live API costs; one live test reserved for behaviors that cannot be verified any other way (e.g. confirming an LLM actually complies with an instruction).
7. Web search mandatory in Research Agent — no reliance on model memory for market claims.
8. Honest evidence labeling — never upgrade ASSUMPTION/ESTIMATE to CONFIRMED without a verifiable source or explicit founder confirmation.

---

## 9. Open Items for Next Session

1. **Goal #1 — Supabase migration.** Deferred until ready to deploy on Streamlit Cloud (Supabase setup is materially easier from a live cloud environment than local Windows dev, per prior decision). Independent Supabase project, no shared DB with Unicorn Hunter (file-based handoff only, preserving the Adapter pattern).
2. **Readiness threshold calibration** — real runs show UH-sourced ideas can reach 50%+ readiness immediately after research alone, before any interview. Worth revisiting the 70% placeholder once more real runs exist.
3. **Handoff trigger** (from `idea_dossier_specification.md` Section 8, still open): automatic for every Unicorn Hunter "Build" decision, or manual founder selection? Current implementation is manual (founder uploads/pastes deliberately) — this satisfies the question by default but was never explicitly re-confirmed as the final answer.
4. **Dossier versioning strategy** — full snapshots vs field-level change log (Section 8, still open, not addressed this Iterate cycle).
5. Deployment to Streamlit Cloud itself (after Goal #1).

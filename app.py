"""Idea Dossier — Streamlit chat UI (Lite scope + live side panel, Iterate).

Chat-only flow: raw idea -> Research Agent -> Interview Agent -> assembled
Dossier, persisted via storage/ (Supabase when configured, else local SQLite
— see storage/__init__.py). source_type is always "external" in this phase.
A live sidebar panel mirrors the Dossier skeleton as the interview fills it in.
"""

import copy
import json
import re
import uuid

import streamlit as st

from agents.research_agent import run_research
from agents.interview_agent import start_interview, continue_interview
from core.dossier_assembly import assemble_dossier
from core.field_registry import FIELD_REGISTRY, MANDATORY_FIELDS
from core.readiness import compute_readiness_score
from core.uh_mapper import parse_uh_report
from storage import init_db, save_dossier_version

WELCOME_MESSAGE = "شاركني فكرتك أو ارفع ملفاً من الشريط الجانبي."
_ARABIC_RE = re.compile(r"[؀-ۿ]")

_EVIDENCE_ICONS = {
    "CONFIRMED": "✅",
    "ESTIMATE": "📊",
    "FOUNDER_OPINION": "🗣️",
    "ASSUMPTION": "⚠️",
    "UNKNOWN": "❓",
}

# a.8 fix (cross-project evaluation, 2026-07-23): the sidebar is a narrow,
# fixed-width column -- rendering a long field's full value inline there
# (e.g. a two-sentence market_size research paragraph) makes it cramped
# and hard to read. Fields at or under this length still render inline in
# the sidebar as before; fields over it are redirected to a dedicated
# collapsible section in the main area instead (see
# _render_long_fields_expander()). Founder-approved threshold, 2026-07-23.
_SIDEBAR_LENGTH_THRESHOLD = 80


def _detect_language(text: str) -> str:
    return "ar" if _ARABIC_RE.search(text) else "en"


def _generate_dossier_id() -> str:
    return "DS-" + uuid.uuid4().hex[:8].upper()


def _flatten_field_update(nested: dict) -> dict:
    """Convert continue_interview()'s {"field_updated": "...", "value": {...}}
    shape into the flat leaf shape assemble_dossier() expects."""
    leaf = nested["value"]
    section, key = nested["field_updated"].split(".", 1)
    return {
        "field_code": leaf["field_code"],
        "section": section,
        "key": key,
        "value": leaf["value"],
        "evidence_label": leaf["evidence_label"],
        "sources": leaf["sources"],
        "notes": leaf["notes"],
        "filled_by": leaf["filled_by"],
        "filled_at": leaf["filled_at"],
    }


def _dossier_to_markdown(dossier: dict) -> str:
    lines = [f"# Idea Dossier — {dossier['dossier_id']} (v{dossier['version']})", ""]
    lines.append(f"**Status:** {dossier['status']} — **Readiness:** {dossier['readiness']['score_percentage']}%")
    lines.append("")
    for section_name, fields in dossier["sections"].items():
        lines.append(f"## {section_name}")
        for field_key, leaf in fields.items():
            lines.append(f"- **{field_key}** [{leaf['evidence_label']}]: {leaf['value']}")
        lines.append("")
    if dossier["gap_map"]:
        lines.append("## Remaining Gaps")
        for field_code, reason in dossier["gap_map"].items():
            lines.append(f"- **{field_code}**: {reason}")
        lines.append("")
    return "\n".join(lines)


def _render_chat_history():
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


# ---------------------------------------------------------------------------
# Live side panel (Iterate)
# ---------------------------------------------------------------------------

def build_dossier_skeleton() -> dict:
    """Build a full Dossier "sections" skeleton from FIELD_REGISTRY, every
    leaf initialized as UNKNOWN/empty, matching dossier_assembly.py's
    sections shape (section -> {key -> leaf})."""
    sections = {}
    for code, field in FIELD_REGISTRY.items():
        section, key = field["section"], field["key"]
        sections.setdefault(section, {})[key] = {
            "value": None,
            "evidence_label": "UNKNOWN",
            "sources": [],
            "notes": None,
            "field_code": code,
            "filled_by": None,
            "filled_at": None,
        }
    return {"sections": sections}


def _apply_field_update_to_dossier(dossier: dict, field_update: dict):
    """Write a continue_interview() field_update into the live dossier
    skeleton. Never raises — an unrecognized section/key (e.g. a model
    hallucination) is simply reported back as None instead of writing.

    Returns the "section.key" path on success, or None if the section/key
    don't exist in the skeleton.
    """
    section, _, key = field_update["field_updated"].partition(".")
    sections = dossier["sections"]
    if section in sections and key in sections[section]:
        sections[section][key] = field_update["value"]
        return field_update["field_updated"]
    return None


def _merge_research_leaves(sections: dict, dossier_partial: dict):
    """Pure merge core for merge_research_into_skeleton(). dossier_partial is
    already nested by section, so section/key come from the dict traversal
    itself (unlike interview_agent's "section.key" field_updated strings).
    Same guard-clause validation as _apply_field_update_to_dossier — never
    raises on an unrecognized section/key.

    Returns (merged_paths, invalid_paths), both lists of "section.key".
    """
    merged = []
    invalid = []
    for section, fields in dossier_partial.items():
        for key, leaf in fields.items():
            if section in sections and key in sections[section]:
                sections[section][key] = leaf
                merged.append(f"{section}.{key}")
            else:
                invalid.append(f"{section}.{key}")
    return merged, invalid


def merge_research_into_skeleton(dossier_partial: dict) -> list:
    """Merge Research Agent's dossier_partial into st.session_state.dossier,
    once, right after research completes and before the interview starts.

    Does not touch last_updated_field — bulk research fills should render
    already "settled" in the panel (correct icon, no highlight box), unlike
    the single most-recently-answered interview field.

    Returns the list of successfully merged "section.key" paths.
    """
    sections = st.session_state.dossier["sections"]
    merged, invalid = _merge_research_leaves(sections, dossier_partial)

    for path in invalid:
        st.session_state.setdefault("field_update_warnings", []).append(path)

    return merged


def _flatten_dossier_partial_to_values(dossier_partial: dict) -> dict:
    """Flatten a dossier_partial dict (section -> {key -> leaf}) into a flat
    {"section.key": value} dict — the shape Research Agent's PRE-FILLED
    FIELDS prompt section expects for existing_partial. Only the value is
    needed; Research Agent doesn't need evidence_label/sources/etc. for
    fields it must not re-derive."""
    flat = {}
    for section, fields in dossier_partial.items():
        for key, leaf in fields.items():
            flat[f"{section}.{key}"] = leaf["value"]
    return flat


def _merge_dossier_partials(base: dict, additional: dict) -> dict:
    """Combine two dossier_partial dicts (section -> {key: leaf}) into one,
    with `additional`'s fields taking precedence on any overlapping key.
    Used to combine uh_mapper's fields with Research Agent's delta fields
    into the single dossier_partial assemble_dossier() expects later."""
    combined = copy.deepcopy(base)
    for section, fields in additional.items():
        combined.setdefault(section, {}).update(fields)
    return combined


def _sections_for_readiness(sections: dict) -> dict:
    """compute_readiness_score() determines a field's presence by key
    membership, but the live skeleton keeps every field present as an
    UNKNOWN placeholder. Build a sparse (filled-only) view so the score
    reflects actual progress instead of showing 100% from the start."""
    sparse = {}
    for section_name, fields in sections.items():
        filled = {key: leaf for key, leaf in fields.items() if leaf["evidence_label"] != "UNKNOWN"}
        if filled:
            sparse[section_name] = filled
    return sparse


def _humanize_key(key: str) -> str:
    return key.replace("_", " ").title()


def _active_section(sections: dict, last_updated_field) -> str:
    if last_updated_field:
        return last_updated_field.split(".", 1)[0]

    for code in MANDATORY_FIELDS:
        field = FIELD_REGISTRY[code]
        leaf = sections.get(field["section"], {}).get(field["key"])
        if leaf and leaf["evidence_label"] == "UNKNOWN":
            return field["section"]

    # All mandatory fields already resolved; default to the first section.
    return next(iter(FIELD_REGISTRY.values()))["section"]


def render_dossier_panel():
    sections = st.session_state.dossier["sections"]
    readiness = compute_readiness_score(_sections_for_readiness(sections))

    st.subheader("لوحة الـ Dossier الحية")
    st.metric("نسبة الجاهزية", f"{readiness['score_percentage']}%")
    st.progress(readiness["score_percentage"] / 100)

    last_updated = st.session_state.get("last_updated_field")
    active_section = _active_section(sections, last_updated)

    for section_name, fields in sections.items():
        filled_count = sum(1 for leaf in fields.values() if leaf["evidence_label"] != "UNKNOWN")
        total_count = len(fields)
        with st.expander(
            f"{section_name} ({filled_count}/{total_count})",
            expanded=(section_name == active_section),
        ):
            for key, leaf in fields.items():
                icon = _EVIDENCE_ICONS.get(leaf["evidence_label"], "❓")
                label = _humanize_key(key)
                if leaf["evidence_label"] == "UNKNOWN":
                    line = f"{icon} {label}"
                elif _is_long_field(leaf):
                    # a.8 fix: long content redirected to the main-area
                    # expander (_render_long_fields_expander()) instead of
                    # being crammed into the narrow sidebar column.
                    line = f"{icon} {label} — 📄 التفاصيل في الأعلى"
                else:
                    line = f"{icon} {label}: {leaf['value']}"

                if f"{section_name}.{key}" == last_updated:
                    st.success(line)
                else:
                    st.markdown(line)

    for warning in st.session_state.get("field_update_warnings", []):
        st.warning(f"تعذر تحديث الحقل في اللوحة الجانبية: {warning}")


def _is_long_field(leaf: dict) -> bool:
    """Pure predicate, no Streamlit dependency -- a.8 fix (cross-project
    evaluation, 2026-07-23). A field is "long" (redirected to the
    main-area expander instead of the sidebar) only if it's actually
    filled (not UNKNOWN) and its value's length exceeds the founder-set
    threshold. Kept as its own testable function rather than inlined
    twice (once in the sidebar loop, once in the expander collector)."""
    if leaf["evidence_label"] == "UNKNOWN":
        return False
    value = leaf.get("value", "")
    return isinstance(value, str) and len(value) > _SIDEBAR_LENGTH_THRESHOLD


def _collect_long_fields(sections: dict) -> list:
    """Pure, no Streamlit dependency -- a.8 fix. Returns
    [(icon, humanized_label, value), ...] for every long field across all
    sections, in section/insertion order. Used by
    _render_long_fields_expander(); factored out so the actual
    long-vs-short classification logic is unit-testable without a live
    Streamlit script context."""
    collected = []
    for fields in sections.values():
        for key, leaf in fields.items():
            if _is_long_field(leaf):
                icon = _EVIDENCE_ICONS.get(leaf["evidence_label"], "❓")
                collected.append((icon, _humanize_key(key), leaf["value"]))
    return collected


def _render_long_fields_expander():
    """Main-area counterpart to render_dossier_panel()'s sidebar summary
    (a.8 fix, cross-project evaluation, 2026-07-23). Every filled field
    whose value exceeds _SIDEBAR_LENGTH_THRESHOLD gets its full text shown
    here instead of the cramped sidebar column -- collapsed by default so
    it never displaces the active chat conversation; the founder opens it
    only when they actually want to read the longer research paragraphs.
    Renders nothing at all if there are no long fields yet (nothing to
    show early in a fresh interview)."""
    long_fields = _collect_long_fields(st.session_state.dossier["sections"])

    if not long_fields:
        return

    with st.expander(f"📄 تفاصيل إضافية ({len(long_fields)})", expanded=False):
        for icon, label, value in long_fields:
            st.markdown(f"**{icon} {label}**")
            st.markdown(value)
            st.divider()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _reset_session_state():
    st.session_state.stage = "awaiting_input"
    st.session_state.chat_history = [{"role": "assistant", "content": WELCOME_MESSAGE}]
    st.session_state.dossier_partial = None
    st.session_state.gap_map = None
    st.session_state.interview_messages = None
    st.session_state.interview_updates = []
    st.session_state.dossier_id = None
    st.session_state.final_dossier = None
    st.session_state.raw_input = None
    st.session_state.entry_path = None
    st.session_state.language = "ar"
    st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1
    st.session_state.dossier = build_dossier_skeleton()
    st.session_state.last_updated_field = None
    st.session_state.field_update_warnings = []
    st.session_state.parse_failed_fields = set()


def _init_session_state():
    if "stage" not in st.session_state:
        st.session_state.stage = "awaiting_input"
        st.session_state.chat_history = [{"role": "assistant", "content": WELCOME_MESSAGE}]
        st.session_state.dossier_partial = None
        st.session_state.gap_map = None
        st.session_state.interview_messages = None
        st.session_state.interview_updates = []
        st.session_state.dossier_id = None
        st.session_state.final_dossier = None
        st.session_state.raw_input = None
        st.session_state.entry_path = None
        st.session_state.language = "ar"
        st.session_state.uploader_key = 0
        st.session_state.last_updated_field = None
        st.session_state.field_update_warnings = []
        st.session_state.parse_failed_fields = set()

    if "dossier" not in st.session_state:
        st.session_state.dossier = build_dossier_skeleton()


# ---------------------------------------------------------------------------
# App flow
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Idea Dossier", page_icon="📋")
    init_db()

    _init_session_state()

    with st.sidebar:
        render_dossier_panel()

    st.title("Idea Dossier")
    # a.8 fix (cross-project evaluation, 2026-07-23): rendered once here,
    # stage-independently, same placement pattern as the sidebar panel
    # above -- collapsed by default, so it never displaces the active
    # chat conversation in any stage.
    _render_long_fields_expander()

    if st.session_state.stage == "awaiting_input":
        _render_chat_history()

        with st.sidebar:
            st.header("طريقة البدء")
            input_mode = st.radio(
                "اختر طريقة البدء",
                ["فكرة خارجية", "تقرير Unicorn Hunter"],
                key="input_mode",
            )

            if input_mode == "فكرة خارجية":
                st.header("رفع فكرة كملف")
                uploaded_file = st.file_uploader(
                    "ارفع ملف نصي (.txt أو .md)",
                    type=["txt", "md"],
                    key=f"uploader_{st.session_state.uploader_key}",
                )
                uh_uploaded_file = None
                uh_pasted_text = ""
                uh_submit = False
            else:
                uploaded_file = None
                st.header("رفع تقرير Unicorn Hunter")
                uh_uploaded_file = st.file_uploader(
                    "ارفع ملف تقرير Unicorn Hunter (.md)",
                    type=["md"],
                    key=f"uh_uploader_{st.session_state.uploader_key}",
                )
                uh_pasted_text = st.text_area(
                    "أو الصق نص التقرير هنا مباشرةً",
                    key=f"uh_paste_{st.session_state.uploader_key}",
                )
                uh_submit = st.button("ابدأ من تقرير Unicorn Hunter")

        if input_mode == "فكرة خارجية":
            typed_input = st.chat_input("شاركني فكرتك...")

            raw_input = None
            if uploaded_file is not None:
                raw_input = uploaded_file.read().decode("utf-8")
            elif typed_input:
                raw_input = typed_input

            if raw_input:
                st.session_state.chat_history.append({"role": "user", "content": raw_input})
                st.session_state.raw_input = raw_input
                st.session_state.entry_path = "external"
                st.session_state.stage = "researching"
                st.rerun()
        else:
            raw_uh_markdown = None
            if uh_uploaded_file is not None:
                raw_uh_markdown = uh_uploaded_file.read().decode("utf-8")
            elif uh_submit and uh_pasted_text.strip():
                raw_uh_markdown = uh_pasted_text

            if raw_uh_markdown:
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": "📄 تم رفع تقرير Unicorn Hunter.",
                })
                st.session_state.raw_input = raw_uh_markdown
                st.session_state.entry_path = "unicorn_hunter"
                st.session_state.stage = "researching"
                st.rerun()

    elif st.session_state.stage == "researching":
        _render_chat_history()

        with st.spinner("جاري البحث..."):
            pre_filled_dossier_partial = {}

            if st.session_state.entry_path == "unicorn_hunter":
                try:
                    uh_result = parse_uh_report(st.session_state.raw_input)
                except Exception as e:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": f"حدث خطأ أثناء تحليل تقرير Unicorn Hunter، حاول مرة أخرى.\n\nتفاصيل الخطأ: {e}",
                    })
                    st.session_state.stage = "awaiting_input"
                    st.rerun()

                pre_filled_dossier_partial = uh_result["dossier_partial"]
                merge_research_into_skeleton(pre_filled_dossier_partial)
                st.session_state.dossier["source"] = uh_result["source_metadata"]

                if uh_result["parse_warnings"]:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": (
                            "ملاحظة: لم يتم العثور على بعض الحقول المتوقعة في تقرير Unicorn Hunter:\n"
                            + "\n".join(f"- {w}" for w in uh_result["parse_warnings"])
                        ),
                    })

            try:
                research_result = run_research(
                    st.session_state.raw_input,
                    source_type="unicorn_hunter" if st.session_state.entry_path == "unicorn_hunter" else "external",
                    existing_partial=_flatten_dossier_partial_to_values(pre_filled_dossier_partial) or None,
                )
            except Exception as e:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"حدث خطأ أثناء البحث، حاول مرة أخرى بصياغة مختلفة.\n\nتفاصيل الخطأ: {e}",
                })
                st.session_state.stage = "awaiting_input"
                st.rerun()

            st.session_state.dossier_partial = _merge_dossier_partials(
                pre_filled_dossier_partial, research_result["dossier_partial"]
            )
            st.session_state.gap_map = research_result["gap_map"]
            st.session_state.dossier_id = _generate_dossier_id()
            st.session_state.language = _detect_language(st.session_state.raw_input)
            st.session_state.chat_history.append(
                {"role": "assistant", "content": research_result["research_summary"]}
            )

            merge_research_into_skeleton(research_result["dossier_partial"])

            try:
                first_question, interview_messages = start_interview(
                    st.session_state.gap_map, st.session_state.dossier_partial
                )
            except Exception as e:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"تم البحث بنجاح، لكن حدث خطأ عند بدء المقابلة. حاول مرة أخرى.\n\nتفاصيل الخطأ: {e}",
                })
                st.session_state.stage = "awaiting_input"
                st.rerun()

            st.session_state.interview_messages = interview_messages
            st.session_state.chat_history.append({"role": "assistant", "content": first_question})
            st.session_state.stage = "interviewing"

        st.rerun()

    elif st.session_state.stage == "interviewing":
        _render_chat_history()

        answer = st.chat_input("اكتب إجابتك هنا...")

        if answer:
            st.session_state.chat_history.append({"role": "user", "content": answer})

            try:
                result = continue_interview(st.session_state.interview_messages, answer)
            except Exception as e:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"حدث خطأ أثناء معالجة إجابتك، حاول مرة أخرى.\n\nتفاصيل الخطأ: {e}",
                })
                st.rerun()

            st.session_state.interview_messages = result["messages"]

            if result["field_update"] is not None:
                st.session_state.interview_updates.append(_flatten_field_update(result["field_update"]))
                st.session_state.parse_failed_fields.discard(result["field_update"]["field_updated"])

                updated_path = _apply_field_update_to_dossier(st.session_state.dossier, result["field_update"])
                if updated_path:
                    st.session_state.last_updated_field = updated_path
                else:
                    st.session_state.setdefault("field_update_warnings", []).append(
                        result["field_update"]["field_updated"]
                    )
            elif result.get("parse_failure") and result.get("failed_field_path"):
                st.session_state.parse_failed_fields.add(result["failed_field_path"])

            if result["next_question"] is not None:
                st.session_state.chat_history.append({"role": "assistant", "content": result["next_question"]})

            if result["next_action"] == "interview_complete":
                try:
                    final_dossier = assemble_dossier(
                        st.session_state.dossier_partial,
                        st.session_state.interview_updates,
                        st.session_state.dossier_id,
                        source_type=st.session_state.entry_path,
                        language=st.session_state.language,
                        research_gap_map=st.session_state.gap_map,
                        source=st.session_state.dossier.get("source"),
                        parse_failed_fields=st.session_state.parse_failed_fields,
                    )
                    save_dossier_version(final_dossier)
                except Exception as e:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": f"حدث خطأ أثناء تجميع أو حفظ الـ Dossier.\n\nتفاصيل الخطأ: {e}",
                    })
                    st.rerun()

                st.session_state.final_dossier = final_dossier
                readiness = final_dossier["readiness"]
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": (
                        "تم! هذا هو Dossier الفكرة.\n\n"
                        f"نسبة الجاهزية: {readiness['score_percentage']}% — الحالة: {final_dossier['status']}"
                    ),
                })
                st.session_state.stage = "complete"

            st.rerun()

    elif st.session_state.stage == "complete":
        _render_chat_history()

        dossier = st.session_state.final_dossier
        md_text = _dossier_to_markdown(dossier)

        st.markdown("---")
        st.markdown(md_text)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "تحميل JSON",
                data=json.dumps(dossier, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name=f"{dossier['dossier_id']}.json",
                mime="application/json",
            )
        with col2:
            st.download_button(
                "تحميل Markdown",
                data=md_text.encode("utf-8"),
                file_name=f"{dossier['dossier_id']}.md",
                mime="text/markdown",
            )

        if st.button("فكرة جديدة"):
            _reset_session_state()
            st.rerun()


if __name__ == "__main__":
    main()

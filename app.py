"""Idea Dossier — Streamlit chat UI (Lite scope).

Chat-only flow: raw idea -> Research Agent -> Interview Agent -> assembled
Dossier, persisted via storage/db.py. No live side-panel (deferred to
Iterate). source_type is always "external" in this phase.
"""

import json
import re
import uuid

import streamlit as st

from agents.research_agent import run_research
from agents.interview_agent import start_interview, continue_interview
from core.dossier_assembly import assemble_dossier
from storage.db import init_db, save_dossier_version

WELCOME_MESSAGE = "شاركني فكرتك أو ارفع ملفاً من الشريط الجانبي."
_ARABIC_RE = re.compile(r"[؀-ۿ]")

st.set_page_config(page_title="Idea Dossier", page_icon="📋")

init_db()


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
    st.session_state.language = "ar"
    st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1


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
        st.session_state.language = "ar"
        st.session_state.uploader_key = 0


_init_session_state()

st.title("Idea Dossier")

if st.session_state.stage == "awaiting_input":
    _render_chat_history()

    with st.sidebar:
        st.header("رفع فكرة كملف")
        uploaded_file = st.file_uploader(
            "ارفع ملف نصي (.txt أو .md)",
            type=["txt", "md"],
            key=f"uploader_{st.session_state.uploader_key}",
        )

    typed_input = st.chat_input("شاركني فكرتك...")

    raw_input = None
    if uploaded_file is not None:
        raw_input = uploaded_file.read().decode("utf-8")
    elif typed_input:
        raw_input = typed_input

    if raw_input:
        st.session_state.chat_history.append({"role": "user", "content": raw_input})
        st.session_state.raw_input = raw_input
        st.session_state.stage = "researching"
        st.rerun()

elif st.session_state.stage == "researching":
    _render_chat_history()

    with st.spinner("جاري البحث..."):
        try:
            research_result = run_research(st.session_state.raw_input, source_type="external")
        except Exception as e:
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": f"حدث خطأ أثناء البحث، حاول مرة أخرى بصياغة مختلفة.\n\nتفاصيل الخطأ: {e}",
            })
            st.session_state.stage = "awaiting_input"
            st.rerun()

        st.session_state.dossier_partial = research_result["dossier_partial"]
        st.session_state.gap_map = research_result["gap_map"]
        st.session_state.dossier_id = _generate_dossier_id()
        st.session_state.language = _detect_language(st.session_state.raw_input)
        st.session_state.chat_history.append(
            {"role": "assistant", "content": research_result["research_summary"]}
        )

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

        if result["next_question"] is not None:
            st.session_state.chat_history.append({"role": "assistant", "content": result["next_question"]})

        if result["next_action"] == "interview_complete":
            try:
                final_dossier = assemble_dossier(
                    st.session_state.dossier_partial,
                    st.session_state.interview_updates,
                    st.session_state.dossier_id,
                    source_type="external",
                    language=st.session_state.language,
                    research_gap_map=st.session_state.gap_map,
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

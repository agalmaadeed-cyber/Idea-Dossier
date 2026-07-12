"""Shared Anthropic client and agent-call helpers for all Idea Dossier agents."""

import os

import streamlit as st
from anthropic import Anthropic

LANGUAGE_INSTRUCTION = """
IMPORTANT: Always respond in the same language as the user's input.
If the user writes in Arabic, respond entirely in Arabic.
If the user writes in English, respond entirely in English.
"""


def get_client():
    """Return an Anthropic client, reading the API key from Streamlit secrets
    with a fallback to the ANTHROPIC_API_KEY environment variable."""
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    except (KeyError, FileNotFoundError):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not found in st.secrets or environment variables."
        )
    return Anthropic(api_key=api_key)


def call_agent(system_prompt, messages, tools=None, model="claude-sonnet-4-6", max_tokens=4096):
    """Call the Anthropic Messages API and return the raw response.

    The language instruction is appended to every system prompt so all
    agents mirror the user's input language."""
    client = get_client()
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt + "\n" + LANGUAGE_INSTRUCTION,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    return client.messages.create(**kwargs)

# Idea Dossier

Idea Dossier converts a raw business idea (or an Opportunity Report) into a structured, evidence-labeled dossier through a chat-based flow: a Research Agent parses and fills what it can from web research, then an Interview Agent asks the founder targeted questions to close the remaining gaps. The result is assembled into a versioned dossier with a readiness score and persisted to storage.

This is a standalone project, independent of any other repository (e.g. Unicorn Hunter), built per `idea_dossier_specification.md`.

## Current scope (Lite phase)

- `source_type` is always `"external"` (free-form founder input or an uploaded `.txt`/`.md` file). Unicorn Hunter Opportunity Report ingestion is not wired into the UI yet.
- Storage is SQLite only (`storage/dossiers.db`), full-snapshot versioning. No Supabase.
- Chat-only UI (`st.chat_message` / `st.chat_input`). No live side-panel dossier view — the assembled dossier is shown only after the interview completes. Deferred to Iterate.

## Running locally

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Add your Anthropic API key to `.streamlit/secrets.toml` (copy `.streamlit/secrets.toml.example` and fill it in):
   ```
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
   Alternatively, set `ANTHROPIC_API_KEY` as an environment variable.
3. Run the app:
   ```
   streamlit run app.py
   ```

## Known Issues

- The Interview Agent generally respects mandatory-before-optional field ordering, but the exact internal order among mandatory fields is not currently enforced in code — it depends on the model's own judgment within the system prompt. All mandatory fields are still guaranteed to be resolved before the interview completes. Revisit in Iterate if this proves inconsistent across more test runs.

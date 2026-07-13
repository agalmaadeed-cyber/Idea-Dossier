"""Supabase storage for Idea Dossier snapshots — Iterate goal #1.

Mirrors storage/db.py's four function signatures and error contract exactly,
so storage/__init__.py's selector can expose either backend under the same
names with zero change to callers. The `dossiers` table is created manually
via the Supabase SQL Editor (see idea_dossier_project_reference.md) — nothing
here creates or migrates schema.

full_json is a JSONB column: the Supabase client serializes a Python dict to
a native JSON object when passed directly as a field value (verified against
the installed supabase/postgrest client — see manual_test_supabase_storage.py),
so it is passed as-is, never pre-serialized with json.dumps().
"""

import streamlit as st
from postgrest.exceptions import APIError
from supabase import Client, create_client

TABLE = "dossiers"

_UNIQUE_VIOLATION = "23505"


def _client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def init_db() -> None:
    """The table is created manually via the SQL Editor, not from code. This
    only verifies it's reachable, so a misconfiguration (bad URL/key, table
    not yet created) surfaces immediately at startup instead of mid-interview
    when a founder is about to lose an in-progress session."""
    try:
        _client().table(TABLE).select("dossier_id").limit(1).execute()
    except APIError as e:
        raise RuntimeError(
            "Supabase 'dossiers' table is not reachable. Confirm SUPABASE_URL/"
            "SUPABASE_SERVICE_ROLE_KEY are correct and the table has been "
            "created via the Supabase SQL Editor."
        ) from e


def save_dossier_version(dossier: dict) -> int:
    """Insert a new immutable snapshot row for this Dossier version.

    Raises ValueError if (dossier_id, version) already exists — same
    contract as storage/db.py's UNIQUE constraint violation, so callers
    can't tell which backend is active from this behavior alone.
    """
    payload = {
        "dossier_id": dossier["dossier_id"],
        "version": dossier["version"],
        "created_at": dossier["created_at"],
        "updated_at": dossier["updated_at"],
        "source_type": dossier["source"]["type"],
        "source_reference": dossier["source"].get("reference"),
        "language": dossier["language"],
        "full_json": dossier,
        "score_percentage": dossier["readiness"]["score_percentage"],
        "status": dossier["status"],
    }
    try:
        result = _client().table(TABLE).insert(payload).execute()
    except APIError as e:
        if e.code == _UNIQUE_VIOLATION:
            raise ValueError(
                f"Dossier version already exists: dossier_id={dossier['dossier_id']!r}, "
                f"version={dossier['version']!r}"
            ) from e
        raise
    return result.data[0]["id"]


def get_latest_version(dossier_id: str) -> dict | None:
    """Return the full parsed Dossier dict for the highest version of dossier_id, or None."""
    result = (
        _client()
        .table(TABLE)
        .select("full_json")
        .eq("dossier_id", dossier_id)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0]["full_json"] if result.data else None


def get_version(dossier_id: str, version: int) -> dict | None:
    """Return the full parsed Dossier dict for a specific version, or None."""
    result = (
        _client()
        .table(TABLE)
        .select("full_json")
        .eq("dossier_id", dossier_id)
        .eq("version", version)
        .execute()
    )
    return result.data[0]["full_json"] if result.data else None


def list_dossiers() -> list:
    """Return one lightweight summary row per unique dossier_id (latest version only),
    newest updated_at first. Does not include full_json.

    PostgREST's query builder has no direct equivalent to storage/db.py's
    correlated MAX(version) subquery, so this fetches all (dossier_id,
    version) rows and keeps the highest version per dossier_id client-side.
    Fine at this project's current scale; would need a Postgres view or RPC
    if the table grows large enough for that to matter.
    """
    result = (
        _client()
        .table(TABLE)
        .select("dossier_id, version, updated_at, source_type, language, score_percentage, status")
        .execute()
    )
    latest_by_id = {}
    for row in result.data or []:
        existing = latest_by_id.get(row["dossier_id"])
        if existing is None or row["version"] > existing["version"]:
            latest_by_id[row["dossier_id"]] = row
    return sorted(latest_by_id.values(), key=lambda r: r["updated_at"], reverse=True)

"""Storage backend selector.

Exposes init_db, save_dossier_version, get_latest_version, get_version, and
list_dossiers under one set of names regardless of backend, so app.py never
needs to know which one is active.

Supabase is used when both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are
present in st.secrets; otherwise this falls back to the local SQLite
implementation in storage/db.py (the default for anyone without Supabase
configured — zero behavior change from the Lite phase).
"""

import streamlit as st


def _supabase_configured() -> bool:
    try:
        return bool(st.secrets.get("SUPABASE_URL")) and bool(st.secrets.get("SUPABASE_SERVICE_ROLE_KEY"))
    except Exception:
        # st.secrets raises if .streamlit/secrets.toml doesn't exist at all
        # (e.g. a bare local dev environment with no secrets file yet).
        return False


if _supabase_configured():
    from storage.supabase_db import (
        get_latest_version,
        get_version,
        init_db,
        list_dossiers,
        save_dossier_version,
    )
else:
    from storage.db import (
        get_latest_version,
        get_version,
        init_db,
        list_dossiers,
        save_dossier_version,
    )

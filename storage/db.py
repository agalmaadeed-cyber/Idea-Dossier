"""SQLite storage for Idea Dossier snapshots — Lite phase only.

Implements the full-snapshot-per-version table from idea_dossier_schema.md
Section 5. full_json is the single source of truth for a row; the other
columns (source_type, language, score_percentage, status) are denormalized
copies kept only so listing/filtering doesn't require parsing JSON.

No Supabase here — that's an Iterate-phase addition.
"""

import json
import os
import sqlite3

DEFAULT_DB_PATH = "storage/dossiers.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dossiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dossier_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_reference TEXT,
    language TEXT NOT NULL,
    full_json TEXT NOT NULL,
    score_percentage INTEGER NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(dossier_id, version)
)
"""


def _connect(db_path: str) -> sqlite3.Connection:
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Create the dossiers table if it doesn't exist. Call once at app startup."""
    conn = _connect(db_path)
    try:
        conn.execute(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def save_dossier_version(dossier: dict, db_path: str = DEFAULT_DB_PATH) -> int:
    """Insert a new immutable snapshot row for this Dossier version.

    Raises ValueError if (dossier_id, version) already exists — versions
    are never overwritten.
    """
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO dossiers (
                dossier_id, version, created_at, updated_at, source_type,
                source_reference, language, full_json, score_percentage, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dossier["dossier_id"],
                dossier["version"],
                dossier["created_at"],
                dossier["updated_at"],
                dossier["source"]["type"],
                dossier["source"].get("reference"),
                dossier["language"],
                json.dumps(dossier, ensure_ascii=False),
                dossier["readiness"]["score_percentage"],
                dossier["status"],
            ),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as e:
        raise ValueError(
            f"Dossier version already exists: dossier_id={dossier['dossier_id']!r}, "
            f"version={dossier['version']!r}"
        ) from e
    finally:
        conn.close()


def get_latest_version(dossier_id: str, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    """Return the full parsed Dossier dict for the highest version of dossier_id, or None."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT full_json FROM dossiers WHERE dossier_id = ? ORDER BY version DESC LIMIT 1",
            (dossier_id,),
        ).fetchone()
        return json.loads(row["full_json"]) if row else None
    finally:
        conn.close()


def get_version(dossier_id: str, version: int, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    """Return the full parsed Dossier dict for a specific version, or None."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT full_json FROM dossiers WHERE dossier_id = ? AND version = ?",
            (dossier_id, version),
        ).fetchone()
        return json.loads(row["full_json"]) if row else None
    finally:
        conn.close()


def list_dossiers(db_path: str = DEFAULT_DB_PATH) -> list:
    """Return one lightweight summary row per unique dossier_id (latest version only),
    newest updated_at first. Does not include full_json."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT dossier_id, version, updated_at, source_type, language,
                   score_percentage, status
            FROM dossiers AS d
            WHERE version = (
                SELECT MAX(version) FROM dossiers WHERE dossier_id = d.dossier_id
            )
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

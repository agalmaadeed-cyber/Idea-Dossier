"""Offline unit tests for storage/__init__.py's backend selector.

No real Supabase credentials needed and no network calls: only tests the
_supabase_configured() decision logic (by monkeypatching st.secrets) and
confirms what storage.* currently resolves to at real import time in this
environment. The live save/get/list round-trip against a real Supabase
project is a separate, explicitly-gated test (manual_test_supabase_storage.py)
run only once real credentials are in place locally.
"""

import sys
from pathlib import Path
from unittest import mock

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import storage
from storage.db import save_dossier_version as sqlite_save_dossier_version


def test_fallback_to_sqlite_when_secrets_file_absent():
    class RaisingSecrets:
        def get(self, key, default=None):
            raise FileNotFoundError("no .streamlit/secrets.toml in this environment")

    with mock.patch.object(storage.st, "secrets", RaisingSecrets()):
        assert storage._supabase_configured() is False
    print("PASS: falls back to SQLite when secrets.toml is entirely absent")


def test_fallback_to_sqlite_when_supabase_keys_absent():
    with mock.patch.object(storage.st, "secrets", {"ANTHROPIC_API_KEY": "sk-test-not-real"}):
        assert storage._supabase_configured() is False
    print("PASS: falls back to SQLite when secrets exist but Supabase keys are absent")


def test_fallback_to_sqlite_when_only_one_supabase_key_present():
    with mock.patch.object(storage.st, "secrets", {"SUPABASE_URL": "https://example.supabase.co"}):
        assert storage._supabase_configured() is False
    print("PASS: falls back to SQLite when only one of the two required Supabase keys is present")


def test_supabase_selected_when_both_keys_present():
    with mock.patch.object(storage.st, "secrets", {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "fake-service-role-key-not-real",
    }):
        assert storage._supabase_configured() is True
    print("PASS: Supabase selected when both required secrets are present")


def test_current_real_import_resolves_to_sqlite():
    # This environment's actual .streamlit/secrets.toml (checked earlier) has
    # no Supabase keys yet, so the module-level selection that already ran at
    # `import storage` time above should have picked SQLite's functions.
    assert storage.save_dossier_version is sqlite_save_dossier_version
    print("PASS: storage.save_dossier_version currently resolves to the SQLite "
          "implementation (no Supabase secrets configured locally yet)")


if __name__ == "__main__":
    test_fallback_to_sqlite_when_secrets_file_absent()
    test_fallback_to_sqlite_when_supabase_keys_absent()
    test_fallback_to_sqlite_when_only_one_supabase_key_present()
    test_supabase_selected_when_both_keys_present()
    test_current_real_import_resolves_to_sqlite()
    print("\nAll storage-selector tests passed.")

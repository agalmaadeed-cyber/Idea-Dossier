"""Zero-cost test of storage/db.py, reusing the assembled-Dossier fixtures
from manual_test_assembly.py. Makes NO API calls.
"""

import copy
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR.parent))
sys.path.insert(0, str(SCRIPTS_DIR))

import manual_test_assembly as ma  # noqa: E402  (reuses its fixture-loading helpers)
from core.dossier_assembly import assemble_dossier  # noqa: E402
from storage.db import (  # noqa: E402
    get_latest_version,
    get_version,
    init_db,
    list_dossiers,
    save_dossier_version,
)

TEST_DB_PATH = str(SCRIPTS_DIR / "fixtures" / "test_dossiers.db")


def build_dossier_v1():
    research_fixture = json.loads((ma.FIXTURES_DIR / "sample_research_output.json").read_text(encoding="utf-8"))
    dossier_partial = research_fixture["dossier_partial"]
    research_gap_map = research_fixture["gap_map"]

    interview_text = ma.INTERVIEW_OUTPUT_TXT.read_text(encoding="utf-8")
    nested_updates = ma._extract_balanced_json_blocks_after_marker(interview_text, "--- field_update ---")
    interview_updates = [ma._flatten_field_update(u) for u in nested_updates]

    return assemble_dossier(
        dossier_partial=dossier_partial,
        interview_updates=interview_updates,
        dossier_id="DS-TEST-001",
        source_type="external",
        language="ar",
        research_gap_map=research_gap_map,
    )


def main():
    out = []

    db_file = Path(TEST_DB_PATH)
    if db_file.exists():
        db_file.unlink()

    out.append("=" * 70)
    out.append("STEP 1: init_db()")
    out.append("=" * 70)
    init_db(TEST_DB_PATH)
    out.append(f"OK — table created at {TEST_DB_PATH}")

    out.append("\n" + "=" * 70)
    out.append("STEP 2/3: save_dossier_version() for v1, then v2 (edited)")
    out.append("=" * 70)
    dossier_v1 = build_dossier_v1()
    row_id_1 = save_dossier_version(dossier_v1, TEST_DB_PATH)
    out.append(f"saved v1 -> row id={row_id_1}, dossier_id={dossier_v1['dossier_id']!r}, version={dossier_v1['version']}")

    dossier_v2 = copy.deepcopy(dossier_v1)
    dossier_v2["version"] = 2
    dossier_v2["sections"]["customer_market"]["payer"]["notes"] = "تم التحديث في نسخة v2 لأغراض الاختبار."
    dossier_v2["updated_at"] = "2026-07-13T00:00:00+00:00"
    row_id_2 = save_dossier_version(dossier_v2, TEST_DB_PATH)
    out.append(f"saved v2 -> row id={row_id_2}, dossier_id={dossier_v2['dossier_id']!r}, version={dossier_v2['version']}")

    out.append("\n" + "=" * 70)
    out.append("STEP 4: get_latest_version() must return v2")
    out.append("=" * 70)
    latest = get_latest_version(dossier_v1["dossier_id"], TEST_DB_PATH)
    check4 = latest is not None and latest["version"] == 2
    out.append(f"latest['version'] == 2: {check4} (got {latest['version'] if latest else None})")
    out.append(f"latest payer.notes: {latest['sections']['customer_market']['payer']['notes']}")
    assert check4

    out.append("\n" + "=" * 70)
    out.append("STEP 5: get_version(dossier_id, 1) must return original v1 unchanged")
    out.append("=" * 70)
    v1_fetched = get_version(dossier_v1["dossier_id"], 1, TEST_DB_PATH)
    check5 = v1_fetched == dossier_v1
    out.append(f"fetched v1 == original v1 dict: {check5}")
    out.append(f"v1 payer.notes (should NOT contain 'v2 لأغراض الاختبار'): {v1_fetched['sections']['customer_market']['payer']['notes']}")
    assert check5

    out.append("\n" + "=" * 70)
    out.append("STEP 6: list_dossiers() must show exactly ONE row (latest version only)")
    out.append("=" * 70)
    summaries = list_dossiers(TEST_DB_PATH)
    out.append(json.dumps(summaries, ensure_ascii=False, indent=2))
    check6 = len(summaries) == 1 and summaries[0]["version"] == 2
    out.append(f"row count == 1 and version == 2: {check6}")
    assert check6

    out.append("\n" + "=" * 70)
    out.append("STEP 7: duplicate insert of v2 must raise, never overwrite")
    out.append("=" * 70)
    try:
        save_dossier_version(dossier_v2, TEST_DB_PATH)
        out.append("FAIL: duplicate insert succeeded silently — this must not happen")
        raise AssertionError("duplicate insert did not raise")
    except ValueError as e:
        out.append(f"PASS: duplicate insert raised ValueError: {e}")

    text = "\n".join(out)
    print(text)

    report_path = SCRIPTS_DIR / "manual_test_storage_output.txt"
    report_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

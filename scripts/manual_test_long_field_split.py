"""
Manual test: sidebar/main-area content split by length (a.8 fix,
cross-project evaluation, 2026-07-23).

Verifies the pure classification logic (_is_long_field, _collect_long_fields
in app.py) directly, with zero Streamlit script-context dependency and zero
API cost -- these two functions were specifically factored out of the
Streamlit-calling render functions (render_dossier_panel(),
_render_long_fields_expander()) so the actual "is this field long enough to
redirect to the main area" decision is unit-testable on its own.

Run: python scripts/manual_test_long_field_split.py
Exit 0 = all assertions passed.
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# app.py runs top-level Streamlit calls (st.set_page_config etc.) only
# inside main(), never at import time, so importing it here is safe and
# makes no Streamlit calls.
import app

out = []

out.append("=" * 70)
out.append("PART 1: _is_long_field() -- pure predicate")
out.append("=" * 70)

short_leaf = {"evidence_label": "ESTIMATE", "value": "Short answer."}
assert app._is_long_field(short_leaf) is False, "a short (<=threshold) filled field must NOT be classified long"
out.append(f"PASS -- short field (len={len(short_leaf['value'])}) classified as NOT long")

long_value = "This is a much longer research paragraph. " * 3
long_leaf = {"evidence_label": "ESTIMATE", "value": long_value}
assert len(long_value) > app._SIDEBAR_LENGTH_THRESHOLD
assert app._is_long_field(long_leaf) is True, "a field over the threshold must be classified long"
out.append(f"PASS -- long field (len={len(long_value)}, threshold={app._SIDEBAR_LENGTH_THRESHOLD}) classified as long")

unknown_leaf = {"evidence_label": "UNKNOWN", "value": long_value}
assert app._is_long_field(unknown_leaf) is False, "UNKNOWN fields must never be classified long, regardless of any stale value"
out.append("PASS -- UNKNOWN field never classified long, even with a long stale value present")

out.append("\n" + "=" * 70)
out.append("PART 2: _collect_long_fields() -- gathers only the long ones, across sections")
out.append("=" * 70)

sections = {
    "opportunity": {
        "problem": {"evidence_label": "CONFIRMED", "value": "Short problem statement.", "field_code": "A1"},
    },
    "customer_market": {
        "market_size": {"evidence_label": "ESTIMATE", "value": long_value, "field_code": "B6"},
        "payer": {"evidence_label": "UNKNOWN", "value": "", "field_code": "B1"},
    },
}

collected = app._collect_long_fields(sections)
assert len(collected) == 1, f"expected exactly 1 long field (market_size), got {len(collected)}: {collected}"
icon, label, value = collected[0]
assert label == "Market Size", f"expected humanized label 'Market Size', got {label!r}"
assert value == long_value
out.append(f"PASS -- exactly 1 long field collected: icon={icon!r}, label={label!r}, correct full value preserved")

out.append("\n" + "=" * 70)
out.append("PART 3: no long fields -> empty list (nothing to render)")
out.append("=" * 70)

all_short_sections = {
    "opportunity": {
        "problem": {"evidence_label": "CONFIRMED", "value": "Short.", "field_code": "A1"},
    },
}
assert app._collect_long_fields(all_short_sections) == [], "an all-short Dossier must collect nothing"
out.append("PASS -- Dossier with no long fields collects an empty list")

out.append("\n" + "=" * 70)
out.append("ALL ASSERTIONS PASSED")
out.append("=" * 70)

print("\n".join(out))

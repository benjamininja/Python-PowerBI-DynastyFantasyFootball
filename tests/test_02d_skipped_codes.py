import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

rt = importlib.import_module("02d_fact_roster_transactions")


def _rows(*codes):
    return [{"transactionCode": c} for c in codes]


def test_known_skip_is_counted_without_a_warning():
    rows = _rows("LINEUP_CHANGE", "LINEUP_CHANGE", "CLAIM", "DROP", None)
    counts, unknown = rt.count_skipped_codes(rows)
    assert counts == {"LINEUP_CHANGE": 2}
    assert unknown == []
    lines = rt.skipped_code_lines(rows)
    assert lines == ["[info] skipped transaction code(s): LINEUP_CHANGE x2"]


def test_unknown_code_is_counted_with_a_warning():
    rows = _rows("LINEUP_CHANGE", "WAIVER_X", "WAIVER_X")
    counts, unknown = rt.count_skipped_codes(rows)
    assert counts == {"LINEUP_CHANGE": 1, "WAIVER_X": 2}
    assert unknown == ["WAIVER_X"]
    lines = rt.skipped_code_lines(rows)
    assert any(l.startswith("[warn]") and "WAIVER_X x2" in l for l in lines)
    assert not any(l.startswith("[warn]") and "LINEUP_CHANGE" in l for l in lines)


def test_no_skipped_rows_prints_nothing():
    assert rt.skipped_code_lines(_rows(None, "CLAIM", "DROP")) == []

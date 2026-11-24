"""check_data_model tolerates a published column the table's own `drops:` names (#671).

Built on small registry dicts and a temporary snapshot folder, never on data/.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import check_data_model as cdm
import etl_helpers


def _registry(drops=None):
    table = {
        "name": "dim_demo",
        "type": "dim",
        "schema": "football",
        "columns": [{"name": "demo_id", "dtype": "str", "sql_type": "text"}],
    }
    if drops:
        table["drops"] = drops
    return {"tables": [table], "other_tables": []}


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(etl_helpers, "DATA", tmp_path)

    def write(**cols):
        pd.DataFrame({"demo_id": ["a"], **{c: ["x"] for c in cols}}).to_parquet(tmp_path / "dim_demo.parquet")

    return write


def _run(registry, capsys, monkeypatch):
    monkeypatch.setattr(cdm, "key_errors", lambda t, by_name: [])
    monkeypatch.setattr(cdm, "sql_type_errors", lambda t: [])
    monkeypatch.setattr(cdm, "model_errors", lambda data: [])
    monkeypatch.setattr(cdm, "REQUIRED_FIELDS", ())
    rc = cdm.validate(registry)
    return rc, capsys.readouterr().out


def test_dropped_column_still_stored_warns_and_passes(snapshot, capsys, monkeypatch):
    snapshot(x_old=1)
    rc, out = _run(_registry([{"column": "x_old", "ticket": 597}]), capsys, monkeypatch)
    assert rc == 0
    warns = [ln for ln in out.splitlines() if ln.startswith("WARN")]
    assert len(warns) == 1
    assert "dim_demo" in warns[0] and "x_old" in warns[0] and "#597" in warns[0]
    assert "FAIL" not in out


def test_undeclared_column_without_drops_entry_fails(snapshot, capsys, monkeypatch):
    snapshot(x_old=1)
    rc, out = _run(_registry(), capsys, monkeypatch)
    assert rc == 1
    assert "parquet has undeclared columns" in out
    assert "WARN" not in out


def test_drops_entry_does_not_excuse_a_second_undeclared_column(snapshot, capsys, monkeypatch):
    snapshot(x_old=1, y_new=2)
    rc, out = _run(_registry([{"column": "x_old", "ticket": 597}]), capsys, monkeypatch)
    assert rc == 1
    fail = [ln for ln in out.splitlines() if "undeclared columns" in ln]
    assert len(fail) == 1
    assert "y_new" in fail[0] and "x_old" not in fail[0]


def test_drops_entry_for_a_column_already_gone_prints_nothing(snapshot, capsys, monkeypatch):
    snapshot()
    rc, out = _run(_registry([{"column": "x_old", "ticket": 597}]), capsys, monkeypatch)
    assert rc == 0, out
    assert "WARN" not in out

"""#300 done condition, on the published tables: no old_gsis_id sits in any
gsis_id column, and every DROPPED dim_nfl_players row is referenced."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest
import yaml

import etl_helpers as etl

NPL = "dim_nfl_players"


def gsis_tables():
    return [n for n, e in etl._registry().items()
            if "gsis_id" in [c["name"] for c in e.get("columns", [])]
            and etl.table_exists(n)]


FIXTURE_REGISTRY = {"tables": [
    {"name": NPL, "type": "dim", "grain": "gsis_id",
     "columns": [{"name": "gsis_id", "dtype": "str"}, {"name": "status", "dtype": "str"}]},
    {"name": "fact_pointer", "type": "fact", "grain": "pointer_key",
     "columns": [{"name": "pointer_key", "dtype": "str"}, {"name": "new_gsis_id", "dtype": "str"}]},
]}


@pytest.fixture
def only_a_prefixed_column_points(tmp_path, monkeypatch):
    registry = tmp_path / "registry.yml"
    registry.write_text(yaml.safe_dump(FIXTURE_REGISTRY), encoding="utf-8")
    monkeypatch.setattr(etl, "REGISTRY_PATH", registry)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    etl.write_table(NPL, pd.DataFrame({"gsis_id": ["A1", "B2"], "status": ["ACT", etl.DROPPED_STATUS]}))
    etl.write_table("fact_pointer", pd.DataFrame({"pointer_key": ["p1"], "new_gsis_id": ["B2"]}))


def test_a_new_gsis_id_column_alone_references_a_dropped_row(only_a_prefixed_column_points):
    assert etl.referenced_ids(NPL) == {"B2"}


def test_a_dropped_row_referenced_only_by_a_new_gsis_id_column_is_kept(only_a_prefixed_column_points):
    fresh = pd.DataFrame({"gsis_id": ["A1"], "status": ["ACT"]})
    assert etl.keep_dropped_ids(NPL, fresh)["gsis_id"].tolist() == ["A1", "B2"]


def test_the_registry_finds_the_tables_with_a_gsis_id_column():
    assert NPL in gsis_tables()
    assert len(gsis_tables()) > 1


def test_no_old_gsis_id_is_in_any_gsis_id_column():
    old = set(etl.read_table(etl.GSIS_LINK_TABLE)["old_gsis_id"])
    held = {n: len(old & set(etl.read_table(n, ["gsis_id"])["gsis_id"].dropna()))
            for n in gsis_tables() if n != NPL}
    assert {n: c for n, c in held.items() if c} == {}


def test_every_dropped_row_is_referenced():
    players = etl.read_table(NPL)
    dropped = set(players.loc[players["status"] == etl.DROPPED_STATUS, "gsis_id"])
    assert dropped <= etl.referenced_ids(NPL)

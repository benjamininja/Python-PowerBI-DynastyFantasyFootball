"""#300 done condition, on the published tables: no old_gsis_id sits in any
gsis_id column, and every DROPPED dim_nfl_players row is referenced."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pytest

import etl_helpers as etl

NPL = "dim_nfl_players"


def gsis_tables():
    return [n for n, e in etl._registry().items()
            if "gsis_id" in [c["name"] for c in e.get("columns", [])]
            and etl.table_exists(n)]


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

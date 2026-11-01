"""#299: 01e keeps any gsis_id nflverse stops returning, and name matching
prefers the live row over a kept (DROPPED) one.

Contract cases run on a temp data dir with a small fixture registry; the
04z cases load `disambiguate` out of the notebook cell, so they test the
code that ships.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest
import yaml

import etl_helpers as etl

NPL = "dim_nfl_players"
COLUMNS = ["gsis_id", "display_name", "status", "team_abbr", "position",
           "position_group", "entry_year", "weight"]

REGISTRY = {"tables": [
    {"name": NPL, "type": "dim", "grain": "gsis_id",
     "columns": [{"name": "gsis_id", "dtype": "str"}, {"name": "display_name", "dtype": "str"},
                 {"name": "status", "dtype": "str"}, {"name": "team_abbr", "dtype": "str"},
                 {"name": "position", "dtype": "str"}, {"name": "position_group", "dtype": "str"},
                 {"name": "entry_year", "dtype": "int32"}, {"name": "weight", "dtype": "float64"}]},
    {"name": "dim_rookie_prospect", "type": "dim", "grain": "player_key",
     "columns": [{"name": "player_key", "dtype": "str"}, {"name": "player_name", "dtype": "str"}]},
    {"name": etl.GSIS_LINK_TABLE, "type": "resolver", "grain": "old_gsis_id",
     "columns": [{"name": c, "dtype": "str"} for c in etl.GSIS_LINK_COLUMNS]},
]}


@pytest.fixture
def store(tmp_path, monkeypatch):
    registry = tmp_path / "registry.yml"
    registry.write_text(yaml.safe_dump(REGISTRY), encoding="utf-8")
    monkeypatch.setattr(etl, "REGISTRY_PATH", registry)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    return tmp_path


def rows(*specs):
    return pd.DataFrame(specs, columns=COLUMNS).astype({"entry_year": "int32"})


def person(gsis, name, status="ACT", team="DAL", pos="WR", year=2020, weight=200.0):
    return (gsis, name, status, team, pos, pos, year, weight)


STORED = rows(person("A1", "Ann Alpha"), person("B2", "Bo Beta", "CUT", year=2018, weight=215.0),
              person("C3", "Cy Gamma", "RES", pos="DB", year=2022, weight=190.5))
FRESH = rows(person("A1", "Ann Alpha", "RET", year=2020, weight=201.0),
             person("D4", "Di Delta", "ACT", year=2025))


def stored_table(df):
    etl.write_table(NPL, df)
    return etl.read_table(NPL)


class TestKeepDroppedIds:
    def test_dropped_id_is_kept_after_the_fresh_rows(self, store):
        stored_table(STORED)
        out = etl.keep_dropped_ids(NPL, FRESH)
        assert out["gsis_id"].tolist() == ["A1", "D4", "B2", "C3"]

    def test_every_stored_and_fresh_id_is_present(self, store):
        stored_table(STORED)
        out = etl.keep_dropped_ids(NPL, FRESH)
        assert set(STORED["gsis_id"]) | set(FRESH["gsis_id"]) <= set(out["gsis_id"])
        assert out["gsis_id"].is_unique

    def test_kept_rows_say_dropped(self, store):
        stored_table(STORED)
        out = etl.keep_dropped_ids(NPL, FRESH).set_index("gsis_id")
        assert out.loc[["B2", "C3"], "status"].tolist() == ["DROPPED", "DROPPED"]

    def test_kept_rows_otherwise_match_what_was_stored(self, store):
        stored = stored_table(STORED).set_index("gsis_id")
        out = etl.keep_dropped_ids(NPL, FRESH).set_index("gsis_id")
        ids = ["B2", "C3"]
        pd.testing.assert_frame_equal(
            out.loc[ids].drop(columns="status"), stored.loc[ids].drop(columns="status"),
            check_dtype=False)

    def test_fresh_row_wins_on_a_returned_id(self, store):
        stored_table(STORED)
        out = etl.keep_dropped_ids(NPL, FRESH).set_index("gsis_id")
        assert out.loc["A1", "status"] == "RET"
        assert out.loc["A1", "weight"] == 201.0

    def test_a_returned_id_takes_its_real_status_back(self, store):
        stored_table(rows(person("B2", "Bo Beta", "DROPPED")))
        out = etl.keep_dropped_ids(NPL, rows(person("B2", "Bo Beta", "CUT"))).set_index("gsis_id")
        assert out.loc["B2", "status"] == "CUT"
        assert len(out) == 1

    def test_a_second_run_on_the_same_input_changes_nothing(self, store):
        stored_table(STORED)
        etl.write_table(NPL, etl.keep_dropped_ids(NPL, FRESH))
        first = etl.read_table(NPL)
        etl.write_table(NPL, etl.keep_dropped_ids(NPL, FRESH))
        pd.testing.assert_frame_equal(etl.read_table(NPL), first)

    def test_a_published_table_passes_the_seam_write(self, store):
        stored_table(STORED)
        assert etl.write_table(NPL, etl.keep_dropped_ids(NPL, FRESH)) == 4

    def test_no_existing_table_keeps_nothing(self, store):
        assert not etl.table_exists(NPL)
        out = etl.keep_dropped_ids(NPL, FRESH)
        pd.testing.assert_frame_equal(out, FRESH)


def crosswalk_gsis(name, pos="WR"):
    etl.write_table("dim_rookie_prospect", pd.DataFrame({"player_key": ["k"], "player_name": ["Zed Nobody"]}))
    ident = pd.DataFrame([{"source": "KTC", "source_player_id": "1", "player_name": name,
                           "position_raw": pos, "nfl_team": "DAL"}])
    return etl.resolve_dynasty_crosswalk(ident, today="2026-10-31").loc[0, "gsis_id"]


class TestDynastyCrosswalkNameMatch:
    def test_fresh_row_beats_a_dropped_row_even_when_not_act(self, store):
        stored_table(rows(person("NEW1", "Pat Sample", "CUT", year=2021),
                          person("OLD1", "Pat Sample", "DROPPED", year=2024)))
        assert crosswalk_gsis("Pat Sample") == "NEW1"

    def test_fresh_row_beats_a_dropped_row_on_position_too(self, store):
        stored_table(rows(person("NEW1", "Pat Sample", "CUT", pos="RB", year=2021),
                          person("OLD1", "Pat Sample", "DROPPED", pos="WR", year=2024)))
        assert crosswalk_gsis("Pat Sample", pos="WR") == "NEW1"

    def test_a_person_with_only_a_dropped_row_still_matches(self, store):
        stored_table(rows(person("OLD2", "Lee Sample", "DROPPED"), person("X9", "Other Person")))
        assert crosswalk_gsis("Lee Sample") == "OLD2"

    def test_two_dropped_rows_resolve_as_before(self, store):
        stored_table(rows(person("OLD3", "Kai Sample", "DROPPED", year=2019),
                          person("OLD4", "Kai Sample", "DROPPED", year=2023)))
        assert crosswalk_gsis("Kai Sample") == "OLD4"


def load_04z_disambiguate():
    nb = json.loads((REPO / "notebooks" / "04z_fantrax_crosswalk.ipynb").read_text(encoding="utf-8"))
    cell = next(c for c in nb["cells"] if c["id"] == "b4224514")
    src = cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
    start, end = src.index("def disambiguate"), src.index("def match_one")
    ns = {"pd": pd}
    exec(src[start:end], ns)
    return ns["disambiguate"]


class Test04zDisambiguate:
    def test_fresh_row_beats_a_dropped_row_even_when_not_act(self):
        pick = load_04z_disambiguate()(
            rows(person("NEW1", "Pat Sample", "CUT", year=2021),
                 person("OLD1", "Pat Sample", "DROPPED", year=2024)), {"WR"})
        assert pick["gsis_id"] == "NEW1"

    def test_fresh_row_beats_a_dropped_row_on_position_too(self):
        pick = load_04z_disambiguate()(
            rows(person("NEW1", "Pat Sample", "CUT", pos="RB", year=2021),
                 person("OLD1", "Pat Sample", "DROPPED", pos="WR", year=2024)), {"WR"})
        assert pick["gsis_id"] == "NEW1"

    def test_a_person_with_only_dropped_rows_still_matches(self):
        pick = load_04z_disambiguate()(
            rows(person("OLD3", "Kai Sample", "DROPPED", year=2019),
                 person("OLD4", "Kai Sample", "DROPPED", year=2023)), {"WR"})
        assert pick["gsis_id"] == "OLD4"

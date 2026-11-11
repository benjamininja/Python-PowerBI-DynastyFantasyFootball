"""#300 Brief 3: the three writers that resolve a name or an id to a gsis_id
end on the newest id of dim_gsis_link.

The notebook cases load the shipped cell by its id (04z `b4224514`, 02a
`b0ac5110`) and run it on small fixtures, so they test the code that ships.
Classes named Guard* hold behaviour that existed before the change and
passes without it; each fails against a wrong version of the change (one
that blanks an unlinked id, drops a null, or needs the link table to exist).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest
import yaml
from thefuzz import fuzz, process

import etl_helpers as etl

NPL = "dim_nfl_players"
LINK = etl.GSIS_LINK_TABLE
NPL_COLS = ["gsis_id", "display_name", "status", "team_abbr", "position",
            "position_group", "entry_year", "pfr_id"]

REGISTRY = {"tables": [
    {"name": NPL, "type": "dim", "grain": "gsis_id",
     "columns": [{"name": c, "dtype": "int32" if c == "entry_year" else "str"} for c in NPL_COLS]},
    {"name": "dim_rookie_prospect", "type": "dim", "grain": "player_key",
     "columns": [{"name": c, "dtype": "str"} for c in ("player_key", "player_name", "pfr_id")]},
    {"name": LINK, "type": "resolver", "grain": "old_gsis_id",
     "columns": [{"name": c, "dtype": "str"} for c in etl.GSIS_LINK_COLUMNS]},
]}


@pytest.fixture
def store(tmp_path, monkeypatch):
    registry = tmp_path / "registry.yml"
    registry.write_text(yaml.safe_dump(REGISTRY), encoding="utf-8")
    monkeypatch.setattr(etl, "REGISTRY_PATH", registry)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    return tmp_path


def person(gsis, name, status="ACT", pos="WR", year=2024, pfr=None, team="DAL"):
    return (gsis, name, status, team, pos, pos, year, pfr)


def put_players(*people):
    df = pd.DataFrame(list(people), columns=NPL_COLS).astype({"entry_year": "int32"})
    etl.write_table(NPL, df)
    return df


def put_links(*pair_list):
    etl.write_table(LINK, pd.DataFrame([(o, n, "smart_id", "2026-11-01") for o, n in pair_list],
                                       columns=etl.GSIS_LINK_COLUMNS))


def put_prospects(*specs):
    etl.write_table("dim_rookie_prospect",
                    pd.DataFrame(list(specs), columns=["player_key", "player_name", "pfr_id"]))


def cell_source(notebook, cell_id):
    nb = json.loads((REPO / "notebooks" / notebook).read_text(encoding="utf-8"))
    cell = next(c for c in nb["cells"] if c["id"] == cell_id)
    return cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])


# ---- resolve_dynasty_crosswalk (manual 04x) -------------------------

def dynasty_row(name, spid="1", pos="WR"):
    return pd.DataFrame([{"source": "KTC", "source_player_id": spid, "player_name": name,
                          "position_raw": pos, "nfl_team": "DAL"}])


def dynasty(name, overrides=None, spid="1"):
    put_prospects(("k1", "Zed Nobody", None))
    return etl.resolve_dynasty_crosswalk(dynasty_row(name, spid), overrides, today="2026-11-01").loc[0]


class TestDynastyCrosswalkAppliesLink:
    def test_an_override_holding_an_old_id_ends_on_the_new_id(self, store):
        put_players(person("OLD", "Pat Sample", "DROPPED"), person("NEW", "Pat Sample"))
        put_links(("OLD", "NEW"))
        row = dynasty("Someone Else", overrides={"1": "OLD"})
        assert row["gsis_id"] == "NEW"
        assert row["match_method"] == "manual"

    def test_a_name_match_on_an_old_id_ends_on_the_new_id(self, store):
        put_players(person("OLD", "Lee Sample", "DROPPED"), person("NEW", "Lee Samples"),
                    person("X9", "Other Person"))
        put_links(("OLD", "NEW"))
        row = dynasty("Lee Sample")
        assert row["gsis_id"] == "NEW"
        assert row["match_method"] == "exact"

    def test_a_chain_ends_on_the_newest_id(self, store):
        put_players(person("A", "Kai Sample", "DROPPED"), person("B", "Kai Samplo", "DROPPED"),
                    person("C", "Kai Samplx"))
        put_links(("A", "B"), ("B", "C"))
        assert dynasty("Kai Sample")["gsis_id"] == "C"


class TestGuardDynastyCrosswalk:
    def test_an_unlinked_old_id_stays_as_it_is(self, store):
        put_players(person("OLD", "Lee Sample", "DROPPED"), person("X9", "Other Person"))
        put_links(("ZZZ", "YYY"))
        assert dynasty("Lee Sample")["gsis_id"] == "OLD"

    def test_an_override_on_a_current_id_stays(self, store):
        put_players(person("NEW", "Pat Sample"), person("OLD", "Pat Sample", "DROPPED"))
        put_links(("OLD", "NEW"))
        assert dynasty("Someone Else", overrides={"1": "NEW"})["gsis_id"] == "NEW"

    def test_no_link_table_changes_nothing(self, store):
        put_players(person("OLD", "Lee Sample", "DROPPED"), person("X9", "Other Person"))
        assert not etl.table_exists(LINK)
        assert dynasty("Lee Sample")["gsis_id"] == "OLD"

    def test_an_unmatched_name_stays_null(self, store):
        put_players(person("NEW", "Pat Sample"))
        put_links(("OLD", "NEW"))
        assert pd.isna(dynasty("Qq Zz")["gsis_id"])


# ---- 04z: scorer_id -> gsis_id --------------------------------------------

def run_04z(overrides=None, rows=None):
    """Run the shipped match cell on the stored dim_nfl_players; returns its `xwalk`."""
    npl = etl.read_table(NPL).copy()
    npl["name_clean"] = npl["display_name"].map(etl.clean_name_for_match)
    ns = {"pd": pd, "etl": etl, "CFG": etl.CFG, "fuzz": fuzz, "process": process,
          "clean_name_for_match": etl.clean_name_for_match}
    exec(cell_source("04z_fantrax_crosswalk.ipynb", "0bf7092f"), ns)
    ns.update(npl=npl, rp_lookup={}, alias_lookup={}, overrides=overrides or {},
              fact_latest=pd.DataFrame(rows or [
                  {"scorer_id": "s1", "player_name": "Pat Sample", "position_raw": "WR",
                   "nfl_team": "DAL", "is_rookie": False}]))
    exec(cell_source("04z_fantrax_crosswalk.ipynb", "b4224514"), ns)
    return ns["xwalk"].set_index("scorer_id")


def fantrax_row(sid, name):
    return {"scorer_id": sid, "player_name": name, "position_raw": "WR",
            "nfl_team": "DAL", "is_rookie": False}


class Test04zAppliesLink:
    def test_an_override_holding_an_old_id_ends_on_the_new_id(self, store):
        put_players(person("OLD", "Pat Sample", "DROPPED"), person("NEW", "Pat Sample"))
        put_links(("OLD", "NEW"))
        out = run_04z(overrides={"s1": "OLD"})
        assert out.loc["s1", "gsis_id"] == "NEW"
        assert out.loc["s1", "match_method"] == "manual"

    def test_a_name_match_on_an_old_id_ends_on_the_new_id(self, store):
        put_players(person("OLD", "Pat Sample", "DROPPED"), person("NEW", "Pat Samples"))
        put_links(("OLD", "NEW"))
        out = run_04z()
        assert out.loc["s1", "gsis_id"] == "NEW"
        assert out.loc["s1", "match_method"] == "exact"

    def test_every_row_of_a_mixed_batch_is_resolved(self, store):
        put_players(person("OLD", "Pat Sample", "DROPPED"), person("NEW", "Pat Samples"),
                    person("KEEP", "Cy Gamma"))
        put_links(("OLD", "NEW"))
        out = run_04z(rows=[fantrax_row("s1", "Pat Sample"), fantrax_row("s2", "Cy Gamma")])
        assert out["gsis_id"].to_dict() == {"s1": "NEW", "s2": "KEEP"}


class TestGuard04z:
    def test_an_unlinked_old_id_stays_as_it_is(self, store):
        put_players(person("OLD", "Pat Sample", "DROPPED"), person("X9", "Other Person"))
        put_links(("ZZZ", "YYY"))
        assert run_04z().loc["s1", "gsis_id"] == "OLD"

    def test_an_override_of_new_stays_null(self, store):
        put_players(person("OLD", "Pat Sample", "DROPPED"), person("NEW", "Pat Samples"))
        put_links(("OLD", "NEW"))
        out = run_04z(overrides={"s1": "new"})
        assert pd.isna(out.loc["s1", "gsis_id"])
        assert out.loc["s1", "match_method"] == "new"

    def test_no_link_table_changes_nothing(self, store):
        put_players(person("OLD", "Pat Sample", "DROPPED"), person("X9", "Other Person"))
        assert not etl.table_exists(LINK)
        assert run_04z().loc["s1", "gsis_id"] == "OLD"


# ---- 02a: pfr_id -> gsis_id ---------------------------------------------------

def build_02a(combine):
    src = cell_source("02a_fact_nfl_combine_pro_day_metrics.ipynb", "b0ac5110")
    ns = {"pd": pd, "etl": etl, "LeagueConfig": etl.LeagueConfig,
          "parse_height_to_inches": etl.parse_height_to_inches}
    exec(src[:src.index('print("Building fact_nfl')], ns)
    return ns["build_fact_nfl_combine_pro_day_metrics"](combine, etl.CFG).set_index("pfr_id")["gsis_id"]


def combine_rows(*pfr_ids):
    return pd.DataFrame({"pfr_id": list(pfr_ids), "season": 2020,
                         "player_name": [f"Name {p}" for p in pfr_ids]})


class Test02aAppliesLink:
    def test_a_pfr_id_that_gives_an_old_id_ends_on_the_new_id(self, store):
        put_players(person("OLD", "Pat Sample", "DROPPED", pfr="SampPa00"),
                    person("NEW", "Pat Sample", pfr="SampPa01"))
        put_links(("OLD", "NEW"))
        put_prospects(("k1", "Zed Nobody", None))
        assert build_02a(combine_rows("SampPa00")).to_dict() == {"SampPa00": "NEW"}


class TestGuard02a:
    def test_an_unlinked_old_id_stays_as_it_is(self, store):
        put_players(person("OLD", "Pat Sample", "DROPPED", pfr="SampPa00"))
        put_links(("ZZZ", "YYY"))
        put_prospects(("k1", "Zed Nobody", None))
        assert build_02a(combine_rows("SampPa00")).to_dict() == {"SampPa00": "OLD"}

    def test_a_pfr_id_with_no_player_stays_null(self, store):
        put_players(person("NEW", "Pat Sample", pfr="SampPa01"))
        put_links(("OLD", "NEW"))
        put_prospects(("k1", "Zed Nobody", None))
        assert pd.isna(build_02a(combine_rows("NoneXx00")).loc["NoneXx00"])

    def test_no_link_table_changes_nothing(self, store):
        put_players(person("OLD", "Pat Sample", "DROPPED", pfr="SampPa00"))
        put_prospects(("k1", "Zed Nobody", None))
        assert not etl.table_exists(LINK)
        assert build_02a(combine_rows("SampPa00")).to_dict() == {"SampPa00": "OLD"}

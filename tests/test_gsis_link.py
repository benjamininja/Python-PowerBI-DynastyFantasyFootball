"""#300 Brief 2: dim_gsis_link, the old-id -> new-id table that 01e adds to,
and `current_gsis`, which follows it.

The rule is the owner's D1: the same smart_id, one to one, the same entry
year, and no id both rows hold disagrees. Birth date and name are not
conditions. Every case runs on small fixtures.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest
import yaml

import etl_helpers as etl

COLUMNS = ["gsis_id", "display_name", "birth_date", "status", "entry_year",
           "smart_id", "esb_id", "espn_id", "pfr_id", "nfl_id", "otc_id"]
LINK = etl.GSIS_LINK_TABLE

REGISTRY = {"tables": [
    {"name": "dim_nfl_players", "type": "dim", "grain": "gsis_id",
     "columns": [{"name": c, "dtype": "str"} for c in COLUMNS if c != "entry_year"]
     + [{"name": "entry_year", "dtype": "int32"}]},
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


def player(gsis, smart, status="ACT", year=2026, name="Pat Sample", birth="2003-01-01", **ids):
    row = dict.fromkeys(COLUMNS)
    row.update(gsis_id=gsis, display_name=name, birth_date=birth, status=status,
               entry_year=year, smart_id=smart)
    row.update(ids)
    return row


def frame(*rows):
    return pd.DataFrame(list(rows), columns=COLUMNS)


def links(df, stored=None, decided="2026-11-01"):
    return etl.derive_gsis_links(df, stored, decided)


def pairs(df):
    return list(zip(df["old_gsis_id"], df["new_gsis_id"]))


def stored(*pair_list):
    return pd.DataFrame([(o, n, "smart_id", "2026-10-01") for o, n in pair_list],
                        columns=etl.GSIS_LINK_COLUMNS)


class TestTheRule:
    def test_a_dropped_id_and_a_live_id_on_one_smart_id_link(self):
        out = links(frame(player("OLD", "s1", "DROPPED"), player("NEW", "s1")))
        assert pairs(out) == [("OLD", "NEW")]
        assert out.loc[0, "method"] == "smart_id"
        assert out.loc[0, "decided_date"] == "2026-11-01"

    def test_the_columns_are_the_registry_columns(self):
        out = links(frame(player("OLD", "s1", "DROPPED"), player("NEW", "s1")))
        assert list(out.columns) == etl.GSIS_LINK_COLUMNS

    def test_birth_date_is_not_a_condition(self):
        out = links(frame(player("OLD", "s1", "DROPPED", birth="2003-01-01"),
                          player("NEW", "s1", birth="2003-06-30")))
        assert pairs(out) == [("OLD", "NEW")]

    def test_a_null_birth_date_is_not_a_condition(self):
        out = links(frame(player("OLD", "s1", "DROPPED", birth=None), player("NEW", "s1")))
        assert pairs(out) == [("OLD", "NEW")]

    def test_a_different_name_is_not_a_condition(self):
        out = links(frame(player("OLD", "s1", "DROPPED", name="P. Sample"),
                          player("NEW", "s1", name="Patrick Sample")))
        assert pairs(out) == [("OLD", "NEW")]

    def test_an_id_only_one_row_holds_is_not_a_disagreement(self):
        out = links(frame(player("OLD", "s1", "DROPPED", espn_id=None, pfr_id="P1"),
                          player("NEW", "s1", espn_id="E1", pfr_id="P1")))
        assert pairs(out) == [("OLD", "NEW")]

    def test_no_live_row_on_the_smart_id_is_no_link(self):
        assert links(frame(player("OLD", "s1", "DROPPED"), player("NEW", "s2"))).empty

    def test_a_null_smart_id_is_no_link(self):
        assert links(frame(player("OLD", None, "DROPPED"), player("NEW", None))).empty

    def test_a_live_row_alone_is_no_link(self):
        assert links(frame(player("NEW", "s1"), player("OTHER", "s2"))).empty

    def test_a_different_entry_year_is_no_link(self):
        assert links(frame(player("OLD", "s1", "DROPPED", year=2025),
                           player("NEW", "s1", year=2026))).empty

    def test_a_null_entry_year_is_no_link(self):
        assert links(frame(player("OLD", "s1", "DROPPED", year=None),
                           player("NEW", "s1", year=2026))).empty
        assert links(frame(player("OLD", "s1", "DROPPED", year=2026),
                           player("NEW", "s1", year=None))).empty

    @pytest.mark.parametrize("column", ["esb_id", "espn_id", "pfr_id", "nfl_id", "otc_id"])
    def test_a_shared_id_that_disagrees_is_no_link(self, column):
        old = player("OLD", "s1", "DROPPED", **{column: "X1"})
        new = player("NEW", "s1", **{column: "X2"})
        assert links(frame(old, new)).empty

    def test_a_shared_id_that_agrees_still_links(self):
        out = links(frame(player("OLD", "s1", "DROPPED", esb_id="E1", espn_id="9", pfr_id="P1"),
                          player("NEW", "s1", esb_id="E1", espn_id="9", pfr_id="P1")))
        assert pairs(out) == [("OLD", "NEW")]

    def test_two_dropped_ids_on_one_smart_id_make_no_link(self):
        assert links(frame(player("OLD1", "s1", "DROPPED"), player("OLD2", "s1", "DROPPED"),
                           player("NEW", "s1"))).empty

    def test_two_live_ids_on_one_smart_id_make_no_link(self):
        assert links(frame(player("OLD", "s1", "DROPPED"), player("NEW1", "s1"),
                           player("NEW2", "s1"))).empty

    def test_a_refused_id_does_not_stop_another_link(self):
        out = links(frame(player("BAD", "s1", "DROPPED", year=2024), player("NEWBAD", "s1"),
                          player("OLD", "s2", "DROPPED"), player("NEW", "s2")))
        assert pairs(out) == [("OLD", "NEW")]

    def test_several_links_come_out_in_old_id_order(self):
        out = links(frame(player("OLD2", "s2", "DROPPED"), player("NEW2", "s2"),
                          player("OLD1", "s1", "DROPPED"), player("NEW1", "s1")))
        assert pairs(out) == [("OLD1", "NEW1"), ("OLD2", "NEW2")]

    def test_the_players_table_is_not_changed(self):
        players = frame(player("OLD", "s1", "DROPPED"), player("NEW", "s1"))
        before = players.copy()
        links(players)
        pd.testing.assert_frame_equal(players, before)


class TestStoredLinksAreKept:
    def test_a_stored_link_stays_when_the_rule_no_longer_holds(self):
        players = frame(player("OLD", "s1", "DROPPED", year=2020), player("NEW", "s1", year=2026))
        out = links(players, stored(("OLD", "NEW")))
        assert pairs(out) == [("OLD", "NEW")]
        assert out.loc[0, "decided_date"] == "2026-10-01"

    def test_a_stored_link_stays_when_its_old_row_is_gone(self):
        out = links(frame(player("NEW", "s1")), stored(("OLD", "NEW")))
        assert pairs(out) == [("OLD", "NEW")]

    def test_a_stored_link_is_not_rewritten_to_another_target(self):
        players = frame(player("OLD", "s1", "DROPPED"), player("OTHER", "s1"))
        out = links(players, stored(("OLD", "NEW")))
        assert pairs(out) == [("OLD", "NEW")]

    def test_an_old_id_with_a_link_adds_no_second_row(self):
        players = frame(player("OLD", "s1", "DROPPED"), player("NEW", "s1"))
        out = links(players, stored(("OLD", "NEW")))
        assert out["old_gsis_id"].is_unique
        assert len(out) == 1

    def test_a_new_link_is_added_after_the_stored_ones(self):
        players = frame(player("A", "s0", "DROPPED"), player("A2", "s0"),
                        player("OLD", "s1", "DROPPED"), player("NEW", "s1"))
        out = links(players, stored(("Z", "ZNEW")), decided="2026-11-02")
        assert pairs(out) == [("Z", "ZNEW"), ("A", "A2"), ("OLD", "NEW")]
        assert out["decided_date"].tolist() == ["2026-10-01", "2026-11-02", "2026-11-02"]

    def test_a_live_id_already_a_target_is_not_given_a_second_old_id(self):
        players = frame(player("OLD2", "s1", "DROPPED"), player("NEW", "s1"))
        out = links(players, stored(("OLD1", "NEW")))
        assert pairs(out) == [("OLD1", "NEW")]

    def test_a_stored_link_does_not_count_as_a_repeat_on_its_smart_id(self):
        players = frame(player("OLD1", "s1", "DROPPED"), player("OLD2", "s1", "DROPPED"),
                        player("NEW2", "s1"))
        out = links(players, stored(("OLD1", "NEW1")))
        assert pairs(out) == [("OLD1", "NEW1"), ("OLD2", "NEW2")]


class TestChains:
    def test_a_new_id_that_drops_links_on_to_the_next(self):
        players = frame(player("B", "s1", "DROPPED"), player("C", "s1"))
        out = links(players, stored(("A", "B")))
        assert pairs(out) == [("A", "B"), ("B", "C")]
        assert etl.current_gsis(pd.Series(["A", "B", "C"]), out).tolist() == ["C", "C", "C"]

    def test_a_loop_in_the_stored_links_raises(self):
        with pytest.raises(ValueError, match="loop"):
            links(frame(player("NEW", "s1")), stored(("A", "B"), ("B", "A")))

    def test_a_loop_the_new_link_would_close_raises(self):
        players = frame(player("B", "s1", "DROPPED"), player("A", "s1"))
        with pytest.raises(ValueError, match="loop"):
            links(players, stored(("A", "B")))

    def test_a_loop_raises_in_current_gsis_too(self):
        with pytest.raises(ValueError, match="loop"):
            etl.current_gsis(pd.Series(["A"]), stored(("A", "B"), ("B", "A")))


class TestCurrentGsis:
    def test_a_linked_id_becomes_the_new_one(self):
        out = etl.current_gsis(pd.Series(["OLD", "KEEP"]), stored(("OLD", "NEW")))
        assert out.tolist() == ["NEW", "KEEP"]

    def test_an_unlinked_id_and_a_null_stay_as_they_are(self):
        out = etl.current_gsis(pd.Series(["KEEP", None, pd.NA]), stored(("OLD", "NEW")))
        assert out.iloc[0] == "KEEP"
        assert out.iloc[1:].isna().all()

    def test_the_index_and_length_are_kept(self):
        ids = pd.Series(["OLD", "KEEP", "OLD"], index=[7, 3, 9])
        out = etl.current_gsis(ids, stored(("OLD", "NEW")))
        assert out.index.tolist() == [7, 3, 9]
        assert out.tolist() == ["NEW", "KEEP", "NEW"]

    def test_the_input_is_not_changed(self):
        ids = pd.Series(["OLD"])
        etl.current_gsis(ids, stored(("OLD", "NEW")))
        assert ids.tolist() == ["OLD"]

    def test_no_stored_table_changes_nothing(self, store):
        assert not etl.table_exists(LINK)
        assert etl.current_gsis(pd.Series(["OLD"])).tolist() == ["OLD"]

    def test_an_empty_table_changes_nothing(self):
        out = etl.current_gsis(pd.Series(["OLD"]), pd.DataFrame(columns=etl.GSIS_LINK_COLUMNS))
        assert out.tolist() == ["OLD"]

    def test_it_reads_the_stored_table_through_the_seam(self, store):
        etl.write_table(LINK, stored(("OLD", "NEW")))
        assert etl.current_gsis(pd.Series(["OLD", "X"])).tolist() == ["NEW", "X"]


class TestTheSeam:
    PLAYERS = frame(player("OLD", "s1", "DROPPED"), player("NEW", "s1"),
                    player("GONE", "s2", "DROPPED"), player("LIVE", "s3"))

    def test_the_links_pass_the_seam_write(self, store):
        assert etl.write_table(LINK, links(self.PLAYERS)) == 1

    def test_a_second_run_changes_nothing(self, store):
        etl.write_table(LINK, links(self.PLAYERS, decided="2026-11-01"))
        first = etl.read_table(LINK)
        again = links(self.PLAYERS, etl.read_table(LINK), decided="2026-11-08")
        etl.write_table(LINK, again)
        pd.testing.assert_frame_equal(etl.read_table(LINK), first)

    def test_a_run_with_no_links_writes_an_empty_table(self, store):
        out = links(frame(player("LIVE", "s3")))
        assert etl.write_table(LINK, out) == 0

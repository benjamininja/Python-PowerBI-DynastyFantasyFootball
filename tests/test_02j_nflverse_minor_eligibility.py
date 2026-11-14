"""02j: minors eligibility from nflverse career games (#524).

The rule (planner ruling on #524, the games rule of #473 Q7): a game is a
regular-season game with a snap from 2012 on, a regular-season stats row
before it; playoffs never count; eligible while the count is 19 or fewer.
The builders are I/O free and tested on small frames; main() runs against a
temp data dir with the nflverse loads patched out.
"""
import importlib
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))
import etl_helpers as etl

ne = importlib.import_module("02j_nflverse_minor_eligibility")

NO_LINKS = pd.DataFrame()
PERIODS = pd.DataFrame({
    "season_id": ["2026-2027"] * 2,
    "period": [1, 2],
    "start_date": pd.to_datetime(["2026-09-09", "2026-09-17"]),
    "end_date": pd.to_datetime(["2026-09-17", "2026-09-24"]),
})
LOOKUP = pd.Series({"p1": "g1", "p2": "g2"})


def snap(pfr, game, season=2026, kind="REG", off=10.0, de=0.0, st=0.0, pos="WR"):
    return {"game_id": game, "season": season, "game_type": kind, "pfr_player_id": pfr,
            "position": pos, "offense_snaps": off, "defense_snaps": de, "st_snaps": st}


def players(*rows):
    return pd.DataFrame(rows, columns=["gsis_id", "pfr_id", "last_season"])


class TestSeasonAndWeek:
    def test_the_season_is_the_first_year_of_the_newest_league_season(self):
        both = pd.concat([PERIODS.assign(season_id="2025-2026"), PERIODS])
        assert ne.current_season(both) == 2026

    def test_the_week_is_the_two_digit_period_holding_the_day(self):
        assert ne.week_label(date(2026, 9, 10), PERIODS) == "01"
        assert ne.week_label(date(2026, 9, 20), PERIODS) == "02"

    def test_a_day_no_period_holds_is_pre(self):
        assert ne.week_label(date(2026, 7, 1), PERIODS) == "PRE"


class TestPfrLookup:
    def test_both_sources_fill_the_map_and_the_player_dim_wins_a_clash(self):
        ids = pd.DataFrame({"pfr_id": ["p1", "p2", None], "gsis_id": ["gX", "g2", "g3"]})
        dim = players(("g1", "p1", 2026), ("g4", None, 2026))
        got = ne.pfr_lookup(dim, ids)
        assert got.to_dict() == {"p1": "g1", "p2": "g2"}


class TestSnapGames:
    def test_a_regular_season_game_with_a_snap_counts_once(self):
        snaps = pd.DataFrame([snap("p1", "g-a"), snap("p1", "g-b"), snap("p1", "g-b")])
        got, _ = ne.snap_games(snaps, LOOKUP)
        assert got.to_dict() == {"g1": 2}

    def test_a_playoff_game_never_counts(self):
        got, _ = ne.snap_games(pd.DataFrame([snap("p1", "g-a", kind="POST"),
                                             snap("p1", "g-b", kind="REG")]), LOOKUP)
        assert got.to_dict() == {"g1": 1}

    def test_a_snap_on_any_unit_counts_and_no_snap_does_not(self):
        snaps = pd.DataFrame([snap("p1", "g-a", off=0.0, st=3.0), snap("p2", "g-b", off=0.0),
                              snap("p2", "g-c", off=None, de=None, st=None)])
        got, _ = ne.snap_games(snaps, LOOKUP)
        assert got.to_dict() == {"g1": 1}

    def test_a_season_before_2012_is_left_to_the_stats_rows(self):
        got, _ = ne.snap_games(pd.DataFrame([snap("p1", "g-old", season=2011),
                                             snap("p1", "g-new")]), LOOKUP)
        assert got.to_dict() == {"g1": 1}

    def test_a_row_with_no_gsis_id_is_counted_by_position_and_left_out(self):
        snaps = pd.DataFrame([snap("p1", "g-a"), snap("x9", "g-a", pos="T"), snap("x8", "g-b", pos="T")])
        got, unmapped = ne.snap_games(snaps, LOOKUP)
        assert got.to_dict() == {"g1": 1} and unmapped == {"T": 2}


class TestStatGames:
    def test_the_games_column_is_summed_for_seasons_before_2012_only(self):
        stats = pd.DataFrame({"player_id": ["g1", "g1", "g1", None],
                              "season": [2010, 2011, 2012, 2010], "games": [10, 6, 16, 3]})
        assert ne.stat_games(stats).to_dict() == {"g1": 16}


class TestCareerGames:
    def test_the_two_counts_are_added(self):
        got = ne.career_games(pd.Series({"g1": 5}), pd.Series({"g1": 7, "g2": 2}), NO_LINKS)
        assert got.to_dict() == {"g1": 12, "g2": 2}

    def test_a_renumbered_player_keeps_one_count(self):
        links = pd.DataFrame([["old1", "g1", "x", "2026-01-01"]], columns=etl.GSIS_LINK_COLUMNS)
        got = ne.career_games(pd.Series({"g1": 5}), pd.Series({"old1": 7}), links)
        assert got.to_dict() == {"g1": 12}


class TestBuildEligibility:
    def build(self, games, players_frame, links=NO_LINKS):
        return ne.build_eligibility(players_frame, pd.Series(games, dtype="int64"), 2026, "02",
                                    "2026-09-18", links).set_index("gsis_id")

    def test_nineteen_games_is_eligible_and_twenty_is_not(self):
        df = self.build({"g1": 19, "g2": 20},
                        players(("g1", "p1", 2026), ("g2", "p2", 2026)))
        assert df["eligible"].to_dict() == {"g1": True, "g2": False}
        assert df["career_games"].to_dict() == {"g1": 19, "g2": 20}

    def test_a_player_with_no_game_has_zero_and_is_eligible(self):
        df = self.build({"g1": 3}, players(("g1", "p1", 2026), ("g5", "p5", 2026)))
        assert df.loc["g5", "career_games"] == 0 and bool(df.loc["g5", "eligible"])

    def test_the_pool_is_this_season_and_last_season_s_players(self):
        df = self.build({"g1": 3}, players(("g1", "p1", 2026), ("g2", "p2", 2025), ("g3", "p3", 2024)))
        assert sorted(df.index) == ["g1", "g2"]

    def test_an_id_a_newer_one_replaced_is_not_a_player(self):
        links = pd.DataFrame([["old1", "g1", "x", "2026-01-01"]], columns=etl.GSIS_LINK_COLUMNS)
        df = self.build({"g1": 3}, players(("g1", "p1", 2026), ("old1", "p1", 2026)), links)
        assert list(df.index) == ["g1"]

    def test_the_columns_and_types_are_the_registry_s(self):
        df = ne.build_eligibility(players(("g1", "p1", 2026)), pd.Series({"g1": 3}), 2026, "02",
                                  "2026-09-18", NO_LINKS)
        assert list(df.columns) == list(ne.DTYPES)
        assert [str(df[c].dtype) for c in ("season", "career_games", "eligible")] == [
            "int64", "int64", "bool"]

    def test_an_empty_count_stops_the_build_rather_than_make_everyone_eligible(self):
        with pytest.raises(ValueError, match="came back empty"):
            ne.build_eligibility(players(("g1", "p1", 2026)), pd.Series(dtype="int64"), 2026, "02",
                                 "2026-09-18", NO_LINKS)


class TestMain:
    SNAPS = pd.DataFrame([snap("p1", "g-a"), snap("p1", "g-b"), snap("p2", "g-a"),
                          snap("x9", "g-a", pos="T")])
    STATS = pd.DataFrame({"player_id": ["g2"], "season": [2010], "games": [30]})
    IDS = pd.DataFrame({"pfr_id": ["p1", "p2"], "gsis_id": ["g1", "g2"]})

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
        root = Path(__file__).resolve().parents[1] / "data"
        etl.write_table("dim_scoring_period", pd.read_parquet(root / "dim_scoring_period.parquet"))
        dim = pd.read_parquet(root / "dim_nfl_players.parquet").iloc[:3].copy()
        dim["gsis_id"], dim["pfr_id"], dim["last_season"] = ["g1", "g2", "g3"], ["p1", "p2", None], 2026
        etl.write_table("dim_nfl_players", dim)
        frames = {"snaps": self.SNAPS, "stats": self.STATS, "ids": self.IDS}
        monkeypatch.setattr(ne, "load_nflverse", lambda season: frames)
        return tmp_path

    def test_it_writes_one_capture_through_the_seam(self, env, capsys):
        assert ne.main() == 0
        df = etl.read_table(ne.TABLE).set_index("gsis_id")
        assert df["career_games"].to_dict() == {"g1": 2, "g2": 31, "g3": 0}
        assert df["eligible"].to_dict() == {"g1": True, "g2": False, "g3": True}
        assert df["capture_date"].nunique() == 1
        assert "1 snap row(s) with no gsis_id, by position: {'T': 1}" in capsys.readouterr().out

    def test_a_rerun_replaces_its_week_and_keeps_another(self, env):
        ne.main()
        old = etl.read_table(ne.TABLE).assign(week="01")
        etl.write_table(ne.TABLE, old, mode="replace_partition", keys=("season", "week"))
        ne.main()
        now = etl.read_table(ne.TABLE)
        assert now["week"].nunique() == 2 and len(now) == 6

    def test_an_empty_load_writes_nothing(self, env, monkeypatch):
        empty = {"snaps": self.SNAPS.iloc[:0], "stats": self.STATS.iloc[:0], "ids": self.IDS}
        monkeypatch.setattr(ne, "load_nflverse", lambda season: empty)
        with pytest.raises(ValueError, match="came back empty"):
            ne.main()
        assert not etl.table_exists(ne.TABLE)

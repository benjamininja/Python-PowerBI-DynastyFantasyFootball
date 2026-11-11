"""02g: the two nflverse facts of ADR-0017 (#86).

Per ADR-0008 the builders are I/O-free and tested on small frames; main()
runs against a temp data dir with the nflverse loads patched out, so no
test touches the network or the published tables.
"""
import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))
import etl_helpers as etl

nv = importlib.import_module("02g_nflverse_inseason")

PERIODS = pd.DataFrame({
    "season_id": ["2026-2027"] * 2,
    "period": [1, 2],
    "start_date": pd.to_datetime(["2026-09-09", "2026-09-17"]),
    "end_date": pd.to_datetime(["2026-09-17", "2026-09-24"]),
})
SCHEDULE = pd.DataFrame({
    "game_id": ["2026_01_AAA_BBB", "2026_02_AAA_CCC"],
    "week": [1, 2],
    "gameday": ["2026-09-13", "2026-09-17"],
    "home_team": ["BBB", "CCC"],
    "away_team": ["AAA", "AAA"],
})
ROSTERS = pd.DataFrame({"pfr_id": ["p1", "p1", "p2", None], "gsis_id": ["g1", "g1", "g2", "g9"]})


def snap(pfr, game, week, pos="WR", off=10.0):
    return {"game_id": game, "season": 2026, "week": week, "pfr_player_id": pfr, "position": pos,
            "team": "AAA", "offense_snaps": off, "offense_pct": 0.5, "defense_snaps": 0.0,
            "defense_pct": 0.0, "st_snaps": 2.0, "st_pct": 0.1}


def injury(gsis, week, team="AAA", status="Out"):
    return {"season": 2026, "week": week, "game_type": "REG", "team": team, "gsis_id": gsis,
            "report_status": status, "report_primary_injury": "Knee",
            "practice_status": "Did Not Participate In Practice"}


SNAPS = pd.DataFrame([snap("p1", "2026_01_AAA_BBB", 1), snap("p2", "2026_01_AAA_BBB", 1),
                      snap("p1", "2026_02_AAA_CCC", 2), snap("x9", "2026_01_AAA_BBB", 1, pos="T")])
INJURIES = pd.DataFrame([injury("g1", 1), injury("g2", 2, status=None), injury("g3", 2, team="ZZZ")])


class TestStampPeriod:
    def test_a_period_starts_on_its_start_date_and_ends_before_the_next(self):
        days = pd.Series(["2026-09-09", "2026-09-16", "2026-09-17", "2026-09-23"])
        assert nv.stamp_period(days, PERIODS).tolist() == [1, 1, 2, 2]

    def test_a_date_in_no_period_or_missing_is_empty(self):
        got = nv.stamp_period(pd.Series(["2026-09-08", "2026-09-24", None]), PERIODS)
        assert got.isna().all() and str(got.dtype) == "Int64"


class TestCurrentSeason:
    def test_it_is_the_first_year_of_the_newest_league_season(self):
        both = pd.concat([PERIODS.assign(season_id="2025-2026"), PERIODS])
        season, periods = nv.current_season(both)
        assert season == 2026 and set(periods["season_id"]) == {"2026-2027"}


class TestBuildSnapCounts:
    def test_rows_are_keyed_by_gsis_id_and_stamped_with_the_game_s_period(self):
        df, _ = nv.build_snap_counts(SNAPS, ROSTERS, SCHEDULE, PERIODS)
        assert list(df.columns) == list(nv.SNAP_DTYPES)
        assert df[["gsis_id", "game_id", "period"]].values.tolist() == [
            ["g1", "2026_01_AAA_BBB", 1], ["g2", "2026_01_AAA_BBB", 1], ["g1", "2026_02_AAA_CCC", 2]]
        assert df.loc[0, ["offense_snaps", "st_snaps", "offense_pct"]].tolist() == [10.0, 2.0, 0.5]

    def test_a_row_with_no_gsis_id_is_dropped_and_counted_by_position(self):
        df, unmapped = nv.build_snap_counts(SNAPS, ROSTERS, SCHEDULE, PERIODS)
        assert unmapped == {"T": 1} and "x9" not in df["gsis_id"].tolist() and len(df) == 3

    def test_a_pfr_id_with_two_gsis_ids_stops_the_build(self):
        twice = pd.concat([ROSTERS, pd.DataFrame({"pfr_id": ["p1"], "gsis_id": ["g7"]})])
        with pytest.raises(ValueError, match="more than one gsis_id"):
            nv.build_snap_counts(SNAPS, twice, SCHEDULE, PERIODS)

    def test_a_repeated_key_stops_the_build(self):
        with pytest.raises(ValueError, match="repeat the key"):
            nv.build_snap_counts(pd.concat([SNAPS, SNAPS.iloc[:1]]), ROSTERS, SCHEDULE, PERIODS)

    def test_an_empty_pull_gives_an_empty_typed_frame(self):
        df, unmapped = nv.build_snap_counts(SNAPS.iloc[:0], ROSTERS, SCHEDULE, PERIODS)
        assert df.empty and unmapped == {} and list(df.columns) == list(nv.SNAP_DTYPES)


class TestBuildInjuries:
    def test_the_period_is_that_of_the_team_s_game_that_week(self):
        df = nv.build_injuries(INJURIES, SCHEDULE, PERIODS).set_index("gsis_id")
        assert list(df.reset_index().columns) == list(nv.INJURY_DTYPES)
        assert df.loc["g1", "period"] == 1 and df.loc["g2", "period"] == 2
        assert pd.isna(df.loc["g2", "report_status"])            # no game status is not "None"

    def test_a_team_with_no_game_that_week_takes_the_week_s_first_game_day(self):
        df = nv.build_injuries(INJURIES, SCHEDULE, PERIODS).set_index("gsis_id")
        assert df.loc["g3", "period"] == 2

    def test_a_row_with_no_gsis_id_is_left_out(self):
        df = nv.build_injuries(pd.concat([INJURIES, pd.DataFrame([injury(None, 1)])]), SCHEDULE, PERIODS)
        assert len(df) == 3

    def test_a_repeated_key_stops_the_build(self):
        with pytest.raises(ValueError, match="repeat the key"):
            nv.build_injuries(pd.concat([INJURIES, INJURIES.iloc[:1]]), SCHEDULE, PERIODS)


class TestMain:
    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))      # where the seam reads and writes
        published = pd.read_parquet(Path(__file__).resolve().parents[1] / "data" / "dim_scoring_period.parquet")
        etl.write_table("dim_scoring_period", published)
        players = pd.read_parquet(
            Path(__file__).resolve().parents[1] / "data" / "dim_nfl_players.parquet").iloc[:2].copy()
        players["gsis_id"] = ["g1", "g2"]                             # g3 is not a known player
        etl.write_table("dim_nfl_players", players)
        frames = {"snaps": SNAPS, "injuries": INJURIES, "rosters": ROSTERS, "schedule": SCHEDULE}
        monkeypatch.setattr(nv, "load_nflverse", lambda season: frames)
        return tmp_path

    def test_it_writes_both_tables_through_the_seam(self, env, capsys):
        assert nv.main() == 0
        assert len(etl.read_table("fact_nfl_snap_counts")) == 3
        assert len(etl.read_table("fact_nfl_injuries")) == 3
        out = capsys.readouterr().out
        assert "1 snap row(s) dropped with no gsis_id" in out
        # a player the dim does not hold yet is kept and reported, not dropped
        assert "fact_nfl_injuries: 1 row(s) of 1 player(s) have a gsis_id that dim_nfl_players" in out

    def test_a_rerun_writes_the_same_bytes(self, env):
        nv.main()
        first = [(env / f"{t}.parquet").read_bytes() for t in (nv.SNAP_TABLE, nv.INJURY_TABLE)]
        nv.main()
        assert [(env / f"{t}.parquet").read_bytes() for t in (nv.SNAP_TABLE, nv.INJURY_TABLE)] == first

    def test_a_run_replaces_its_season_and_keeps_another(self, env):
        nv.main()
        old = etl.read_table("fact_nfl_snap_counts")
        old = old.assign(season=2025, game_id=old["game_id"].str.replace("2026_", "2025_"))
        etl.write_table("fact_nfl_snap_counts", old, mode="replace_partition", partition={"season": [2025]})
        nv.main()
        assert etl.read_table("fact_nfl_snap_counts")["season"].value_counts().to_dict() == {2025: 3, 2026: 3}

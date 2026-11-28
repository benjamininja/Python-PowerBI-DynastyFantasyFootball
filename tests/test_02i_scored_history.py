"""02i: the scored history of the MouseRatPresents Baseline and its drift
check (#473 brief 4, ADR-0023).

The builders are I/O-free and tested on small frames. main() runs against a
temp data dir holding fake tables, with the nflverse loads patched out, so no
test touches the network or the published tables.
"""
import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))
import etl_helpers as etl

sh = importlib.import_module("02i_nflverse_scored_history")

POSITIONS7 = ["QB", "RB", "WR", "TE", "DL", "LB", "DB"]
NO_LINKS = pd.DataFrame(columns=etl.GSIS_LINK_COLUMNS)


def rules_frame(tks_dl=3.5):
    rows = []
    for pos in POSITIONS7:
        rows += [("2870", pos, 0.04), ("3218", pos, 0.1), ("256g", pos, 2.0),
                 ("3120", pos, {"DL": tks_dl, "DB": 2.0}.get(pos, 1.5))]
    df = pd.DataFrame(rows, columns=["category_id", "position", "points"])
    df["season_id"] = "2026-2027"
    df["category_code"] = df["category_id"]
    df["category_name"] = df["category_id"]
    df["scoring_group"] = "Offense"
    return df


CATEGORIES = pd.DataFrame({
    "category_id": ["2870", "3120", "3218", "256g"],
    "category_code": ["YDS", "TkS", "RtY", "BK"],
    "category_name": ["Passing Yards", "Solo Tackles", "Return Yards", "Blocked Kicks"],
    "category_group": ["Passing", "Defense, tackles", "Special teams", "Special teams"],
    "group_sort_order": [1, 5, 4, 4],
    "unit": ["Offense", "Defense", "Special Teams", "Special Teams"],
    "nflverse_columns": ["passing_yards", "def_tackles_solo", "kickoff_return_yards+punt_return_yards", None],
})
POSITIONS = pd.DataFrame({
    "position_raw": ["QB", "LB", "DE", "DL", "T", "CB"],
    "position_group": ["QB", "LB", "DL", "DL", "OL", "DB"],
})
PLAYERS = pd.DataFrame({"gsis_id": ["g1", "g2", "g3", "g4"], "pfr_id": ["p1", "p2", "p3", "p4"],
                        "status": ["ACT"] * 4})
CROSSWALK = pd.DataFrame({"scorer_id": ["s1", "s3"], "gsis_id": ["g1", "g3"],
                          "position_raw": ["QB", "DL,LB"]})
STAT_COLS = ["passing_yards", "def_tackles_solo", "kickoff_return_yards", "punt_return_yards"]


def stat(pid, season, pos, games, py=0.0, tks=0.0, kr=0.0, pr=0.0):
    return {"player_id": pid, "season": season, "position": pos, "games": games, "passing_yards": py,
            "def_tackles_solo": tks, "kickoff_return_yards": kr, "punt_return_yards": pr}


def season_stats():
    rows = [stat("g1", s, "QB", 16, py=4000) for s in range(2011, 2025)]
    rows += [stat("g1", 2025, "QB", 17, py=3000), stat("g2", 2025, "LB", 15, tks=80, kr=100),
             stat("g3", 2025, "DE", 16, tks=40), stat("g4", 2025, "T", 16),
             stat(None, 2025, None, 0), stat("g1", 2026, "QB", 2, py=500), stat("g3", 2026, "DE", 2, tks=6)]
    return pd.DataFrame(rows)


def snap(pfr, season, game, off=0.0, dfn=0.0, st=0.0):
    return {"game_type": "REG", "season": season, "game_id": game, "pfr_player_id": pfr,
            "offense_snaps": off, "defense_snaps": dfn, "st_snaps": st}


SNAPS = pd.DataFrame([snap("p1", 2025, "a", off=60), snap("p1", 2025, "b", off=55), snap("p1", 2025, "c", off=50),
                      snap("p3", 2025, "a", dfn=40), snap("p3", 2025, "b"), snap("p1", 2024, "z", off=1)])


def week(pid, game, wk, py=0.0, tks=0.0):
    return {"player_id": pid, "season": 2026, "week": wk, "season_type": "REG", "game_id": game,
            "passing_yards": py, "def_tackles_solo": tks, "kickoff_return_yards": 0.0,
            "punt_return_yards": 0.0}


WEEKS = pd.DataFrame([week("g1", "G1", 1, py=250), week("g1", "G2", 2, py=250),
                      week("g3", "G1", 1, tks=3), week("g3", "G2", 2, tks=3), week(None, "G1", 1)])
SCHEDULE = pd.DataFrame({"game_id": ["G1", "G2"], "gameday": ["2026-09-13", "2026-09-20"]})
PERIODS = pd.DataFrame({
    "season_id": ["2026-2027"] * 3, "period": [1, 2, 3],
    "start_date": pd.to_datetime(["2026-09-09", "2026-09-17", "2026-09-24"]),
    "end_date": pd.to_datetime(["2026-09-17", "2026-09-24", "2026-10-01"]),
    "is_playoff": [False] * 3, "update_set_state": ["closed", "open", None],
})
PERIOD_SCORING = pd.DataFrame({
    "season_id": ["2026-2027"] * 3, "period": [1, 1, 2], "team_key": ["t1", "t2", "t1"],
    "scorer_id": ["s1", "s3", "s1"], "fpts": [10.0, 10.5, 99.0],
    "fpts_offense": [10.0, 0.0, 99.0], "fpts_defense": [0.0, 10.5, 0.0], "fpts_special_teams": [0.0] * 3,
})


def adp(g2_fpts=130.0):
    return pd.DataFrame({
        "scorer_id": ["s1", "s2", "s3", "s9", "s1"], "season": [2025, 2025, 2025, 2025, 2026],
        "week": ["YTD", "YTD", "YTD", "YTD", "YTD"], "position_raw": ["QB", "LB", "DL,LB", "WR", "QB"],
        "fpts": [120.0, g2_fpts, 140.0, 300.0, 1.0], "games_played": [17.0, 15.0, 16.0, 4.0, 2.0],
        "gsis_id": ["g1", "g2", "g3", "g9", "g1"]})


def points_series(rules=None):
    return sh.rule_points(rules_frame() if rules is None else rules, CATEGORIES)[1]


def build(stats=None, snaps=SNAPS):
    points = points_series()
    colmap, _ = sh.column_map(CATEGORIES, points)
    return sh.build_history(season_stats() if stats is None else stats, snaps, PLAYERS, CROSSWALK,
                            POSITIONS, colmap, points, "2026-2027", NO_LINKS)


class TestScoring:
    def test_points_are_count_times_the_rules_points_for_the_position(self):
        stats, players, _ = build()
        got = stats.set_index(["gsis_id", "season", "category_id"])["points"]
        assert got[("g1", 2025, "2870")] == pytest.approx(120.0)
        assert got[("g2", 2025, "3120")] == pytest.approx(120.0)
        assert got[("g2", 2025, "3218")] == pytest.approx(10.0)
        assert got[("g3", 2025, "3120")] == pytest.approx(140.0)

    def test_the_default_fills_a_position_without_an_override(self):
        stats, _, _ = build()
        per = stats.set_index(["gsis_id", "season", "category_id"])
        assert per.loc[("g2", 2025, "3120"), "points"] / per.loc[("g2", 2025, "3120"), "stat_count"] == 1.5
        assert per.loc[("g3", 2025, "3120"), "points"] / per.loc[("g3", 2025, "3120"), "stat_count"] == 3.5

    def test_a_category_is_the_sum_of_its_columns(self):
        frame = season_stats()
        frame.loc[frame["player_id"] == "g2", "punt_return_yards"] = 20.0
        stats, _, _ = build(frame)
        row = stats[(stats["gsis_id"] == "g2") & (stats["category_id"] == "3218")].iloc[0]
        assert row["stat_count"] == 120.0 and row["points"] == pytest.approx(12.0)

    def test_a_zero_count_writes_no_row(self):
        stats, players, _ = build()
        assert not ((stats["gsis_id"] == "g1") & (stats["category_id"] == "3120")).any()
        assert (stats["stat_count"] != 0).all()

    def test_a_category_with_no_column_scores_0_and_has_no_row(self):
        colmap, unmapped = sh.column_map(CATEGORIES, points_series())
        assert unmapped == ["256g"] and "256g" not in colmap
        stats, _, _ = build()
        assert "256g" not in set(stats["category_id"])

    def test_the_crosswalk_position_wins_first_listed(self):
        _, players, _ = build()
        g3 = players[(players["gsis_id"] == "g3") & (players["season"] == 2025)].iloc[0]
        g2 = players[(players["gsis_id"] == "g2") & (players["season"] == 2025)].iloc[0]
        assert (g3["position"], g3["position_source"]) == ("DL", "fantrax")
        assert (g2["position"], g2["position_source"]) == ("LB", "nflverse")
        assert set(players["rules_season_id"]) == {"2026-2027"}

    def test_a_player_with_no_league_position_is_left_out_and_counted(self):
        stats, players, info = build()
        assert "g4" not in set(players["gsis_id"])
        assert info["no_league_position"] == {"OL": 1}

    def test_an_unknown_id_and_a_null_id_are_dropped(self):
        frame = pd.concat([season_stats(), pd.DataFrame([stat("gX", 2025, "QB", 3, py=10)])])
        stats, players, info = build(frame)
        assert info["dropped_ids"] == 1 and "gX" not in set(players["gsis_id"])
        assert players["gsis_id"].notna().all()

    def test_an_old_id_is_moved_to_its_newest(self):
        frame = pd.concat([season_stats(), pd.DataFrame([stat("gOld", 2026, "LB", 1, tks=2)])])
        links = pd.DataFrame({"old_gsis_id": ["gOld"], "new_gsis_id": ["g2"], "method": ["smart_id"],
                              "decided_date": ["2026-11-01"]})
        points = points_series()
        colmap, _ = sh.column_map(CATEGORIES, points)
        stats, players, _ = sh.build_history(frame, SNAPS, PLAYERS, CROSSWALK, POSITIONS, colmap, points,
                                             "2026-2027", links)
        assert ((players["gsis_id"] == "g2") & (players["season"] == 2026)).any()
        assert "gOld" not in set(stats["gsis_id"])

    def test_every_stat_row_has_a_player_season_row(self):
        stats, players, _ = build()
        keys = set(map(tuple, players[["gsis_id", "season"]].to_numpy()))
        assert set(map(tuple, stats[["gsis_id", "season"]].to_numpy())) <= keys


class TestGames:
    def test_snaps_from_2012_stats_rows_before_and_a_fallback(self):
        _, players, info = build()
        games = players.set_index(["gsis_id", "season"])["games"]
        assert games[("g1", 2011)] == 16          # before 2012: stats rows
        assert games[("g1", 2025)] == 3           # snaps above 0
        assert games[("g3", 2025)] == 1           # a game with 0 snaps does not count
        assert games[("g1", 2024)] == 1
        assert games[("g2", 2025)] == 15          # no mapped snap game: stats rows
        assert info["games_from_stats_rows"] >= 1


class TestFailures:
    def test_a_mapped_column_the_frame_lacks_fails_by_name(self):
        colmap, _ = sh.column_map(CATEGORIES, points_series())
        with pytest.raises(ValueError, match="def_tackles_solo"):
            sh.check_columns(season_stats().drop(columns=["def_tackles_solo"]), colmap, "season stats")

    def test_the_confirmed_columns_are_listed(self):
        colmap, _ = sh.column_map(CATEGORIES, points_series())
        assert sh.check_columns(season_stats(), colmap, "season stats") == sorted(STAT_COLS)

    def test_a_rules_category_with_no_category_row_fails_by_name(self):
        rules = pd.concat([rules_frame(), rules_frame().assign(category_id="9999")])
        with pytest.raises(ValueError, match="9999"):
            sh.rule_points(rules, CATEGORIES)

    def test_the_newest_rules_season_scores(self):
        old = rules_frame(tks_dl=9.0).assign(season_id="2025-2026")
        season_id, points = sh.rule_points(pd.concat([old, rules_frame()]), CATEGORIES)
        assert season_id == "2026-2027" and points[("3120", "DL")] == 3.5


class TestDriftVerdict:
    def frame(self, ours, theirs, pos="QB"):
        return pd.DataFrame({"ours": ours, "theirs": theirs, "position": pos, "group": "Passing"})

    def test_inside_the_threshold_passes(self):
        fig = sh.figures(self.frame([100.0, 50.4], [100.0, 50.0]))
        assert fig["pass_share"] == 1.0 and fig["exact_share"] == 0.5
        assert sh.failures("2025", fig) == []

    def test_too_few_players_pass(self):
        fig = sh.figures(self.frame([100.0] * 19 + [200.0], [100.0] * 20))
        assert fig["pass_share"] == 0.95 and not any("pass" in f for f in sh.failures("2025", fig))
        fig = sh.figures(self.frame([100.0] * 18 + [200.0] * 2, [100.0] * 20))
        assert any("compared pass" in f for f in sh.failures("2025", fig))

    def test_a_position_sum_off_by_more_than_1_percent_fails(self):
        fig = sh.figures(self.frame([102.0] * 10, [100.0] * 10))
        assert fig["pass_share"] == 1.0
        assert any("QB summed points differ" in f for f in sh.failures("2025", fig))

    def test_the_owner_bar_share_is_reported(self):
        fig = sh.figures(self.frame([11.5], [10.0]))
        assert fig["pass_share"] == 0.0 and fig["owner_bar_share"] == 1.0


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    tables = {"dim_scoring_period": PERIODS, "dim_scoring_category": CATEGORIES,
              "dim_fantrax_scoring_rule": rules_frame(), "dim_nfl_players": PLAYERS,
              "dim_fantrax_crosswalk": CROSSWALK, "dim_position": POSITIONS,
              "fact_period_scoring": PERIOD_SCORING, "fact_fantrax_adp": adp()}
    for name, df in tables.items():
        df.to_parquet(tmp_path / f"{name}.parquet", index=False)
    frames = {"stats": season_stats(), "snaps": SNAPS, "weeks": WEEKS, "schedule": SCHEDULE}
    calls = []

    def load(seasons, week_seasons):
        calls.append((list(seasons), list(week_seasons)))
        return frames
    monkeypatch.setattr(sh, "load_nflverse", load)
    return tmp_path, calls


class TestMain:
    def test_it_writes_both_tables_and_the_drift_passes(self, world, capsys):
        tmp, calls = world
        assert sh.main() == 0
        out = capsys.readouterr().out
        assert calls[0] == (list(range(2011, 2027)), [2026])
        stats, players = etl.read_table(sh.STAT_TABLE), etl.read_table(sh.PLAYER_TABLE)
        assert set(players["season"]) == set(range(2011, 2027))
        assert len(stats) and (stats["stat_count"] != 0).all()
        assert "drift inside the threshold" in out
        assert "2025 season totals: 3 compared" in out
        assert "2026-2027 period 1: 2 compared; exact (within 0.05) 100.0%" in out
        assert "held but not closed [2]" in out and "not compared (no Fantrax figure) [3]" in out
        assert "['BK']" in out and "has no nflverse column" in out

    def test_an_unchanged_run_writes_nothing(self, world, capsys, monkeypatch):
        tmp, calls = world
        sh.main()
        capsys.readouterr()
        monkeypatch.setattr(sh, "write_table", lambda *a, **k: pytest.fail("a write on an unchanged run"))
        assert sh.main() == 0
        assert calls[1] == ([2026], [2026])
        assert "nothing written" in capsys.readouterr().out

    def test_a_rules_change_rescores_every_season(self, world, capsys):
        tmp, calls = world
        sh.main()
        rules = rules_frame(tks_dl=3.5)
        rules.loc[rules["category_id"] == "2870", "points"] = 0.05
        rules.to_parquet(tmp / "dim_fantrax_scoring_rule.parquet", index=False)
        adp().assign(fpts=[150.0, 130.0, 140.0, 300.0, 1.0]).to_parquet(tmp / "fact_fantrax_adp.parquet",
                                                                        index=False)
        PERIOD_SCORING.assign(fpts=[12.5, 10.5, 99.0]).to_parquet(tmp / "fact_period_scoring.parquet",
                                                                 index=False)
        assert sh.main() == 0
        assert calls[1][0] == list(range(2011, 2027))
        stats = etl.read_table(sh.STAT_TABLE).set_index(["gsis_id", "season", "category_id"])
        assert stats.loc[("g1", 2011, "2870"), "points"] == pytest.approx(200.0)

    def test_drift_past_the_threshold_fails_before_any_write(self, world, capsys):
        tmp, _ = world
        adp(g2_fpts=200.0).to_parquet(tmp / "fact_fantrax_adp.parquet", index=False)
        with pytest.raises(sh.DriftError, match="2025"):
            sh.main()
        assert not (tmp / f"{sh.STAT_TABLE}.parquet").exists()
        assert not (tmp / f"{sh.PLAYER_TABLE}.parquet").exists()
        assert "2025 season totals: 3 compared" in capsys.readouterr().out

    def test_a_missing_mapped_column_fails_before_any_write(self, world, monkeypatch):
        tmp, _ = world
        frames = {"stats": season_stats().drop(columns=["punt_return_yards"]), "snaps": SNAPS,
                  "weeks": WEEKS, "schedule": SCHEDULE}
        monkeypatch.setattr(sh, "load_nflverse", lambda seasons, week_seasons: frames)
        with pytest.raises(ValueError, match="punt_return_yards"):
            sh.main()
        assert not (tmp / f"{sh.STAT_TABLE}.parquet").exists()


class TestStampPeriodMoved:
    def test_02g_and_02i_share_the_one_in_etl_helpers(self):
        nv = importlib.import_module("02g_nflverse_inseason")
        assert nv.stamp_period is etl.stamp_period is sh.stamp_period

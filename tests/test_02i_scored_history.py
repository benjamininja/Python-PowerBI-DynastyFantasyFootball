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
SCHEDULE = pd.DataFrame({"game_id": ["G1", "G2"], "gameday": ["2026-09-13", "2026-09-20"], "week": [1, 2],
                         "game_type": ["REG", "REG"]})
PERIODS = pd.DataFrame({
    "season_id": ["2026-2027"] * 3, "period": [1, 2, 3],
    "start_date": pd.to_datetime(["2026-09-09", "2026-09-17", "2026-09-24"]),
    "end_date": pd.to_datetime(["2026-09-17", "2026-09-24", "2026-10-01"]),
    "is_playoff": [False] * 3, "update_set_state": ["closed", "open", None],
})
PERIOD_SCORING = pd.DataFrame({
    "season_id": ["2026-2027"] * 3, "period": [1, 1, 2], "team_key": ["t1", "t2", "t1"],
    "scorer_id": ["s1", "s3", "s1"], "is_starter": [True, False, True], "fpts": [10.0, 10.5, 99.0],
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
        fig = sh.figures(self.frame([100.0] * 18 + [200.0] * 2, [100.0] * 20))
        assert fig["pass_share"] == 0.90 and not any("pass" in f for f in sh.failures("2025", fig))
        fig = sh.figures(self.frame([100.0] * 17 + [200.0] * 3, [100.0] * 20))
        assert any("compared pass" in f for f in sh.failures("2025", fig))

    def test_a_position_sum_off_by_more_than_2_percent_fails(self):
        fig = sh.figures(self.frame([102.0] * 10, [100.0] * 10))
        assert sh.failures("2025", fig) == []
        fig = sh.figures(self.frame([103.0] * 10, [100.0] * 10))
        assert fig["pass_share"] == 1.0
        assert any("QB summed points differ" in f for f in sh.failures("2025", fig))

    def test_the_tighter_share_is_reported(self):
        fig = sh.figures(self.frame([11.5], [10.0]))
        assert fig["pass_share"] == 1.0 and fig["tight_share"] == 0.0


class TestOneFigurePerScorer:
    def rows(self, fpts_by_team, starters=None):
        teams = list(fpts_by_team)
        return pd.DataFrame({"scorer_id": "s1", "period": 1, "team_key": teams,
                             "is_starter": starters or [False] * len(teams),
                             "fpts": list(fpts_by_team.values()), "fpts_offense": list(fpts_by_team.values()),
                             "fpts_defense": 0.0, "fpts_special_teams": 0.0})

    def test_one_row_is_taken_as_it_is(self):
        one, many, disagree = sh.one_figure(self.rows({"t1": 12.0}))
        assert one["fpts"].tolist() == [12.0] and (many, disagree) == (0, 0)
        assert one["pair_kind"].isna().all() and one["low"].isna().all()

    def test_two_agreeing_rows_give_one_figure_not_a_sum(self):
        one, many, disagree = sh.one_figure(self.rows({"t1": 12.0, "t15": 12.005}))
        assert len(one) == 1 and one["fpts"].iloc[0] == pytest.approx(12.005) and (many, disagree) == (0, 0)
        assert one["pair_kind"].isna().all()

    def test_two_disagreeing_rows_give_the_higher_and_keep_the_lower(self):
        one, many, disagree = sh.one_figure(self.rows({"t1": 10.0, "t15": 12.5}, starters=[True, False]))
        assert (many, disagree) == (0, 1)
        row = one.iloc[0]
        assert (row["fpts"], row["fpts_offense"], row["low"], row["pair_kind"]) == (12.5, 12.5, 10.0, "mixed")

    @pytest.mark.parametrize("starters, kind", [([False, False], "both bench"), ([True, True], "both Starters")])
    def test_a_disagreeing_pair_is_split_by_starter(self, starters, kind):
        one, _, _ = sh.one_figure(self.rows({"t1": 8.0, "t15": 10.0}, starters=starters))
        assert one["pair_kind"].iloc[0] == kind

    def test_three_rows_are_counted(self):
        _, many, _ = sh.one_figure(self.rows({"t1": 12.0, "t15": 12.0, "t20": 12.0}))
        assert many == 1

    def test_the_pair_shares_test_the_higher_row_against_the_lower(self):
        df = pd.DataFrame({"ours": [12.5, 10.0, 5.0], "theirs": [12.5, 12.5, 5.0], "low": [10.0, 10.0, None],
                           "pair_kind": ["mixed", "both Starters", None]})
        assert sh.pair_counts(df) == {"pairs": 2, "both_bench": 0, "mixed": 1, "both_starters": 1,
                                      "inside_vs_higher": 0.5, "inside_vs_lower": 0.5}


class TestOffenseAndTE:
    def test_the_offense_fit_finds_the_points_per_unit_that_fit(self):
        rows = pd.DataFrame({"gsis_id": ["a", "b", "c"], "period": [1, 1, 2], "category_id": ["2870"] * 3,
                             "stat_count": [100.0, 250.0, 300.0]})
        df = pd.DataFrame({"gsis_id": ["a", "b", "c"], "period": [1, 1, 2], "position": ["QB"] * 3,
                           "ours": [4.0, 10.0, 12.0], "theirs": [3.0, 7.5, 9.0]})
        fit = sh.offense_fit(df, rows, CATEGORIES, points_series())["QB"]
        assert fit["player_periods"] == 3 and fit["share_rules"] == pytest.approx(1 / 3, abs=1e-3)
        assert fit["share_fitted"] == 1.0
        (rule, fitted), = fit["points"].values()
        assert rule == 0.04 and fitted == pytest.approx(0.03)

    def test_the_te_gap_splits_by_bench_row(self):
        df = pd.DataFrame({"position": ["TE", "TE", "TE", "WR"], "has_bench": [True, False, False, True],
                           "ours": [10.0, 12.0, 8.0, 1.0], "theirs": [10.0, 10.0, 8.0, 5.0]})
        got = sh.te_split(df)
        assert got["with a bench row"] == {"player_periods": 1, "gap": 0.0, "gap_share": 0.0, "inside_bar": 1.0}
        assert got["Starter rows only"] == {"player_periods": 2, "gap": 2.0, "gap_share": round(2 / 18, 4),
                                             "inside_bar": 0.5}

    def test_a_bench_row_is_flagged(self):
        rows = pd.DataFrame({"scorer_id": ["s1", "s1", "s2"], "period": 1, "team_key": ["t1", "t15", "t1"],
                             "is_starter": [True, False, True], "fpts": 5.0, "fpts_offense": 5.0,
                             "fpts_defense": 0.0, "fpts_special_teams": 0.0})
        one, _, _ = sh.one_figure(rows)
        assert one.set_index("scorer_id")["has_bench"].to_dict() == {"s1": True, "s2": False}


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fantrax" / "live_scoring.json"


def live(entries_by_team):
    """A getLiveScoringStats reply: {team: {scorer: (total, [(scipId, sv, fpts)])}}, all under ACTIVE."""
    teams = {}
    for team, entries in entries_by_team.items():
        stats = {sid: {"object1": tot, "object2": [{"scipId": s, "sv": v, "fpts": f} for s, v, f in lines]}
                 for sid, (tot, lines) in entries.items()}
        stats["_1010"] = {"object1": 99.0, "object2": [{"scipId": "1010#2870#-1", "fpts": 99.0}]}
        teams[team] = {"ACTIVE": {"statsMap": stats}, "BENCH": {"statsMap": {}}}
    return {"responses": [{"data": {"statsPerTeam": {"allTeamsStats": teams}}}]}


class TestCaptureComparison:
    def test_the_committed_fixture_parses_into_stat_lines(self):
        import json
        lines = sh.capture_lines(json.loads(FIXTURE.read_text(encoding="utf-8")))
        assert len(lines) and lines["category_id"].notna().all()
        assert not lines["scorer_id"].str.startswith("_").any()
        assert set(lines.columns) == {"team_id", "scorer_id", "player_fpts", "scip_id", "category_id", "sv", "fpts"}

    def test_a_scorer_on_two_teams_counts_once_from_the_higher_total(self):
        body = live({"T1": {"s1": (10.0, [("1010#2870#-1", 250, 10.0)])},
                     "T2": {"s1": (8.0, [("1010#2870#-1", 250, 8.0)]), "s3": (9.0, [("1020#3120#-1", 3, 9.0)])}})
        lines = sh.capture_lines(body).assign(period=1)
        assert len(lines) == 3
        rows = pd.DataFrame({"gsis_id": ["g1", "g3"], "period": [1, 1], "position": ["QB", "DL"],
                             "category_id": ["2870", "3120"], "stat_count": [250.0, 2.0], "points": [10.0, 7.0]})
        comp = sh.capture_comparison(lines, rows, CROSSWALK, pd.Series({"g1": "QB", "g3": "DL"}), NO_LINKS)
        got = comp.set_index(["position", "category_id"])
        qb = got.loc[("QB", "2870")]
        assert (qb["ft_count"], qb["our_count"], qb["ft_points"], qb["count_differs"]) == (250, 250, 10.0, 0)
        assert qb["ft_points_per_unit"] == pytest.approx(0.04)
        dl = got.loc[("DL", "3120")]
        assert (dl["ft_count"], dl["our_count"], dl["count_differs"], dl["count_abs_diff"]) == (3, 2, 1, 1.0)
        assert dl["ft_points_per_unit"] == pytest.approx(3.0)

    def test_a_line_with_no_sv_leaves_the_count_unknown(self):
        body = live({"T1": {"s1": (10.0, [("1010#2870#-1", None, 10.0)])}})
        rows = pd.DataFrame({"gsis_id": ["g1"], "period": [1], "position": ["QB"], "category_id": ["2870"],
                             "stat_count": [250.0], "points": [10.0]})
        comp = sh.capture_comparison(sh.capture_lines(body).assign(period=1), rows, CROSSWALK,
                                     pd.Series({"g1": "QB"}), NO_LINKS)
        row = comp.iloc[0]
        assert pd.isna(row["ft_count"]) and row["count_differs"] == 0 and pd.isna(row["ft_points_per_unit"])


class TestDiagnostics:
    def test_how_the_misses_miss(self):
        df = pd.DataFrame({"ours": [0.0, 0.0, 5.0, 9.6, 30.0, 10.0], "theirs": [0.0, 8.0, 10.0, 10.0, 10.0, 10.0],
                           "joined": [True, False, True, True, True, True]})
        assert sh.miss_counts(df) == {"compared": 6, "misses": 4, "ours_zero_theirs_above": 1, "near_half": 1,
                                      "near_equal": 1, "elsewhere": 1, "no_row_of_ours": 1}

    def test_the_tackle_fit_finds_the_points_that_fit_and_tests_the_swap(self):
        cats = pd.concat([CATEGORIES, pd.DataFrame({
            "category_id": ["3110"], "category_code": ["TkA"], "category_name": ["Assisted Tackles"],
            "category_group": ["Defense, tackles"], "group_sort_order": [5], "unit": ["Defense"],
            "nflverse_columns": ["def_tackle_assists"]})], ignore_index=True)
        rules = pd.concat([rules_frame(), rules_frame().query("category_id == '3120'")
                           .assign(category_id="3110", points=1.0)], ignore_index=True)
        points = sh.rule_points(rules, cats)[1]
        rows = pd.DataFrame({"gsis_id": ["a", "a", "b", "b"], "category_id": ["3120", "3110", "3120", "3110"],
                             "stat_count": [40.0, 20.0, 10.0, 30.0]})
        rows["points"] = rows["stat_count"] * [1.5, 1.0, 1.5, 1.0]
        ytd = pd.DataFrame({"gsis_id": ["a", "b"], "position": ["LB", "LB"],
                            "ours": [80.0, 45.0], "theirs": [40 * 0.75 + 20 * 0.5, 10 * 0.75 + 30 * 0.5]})
        fit = sh.tackle_fit(ytd, rows, cats, points)["LB"]
        assert fit["fit_solo"] == pytest.approx(0.75) and fit["fit_assist"] == pytest.approx(0.5)
        assert (fit["rule_solo"], fit["rule_assist"]) == (1.5, 1.0)
        assert fit["share_fitted"] == 1.0 and fit["gap_fitted"] == pytest.approx(0.0)
        assert fit["share_rules"] == 0.0 and fit["players"] == 2


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
        assert "'no_row_of_ours': 0" in out
        assert "{'players': 2, 'more_than_one': 0, 'max_rows': 1}" in out
        assert "'nfl_weeks_stamped': 1" in out

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

    def test_the_capture_comparison_prints_only_where_the_file_is_present(self, world, capsys):
        import json
        tmp, _ = world
        sh.main()
        assert "no stored 04s capture read for period(s) [1]" in capsys.readouterr().out
        (tmp / "raw").mkdir()
        body = {"live_scoring": live({"T1": {"s1": (10.0, [("1010#2870#-1", 250, 10.0)])},
                                      "T2": {"s3": (10.5, [("1020#3120#-1", 3, 10.5)])}})}
        (tmp / "raw" / "fantrax_inseason_2026_p01.json").write_text(json.dumps(body), encoding="utf-8")
        assert sh.main() == 0
        out = capsys.readouterr().out
        assert "capture comparison, periods [1]: 2 of 2 stat lines carry sv" in out
        assert ("QB 2870 YDS: 1 player-periods; count Fantrax 250 ours 250; points Fantrax 10.0 ours 10.0; "
                "counts differ in 0 (abs total 0); Fantrax points per unit 0.040") in out
        assert "first downs (2657) stat ids in the capture: none" in out

    def test_a_checkout_without_the_two_declarations_still_prints_the_report(self, world, capsys, monkeypatch):
        tmp, _ = world
        full = etl._registry()
        monkeypatch.setattr(etl, "_registry",
                            lambda: {k: v for k, v in full.items() if k not in (sh.STAT_TABLE, sh.PLAYER_TABLE)})
        PERIOD_SCORING.assign(fpts=[20.0, 10.5, 99.0]).to_parquet(tmp / "fact_period_scoring.parquet", index=False)
        with pytest.raises(sh.DriftError):
            sh.main()
        out = capsys.readouterr().out
        assert "fact_scored_season_stat is not declared in the registry of this checkout" in out
        assert "2026-2027 all compared periods: 2 compared" in out

    def test_2025_drift_is_printed_only(self, world, capsys):
        tmp, _ = world
        adp(g2_fpts=200.0).to_parquet(tmp / "fact_fantrax_adp.parquet", index=False)
        assert sh.main() == 0
        out = capsys.readouterr().out
        assert "2025 season totals: 3 compared" in out
        assert "printed only, does not fail the step: 2025: 66.7% of 3 compared pass" in out
        assert (tmp / f"{sh.STAT_TABLE}.parquet").exists()

    def test_2026_drift_past_the_bar_fails_before_any_write(self, world, capsys):
        tmp, _ = world
        PERIOD_SCORING.assign(fpts=[20.0, 10.5, 99.0]).to_parquet(tmp / "fact_period_scoring.parquet", index=False)
        with pytest.raises(sh.DriftError, match="2026-2027"):
            sh.main()
        assert not (tmp / f"{sh.STAT_TABLE}.parquet").exists()
        assert not (tmp / f"{sh.PLAYER_TABLE}.parquet").exists()

    def test_a_player_in_both_conferences_is_compared_once(self, world, capsys):
        tmp, _ = world
        second = PERIOD_SCORING.iloc[[0]].assign(team_key="t15")
        pd.concat([PERIOD_SCORING, second]).to_parquet(tmp / "fact_period_scoring.parquet", index=False)
        assert sh.main() == 0
        out = capsys.readouterr().out
        assert "2026-2027 period 1: 2 compared; exact (within 0.05) 100.0%" in out
        assert "0 scorer-period(s) whose rows disagree" in out

    def test_a_disagreeing_pair_compares_the_higher_and_does_not_fail(self, world, capsys):
        tmp, _ = world
        lower = PERIOD_SCORING.iloc[[0]].assign(team_key="t15", fpts=8.0, fpts_offense=8.0, is_starter=False)
        pd.concat([PERIOD_SCORING, lower]).to_parquet(tmp / "fact_period_scoring.parquet", index=False)
        assert sh.main() == 0
        out = capsys.readouterr().out
        assert "1 scorer-period(s) whose rows disagree" in out
        assert ("{'pairs': 1, 'both_bench': 0, 'mixed': 1, 'both_starters': 0, "
                "'inside_vs_higher': 1.0, 'inside_vs_lower': 0.0}") in out

    def test_a_third_row_fails_before_any_write(self, world):
        tmp, _ = world
        extra = [PERIOD_SCORING.iloc[[0]].assign(team_key=t) for t in ("t15", "t20")]
        pd.concat([PERIOD_SCORING, *extra]).to_parquet(tmp / "fact_period_scoring.parquet", index=False)
        with pytest.raises(sh.DriftError, match="more than 2 rows"):
            sh.main()
        assert not (tmp / f"{sh.STAT_TABLE}.parquet").exists()

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

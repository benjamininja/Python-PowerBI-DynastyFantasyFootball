"""04s: the Unit rule, which Scoring Periods load, the parsers' failure modes
and a run of main() from saved raw files (#118, ADR-0016 amendment decisions
1, 5, 9 and 15).

The parser tests on the real payload shape live in test_fantrax_parsers.py
(TestLiveScoring, TestMatchups). These run on hand-built inputs: the bad
replies a capture does not hold. Nothing here opens a browser or touches the
network; main() runs against a temp data dir with `--from-raw`.
"""
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

from test_04r_roster_state import FIRST, IN_PERIOD_3, IN_PLAYOFFS, SEASON, TEAMS, WEEK, dim

lg = importlib.import_module("04p_fantrax_league_info")
fs = importlib.import_module("04s_fantrax_inseason_capture")

DAY = pd.Timestamp("2026-10-04")
OFFENSE, DEFENSE = "1010#2657#1", "1020#2680#2"
RETURN_YARDS, BLOCKED_KICK = "1010#3218#1", "1020#256g#2"


def entry(stats):
    """One statsMap entry from {stat id: points}."""
    return {"object1": round(sum(stats.values()), 2),
            "object2": [{"scipId": k, "fpts": v} for k, v in stats.items()]}


def team(active=None, bench=None, total=None):
    """One team's two groups: a Starter worth 12.5 and a non-starter worth 5."""
    active = {"p1": entry({OFFENSE: 10.0, RETURN_YARDS: 2.5})} if active is None else active
    bench = {"p2": entry({DEFENSE: 4.0, BLOCKED_KICK: 1.0})} if bench is None else bench
    total = sum(e["object1"] for e in active.values()) if total is None else total
    return {"ACTIVE": {"totalFpts": total, "statsMap": {"_1010": entry({}), **active}},
            "BENCH": {"statsMap": {"_1020": entry({}), **bench}}}


def live(teams=None, final=True):
    teams = {"fa": team(), "fb": team()} if teams is None else teams
    return {"responses": [{"data": {"allEventsFinished": final,
                                    "statsPerTeam": {"allTeamsStats": teams}}}]}


def schedule(weeks):
    """A schedule reply from {week: [(away id, away score, home id, home score)]}."""
    return {"responses": [{"data": {"tableList": [
        {"caption": f"Week {n}", "rows": [
            {"cells": [{"teamId": a}, {"content": af}, {"teamId": h}, {"content": hf}]}
            for a, af, h, hf in rows]}
        for n, rows in weeks.items()]}}]}


def scoring(reply):
    return fs.scoring_to_frame(reply, TEAMS, SEASON, 3, DAY)


def matchups(reply, period=1):
    return fs.matchups_to_frame(reply, TEAMS, SEASON, period, DAY)


class TestUnitOf:
    @pytest.mark.parametrize("scip_id, unit", [
        (OFFENSE, "Offense"), (DEFENSE, "Defense"),
        (RETURN_YARDS, "Special Teams"), ("1020#3218#2", "Special Teams"),
        (BLOCKED_KICK, "Special Teams")])
    def test_group_and_category_decide(self, scip_id, unit):
        assert fs.unit_of(scip_id) == unit

    @pytest.mark.parametrize("scip_id", ["1030#2657#1", "1010#2657", "", None])
    def test_an_unknown_id_raises(self, scip_id):
        with pytest.raises(ValueError, match="unknown stat id"):
            fs.unit_of(scip_id)


class TestPeriodsToLoad:
    def test_every_started_regular_season_period(self):
        assert fs.periods_to_load(dim(IN_PERIOD_3), IN_PERIOD_3) == [1, 2, 3]

    def test_a_closed_period_is_not_loaded_again(self):
        assert fs.periods_to_load(dim(IN_PERIOD_3, closed={1}), IN_PERIOD_3) == [2, 3]

    def test_playoff_periods_are_never_loaded(self):
        assert fs.periods_to_load(dim(IN_PLAYOFFS), IN_PLAYOFFS) == [1, 2, 3, 4]

    def test_nothing_before_period_1_starts(self):
        before = FIRST - pd.Timedelta(days=1)
        assert fs.periods_to_load(dim(before), before) == []


class TestScoringToFrame:
    def test_points_split_by_unit(self):
        by = scoring(live()).set_index(["team_key", "scorer_id"])
        starter = by.loc[("A01", "p1")]
        assert (starter["fpts"], starter["fpts_offense"], starter["fpts_defense"],
                starter["fpts_special_teams"]) == (12.5, 10.0, 0.0, 2.5)
        bench = by.loc[("A01", "p2")]
        assert (bench["fpts"], bench["fpts_offense"], bench["fpts_defense"],
                bench["fpts_special_teams"]) == (5.0, 0.0, 4.0, 1.0)

    def test_is_starter_follows_the_group(self):
        df = scoring(live())
        assert df.set_index("scorer_id")["is_starter"].groupby(level=0).first().to_dict() == {
            "p1": True, "p2": False}

    def test_the_same_player_on_two_teams_is_two_rows(self):
        df = scoring(live())
        assert len(df) == 4 and not df.duplicated(["team_key", "scorer_id"]).any()
        assert (df["period"] == 3).all() and (df["capture_date"] == DAY).all()

    def test_group_totals_are_skipped(self):
        assert not scoring(live())["scorer_id"].str.startswith("_").any()

    def test_an_entry_with_no_stats_is_a_row_of_zeros(self):
        df = scoring(live({"fa": team(bench={"p2": entry({})}), "fb": team()}))
        row = df[(df["team_key"] == "A01") & (df["scorer_id"] == "p2")].iloc[0]
        assert (row["fpts"], row["fpts_offense"], row["fpts_defense"],
                row["fpts_special_teams"]) == (0.0, 0.0, 0.0, 0.0)

    def test_a_unit_sum_carries_no_float_noise(self):
        stats = {OFFENSE: 0.1, "1010#2670#1": 0.2}                 # 0.1 + 0.2 != 0.3 in floats
        df = scoring(live({"fa": team(active={"p1": entry(stats)}), "fb": team()}))
        assert df.loc[(df["team_key"] == "A01") & df["is_starter"], "fpts_offense"].iloc[0] == 0.3

    @pytest.mark.parametrize("teams, message", [
        ({"fa": team()}, "1 teams, expected 2"),
        ({"fa": team(), "fb": team(), "fz": team()}, "not in dim_fantasy_teams"),
        ({"fa": team(total=99.0), "fb": team()}, "Starters sum to 12.50, totalFpts is 99.0"),
        ({"fa": team(bench={"p1": entry({DEFENSE: 1.0})}), "fb": team()}, "p1 is listed twice"),
        ({"fa": team(active={"p1": entry({"1030#1#1": 1.0})}), "fb": team()}, "unknown stat id"),
    ])
    def test_a_bad_reply_raises(self, teams, message):
        with pytest.raises(ValueError, match=message):
            scoring(live(teams))

    def test_a_reply_without_the_bench_view_raises(self):
        starters_only = {k: v for k, v in team().items() if k == "ACTIVE"}
        with pytest.raises(ValueError, match="no BENCH group"):
            scoring(live({"fa": starters_only, "fb": team()}))


class TestMatchupsToFrame:
    def test_sides_and_scores(self):
        df = matchups(schedule({1: [("fa", "12.5", "fb", "1,024.25")]})).set_index("team_key")
        cols = ["opponent_team_key", "is_home", "fpts_for", "fpts_against"]
        assert df.loc["A01", cols].tolist() == ["B01", False, 12.5, 1024.25]
        assert df.loc["B01", cols].tolist() == ["A01", True, 1024.25, 12.5]

    def test_only_the_week_asked_for(self):
        reply = schedule({1: [("fa", "1", "fb", "2")], 2: [("fb", "3", "fa", "4")]})
        df = matchups(reply, period=2)
        assert (df["period"] == 2).all()
        assert df.set_index("team_key").loc["B01", "fpts_for"] == 3.0

    @pytest.mark.parametrize("rows, message", [
        ([("fa", "1", "fz", "2")], "not in dim_fantasy_teams"),
        ([("fa", "1", "fa", "2")], "1 teams, expected 2"),
        ([("fa", "1", "fb", "2"), ("fb", "1", "fa", "2")], "do not hold each of 2 teams once"),
        ([("fa", "-", "fb", "2")], "score '-' is not a number"),
    ])
    def test_a_bad_week_raises(self, rows, message):
        with pytest.raises(ValueError, match=message):
            matchups(schedule({1: rows}))


STAMP = "2026-10-05T02:30:00+00:00"          # 22:30 Eastern on 2026-10-04


class TestMain:
    """main(--from-raw) end to end on a temp data dir. The calendar is built
    around the real clock, because main() reads it: the run lands inside
    period 3. Periods 1 and 2 are final on disk; period 3 is in progress."""

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        data, raw = tmp_path / "data", tmp_path / "raw"
        data.mkdir()
        raw.mkdir()
        now = pd.Timestamp.now(tz="UTC").floor("s")
        self.first = now - 2 * WEEK - pd.Timedelta(days=2)
        self.data = data
        self.write_dim(now)
        TEAMS.to_parquet(data / "dim_fantasy_teams.parquet", index=False)

        self.season_year = 2026
        self.captured = []
        monkeypatch.setattr(fs, "fantrax_public_get",
                            lambda method, league_id, expect=(): {"seasonYear": self.season_year})
        monkeypatch.setattr(fs, "capture", self.captured.append)
        monkeypatch.setattr(fs, "DATA", data)
        monkeypatch.setattr(fs, "SCORING_PATH", data / "fact_period_scoring.parquet")
        monkeypatch.setattr(fs, "MATCHUP_PATH", data / "fact_matchup.parquet")
        monkeypatch.setattr(lg, "PERIODS_PATH", data / "dim_scoring_period.parquet")
        monkeypatch.setattr(fs, "out_path", lambda suffix: raw / f"inseason_{suffix}.json")

        self.raw = raw
        self.save("schedule", schedule({n: [("fa", "12.5", "fb", "12.5")] for n in (1, 2, 3, 4)}))
        for n, final in ((1, True), (2, True), (3, False)):
            self.save_period(n, live(final=final))
        return data

    def write_dim(self, now, closed=()):
        dim(now, closed=closed, first=self.first).to_parquet(
            self.data / "dim_scoring_period.parquet", index=False)

    def save(self, suffix, body, stamp=STAMP):
        head = {"captured_at": stamp} if stamp else {}
        (self.raw / f"inseason_{suffix}.json").write_text(json.dumps({**head, **body}),
                                                          encoding="utf-8")

    def save_period(self, n, reply, stamp=STAMP):
        self.save(f"p{n:02d}", {"period": n, "live_scoring": reply}, stamp)

    def tables(self):
        return (pd.read_parquet(self.data / "fact_period_scoring.parquet"),
                pd.read_parquet(self.data / "fact_matchup.parquet"))

    def test_loads_every_final_period_and_skips_the_one_in_progress(self, env, capsys):
        assert fs.main(["--from-raw"]) == 0
        scores, games = self.tables()
        assert scores.groupby("period").size().to_dict() == {1: 4, 2: 4}
        assert games.groupby("period").size().to_dict() == {1: 2, 2: 2}
        assert not scores.isna().any().any() and not games.isna().any().any()
        assert (scores["season_id"] == SEASON).all()
        assert "[skip] period(s) [3]: games not final" in capsys.readouterr().out

    def test_from_raw_opens_no_browser(self, env):
        fs.main(["--from-raw"])
        assert self.captured == []

    def test_without_from_raw_the_due_periods_are_captured_first(self, env):
        fs.main([])
        assert self.captured == [[1, 2, 3]]
        assert self.tables()[0]["period"].max() == 2

    def test_capture_date_is_the_eastern_day_the_file_was_written(self, env):
        fs.main(["--from-raw"])
        scores, games = self.tables()
        assert (scores["capture_date"] == DAY).all() and (games["capture_date"] == DAY).all()

    def test_a_second_run_changes_nothing(self, env):
        fs.main(["--from-raw"])
        first = self.tables()
        fs.main(["--from-raw"])
        for before, after in zip(first, self.tables()):
            pd.testing.assert_frame_equal(before, after)

    def test_a_period_that_becomes_final_loads_on_the_next_run(self, env):
        fs.main(["--from-raw"])
        self.save_period(3, live())
        fs.main(["--from-raw"])
        assert self.tables()[0].groupby("period").size().to_dict() == {1: 4, 2: 4, 3: 4}

    def test_a_period_that_has_not_started_is_never_loaded(self, env, capsys):
        self.save_period(4, live())                  # a final-looking file for a future period
        assert fs.main(["--from-raw", "--periods", "1-4"]) == 0
        assert set(self.tables()[0]["period"]) == {1, 2}
        assert "[skip] period(s) [4]" in capsys.readouterr().out

    def test_a_closed_period_is_not_loaded_again(self, env):
        self.write_dim(pd.Timestamp.now(tz="UTC"), closed={1})
        fs.main(["--from-raw"])
        assert set(self.tables()[0]["period"]) == {2}

    def test_a_run_replaces_only_the_periods_it_loaded(self, env):
        old = pd.DataFrame({
            "season_id": ["2025-2026", SEASON], "period": [12, 1], "team_key": ["A01", "A01"],
            "scorer_id": ["old", "stale"], "is_starter": [True, True], "fpts": [1.0, 1.0],
            "fpts_offense": [1.0, 1.0], "fpts_defense": [0.0, 0.0],
            "fpts_special_teams": [0.0, 0.0],
            "capture_date": pd.Series([pd.Timestamp("2025-12-01")] * 2, dtype="datetime64[us]")})
        old.to_parquet(self.data / "fact_period_scoring.parquet", index=False)
        fs.main(["--from-raw"])
        ids = set(self.tables()[0]["scorer_id"])
        assert "old" in ids and "stale" not in ids

    def test_nothing_final_writes_nothing(self, env):
        for n in (1, 2):
            self.save_period(n, live(final=False))
        assert fs.main(["--from-raw"]) == 0
        assert not (self.data / "fact_period_scoring.parquet").exists()
        assert not (self.data / "fact_matchup.parquet").exists()

    def test_a_bad_period_writes_nothing(self, env):
        self.save_period(2, live({"fa": team(total=99.0), "fb": team()}))
        with pytest.raises(ValueError, match="Starters sum to"):
            fs.main(["--from-raw"])
        assert not (self.data / "fact_period_scoring.parquet").exists()
        assert not (self.data / "fact_matchup.parquet").exists()

    def test_a_file_without_the_stamp_raises(self, env):
        self.save_period(1, live(), stamp=None)
        with pytest.raises(ValueError, match="has no captured_at"):
            fs.main(["--from-raw"])

    def test_a_missing_file_raises(self, env):
        (self.raw / "inseason_p02.json").unlink()
        with pytest.raises(FileNotFoundError, match="no capture on disk"):
            fs.main(["--from-raw"])

    def test_a_file_holding_another_period_raises(self, env):
        self.save("p02", {"period": 1, "live_scoring": live()})
        with pytest.raises(ValueError, match="holds period 1"):
            fs.main(["--from-raw"])

    def test_a_season_that_is_not_the_raw_files_season_raises(self, env):
        self.season_year = 2027
        with pytest.raises(ValueError, match="snapshot_season is 2026"):
            fs.main(["--from-raw"])

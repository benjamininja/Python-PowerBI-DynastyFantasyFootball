"""04p: the Update-Set state machine and the Division Gate (#117, ADR-0016
amendment decisions 12 and 14).

The parser tests on the real payload shape live in test_fantrax_parsers.py
(TestLeagueInfo). These run on hand-built inputs, because they need instants
and team layouts the capture does not hold: every state transition, a closed
period carried forward, and each way a division can fail to map to one
Conference.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

lg = importlib.import_module("04p_fantrax_league_info")


def ts(text):
    return pd.Timestamp(text, tz="UTC")


START, END, NEXT_END = ts("2026-09-10 00:20"), ts("2026-09-18 00:14:59"), ts("2026-09-25 00:14:59")
SECOND = pd.Timedelta(seconds=1)


def state(now, is_playoff=False, prior=None, checks_pass=False, next_end_at=NEXT_END):
    return lg.update_set_state(START, END, next_end_at, now, is_playoff,
                               prior=prior, checks_pass=checks_pass)


class TestUpdateSetState:
    def test_not_started_has_no_state(self):
        assert state(START - SECOND) is None

    def test_open_from_the_first_instant_to_the_last(self):
        assert state(START) == "open"
        assert state(END) == "open"

    def test_closing_once_the_period_has_ended(self):
        assert state(END + SECOND) == "closing"

    def test_closing_while_the_next_period_is_in_play(self):
        # Checks passing is not enough: the following period must have ended.
        assert state(NEXT_END, checks_pass=True) == "closing"

    def test_closing_until_the_checks_pass(self):
        assert state(NEXT_END + SECOND, checks_pass=False) == "closing"

    def test_closed_when_the_next_period_has_ended_and_checks_pass(self):
        assert state(NEXT_END + SECOND, checks_pass=True) == "closed"

    def test_closed_stays_closed(self):
        # Frozen: failing checks, or a calendar that moved, do not reopen it.
        assert state(NEXT_END + SECOND, prior="closed", checks_pass=False) == "closed"
        assert state(START - SECOND, prior="closed") == "closed"

    def test_open_and_closing_are_not_sticky(self):
        assert state(END + SECOND, prior="open") == "closing"
        assert state(NEXT_END + SECOND, prior="closing", checks_pass=True) == "closed"

    def test_playoff_period_has_no_state(self):
        for now in (START - SECOND, START, END + SECOND, NEXT_END + SECOND):
            assert state(now, is_playoff=True, checks_pass=True) is None

    def test_last_period_never_closes_here(self):
        assert state(NEXT_END + SECOND, checks_pass=True, next_end_at=None) == "closing"


def info(n_periods=4, first_playoff=4, season_year=2026):
    """Weekly periods from 2026-09-10 00:15 UTC; the last one is a playoff."""
    first = ts("2026-09-10 00:15")
    week = pd.Timedelta(weeks=1)
    return {
        "seasonYear": season_year,
        "playoffs": {"lastRegularSeasonPeriod": first_playoff - 1,
                     "firstPlayoffPeriod": first_playoff},
        "scoringPeriods": [
            {"number": n,
             "startDate": (first + (n - 1) * week).isoformat(),
             "endDate": (first + n * week - SECOND).isoformat()}
            for n in range(1, n_periods + 1)],
    }


IN_PERIOD_3 = ts("2026-09-26 12:00")
AFTER_PERIOD_3 = ts("2026-10-02 12:00")


class TestParseScoringPeriods:
    def states(self, df):
        return {p: s if isinstance(s, str) else None
                for p, s in zip(df["period"], df["update_set_state"])}

    def test_no_period_closes_without_passing_checks(self):
        df = lg.parse_scoring_periods(info(), AFTER_PERIOD_3)
        assert self.states(df) == {1: "closing", 2: "closing", 3: "closing", 4: None}
        assert df["closed_at"].isna().all()

    def test_a_period_closes_when_its_checks_pass(self):
        df = lg.parse_scoring_periods(info(), IN_PERIOD_3, checks_passed={1, 2})
        # Period 2's follower (period 3) is still in play, so only 1 closes.
        assert self.states(df) == {1: "closed", 2: "closing", 3: "open", 4: None}
        assert df.set_index("period").loc[1, "closed_at"] == IN_PERIOD_3

    def test_a_closed_period_keeps_its_state_and_stamp(self):
        closed = lg.parse_scoring_periods(info(), IN_PERIOD_3, checks_passed={1})
        again = lg.parse_scoring_periods(info(), AFTER_PERIOD_3, prior=closed)
        row = again.set_index("period").loc[1]
        assert (row["update_set_state"], row["closed_at"]) == ("closed", IN_PERIOD_3)
        assert self.states(again)[2] == "closing"      # not carried: it was never closed

    def test_another_seasons_rows_are_not_read(self):
        closed = lg.parse_scoring_periods(info(), IN_PERIOD_3, checks_passed={1})
        closed["season_id"] = "2025-2026"
        again = lg.parse_scoring_periods(info(), AFTER_PERIOD_3, prior=closed)
        assert self.states(again)[1] == "closing"

    def test_rerun_at_the_same_instant_is_identical(self):
        first = lg.parse_scoring_periods(info(), IN_PERIOD_3)
        again = lg.parse_scoring_periods(info(), IN_PERIOD_3, prior=first)
        pd.testing.assert_frame_equal(first, again)

    def test_season_id_from_the_season_year(self):
        df = lg.parse_scoring_periods(info(season_year="2027"), IN_PERIOD_3)
        assert set(df["season_id"]) == {"2027-2028"}

    def test_periods_out_of_order_are_sorted(self):
        raw = info()
        raw["scoringPeriods"].reverse()
        assert list(lg.parse_scoring_periods(raw, IN_PERIOD_3)["period"]) == [1, 2, 3, 4]

    def test_a_missing_period_raises(self):
        raw = info()
        del raw["scoringPeriods"][1]
        with pytest.raises(ValueError, match="not numbered"):
            lg.parse_scoring_periods(raw, IN_PERIOD_3)

    def test_overlapping_periods_raise(self):
        raw = info()
        raw["scoringPeriods"][1]["startDate"] = raw["scoringPeriods"][0]["startDate"]
        with pytest.raises(ValueError, match="starts before"):
            lg.parse_scoring_periods(raw, IN_PERIOD_3)

    def test_a_period_that_ends_before_it_starts_raises(self):
        raw = info()
        p = raw["scoringPeriods"][0]
        p["startDate"], p["endDate"] = p["endDate"], p["startDate"]
        with pytest.raises(ValueError, match="does not start before"):
            lg.parse_scoring_periods(raw, IN_PERIOD_3)

    def test_playoff_keys_must_agree(self):
        raw = info()
        del raw["playoffs"]["firstPlayoffPeriod"]
        with pytest.raises(ValueError, match="firstPlayoffPeriod"):
            lg.parse_scoring_periods(raw, IN_PERIOD_3)
        raw = info()
        raw["playoffs"]["lastRegularSeasonPeriod"] = 1
        with pytest.raises(ValueError, match="lastRegularSeasonPeriod"):
            lg.parse_scoring_periods(raw, IN_PERIOD_3)


TEAMS = pd.DataFrame({"fantrax_team_id": ["t1", "t2", "t3", "t4"],
                      "conference": ["A", "A", "B", "B"]})


def team_info(divisions):
    return {"teamInfo": {tid: {"id": tid, "division": d} for tid, d in divisions.items()}}


GOOD = {"t1": "Riddell ", "t2": "Riddell ", "t3": "Wilson", "t4": "Wilson"}


class TestParseDivisions:
    def test_one_row_per_conference(self):
        df = lg.parse_divisions(team_info(GOOD), TEAMS, "2026-2027")
        assert list(df.columns) == ["season_id", "conference", "division_name"]
        assert list(zip(df["conference"], df["division_name"])) == [("A", "Riddell"), ("B", "Wilson")]

    def test_team_info_as_a_list(self):
        raw = {"teamInfo": list(team_info(GOOD)["teamInfo"].values())}
        assert len(lg.parse_divisions(raw, TEAMS, "2026-2027")) == 2

    def test_division_across_two_conferences_raises(self):
        with pytest.raises(ValueError, match="not one-to-one"):
            lg.parse_divisions(team_info({**GOOD, "t3": "Riddell"}), TEAMS, "2026-2027")

    def test_two_divisions_in_one_conference_raise(self):
        with pytest.raises(ValueError, match="not one-to-one"):
            lg.parse_divisions(team_info({**GOOD, "t2": "Spalding"}), TEAMS, "2026-2027")

    def test_unknown_team_raises(self):
        with pytest.raises(ValueError, match="not in dim_fantasy_teams"):
            lg.parse_divisions(team_info({**GOOD, "t9": "Wilson"}), TEAMS, "2026-2027")

    def test_blank_division_raises(self):
        with pytest.raises(ValueError, match="has no division"):
            lg.parse_divisions(team_info({**GOOD, "t4": " "}), TEAMS, "2026-2027")

    def test_conference_with_no_team_raises(self):
        only_a = {k: v for k, v in GOOD.items() if k in ("t1", "t2")}
        with pytest.raises(ValueError, match="no teamInfo team"):
            lg.parse_divisions(team_info(only_a), TEAMS, "2026-2027")

"""04r: which Scoring Periods are read, the reply checks, the parser's failure
modes and a run of main() (#117, ADR-0016 amendment decisions 3 and 14).

The parser tests on the real payload shape live in test_fantrax_parsers.py
(TestPublicRosters). These run on hand-built inputs: the calendar positions,
bad replies and bad rows a capture does not hold. Nothing here touches the
network; main() runs against a temp data dir with a canned Fantrax.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

lg = importlib.import_module("04p_fantrax_league_info")
rs = importlib.import_module("04r_fantrax_roster_state")

SEASON = "2026-2027"
WEEK = pd.Timedelta(weeks=1)
SECOND = pd.Timedelta(seconds=1)


def ts(text):
    return pd.Timestamp(text, tz="UTC")


FIRST = ts("2026-09-10 00:15")


def league_info(first=FIRST, n_periods=6, first_playoff=5):
    """Weekly periods from `first`; periods 5 and 6 are playoffs."""
    return {
        "seasonYear": 2026,
        "playoffs": {"lastRegularSeasonPeriod": first_playoff - 1,
                     "firstPlayoffPeriod": first_playoff},
        "scoringPeriods": [
            {"number": n,
             "startDate": (first + (n - 1) * WEEK).isoformat(),
             "endDate": (first + n * WEEK - SECOND).isoformat()}
            for n in range(1, n_periods + 1)],
    }


def dim(now, closed=(), first=FIRST):
    """dim_scoring_period rows as 04p writes them at `now`."""
    return lg.parse_scoring_periods(league_info(first), now, checks_passed=set(closed))


IN_PERIOD_3 = FIRST + 2 * WEEK + pd.Timedelta(days=2)
IN_PLAYOFFS = FIRST + 5 * WEEK + pd.Timedelta(days=2)       # period 6


class TestPeriodsToPull:
    def test_every_started_regular_season_period(self):
        assert rs.periods_to_pull(dim(IN_PERIOD_3), 3, IN_PERIOD_3) == [1, 2, 3]

    def test_never_past_the_period_fantrax_calls_current(self):
        # The calendar says 3 has started; Fantrax has not moved on yet.
        assert rs.periods_to_pull(dim(IN_PERIOD_3), 2, IN_PERIOD_3) == [1, 2]

    def test_never_a_period_the_calendar_says_has_not_started(self):
        # Fantrax is a period ahead: asking for 4 would return a future roster.
        assert rs.periods_to_pull(dim(IN_PERIOD_3), 4, IN_PERIOD_3) == [1, 2, 3]

    def test_a_closed_period_is_not_read_again(self):
        periods = dim(IN_PERIOD_3, closed={1})
        assert periods.set_index("period").loc[1, "update_set_state"] == "closed"
        assert rs.periods_to_pull(periods, 3, IN_PERIOD_3) == [2, 3]

    def test_playoff_periods_are_never_read(self):
        assert rs.periods_to_pull(dim(IN_PLAYOFFS), 6, IN_PLAYOFFS) == [1, 2, 3, 4]

    def test_nothing_before_period_1_starts(self):
        before = FIRST - SECOND
        assert rs.periods_to_pull(dim(before), 1, before) == []

    def test_the_first_instant_of_a_period_counts(self):
        start_of_2 = FIRST + WEEK
        assert rs.periods_to_pull(dim(start_of_2), 2, start_of_2) == [1, 2]
        assert rs.periods_to_pull(dim(start_of_2), 2, start_of_2 - SECOND) == [1]


class TestPeriodInPlay:
    def test_the_period_holding_now(self):
        assert rs.period_in_play(dim(IN_PERIOD_3), IN_PERIOD_3) == 3

    def test_a_playoff_period_counts(self):
        assert rs.period_in_play(dim(IN_PLAYOFFS), IN_PLAYOFFS) == 6

    def test_none_out_of_season(self):
        periods = dim(IN_PERIOD_3)
        assert rs.period_in_play(periods, FIRST - SECOND) is None
        assert rs.period_in_play(periods, FIRST + 6 * WEEK) is None


def test_league_day_is_the_eastern_day():
    # 02:00 UTC on the 4th is 22:00 on the 3rd in New York.
    assert rs.league_day(ts("2026-10-04 02:00")) == pd.Timestamp("2026-10-03")


TEAMS = pd.DataFrame({"fantrax_team_id": ["fa", "fb"], "team_key": ["A01", "B01"]})
CONTRACTS = {"Minor", "1st", "FA"}
DAY = pd.Timestamp("2026-10-04")


def item(scorer_id="p1", status="ACTIVE", salary=2000000.0, contract="1st"):
    return {"id": scorer_id, "status": status, "salary": salary,
            "contract": None if contract is None else {"name": contract}}


def reply(period, rosters=None):
    """A getTeamRosters reply: by default one player (the same one) per team."""
    if rosters is None:
        rosters = {"fa": [item()], "fb": [item()]}
    return {"period": period,
            "rosters": {tid: {"rosterItems": items} for tid, items in rosters.items()}}


class TestCheckReply:
    def test_returns_the_echoed_period(self):
        assert rs.check_reply(reply(3), 3, TEAMS["fantrax_team_id"]) == 3
        assert rs.check_reply(reply("3"), None, TEAMS["fantrax_team_id"]) == 3

    def test_another_period_than_asked_raises(self):
        with pytest.raises(ValueError, match="period=4 echoed period 3"):
            rs.check_reply(reply(3), 4, TEAMS["fantrax_team_id"])

    def test_a_missing_team_raises(self):
        with pytest.raises(ValueError, match=r"1 teams, expected 2 \(missing \['fb'\]"):
            rs.check_reply(reply(3, {"fa": [item()]}), 3, TEAMS["fantrax_team_id"])

    def test_a_team_the_dim_lacks_raises(self):
        rosters = {"fa": [item()], "fb": [item()], "fz": [item()]}
        with pytest.raises(ValueError, match=r"not in dim_fantasy_teams \['fz'\]"):
            rs.check_reply(reply(3, rosters), 3, TEAMS["fantrax_team_id"])


def state(rosters, period=3):
    return rs.rosters_to_state(reply(period, rosters), TEAMS, CONTRACTS, SEASON, period, DAY)


class TestRostersToState:
    def test_the_same_player_on_two_teams_is_two_rows(self):
        df = state({"fa": [item("p1")], "fb": [item("p1")]})
        assert list(zip(df["team_key"], df["scorer_id"])) == [("A01", "p1"), ("B01", "p1")]

    def test_a_repeated_row_on_one_team_keeps_the_first(self):
        df = state({"fa": [item("p1", "ACTIVE"), item("p1", "RESERVE")], "fb": [item("p2")]})
        assert df[df["team_key"] == "A01"]["roster_slot"].tolist() == ["Starter"]

    def test_rows_come_out_in_key_order(self):
        df = state({"fb": [item("p9"), item("p2")], "fa": [item("p5"), item("p3")]})
        assert list(zip(df["team_key"], df["scorer_id"])) == [
            ("A01", "p3"), ("A01", "p5"), ("B01", "p2"), ("B01", "p9")]

    def test_salary_is_kept_to_the_cent(self):
        df = state({"fa": [item(salary=2500000.5)], "fb": [item(salary=3000000)]})
        assert df["salary"].tolist() == [2500000.5, 3000000.0]

    @pytest.mark.parametrize("bad, message", [
        (item(status="TAXI"), "unknown roster status 'TAXI'"),
        (item(contract="7th"), "contract '7th' is not in dim_contract"),
        (item(contract=None), "contract None is not in dim_contract"),
        (item(salary=None), "no salary"),
        (item(scorer_id=""), "no player id"),
    ])
    def test_a_bad_row_raises(self, bad, message):
        with pytest.raises(ValueError, match=message):
            state({"fa": [item("p1"), bad], "fb": [item("p2")]})

    def test_a_team_the_dim_lacks_raises(self):
        with pytest.raises(ValueError, match="fz is not in dim_fantasy_teams"):
            state({"fa": [item()], "fz": [item()]})

    def test_a_team_with_no_rows_raises(self):
        with pytest.raises(ValueError, match="team fb has no roster rows"):
            state({"fa": [item()], "fb": []})


class Fantrax:
    """A canned getTeamRosters: `current` is the period a call with no period
    echoes; `echo` overrides what an asked period echoes."""

    def __init__(self, current, echo=None, bad_period=None):
        self.current, self.echo, self.bad_period = current, echo or {}, bad_period
        self.asked = []

    def __call__(self, period):
        self.asked.append(period)
        echoed = self.current if period is None else self.echo.get(period, period)
        if echoed == self.bad_period:
            return reply(echoed, {"fa": [item(status="TAXI")], "fb": [item()]})
        return reply(echoed)


def collect(fantrax, now=IN_PERIOD_3, closed=()):
    return rs.collect(fantrax, dim(now, closed), TEAMS, CONTRACTS, SEASON, now)


class TestCollect:
    def test_one_call_per_period_and_the_current_reply_is_reused(self):
        fantrax = Fantrax(current=3)
        df, current = collect(fantrax)
        assert fantrax.asked == [None, 1, 2] and current == 3
        assert df.groupby("period").size().to_dict() == {1: 2, 2: 2, 3: 2}
        assert (df["season_id"] == SEASON).all()
        assert (df["capture_date"] == rs.league_day(IN_PERIOD_3)).all()

    def test_no_period_past_fantraxs_current_is_asked_for(self):
        fantrax = Fantrax(current=2)
        df, _ = collect(fantrax)
        assert fantrax.asked == [None, 1] and set(df["period"]) == {1, 2}

    def test_no_period_the_calendar_has_not_started_is_asked_for(self):
        fantrax = Fantrax(current=4)
        df, _ = collect(fantrax)
        assert fantrax.asked == [None, 1, 2, 3] and set(df["period"]) == {1, 2, 3}

    def test_in_the_playoffs_the_current_reply_is_not_stored(self):
        fantrax = Fantrax(current=6)
        df, current = collect(fantrax, now=IN_PLAYOFFS)
        assert fantrax.asked == [None, 1, 2, 3, 4] and current == 6
        assert set(df["period"]) == {1, 2, 3, 4}

    def test_a_closed_period_is_not_asked_for(self):
        fantrax = Fantrax(current=3)
        df, _ = collect(fantrax, closed={1})
        assert fantrax.asked == [None, 2] and set(df["period"]) == {2, 3}

    def test_nothing_due_gives_an_empty_frame(self):
        fantrax = Fantrax(current=1)
        df, current = collect(fantrax, now=FIRST - SECOND)
        assert fantrax.asked == [None] and current == 1
        assert df.empty and list(df.columns) == rs.STATE_COLUMNS

    def test_a_reply_for_the_wrong_period_raises(self):
        with pytest.raises(ValueError, match="period=2 echoed period 3"):
            collect(Fantrax(current=3, echo={2: 3}))

    def test_a_bad_row_in_any_period_raises(self):
        with pytest.raises(ValueError, match="unknown roster status"):
            collect(Fantrax(current=3, bad_period=2))


class TestMain:
    """main() end to end on a temp data dir. The calendar is built around the
    real clock, because main() reads it: the run lands inside period 3."""

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        data, raw = tmp_path / "data", tmp_path / "raw"
        data.mkdir()
        now = pd.Timestamp.now(tz="UTC").floor("s")
        first = now - 2 * WEEK - pd.Timedelta(days=2)
        dim(now, first=first).to_parquet(data / "dim_scoring_period.parquet", index=False)
        TEAMS.to_parquet(data / "dim_fantasy_teams.parquet", index=False)
        pd.DataFrame({"contract_id": sorted(CONTRACTS)}).to_parquet(
            data / "dim_contract.parquet", index=False)

        fantrax = Fantrax(current=3)

        def public_get(method, league_id, expect=(), **params):
            if method == "getLeagueInfo":
                return {"seasonYear": self.season_year}
            assert method == "getTeamRosters"
            return fantrax(params.get("period"))

        self.season_year = 2026
        monkeypatch.setattr(rs, "fantrax_public_get", public_get)
        monkeypatch.setattr(rs, "DATA", data)
        monkeypatch.setattr(rs, "STATE_PATH", data / "fact_roster_state.parquet")
        monkeypatch.setattr(lg, "PERIODS_PATH", data / "dim_scoring_period.parquet")
        monkeypatch.setattr(rs.FX_CFG, "raw_dir", str(raw))
        monkeypatch.setattr(rs.time, "sleep", lambda s: None)
        return data, raw, fantrax

    def test_writes_every_due_period_and_the_raw_replies(self, env):
        data, raw, fantrax = env
        assert rs.main() == 0
        df = pd.read_parquet(data / "fact_roster_state.parquet")
        assert df.groupby("period").size().to_dict() == {1: 2, 2: 2, 3: 2}
        assert not df.isna().any().any()
        assert sorted(p.name for p in raw.iterdir()) == [
            f"fantrax_public_rosters_2026_p0{n}.json" for n in (1, 2, 3)]

    def test_a_second_run_changes_nothing(self, env):
        data = env[0]
        rs.main()
        first = pd.read_parquet(data / "fact_roster_state.parquet")
        rs.main()
        pd.testing.assert_frame_equal(first, pd.read_parquet(data / "fact_roster_state.parquet"))

    def test_a_run_replaces_only_the_periods_it_read(self, env):
        data = env[0]
        old = pd.DataFrame({
            "season_id": ["2025-2026", SEASON], "period": [12, 1], "team_key": ["A01", "A01"],
            "scorer_id": ["old", "stale"], "roster_slot": ["Bench", "Bench"],
            "salary": [1.0, 1.0], "contract_id": ["FA", "FA"],
            "capture_date": pd.Series([pd.Timestamp("2025-12-01")] * 2, dtype="datetime64[us]")})
        old.to_parquet(data / "fact_roster_state.parquet", index=False)
        rs.main()
        df = pd.read_parquet(data / "fact_roster_state.parquet")
        assert "old" in set(df["scorer_id"])              # another season's period: kept
        assert "stale" not in set(df["scorer_id"])        # this season's period 1: replaced

    def test_a_bad_reply_writes_nothing(self, env):
        data, _, fantrax = env
        fantrax.echo = {2: 3}
        with pytest.raises(ValueError, match="echoed period 3"):
            rs.main()
        assert not (data / "fact_roster_state.parquet").exists()

    def test_a_season_the_period_dim_lacks_raises(self, env):
        self.season_year = 2027
        with pytest.raises(ValueError, match="2027-2028 is not in dim_scoring_period"):
            rs.main()

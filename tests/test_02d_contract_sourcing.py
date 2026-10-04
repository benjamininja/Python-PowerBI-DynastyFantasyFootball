"""Contract and salary sourcing in 02d (#113, ADR-0019 decision 6; #125; #117).

A Roster Move's contract is read off Roster State, one roster per Scoring
Period. A draft pick and a claim start a stint and read the first row inside
it; a trade and a drop end one and read the latest row before they take
effect. A default applies only when no row covers the move. A stint-starting
move's salary is read off the preseason capture, else off that same first
row. These tests build the lookups by hand; only TestPublishedDimContract
reads data/ (the seeded dim_contract).
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

rt = importlib.import_module("02d_fact_roster_transactions")

CONTRACTS = pd.DataFrame({
    "contract_id": ["Minor", "1st", "2nd", "FA"],
    "contract_year": pd.array([pd.NA, 1, 2, 1], dtype="Int64"),
    "cap_hit_pct": [0.0, 0.5, 0.4, 0.0],
    "min_salary": [None, None, None, 2_000_000.0],
})
YEAR = 2026
SEASON = "2026-2027"
LAST_SEASON, NEXT_SEASON = "2025-2026", "2027-2028"
SPANS = [(pd.Timestamp("2025-03-01"), pd.Timestamp("2026-02-28"), LAST_SEASON),
         (pd.Timestamp("2026-03-01"), pd.Timestamp("2027-02-28"), SEASON),
         (pd.Timestamp("2027-03-01"), pd.Timestamp("2028-02-29"), NEXT_SEASON)]
CONF = {"A01": "A", "A02": "A", "B01": "B"}
DRAFTED = pd.Timestamp("2026-06-11")
PRESEASON_DAY = "2026-07-18"
MOVE = pd.Timestamp("2026-09-20 14:00")
MOVE_PERIOD = 3                 # the Scoring Period Fantrax stamps MOVE with
MINIMUM = 2_000_000.0           # CONTRACTS' league minimum
SALARY = 5_000_000.0            # a Roster State row's salary when the test does not care
NO_FLAGS = {"observed": 0, "after_newest": 0, "left_list": 0, "stale_capture": 0}


def read_day(period):
    """The day a Scoring Period's roster was last read: the day after it ended
    (period 1 ends 2026-09-17)."""
    return pd.Timestamp("2026-09-11") + pd.Timedelta(weeks=period)


def _stamp(day):
    return pd.NaT if day is None else pd.Timestamp(day)


def state(*rows, season=SEASON):
    """fact_roster_state rows: (team_key, scorer_id, period, contract_id[,
    salary[, capture_date]]). A row carries SALARY, and was read on
    read_day(period), unless it says otherwise."""
    recs = []
    for team, sid, period, contract, *rest in rows:
        salary = rest[0] if rest else SALARY
        captured = rest[1] if len(rest) > 1 else read_day(period)
        recs.append((season, period, team, sid, "Bench", salary, contract, _stamp(captured)))
    return pd.DataFrame(recs, columns=["season_id", "period", "team_key", "scorer_id",
                                       "roster_slot", "salary", "contract_id", "capture_date"])


def preseason(*rows, season=SEASON):
    """fact_preseason_salary rows: (team_key, scorer_id, salary[, capture_date]),
    captured on PRESEASON_DAY unless a row says otherwise."""
    recs = [(season, team, sid, salary, _stamp(rest[0] if rest else PRESEASON_DAY))
            for team, sid, salary, *rest in rows]
    return pd.DataFrame(recs, columns=["season_id", "team_key", "scorer_id", "salary",
                                       "capture_date"])


def adp(*rows):
    """fact_fantrax_adp rows: (scorer_id, season, week, capture_date, salary)."""
    return pd.DataFrame(rows, columns=["scorer_id", "season", "week", "capture_date", "salary"])


def eligibility(by_day, season=YEAR):
    """by_day: {capture_date: [scorer_id, ...]}."""
    return pd.DataFrame([{"season": season, "capture_date": day, "scorer_id": sid}
                         for day, sids in by_day.items() for sid in sids])


def source(rosters=None, elig=None, pre=None):
    return rt.contract_source(rosters, pre, elig, CONTRACTS, season_id=SEASON, season=YEAR)


def base(*rows):
    """Startup ledger rows: (team_key, asset_id, contract_id, contract_value)."""
    cols = ["team_key", "asset_id", "event_seq", "event_date", "season_id", "contract_id",
            "contract_year", "contract_value", "cap_hit", "status"]
    return pd.DataFrame([(t, a, i, DRAFTED, SEASON, c, 1.0, v, v * 0.5, "active")
                         for i, (t, a, c, v) in enumerate(rows, 1)], columns=cols)


def leg(kind, sid, team_to, team_from=pd.NA, when=MOVE, period=MOVE_PERIOD):
    """A transaction leg, as parse_txn_rows emits it. `period` is the Scoring
    Period the move takes effect in: 1 for an offseason move."""
    return {"kind": kind, "scorer_id": sid, "team_from": team_from, "team_to": team_to,
            "event_dt": when, "period": period}


def resolve_all(legs, src, startup=None):
    """resolve_legs' full return: (rows, missing_source, fa_fallback, sourcing,
    roster_priced)."""
    startup = base() if startup is None else startup
    return rt.resolve_legs(legs, startup, {"p1": 1, "p2": 2}, CONF, {},
                           SPANS, rt.fa_terms(CONTRACTS), src)


def resolve(legs, src, startup=None):
    return pd.DataFrame(resolve_all(legs, src, startup)[0])


class TestIndexState:
    def test_rows_are_indexed_per_copy_by_period(self):
        snaps = rt.index_state(state(("A01", "p1", 2, "2nd", 6_000_000),
                                     ("A01", "p1", 1, "1st"),
                                     ("A02", "p2", 1, "FA")), SEASON)
        assert snaps == {
            ("A01", "p1"): [rt.Seen(1, read_day(1), "1st", SALARY),
                            rt.Seen(2, read_day(2), "2nd", 6_000_000.0)],
            ("A02", "p2"): [rt.Seen(1, read_day(1), "FA", SALARY)]}

    def test_rows_with_no_contract_salary_or_period_are_left_out(self):
        snaps = rt.index_state(state(("A01", "p1", 1, "1st"),
                                     ("A01", "p1", 2, None),
                                     ("A01", "p1", 3, "2nd", None),
                                     ("A01", "p1", None, "2nd", SALARY, "2026-10-09"),
                                     ("A02", "p2", 2, None)), SEASON)
        assert set(snaps) == {("A01", "p1")}
        assert [s.period for s in snaps[("A01", "p1")]] == [1]

    def test_rows_with_no_capture_date_are_left_out(self):
        snaps = rt.index_state(state(("A01", "p1", 1, "1st"),
                                     ("A01", "p1", 2, "2nd", SALARY, None)), SEASON)
        assert rt.latest_before(snaps, "A01", "p1", MOVE_PERIOD).contract_id == "1st"

    def test_no_roster_state_table(self):
        assert rt.index_state(None, SEASON) == {}
        assert rt.index_state(state(), SEASON) == {}


class TestLatestBefore:
    SNAPS = rt.index_state(state(("A01", "p1", 1, "1st"),
                                 ("A01", "p1", 2, "2nd"),
                                 ("A01", "p1", 4, "Minor")), SEASON)

    def _contract(self, period, since=None, team="A01"):
        seen = rt.latest_before(self.SNAPS, team, "p1", period, since)
        return None if seen is None else seen.contract_id

    def test_latest_row_before_the_moves_period(self):
        assert self._contract(MOVE_PERIOD) == "2nd"
        assert self._contract(2) == "1st"
        assert rt.latest_before(self.SNAPS, "A01", "p1", 9) == rt.Seen(
            4, read_day(4), "Minor", SALARY)

    def test_the_moves_own_period_is_not_read(self):
        # A period's roster already shows the moves that take effect in it.
        assert self._contract(4) == "2nd"
        assert self._contract(5) == "Minor"

    def test_nothing_before_the_first_period_on_record(self):
        assert self._contract(1) is None

    def test_another_team_or_no_period(self):
        assert self._contract(MOVE_PERIOD, team="A02") is None
        assert self._contract(None) is None
        assert self._contract(pd.NA) is None

    def test_rows_from_before_the_stint_are_ignored(self):
        # joined in period 3: the rows of periods 1 and 2 belong to an earlier stint
        assert self._contract(4, since=3) is None
        # the row of the period the copy joined in counts
        assert self._contract(MOVE_PERIOD, since=2) == "2nd"
        assert self._contract(5, since=3) == "Minor"
        assert self._contract(5, since=5) is None

    def test_a_stint_that_starts_in_the_moves_period_reads_nothing(self):
        assert self._contract(MOVE_PERIOD, since=MOVE_PERIOD) is None

    def test_no_stint_on_record_reads_any_earlier_row(self):
        assert self._contract(MOVE_PERIOD, since=None) == "2nd"
        assert self._contract(MOVE_PERIOD, since=pd.NA) == "2nd"


class TestFirstInStint:
    P1 = ("A01", "p1", 1, "1st", 5_000_000)        # read 09-18
    P2 = ("A01", "p1", 2, "2nd", 6_000_000)        # read 09-25
    JOINED = pd.Timestamp("2026-07-01 09:00")

    def _seen(self, rows, period=1, when=JOINED, until=None, team="A01"):
        return rt.first_in_stint(rt.index_state(state(*rows), SEASON), team, "p1",
                                 period, when, until)

    def test_first_row_from_the_moves_own_period_on(self):
        assert self._seen([self.P1, self.P2]) == rt.Seen(1, read_day(1), "1st", 5_000_000.0)
        assert self._seen([self.P1, self.P2], period=2).salary == 6_000_000
        # no row for the move's own period: the next one inside the stint
        assert self._seen([self.P2]).period == 2

    def test_a_row_captured_on_or_before_the_move_day_is_skipped(self):
        both = [self.P1, self.P2]
        assert self._seen(both, when=pd.Timestamp("2026-09-17 23:00")).period == 1
        assert self._seen(both, when=pd.Timestamp("2026-09-18 08:00")).period == 2
        assert self._seen(both, when=pd.Timestamp("2026-09-21")).period == 2
        assert self._seen(both, when=pd.Timestamp("2026-09-25 08:00")) is None

    def test_a_move_with_no_date_skips_the_capture_guard(self):
        assert self._seen([self.P1], when=pd.NaT).period == 1

    def test_nothing_after_the_newest_period_on_record(self):
        assert self._seen([self.P1, self.P2], period=3) is None

    def test_stops_at_the_period_the_copy_left_in(self):
        assert self._seen([self.P1, self.P2], until=1) is None
        assert self._seen([self.P1, self.P2], until=2).period == 1
        # a later stint's row is out of reach
        assert self._seen([self.P2], until=2) is None
        assert self._seen([self.P2], until=3).period == 2

    def test_a_move_with_no_period_reads_nothing(self):
        assert self._seen([self.P1], period=None) is None
        assert self._seen([self.P1], period=pd.NA) is None

    def test_another_teams_row_is_not_read(self):
        assert self._seen([self.P1], team="A02") is None

    def test_no_roster_state_table(self):
        assert rt.first_in_stint({}, "A01", "p1", 1, self.JOINED) is None


class TestPreseasonSalary:
    PRE = rt.index_preseason(preseason(("A01", "p1", 5_000_000)), SEASON)     # captured 07-18
    JOINED = pd.Timestamp("2026-07-01 09:00")

    def _salary(self, when=JOINED, until=None, team="A01"):
        return rt.preseason_salary(self.PRE, team, "p1", when, until)

    def test_a_capture_after_the_move_day_is_read(self):
        assert self._salary() == 5_000_000

    def test_a_capture_dated_the_move_day_is_not_read(self):
        assert self._salary(when=pd.Timestamp("2026-07-18 08:00")) is None
        assert self._salary(when=pd.Timestamp("2026-07-17 23:00")) == 5_000_000
        assert self._salary(when=pd.Timestamp("2026-07-20")) is None

    def test_a_copy_that_left_before_the_capture_is_not_priced_by_it(self):
        assert self._salary(until=pd.Timestamp("2026-07-10")) is None
        assert self._salary(until=pd.Timestamp("2026-07-18 20:00")) is None
        assert self._salary(until=pd.Timestamp("2026-07-19")) == 5_000_000

    def test_rows_with_no_salary_or_no_date_are_left_out(self):
        blank = ("A01", "p2", None)
        undated = ("A02", "p2", 9_000_000, None)
        index = rt.index_preseason(preseason(blank, undated, ("B01", "p2", 6_000_000)), SEASON)
        assert index == {("B01", "p2"): (pd.Timestamp(PRESEASON_DAY), 6_000_000.0)}

    def test_another_team_or_no_date(self):
        assert self._salary(team="A02") is None
        assert self._salary(when=pd.NaT) is None

    def test_no_preseason_table(self):
        assert rt.index_preseason(None, SEASON) == {}
        assert rt.index_preseason(preseason(), SEASON) == {}
        assert rt.preseason_salary({}, "A01", "p1", self.JOINED) is None


class TestSeasonBound:
    def test_index_state_keeps_only_the_asked_season(self):
        rosters = pd.concat([state(("A01", "p1", 1, "1st")),
                             state(("A01", "p1", 2, "2nd"), season=NEXT_SEASON)])
        assert [s.contract_id for s in rt.index_state(rosters, SEASON)[("A01", "p1")]] == ["1st"]
        assert [s.contract_id
                for s in rt.index_state(rosters, NEXT_SEASON)[("A01", "p1")]] == ["2nd"]
        assert rt.index_state(rosters, LAST_SEASON) == {}

    def test_index_preseason_keeps_only_the_asked_season(self):
        pre = pd.concat([preseason(("A01", "p1", 5_000_000)),
                         preseason(("A01", "p2", 7_000_000), season=NEXT_SEASON)])
        assert rt.index_preseason(pre, SEASON) == {
            ("A01", "p1"): (pd.Timestamp(PRESEASON_DAY), 5_000_000.0)}
        assert set(rt.index_preseason(pre, NEXT_SEASON)) == {("A01", "p2")}

    def test_index_eligibility_keeps_only_the_asked_season(self):
        elig = pd.concat([eligibility({"2025-09-17": ["p2"]}, season=2025),
                          eligibility({"2026-09-17": ["p1"]})])
        assert rt.index_eligibility(elig, season=YEAR) == [(pd.Timestamp("2026-09-17"), {"p1"})]
        assert len(rt.index_eligibility(elig)) == 2

    def test_an_old_seasons_list_cannot_default_a_move_to_minor(self):
        # p2 was eligible last season and is on no list this season.
        elig = pd.concat([eligibility({"2025-09-17": ["p2"]}, season=2025),
                          eligibility({"2026-09-17": ["p1"]})])
        got = rt.resolve_contract(source(elig=elig), rt.CLAIM_EVENT, "p2",
                                  pd.Timestamp("2026-08-01"))
        assert got == rt.Sourced("FA")

    def test_the_source_holds_one_season(self):
        rosters = pd.concat([state(("A01", "p1", 1, "1st")),
                             state(("A02", "p2", 1, "2nd"), season=NEXT_SEASON)])
        pre = pd.concat([preseason(("A01", "p1", 5_000_000)),
                         preseason(("A02", "p2", 7_000_000), season=NEXT_SEASON)])
        src = rt.contract_source(rosters, pre, None, CONTRACTS, season_id=NEXT_SEASON, season=2027)
        assert src.season == NEXT_SEASON
        assert set(src.snaps) == set(src.preseason) == {("A02", "p2")}

    def test_a_leg_dated_in_another_season_reads_no_roster(self):
        src = source(state(("A01", "p2", 2, "2nd"), ("A02", "p1", 1, "1st", 8_200_000)),
                     pre=preseason(("A02", "p1", 7_500_000)))
        startup = base(("A01", 2, "1st", 9_000_000))

        def legs(drop_day, claim_day):
            return [leg(rt.DROP_EVENT, "p2", "A01", when=drop_day),
                    leg(rt.CLAIM_EVENT, "p1", "A02", when=claim_day, period=1)]

        # Next season's drop and last season's claim: this season's rosters cover neither.
        rows, _, fa_fallback, sourcing, priced = resolve_all(
            legs(pd.Timestamp("2027-09-20"), pd.Timestamp("2026-02-10")), src, startup)
        by_kind = {r["event_type"]: r for r in rows}
        assert by_kind["drop"]["season_id"] == NEXT_SEASON
        assert by_kind["drop"]["contract_id"] == "1st"
        assert by_kind["claim"]["season_id"] == LAST_SEASON
        assert (by_kind["claim"]["contract_id"], by_kind["claim"]["contract_value"]) == (
            "FA", MINIMUM)
        assert sourcing["observed"] == 0 and priced == [] and fa_fallback == ["p1"]

        # The same legs dated this season read them.
        rows, _, _, sourcing, priced = resolve_all(
            legs(MOVE, pd.Timestamp("2026-07-10")), src, startup)
        by_kind = {r["event_type"]: r for r in rows}
        assert by_kind["drop"]["contract_id"] == "2nd"
        assert (by_kind["claim"]["contract_id"], by_kind["claim"]["contract_value"]) == (
            "1st", 7_500_000)
        assert sourcing["observed"] == 2 and priced == ["p1"]


class TestEligibleAt:
    # p1 stays eligible; p2 graduates between the two captures.
    ELIG = rt.index_eligibility(eligibility({"2026-07-18": ["p1", "p2"], "2026-09-17": ["p1"]}))

    def test_the_capture_on_or_after_the_move_decides_first(self):
        assert rt.eligible_at(self.ELIG, "p2", pd.Timestamp("2026-06-11")) == "next"
        assert rt.eligible_at(self.ELIG, "p2", pd.Timestamp("2026-07-18 09:00")) == "next"
        assert rt.eligible_at(self.ELIG, "p1", pd.Timestamp("2026-08-01")) == "next"

    def test_the_capture_before_the_move_also_counts(self):
        # p2 is off the 09-17 list but on the 07-18 one: graduated in between,
        # on an unknown side of the move.
        assert rt.eligible_at(self.ELIG, "p2", pd.Timestamp("2026-08-01")) == "previous"

    def test_after_the_newest_capture_it_is_the_only_one_to_read(self):
        assert rt.eligible_at(self.ELIG, "p1", pd.Timestamp("2026-10-01")) == "newest"
        assert rt.eligible_at(self.ELIG, "p2", pd.Timestamp("2026-10-01")) is None

    def test_only_the_neighbouring_captures_count(self):
        elig = rt.index_eligibility(eligibility(
            {"2026-07-18": ["p2"], "2026-09-10": ["p1"], "2026-09-17": ["p1"]}))
        assert rt.eligible_at(elig, "p2", pd.Timestamp("2026-09-15")) is None

    def test_a_single_capture(self):
        elig = rt.index_eligibility(eligibility({"2026-07-18": ["p1"]}))
        assert rt.eligible_at(elig, "p1", pd.Timestamp("2026-07-18 20:00")) == "next"
        assert rt.eligible_at(elig, "p1", pd.Timestamp("2026-07-19")) == "newest"
        assert rt.eligible_at(elig, "p2", pd.Timestamp("2026-07-19")) is None

    def test_a_move_with_no_date_reads_the_newest_capture(self):
        assert rt.eligible_at(self.ELIG, "p1", pd.NaT) == "newest"
        assert rt.eligible_at(self.ELIG, "p2", pd.NaT) is None

    def test_no_eligibility_table(self):
        assert rt.eligible_at(rt.index_eligibility(None), "p1", MOVE) is None


class TestStaleCapture:
    ELIG = rt.index_eligibility(eligibility({"2026-07-18": ["p1"], "2026-09-17": ["p1"]}))

    def test_more_than_eight_days_past_the_newest_capture(self):
        assert not rt.stale_capture(self.ELIG, pd.Timestamp("2026-09-25 23:00"))   # day 8
        assert rt.stale_capture(self.ELIG, pd.Timestamp("2026-09-26 00:05"))       # day 9

    def test_never_stale_before_the_newest_capture(self):
        assert not rt.stale_capture(self.ELIG, pd.Timestamp("2026-08-20"))

    def test_no_date_or_no_table(self):
        assert not rt.stale_capture(self.ELIG, pd.NaT)
        assert not rt.stale_capture([], MOVE)


class TestDefaultContract:
    def test_eligible_is_minor_whatever_the_move(self):
        for kind in (rt.EVENT_TYPE, rt.CLAIM_EVENT, rt.DROP_EVENT, rt.TRADE_IN):
            assert rt.default_contract(True, kind, "1st") == "Minor"

    def test_ineligible_keeps_the_inherited_contract(self):
        assert rt.default_contract(False, rt.CLAIM_EVENT, "2nd") == "2nd"
        assert rt.default_contract(False, rt.TRADE_IN, "FA") == "FA"

    def test_graduated_minor_becomes_1st(self):
        assert rt.default_contract(False, rt.TRADE_IN, "Minor") == "1st"

    def test_no_history(self):
        assert rt.default_contract(False, rt.EVENT_TYPE) == "1st"
        assert rt.default_contract(False, rt.CLAIM_EVENT) == "FA"
        assert rt.default_contract(False, rt.DROP_EVENT, pd.NA) == "FA"
        assert pd.isna(rt.default_contract(False, rt.TRADE_IN, pd.NA))


class TestResolveContract:
    ELIG = eligibility({"2026-09-17": ["p1"]})

    def _drop(self, src, when=MOVE, period=MOVE_PERIOD, since=None):
        """A01's drop of p1, reading the row latest_before() finds."""
        seen = rt.latest_before(src.snaps, "A01", "p1", period, since)
        return rt.resolve_contract(src, rt.DROP_EVENT, "p1", when, seen=seen)

    def test_roster_state_wins_over_the_default(self):
        # p1 is eligible (default Minor), but Fantrax showed 1st on that team.
        src = source(state(("A01", "p1", 2, "1st")), self.ELIG)
        assert self._drop(src) == rt.Sourced("1st", observed=True)

    def test_default_when_no_row_covers_the_move(self):
        src = source(state(("A02", "p1", 2, "1st")), self.ELIG)
        assert self._drop(src) == rt.Sourced("Minor", after_newest=True)

    def test_default_when_the_row_predates_the_stint(self):
        src = source(state(("A01", "p1", 2, "1st")), self.ELIG)
        assert self._drop(src, since=MOVE_PERIOD) == rt.Sourced("Minor", after_newest=True)

    def test_a_graduate_between_two_captures_is_flagged(self):
        elig = eligibility({"2026-07-18": ["p1"], "2026-09-17": ["p2"]})
        got = rt.resolve_contract(source(elig=elig), rt.CLAIM_EVENT, "p1",
                                  pd.Timestamp("2026-08-01"))
        assert got == rt.Sourced("Minor", left_list=True)

    def test_a_default_long_after_the_newest_capture_is_flagged_stale(self):
        src = source(elig=self.ELIG)
        late = pd.Timestamp("2026-10-20")
        assert rt.resolve_contract(src, rt.CLAIM_EVENT, "p1", late) == rt.Sourced(
            "Minor", after_newest=True, stale_capture=True)
        assert rt.resolve_contract(src, rt.CLAIM_EVENT, "p2", late) == rt.Sourced(
            "FA", stale_capture=True)

    def test_an_observed_contract_is_never_stale(self):
        src = source(state(("A01", "p1", 5, "1st")), self.ELIG)
        got = self._drop(src, when=pd.Timestamp("2026-10-20"), period=6)
        assert got == rt.Sourced("1st", observed=True)

    def test_unlisted_roster_state_contract_is_written_as_observed(self):
        src = source(state(("A01", "p1", 2, "7th")), self.ELIG)
        got = self._drop(src)
        assert got == rt.Sourced("7th", observed=True)
        assert pd.isna(rt.contract_year_of(src, got.contract_id))
        frame = pd.DataFrame({"contract_id": [got.contract_id, "1st", pd.NA]})
        assert rt.unknown_contracts(frame, CONTRACTS) == ["7th"]

    def test_tally_counts_each_flag(self):
        got = rt.tally_sourcing([rt.Sourced("1st", observed=True),
                                 rt.Sourced("Minor", after_newest=True, stale_capture=True),
                                 rt.Sourced("Minor", after_newest=True),
                                 rt.Sourced("Minor", left_list=True),
                                 rt.Sourced("FA")])
        assert got == {"observed": 1, "after_newest": 2, "left_list": 1, "stale_capture": 1}
        assert rt.tally_sourcing([]) == NO_FLAGS


class TestSourcingReport:
    ELIG = rt.index_eligibility(eligibility({"2026-07-18": ["p1"], "2026-09-17": ["p1"]}))

    def test_sums_the_draft_and_transaction_tallies(self):
        lines = rt.sourcing_report(self.ELIG, [{**NO_FLAGS, "after_newest": 2},
                                               {**NO_FLAGS, "after_newest": 6, "left_list": 3}])
        assert len(lines) == 1 and lines[0].startswith("[info]")
        assert "8 move(s) made after the newest capture (2026-09-17)" in lines[0]
        assert "3 by a player off the next capture's list" in lines[0]

    def test_warns_only_when_a_default_is_stale(self):
        lines = rt.sourcing_report(self.ELIG, [NO_FLAGS, {**NO_FLAGS, "stale_capture": 4}])
        assert len(lines) == 2 and lines[1].startswith("[warn] 4 move(s)")
        assert "8 days" in lines[1] and "2026-09-17" in lines[1]

    def test_draft_tally_alone(self):
        assert len(rt.sourcing_report(self.ELIG, [NO_FLAGS])) == 1

    def test_no_eligibility_table_prints_nothing(self):
        assert rt.sourcing_report([], [NO_FLAGS]) == []


class TestStartupRows:
    MADE = pd.DataFrame({
        "scorerId": ["p1", "p2"], "teamId": ["tA", "tA"], "round": [1, 2],
        "pickNumber": [1, 14], "overall_slot": [1, 28],
        "modifiedDate": [1781138250000, 1781138250000],      # 2026-06-11 UTC
    })

    # The pool at the draft, and after Fantrax re-priced it.
    ADP = adp(("p1", 2026, "DRAFT", "2026-06-09", 4_000_000),
              ("p2", 2026, "DRAFT", "2026-06-09", 6_000_000),
              ("p1", 2026, "PRE", "2026-07-31", 2_500_000),
              ("p2", 2026, "PRE", "2026-07-31", 2_500_000))
    PRE = preseason(("A01", "p2", 7_500_000))
    WEEK_1 = ("A01", "p2", 1, "2nd", 7_200_000)

    def _priced(self, src, legs=(), pool=ADP):
        fact, sourcing, priced = rt.build_startup_rows(
            self.MADE, {"tA": "A01"}, {"p1": 1, "p2": 2}, {},
            rt.index_draft_salaries(pool, YEAR), src, rt.departures(list(legs)), MINIMUM)
        return fact.set_index("scorer_id"), sourcing, priced

    def _rows(self, src):
        return self._priced(src)[:2]

    def test_eligible_pick_is_minor_with_no_year(self):
        fact, sourcing = self._rows(source(elig=eligibility({"2026-07-18": ["p1"]})))
        assert fact.loc["p1", "contract_id"] == "Minor"
        assert pd.isna(fact.loc["p1", "contract_year"])
        assert fact.loc["p1", "contract_value"] == 4_000_000     # salary untouched
        assert fact.loc["p1", "cap_hit"] == 0
        assert sourcing == NO_FLAGS

    def test_ineligible_pick_is_1st_year_1(self):
        fact, _ = self._rows(source(elig=eligibility({"2026-07-18": ["p1"]})))
        assert (fact.loc["p2", "contract_id"], fact.loc["p2", "contract_year"]) == ("1st", 1.0)
        assert fact.loc["p2", "cap_hit"] == 3_000_000

    def test_a_pick_takes_contract_and_salary_off_its_first_roster_state(self):
        later = ("A01", "p2", 2, "1st", 9_900_000)
        fact, sourcing, priced = self._priced(source(state(later, self.WEEK_1)))
        row = fact.loc["p2"]
        assert (row["contract_id"], row["contract_year"], row["contract_value"]) == (
            "2nd", 2.0, 7_200_000)
        assert row["cap_hit"] == pytest.approx(2_880_000)
        assert sourcing["observed"] == 1
        assert priced == {rt.SALARY_AT_PICK: 1, rt.SALARY_STATE: 1}

    def test_roster_state_wins_over_an_eligible_picks_minor(self):
        src = source(state(("A01", "p1", 1, "1st")), eligibility({"2026-07-18": ["p1"]}))
        fact, sourcing = self._rows(src)
        assert fact.loc["p1", "contract_id"] == "1st" and sourcing["observed"] == 1

    def test_a_roster_state_read_before_the_pick_is_skipped(self):
        early = ("A01", "p2", 1, "2nd", 7_200_000, "2026-06-11")
        fact, sourcing, priced = self._priced(source(state(early)))
        assert fact.loc["p2", "contract_id"] == "1st" and sourcing["observed"] == 0
        assert fact.loc["p2", "contract_value"] == 6_000_000
        assert priced == {rt.SALARY_AT_PICK: 2}

    def test_no_eligibility_table_is_1st_for_all(self):
        fact, _ = self._rows(source())
        assert set(fact["contract_id"]) == {"1st"}
        assert fact["contract_year"].dtype == "float64"

    def test_salary_is_the_pool_at_the_draft_not_the_latest(self):
        fact, _, priced = self._priced(source())
        assert fact["contract_value"].to_dict() == {"p1": 4_000_000, "p2": 6_000_000}
        assert priced == {rt.SALARY_AT_PICK: 2}

    def test_preseason_salary_beats_the_pool(self):
        fact, sourcing, priced = self._priced(source(pre=self.PRE))
        assert fact.loc["p2", "contract_value"] == 7_500_000
        assert fact.loc["p2", "cap_hit"] == 3_750_000
        assert priced == {rt.SALARY_AT_PICK: 1, rt.SALARY_PRESEASON: 1}
        # the preseason capture prices the pick; it sets no contract
        assert fact.loc["p2", "contract_id"] == "1st" and sourcing["observed"] == 0

    def test_preseason_salary_beats_roster_state_which_still_sets_the_contract(self):
        fact, sourcing, priced = self._priced(source(state(self.WEEK_1), pre=self.PRE))
        assert (fact.loc["p2", "contract_id"], fact.loc["p2", "contract_value"]) == (
            "2nd", 7_500_000)
        assert sourcing["observed"] == 1
        assert priced == {rt.SALARY_AT_PICK: 1, rt.SALARY_PRESEASON: 1}

    def test_pool_when_the_copy_left_before_the_capture(self):
        # A01 traded p2 away on 07-10 and holds it again by 07-18. That row is
        # a later stint's, not the pick's.
        away = leg(rt.TRADE_IN, "p2", "A02", team_from="A01",
                   when=pd.Timestamp("2026-07-10"), period=1)
        fact, _, priced = self._priced(source(pre=self.PRE), [away])
        assert fact.loc["p2", "contract_value"] == 6_000_000
        assert priced == {rt.SALARY_AT_PICK: 2}

    def test_capture_from_before_the_copy_left_is_read(self):
        away = leg(rt.TRADE_IN, "p2", "A02", team_from="A01",
                   when=pd.Timestamp("2026-08-01"), period=1)
        fact, _, _ = self._priced(source(pre=self.PRE), [away])
        assert fact.loc["p2", "contract_value"] == 7_500_000

    def test_a_pick_that_left_in_period_1_reads_no_roster_state(self):
        # Traded away in the offseason and back on A01 by period 1: that row
        # is the later stint's.
        away = leg(rt.TRADE_IN, "p2", "A02", team_from="A01",
                   when=pd.Timestamp("2026-07-10"), period=1)
        fact, sourcing, priced = self._priced(source(state(self.WEEK_1)), [away])
        assert (fact.loc["p2", "contract_id"], fact.loc["p2", "contract_value"]) == (
            "1st", 6_000_000)
        assert sourcing["observed"] == 0 and priced == {rt.SALARY_AT_PICK: 2}

    def test_a_reclaims_capture_does_not_price_the_pick(self):
        legs = [leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-06-20"), period=1),
                leg(rt.CLAIM_EVENT, "p2", "A01", when=pd.Timestamp("2026-07-01"), period=1)]
        src = source(pre=self.PRE)
        fact, _, _ = self._priced(src, legs)
        assert fact.loc["p2", "contract_value"] == 6_000_000
        # ...it prices the claim that started the stint the capture shows
        rows = resolve(legs, src, base(("A01", 2, "1st", 6_000_000)))
        assert rows["contract_value"].tolist() == [6_000_000, 7_500_000]

    def test_a_reclaims_roster_state_is_not_the_picks(self):
        # A01 dropped p2 in period 2 and claimed it back in period 3.
        legs = [leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-12"), period=2),
                leg(rt.CLAIM_EVENT, "p2", "A01")]
        back = ("A01", "p2", 3, "2nd", 8_000_000)
        fact, sourcing, priced = self._priced(source(state(back)), legs)
        assert (fact.loc["p2", "contract_id"], fact.loc["p2", "contract_value"]) == (
            "1st", 6_000_000)
        assert sourcing["observed"] == 0 and priced == {rt.SALARY_AT_PICK: 2}
        # the pick's own stint is period 1; the claim's starts in period 3
        first = ("A01", "p2", 1, "Minor", 6_500_000)
        src = source(state(first, back))
        fact, sourcing, priced = self._priced(src, legs)
        assert (fact.loc["p2", "contract_id"], fact.loc["p2", "contract_value"]) == (
            "Minor", 6_500_000)
        assert sourcing["observed"] == 1
        rows = resolve(legs, src, base(("A01", 2, "Minor", 6_500_000)))
        assert rows["contract_id"].tolist() == ["Minor", "2nd"]
        assert rows["contract_value"].tolist() == [6_500_000, 8_000_000]

    def test_a_pick_with_no_capture_is_priced_at_the_league_minimum(self):
        fact, _, priced = self._priced(source(), pool=self.ADP[self.ADP["scorer_id"] == "p1"])
        assert fact.loc["p2", "contract_value"] == MINIMUM
        assert fact.loc["p2", "cap_hit"] == MINIMUM * 0.5
        assert priced == {rt.SALARY_AT_PICK: 1, rt.SALARY_MINIMUM: 1}


class TestStintEnd:
    LEGS = [leg(rt.DROP_EVENT, "p1", "A01", when=pd.Timestamp("2026-09-25"), period=4),
            leg(rt.TRADE_IN, "p1", "A02", team_from="A01",
                when=pd.Timestamp("2026-07-10 12:00"), period=1),
            leg(rt.CLAIM_EVENT, "p1", "A01", when=pd.Timestamp("2026-09-01"), period=1),
            leg(rt.DROP_EVENT, "p1", "A02", when=pd.NaT, period=2)]
    TRADED = rt.Left(pd.Timestamp("2026-07-10 12:00"), 1)
    DROPPED = rt.Left(pd.Timestamp("2026-09-25"), 4)

    def test_departures_are_trades_away_and_drops(self):
        assert rt.departures(self.LEGS) == {("A01", "p1"): [self.TRADED, self.DROPPED]}

    def test_a_departure_of_another_season_carries_no_period(self):
        # Its period counts that season's periods. Left as a number, a drop in
        # next season's period 1 would end this season's stint before period 1.
        later = pd.Timestamp("2027-03-10")
        legs = [leg(rt.DROP_EVENT, "p1", "A01", when=later, period=1)]
        assert rt.departures(legs, SPANS, SEASON) == {("A01", "p1"): [rt.Left(later, None)]}
        assert rt.departures(legs) == {("A01", "p1"): [rt.Left(later, 1)]}
        assert rt.departures(self.LEGS, SPANS, SEASON) == rt.departures(self.LEGS)

    def test_a_claim_keeps_its_roster_row_when_the_copy_leaves_next_season(self):
        src = source(state(("A01", "p2", 3, "1st", 8_000_000)))
        legs = [leg(rt.CLAIM_EVENT, "p2", "A01"),
                leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2027-03-10"), period=1)]
        rows, _, _, _, priced = resolve_all(legs, src)
        assert (rows[0]["contract_id"], rows[0]["contract_value"]) == ("1st", 8_000_000)
        assert priced == ["p2"]

    def test_a_departure_with_no_period_is_still_a_departure(self):
        assert rt.departures([leg(rt.DROP_EVENT, "p1", "A01", period=None)]) == {
            ("A01", "p1"): [rt.Left(MOVE, None)]}

    def test_the_first_departure_after_the_copy_joined(self):
        departs = rt.departures(self.LEGS)
        assert rt.stint_end(departs, "A01", "p1", pd.Timestamp("2026-07-01")) == self.TRADED
        assert rt.stint_end(departs, "A01", "p1", pd.Timestamp("2026-09-01")) == self.DROPPED
        assert rt.stint_end(departs, "A01", "p1", pd.Timestamp("2026-09-25")) is None

    def test_a_departure_at_the_same_instant_is_the_stint_before(self):
        departs = rt.departures(self.LEGS)
        assert rt.stint_end(departs, "A01", "p1",
                            pd.Timestamp("2026-07-10 12:00")) == self.DROPPED

    def test_a_draft_pick_ends_at_the_first_departure(self):
        departs = rt.departures(self.LEGS)
        assert rt.stint_end(departs, "A01", "p1") == self.TRADED
        assert rt.stint_end(departs, "A02", "p1") is None
        assert rt.stint_end({}, "A01", "p1") is None


class TestDraftTimeSalary:
    PICK = pd.Timestamp("2026-06-11")

    def _salary(self, *rows, when=PICK):
        return rt.draft_time_salary(rt.index_draft_salaries(adp(*rows), YEAR), "p1", when,
                                    MINIMUM)

    def test_the_index_holds_the_draft_seasons_captures_oldest_first(self):
        index = rt.index_draft_salaries(adp(("p1", 2026, "PRE", "2026-07-31", 2_500_000),
                                            ("p1", 2025, "YTD", "2026-06-06", 9_000_000),
                                            ("p1", 2026, "DRAFT", "2026-06-09", 4_000_000)), YEAR)
        assert index == {"p1": [(pd.Timestamp("2026-06-09"), 4_000_000.0),
                                (pd.Timestamp("2026-07-31"), 2_500_000.0)]}

    def test_latest_capture_on_or_before_the_pick(self):
        rows = [("p1", 2026, "DRAFT", "2026-06-09", 4_000_000),
                ("p1", 2026, "PRE", "2026-07-31", 2_500_000)]
        assert self._salary(*rows) == (4_000_000, rt.SALARY_AT_PICK)
        assert self._salary(*rows, when=pd.Timestamp("2026-06-09")) == (
            4_000_000, rt.SALARY_AT_PICK)
        assert self._salary(*rows, when=pd.Timestamp("2026-08-01")) == (
            2_500_000, rt.SALARY_AT_PICK)

    def test_else_the_earliest_capture_after_it(self):
        rows = [("p1", 2026, "01", "2026-09-27", 3_000_000),
                ("p1", 2026, "PRE", "2026-07-31", 2_500_000)]
        assert self._salary(*rows) == (2_500_000, rt.SALARY_AFTER_PICK)

    def test_both_tiers_are_floored_at_the_league_minimum(self):
        at_pick = ("p1", 2026, "DRAFT", "2026-06-09", 1_200_000)
        after = ("p1", 2026, "PRE", "2026-07-31", 900_000)
        assert self._salary(at_pick, after) == (MINIMUM, rt.SALARY_AT_PICK)
        assert self._salary(after) == (MINIMUM, rt.SALARY_AFTER_PICK)

    def test_another_seasons_capture_is_never_read(self):
        old = ("p1", 2025, "YTD", "2026-06-06", 9_000_000)
        assert self._salary(old, ("p1", 2026, "PRE", "2026-07-31", 2_500_000)) == (
            2_500_000, rt.SALARY_AFTER_PICK)
        assert self._salary(old) == (MINIMUM, rt.SALARY_MINIMUM)

    def test_rows_with_no_salary_are_skipped(self):
        rows = [("p1", 2026, "DRAFT", "2026-06-09", None),
                ("p1", 2026, "PRE", "2026-07-31", 2_500_000)]
        assert self._salary(*rows) == (2_500_000, rt.SALARY_AFTER_PICK)

    def test_a_pick_with_no_date_reads_the_seasons_first_capture(self):
        rows = [("p1", 2026, "DRAFT", "2026-06-09", 4_000_000),
                ("p1", 2026, "PRE", "2026-07-31", 2_500_000)]
        assert self._salary(*rows, when=pd.NaT) == (4_000_000, rt.SALARY_AFTER_PICK)

    def test_no_capture_in_the_draft_season_is_the_league_minimum(self):
        assert self._salary(("p2", 2026, "DRAFT", "2026-06-09", 4_000_000)) == (
            MINIMUM, rt.SALARY_MINIMUM)


class TestClaimSalary:
    ELIG = eligibility({"2026-07-18": ["p1"]})     # p1 eligible, p2 not
    CLAIMED = pd.Timestamp("2026-07-10 11:00")

    def _src(self, sid="p2", team="A01", salary=8_200_000):
        return source(elig=self.ELIG, pre=preseason((team, sid, salary)))

    def _claim(self, sid="p2", when=CLAIMED):
        return leg(rt.CLAIM_EVENT, sid, "A01", when=when, period=1)

    def test_preseason_capture_beats_the_league_minimum(self):
        rows, _, fa_fallback, sourcing, priced = resolve_all([self._claim()], self._src())
        assert (rows[0]["contract_value"], rows[0]["cap_hit"]) == (8_200_000, 8_200_000)
        assert fa_fallback == [] and priced == ["p2"]
        # the preseason capture sets the salary, never the contract
        assert rows[0]["contract_id"] == "FA" and sourcing["observed"] == 0

    def test_eligible_claim_is_minor_at_the_capture_salary(self):
        row = resolve([self._claim("p1")], self._src("p1")).iloc[0]
        assert (row["contract_id"], row["contract_value"]) == ("Minor", 8_200_000)

    def test_capture_beats_the_inherited_salary(self):
        # Dropped by A02 at 9.0M, claimed by A01; cap_hit keeps the draft row's share.
        startup = base(("A02", 2, "1st", 9_000_000))
        legs = [leg(rt.DROP_EVENT, "p2", "A02", when=pd.Timestamp("2026-07-05"), period=1),
                self._claim()]
        out = resolve(legs, self._src(salary=9_500_000), startup)
        assert out["contract_id"].tolist() == ["1st", "1st"]
        assert out["contract_value"].tolist() == [9_000_000, 9_500_000]
        assert out["cap_hit"].tolist() == [4_500_000, 4_750_000]

    def test_a_capture_at_the_inherited_salary_changes_nothing(self):
        startup = base(("A02", 2, "1st", 9_000_000))
        legs = [leg(rt.DROP_EVENT, "p2", "A02", when=pd.Timestamp("2026-07-05"), period=1),
                self._claim()]
        out = resolve(legs, self._src(salary=9_000_000), startup)
        assert out["contract_value"].tolist() == [9_000_000, 9_000_000]
        assert out["cap_hit"].tolist() == [4_500_000, 4_500_000]

    def test_a_later_trade_carries_the_new_salary(self):
        legs = [self._claim(), leg(rt.TRADE_IN, "p2", "A02", team_from="A01")]
        out = resolve(legs, self._src())
        assert out["event_type"].tolist() == ["claim", "trade_away", "trade"]
        assert out["contract_value"].tolist() == [8_200_000] * 3

    def test_claim_after_the_capture_keeps_its_default(self):
        rows, _, fa_fallback, _, priced = resolve_all(
            [self._claim(when=pd.Timestamp("2026-07-20"))], self._src())
        assert rows[0]["contract_value"] == 2_000_000
        assert fa_fallback == ["p2"] and priced == []

    def test_claim_on_the_capture_day_keeps_its_default(self):
        row = resolve([self._claim(when=pd.Timestamp("2026-07-18 09:00"))], self._src()).iloc[0]
        assert row["contract_value"] == 2_000_000

    def test_claim_dropped_before_the_capture_keeps_its_default(self):
        # Claimed, dropped, claimed back: the capture shows the second stint.
        legs = [self._claim(when=pd.Timestamp("2026-07-01")),
                leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-07-08"), period=1),
                self._claim(when=pd.Timestamp("2026-07-12"))]
        rows, _, fa_fallback, _, priced = resolve_all(legs, self._src())
        assert [r["contract_value"] for r in rows] == [2_000_000, 2_000_000, 8_200_000]
        assert fa_fallback == ["p2"] and priced == ["p2"]

    def test_another_teams_capture_does_not_price_the_claim(self):
        row = resolve([self._claim()], self._src(team="A02")).iloc[0]
        assert row["contract_value"] == 2_000_000

    def test_a_repriced_claim_leaves_the_other_conferences_copy_alone(self):
        # B01 drafted its own copy of p2 at 9.0M; A01's claim is re-priced.
        startup = base(("B01", 2, "1st", 9_000_000))
        legs = [self._claim(),
                leg(rt.DROP_EVENT, "p2", "B01", when=pd.Timestamp("2026-07-20"), period=1)]
        out = resolve(legs, self._src(), startup)
        assert out["contract_value"].tolist() == [8_200_000, 9_000_000]

    def test_a_claim_with_no_period_is_still_priced_by_the_capture(self):
        # The capture is read by day: it belongs to no Scoring Period.
        row = resolve([leg(rt.CLAIM_EVENT, "p2", "A01", when=self.CLAIMED, period=None)],
                      self._src()).iloc[0]
        assert row["contract_value"] == 8_200_000

    def test_a_drop_and_a_trade_set_no_salary(self):
        # A01 drafted p2 at 9.0M; the capture and Roster State show other
        # salaries. The drop and the trade carry the ledger's.
        startup = base(("A01", 2, "1st", 9_000_000))
        src = source(state(("A01", "p2", 2, "2nd", 7_000_000)), self.ELIG,
                     preseason(("A01", "p2", 8_200_000)))
        out = resolve([leg(rt.DROP_EVENT, "p2", "A01")], src, startup)
        assert out["contract_value"].tolist() == [9_000_000]
        assert out["contract_id"].tolist() == ["2nd"]
        out = resolve([leg(rt.TRADE_IN, "p2", "A02", team_from="A01")], src, startup)
        assert out["contract_value"].tolist() == [9_000_000, 9_000_000]


class TestClaimReadsRosterState:
    ELIG = eligibility({"2026-09-17": ["p1"]})     # p1 eligible, p2 not
    WEEK_3 = ("A01", "p2", 3, "1st", 8_200_000)    # read 10-02

    def test_contract_and_salary_off_the_first_row_in_the_stint(self):
        later = ("A01", "p2", 4, "2nd", 9_900_000)
        rows, _, fa_fallback, sourcing, priced = resolve_all(
            [leg(rt.CLAIM_EVENT, "p2", "A01")], source(state(later, self.WEEK_3), self.ELIG))
        row = rows[0]
        assert (row["contract_id"], row["contract_year"], row["contract_value"]) == (
            "1st", 1.0, 8_200_000)
        assert fa_fallback == [] and priced == ["p2"] and sourcing["observed"] == 1

    def test_roster_state_wins_over_an_eligible_claims_minor(self):
        src = source(state(("A01", "p1", 3, "1st")), self.ELIG)
        rows, _, _, sourcing, _ = resolve_all([leg(rt.CLAIM_EVENT, "p1", "A01")], src)
        assert rows[0]["contract_id"] == "1st" and sourcing["observed"] == 1

    def test_preseason_capture_prices_first_and_roster_state_sets_the_contract(self):
        src = source(state(("A01", "p2", 1, "1st", 9_900_000)), self.ELIG,
                     preseason(("A01", "p2", 8_200_000)))
        claim = leg(rt.CLAIM_EVENT, "p2", "A01", when=pd.Timestamp("2026-07-10"), period=1)
        rows, _, _, sourcing, priced = resolve_all([claim], src)
        assert (rows[0]["contract_id"], rows[0]["contract_value"]) == ("1st", 8_200_000)
        assert sourcing["observed"] == 1 and priced == ["p2"]

    def test_claim_effective_after_the_newest_period_keeps_its_default(self):
        late = leg(rt.CLAIM_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-29"), period=4)
        rows, _, fa_fallback, sourcing, priced = resolve_all(
            [late], source(state(self.WEEK_3), self.ELIG))
        assert (rows[0]["contract_id"], rows[0]["contract_value"]) == ("FA", MINIMUM)
        assert fa_fallback == ["p2"] and priced == [] and sourcing["observed"] == 0

    def test_another_teams_row_is_not_the_claims(self):
        rows, _, _, sourcing, priced = resolve_all(
            [leg(rt.CLAIM_EVENT, "p2", "A02")], source(state(self.WEEK_3), self.ELIG))
        assert (rows[0]["contract_id"], rows[0]["contract_value"]) == ("FA", MINIMUM)
        assert sourcing["observed"] == 0 and priced == []

    def test_a_claim_that_leaves_in_the_period_it_took_effect_in_reads_nothing(self):
        # Claimed, dropped and claimed back, all effective in period 3: that
        # period's roster shows the second stint.
        legs = [leg(rt.CLAIM_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-18 10:00")),
                leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-20 10:00")),
                leg(rt.CLAIM_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-20 15:00"))]
        rows, _, fa_fallback, sourcing, priced = resolve_all(
            legs, source(state(self.WEEK_3), self.ELIG))
        assert [r["contract_id"] for r in rows] == ["FA", "FA", "1st"]
        assert [r["contract_value"] for r in rows] == [MINIMUM, MINIMUM, 8_200_000]
        assert fa_fallback == ["p2"] and priced == ["p2"] and sourcing["observed"] == 1

    def test_each_stint_reads_its_own_first_row(self):
        legs = [leg(rt.CLAIM_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-12"), period=2),
                leg(rt.DROP_EVENT, "p2", "A01"),
                leg(rt.CLAIM_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-29"), period=4)]
        src = source(state(("A01", "p2", 2, "FA", 3_000_000),
                           ("A01", "p2", 4, "1st", 8_000_000)), self.ELIG)
        rows, _, _, sourcing, priced = resolve_all(legs, src)
        assert [r["contract_id"] for r in rows] == ["FA", "FA", "1st"]
        assert [r["contract_value"] for r in rows] == [3_000_000, 3_000_000, 8_000_000]
        assert sourcing["observed"] == 3 and priced == ["p2", "p2"]

    def test_a_row_read_on_the_claim_day_is_left_to_the_drop(self):
        # Period 3's roster was last read on the claim day, so it may predate
        # the claim. A later drop reads it: by then the period has locked.
        same_day = ("A01", "p2", 3, "1st", 8_200_000, "2026-09-20")
        legs = [leg(rt.CLAIM_EVENT, "p2", "A01"),
                leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-29"), period=4)]
        rows, _, fa_fallback, sourcing, priced = resolve_all(
            legs, source(state(same_day), self.ELIG))
        assert [r["contract_id"] for r in rows] == ["FA", "1st"]
        assert [r["contract_value"] for r in rows] == [MINIMUM, MINIMUM]
        assert fa_fallback == ["p2"] and priced == [] and sourcing["observed"] == 1


class TestLegsWithoutPeriod:
    def test_only_this_seasons_legs_with_no_readable_period_are_listed(self):
        placed = leg(rt.CLAIM_EVENT, "p1", "A01")
        unplaced = leg(rt.DROP_EVENT, "p1", "A01", period=None)
        unread = leg(rt.CLAIM_EVENT, "p2", "A01", period="n/a")
        next_season = leg(rt.CLAIM_EVENT, "p2", "A02", when=pd.Timestamp("2027-03-10"),
                          period=None)
        undated = leg(rt.DROP_EVENT, "p2", "A02", when=pd.NaT, period=None)
        legs = [placed, unplaced, unread, next_season, undated]
        assert rt.legs_without_period(legs, SPANS, SEASON) == [unplaced, unread]
        assert rt.legs_without_period([placed], SPANS, SEASON) == []


class TestTransactionLegs:
    ELIG = eligibility({"2026-09-17": ["p1"]})     # p1 eligible, p2 not

    def test_eligible_claim_is_minor_at_the_league_minimum(self):
        row = resolve([leg(rt.CLAIM_EVENT, "p1", "A01")], source(elig=self.ELIG)).iloc[0]
        assert row["contract_id"] == "Minor" and pd.isna(row["contract_year"])
        assert row["contract_value"] == 2_000_000

    def test_ineligible_claim_with_no_history_is_fa(self):
        row = resolve([leg(rt.CLAIM_EVENT, "p2", "A01")], source(elig=self.ELIG)).iloc[0]
        assert (row["contract_id"], row["contract_year"], row["contract_value"]) == (
            "FA", 1.0, 2_000_000)

    def test_ineligible_claim_inherits_this_seasons_contract(self):
        # Dropped by A02, re-claimed by A01 in the same Conference.
        startup = base(("A02", 2, "1st", 9_000_000))
        legs = [leg(rt.DROP_EVENT, "p2", "A02", when=pd.Timestamp("2026-09-18")),
                leg(rt.CLAIM_EVENT, "p2", "A01")]
        out = resolve(legs, source(elig=self.ELIG), startup)
        assert out["event_type"].tolist() == ["drop", "claim"]
        assert out["contract_id"].tolist() == ["1st", "1st"]
        assert out["contract_value"].tolist() == [9_000_000, 9_000_000]

    def test_other_conference_does_not_donate_a_contract(self):
        startup = base(("B01", 2, "1st", 9_000_000))
        row = resolve([leg(rt.CLAIM_EVENT, "p2", "A01")], source(elig=self.ELIG), startup).iloc[0]
        assert (row["contract_id"], row["contract_value"]) == ("FA", 2_000_000)

    def test_trade_carries_the_contract_on_both_legs(self):
        startup = base(("A01", 1, "Minor", 4_000_000))
        out = resolve([leg(rt.TRADE_IN, "p1", "A02", team_from="A01")],
                      source(elig=self.ELIG), startup)
        assert out["event_type"].tolist() == ["trade_away", "trade"]
        assert out["team_key"].tolist() == ["A01", "A02"]
        assert out["contract_id"].tolist() == ["Minor", "Minor"]
        assert out["contract_value"].tolist() == [4_000_000, 4_000_000]
        assert out["event_seq"].nunique() == 1

    def test_trade_reads_the_from_teams_roster_state(self):
        startup = base(("A01", 2, "1st", 9_000_000))
        src = source(state(("A01", "p2", 2, "2nd")), self.ELIG)
        rows, _, _, sourcing, _ = resolve_all(
            [leg(rt.TRADE_IN, "p2", "A02", team_from="A01")], src, startup)
        assert [r["contract_id"] for r in rows] == ["2nd", "2nd"]
        assert [r["contract_year"] for r in rows] == [2.0, 2.0]
        assert sourcing["observed"] == 1

    def test_trade_does_not_read_the_period_it_takes_effect_in(self):
        startup = base(("A01", 2, "1st", 9_000_000))
        src = source(state(("A01", "p2", MOVE_PERIOD, "2nd")), self.ELIG)
        rows, _, _, sourcing, _ = resolve_all(
            [leg(rt.TRADE_IN, "p2", "A02", team_from="A01")], src, startup)
        assert [r["contract_id"] for r in rows] == ["1st", "1st"]
        assert sourcing["observed"] == 0

    def test_a_leg_with_no_period_takes_the_default(self):
        startup = base(("A01", 2, "1st", 9_000_000))
        src = source(state(("A01", "p2", 2, "2nd"), ("A02", "p1", 3, "1st", 8_200_000)), self.ELIG)
        legs = [leg(rt.DROP_EVENT, "p2", "A01", period=None),
                leg(rt.CLAIM_EVENT, "p1", "A02", period=None)]
        rows, _, fa_fallback, sourcing, priced = resolve_all(legs, src, startup)
        assert [(r["event_type"], r["contract_id"]) for r in rows] == [
            ("drop", "1st"), ("claim", "Minor")]
        assert rows[1]["contract_value"] == MINIMUM
        assert sourcing["observed"] == 0 and priced == [] and fa_fallback == ["p1"]

    def test_a_reclaim_does_not_read_the_old_stints_row(self):
        # A01 held p2 on Minor, dropped it, and claims it back after p2
        # graduated. The old stint's Minor row must not be read.
        startup = base(("A01", 2, "Minor", 9_000_000))
        src = source(state(("A01", "p2", 1, "Minor")), self.ELIG)
        legs = [leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-12"), period=2),
                leg(rt.CLAIM_EVENT, "p2", "A01")]
        rows, _, _, sourcing, _ = resolve_all(legs, src, startup)
        assert [(r["event_type"], r["contract_id"]) for r in rows] == [
            ("drop", "Minor"), ("claim", "1st")]
        assert sourcing["observed"] == 1                 # the drop; the claim defaulted

    def test_drop_after_a_reclaim_ignores_the_old_stints_row(self):
        startup = base(("A01", 2, "Minor", 9_000_000))
        legs = [leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-12"), period=2),
                leg(rt.CLAIM_EVENT, "p2", "A01"),
                leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-29"), period=4)]
        old = ("A01", "p2", 1, "Minor")
        rows, _, _, sourcing, _ = resolve_all(legs, source(state(old), self.ELIG), startup)
        assert [r["contract_id"] for r in rows] == ["Minor", "1st", "1st"]
        assert sourcing["observed"] == 1
        # a row inside the new stint is read, by the claim that starts it too
        new = ("A01", "p2", 3, "2nd")
        rows, _, _, sourcing, _ = resolve_all(legs, source(state(old, new), self.ELIG), startup)
        assert [r["contract_id"] for r in rows] == ["Minor", "2nd", "2nd"]
        assert sourcing["observed"] == 3

    def test_trade_after_a_reclaim_ignores_the_old_stints_row(self):
        startup = base(("A01", 2, "Minor", 9_000_000))
        legs = [leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-12"), period=2),
                leg(rt.CLAIM_EVENT, "p2", "A01"),
                leg(rt.TRADE_IN, "p2", "A02", team_from="A01",
                    when=pd.Timestamp("2026-09-29"), period=4)]
        src = source(state(("A01", "p2", 1, "Minor")), self.ELIG)
        rows, missing, _, sourcing, _ = resolve_all(legs, src, startup)
        assert [(r["event_type"], r["contract_id"]) for r in rows] == [
            ("drop", "Minor"), ("claim", "1st"), ("trade_away", "1st"), ("trade", "1st")]
        assert missing == [] and sourcing["observed"] == 1

    def test_traded_copy_reads_only_the_new_teams_stint(self):
        # p2 goes A01 -> A02 in period 2, then A02 drops it. A02's row from
        # before the trade is outside the stint.
        startup = base(("A01", 2, "1st", 9_000_000))
        legs = [leg(rt.TRADE_IN, "p2", "A02", team_from="A01",
                    when=pd.Timestamp("2026-09-12"), period=2),
                leg(rt.DROP_EVENT, "p2", "A02")]
        src = source(state(("A02", "p2", 1, "3rd")), self.ELIG)
        rows, _, _, sourcing, _ = resolve_all(legs, src, startup)
        assert [r["contract_id"] for r in rows] == ["1st", "1st", "1st"]
        assert sourcing["observed"] == 0
        src = source(state(("A02", "p2", 1, "3rd"), ("A02", "p2", 2, "2nd")), self.ELIG)
        rows, _, _, sourcing, _ = resolve_all(legs, src, startup)
        assert [r["contract_id"] for r in rows] == ["1st", "1st", "2nd"]
        assert sourcing["observed"] == 1

    def test_trades_chained_in_one_period_carry_the_observed_contract(self):
        # A01 -> A02 in the morning reads A01's row. A02 -> A01 that afternoon
        # starts and ends inside one period, so it defaults -- to the contract
        # the copy now carries.
        startup = base(("A01", 2, "1st", 9_000_000))
        src = source(state(("A01", "p2", 2, "2nd")), self.ELIG)
        morning, afternoon = pd.Timestamp("2026-09-20 10:00"), pd.Timestamp("2026-09-20 15:00")
        legs = [leg(rt.TRADE_IN, "p2", "A02", team_from="A01", when=morning),
                leg(rt.TRADE_IN, "p2", "A01", team_from="A02", when=afternoon)]
        rows, missing, _, sourcing, _ = resolve_all(legs, src, startup)
        assert [r["contract_id"] for r in rows] == ["2nd"] * 4
        assert missing == [] and sourcing["observed"] == 1

    def test_trade_with_no_stint_on_record_reads_the_from_teams_roster_state(self):
        # The ledger never saw p2 join A01, so it has no terms to inherit: the
        # roster row gives the contract and the salary, on both sides.
        src = source(state(("A01", "p2", 2, "2nd", 9_000_000)), self.ELIG)
        rows, missing, _, sourcing, _ = resolve_all(
            [leg(rt.TRADE_IN, "p2", "A02", team_from="A01")], src)
        assert missing == [("A01", "p2")] and sourcing["observed"] == 1
        assert [r["contract_id"] for r in rows] == ["2nd", "2nd"]
        assert [r["contract_value"] for r in rows] == [9_000_000, 9_000_000]
        assert [r["cap_hit"] for r in rows] == [9_000_000, 9_000_000]

    def test_drop_with_no_stint_on_record_reads_the_roster_state(self):
        # The ledger never saw p2 join A01 (claimed before the capture window):
        # the roster row gives the contract and the salary, not the league minimum.
        src = source(state(("A01", "p2", 2, "2nd", 9_000_000)), self.ELIG)
        rows, _, fa_fallback, sourcing, priced = resolve_all(
            [leg(rt.DROP_EVENT, "p2", "A01")], src)
        assert rows[0]["contract_id"] == "2nd" and sourcing["observed"] == 1
        assert rows[0]["contract_value"] == 9_000_000
        assert fa_fallback == [] and priced == []

    def test_drop_with_ledger_terms_keeps_them_over_the_roster_rows_salary(self):
        # Only a copy with no terms on the ledger is priced off the row.
        startup = base(("A01", 2, "1st", 7_000_000))
        src = source(state(("A01", "p2", 2, "2nd", 9_000_000)), self.ELIG)
        rows, _, _, _, _ = resolve_all([leg(rt.DROP_EVENT, "p2", "A01")], src, startup)
        assert (rows[0]["contract_id"], rows[0]["contract_value"]) == ("2nd", 7_000_000)

    def test_drop_with_no_history_and_no_roster_row_keeps_the_league_minimum(self):
        rows, _, _, _, _ = resolve_all([leg(rt.DROP_EVENT, "p2", "A01")],
                                       source(elig=self.ELIG))
        assert rows[0]["contract_value"] == MINIMUM

    def test_graduated_players_inherited_minor_becomes_1st(self):
        # p2 was drafted on Minor and is no longer eligible at the trade.
        startup = base(("A01", 2, "Minor", 9_000_000))
        out = resolve([leg(rt.TRADE_IN, "p2", "A02", team_from="A01")],
                      source(elig=self.ELIG), startup)
        assert out["contract_id"].tolist() == ["1st", "1st"]
        assert out["contract_year"].tolist() == [1.0, 1.0]

    def test_resolved_contract_carries_into_the_next_move(self):
        # Eligible claim -> Minor; the same copy's later drop keeps Minor.
        legs = [leg(rt.CLAIM_EVENT, "p1", "A01", when=pd.Timestamp("2026-09-12"), period=2),
                leg(rt.DROP_EVENT, "p1", "A01", when=pd.Timestamp("2026-09-15"), period=2)]
        out = resolve(legs, source(elig=self.ELIG))
        assert out["contract_id"].tolist() == ["Minor", "Minor"]

    def test_trade_with_no_source_row_stays_unknown(self):
        rows, missing, _, _, _ = resolve_all(
            [leg(rt.TRADE_IN, "p2", "A02", team_from="A01")], source(elig=self.ELIG))
        assert missing == [("A01", "p2")]
        assert all(pd.isna(r["contract_id"]) and pd.isna(r["contract_value"]) for r in rows)

    def test_sourcing_counts_how_each_default_was_reached(self):
        elig = eligibility({"2026-07-18": ["p1", "p2"], "2026-09-17": ["p1"]})
        # p2 is off the next list; p1 is on it; p1's drop postdates the newest.
        legs = [leg(rt.CLAIM_EVENT, "p2", "A01", when=pd.Timestamp("2026-08-01"), period=1),
                leg(rt.CLAIM_EVENT, "p1", "A02", when=pd.Timestamp("2026-09-01"), period=1),
                leg(rt.DROP_EVENT, "p1", "A02", when=pd.Timestamp("2026-10-20"), period=6)]
        rows, _, _, sourcing, _ = resolve_all(legs, source(elig=elig))
        assert [r["contract_id"] for r in rows] == ["Minor", "Minor", "Minor"]
        assert sourcing == {"observed": 0, "after_newest": 1, "left_list": 1, "stale_capture": 1}


class TestRepriced:
    TERMS = dict(contract_id="1st", contract_year=1.0, contract_value=9_000_000,
                 cap_hit=4_500_000, status="active")

    def test_cap_hit_keeps_its_share_of_the_salary(self):
        out = rt.repriced(self.TERMS, 9_500_000)
        assert (out["contract_value"], out["cap_hit"]) == (9_500_000, 4_750_000)
        assert out["contract_id"] == "1st"
        assert self.TERMS["contract_value"] == 9_000_000        # the input is not mutated

    def test_the_same_salary_returns_the_terms_untouched(self):
        assert rt.repriced(self.TERMS, 9_000_000) is self.TERMS

    def test_an_unknown_share_leaves_cap_hit_unknown(self):
        for old, hit in ((pd.NA, pd.NA), (9_000_000, pd.NA), (0, 0)):
            out = rt.repriced({**self.TERMS, "contract_value": old, "cap_hit": hit}, 8_200_000)
            assert out["contract_value"] == 8_200_000 and pd.isna(out["cap_hit"])


@pytest.fixture(scope="module")
def dim():
    return pd.read_parquet(Path(__file__).resolve().parent.parent / "data" / "dim_contract.parquet")


class TestPublishedDimContract:
    """The seeded table 02d prices against (notebooks/01b)."""

    def test_minor_row_costs_nothing_to_drop(self, dim):
        minor = dim.set_index("contract_id").loc[rt.MINOR_CONTRACT_ID]
        assert minor["cap_hit_pct"] == 0 and not minor["guaranteed"]
        assert not minor["cap_exempt"]                  # exemption follows the Minors slot
        assert pd.isna(minor["contract_year"]) and pd.isna(minor["total_years"])

    def test_year_columns_stay_nullable_integers(self, dim):
        assert str(dim["contract_year"].dtype) == "Int64"
        assert str(dim["total_years"].dtype) == "Int64"

    def test_every_default_contract_is_listed(self, dim):
        ids = set(dim["contract_id"])
        assert {rt.MINOR_CONTRACT_ID, rt.DRAFT_CONTRACT_ID, rt.FA_CONTRACT_ID} <= ids
        assert len(dim) == 11 and dim["contract_id"].is_unique

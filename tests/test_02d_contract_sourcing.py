"""Contract sourcing in 02d (#113, ADR-0019 decision 6).

A Roster Move's contract is read off the latest in-season Roster State
snapshot taken inside the copy's stint on the team and before the move day; a
default applies only when no snapshot covers it. These tests build the lookups
by hand; only TestPublishedDimContract reads data/ (the seeded dim_contract).
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
SEASON = "2026-2027"
SPANS = [(pd.Timestamp("2026-03-01"), pd.Timestamp("2027-02-28"), SEASON)]
CONF = {"A01": "A", "A02": "A", "B01": "B"}
DRAFTED = pd.Timestamp("2026-06-11")
MOVE = pd.Timestamp("2026-09-20 14:00")
NO_FLAGS = {"observed": 0, "after_newest": 0, "left_list": 0, "stale_capture": 0}


def placement(*rows):
    """rows: (team_key, scorer_id, week, capture_date, contract)."""
    return pd.DataFrame(rows, columns=["team_key", "scorer_id", "week", "capture_date", "contract"])


def eligibility(by_day):
    """by_day: {capture_date: [scorer_id, ...]}."""
    return pd.DataFrame([{"capture_date": day, "scorer_id": sid}
                         for day, sids in by_day.items() for sid in sids])


def source(snaps=None, elig=None):
    return rt.contract_source(snaps, elig, CONTRACTS)


def base(*rows):
    """Startup ledger rows: (team_key, asset_id, contract_id, contract_value)."""
    cols = ["team_key", "asset_id", "event_seq", "event_date", "season_id", "contract_id",
            "contract_year", "contract_value", "cap_hit", "status"]
    return pd.DataFrame([(t, a, i, DRAFTED, SEASON, c, 1.0, v, v * 0.5, "active")
                         for i, (t, a, c, v) in enumerate(rows, 1)], columns=cols)


def leg(kind, sid, team_to, team_from=pd.NA, when=MOVE):
    return {"kind": kind, "scorer_id": sid, "team_from": team_from, "team_to": team_to,
            "event_dt": when}


def resolve_all(legs, src, startup=None):
    """resolve_legs' full return: (rows, missing_source, fa_fallback, sourcing)."""
    startup = base() if startup is None else startup
    return rt.resolve_legs(legs, startup, {"p1": 1, "p2": 2}, CONF, {},
                           SPANS, rt.fa_terms(CONTRACTS), src)


def resolve(legs, src, startup=None):
    return pd.DataFrame(resolve_all(legs, src, startup)[0])


class TestSnapshot:
    SNAPS = placement(("A01", "p1", "01", "2026-09-09", "1st"),
                      ("A01", "p1", "02", "2026-09-17", "2nd"),
                      ("A01", "p1", "04", "2026-10-01", "Minor"),
                      ("A02", "p2", "PRE", "2026-07-18", "1st"))

    def test_latest_before_the_move_day(self):
        snaps = rt.index_snapshots(self.SNAPS)
        assert rt.snapshot_contract(snaps, "A01", "p1", MOVE) == "2nd"
        assert rt.snapshot_contract(snaps, "A01", "p1", pd.Timestamp("2026-09-10")) == "1st"

    def test_a_capture_dated_the_move_day_is_not_read(self):
        # 04v stamps the day it ran, so that capture may postdate the move.
        snaps = rt.index_snapshots(self.SNAPS)
        assert rt.snapshot_contract(snaps, "A01", "p1", pd.Timestamp("2026-09-17 23:00")) == "1st"
        assert rt.snapshot_contract(snaps, "A01", "p1", pd.Timestamp("2026-09-18 00:05")) == "2nd"
        assert rt.snapshot_contract(snaps, "A01", "p1", pd.Timestamp("2026-09-09 23:00")) is None

    def test_nothing_before_the_first_snapshot(self):
        snaps = rt.index_snapshots(self.SNAPS)
        assert rt.snapshot_contract(snaps, "A01", "p1", pd.Timestamp("2026-09-08")) is None

    def test_another_team_or_no_date(self):
        snaps = rt.index_snapshots(self.SNAPS)
        assert rt.snapshot_contract(snaps, "A02", "p1", MOVE) is None
        assert rt.snapshot_contract(snaps, "A01", "p1", pd.NaT) is None

    def test_snapshots_from_before_the_stint_are_ignored(self):
        snaps = rt.index_snapshots(self.SNAPS)
        late = pd.Timestamp("2026-10-05")
        # joined 09-10: the 09-09 capture belongs to an earlier stint
        assert rt.snapshot_contract(snaps, "A01", "p1", pd.Timestamp("2026-09-12"),
                                    since=pd.Timestamp("2026-09-10")) is None
        # a capture dated the day the copy joined counts
        assert rt.snapshot_contract(snaps, "A01", "p1", MOVE,
                                    since=pd.Timestamp("2026-09-17 16:00")) == "2nd"
        assert rt.snapshot_contract(snaps, "A01", "p1", late,
                                    since=pd.Timestamp("2026-09-18")) == "Minor"
        assert rt.snapshot_contract(snaps, "A01", "p1", late,
                                    since=pd.Timestamp("2026-10-02")) is None

    def test_a_stint_that_starts_with_the_move_reads_nothing(self):
        snaps = rt.index_snapshots(self.SNAPS)
        assert rt.snapshot_contract(snaps, "A01", "p1", MOVE, since=MOVE) is None

    def test_no_stint_on_record_reads_any_earlier_snapshot(self):
        snaps = rt.index_snapshots(self.SNAPS)
        assert rt.snapshot_contract(snaps, "A01", "p1", MOVE, since=None) == "2nd"
        assert rt.snapshot_contract(snaps, "A01", "p1", MOVE, since=pd.NaT) == "2nd"

    def test_preseason_snapshot_is_not_read(self):
        snaps = rt.index_snapshots(self.SNAPS)
        assert ("A02", "p2") not in snaps
        assert rt.snapshot_contract(snaps, "A02", "p2", MOVE) is None

    def test_blank_contracts_are_not_observations(self):
        # 04v writes an empty contract cell as "".
        snaps = rt.index_snapshots(placement(("A01", "p1", "01", "2026-09-09", "1st"),
                                             ("A01", "p1", "02", "2026-09-17", ""),
                                             ("A01", "p2", "02", "2026-09-17", "  "),
                                             ("A02", "p2", "02", "2026-09-17", None)))
        assert set(snaps) == {("A01", "p1")}
        assert rt.snapshot_contract(snaps, "A01", "p1", MOVE) == "1st"

    def test_rows_with_no_capture_date_are_left_out(self):
        snaps = rt.index_snapshots(placement(("A01", "p1", "01", "2026-09-09", "1st"),
                                             ("A01", "p1", "02", None, "2nd")))
        assert rt.snapshot_contract(snaps, "A01", "p1", MOVE) == "1st"

    def test_no_placement_table(self):
        assert rt.index_snapshots(None) == {}


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

    def test_snapshot_wins_over_the_default(self):
        # p1 is eligible (default Minor), but Fantrax showed 1st on that team.
        src = source(placement(("A01", "p1", "02", "2026-09-17", "1st")), self.ELIG)
        got = rt.resolve_contract(src, rt.DROP_EVENT, "A01", "p1", MOVE)
        assert got == rt.Sourced("1st", observed=True)

    def test_default_when_no_snapshot_covers_the_move(self):
        src = source(placement(("A02", "p1", "02", "2026-09-17", "1st")), self.ELIG)
        got = rt.resolve_contract(src, rt.DROP_EVENT, "A01", "p1", MOVE)
        assert got == rt.Sourced("Minor", after_newest=True)

    def test_default_when_the_snapshot_predates_the_stint(self):
        src = source(placement(("A01", "p1", "02", "2026-09-17", "1st")), self.ELIG)
        got = rt.resolve_contract(src, rt.DROP_EVENT, "A01", "p1", MOVE,
                                  since=pd.Timestamp("2026-09-18"))
        assert got == rt.Sourced("Minor", after_newest=True)

    def test_a_graduate_between_two_captures_is_flagged(self):
        elig = eligibility({"2026-07-18": ["p1"], "2026-09-17": ["p2"]})
        got = rt.resolve_contract(source(elig=elig), rt.CLAIM_EVENT, "A01", "p1",
                                  pd.Timestamp("2026-08-01"))
        assert got == rt.Sourced("Minor", left_list=True)

    def test_preseason_snapshot_does_not_block_the_default(self):
        src = source(placement(("A01", "p1", "PRE", "2026-07-18", "1st")), self.ELIG)
        assert rt.resolve_contract(src, rt.DROP_EVENT, "A01", "p1", MOVE).contract_id == "Minor"

    def test_blank_snapshot_contract_does_not_block_the_default(self):
        src = source(placement(("A01", "p1", "02", "2026-09-17", "")), self.ELIG)
        got = rt.resolve_contract(src, rt.DROP_EVENT, "A01", "p1", MOVE)
        assert (got.contract_id, got.observed) == ("Minor", False)

    def test_a_default_long_after_the_newest_capture_is_flagged_stale(self):
        src = source(elig=self.ELIG)
        late = pd.Timestamp("2026-10-20")
        assert rt.resolve_contract(src, rt.CLAIM_EVENT, "A01", "p1", late) == rt.Sourced(
            "Minor", after_newest=True, stale_capture=True)
        assert rt.resolve_contract(src, rt.CLAIM_EVENT, "A01", "p2", late) == rt.Sourced(
            "FA", stale_capture=True)

    def test_an_observed_contract_is_never_stale(self):
        src = source(placement(("A01", "p1", "05", "2026-10-08", "1st")), self.ELIG)
        got = rt.resolve_contract(src, rt.DROP_EVENT, "A01", "p1", pd.Timestamp("2026-10-20"))
        assert got == rt.Sourced("1st", observed=True)

    def test_unlisted_snapshot_contract_is_written_as_observed(self):
        src = source(placement(("A01", "p1", "02", "2026-09-17", "7th")), self.ELIG)
        got = rt.resolve_contract(src, rt.DROP_EVENT, "A01", "p1", MOVE)
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

    def _rows(self, src):
        fact, sourcing = rt.build_startup_rows(
            self.MADE, {"tA": "A01"}, {"p1": 1, "p2": 2}, {}, {"p1": 4_000_000, "p2": 6_000_000}, src)
        return fact.set_index("scorer_id"), sourcing

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

    def test_a_pick_never_reads_a_snapshot(self):
        # The pick starts the stint, so even a snapshot of that team from
        # before the draft day cannot cover it.
        snaps = placement(("A01", "p2", "01", "2026-06-01", "2nd"))
        fact, sourcing = self._rows(source(snaps, eligibility({"2026-07-18": ["p1"]})))
        assert fact.loc["p2", "contract_id"] == "1st" and sourcing["observed"] == 0

    def test_no_eligibility_table_is_1st_for_all(self):
        fact, _ = self._rows(source())
        assert set(fact["contract_id"]) == {"1st"}
        assert fact["contract_year"].dtype == "float64"


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

    def test_trade_reads_the_from_teams_snapshot(self):
        startup = base(("A01", 2, "1st", 9_000_000))
        src = source(placement(("A01", "p2", "02", "2026-09-17", "2nd")), self.ELIG)
        rows, _, _, sourcing = resolve_all(
            [leg(rt.TRADE_IN, "p2", "A02", team_from="A01")], src, startup)
        assert [r["contract_id"] for r in rows] == ["2nd", "2nd"]
        assert [r["contract_year"] for r in rows] == [2.0, 2.0]
        assert sourcing["observed"] == 1

    def test_trade_does_not_read_a_capture_dated_the_trade_day(self):
        startup = base(("A01", 2, "1st", 9_000_000))
        src = source(placement(("A01", "p2", "03", "2026-09-20", "2nd")), self.ELIG)
        rows, _, _, sourcing = resolve_all(
            [leg(rt.TRADE_IN, "p2", "A02", team_from="A01")], src, startup)
        assert [r["contract_id"] for r in rows] == ["1st", "1st"]
        assert sourcing["observed"] == 0

    def test_claim_never_reads_a_snapshot(self):
        # A01 held p2 on Minor, dropped it, and claims it back after p2
        # graduated. The old stint's Minor snapshot must not be read.
        startup = base(("A01", 2, "Minor", 9_000_000))
        src = source(placement(("A01", "p2", "01", "2026-09-09", "Minor")), self.ELIG)
        legs = [leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-12")),
                leg(rt.CLAIM_EVENT, "p2", "A01")]
        rows, _, _, sourcing = resolve_all(legs, src, startup)
        assert [(r["event_type"], r["contract_id"]) for r in rows] == [
            ("drop", "Minor"), ("claim", "1st")]
        assert sourcing["observed"] == 1                 # the drop; the claim defaulted

    def test_drop_after_a_reclaim_ignores_the_old_stints_snapshot(self):
        startup = base(("A01", 2, "Minor", 9_000_000))
        legs = [leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-12")),
                leg(rt.CLAIM_EVENT, "p2", "A01"),
                leg(rt.DROP_EVENT, "p2", "A01", when=pd.Timestamp("2026-09-25"))]
        old = ("A01", "p2", "01", "2026-09-09", "Minor")
        rows, _, _, sourcing = resolve_all(legs, source(placement(old), self.ELIG), startup)
        assert [r["contract_id"] for r in rows] == ["Minor", "1st", "1st"]
        assert sourcing["observed"] == 1
        # a snapshot inside the new stint is read
        new = ("A01", "p2", "03", "2026-09-22", "2nd")
        rows, _, _, sourcing = resolve_all(legs, source(placement(old, new), self.ELIG), startup)
        assert [r["contract_id"] for r in rows] == ["Minor", "1st", "2nd"]
        assert sourcing["observed"] == 2

    def test_traded_copy_reads_only_the_new_teams_stint(self):
        # p2 goes A01 -> A02 on 09-12, then A02 drops it. A02's row from before
        # the trade is outside the stint.
        startup = base(("A01", 2, "1st", 9_000_000))
        legs = [leg(rt.TRADE_IN, "p2", "A02", team_from="A01", when=pd.Timestamp("2026-09-12")),
                leg(rt.DROP_EVENT, "p2", "A02")]
        src = source(placement(("A02", "p2", "01", "2026-09-09", "3rd")), self.ELIG)
        rows, _, _, sourcing = resolve_all(legs, src, startup)
        assert [r["contract_id"] for r in rows] == ["1st", "1st", "1st"]
        assert sourcing["observed"] == 0
        src = source(placement(("A02", "p2", "01", "2026-09-09", "3rd"),
                               ("A02", "p2", "02", "2026-09-17", "2nd")), self.ELIG)
        rows, _, _, sourcing = resolve_all(legs, src, startup)
        assert [r["contract_id"] for r in rows] == ["1st", "1st", "2nd"]
        assert sourcing["observed"] == 1

    def test_trades_chained_on_one_day_carry_the_observed_contract(self):
        # A01 -> A02 in the morning reads A01's snapshot. A02 -> A01 that
        # afternoon starts and ends inside one day, so it defaults -- to the
        # contract the copy now carries.
        startup = base(("A01", 2, "1st", 9_000_000))
        src = source(placement(("A01", "p2", "02", "2026-09-17", "2nd")), self.ELIG)
        legs = [leg(rt.TRADE_IN, "p2", "A02", team_from="A01", when=pd.Timestamp("2026-09-20 10:00")),
                leg(rt.TRADE_IN, "p2", "A01", team_from="A02", when=pd.Timestamp("2026-09-20 15:00"))]
        rows, missing, _, sourcing = resolve_all(legs, src, startup)
        assert [r["contract_id"] for r in rows] == ["2nd"] * 4
        assert missing == [] and sourcing["observed"] == 1

    def test_trade_with_no_stint_on_record_reads_the_from_teams_snapshot(self):
        # The ledger never saw p2 join A01, so its salary is unknown, but the
        # snapshot still shows the contract.
        src = source(placement(("A01", "p2", "02", "2026-09-17", "2nd")), self.ELIG)
        rows, missing, _, sourcing = resolve_all(
            [leg(rt.TRADE_IN, "p2", "A02", team_from="A01")], src)
        assert missing == [("A01", "p2")] and sourcing["observed"] == 1
        assert [r["contract_id"] for r in rows] == ["2nd", "2nd"]
        assert all(pd.isna(r["contract_value"]) for r in rows)

    def test_drop_with_no_stint_on_record_reads_the_snapshot(self):
        # The ledger never saw p2 join A01 (claimed before the capture window).
        src = source(placement(("A01", "p2", "02", "2026-09-17", "2nd")), self.ELIG)
        rows, _, _, sourcing = resolve_all([leg(rt.DROP_EVENT, "p2", "A01")], src)
        assert rows[0]["contract_id"] == "2nd" and sourcing["observed"] == 1

    def test_graduated_players_inherited_minor_becomes_1st(self):
        # p2 was drafted on Minor and is no longer eligible at the trade.
        startup = base(("A01", 2, "Minor", 9_000_000))
        out = resolve([leg(rt.TRADE_IN, "p2", "A02", team_from="A01")],
                      source(elig=self.ELIG), startup)
        assert out["contract_id"].tolist() == ["1st", "1st"]
        assert out["contract_year"].tolist() == [1.0, 1.0]

    def test_resolved_contract_carries_into_the_next_move(self):
        # Eligible claim -> Minor; the same copy's later drop keeps Minor.
        legs = [leg(rt.CLAIM_EVENT, "p1", "A01", when=pd.Timestamp("2026-09-12")),
                leg(rt.DROP_EVENT, "p1", "A01", when=pd.Timestamp("2026-09-15"))]
        out = resolve(legs, source(elig=self.ELIG))
        assert out["contract_id"].tolist() == ["Minor", "Minor"]

    def test_trade_with_no_source_row_stays_unknown(self):
        rows, missing, _, _ = resolve_all(
            [leg(rt.TRADE_IN, "p2", "A02", team_from="A01")], source(elig=self.ELIG))
        assert missing == [("A01", "p2")]
        assert all(pd.isna(r["contract_id"]) and pd.isna(r["contract_value"]) for r in rows)

    def test_sourcing_counts_how_each_default_was_reached(self):
        elig = eligibility({"2026-07-18": ["p1", "p2"], "2026-09-17": ["p1"]})
        legs = [leg(rt.CLAIM_EVENT, "p2", "A01", when=pd.Timestamp("2026-08-01")),   # off the next list
                leg(rt.CLAIM_EVENT, "p1", "A02", when=pd.Timestamp("2026-09-01")),   # on the next list
                leg(rt.DROP_EVENT, "p1", "A02", when=pd.Timestamp("2026-10-20"))]    # after the newest
        rows, _, _, sourcing = resolve_all(legs, source(elig=elig))
        assert [r["contract_id"] for r in rows] == ["Minor", "Minor", "Minor"]
        assert sourcing == {"observed": 0, "after_newest": 1, "left_list": 1, "stale_capture": 1}


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

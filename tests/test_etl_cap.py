"""etl_cap: the slot exemption, the per-row charge, the next-season carry,
Dead Money by season and the ledger replay (#97)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

import etl_cap as cap

CONTRACTS = pd.DataFrame({
    "contract_id": ["1st", "2nd", "3rd", "FA", "Tag", "Minor"],
    "contract_year": pd.array([1, 2, 3, pd.NA, pd.NA, pd.NA], dtype="Int64"),
    "total_years": pd.array([3, 3, 3, pd.NA, pd.NA, pd.NA], dtype="Int64"),
})


class TestStampCap:
    def test_minors_and_ir_are_exempt_other_slots_are_charged(self):
        slots = pd.Series(["Starter", "Bench", "IR", "Minors"])
        out = cap.stamp_cap(slots, pd.Series([10.0, 20.0, 30.0, 40.0]))
        assert out["cap_exempt"].tolist() == [False, False, True, True]
        assert out["cap_hit"].tolist() == [10.0, 20.0, 0.0, 0.0]

    def test_a_null_slot_is_charged(self):
        out = cap.stamp_cap(pd.Series([None, pd.NA], dtype="object"), pd.Series([5.0, 6.0]))
        assert out["cap_exempt"].tolist() == [False, False]
        assert out["cap_hit"].tolist() == [5.0, 6.0]

    def test_the_exempt_slots_are_the_rulings(self):
        assert cap.EXEMPT_SLOTS == {"Minors", "IR"}


class TestCarriesNextSeason:
    @pytest.mark.parametrize("contract, carries", [
        ("1st", True), ("2nd", True), ("3rd", False), ("FA", False),
        ("Tag", False), ("Minor", True), ("unknown", False)])
    def test_contract(self, contract, carries):
        assert cap.carries_next_season(pd.Series([contract]), CONTRACTS).tolist() == [carries]

    def test_the_published_dim_contract(self):
        import etl_helpers
        real = etl_helpers.read_table("dim_contract")
        ids = real["contract_id"]
        got = dict(zip(ids, cap.carries_next_season(ids, real)))
        carrying = {"Minor"} | {c for c, y, t in zip(ids, real["contract_year"],
                                                     real["total_years"])
                                if pd.notna(y) and pd.notna(t) and y < t}
        assert {c for c, v in got.items() if v} == carrying
        assert got["Minor"] and got["1st"]
        assert not got["Tag"] and not got["FA"] and not got["X"]


class TestDeadMoneyByTeam:
    DEAD = pd.DataFrame({
        "team_key": ["A01", "A01", "A01", "B02"],
        "season_id": ["2026-2027", "2027-2028", "2026-2027", "2027-2028"],
        "dead_money": [5.0, 4.0, 1.0, 7.0],
    })

    def test_each_season_is_charged_on_its_own(self):
        this = cap.dead_money_by_team(self.DEAD, "2026-2027")
        nxt = cap.dead_money_by_team(self.DEAD, "2027-2028")
        assert this.to_dict() == {"A01": 6.0}
        assert nxt.to_dict() == {"A01": 4.0, "B02": 7.0}

    def test_a_season_with_no_rows_charges_nothing(self):
        assert cap.dead_money_by_team(self.DEAD, "2028-2029").empty


def ledger(*moves):
    """(event_seq, team_key, scorer_id, event_type) rows."""
    df = pd.DataFrame(moves, columns=["event_seq", "team_key", "scorer_id", "event_type"])
    df["event_date"] = pd.Timestamp("2026-09-01") + pd.to_timedelta(df["event_seq"], unit="D")
    return df


class TestOpenStints:
    def test_a_drop_closes_the_stint(self):
        led = ledger((1, "A01", "p1", "startup_draft"), (2, "A01", "p1", "drop"))
        assert cap.open_stints(led).empty

    def test_a_reclaim_opens_a_new_stint_from_the_claim(self):
        led = ledger((1, "A01", "p1", "startup_draft"), (2, "A01", "p1", "drop"),
                     (3, "A01", "p1", "claim"))
        got = cap.open_stints(led)
        assert got[["team_key", "scorer_id", "event_type"]].values.tolist() == [["A01", "p1", "claim"]]
        assert got["event_date"].iloc[0] == pd.Timestamp("2026-09-04")

    def test_a_trade_moves_the_stint(self):
        led = ledger((1, "A01", "p1", "startup_draft"), (2, "A01", "p1", "trade_away"),
                     (2, "A02", "p1", "trade"))
        got = cap.open_stints(led)
        assert got[["team_key", "event_type"]].values.tolist() == [["A02", "trade"]]

    def test_order_is_event_seq_not_row_order(self):
        led = ledger((3, "A01", "p1", "claim"), (2, "A01", "p1", "drop"),
                     (1, "A01", "p1", "startup_draft"))
        assert cap.open_stints(led)["event_type"].tolist() == ["claim"]

    def test_other_event_types_do_not_count(self):
        led = ledger((1, "A01", "p1", "startup_draft"), (2, "A01", "p1", "minor_assignment"))
        assert cap.open_stints(led)["event_type"].tolist() == ["startup_draft"]


def test_membership_differences():
    roster = pd.DataFrame({"team_key": ["A01", "A01"], "scorer_id": ["p1", "p2"]})
    stints = pd.DataFrame({"team_key": ["A01", "B01"], "scorer_id": ["p1", "p1"]})
    assert cap.membership_differences(roster, stints) == ([("A01", "p2")], [("B01", "p1")])

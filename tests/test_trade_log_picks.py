"""Trade-log pick legs resolved to a pick, and the pick assets (#109).

02d gives every row of fact_trade_log an `asset_id`: a pick leg is resolved
to the pick it moved (a slot of fact_draft_pick, or a future pick found by
replaying ownership), and every pick has a `dim_roster_asset` row. A leg
that resolves to no pick goes to review and stays out of the table.
"""
import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest

rt = importlib.import_module("02d_fact_roster_transactions")

TEAMS = ["A01", "A02", "A03"]
NAMES = {"alpha": "A01", "bravo": "A02", "charlie": "A03"}

# One division, three teams, two rounds: round 1 in team order, round 2 snaked.
SLOTTED = pd.DataFrame(
    [(f"2026-2027|div|S{slot:03d}", "2026-2027", "div", rnd, pick, slot, owner, owner)
     for slot, (rnd, pick, owner) in enumerate(
         [(1, 1, "A01"), (1, 2, "A02"), (1, 3, "A03"),
          (2, 1, "A03"), (2, 2, "A02"), (2, 3, "A01")], start=1)],
    columns=["pick_ref", "draft_season", "division_id", "round", "pick_in_round",
             "overall_slot", "current_owner", "original_owner"])
FUTURE = pd.DataFrame(
    [(f"{year}|{team}|{rnd}", f"{year}-{year + 1}", rnd, team, team)
     for year in (2027, 2028) for rnd in (1, 2) for team in TEAMS],
    columns=["pick_ref", "draft_season", "round", "original_owner", "current_owner"])


def leg(txn, when, frm, to, year, rnd, pick=None, hint=None):
    return {"transaction_id": txn, "asset_kind": "pick", "team_key_from": frm, "team_key_to": to,
            "event_date": pd.Timestamp(when), "week": "1", "scorer_id": pd.NA, "gsis_id": pd.NA,
            "draft_round": rnd, "pick_in_round": pick if pick is not None else pd.NA,
            "draft_year": year, "pick_owner_hint": hint if hint is not None else pd.NA,
            "source": rt.TRADE_SOURCE}


def player(txn, when, frm, to, scorer):
    return {**leg(txn, when, frm, to, pd.NA, pd.NA), "asset_kind": "player", "scorer_id": scorer}


def resolve(rows, slotted=SLOTTED, future=FUTURE, names=NAMES):
    log = pd.DataFrame(rows)
    refs, reasons, holders = rt.resolve_pick_legs(log, slotted, future, names)
    return refs.tolist(), reasons.tolist(), holders


class TestSlottedLeg:
    def test_a_leg_with_a_pick_number_is_its_slot(self):
        refs, reasons, _ = resolve([leg("t1", "2026-06-01", "A03", "A01", 2026, 2, pick=1)])
        assert refs == ["2026-2027|div|S004"] and pd.isna(reasons[0])

    def test_a_slot_traded_on_keeps_its_ref(self):
        # the second sender is not the slot's Original Owner
        refs, _, _ = resolve([leg("t1", "2026-06-01", "A03", "A01", 2026, 2, pick=1),
                              leg("t2", "2026-06-02", "A01", "A02", 2026, 2, pick=1)])
        assert refs == ["2026-2027|div|S004"] * 2

    def test_a_pick_number_the_grid_does_not_hold_is_unresolved(self):
        refs, reasons, _ = resolve([leg("t1", "2026-06-01", "A01", "A02", 2026, 2, pick=9)])
        assert pd.isna(refs[0]) and reasons == ["no_such_slot"]

    def test_a_player_leg_gets_no_pick_ref(self):
        refs, reasons, _ = resolve([player("t1", "2026-06-01", "A01", "A02", "s1")])
        assert pd.isna(refs[0]) and pd.isna(reasons[0])


class TestFutureLeg:
    def test_the_sender_s_own_pick(self):
        refs, _, holders = resolve([leg("t1", "2026-07-01", "A01", "A02", 2027, 1)])
        assert refs == ["2027|A01|1"]
        assert holders["2027|A01|1"] == "A02" and holders["2027|A02|1"] == "A02"

    def test_a_pick_traded_on_is_still_its_original_owner_s(self):
        refs, _, holders = resolve([leg("t1", "2026-07-01", "A01", "A02", 2027, 1),
                                    leg("t2", "2026-07-02", "A02", "A03", 2027, 1, hint="Alpha")])
        assert refs == ["2027|A01|1", "2027|A01|1"]
        assert holders["2027|A01|1"] == "A03"

    def test_legs_are_replayed_in_time_order_not_row_order(self):
        refs, _, _ = resolve([leg("t2", "2026-07-02", "A02", "A03", 2027, 1, hint="alpha"),
                              leg("t1", "2026-07-01", "A01", "A02", 2027, 1)])
        assert refs == ["2027|A01|1", "2027|A01|1"]

    def test_a_sender_holding_two_needs_the_hint(self):
        first = leg("t1", "2026-07-01", "A01", "A02", 2027, 1)
        refs, reasons, _ = resolve([first, leg("t2", "2026-07-02", "A02", "A03", 2027, 1)])
        assert pd.isna(refs[1]) and reasons[1] == "sender_holds_no_single_pick"
        refs, _, _ = resolve([first, leg("t2", "2026-07-02", "A02", "A03", 2027, 1, hint=" Bravo ")])
        assert refs[1] == "2027|A02|1"

    def test_a_hint_naming_a_pick_the_sender_does_not_hold_is_unresolved(self):
        refs, reasons, holders = resolve([leg("t1", "2026-07-01", "A01", "A02", 2027, 1, hint="Charlie")])
        assert pd.isna(refs[0]) and reasons == ["sender_holds_no_single_pick"]
        assert holders["2027|A01|1"] == "A01"            # nothing moved

    def test_a_hint_that_names_no_team_is_ignored(self):
        refs, _, _ = resolve([leg("t1", "2026-07-01", "A01", "A02", 2027, 1, hint="An Old Name")])
        assert refs == ["2027|A01|1"]

    def test_a_pick_passing_through_two_teams_in_one_trade(self):
        # listed receiver-first: A02 can only send A01's pick once it has it
        refs, _, holders = resolve([leg("t1", "2026-07-01", "A02", "A03", 2027, 1, hint="Alpha"),
                                    leg("t1", "2026-07-01", "A01", "A02", 2027, 1)])
        assert refs == ["2027|A01|1", "2027|A01|1"] and holders["2027|A01|1"] == "A03"

    def test_two_picks_of_one_round_in_one_trade_are_two_picks(self):
        rows = [leg("t1", "2026-07-01", "A01", "A02", 2027, 1),
                leg("t2", "2026-07-02", "A02", "A03", 2027, 1, hint="Alpha"),
                leg("t2", "2026-07-02", "A02", "A03", 2027, 1, hint="Bravo")]
        refs, _, _ = resolve(rows)
        assert refs == ["2027|A01|1", "2027|A01|1", "2027|A02|1"]

    def test_a_year_the_future_table_does_not_hold_is_unresolved(self):
        refs, reasons, _ = resolve([leg("t1", "2026-07-01", "A01", "A02", 2029, 1)])
        assert pd.isna(refs[0]) and reasons == ["sender_holds_no_single_pick"]

    def test_no_future_table_at_all(self):
        refs, reasons, holders = resolve([leg("t1", "2026-07-01", "A01", "A02", 2027, 1)],
                                         future=FUTURE.iloc[0:0])
        assert pd.isna(refs[0]) and reasons == ["sender_holds_no_single_pick"]
        assert not any(ref.startswith("2027") for ref in holders)

    def test_a_same_round_swap_resolves_by_the_hints(self):
        # after the first leg A02 holds two round-1 picks; the hint names its own
        refs, _, holders = resolve([leg("t1", "2026-07-01", "A01", "A02", 2027, 1, hint="Alpha"),
                                    leg("t1", "2026-07-01", "A02", "A01", 2027, 1, hint="Bravo")])
        assert refs == ["2027|A01|1", "2027|A02|1"]
        assert holders["2027|A01|1"] == "A02" and holders["2027|A02|1"] == "A01"

    def test_a_leg_made_before_the_pick_was_slotted_resolves_to_its_slot(self):
        # the 2026 picks are in the slotted grid only; a leg with no pick number
        refs, _, holders = resolve([leg("t1", "2026-05-01", "A03", "A01", 2026, 2)],
                                   future=FUTURE.iloc[0:0])
        assert refs == ["2026-2027|div|S004"] and holders["2026-2027|div|S004"] == "A01"

    def test_a_pick_in_both_tables_is_replayed_once_under_its_slot(self):
        both = pd.concat([FUTURE, pd.DataFrame(
            [("2026|A03|2", "2026-2027", 2, "A03", "A03")], columns=FUTURE.columns)])
        refs, _, _ = resolve([leg("t1", "2026-05-01", "A03", "A01", 2026, 2)], future=both)
        assert refs == ["2026-2027|div|S004"]

    def test_an_unmapped_team_is_unresolved(self):
        refs, reasons, _ = resolve([leg("t1", "2026-07-01", pd.NA, "A02", 2027, 1)])
        assert pd.isna(refs[0]) and reasons == ["unmapped_team"]


class TestOwnershipGaps:
    NO_LEGS = pd.DataFrame(columns=["pick_ref", "pick_in_round", "team_key_to", "event_date"])

    def test_none_when_the_replay_matches_the_reported_owner(self):
        _, _, holders = resolve([leg("t1", "2026-07-01", "A01", "A02", 2027, 1)])
        reported = FUTURE.assign(current_owner=FUTURE["current_owner"].where(
            FUTURE["pick_ref"] != "2027|A01|1", "A02"))
        assert rt.ownership_gaps(SLOTTED, reported, holders, self.NO_LEGS) == []

    def test_a_pick_table_older_than_the_trade_is_a_gap(self):
        _, _, holders = resolve([leg("t1", "2026-07-01", "A01", "A02", 2027, 1)])
        assert rt.ownership_gaps(SLOTTED, FUTURE, holders, self.NO_LEGS) == [("2027|A01|1", "A02", "A01")]

    def test_a_slot_whose_last_receiver_is_not_its_current_owner_is_a_gap(self):
        log = pd.DataFrame({"pick_ref": ["2026-2027|div|S004"] * 2, "pick_in_round": [1, 1],
                            "team_key_to": ["A01", "A02"],
                            "event_date": pd.to_datetime(["2026-06-01", "2026-06-02"])})
        assert rt.ownership_gaps(SLOTTED, FUTURE, {}, log) == [("2026-2027|div|S004", "A02", "A03")]
        made_by = SLOTTED.assign(current_owner=SLOTTED["current_owner"].where(
            SLOTTED["pick_ref"] != "2026-2027|div|S004", "A02"))
        assert rt.ownership_gaps(made_by, FUTURE, {}, log) == []

    def test_a_slot_that_changed_owner_with_no_leg_is_a_gap(self):
        # a trade the capture missed
        moved = SLOTTED.assign(current_owner=SLOTTED["current_owner"].where(
            SLOTTED["pick_ref"] != "2026-2027|div|S002", "A03"))
        assert rt.ownership_gaps(moved, FUTURE, {}, self.NO_LEGS) == [("2026-2027|div|S002", "A02", "A03")]


class TestMintPickAssets:
    EXISTING = pd.DataFrame([dict(asset_id=1, asset_type="player", scorer_id="s1",
                                  gsis_id="00-1", player_key=pd.NA, pick_ref=pd.NA)],
                            columns=rt.ASSET_COLS)

    def test_one_pick_asset_per_ref_after_the_last_id(self):
        bridge, ref2aid = rt.mint_pick_assets(self.EXISTING, ["p1", "p2"])
        assert ref2aid == {"p1": 2, "p2": 3}
        picks = bridge[bridge["asset_type"] == "pick"]
        assert picks["pick_ref"].tolist() == ["p1", "p2"] and picks["scorer_id"].isna().all()
        assert bridge.iloc[0].to_dict()["scorer_id"] == "s1"

    def test_a_second_mint_keeps_every_id(self):
        bridge, first = rt.mint_pick_assets(self.EXISTING, ["p1", "p2"])
        again, second = rt.mint_pick_assets(bridge, ["p2", "p3", "p1"])
        assert second == {**first, "p3": 4}
        pd.testing.assert_frame_equal(again.iloc[:3], bridge)

    def test_into_an_empty_bridge(self):
        bridge, ref2aid = rt.mint_pick_assets(pd.DataFrame(columns=rt.ASSET_COLS), ["p1"])
        assert ref2aid == {"p1": 1} and list(bridge.columns) == rt.ASSET_COLS

    def test_the_player_mint_keeps_the_pick_rows(self):
        bridge, _ = rt.mint_pick_assets(self.EXISTING, ["p1"])
        out, sid2aid = rt.mint_assets(["s1", "s2"], bridge, {"s1": "00-1"}, {})
        assert sid2aid == {"s1": 1, "s2": 3}
        assert out.set_index("asset_id").loc[2, "pick_ref"] == "p1"

    def test_a_pick_that_gets_a_slot_keeps_its_asset(self):
        # minted as a future pick, then the draft order is set
        bridge, first = rt.mint_pick_assets(self.EXISTING, ["2026|A03|2", "2027|A01|1"])
        again, second = rt.mint_pick_assets(bridge, rt.all_pick_refs(SLOTTED, FUTURE.iloc[0:0]),
                                            rt.slot_history(SLOTTED))
        assert second["2026-2027|div|S004"] == first["2026|A03|2"] and "2026|A03|2" not in second
        by_id = again.set_index("asset_id")["pick_ref"]
        assert by_id[first["2026|A03|2"]] == "2026-2027|div|S004"
        assert by_id[first["2027|A01|1"]] == "2027|A01|1"           # an unslotted pick is untouched
        assert again["pick_ref"].dropna().is_unique and len(again) == 1 + 1 + 6

    def test_a_pick_in_both_tables_is_one_asset(self):
        both = pd.DataFrame([("2026|A03|2", "2026-2027", 2, "A03", "A03")], columns=FUTURE.columns)
        refs = rt.all_pick_refs(SLOTTED, both)
        assert refs == SLOTTED["pick_ref"].tolist()

    def test_all_pick_refs_is_slotted_then_future_in_a_fixed_order(self):
        refs = rt.all_pick_refs(SLOTTED.sample(frac=1, random_state=1),
                                FUTURE.sample(frac=1, random_state=1))
        assert refs[:6] == SLOTTED["pick_ref"].tolist()
        assert refs[6:9] == ["2027|A01|1", "2027|A02|1", "2027|A03|1"] and len(refs) == 18


class TestFinishTradeLog:
    ROWS = [player("t1", "2026-07-01", "A01", "A02", "s1"),
            leg("t1", "2026-07-01", "A02", "A01", 2027, 1),
            leg("t1", "2026-07-01", "A02", "A01", 2029, 1)]          # no such pick

    @pytest.fixture
    def finished(self):
        parsed = pd.DataFrame(self.ROWS)
        refs, reasons, _ = rt.resolve_pick_legs(parsed, SLOTTED, FUTURE, NAMES)
        return rt.finish_trade_log(parsed, refs, reasons, {"s1": 7}, {"2027|A02|1": 40})

    def test_every_row_of_the_table_has_an_asset(self, finished):
        log, _ = finished
        assert list(log.columns) == rt.TRADE_LOG_COLS and "pick_owner_hint" not in log.columns
        assert log["asset_id"].tolist() == [7, 40] and str(log["asset_id"].dtype) == "int64"
        assert log["pick_ref"].isna().tolist() == [True, False]
        assert not log.duplicated(["transaction_id", "asset_id"]).any()

    def test_an_unresolved_leg_goes_to_review_and_not_the_table(self, finished):
        log, review = finished
        assert len(log) == 2 and len(review) == 1
        assert list(review.columns) == rt.PICK_REVIEW_COLS
        assert review.loc[0, "reason"] == "sender_holds_no_single_pick"
        assert review.loc[0, "draft_year"] == 2029

    def test_an_asset_moving_twice_in_one_trade_goes_to_review_whole(self):
        parsed = pd.DataFrame([leg("t1", "2026-07-01", "A02", "A03", 2027, 1, hint="Alpha"),
                               leg("t1", "2026-07-01", "A01", "A02", 2027, 1),
                               leg("t1", "2026-07-01", "A03", "A01", 2027, 2)])
        refs, reasons, _ = rt.resolve_pick_legs(parsed, SLOTTED, FUTURE, NAMES)
        log, review = rt.finish_trade_log(parsed, refs, reasons, {}, {"2027|A01|1": 40, "2027|A03|2": 41})
        assert log["asset_id"].tolist() == [41]
        assert review["reason"].tolist() == ["asset_moves_twice_in_trade"] * 2

    def test_a_player_with_no_asset_goes_to_review(self):
        parsed = pd.DataFrame([player("t1", "2026-07-01", "A01", "A02", "s9")])
        refs, reasons, _ = rt.resolve_pick_legs(parsed, SLOTTED, FUTURE, NAMES)
        log, review = rt.finish_trade_log(parsed, refs, reasons, {}, {})
        assert len(log) == 0 and review["reason"].tolist() == ["no_asset"]

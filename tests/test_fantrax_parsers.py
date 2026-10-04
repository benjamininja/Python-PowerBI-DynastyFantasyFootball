"""Parser tests on generated Fantrax fixtures (#115, ADR-0008 amendment
decision 13).

Fixtures in tests/fixtures/fantrax/ are cut from real data/raw payloads by
scripts/make_fixtures.py (allowlisted keys only). When Fantrax changes shape,
regenerate them in a PR; a failure here is the shape drift showing up.

Covered today: 04a player_stats_to_frame, 04u build_future_picks, 04p
getLeagueInfo (periods + divisions), 04s schedule helpers, 04v
rosters_to_frame, 02d draft results + transaction history. Later builds add
the public rosters (#117), live scoring + standings (#118).
"""
import copy
import importlib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fantrax"

fx = importlib.import_module("04a_fantrax_weekly_scrape")
fs = importlib.import_module("04s_fantrax_inseason_capture")
fu = importlib.import_module("04u_fantrax_public_api")
lg = importlib.import_module("04p_fantrax_league_info")
mv = importlib.import_module("04v_minor_contracts")
rt = importlib.import_module("02d_fact_roster_transactions")


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def no_crosswalk(monkeypatch):
    """Parsers join dim_fantrax_crosswalk from data/; pin it for determinism."""
    monkeypatch.setattr(fx, "_load_crosswalk", lambda cfg: {"06jdx": ("00-TEST", "pk-test")})


class TestPlayerStats:
    @pytest.fixture
    def df(self, no_crosswalk):
        return fx.player_stats_to_frame(_load("playerstats_page.json"), fx.CFG, 2026, "01")

    def test_rows_and_grain(self, df):
        # 5 active offense + 4 defense rows, minus the (N/A) row and the
        # offense/defense duplicate.
        assert len(df) == 8
        assert df["scorer_id"].is_unique
        assert (df["season"] == 2026).all() and (df["week"] == "01").all()

    def test_inactive_filtered(self, df):
        assert "040id" not in set(df["scorer_id"])          # teamShortName "(N/A)"

    def test_dual_eligible_first_occurrence_wins(self, df):
        row = df.set_index("scorer_id").loc["060sm"]
        assert row["position_raw"] == "WR,DB"                 # <b> tags stripped
        assert row["fpts"] == pytest.approx(15.40)            # offense page's row

    def test_header_mapped_columns(self, df):
        row = df.set_index("scorer_id").loc["06jdx"]
        assert (row["salary"], row["fpts"], row["games_played"], row["age"]) == (
            15460000.0, pytest.approx(56.76), 1, 24)
        assert (row["gsis_id"], row["player_key"]) == ("00-TEST", "pk-test")
        assert df.set_index("scorer_id").loc["074yk", "is_rookie"]

    def test_universe_check_runs(self, df):
        # Multi-eligible players count under each position ("DL,LB" -> LB too).
        verdict = fx.check_universe(df, minimums={"QB": 4, "LB": 3})
        assert verdict == {"LB": (3, 3, True), "QB": (3, 4, False)}

    def test_rank_derived_when_not_served(self, df):
        # BY_DATE pull: no scorer.rank, so Rk is FPts order across both pages.
        assert df.set_index("scorer_id")["overall_rank"].to_dict() == {
            "06jdx": 1, "06anq": 2, "04mnz": 3, "06amz": 4,
            "05rlj": 5, "074yk": 6, "04cap": 7, "060sm": 8}

    def test_served_rank_wins(self, no_crosswalk):
        # YEAR_TO_DATE pull: Fantrax's pool-wide Rk, not a re-rank of these rows.
        df = fx.player_stats_to_frame(
            _load("playerstats_page_ranked.json"), fx.CFG, 2025, "YTD").set_index("scorer_id")
        assert df["overall_rank"].to_dict() == {
            "06jdy": 1, "04mnz": 2, "048xf": 3, "01cdj": 4,
            "060sm": 762, "04ca0": 99, "04zv3": 117, "060jq": 143}
        assert df.loc["060sm", "fpts"] == pytest.approx(78.15)    # offense page's row
        # Rk at header index 0 shifts every column; shortName mapping still holds.
        row = df.loc["06jdy"]
        assert (row["adp"], row["percent_drafted"], row["games_played"], row["age"]) == (
            pytest.approx(54.2), 100.0, 17, 23)

    def test_fpts_rank_rule(self):
        # Zero / missing FPts are unranked; ties keep input order.
        scored = [("a", 5.0), ("b", 0.0), ("c", 5.0), ("d", None), ("e", 9.0)]
        assert fx._fpts_rank(scored) == {"e": 1, "a": 2, "c": 3}


class TestFuturePicks:
    def test_build(self):
        raw = _load("public_draftpicks.json")
        ids = sorted({p["originalOwnerTeamId"] for p in raw["futureDraftPicks"]})
        teams = pd.DataFrame({"fantrax_team_id": ids, "team_key": ["T1", "T2"],
                              "division": ["Riddell", "Wilson"]})
        df = fu.build_future_picks(raw, teams)
        assert len(df) == len(raw["futureDraftPicks"]) == 18
        assert df["pick_ref"].is_unique
        assert int((df["original_owner"] != df["current_owner"]).sum()) == 1
        assert set(df["divisionId"]) == set(fu.DIVISION_ID_BY_NAME.values())
        assert not df["is_slotted"].any() and not df["is_made"].any()
        assert set(df["draft_season"]) == {"2027-2028", "2028-2029"}


class TestLeagueInfo:
    NOW = pd.Timestamp("2026-10-03T12:00:00Z")           # inside period 4

    @pytest.fixture
    def raw(self):
        return _load("league_info.json")

    @pytest.fixture
    def periods(self, raw):
        return lg.parse_scoring_periods(raw, self.NOW).set_index("period")

    @pytest.fixture
    def teams(self, raw):
        info = raw["teamInfo"]
        return pd.DataFrame({
            "fantrax_team_id": list(info),
            "conference": ["A" if t["division"].strip() == "Riddell" else "B"
                           for t in info.values()]})

    def test_every_period_of_the_season(self, periods):
        assert list(periods.index) == list(range(1, 18))
        assert (periods["season_id"] == "2026-2027").all()

    def test_bounds_and_league_days(self, periods):
        p1 = periods.loc[1]
        assert p1["start_at"] == pd.Timestamp("2026-09-10T00:20:00Z")
        assert p1["end_at"] == pd.Timestamp("2026-09-18T00:14:59Z")
        # The dates are days on the Eastern clock, not UTC days.
        assert (p1["start_date"], p1["end_date"]) == (
            pd.Timestamp("2026-09-09"), pd.Timestamp("2026-09-17"))
        # Period 8 ends after the clocks go back: 20:14:59 at -0500.
        assert periods.loc[8, "end_at"] == pd.Timestamp("2026-11-06T01:14:59Z")
        assert periods.loc[8, "end_date"] == pd.Timestamp("2026-11-05")

    def test_neighbours_share_a_day_but_not_an_instant(self, periods):
        assert periods.loc[1, "end_date"] == periods.loc[2, "start_date"]
        assert periods.loc[1, "end_at"] < periods.loc[2, "start_at"]

    def test_is_playoff_from_the_first_playoff_period(self, periods):
        assert not periods.loc[:12, "is_playoff"].any()
        assert periods.loc[13:, "is_playoff"].all()

    def test_states_at_a_fixed_instant(self, periods):
        state = periods["update_set_state"]
        assert list(state.loc[1:3]) == ["closing"] * 3 and state.loc[4] == "open"
        assert state.loc[5:].isna().all()                 # not started, or playoff
        assert periods["closed_at"].isna().all()

    def test_schema_matches_the_registry(self, raw):
        import etl_checks as ec
        declared = {c["name"]: c["dtype"]
                    for c in ec.load_registry()["dim_scoring_period"]["columns"]}
        df = lg.parse_scoring_periods(raw, self.NOW)
        assert {c: str(t) for c, t in df.dtypes.items()} == declared

    def test_divisions_strip_fantrax_padding(self, raw, teams):
        assert any(t["division"] != t["division"].strip() for t in raw["teamInfo"].values())
        df = lg.parse_divisions(raw, teams, "2026-2027")
        assert df.to_dict("records") == [
            {"season_id": "2026-2027", "conference": "A", "division_name": "Riddell"},
            {"season_id": "2026-2027", "conference": "B", "division_name": "Wilson"}]

    def test_division_in_two_conferences_raises(self, raw, teams):
        teams.loc[0, "conference"] = "B" if teams.loc[0, "conference"] == "A" else "A"
        with pytest.raises(ValueError, match="not one-to-one"):
            lg.parse_divisions(raw, teams, "2026-2027")


class TestSchedule:
    def test_periods(self):
        assert fs.schedule_periods(_load("schedule.json")) == [
            (1, date(2026, 9, 9)), (2, date(2026, 9, 17))]

    def test_team_ids(self):
        ids = fs.schedule_team_ids(_load("schedule.json"))
        assert len(ids) == 5 and ids == sorted(ids)

    def test_page_error(self):
        assert fs.page_error(_load("schedule.json")) is None
        assert fs.page_error({"pageError": {"code": "X"}}) == {"code": "X"}
        assert fs.page_error({"responses": [{"pageError": {"code": "Y"}}]}) == {"code": "Y"}


class TestRosterInfo:
    @pytest.fixture
    def df(self, no_crosswalk):
        raw = _load("roster_info.json")
        teams = pd.DataFrame({"fantrax_team_id": sorted(raw), "team_key": ["T1", "T2"]})
        return mv.rosters_to_frame(raw, teams, 2026, "01")

    def test_rows(self, df):
        assert len(df) == 25                                  # empty slots dropped
        assert not df.duplicated(["team_id", "scorer_id"]).any()
        assert df["team_key"].notna().all()

    def test_sections_from_status_totals(self, df):
        assert set(df["roster_section"]) == {"Active", "Reserve", "Inj Res", "Minors"}
        assert (df.loc[df["status_id"] == "9", "roster_section"] == "Minors").all()

    def test_minors_eligible_and_cells(self, df):
        assert df.loc[df["roster_section"] == "Minors", "minors_eligible"].all()
        row = df.set_index("scorer_id").loc["060tq"]
        assert (row["salary"], row["contract"], row["position_raw"]) == (17118000.0, "1st", "QB")


def _team_lut(team_ids):
    return {t: f"T{i:02d}" for i, t in enumerate(sorted(set(team_ids)), 1)}


class TestDraftResults:
    @pytest.fixture
    def raw(self):
        return _load("draft_results.json")

    @staticmethod
    def _slots(raw):
        return raw["responses"][0]["data"]["draftPicksOrdered"]

    def _grid(self, raw):
        lut = _team_lut(p["teamId"] for p in self._slots(raw))
        return rt.build_draft_picks(rt.parse_draft_results([raw]), lut, "2026-2027")

    def test_slots(self, raw):
        picks = rt.parse_draft_results([raw])
        assert len(picks) == 28                               # rounds 1-2, 14 teams
        assert sorted(picks["overall_slot"]) == list(range(1, 29))
        slot = picks[(picks["round"] == 2) & (picks["pickNumber"] == 3)]
        assert slot["overall_slot"].tolist() == [17]

    def test_dedupe_keeps_latest_capture(self, raw):
        later = copy.deepcopy(raw)
        self._slots(later)[0]["teamId"] = "recaptured"
        picks = rt.parse_draft_results([raw, later])          # oldest first
        assert len(picks) == 28
        first = picks[(picks["round"] == 1) & (picks["pickNumber"] == 1)]
        assert first["teamId"].tolist() == ["recaptured"]

    def test_grid(self, raw):
        grid = self._grid(raw)
        assert grid["pick_ref"].is_unique and grid["is_made"].all()
        assert grid["pick_ref"].iloc[0] == "2026-2027|svxeyvvgmmvk3jnh|S001"
        assert grid["current_owner"].notna().all()

    def test_traded_slot_keeps_its_original_owner(self, raw):
        grid = self._grid(raw)
        r1 = grid[grid["round"] == 1].set_index("pick_in_round")["current_owner"]
        r2 = grid[grid["round"] == 2]
        assert (grid.loc[grid["round"] == 1, "original_owner"] == r1.to_numpy()).all()
        # Snake: round 2's slot k first belonged to round 1's slot 15 - k.
        assert (r2["original_owner"].to_numpy()
                == r1.loc[15 - r2["pick_in_round"]].to_numpy()).all()
        traded = grid[grid["current_owner"] != grid["original_owner"]]
        assert sorted(zip(traded["round"], traded["pick_in_round"])) == [(2, 3), (2, 10)]

    def test_slot_not_yet_picked(self, raw):
        del self._slots(raw)[-1]["scorerId"]
        grid = self._grid(raw)
        assert int((~grid["is_made"]).sum()) == 1


class TestTxnHistory:
    @pytest.fixture
    def rows(self):
        return rt.rows_from_pages(_load("txn_history.json"))

    @staticmethod
    def _lut(rows):
        return _team_lut(c["teamId"] for r in rows for c in r["cells"] if "teamId" in c)

    @pytest.fixture
    def parsed(self, rows):
        return rt.parse_txn_rows(rows, self._lut(rows), {"06an4": "00-TEST"})

    def test_counts(self, parsed):
        log, legs, stats = parsed
        assert stats == {"trade_rows": 4, "claim_drop_rows": 4, "no_player": 0, "no_team": 0}
        assert len(log) == 4 and log["transaction_id"].nunique() == 1
        assert [l["kind"] for l in legs] == ["trade", "trade", "claim", "drop", "claim", "drop"]

    def test_trade_date_carried_across_the_set(self, parsed):
        # Only the first row of a trade carries the date cell.
        log = parsed[0]
        assert (log["event_date"] == pd.Timestamp("2026-07-13 16:24")).all()

    def test_pick_legs(self, parsed):
        picks = parsed[0][parsed[0]["asset_kind"] == "pick"]
        assert picks["draft_round"].tolist() == [1, 1]
        assert picks["draft_year"].tolist() == [2027, 2028]
        assert picks["pick_in_round"].isna().all()            # future pick: no slot yet
        assert picks["pick_owner_hint"].tolist() == ["Team (X)", "Team (X)"]
        assert picks["scorer_id"].isna().all() and picks["gsis_id"].isna().all()

    def test_player_legs(self, parsed):
        log, legs, _ = parsed
        players = log[log["asset_kind"] == "player"]
        assert players["scorer_id"].tolist() == ["06an4", "06jeb"]
        assert players["gsis_id"].iloc[0] == "00-TEST" and pd.isna(players["gsis_id"].iloc[1])
        a, b = legs[0], legs[1]                               # the two legs go opposite ways
        assert (a["team_from"], a["team_to"]) == (b["team_to"], b["team_from"])

    def test_drop_inherits_its_claims_team_and_date(self, parsed):
        claim, drop = parsed[1][2], parsed[1][3]
        assert (claim["kind"], drop["kind"]) == ("claim", "drop")
        assert drop["team_to"] == claim["team_to"]
        assert drop["event_dt"] == claim["event_dt"] == pd.Timestamp("2026-07-24 16:24")

    def test_unmapped_team_is_skipped(self, rows):
        lut = self._lut(rows)
        lut.pop("66ao8djmmn0kdqp0")                           # the lone drop's team
        _, legs, stats = rt.parse_txn_rows(rows, lut, {})
        assert stats["no_team"] == 1 and len(legs) == 5

    def test_legs_resolve_in_time_order(self, parsed):
        # Same timestamp: the drop frees the spot its paired claim fills.
        order = [(l["kind"], l["scorer_id"]) for l in rt.sort_legs(parsed[1])]
        assert order == [("drop", "06anf"), ("trade", "06an4"), ("trade", "06jeb"),
                         ("drop", "05jel"), ("claim", "05rll"), ("claim", "07521")]

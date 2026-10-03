"""Parser tests on generated Fantrax fixtures (#115, ADR-0008 amendment
decision 13).

Fixtures in tests/fixtures/fantrax/ are cut from real data/raw payloads by
scripts/make_fixtures.py (allowlisted keys only). When Fantrax changes shape,
regenerate them in a PR; a failure here is the shape drift showing up.

Covered today: 04a player_stats_to_frame, 04u build_future_picks, 04s
schedule helpers, 04v rosters_to_frame. Later builds add 02d (#113),
getLeagueInfo (#117), live scoring + standings (#118).
"""
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
mv = importlib.import_module("04v_minor_contracts")


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

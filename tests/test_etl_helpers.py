"""Unit tests for etl_helpers.py's pure, I/O-free functions.

Per ADR-0008 / the "modular extraction rule" in CLAUDE.md: logic used by
multiple notebooks lives in etl_helpers.py, which makes it unit-testable in
isolation. This covers the first-pass pure-function candidates only —
add_players_from_source/ingest_ranking_source/resolve_dynasty_crosswalk/
_make_session are I/O-heavy integration-test candidates, out of scope here.
fantrax_public_get is covered with a canned session (no network), because
its job is to turn Fantrax's 200-with-an-error replies into failures.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

import etl_helpers as etl
from etl_helpers import (
    clean_name_for_match,
    clean_player_name,
    fold_ranks_long,
    generate_player_key,
    parse_height_to_inches,
)


class TestCleanPlayerName:
    def test_strips_periods_and_lowercases(self):
        assert clean_player_name("A.J. Brown") == "aj brown"

    def test_collapses_whitespace(self):
        assert clean_player_name("  Ja'Marr   Chase ") == "ja'marr chase"

    def test_normalizes_curly_apostrophes(self):
        assert clean_player_name("Amon’Ra St. Brown") == "amon'ra st brown"

    def test_nan_returns_empty_string(self):
        assert clean_player_name(pd.NA) == ""
        assert clean_player_name(float("nan")) == ""


class TestCleanNameForMatch:
    def test_strips_generational_suffix(self):
        assert clean_name_for_match("Michael Pittman Jr.") == "michael pittman"
        assert clean_name_for_match("Odell Beckham III") == "odell beckham"

    def test_strips_apostrophes(self):
        assert clean_name_for_match("Ja'Marr Chase") == "jamarr chase"

    def test_non_string_returns_empty(self):
        assert clean_name_for_match(None) == ""
        assert clean_name_for_match(float("nan")) == ""


class TestGeneratePlayerKey:
    def test_deterministic(self):
        k1 = generate_player_key("Bijan Robinson", "RB", "Texas")
        k2 = generate_player_key("Bijan Robinson", "RB", "Texas")
        assert k1 == k2
        assert len(k1) == 12

    def test_differs_on_disambiguating_field(self):
        k_rb = generate_player_key("John Smith", "RB", "Texas")
        k_wr = generate_player_key("John Smith", "WR", "Texas")
        assert k_rb != k_wr


class TestParseHeightToInches:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("6'2\"", 74.0),
            ("6'2", 74.0),
            ("6-2", 74.0),
            ("602", 74.0),
            ("74", 74.0),
            (74, 74.0),
            (6, 72.0),
        ],
    )
    def test_formats(self, raw, expected):
        assert parse_height_to_inches(raw) == expected

    def test_nan_returns_none(self):
        assert parse_height_to_inches(pd.NA) is None

    def test_unparseable_returns_none(self):
        assert parse_height_to_inches("not-a-height") is None


class TestFoldRanksLong:
    def test_melts_and_prefixes_metric_key(self):
        df = pd.DataFrame(
            {
                "source_name": ["KTC", "DynastySharks"],
                "source_player_id": ["1", "2"],
                "format": ["SF", "SF"],
                "source_uid": ["KTC|1", "DynastySharks|2"],
                "overall_rank": [1.0, None],
                "positional_rank": [1.0, 5.0],
            }
        )
        long = fold_ranks_long(df)
        keys = set(long["metric_key"])
        assert "ktc_overall_rank" in keys
        assert "ds_positional_rank" in keys
        # The null overall_rank for DynastySharks was dropped, not folded as NaN.
        assert not long[
            (long["metric_key"] == "ds_overall_rank")
        ].shape[0]


class _FakeResponse:
    def __init__(self, status_code=200, body=None, text=None):
        self.status_code, self._body, self._text = status_code, body, text

    def json(self):
        if self._text is not None:
            raise ValueError("not JSON")
        return self._body


class TestFantraxPublicGet:
    """No network: the session is swapped for one that returns a canned reply."""

    @pytest.fixture
    def reply(self, monkeypatch):
        calls = []
        sent_headers = []
        self.sent_headers = sent_headers

        def install(response):
            class Session:
                def get(self, url, params=None, timeout=None, headers=None):
                    calls.append((url, params, timeout))
                    sent_headers.append(headers)
                    if isinstance(response, Exception):
                        raise response
                    return response
            monkeypatch.setattr(etl, "_make_session", lambda: Session())
            return calls
        return install

    def test_returns_the_body_and_sends_the_league_and_params(self, reply):
        calls = reply(_FakeResponse(body={"period": 3, "rosters": {}}))
        body = etl.fantrax_public_get("getTeamRosters", "LG", expect=("rosters",), period=3)
        assert body == {"period": 3, "rosters": {}}
        url, params, timeout = calls[0]
        assert url.endswith("/fxea/general/getTeamRosters")
        assert params == {"leagueId": "LG", "period": 3} and timeout == 30

    def test_sends_the_program_user_agent(self, reply):
        reply(_FakeResponse(body={"rosters": {}}))
        etl.fantrax_public_get("getTeamRosters", "LG")
        assert self.sent_headers == [{"User-Agent": etl.FANTRAX_PUBLIC_UA}]
        assert etl.FANTRAX_PUBLIC_UA.startswith("MouseratDynastyETL/1.0 (+https://github.com/")

    def test_default_headers_user_agent_is_the_program_constant(self):
        assert etl.DEFAULT_HEADERS["User-Agent"] == etl.ETL_USER_AGENT
        assert etl.FANTRAX_PUBLIC_UA == etl.ETL_USER_AGENT

    def test_non_200_raises(self, reply):
        reply(_FakeResponse(status_code=503, body={}))
        with pytest.raises(RuntimeError, match="HTTP 503"):
            etl.fantrax_public_get("getLeagueInfo", "LG")

    def test_error_body_on_a_200_raises(self, reply):
        reply(_FakeResponse(body={"error": "League not found"}))
        with pytest.raises(RuntimeError, match="error body"):
            etl.fantrax_public_get("getLeagueInfo", "LG")

    def test_missing_expected_key_raises(self, reply):
        reply(_FakeResponse(body={"scoringPeriods": []}))
        with pytest.raises(RuntimeError, match="teamInfo"):
            etl.fantrax_public_get("getLeagueInfo", "LG", expect=("scoringPeriods", "teamInfo"))

    def test_non_json_body_raises(self, reply):
        reply(_FakeResponse(text="<html>"))
        with pytest.raises(RuntimeError, match="not JSON"):
            etl.fantrax_public_get("getLeagueInfo", "LG")

    def test_non_object_body_raises(self, reply):
        reply(_FakeResponse(body=[]))
        with pytest.raises(RuntimeError, match="error body"):
            etl.fantrax_public_get("getLeagueInfo", "LG")

    def test_request_failure_raises(self, reply):
        import requests
        reply(requests.ConnectionError("down"))
        with pytest.raises(RuntimeError, match="request failed"):
            etl.fantrax_public_get("getLeagueInfo", "LG")


class TestPfrToGsisMap:
    @pytest.mark.parametrize("live_last", [True, False])
    def test_a_live_row_wins_whichever_comes_last(self, live_last):
        rows = [("PfrAnn", "g_live", "ACT"), ("PfrAnn", "g_drop", etl.DROPPED_STATUS)]
        rows = rows if live_last else rows[::-1]
        dim = pd.DataFrame(rows, columns=["pfr_id", "gsis_id", "status"])
        assert etl.pfr_to_gsis_map(dim) == {"PfrAnn": "g_live"}

    def test_a_dropped_only_pfr_id_keeps_its_id_and_nulls_are_skipped(self):
        dim = pd.DataFrame({
            "pfr_id": ["PfrBob", None, "PfrCy"],
            "gsis_id": ["g_bob", "g_none", None],
            "status": [etl.DROPPED_STATUS, "ACT", "ACT"],
        })
        assert etl.pfr_to_gsis_map(dim) == {"PfrBob": "g_bob"}


class TestIngestRankingSourceGsis:
    """No disk: the three table calls are swapped for in-memory frames."""

    def test_gsis_pairs_with_its_own_pfr_row_past_a_null_pfr_id(self, monkeypatch):
        tables = {
            "dim_rookie_prospect": pd.DataFrame({
                "player_name_clean": ["ann one", "bob two"],
                "player_key": ["k_ann", "k_bob"],
                "pfr_id": ["PfrAnn", "PfrBob"],
            }),
            "dim_nfl_players": pd.DataFrame({
                "pfr_id": [None, "PfrAnn", "PfrBob"],
                "gsis_id": ["00-0000000", "00-0000001", "00-0000002"],
                "status": ["ACT", "ACT", "ACT"],
            }),
            "fact_rookie_rankings": pd.DataFrame(),
        }
        written = {}
        monkeypatch.setattr(etl, "read_table", lambda name, columns=None: tables[name].copy())
        monkeypatch.setattr(etl, "table_exists", lambda name: False)
        monkeypatch.setattr(etl, "write_table", lambda name, df, **kw: written.update({name: df}))

        rankings = pd.DataFrame({"player_name": ["Ann One", "Bob Two"], "global_rank": [1, 2]})
        out = etl.ingest_ranking_source(rankings, "src", "site", "pre_combine", draft_year=2026,
                                        capture_date="2026-01-01")

        assert dict(zip(out["player_key"], out["gsis_id"])) == {
            "k_ann": "00-0000001", "k_bob": "00-0000002"}
        assert "fact_rookie_rankings" in written

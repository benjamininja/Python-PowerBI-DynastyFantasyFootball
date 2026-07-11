"""Unit tests for etl_helpers.py's pure, I/O-free functions.

Per ADR-0008 / the "modular extraction rule" in CLAUDE.md: logic used by
multiple notebooks lives in etl_helpers.py, which makes it unit-testable in
isolation. This covers the first-pass pure-function candidates only —
add_players_from_source/ingest_ranking_source/resolve_dynasty_crosswalk/
_make_session are I/O-heavy integration-test candidates, out of scope here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

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

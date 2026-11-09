"""rank_date is an ISO date or null, on the way in and on the published table (#306)."""
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import etl_helpers as etl

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TestParseRankDate:
    @pytest.mark.parametrize("raw, want", [
        ("April 19, 2026", "2026-04-19"),
        ("Apr 19, 2026", "2026-04-19"),
        ("2026-04-19", "2026-04-19"),
        ("4/19/2026", "2026-04-19"),
        ("Nov. 3, 2026", "2026-11-03"),
        ("Nov. 3, 2026.", "2026-11-03"),
        ("Sept. 5, 2026", "2026-09-05"),
        ("Sep. 5, 2026", "2026-09-05"),
        ("Dec. 12,2026", "2026-12-12"),
    ])
    def test_a_dated_form_becomes_iso(self, raw, want):
        assert etl._parse_rank_date(raw) == want

    @pytest.mark.parametrize("raw", [None, "", "  ", float("nan"), pd.NA])
    def test_nothing_becomes_none(self, raw):
        assert etl._parse_rank_date(raw) is None

    def test_month_day_takes_the_year_of_the_capture(self):
        assert etl._parse_rank_date("5/16", "2026-05-16") == "2026-05-16"
        assert etl._parse_rank_date("5/26", "2026-05-30") == "2026-05-26"

    def test_month_day_after_the_capture_takes_the_year_before(self):
        assert etl._parse_rank_date("12/30", "2026-01-05") == "2025-12-30"

    def test_leap_day_in_a_non_leap_capture_year_takes_the_year_before(self):
        assert etl._parse_rank_date("2/29", "2025-03-01") == "2024-02-29"

    def test_month_day_without_a_capture_stays_raw(self):
        assert etl._parse_rank_date("5/16") == "5/16"

    def test_an_impossible_month_day_stays_raw(self):
        assert etl._parse_rank_date("13/40", "2026-05-30") == "13/40"


class TestIngestRefusesANonIsoDate:
    @pytest.mark.parametrize("raw", ["5/16 or so", "May sometime", "13/40"])
    def test_it_raises_before_it_reads_a_table(self, raw):
        with pytest.raises(ValueError, match="not YYYY-MM-DD"):
            etl.ingest_ranking_source(pd.DataFrame(), "X", "X", "post_draft",
                                      capture_date="2026-05-30", rank_date=raw)


def test_the_published_table_holds_only_iso_rank_dates():
    values = pd.read_parquet(REPO / "data" / "fact_rookie_rankings.parquet")["rank_date"].dropna().unique()
    bad = sorted(v for v in values if not ISO_DATE.match(str(v)))
    assert bad == [], f"non-ISO rank_date: {bad}"

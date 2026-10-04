"""Unit tests for 04v_minor_contracts.py.

Per ADR-0008: eligibility_to_frame and _header_index are I/O-free (the
Playwright pull is a separate function), so they get unit tests on minimal
payloads. load_eligibility runs against a tmp dir, and run() against a
stand-in browser with the pull patched, so neither needs Playwright or a login.

The former TestBuildWorklist class is gone: ADR-0011 retired 04v's
eligibility-vs-contract diff and its write-side apply path, and ADR-0019 kept
them retired (Fantrax sets the `Minor` contract itself). 04v captures minors
eligibility only; Roster Slots, contracts and salaries are 04r's
(tests/test_04r_roster_state.py).
"""
import importlib
import sys
import types
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd

mv = importlib.import_module("04v_minor_contracts")


def _page(*rows):
    """One getPlayerStats page of a minors-eligibility filter pull: header
    with Sal/Con/GP, one statsTable row per (scorer_id, name, positions)."""
    return {"responses": [{"data": {
        "tableHeader": {"cells": [{"shortName": "Sal"}, {"shortName": "Con"},
                                  {"shortName": "GP"}]},
        "statsTable": [{"scorer": {"scorerId": sid, "name": name,
                                   "posShortNames": pos, "teamShortName": "DEN"},
                        "cells": [{"content": "2,000,000"}, {"content": "Minor"},
                                  {"content": "3"}]}
                       for sid, name, pos in rows],
    }}]}


PULLS = {"MINOR_FANTASY_AVAILABLE": [_page(("x1", "Guy A", "RB"))],
         "MINOR_FANTASY_TAKEN": [_page(("x2", "Guy B", "<b>WR</b>,DB"))]}


class TestHeaderIndex:
    def test_grid_tableheader(self):
        d = {"tableHeader": {"cells": [{"shortName": "Sal"}, {"shortName": "Con"}]}}
        assert mv._header_index(d) == {"Sal": 0, "Con": 1}

    def test_missing_header_empty(self):
        assert mv._header_index({}) == {}


class TestEligibilityToFrame:
    def test_one_row_per_scorer_with_its_filter_status(self):
        df = mv.eligibility_to_frame(PULLS).set_index("scorer_id")
        assert df["fa_status"].to_dict() == {"x1": "available", "x2": "taken"}
        row = df.loc["x2"]
        assert (row["position_raw"], row["salary"], row["contract"], row["games_played"]) == (
            "WR,DB", 2000000.0, "Minor", 3.0)                 # <b> tags stripped

    def test_repeat_within_a_pull_keeps_one_row(self):
        # A dual-eligible player comes back on more than one page of a pull.
        pulls = {"MINOR_FANTASY_TAKEN": [_page(("x1", "Guy A", "DL,LB")),
                                         _page(("x1", "Guy A", "DL,LB"))]}
        assert len(mv.eligibility_to_frame(pulls)) == 1


class TestLoadEligibility:
    @staticmethod
    def _landed(tmp_path):
        return pd.read_parquet(tmp_path / "fact_minor_eligibility.parquet")

    def test_stamps_the_capture_date_it_is_given(self, tmp_path):
        cfg = SimpleNamespace(data_dir=str(tmp_path))
        mv.load_eligibility(mv.eligibility_to_frame(PULLS), cfg, 2026, "04", "2026-10-01")
        df = self._landed(tmp_path)
        assert len(df) == 2
        assert set(df["capture_date"]) == {"2026-10-01"}      # not the day the test runs
        assert (df["season"] == 2026).all() and (df["week"] == "04").all()

    def test_replaces_its_own_season_week_only(self, tmp_path):
        cfg, elig = SimpleNamespace(data_dir=str(tmp_path)), mv.eligibility_to_frame(PULLS)
        mv.load_eligibility(elig, cfg, 2026, "03", "2026-09-24")
        mv.load_eligibility(elig, cfg, 2026, "04", "2026-10-01")
        mv.load_eligibility(elig.iloc[:1], cfg, 2026, "04", "2026-10-02")   # week 04 re-run
        df = self._landed(tmp_path)
        assert df.groupby("week").size().to_dict() == {"03": 2, "04": 1}
        assert df.groupby("week")["capture_date"].agg(set).to_dict() == {
            "03": {"2026-09-24"}, "04": {"2026-10-02"}}


class _FakeBrowser:
    """Stands in for playwright's sync_playwright(). run() only opens a
    persistent context and a page and hands both to fetch_eligibility, which
    the test patches, so one object plays every role."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    chromium = property(lambda self: self)

    def launch_persistent_context(self, *args, **kwargs):
        return self

    def new_page(self):
        return self

    def set_default_timeout(self, ms):
        pass

    def close(self):
        pass


class TestRun:
    def test_one_capture_date_per_run(self, tmp_path, monkeypatch):
        class Clock:
            reads = 0

            @classmethod
            def today(cls):
                cls.reads += 1
                return date(2026, 10, 3 + cls.reads)          # a later day on every read

        cfg = SimpleNamespace(snapshot_season=2026, snapshot_week=4,
                              data_dir=str(tmp_path), raw_dir=str(tmp_path / "raw"),
                              user_data_dir=str(tmp_path / "profile"),
                              headless=True, nav_timeout_ms=1000)
        playwright = types.ModuleType("playwright.sync_api")
        playwright.sync_playwright = _FakeBrowser
        monkeypatch.setitem(sys.modules, "playwright.sync_api", playwright)
        monkeypatch.setattr(mv, "CFG", cfg)
        monkeypatch.setattr(mv, "date", Clock)
        monkeypatch.setattr(mv, "fetch_eligibility", lambda scraper, ctx, page: PULLS)

        elig = mv.run()

        assert Clock.reads == 1
        landed = pd.read_parquet(tmp_path / "fact_minor_eligibility.parquet")
        assert len(landed) == len(elig) == 2
        assert set(landed["capture_date"]) == {"2026-10-04"}
        assert (landed["week"] == "04").all()
        assert (tmp_path / "raw" / "fantrax_minor_eligibility_2026_wk04.json").exists()

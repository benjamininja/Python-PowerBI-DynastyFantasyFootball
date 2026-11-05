"""04v pull sidecar (#370): the request payload, server totals and rows parsed
of each filter pull, saved beside the raw capture. Mocked pull: no Fantrax
login, no network."""
import importlib
import json
import sys
import types
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd

mv = importlib.import_module("04v_minor_contracts")

COOKIE = "COOKIE-VALUE-SENTINEL-123"
AUTH = "AUTH-VALUE-SENTINEL-456"


def _page(rows, total_results, total_pages):
    return {"responses": [{"data": {
        "paginatedResultSet": {"totalNumResults": total_results,
                               "totalNumPages": total_pages},
        "tableHeader": {"cells": [{"shortName": "Sal"}, {"shortName": "Con"},
                                  {"shortName": "GP"}]},
        "statsTable": [{"scorer": {"scorerId": sid, "name": sid,
                                   "posShortNames": "RB", "teamShortName": "DEN"},
                        "cells": [{"content": "1"}, {"content": "Minor"},
                                  {"content": "3"}]} for sid in rows],
    }}]}


class FakeScraper:
    """Serves canned pages per (filter, pageNumber). Holds a cookie and an auth
    header the way the real scraper's session does; neither may reach the
    sidecar."""

    def __init__(self):
        self.cookie, self.auth = COOKIE, AUTH
        self.pages = {
            ("MINOR_FANTASY_AVAILABLE", "1"): _page(["a1", "a2"], 3, 2),
            ("MINOR_FANTASY_AVAILABLE", "2"): _page(["a3"], 3, 2),
            ("MINOR_FANTASY_TAKEN", "1"): _page(["t1"], 1, 1),
        }

    def _post_json(self, ctx, payload, what):
        d = payload["msgs"][0]["data"]
        return self.pages[(d["statusOrTeamFilter"], d["pageNumber"])]

    def _session_dead(self, raw):
        return False


def _pull(monkeypatch, scraper=None):
    monkeypatch.setattr(mv, "_pause", lambda bounds: None)
    meta = {}
    pulls = mv.fetch_eligibility(scraper or FakeScraper(), None, None, meta=meta)
    return pulls, meta


class TestSidecar:
    def test_records_payload_totals_and_rows_per_filter(self, monkeypatch, tmp_path, capsys):
        pulls, meta = _pull(monkeypatch)
        path = tmp_path / "wk_pull.json"
        mv.write_pull_sidecar(meta, path)
        side = json.loads(path.read_text(encoding="utf-8"))

        assert set(side) == {"MINOR_FANTASY_AVAILABLE", "MINOR_FANTASY_TAKEN"}
        av = side["MINOR_FANTASY_AVAILABLE"]
        assert (av["totalNumResults"], av["totalNumPages"]) == (3, 2)
        assert (av["pages_fetched"], av["rows_parsed"]) == (2, 3)
        data = av["request_payload"]["msgs"][0]["data"]
        assert data["statusOrTeamFilter"] == "MINOR_FANTASY_AVAILABLE"
        for key in ("pageNumber", "maxResultsPerPage", "miscDisplayType",
                    "positionOrGroup", "seasonOrProjection", "timeframeTypeCode"):
            assert key in data
        tk = side["MINOR_FANTASY_TAKEN"]
        assert (tk["totalNumResults"], tk["totalNumPages"], tk["rows_parsed"]) == (1, 1, 1)

        out = capsys.readouterr().out
        assert "MINOR_FANTASY_AVAILABLE: totalNumResults=3 totalNumPages=2" in out
        assert "MINOR_FANTASY_TAKEN: totalNumResults=1" in out

    def test_sample_sidecar(self, monkeypatch, tmp_path):
        _, meta = _pull(monkeypatch)
        path = tmp_path / "wk_pull.json"
        mv.write_pull_sidecar(meta, path)
        print(path.read_text(encoding="utf-8"))

    def test_no_cookie_or_auth_value_in_sidecar(self, monkeypatch, tmp_path):
        _, meta = _pull(monkeypatch)
        path = tmp_path / "wk_pull.json"
        mv.write_pull_sidecar(meta, path)
        text = path.read_text(encoding="utf-8")
        assert COOKIE not in text and AUTH not in text
        assert "cookie" not in text.lower()

    def test_scrub_drops_a_credential_that_reaches_the_payload(self, monkeypatch, tmp_path):
        real = mv.eligibility_payload

        def leaky(filt, page_no):
            p = real(filt, page_no)
            p["Cookie"] = COOKIE
            p["msgs"][0]["data"]["authToken"] = AUTH
            return p

        monkeypatch.setattr(mv, "eligibility_payload", leaky)
        _, meta = _pull(monkeypatch)
        path = tmp_path / "wk_pull.json"
        mv.write_pull_sidecar(meta, path)
        text = path.read_text(encoding="utf-8")
        assert COOKIE not in text and AUTH not in text

    def test_meta_does_not_change_what_the_pull_returns(self, monkeypatch):
        with_meta, _ = _pull(monkeypatch)
        monkeypatch.setattr(mv, "_pause", lambda bounds: None)
        without = mv.fetch_eligibility(FakeScraper(), None, None)
        assert with_meta == without
        assert len(mv.eligibility_to_frame(with_meta)) == 4


class _FakeBrowser:
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


class TestSidecarWriteFailure:
    def test_failed_sidecar_write_warns_and_rows_are_unchanged(self, monkeypatch, tmp_path, capsys):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        (raw_dir / "fantrax_minor_eligibility_2026_wk04_pull.json").mkdir()   # write_text fails here
        cfg = SimpleNamespace(snapshot_season=2026, snapshot_week=4,
                              data_dir=str(tmp_path), raw_dir=str(raw_dir),
                              user_data_dir=str(tmp_path / "profile"),
                              headless=True, nav_timeout_ms=1000)
        playwright = types.ModuleType("playwright.sync_api")
        playwright.sync_playwright = _FakeBrowser
        monkeypatch.setitem(sys.modules, "playwright.sync_api", playwright)
        monkeypatch.setattr(mv, "CFG", cfg)
        monkeypatch.setattr(mv.etl.CFG, "data_dir", str(tmp_path))
        monkeypatch.setattr(mv, "date", SimpleNamespace(today=lambda: date(2026, 10, 4)))
        monkeypatch.setattr(mv, "_pause", lambda bounds: None)
        monkeypatch.setattr(mv, "fx", SimpleNamespace(
            FantraxScraper=lambda c: FakeScraper(),
            derive_week_label=lambda c, d: "04",
            _cell_num=mv.fx._cell_num))
        monkeypatch.setattr(mv, "eligibility_payload",
                            lambda f, n: {"msgs": [{"data": {
                                "statusOrTeamFilter": f, "pageNumber": str(n)}}]})

        elig = mv.run()

        out = capsys.readouterr().out
        assert "[warn] pull sidecar not written" in out
        assert sorted(elig["scorer_id"]) == ["a1", "a2", "a3", "t1"]
        landed = pd.read_parquet(tmp_path / "fact_minor_eligibility.parquet")
        assert sorted(landed["scorer_id"]) == ["a1", "a2", "a3", "t1"]

    def test_write_to_missing_directory_does_not_raise(self, tmp_path, capsys):
        mv.write_pull_sidecar({"F": {"pages_fetched": 1, "rows_parsed": 1}},
                              tmp_path / "nope" / "x_pull.json")
        assert "[warn] pull sidecar not written" in capsys.readouterr().out

    def test_malformed_meta_does_not_raise(self, tmp_path, capsys):
        mv.write_pull_sidecar({"F": {}}, tmp_path / "x_pull.json")
        assert "[warn] pull sidecar not written" in capsys.readouterr().out

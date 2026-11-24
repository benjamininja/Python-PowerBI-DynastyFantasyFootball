"""FantraxScraper._creds reads only the two Fantrax names from .env (#626).
Fakes only: no login, no network, no real secret."""
import importlib
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

fx = importlib.import_module("04a_fantrax_weekly_scrape")
etl_run_log = importlib.import_module("etl_run_log")


def test_creds_read_only_the_two_fantrax_names_from_dotenv(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("ETL_STORAGE=postgres\n"
                   "FANTRAX_EMAIL=fake-login-name\n"
                   "FANTRAX_PASSWORD=fake-password\n", encoding="utf-8")
    monkeypatch.setattr(etl_run_log, "ENV_FILE", env)
    for name in ("FANTRAX_EMAIL", "FANTRAX_PASSWORD", "ETL_STORAGE"):
        monkeypatch.delenv(name, raising=False)
    scraper = fx.FantraxScraper.__new__(fx.FantraxScraper)
    assert scraper._creds() == ("fake-login-name", "fake-password")
    assert "ETL_STORAGE" not in os.environ
    assert "FANTRAX_EMAIL" not in os.environ
    assert "FANTRAX_PASSWORD" not in os.environ


def test_totp_secret_is_read_from_dotenv_and_sets_nothing(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("ETL_STORAGE=postgres\nFANTRAX_TOTP_SECRET=FAKEFAKEFAKEFAKE\n",
                   encoding="utf-8")
    monkeypatch.setattr(etl_run_log, "ENV_FILE", env)
    monkeypatch.delenv("FANTRAX_TOTP_SECRET", raising=False)
    monkeypatch.delenv("ETL_STORAGE", raising=False)
    seen = []
    scraper = fx.FantraxScraper.__new__(fx.FantraxScraper)
    monkeypatch.setattr(scraper, "_totp_code", lambda secret, page: seen.append(secret) or "000000",
                        raising=False)

    class Page:
        def __getattr__(self, name):
            raise AssertionError("page touched: " + name)

    try:
        scraper._answer_code_prompt(Page())
    except AssertionError:
        pass
    assert seen == ["FAKEFAKEFAKEFAKE"]
    assert "FANTRAX_TOTP_SECRET" not in os.environ
    assert "ETL_STORAGE" not in os.environ


def test_creds_missing_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(etl_run_log, "ENV_FILE", tmp_path / "absent.env")
    monkeypatch.delenv("FANTRAX_EMAIL", raising=False)
    monkeypatch.delenv("FANTRAX_PASSWORD", raising=False)
    scraper = fx.FantraxScraper.__new__(fx.FantraxScraper)
    with pytest.raises(RuntimeError):
        scraper._creds()

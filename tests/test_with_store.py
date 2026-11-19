"""#615: a hand run reaches the store only through `run.ps1 -Store`
(scripts/with_store.py), never through the seam reading .env.

Three cases, one test each: a seed run through the launcher is on the store, the
keep loader run through it still stops, and a test whose .env names the store
writes only parquet. The values here are fakes in a tmp .env; no connection is
made.
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import etl_helpers as etl
import etl_run_log

LAUNCHER = REPO / "scripts" / "with_store.py"
LOADER = REPO / "scripts" / "load_contract_choices.py"
FAKE_URL = "postgresql://invalid.invalid:5432/none?password=fake-secret-615"

PROBE = f'''
import os
import sys
sys.path.insert(0, {str(REPO / "notebooks")!r})
import etl_helpers as etl

backend = etl._backend()
print("store backend:", backend is not None)
print("url as in .env:", os.environ["SUPABASE_DB_URL"] == {FAKE_URL!r})
'''


@pytest.fixture
def dotenv(tmp_path):
    path = tmp_path / "store.env"
    path.write_text(f"ETL_STORAGE=postgres\nSUPABASE_DB_URL={FAKE_URL}\n", encoding="utf-8")
    return path


def through_launcher(dotenv, *command):
    return subprocess.run([sys.executable, str(LAUNCHER), "--env-file", str(dotenv), "--", *command],
                          capture_output=True, text=True)


def test_a_seed_run_through_the_launcher_is_on_the_store_and_prints_no_value(dotenv, tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    done = through_launcher(dotenv, sys.executable, str(probe))
    assert done.returncode == 0, done.stderr
    assert "store backend: True" in done.stdout and "url as in .env: True" in done.stdout
    assert "fake-secret-615" not in done.stdout + done.stderr


def test_the_keep_loader_run_through_the_launcher_still_stops_and_writes_nothing(dotenv, tmp_path):
    out = tmp_path / "out.sql"
    done = through_launcher(dotenv, sys.executable, str(LOADER), str(tmp_path / "keep.xlsx"),
                            "--season", "2026-2027", "--out", str(out))
    assert done.returncode == 1, done.stdout + done.stderr
    assert "stopped: ETL_STORAGE selects the database; the loader reads the published snapshot only" in done.stdout
    assert "nothing was written" in done.stdout
    assert not out.exists()
    assert "fake-secret-615" not in done.stdout + done.stderr


def test_a_test_whose_dotenv_names_the_store_writes_only_parquet(dotenv, tmp_path, monkeypatch):
    monkeypatch.setattr(etl_run_log, "ENV_FILE", dotenv)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    assert etl._backend() is None
    table = "dim_fantrax_crosswalk_override"
    row = pd.DataFrame({"scorer_id": ["aaaaa"], "gsis_id": ["G1"], "note": ["run 1"],
                        "recorded_at": [pd.Timestamp("2026-11-08 12:00:00", tz="UTC")],
                        "origin": ["form"]})
    etl.write_table(table, row)
    assert (tmp_path / f"{table}.parquet").exists()


def test_the_launcher_refuses_when_the_env_names_no_store_and_runs_nothing(tmp_path):
    empty = tmp_path / "empty.env"
    empty.write_text("OTHER=1\n", encoding="utf-8")
    ran = tmp_path / "ran.txt"
    done = through_launcher(empty, sys.executable, "-c", f"open({str(ran)!r}, 'w').close()")
    assert done.returncode == 2 and not ran.exists()
    assert "ETL_STORAGE is not postgres" in done.stdout


def test_run_ps1_routes_store_and_notebooks():
    text = (REPO / "run.ps1").read_text(encoding="utf-8")
    assert "[switch]$Store" in text and r"scripts\with_store.py" in text
    assert "nbconvert" in text and "'--inplace'" in text

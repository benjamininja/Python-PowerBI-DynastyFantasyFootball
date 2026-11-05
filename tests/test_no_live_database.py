"""No test can reach the real project (#135): tests/conftest.py strips
ETL_STORAGE and SUPABASE_DB_URL before every case. The proof runs a probe
test in a child pytest whose environment holds both, with a copy of the
conftest beside it."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

PROBE = '''
import os
import sys
sys.path.insert(0, {notebooks!r})

import pandas as pd
import pytest

import etl_helpers as etl


def test_the_environment_is_clean():
    assert "ETL_STORAGE" not in os.environ
    assert "SUPABASE_DB_URL" not in os.environ


def test_the_seam_is_on_parquet(tmp_path, monkeypatch):
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    assert etl._backend() is None
    with pytest.raises(etl.StorageError, match="not declared"):
        etl.read_table("fact_not_a_table")
'''


def test_a_test_cannot_see_the_live_database_settings(tmp_path):
    probe_dir = tmp_path / "probe"
    probe_dir.mkdir()
    shutil.copy(HERE / "conftest.py", probe_dir / "conftest.py")
    (probe_dir / "test_probe.py").write_text(
        PROBE.format(notebooks=str(HERE.parent / "notebooks")), encoding="utf-8")
    env = {**os.environ, "ETL_STORAGE": "postgres",
           "SUPABASE_DB_URL": "postgresql://invalid.invalid:5432/none"}
    done = subprocess.run(
        [sys.executable, "-m", "pytest", str(probe_dir), "--rootdir", str(probe_dir),
         "-p", "no:cacheprovider", "-q"],
        env=env, capture_output=True, text=True, cwd=probe_dir)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "2 passed" in done.stdout

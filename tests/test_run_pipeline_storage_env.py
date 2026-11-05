"""run_pipeline resolves ETL_STORAGE and SUPABASE_DB_URL from the repo .env (#356).

Every test uses a tmp .env, never the real one. The process environment wins
over the file; the step subprocesses inherit the resolved values; the URL is
never printed.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import run_pipeline as rp

URL = "postgresql://db.example.invalid:5432/postgres?password=s3cretpw"


@pytest.fixture
def clean_env(monkeypatch):
    for key in ("ETL_STORAGE", rp.etl_run_log.URL_ENV):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def _env_file(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_env_file_postgres_selected_without_env_var(clean_env, tmp_path):
    path = _env_file(tmp_path, f"ETL_STORAGE=postgres\n{rp.etl_run_log.URL_ENV}={URL}\n")
    assert rp.resolve_storage_env(path) == "postgres"
    assert rp.storage_is_postgres()
    assert rp.os.environ[rp.etl_run_log.URL_ENV] == URL


def test_env_var_parquet_beats_env_file_postgres(clean_env, tmp_path):
    clean_env.setenv("ETL_STORAGE", "parquet")
    path = _env_file(tmp_path, "ETL_STORAGE=postgres\n")
    assert rp.resolve_storage_env(path) == "parquet"
    assert not rp.storage_is_postgres()


def test_no_env_file_value_defaults_to_parquet(clean_env, tmp_path):
    assert rp.resolve_storage_env(tmp_path / "missing.env") == "parquet"


def test_step_subprocess_environment_carries_resolved_value(clean_env, tmp_path):
    path = _env_file(tmp_path, f"ETL_STORAGE=postgres\n{rp.etl_run_log.URL_ENV}={URL}\n")
    rp.resolve_storage_env(path)
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw["env"])
        return subprocess.CompletedProcess(cmd, 0, "", "")

    clean_env.setattr(rp.subprocess, "run", fake_run)
    steps = [{"name": "s", "chain": "c", "cmd": ["py", "x"], "phases": {"INSEASON"}, "needs": []}]
    rp.run_steps(steps, "INSEASON", None, False)
    assert seen["ETL_STORAGE"] == "postgres"
    assert seen[rp.etl_run_log.URL_ENV] == URL


def test_url_never_in_stdout(clean_env, tmp_path, capsys):
    path = _env_file(tmp_path, f"ETL_STORAGE=postgres\n{rp.etl_run_log.URL_ENV}={URL}\n")
    clean_env.setattr(rp, "REPO", tmp_path)
    clean_env.setattr(rp, "check_only", lambda accept: 0)
    clean_env.setattr(sys, "argv", ["run_pipeline.py", "--check-only"])
    assert path.name == ".env"
    rp.main()
    out = capsys.readouterr().out
    assert "storage: postgres" in out
    assert URL not in out and "s3cretpw" not in out

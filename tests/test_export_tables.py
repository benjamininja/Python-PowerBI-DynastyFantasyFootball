"""The owner's re-export (#459, B10): scripts/export_tables.py on a fake
database read. Nothing here reaches a database or writes under data/."""
import contextlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd
import pytest
import yaml

import etl_helpers as etl
import etl_storage_pg as pg
import export_tables
from test_etl_storage import REGISTRY


@pytest.fixture
def world(tmp_path, monkeypatch):
    registry = tmp_path / "registry.yml"
    registry.write_text(yaml.safe_dump(REGISTRY), encoding="utf-8")
    monkeypatch.setattr(etl, "REGISTRY_PATH", registry)
    monkeypatch.setattr(pg, "_connect", contextlib.nullcontext)
    seen = {"read_only": []}
    data = {"dim_one": pd.DataFrame({"key": [2, 1], "label": ["b", "a"]}),
            "fact_unseen": pd.DataFrame({"id": [1], "games": [3]})}

    def read_on(conn, entry, columns=None):
        seen["read_only"].append(pg._READ_ONLY)
        return data[entry["name"]].copy()

    monkeypatch.setattr(pg, "read_on", read_on)
    monkeypatch.setenv(pg.URL_ENV, "postgresql://unused")
    default = tmp_path / "default-data"
    default.mkdir()
    monkeypatch.setattr(etl, "DATA", default)
    target = tmp_path / "worktree-data"
    target.mkdir()
    return default, target, seen


def test_it_writes_the_named_tables_into_out_and_prints_names_and_counts(world, capsys):
    default, target, seen = world
    assert export_tables.main(["dim_one", "fact_unseen", "--out", str(target)]) == 0
    out = capsys.readouterr().out
    assert "dim_one: 2 row(s) written" in out and "fact_unseen: 1 row(s) written" in out
    assert "wrote 2 table(s)" in out
    assert pd.read_parquet(target / "dim_one.parquet")["key"].tolist() == [1, 2]
    assert (target / "fact_unseen.parquet").exists()
    assert list(default.iterdir()) == []


def test_without_out_it_writes_into_the_seams_data_folder(world, capsys):
    default, target, _ = world
    assert export_tables.main(["dim_one"]) == 0
    assert (default / "dim_one.parquet").exists()
    assert list(target.iterdir()) == []


def test_the_session_is_read_only_and_the_flag_is_back_off_after(world):
    _, target, seen = world
    export_tables.main(["dim_one", "--out", str(target)])
    assert seen["read_only"] == [True]
    assert pg._READ_ONLY is False


def test_the_exporter_called_is_the_seams_with_the_folder_given(world, monkeypatch):
    _, target, _ = world
    calls = []
    monkeypatch.setattr(pg, "export_published",
                        lambda names, folder, changes=None: calls.append((list(names), Path(folder))) or
                        {n: 0 for n in names})
    assert export_tables.main(["dim_one", "dim_one", "fact_unseen", "--out", str(target)]) == 0
    assert calls == [(["dim_one", "fact_unseen"], target)]


def test_a_changed_column_set_is_reported_by_name_only(world, capsys):
    _, target, _ = world
    pd.DataFrame({"key": [1], "retired": ["x"]}).to_parquet(target / "dim_one.parquet", index=False)
    assert export_tables.main(["dim_one", "--out", str(target)]) == 0
    assert "dim_one: snapshot columns changed, added ['label'] dropped ['retired']" in capsys.readouterr().out


def test_an_unknown_table_is_refused_before_any_read(world, capsys, monkeypatch):
    _, target, _ = world
    monkeypatch.setattr(pg, "export_published", lambda *a, **k: pytest.fail("exported"))
    assert export_tables.main(["dim_one", "dim_nope", "--out", str(target)]) == 2
    assert "refused: not a published table: dim_nope" in capsys.readouterr().out


def test_an_out_folder_that_does_not_exist_is_refused_and_not_created(world, capsys, tmp_path):
    missing = tmp_path / "typo"
    assert export_tables.main(["dim_one", "--out", str(missing)]) == 2
    assert "refused: --out is not an existing folder" in capsys.readouterr().out
    assert not missing.exists()


def test_no_url_is_a_refusal(world, capsys, monkeypatch):
    _, target, _ = world
    monkeypatch.delenv(pg.URL_ENV)
    assert export_tables.main(["dim_one", "--out", str(target)]) == 2
    assert f"refused: {pg.URL_ENV} is not set" in capsys.readouterr().out


@pytest.mark.parametrize("message", [
    "could not reach postgresql://etl_writer.projref:hunter2-pw@aws-0.pooler.example.com:5432/postgres",
    "password hunter2-pw rejected for etl_writer.projref@aws-0.pooler.example.com:5432",
])
def test_an_error_that_holds_the_url_prints_neither_it_nor_its_password(world, capsys, monkeypatch, message):
    _, target, _ = world
    monkeypatch.setenv(pg.URL_ENV, "postgresql://etl_writer.projref:hunter2-pw@aws-0.pooler.example.com:5432/postgres")

    def failing(conn, entry, columns=None):
        raise RuntimeError(message)

    monkeypatch.setattr(pg, "read_on", failing)
    assert export_tables.main(["dim_one", "--out", str(target)]) == 1
    seen = capsys.readouterr()
    shown = seen.out + seen.err
    assert shown.startswith("stopped: RuntimeError")
    for secret in ("hunter2-pw", "etl_writer.projref", "pooler.example.com"):
        assert secret not in shown
    assert "Traceback" not in shown


def test_a_database_error_prints_no_value_and_no_traceback(world, capsys, monkeypatch):
    _, target, _ = world

    def failing(conn, entry, columns=None):
        raise RuntimeError("bad value 'SENTINEL-4471'")

    monkeypatch.setattr(pg, "read_on", failing)
    assert export_tables.main(["dim_one", "--out", str(target)]) == 1
    out = capsys.readouterr()
    assert "SENTINEL" not in out.out + out.err and "Traceback" not in out.out + out.err
    assert not (target / "dim_one.parquet").exists()

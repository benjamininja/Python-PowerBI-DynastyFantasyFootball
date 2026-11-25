"""A load of a published table leaves out a column its drops: entry names (#686).

The published snapshot lags the registry after a column drop until the next
export. `etl.without_dropped_columns` is the one rule: used where the snapshot is
loaded into the store (`load_published`, and so `reload_snapshot`, the backfill
and the restore drill) and where a capture copy is seeded from the stored table.
`_check_batch` and `read_stored` are not changed: a pipeline write that holds the
dropped column still fails, any other undeclared column still fails the load, and
`read_stored` still returns the file as it is.

The unit and capture cases need no database (the module carries the pg marker, as
tests/test_pg_marker.py requires of a file that names the test database). The database cases run on
TEST_DATABASE_URL only (the storage-pg job) against the real registry and the real
snapshot, with the dropped columns put back into a snapshot copy in a temp folder.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd
import pytest
import yaml

import backfill_postgres as backfill
import etl_helpers as etl
import etl_storage_pg as pg
from test_etl_storage import TABLES, database_url, empty_published

pytestmark = pytest.mark.pg

REGISTRY = {"tables": [
    {"name": "dim_kept", "type": "dim", "grain": "key",
     "columns": [{"name": "key", "dtype": "int64", "sql_type": "integer"},
                 {"name": "label", "dtype": "str", "sql_type": "text"}],
     "drops": [{"column": "old_note", "ticket": 686}]},
    {"name": "dim_plain", "type": "dim", "grain": "key",
     "columns": [{"name": "key", "dtype": "int64", "sql_type": "integer"}]},
]}


@pytest.fixture
def store(tmp_path, monkeypatch):
    registry = tmp_path / "registry.yml"
    registry.write_text(yaml.safe_dump(REGISTRY), encoding="utf-8")
    monkeypatch.setattr(etl, "REGISTRY_PATH", registry)
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(etl.CFG, "data_dir", str(data))
    return data


def lagging(**extra):
    """A published dim_kept that still holds the dropped column."""
    return pd.DataFrame({"key": [1, 2], "label": ["a", "b"], "old_note": ["x", "y"], **extra})


def entry(name="dim_kept"):
    return etl._table_entry(name)


class TestTheHelper:
    def test_it_leaves_out_the_named_column_and_prints_one_line(self, store, capsys):
        out = etl.without_dropped_columns(lagging(), entry())
        assert list(out.columns) == ["key", "label"]
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 1
        assert "dim_kept" in lines[0] and "old_note" in lines[0] and "#686" in lines[0]

    def test_the_frame_it_was_given_is_not_changed(self, store):
        frame = lagging()
        etl.without_dropped_columns(frame, entry())
        assert list(frame.columns) == ["key", "label", "old_note"]

    def test_a_frame_without_the_column_comes_back_as_it_was_and_prints_nothing(self, store, capsys):
        frame = lagging().drop(columns=["old_note"])
        assert etl.without_dropped_columns(frame, entry()) is frame
        assert capsys.readouterr().out == ""

    def test_a_table_with_no_drops_entry_comes_back_as_it_was(self, store, capsys):
        frame = pd.DataFrame({"key": [1], "old_note": ["x"]})
        assert etl.without_dropped_columns(frame, entry("dim_plain")) is frame
        assert capsys.readouterr().out == ""


class TestTheGuardsStayStrict:
    def test_a_second_undeclared_column_fails_and_the_message_names_that_column_only(self, store):
        frame = etl.without_dropped_columns(lagging(stray=[1, 2]), entry())
        with pytest.raises(etl.StorageError) as raised:
            etl._check_batch(frame, entry())
        assert "undeclared ['stray']" in str(raised.value)
        assert "old_note" not in str(raised.value)

    def test_a_pipeline_write_of_a_frame_holding_the_dropped_column_still_fails(self, store):
        with pytest.raises(etl.StorageError, match=r"undeclared \['old_note'\]"):
            etl.write_table("dim_kept", lagging())
        assert not (store / "dim_kept.parquet").exists()

    def test_read_stored_still_returns_the_dropped_column(self, store, tmp_path):
        lagging().to_parquet(store / "dim_kept.parquet", index=False)
        assert list(etl.read_stored("dim_kept").columns) == ["key", "label", "old_note"]
        other = tmp_path / "other"
        other.mkdir()
        lagging().to_parquet(other / "dim_kept.parquet", index=False)
        assert "old_note" in etl.read_stored("dim_kept", other).columns


class TestTheCaptureSeed:
    def test_a_merge_write_in_capture_mode_seeds_from_a_snapshot_that_lags_the_registry(self, store, tmp_path):
        lagging().to_parquet(store / "dim_kept.parquet", index=False)
        capture = tmp_path / "capture"
        capture.mkdir()
        with etl.capturing(capture):
            etl.write_table("dim_kept", pd.DataFrame({"key": [3], "label": ["c"]}), mode="upsert")
        got = pd.read_parquet(capture / "dim_kept.parquet")
        assert list(got.columns) == ["key", "label"]
        assert sorted(got["key"]) == [1, 2, 3]
        assert "old_note" in pd.read_parquet(store / "dim_kept.parquet").columns


class TestTheLoadOfARealSnapshot:
    """Every dropped column put back into a copy of the real snapshot."""

    @pytest.fixture
    def db(self, monkeypatch):
        url = database_url()
        empty_published(url, TABLES)
        monkeypatch.setenv(pg.URL_ENV, url)
        try:
            yield url
        finally:
            empty_published(url, TABLES)

    @pytest.fixture
    def snapshot(self, tmp_path):
        folder = tmp_path / "published"
        folder.mkdir()
        for name, frame in backfill.published_frames().items():
            for drop in etl._table_entry(name).get("drops") or []:
                frame = frame.assign(**{drop["column"]: "x"})
            frame.to_parquet(folder / f"{name}.parquet", index=False)
        return folder

    def dropped(self):
        return {(name, d["column"]) for name in etl.published_names()
                for d in etl._table_entry(name).get("drops") or []}

    def test_the_snapshot_copy_holds_every_dropped_column_and_read_stored_returns_it(self, snapshot):
        assert self.dropped()
        for name, column in self.dropped():
            assert column in etl.read_stored(name, snapshot).columns

    def test_a_verified_load_of_the_lagging_snapshot_passes_and_stores_no_such_column(self, db, snapshot, capsys):
        frames = backfill.published_frames(snapshot)
        loaded = pg.load_published(db, frames, replace=True, verify=True)
        assert loaded.problems == []
        printed = capsys.readouterr().out
        for name, column in self.dropped():
            assert f"{name}: column {column} left out of the load" in printed
        import psycopg
        with psycopg.connect(db) as conn:
            for name, column in self.dropped():
                found = conn.execute("SELECT 1 FROM information_schema.columns WHERE table_schema = %s "
                                     "AND table_name = %s AND column_name = %s", (pg.SCHEMA, name, column)).fetchone()
                assert found is None

    def test_the_reload_of_the_daily_run_takes_the_lagging_snapshot(self, db, snapshot):
        loaded = pg.reload_snapshot(db, etl.published_names(), snapshot)
        assert loaded.problems == []

    def test_a_second_undeclared_column_still_fails_the_load_naming_that_column_only(self, db, snapshot):
        name, column = sorted(self.dropped())[0]
        frames = backfill.published_frames(snapshot)
        frames[name] = frames[name].assign(stray=1)
        with pytest.raises(etl.StorageError) as raised:
            pg.load_published(db, frames, replace=True)
        assert "undeclared ['stray']" in str(raised.value)
        assert column not in str(raised.value)

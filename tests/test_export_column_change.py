"""A column change on a published table (#355). The snapshot export follows the
registry when only the snapshot is behind, and still refuses a frame that
disagrees with the registry. The database cases run on the seam_contract
scratch schema of TEST_DATABASE_URL (the storage-pg job); the unit cases need
no database.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest

import etl_helpers as etl
import etl_storage_pg as pg
from test_etl_storage import pg_scratch

pytestmark = pytest.mark.pg


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    yield from pg_scratch(tmp_path, monkeypatch)


@pytest.fixture
def snapshot_dir(scratch):
    folder = scratch / "published"
    folder.mkdir()
    return folder


class TestTheFrameIsTheRegistrysShape:
    ENTRY = {"name": "t", "columns": [{"name": "a"}, {"name": "b"}]}

    def test_the_registry_columns_in_any_order_pass(self):
        pg.frame_drift(pd.DataFrame({"b": [1], "a": [2]}), self.ENTRY)

    def test_a_missing_or_extra_column_raises_naming_columns_only(self):
        with pytest.raises(ValueError, match=r"missing \['b'\], extra \['z'\]") as err:
            pg.frame_drift(pd.DataFrame({"a": ["secret-cell"], "z": ["secret-cell"]}), self.ENTRY)
        assert "secret" not in str(err.value)

    def test_follow_registry_keeps_snapshot_order_then_adds_and_names_the_difference(self):
        frame = pd.DataFrame({"a": [1], "n": [2], "k": [3]})
        snapshot = pd.DataFrame({"k": [0], "gone": [0], "a": [0]})
        out, added, dropped = pg.follow_registry(frame, snapshot)
        assert list(out.columns) == ["k", "a", "n"] and added == ["n"] and dropped == ["gone"]
        assert out.iloc[0].tolist() == [3, 1, 2]


class TestTheExportOnAFakeConnection:
    """export_published with the database read replaced by frames: the same
    two outcomes as the database cases below, with no database."""

    @pytest.fixture
    def world(self, tmp_path, monkeypatch):
        import contextlib
        import yaml
        from test_etl_storage import REGISTRY
        registry = tmp_path / "registry.yml"
        registry.write_text(yaml.safe_dump(REGISTRY), encoding="utf-8")
        monkeypatch.setattr(etl, "REGISTRY_PATH", registry)
        monkeypatch.setattr(pg, "_connect", contextlib.nullcontext)
        data = {"dim_one": pd.DataFrame({"key": [1, 2], "label": ["secret-a", "secret-b"]}),
                "fact_unseen": pd.DataFrame({"id": [1], "games": [3]})}
        monkeypatch.setattr(pg, "read_on", lambda conn, entry, columns=None: data[entry["name"]].copy())
        folder = tmp_path / "published"
        folder.mkdir()
        return folder, data

    def test_a_snapshot_behind_the_registry_is_written_in_the_registry_shape(self, world):
        folder, _ = world
        pd.DataFrame({"key": [1, 2], "retired": ["x", "y"]}).to_parquet(folder / "dim_one.parquet", index=False)
        changes = {}
        pg.export_published(["dim_one"], folder, changes)
        out = pd.read_parquet(folder / "dim_one.parquet")
        assert list(out.columns) == ["key", "label"] and out["label"].tolist() == ["secret-a", "secret-b"]
        assert changes == {"dim_one": {"added": ["label"], "dropped": ["retired"]}}
        again = {}
        pg.export_published(["dim_one"], folder, again)
        assert again == {}

    def test_a_drifted_frame_raises_before_any_file_is_written(self, world):
        folder, data = world
        behind = pd.DataFrame({"key": [1], "retired": ["x"]})
        behind.to_parquet(folder / "dim_one.parquet", index=False)
        data["fact_unseen"] = data["fact_unseen"].assign(stray="secret-cell")
        changes = {}
        with pytest.raises(ValueError, match="fact_unseen: columns differ from the registry"):
            pg.export_published(["dim_one", "fact_unseen"], folder, changes)
        assert changes == {}
        pd.testing.assert_frame_equal(pd.read_parquet(folder / "dim_one.parquet"), behind)
        assert not (folder / "fact_unseen.parquet").exists()


class TestThePublishStepRecordsTheChange:
    def test_column_names_reach_the_plan_and_a_note_and_a_failed_export_records_none(self, monkeypatch):
        sys.path.insert(0, str(REPO / "scripts"))
        import run_pipeline as rp
        monkeypatch.setenv(pg.URL_ENV, "postgresql://unused")
        change = {"dim_one": {"added": ["label"], "dropped": ["retired"]}}

        def export(names, data_dir, changes=None):
            changes.update(change)
            return {}

        monkeypatch.setattr(pg, "export_published", export)
        plan = {"publish": ["dim_one"], "restore": []}
        assert rp.publish_postgres(plan, cwd=REPO) is None
        assert plan["column_changes"] == change
        assert plan["notes"] == ["snapshot columns changed (names only): "
                                 "dim_one added ['label'] dropped ['retired']"]

        def refuse(names, data_dir, changes=None):
            raise ValueError("dim_one: columns differ from the registry: missing [], extra ['stray']")

        monkeypatch.setattr(pg, "export_published", refuse)
        monkeypatch.setattr(rp, "_data_to_head", lambda tables, cwd: None)
        monkeypatch.setattr(pg, "reload_snapshot", lambda url, names, data: pg.Loaded([], {}))
        plan = {"passed": [], "publish": ["dim_one"], "restore": []}
        line = rp.publish_postgres(plan, cwd=REPO)
        assert line.startswith("ABORTED: export failed: ValueError") and "column_changes" not in plan
        assert plan["publish"] == []


class TestAnIntendedColumnChangeExports:
    def test_a_registry_column_add_exports_in_the_new_shape_and_names_the_columns(
            self, scratch, snapshot_dir):
        etl.write_table("dim_one", pd.DataFrame({"key": [1, 2], "label": ["secret-a", "secret-b"]}),
                        mode="replace")
        pd.DataFrame({"key": [1, 2], "retired": ["x", "y"]}).to_parquet(
            snapshot_dir / "dim_one.parquet", index=False)
        changes = {}

        written = pg.export_published(["dim_one"], snapshot_dir, changes)

        out = pd.read_parquet(snapshot_dir / "dim_one.parquet")
        assert written == {"dim_one": 2}
        assert list(out.columns) == ["key", "label"]
        assert out["label"].tolist() == ["secret-a", "secret-b"]
        assert changes == {"dim_one": {"added": ["label"], "dropped": ["retired"]}}
        assert "secret" not in repr(changes)

        again = {}
        pg.export_published(["dim_one"], snapshot_dir, again)
        assert again == {}
        pd.testing.assert_frame_equal(pd.read_parquet(snapshot_dir / "dim_one.parquet"), out)

    def test_a_frame_that_disagrees_with_the_registry_still_raises_and_writes_nothing(
            self, scratch, snapshot_dir, monkeypatch):
        etl.write_table("dim_one", pd.DataFrame({"key": [1], "label": ["a"]}), mode="replace")
        etl.write_table("fact_unseen", pd.DataFrame({"id": [1], "games": [3]}), mode="replace")
        behind = pd.DataFrame({"key": [1], "retired": ["x"]})
        behind.to_parquet(snapshot_dir / "dim_one.parquet", index=False)
        real = pg.read_on

        def drifted(conn, entry, columns=None):
            got = real(conn, entry, columns)
            return got if entry["name"] != "fact_unseen" else got.assign(stray="secret-cell")

        monkeypatch.setattr(pg, "read_on", drifted)
        changes = {}

        with pytest.raises(ValueError, match="fact_unseen: columns differ from the registry") as err:
            pg.export_published(["dim_one", "fact_unseen"], snapshot_dir, changes)

        assert "secret" not in str(err.value)
        assert changes == {}
        pd.testing.assert_frame_equal(pd.read_parquet(snapshot_dir / "dim_one.parquet"), behind)
        assert not (snapshot_dir / "fact_unseen.parquet").exists()

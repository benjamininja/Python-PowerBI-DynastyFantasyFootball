"""scripts/compare_tables.py on fixtures only (#186)."""
import importlib.util
import io
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("compare_tables", REPO / "scripts" / "compare_tables.py")
ct = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ct)

SECRET = "Zebediah Quillfeather"


def table():
    return pd.DataFrame({"k": [1, 2, 3], "v": [SECRET, "b", None]})


def parquet(frame: pd.DataFrame, **kwargs) -> bytes:
    buf = io.BytesIO()
    frame.to_parquet(buf, index=False, **kwargs)
    return buf.getvalue()


class TestCompareBytes:
    def test_same_bytes_are_identical(self):
        raw = parquet(table())
        assert ct.compare_bytes(raw, raw) == (ct.IDENTICAL, "")

    def test_same_frame_in_other_bytes_is_equal(self):
        a = parquet(table(), compression="snappy")
        b = parquet(table(), compression="gzip")
        assert a != b
        assert ct.compare_bytes(a, b) == (ct.EQUAL, "")

    def test_changed_cells_are_counted(self):
        other = table().assign(v=[SECRET, "x", "y"])
        status, detail = ct.compare_bytes(parquet(table()), parquet(other))
        assert (status, detail) == (ct.DIFFERS, "cells differing 2")

    def test_row_counts_are_reported(self):
        status, detail = ct.compare_bytes(parquet(table()), parquet(table().head(2)))
        assert status == ct.DIFFERS and detail == "rows left 3, right 2"

    def test_columns_present_on_one_side_are_counted(self):
        status, detail = ct.compare_bytes(parquet(table()), parquet(table().assign(extra=1)))
        assert status == ct.DIFFERS and "only left 0, only right 1" in detail

    def test_a_dtype_change_is_counted(self):
        other = table().astype({"k": "float64"})
        status, detail = ct.compare_bytes(parquet(table()), parquet(other))
        assert status == ct.DIFFERS and "different dtype 1" in detail

    def test_a_missing_side_differs(self):
        assert ct.compare_bytes(None, parquet(table()))[0] == ct.DIFFERS
        assert ct.compare_bytes(parquet(table()), None)[0] == ct.DIFFERS

    def test_detail_holds_no_value_and_no_column_name(self):
        other = table().assign(v=["x", "x", "x"]).rename(columns={"k": "secret_col"})
        _, detail = ct.compare_bytes(parquet(table()), parquet(other))
        assert SECRET not in detail and "secret_col" not in detail


class TestDirs:
    def folders(self, tmp_path):
        left, right = tmp_path / "left", tmp_path / "right"
        left.mkdir(), right.mkdir()
        return left, right

    def test_identical_folders_exit_zero(self, tmp_path):
        left, right = self.folders(tmp_path)
        for folder in (left, right):
            (folder / "dim_a.parquet").write_bytes(parquet(table()))
        out = io.StringIO()
        assert ct.run([str(left), str(right)], out=out) == 0
        assert "identical dim_a.parquet" in out.getvalue()
        assert "differing 0" in out.getvalue()

    def test_equal_frames_exit_zero(self, tmp_path):
        left, right = self.folders(tmp_path)
        (left / "dim_a.parquet").write_bytes(parquet(table(), compression="snappy"))
        (right / "dim_a.parquet").write_bytes(parquet(table(), compression="gzip"))
        out = io.StringIO()
        assert ct.run([str(left), str(right)], out=out) == 0
        assert "equal     dim_a.parquet" in out.getvalue()

    def test_a_difference_exits_one_and_prints_no_value(self, tmp_path):
        left, right = self.folders(tmp_path)
        (left / "dim_a.parquet").write_bytes(parquet(table()))
        (right / "dim_a.parquet").write_bytes(parquet(table().assign(v=["x", "x", "x"])))
        (left / "dim_only_left.parquet").write_bytes(parquet(table()))
        out = io.StringIO()
        assert ct.run([str(left), str(right)], out=out) == 1
        text = out.getvalue()
        assert "DIFFERS   dim_a.parquet  (cells differing" in text
        assert "dim_only_left.parquet  (missing on the right)" in text
        assert SECRET not in text

    def test_no_tables_is_not_a_pass(self, tmp_path):
        left, right = self.folders(tmp_path)
        assert ct.run([str(left), str(right)], out=io.StringIO()) == 1

    def test_wrong_arguments_exit_two(self, capsys):
        assert ct.run(["one", "two", "three"]) == 2


class TestHead:
    @pytest.fixture
    def repo(self, tmp_path, monkeypatch):
        def git(*args):
            subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "dim_a.parquet").write_bytes(parquet(table()))
        (tmp_path / "data" / "dim_b.parquet").write_bytes(parquet(table()))
        git("add", "data")
        git("commit", "-q", "-m", "tables")
        monkeypatch.setattr(ct, "REPO", tmp_path)
        return tmp_path

    def test_a_clean_tree_is_identical(self, repo):
        out = io.StringIO()
        assert ct.run(["HEAD"], data_dir=repo / "data", out=out) == 0
        assert "tables 2: identical 2, equal 0, differing 0" in out.getvalue()

    def test_an_edited_table_differs(self, repo):
        (repo / "data" / "dim_a.parquet").write_bytes(parquet(table().assign(v=["x", "x", "x"])))
        out = io.StringIO()
        assert ct.run(["HEAD"], data_dir=repo / "data", out=out) == 1
        assert "DIFFERS   dim_a.parquet" in out.getvalue()
        assert "identical dim_b.parquet" in out.getvalue()

    def test_a_table_new_in_the_tree_differs(self, repo):
        (repo / "data" / "dim_c.parquet").write_bytes(parquet(table()))
        out = io.StringIO()
        assert ct.run(["HEAD"], data_dir=repo / "data", out=out) == 1
        assert "dim_c.parquet  (missing on the right)" in out.getvalue()

    def test_a_table_deleted_from_the_tree_differs(self, repo):
        (repo / "data" / "dim_b.parquet").unlink()
        out = io.StringIO()
        assert ct.run(["HEAD"], data_dir=repo / "data", out=out) == 1
        assert "dim_b.parquet  (missing on the left)" in out.getvalue()


def test_the_script_runs_as_a_command(tmp_path):
    for name in ("left", "right"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "dim_a.parquet").write_bytes(parquet(table()))
    done = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "compare_tables.py"),
         str(tmp_path / "left"), str(tmp_path / "right")],
        capture_output=True, text=True)
    assert done.returncode == 0
    assert "tables 1: identical 1" in done.stdout

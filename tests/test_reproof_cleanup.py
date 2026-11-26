"""scripts/reproof.py removes its temp folders on every platform (#644)."""
import importlib.util
import os
import stat
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("reproof", REPO / "scripts" / "reproof.py")
rp = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("reproof", rp)
_spec.loader.exec_module(rp)


def read_only_tree(root: Path) -> Path:
    obj = root / ".git" / "objects" / "ab"
    obj.mkdir(parents=True)
    f = obj / "cdef"
    f.write_bytes(b"blob")
    os.chmod(f, stat.S_IREAD)
    return f


class TestRemoveTree:
    def test_removes_a_folder_holding_a_read_only_file(self, tmp_path):
        root = tmp_path / "export"
        read_only_tree(root)
        lines = []
        assert rp.remove_tree(root, lines.append)
        assert not root.exists()
        assert lines == []

    def test_a_missing_folder_is_fine(self, tmp_path):
        assert rp.remove_tree(tmp_path / "nope", print)

    def test_a_folder_it_cannot_remove_warns_and_does_not_raise(self, tmp_path, monkeypatch):
        root = tmp_path / "stuck"
        root.mkdir()

        def fail(path, **kwargs):
            raise PermissionError("locked")

        monkeypatch.setattr(rp.shutil, "rmtree", fail)
        lines = []
        assert not rp.remove_tree(root, lines.append)
        assert root.exists()
        assert lines == [f"warning: could not remove {root}"]


class TestFinish:
    def test_tmp_without_a_log_is_removed(self, tmp_path):
        tmp = tmp_path / "reproof-x"
        export = tmp / "export"
        export.mkdir(parents=True)
        read_only_tree(export)
        lines = []
        rp.finish(tmp, export, lines.append)
        assert not tmp.exists()
        assert lines == []

    def test_tmp_with_a_log_is_kept_without_the_export(self, tmp_path):
        tmp = tmp_path / "reproof-x"
        export = tmp / "export"
        export.mkdir(parents=True)
        read_only_tree(export)
        (tmp / "pytest.log").write_text("1 passed", encoding="utf-8")
        lines = []
        rp.finish(tmp, export, lines.append)
        assert (tmp / "pytest.log").is_file()
        assert not export.exists()
        assert lines == [f"log kept in {tmp}"]

"""The interpreter run_pipeline.py builds step commands from (#93, brief 1).
Windows keeps .venv/Scripts/python.exe; Linux falls back to .venv/bin/python,
then to the interpreter running the orchestrator."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import run_pipeline as rp


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def test_windows_path_wins_when_present(tmp_path):
    win = _touch(tmp_path / ".venv" / "Scripts" / "python.exe")
    _touch(tmp_path / ".venv" / "bin" / "python")
    assert rp._find_python(tmp_path) == win


def test_falls_back_to_venv_bin_python(tmp_path):
    posix = _touch(tmp_path / ".venv" / "bin" / "python")
    assert rp._find_python(tmp_path) == posix


def test_falls_back_to_sys_executable(tmp_path):
    assert rp._find_python(tmp_path) == Path(sys.executable)


def test_no_step_command_holds_scripts_without_the_windows_path(tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "VENV_PY", rp._find_python(tmp_path))
    steps = rp.build_steps("dynasty")
    assert steps
    for s in steps:
        assert s["cmd"][0] == sys.executable, s["name"]
        assert not any("Scripts" in part for part in s["cmd"][1:]), s["name"]

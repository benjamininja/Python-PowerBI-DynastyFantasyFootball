import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import normalize_notebooks as nn  # noqa: E402

NOTEBOOKS = sorted((ROOT / "notebooks").glob("*.ipynb"))


def _nb(source):
    return {
        "cells": [
            {"cell_type": "code", "id": "abc123", "metadata": {}, "outputs": [],
             "execution_count": None, "source": source},
        ],
        "metadata": {"kernelspec": {"name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _write(path, nb, final_newline=False):
    text = json.dumps(nb, ensure_ascii=False, indent=1)
    path.write_bytes((text + ("\n" if final_newline else "")).encode("utf-8"))


def test_string_source_becomes_list_of_lines(tmp_path):
    p = tmp_path / "nb.ipynb"
    _write(p, _nb("x = 1\ny = 'é'\nz = 3"))
    assert nn.normalize_file(p) is True
    raw = p.read_bytes().decode("utf-8")
    assert raw.endswith("}\n")
    assert "é" in raw
    nb = json.loads(raw)
    assert nb["cells"][0]["source"] == ["x = 1\n", "y = 'é'\n", "z = 3"]
    assert nb["cells"][0]["id"] == "abc123"
    assert nb["metadata"] == {"kernelspec": {"name": "python3"}}


def test_normalize_is_idempotent(tmp_path):
    p = tmp_path / "nb.ipynb"
    _write(p, _nb("a\nb\n"))
    assert nn.normalize_file(p) is True
    first = p.read_bytes()
    assert nn.normalize_file(p) is False
    assert p.read_bytes() == first
    assert json.loads(first)["cells"][0]["source"] == ["a\n", "b\n"]


def test_main_exit_code_fails_when_rewritten(tmp_path):
    p = tmp_path / "nb.ipynb"
    _write(p, _nb("a"))
    assert nn.main([str(p)]) == 1
    assert nn.main([str(p)]) == 0


def test_empty_source(tmp_path):
    p = tmp_path / "nb.ipynb"
    _write(p, _nb(""), final_newline=True)
    nn.normalize_file(p)
    assert json.loads(p.read_bytes())["cells"][0]["source"] == []


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_sources_match_origin_main(path):
    rel = path.relative_to(ROOT).as_posix()
    try:
        res = subprocess.run(["git", "show", f"origin/main:{rel}"], cwd=ROOT,
                             capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("origin/main copy not available")
    old = json.loads(res.stdout.decode("utf-8"))
    new = json.loads(path.read_bytes().decode("utf-8"))
    assert ["".join(c["source"]) for c in new["cells"]] == [
        "".join(c["source"]) if not isinstance(c["source"], str) else c["source"]
        for c in old["cells"]
    ]
    assert [{k: v for k, v in c.items() if k != "source"} for c in new["cells"]] == [
        {k: v for k, v in c.items() if k != "source"} for c in old["cells"]
    ]
    assert new["metadata"] == old["metadata"]


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_joined_sources_unchanged(path):
    before = json.loads(path.read_bytes().decode("utf-8"))
    after = nn.normalize_notebook(copy.deepcopy(before))

    def joined(nb):
        return ["".join(c["source"]) for c in nb["cells"]]

    assert joined(after) == joined(before)
    assert [c.get("id") for c in after["cells"]] == [c.get("id") for c in before["cells"]]
    for b, a in zip(before["cells"], after["cells"]):
        assert {k: v for k, v in a.items() if k != "source"} == {
            k: v for k, v in b.items() if k != "source"
        }
    assert after["metadata"] == before["metadata"]

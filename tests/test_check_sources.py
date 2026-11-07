import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_sources as cs


def _src(status):
    return {
        "id": "x",
        "name": "X",
        "status": status,
        "locator": "l",
        "purpose": "p",
        "auth": "a",
        "cadence": "c",
        "feeds": [],
        "match": [],
    }


def test_rejected_status_is_valid(capsys):
    assert cs.validate({"sources": [_src("rejected")]}) == 0


def test_unknown_status_fails(capsys):
    assert cs.validate({"sources": [_src("maybe")]}) == 1
    assert "status must be one of" in capsys.readouterr().out


def test_rejected_gets_its_own_table():
    data = {"sources": [_src("rejected")]}
    assert "**X**" in cs._table(data["sources"], "rejected")
    assert "**X**" not in cs._table(data["sources"], "planned")

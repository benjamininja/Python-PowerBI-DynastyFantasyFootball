"""Committed Fantrax fixtures hold only allowlisted keys (#115, ADR-0008
amendment decision 13). A fixture must be a fixed point of
make_fixtures.prune — so a hand edit, or a regeneration with a widened
trimmer, can't carry an owner/user field into the repo unnoticed.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import make_fixtures as mf

FIXTURES = sorted((REPO / "tests" / "fixtures" / "fantrax").glob("*.json"))


def test_every_fixture_has_an_allowlist():
    assert FIXTURES, "no fixtures found"
    assert {f.name for f in FIXTURES} <= set(mf.ALLOWLIST)


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_is_pruned(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert mf.prune(data, mf.ALLOWLIST[path.name]) == data


class TestPrune:
    SPEC = {"keep": mf.KEEP, "nested": [{"id": mf.KEEP}], "map": {mf.ANY: {"x": mf.KEEP}}}

    def test_drops_unlisted_keys(self):
        node = {"keep": 1, "owner": "someone", "nested": [{"id": 1, "email": "e"}],
                "map": {"t1": {"x": 1, "y": 2}}}
        assert mf.prune(node, self.SPEC) == {"keep": 1, "nested": [{"id": 1}],
                                             "map": {"t1": {"x": 1}}}

    def test_keep_leaf_rejects_objects(self):
        with pytest.raises(ValueError):
            mf.prune({"keep": {"secret": 1}}, self.SPEC)

    def test_shape_drift_raises(self):
        with pytest.raises(ValueError):
            mf.prune({"nested": {"id": 1}}, self.SPEC)

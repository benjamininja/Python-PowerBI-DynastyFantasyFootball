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


def test_txn_history_holds_no_team_names():
    """prune checks keys, not values: a team's display name sits in `content`
    on the team cells and in the pick owner hint, so trim_txn_history scrubs
    both. This holds a regenerated fixture to that."""
    pages = json.loads((REPO / "tests" / "fixtures" / "fantrax" / "txn_history.json")
                       .read_text(encoding="utf-8"))
    rows = [r for pg in pages for r in pg["responses"][0]["data"]["table"]["rows"]]
    assert rows
    for r in rows:
        for c in r["cells"]:
            assert "content" not in c or c["key"] in mf.TXN_CONTENT_KEYS
        hint = (r.get("draftPickDisplayParts") or {}).get("roundInfo", "")
        assert "(" not in hint or hint.endswith(mf.PICK_OWNER_PLACEHOLDER)

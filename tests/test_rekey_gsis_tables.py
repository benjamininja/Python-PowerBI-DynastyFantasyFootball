"""#639: one shared remap of old gsis_ids for every published table with a
gsis_id column (etl.rekey_gsis_tables), and its place in the pipeline
(run_pipeline.ride_along).

Everything runs on a temporary store with its own registry, through the seam.
The failure it answers: the nflverse Chain writes a new dim_gsis_link row, and
a table of another Chain (dim_fantrax_crosswalk, fact_fantrax_adp) keeps the
old id because its own Chain did not run, or was held, so no writer of it
applied the link. Nothing here touches data/ or git.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest
import yaml

import etl_helpers as etl
import run_pipeline as rp

NPL, LINK = "dim_nfl_players", etl.GSIS_LINK_TABLE
XW, ADP, SNAP, OVR = "dim_fantrax_crosswalk", "fact_fantrax_adp", "fact_nfl_snap_counts", "dim_override_private"
OLD, NEW, OTHER = "OLD1", "NEW1", "KEEP1"


def entry(name, cols, pk, chain, schema=None):
    out = {"name": name, "type": "fact", "grain": ", ".join(pk), "pk": pk, "chain": chain,
           "columns": [{"name": c, "dtype": "str"} for c in cols]}
    if schema:
        out["schema"] = schema
    return out


REGISTRY = {"tables": [
    entry(NPL, ["gsis_id"], ["gsis_id"], "nflverse"),
    entry(LINK, etl.GSIS_LINK_COLUMNS, ["old_gsis_id"], "nflverse"),
    entry(XW, ["scorer_id", "gsis_id"], ["scorer_id"], "fantrax_core"),
    entry(ADP, ["scorer_id", "season", "week", "gsis_id"], ["scorer_id", "season", "week"], "fantrax_core"),
    entry(SNAP, ["season", "week", "gsis_id"], ["season", "week", "gsis_id"], "nflverse"),
    entry(OVR, ["scorer_id", "gsis_id"], ["scorer_id"], None, schema="ops"),
]}


@pytest.fixture
def store(tmp_path, monkeypatch):
    registry = tmp_path / "registry.yml"
    registry.write_text(yaml.safe_dump(REGISTRY), encoding="utf-8")
    monkeypatch.setattr(etl, "REGISTRY_PATH", registry)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    return tmp_path


def put(name, rows, cols):
    etl.write_table(name, pd.DataFrame(rows, columns=cols))


def seed(links=((OLD, NEW),)):
    """The state of the 2026-11-25 failure: a new link row, the two Fantrax
    tables still on the old id."""
    put(NPL, [(NEW,), (OTHER,), (OLD,)], ["gsis_id"])
    put(LINK, [(o, n, "smart_id", "2026-11-24") for o, n in links], etl.GSIS_LINK_COLUMNS)
    put(XW, [("s1", OLD), ("s2", OTHER)], ["scorer_id", "gsis_id"])
    put(ADP, [("s1", "2026", "PRE", OLD), ("s1", "2026", "1", OLD), ("s2", "2026", "PRE", OTHER)],
        ["scorer_id", "season", "week", "gsis_id"])
    put(SNAP, [("2025", "1", OLD), ("2025", "1", OTHER)], ["season", "week", "gsis_id"])


def ids(name):
    return etl.read_table(name)["gsis_id"].tolist()


class TestRekeyGsisTables:
    def test_a_link_row_new_in_the_same_run_reaches_both_fantrax_tables(self, store):
        seed()
        done = etl.rekey_gsis_tables()
        assert ids(XW) == [NEW, OTHER]
        assert ids(ADP) == [NEW, NEW, OTHER]
        assert {XW, ADP} <= set(done["changed"])
        assert done["refused"] == {}

    def test_every_published_table_with_a_gsis_id_column_is_covered(self, store):
        seed()
        assert etl.gsis_id_tables() == sorted([XW, ADP, SNAP])
        etl.rekey_gsis_tables()
        old = set(etl.read_table(LINK)["old_gsis_id"])
        held = {n: sorted(old & set(ids(n))) for n in etl.gsis_id_tables()}
        assert {n: v for n, v in held.items() if v} == {}

    def test_a_table_kept_by_another_chain_is_covered_too(self, store):
        seed()
        etl.rekey_gsis_tables()
        assert ids(SNAP) == [NEW, OTHER]

    def test_a_chain_of_links_ends_on_the_newest_id(self, store):
        seed(links=((OLD, "MID1"), ("MID1", NEW)))
        etl.rekey_gsis_tables()
        assert ids(XW) == [NEW, OTHER]

    def test_only_the_id_column_changes_and_the_row_order_stays(self, store):
        seed()
        before = etl.read_table(ADP)
        etl.rekey_gsis_tables()
        after = etl.read_table(ADP)
        assert list(after.columns) == list(before.columns)
        assert after.drop(columns="gsis_id").equals(before.drop(columns="gsis_id"))

    def test_a_second_run_writes_nothing(self, store):
        seed()
        etl.rekey_gsis_tables()
        assert etl.rekey_gsis_tables()["changed"] == []

    def test_only_limits_the_tables(self, store):
        seed()
        done = etl.rekey_gsis_tables(only=[XW])
        assert done["changed"] == [XW]
        assert ids(ADP) == [OLD, OLD, OTHER]

    def test_dry_run_writes_nothing(self, store):
        seed()
        done = etl.rekey_gsis_tables(dry_run=True)
        assert set(done["changed"]) == {XW, ADP, SNAP}
        assert ids(XW) == [OLD, OTHER]

    def test_no_link_table_changes_nothing(self, store):
        put(NPL, [(OLD,)], ["gsis_id"])
        put(XW, [("s1", OLD)], ["scorer_id", "gsis_id"])
        assert etl.rekey_gsis_tables()["changed"] == []
        assert ids(XW) == [OLD]

    def test_a_private_table_is_not_remapped(self, store):
        seed()
        put(OVR, [("s1", OLD)], ["scorer_id", "gsis_id"])
        assert OVR not in etl.gsis_id_tables()
        etl.rekey_gsis_tables()
        assert ids(OVR) == [OLD]

    def test_a_table_whose_key_would_collide_is_refused_and_the_others_still_remap(self, store):
        seed()
        put(SNAP, [("2025", "1", OLD), ("2025", "1", NEW)], ["season", "week", "gsis_id"])
        done = etl.rekey_gsis_tables()
        assert list(done["refused"]) == [SNAP] and "sharing a key" in done["refused"][SNAP]
        assert ids(SNAP) == [OLD, NEW]
        assert ids(XW) == [NEW, OTHER]
        assert OLD not in done["refused"][SNAP]


def test_every_published_gsis_table_of_the_real_registry_is_covered():
    scanned = {n for n, e in etl._registry().items()
               if "gsis_id" in [c["name"] for c in e.get("columns", [])]
               and not etl.is_private(e) and n != NPL and etl.table_exists(n)}
    assert scanned == set(etl.gsis_id_tables())
    assert len(scanned) > 1


class TestRideAlong:
    def plan(self, **kw):
        base = {"passed": ["nflverse"], "failed": {}, "publish": [LINK, NPL, SNAP], "restore": []}
        base.update(kw)
        return base

    def run(self, plan, candidates, restore=None, gate=None):
        return rp.ride_along(plan, candidates, restore or (lambda t: None),
                             lambda t: etl.rekey_gsis_tables(only=t)["changed"],
                             gate or (lambda t: []))

    def test_a_chain_that_did_not_run_publishes_the_remapped_tables(self, store):
        seed()
        plan = self.plan()
        riders = self.run(plan, [XW, ADP])
        assert riders == [XW, ADP]
        assert {XW, ADP} <= set(plan["publish"]) and plan["restore"] == []
        assert ids(XW) == [NEW, OTHER] and ids(ADP) == [NEW, NEW, OTHER]

    def test_a_held_chain_is_restored_first_so_no_unvetted_row_rides(self, store):
        seed()
        published = etl.read_table(XW)
        put(XW, [("s1", OLD), ("s2", OTHER), ("s9", OLD)], ["scorer_id", "gsis_id"])
        calls = []

        def restore(tables):
            calls.append(list(tables))
            etl.write_table(XW, published)

        plan = self.plan(failed={"fantrax_core": ["step 04t failed"]}, restore=[ADP, XW])
        self.run(plan, [XW, ADP], restore=restore)
        assert calls[0] == [ADP, XW] or calls[0] == [XW, ADP]
        assert etl.read_table(XW)["scorer_id"].tolist() == ["s1", "s2"]
        assert ids(XW) == [NEW, OTHER]
        assert plan["restore"] == [] and {XW, ADP} <= set(plan["publish"])

    def test_a_rider_whose_gate_fails_is_restored_and_stays_out(self, store):
        seed()
        restored = []
        plan = self.plan(restore=[XW])
        riders = self.run(plan, [XW, ADP], restore=lambda t: restored.append(list(t)),
                          gate=lambda t: [XW])
        assert riders == [ADP]
        assert XW not in plan["publish"] and plan["restore"] == [XW]
        assert [XW] in restored

    def test_the_pipeline_call_publishes_a_held_chains_remapped_tables(self, store, monkeypatch, capsys):
        seed()
        restored = []
        monkeypatch.setattr(rp, "restore_to_head", lambda t: restored.append(list(t)))
        monkeypatch.setattr(rp.etl_checks, "run_suite", lambda tables, accepted, **kw: [])
        chains = {"nflverse": [LINK, NPL, SNAP], "fantrax_core": [XW, ADP]}
        plan = self.plan(failed={"fantrax_core": ["step 04t failed"]}, restore=[ADP, XW])
        rp.ride_gsis_links(plan, chains, [], {})
        assert set(plan["publish"]) == {LINK, NPL, SNAP, XW, ADP} and plan["restore"] == []
        assert ids(XW) == [NEW, OTHER] and ids(ADP) == [NEW, NEW, OTHER]
        assert "riders" in capsys.readouterr().out
        assert restored == [sorted([ADP, XW])]

    def test_a_failure_in_the_pipeline_call_restores_and_never_raises(self, store, monkeypatch, capsys):
        seed()
        restored = []
        monkeypatch.setattr(rp, "restore_to_head", lambda t: restored.append(list(t)))

        def boom(tables, accepted, **kw):
            raise RuntimeError("gate down")

        monkeypatch.setattr(rp.etl_checks, "run_suite", boom)
        chains = {"nflverse": [LINK, NPL, SNAP], "fantrax_core": [XW, ADP]}
        plan = self.plan()
        rp.ride_gsis_links(plan, chains, [], {})
        assert plan["publish"] == [LINK, NPL, SNAP] and "riders" not in plan
        assert restored[-1] == sorted([XW, ADP])
        assert "ride along failed" in capsys.readouterr().out

    def test_an_unreadable_store_skips_the_pipeline_call_and_never_raises(self, store, monkeypatch, capsys):
        def down():
            raise RuntimeError("no database")

        monkeypatch.setattr(rp.etl_helpers, "gsis_id_tables", down)
        plan = self.plan()
        rp.ride_gsis_links(plan, {"fantrax_core": [XW]}, [], {})
        assert plan["publish"] == [LINK, NPL, SNAP]
        assert "ride along skipped" in capsys.readouterr().out

    def test_nothing_to_remap_moves_nothing(self, store):
        seed(links=(("ZZZ", "YYY"),))
        plan = self.plan()
        assert self.run(plan, [XW, ADP]) == []
        assert plan["publish"] == [LINK, NPL, SNAP] and "riders" not in plan

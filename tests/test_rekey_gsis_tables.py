"""#639: one shared remap of old gsis_ids for every published table with a
gsis_id column (etl.rekey_gsis_tables), and its place in the pipeline as the
nflverse Chain's all-or-nothing re-key (run_pipeline.rekey_all_or_nothing).

Everything runs on a temporary store with its own registry, through the seam.
The failure it answers: the nflverse Chain writes a new dim_gsis_link row, and
a table of another Chain (dim_fantrax_crosswalk, fact_fantrax_adp) keeps the
old id because its own Chain did not run, or was held, so no writer of it
applied the link. Nothing here touches data/ or git.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

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
CHAINS = {"nflverse": [LINK, NPL, SNAP], "fantrax_core": [XW, ADP]}


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

    def test_undo_receives_each_written_tables_rows_as_they_were(self, store):
        seed()
        before = etl.read_table(XW)
        saved = {}
        etl.rekey_gsis_tables(only=[XW], undo=saved)
        assert list(saved) == [XW] and saved[XW].equals(before)

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

    def test_a_loop_in_the_links_refuses_each_table_without_naming_an_id(self, store):
        seed(links=((OLD, NEW), (NEW, OLD)))
        done = etl.rekey_gsis_tables()
        assert set(done["refused"]) == {XW, ADP, SNAP} and done["changed"] == []
        assert all(OLD not in why and NEW not in why for why in done["refused"].values())


def test_every_published_gsis_table_of_the_real_registry_is_covered():
    scanned = {n for n, e in etl._registry().items()
               if "gsis_id" in [c["name"] for c in e.get("columns", [])]
               and not etl.is_private(e) and n != NPL and etl.table_exists(n)}
    assert scanned == set(etl.gsis_id_tables())
    assert len(scanned) > 1


class Pipe:
    """The callables rekey_all_or_nothing takes, over the temp store. `published`
    is each table's rows at HEAD; the store is whatever the run left."""

    def __init__(self, published, gate_fails=(), step_raises=False, restore_raises=False):
        self.published, self.gate_fails = published, set(gate_fails)
        self.step_raises, self.restore_raises = step_raises, restore_raises
        self.saved, self.restored = {}, []
        self.old = {OLD}

    def needs(self, tables):
        return [t for t in tables if self.old & set(self.published[t]["gsis_id"])]

    def restore(self, tables):
        if self.restore_raises:
            raise RuntimeError("restore failed")
        self.restored.append(list(tables))
        for t in tables:
            etl.write_table(t, self.published[t])

    def rekey(self, tables, dry_run):
        if self.step_raises and not dry_run:
            etl.rekey_gsis_tables(only=tables[:1], undo=self.saved)
            raise RuntimeError("step raised")
        return etl.rekey_gsis_tables(only=tables, dry_run=dry_run, undo=self.saved)

    def undo(self, tables):
        for t in tables:
            if t in self.saved:
                etl.write_table(t, self.saved[t])

    def gate(self, tables):
        return [t for t in tables if t in self.gate_fails]

    def run(self, plan, candidates=(XW, ADP)):
        return rp.rekey_all_or_nothing(plan, CHAINS, list(candidates), self.needs, self.restore,
                                       self.rekey, self.undo, self.gate)


def published_now():
    return {n: etl.read_table(n) for n in (XW, ADP, SNAP)}


def plan_of(passed=("nflverse",), failed=None):
    chains = {c: CHAINS[c] for c in passed}
    return {"passed": list(passed), "failed": failed or {}, "publish": sorted(t for ts in chains.values() for t in ts),
            "restore": sorted(t for c in (failed or {}) for t in CHAINS[c])}


class TestAllOrNothing:
    def test_a_chain_that_did_not_run_rides_with_the_nflverse_link_row(self, store):
        seed()
        pipe = Pipe(published_now())
        plan = plan_of()
        assert pipe.run(plan) == [XW, ADP]
        assert {XW, ADP} <= set(plan["publish"]) and plan["restore"] == []
        assert plan["riders"] == [XW, ADP] and plan["passed"] == ["nflverse"]
        assert ids(XW) == [NEW, OTHER] and ids(ADP) == [NEW, NEW, OTHER]
        assert ids(SNAP) == [NEW, OTHER]

    def test_a_held_chain_goes_back_to_its_published_rows_so_no_unvetted_row_rides(self, store):
        seed()
        pipe = Pipe(published_now())
        put(XW, [("s1", OLD), ("s2", OTHER), ("s9", OLD)], ["scorer_id", "gsis_id"])
        plan = plan_of(failed={"fantrax_core": ["step 04t failed"]})
        pipe.run(plan)
        assert etl.read_table(XW)["scorer_id"].tolist() == ["s1", "s2"]
        assert ids(XW) == [NEW, OTHER]
        assert plan["restore"] == [] and {XW, ADP} <= set(plan["publish"])

    def test_a_store_a_failed_run_left_remapped_is_found_again_from_the_published_rows(self, store):
        seed()
        pipe = Pipe(published_now())
        put(XW, [("s1", NEW), ("s2", OTHER)], ["scorer_id", "gsis_id"])
        put(ADP, [("s1", "2026", "PRE", NEW), ("s1", "2026", "1", NEW), ("s2", "2026", "PRE", OTHER)],
            ["scorer_id", "season", "week", "gsis_id"])
        plan = plan_of()
        assert pipe.run(plan) == [XW, ADP]
        assert pipe.restored == [[XW, ADP]]

    def test_with_nflverse_held_nothing_is_remapped_from_the_run_s_links(self, store):
        seed()
        pipe = Pipe(published_now())
        plan = plan_of(passed=("fantrax_core",), failed={"nflverse": ["Gate failed"]})
        before = {n: ids(n) for n in (XW, ADP, SNAP)}
        assert pipe.run(plan) == []
        assert {n: ids(n) for n in (XW, ADP, SNAP)} == before
        assert pipe.restored == [] and pipe.saved == {} and "riders" not in plan

    def test_with_nflverse_not_run_nothing_is_remapped_either(self, store):
        seed()
        pipe = Pipe(published_now())
        plan = {"passed": ["fantrax_core"], "failed": {}, "publish": [XW, ADP], "restore": []}
        assert pipe.run(plan) == []
        assert ids(XW) == [OLD, OTHER]

    def test_one_table_refusing_holds_nflverse_and_nothing_publishes_or_is_written(self, store):
        seed()
        put(SNAP, [("2025", "1", OLD), ("2025", "1", NEW)], ["season", "week", "gsis_id"])
        pipe = Pipe(published_now())
        plan = plan_of()
        before = {n: ids(n) for n in (XW, ADP, SNAP)}
        assert pipe.run(plan) == []
        assert {n: ids(n) for n in (XW, ADP, SNAP)} == before
        assert plan["passed"] == [] and "nflverse" in plan["failed"]
        assert "sharing a key" in plan["failed"]["nflverse"][0] and OLD not in plan["failed"]["nflverse"][0]
        assert plan["publish"] == [] and {LINK, NPL, SNAP} <= set(plan["restore"])
        assert "riders" not in plan

    def test_a_rider_failing_its_gate_puts_every_remapped_table_back_and_holds_nflverse(self, store):
        seed()
        pipe = Pipe(published_now(), gate_fails=[XW])
        plan = plan_of()
        before = {n: etl.read_table(n) for n in (XW, ADP, SNAP)}
        assert pipe.run(plan) == []
        for n in (XW, ADP, SNAP):
            assert etl.read_table(n).equals(before[n])
        assert plan["passed"] == [] and "Gate failed" in plan["failed"]["nflverse"][0]
        assert {LINK, NPL, SNAP} <= set(plan["restore"])
        assert plan["publish"] == [] and "riders" not in plan

    def test_a_remapped_table_of_the_passing_nflverse_chain_failing_its_gate_holds_it_too(self, store):
        seed()
        pipe = Pipe(published_now(), gate_fails=[SNAP])
        plan = plan_of()
        pipe.run(plan)
        assert ids(SNAP) == [OLD, OTHER] and ids(XW) == [OLD, OTHER]
        assert "nflverse" in plan["failed"] and plan["publish"] == []

    def test_a_step_that_raises_puts_every_written_table_back_and_holds_nflverse(self, store):
        seed()
        pipe = Pipe(published_now(), step_raises=True)
        plan = plan_of()
        before = {n: etl.read_table(n) for n in (XW, ADP, SNAP)}
        assert pipe.run(plan) == []
        for n in (XW, ADP, SNAP):
            assert etl.read_table(n).equals(before[n])
        assert "a step raised" in plan["failed"]["nflverse"][0] and plan["passed"] == []

    def test_a_restore_that_fails_is_not_caught(self, store):
        seed()
        pipe = Pipe(published_now(), restore_raises=True)
        with pytest.raises(RuntimeError, match="restore failed"):
            pipe.run(plan_of())

    def test_nothing_old_anywhere_moves_nothing(self, store):
        seed(links=(("ZZZ", "YYY"),))
        pipe = Pipe(published_now())
        pipe.old = {"ZZZ"}
        plan = plan_of()
        assert pipe.run(plan) == []
        assert plan["passed"] == ["nflverse"] and "riders" not in plan


class TestMainFiling:
    def test_a_held_chains_review_results_are_not_filed_when_its_tables_ride(self, store, monkeypatch, tmp_path):
        seed()
        real = rp.etl_checks.chain_tables(rp.etl_checks.load_registry())
        chain_of = {t: c for c, ts in real.items() for t in ts}
        steps = [{"name": "s_nfl", "cmd": [], "phases": {"INSEASON"}, "needs": [],
                  "chain": "nflverse", "group": "pre_season"},
                 {"name": "s_fx", "cmd": [], "phases": {"INSEASON"}, "needs": [],
                  "chain": "fantrax_core", "group": "regular_season"}]
        filed = []

        def suite(tables, accepted, **kw):
            return ([rp.etl_checks.Result("grain", t, chain_of[t], "gate", True) for t in tables]
                    + [rp.etl_checks.Result("rows", t, chain_of[t], "review", False, "x",
                                            findings=[("k", "d")]) for t in tables])

        monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--phase", "INSEASON", "--no-push"])
        monkeypatch.setattr(rp, "_load_04a", lambda: SimpleNamespace(derive_week_label=lambda cfg: "8", CFG=None))
        monkeypatch.setattr(rp, "build_steps", lambda profile: steps)
        monkeypatch.setattr(rp, "run_steps", lambda *a, **k: [
            {"name": "s_nfl", "status": "ok", "detail": ""},
            {"name": "s_fx", "status": "failed", "detail": "boom"}])
        monkeypatch.setattr(rp, "read_contract_list", lambda: None)
        monkeypatch.setattr(rp.etl_checks, "run_suite", suite)
        monkeypatch.setattr(rp.etl_checks, "file_review",
                            lambda results, run_id=None: filed.extend(r.table for r in results) or
                            {"open": 0, "opened": 0, "cleared": 0, "repeated": 0})
        monkeypatch.setattr(rp, "restore_to_head", lambda t: None)
        monkeypatch.setattr(rp, "_data_to_head", lambda t, cwd=None: None)
        monkeypatch.setattr(rp, "tracked_at_head", lambda t, cwd=None: {f"data/{n}.parquet" for n in t})
        monkeypatch.setattr(rp.etl_helpers, "read_stored",
                            lambda name, data_dir=None: pd.DataFrame({"gsis_id": [OLD, OTHER]}))
        committed = {}
        monkeypatch.setattr(rp, "commit_data", lambda *a, **k: committed.update(k) or "stub")
        monkeypatch.setattr(rp, "notify", lambda text: None)
        monkeypatch.setattr(rp, "review_counts", lambda: {})
        monkeypatch.setattr(rp, "OUT_DIR", tmp_path)

        rp.main()

        assert {XW, ADP} <= set(committed["publish"])
        assert filed and not ({XW, ADP} & set(filed))
        assert LINK in filed
        assert ids(XW) == [NEW, OTHER]


class TestRekeyGsisLinks:
    def wire(self, monkeypatch, gate_fails=()):
        restored = []
        monkeypatch.setattr(rp, "restore_to_head", lambda t: restored.append(list(t)))
        monkeypatch.setattr(rp, "_data_to_head", lambda t, cwd=None: None)
        monkeypatch.setattr(rp, "tracked_at_head",
                            lambda t, cwd=None: {f"data/{n}.parquet" for n in t})
        monkeypatch.setattr(rp.etl_helpers, "read_stored",
                            lambda name, data_dir=None: pd.DataFrame({"gsis_id": [OLD, OTHER]}))
        monkeypatch.setattr(rp.etl_checks, "run_suite", lambda tables, accepted, **kw: [
            rp.etl_checks.Result("grain", t, "fantrax_core", "gate", t not in gate_fails)
            for t in tables])
        monkeypatch.setattr(rp, "read_published", lambda tables, cwd=None: {t: None for t in tables})
        return restored

    def plan(self, **kw):
        base = plan_of()
        base.update(kw)
        return base

    def test_the_pipeline_call_publishes_a_chain_that_did_not_run_with_the_link_row(self, store, monkeypatch, capsys):
        seed()
        self.wire(monkeypatch)
        plan = self.plan()
        rp.rekey_gsis_links(plan, CHAINS, [], {})
        assert {XW, ADP} <= set(plan["publish"]) and plan["riders"] == sorted([XW, ADP])
        assert ids(XW) == [NEW, OTHER] and ids(ADP) == [NEW, NEW, OTHER]
        assert "riders" in capsys.readouterr().out

    def test_the_pipeline_call_holds_nflverse_when_a_rider_fails_its_gate(self, store, monkeypatch, capsys):
        seed()
        self.wire(monkeypatch, gate_fails=(ADP,))
        plan = self.plan()
        rp.rekey_gsis_links(plan, CHAINS, [], {})
        assert "nflverse" in plan["failed"] and plan["publish"] == []
        assert ids(XW) == [OLD, OTHER] and ids(ADP) == [OLD, OLD, OTHER] and ids(SNAP) == [OLD, OTHER]
        assert "HELD" in capsys.readouterr().out

    def test_the_pipeline_call_does_nothing_when_nflverse_did_not_pass(self, store, monkeypatch, capsys):
        seed()
        restored = self.wire(monkeypatch)
        plan = {"passed": ["fantrax_core"], "failed": {"nflverse": ["x"]}, "publish": [XW, ADP], "restore": []}
        rp.rekey_gsis_links(plan, CHAINS, [], {})
        assert restored == [] and ids(XW) == [OLD, OTHER] and "did not pass" in capsys.readouterr().out


KEYED = "fact_keyed_by_gsis"
REGISTRY_WITH_KEYED = {"tables": REGISTRY["tables"] + [
    entry(KEYED, ["season", "gsis_id"], ["season", "gsis_id"], "rookie")]}
CHAINS_WITH_KEYED = {**CHAINS, "rookie": [KEYED]}
PUBLISHED_LINKS = pd.DataFrame(columns=etl.GSIS_LINK_COLUMNS)
PUBLISHED_PLAYERS = pd.DataFrame({"gsis_id": [OLD, OTHER]})


@pytest.fixture
def keyed_store(tmp_path, monkeypatch):
    registry = tmp_path / "registry.yml"
    registry.write_text(yaml.safe_dump(REGISTRY_WITH_KEYED), encoding="utf-8")
    monkeypatch.setattr(etl, "REGISTRY_PATH", registry)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    return tmp_path


def run_in_step_writers():
    """What 04z and the dynasty crosswalk do in their own step (#697): the link
    row the nflverse step of the same run wrote is read from the store, and
    etl.current_gsis puts each id on its newest."""
    put(NPL, [(NEW,), (OTHER,), (OLD,)], ["gsis_id"])
    put(LINK, [(OLD, NEW, "smart_id", "2026-11-25")], etl.GSIS_LINK_COLUMNS)
    written = pd.DataFrame([("s1", OLD), ("s2", OTHER)], columns=["scorer_id", "gsis_id"])
    written["gsis_id"] = etl.current_gsis(written["gsis_id"])
    etl.write_table(XW, written)
    adp = pd.DataFrame([("s1", "2026", "PRE", OLD), ("s1", "2026", "1", OLD), ("s2", "2026", "PRE", OTHER)],
                       columns=["scorer_id", "season", "week", "gsis_id"])
    adp["gsis_id"] = etl.current_gsis(adp["gsis_id"])
    etl.write_table(ADP, adp)


def published_tables(plan):
    return [t for t in plan["publish"] if t in etl.gsis_id_tables() or t == KEYED]


class TestNflverseHeldAfterItsLinkRowWasWritten:
    """#697: nflverse writes a link row and is then held; another Chain passes."""

    def wire(self, monkeypatch, gate_fails=(), published_links=PUBLISHED_LINKS):
        monkeypatch.setattr(rp, "read_published", lambda tables, cwd=None: {
            etl.GSIS_LINK_TABLE: published_links, NPL: PUBLISHED_PLAYERS}.copy())
        monkeypatch.setattr(rp.etl_checks, "run_suite", lambda tables, accepted, **kw: [
            rp.etl_checks.Result("grain", t, "fantrax_core", "gate", t not in gate_fails)
            for t in tables])

    def held(self, passed=("fantrax_core",)):
        plan = {"passed": list(passed), "failed": {"nflverse": ["Gate failed"]},
                "publish": sorted(t for c in passed for t in CHAINS_WITH_KEYED[c]),
                "restore": sorted(CHAINS_WITH_KEYED["nflverse"])}
        return plan

    def test_the_run_leaves_the_new_id_in_the_other_chains_tables(self, keyed_store):
        run_in_step_writers()
        assert ids(XW) == [NEW, OTHER] and ids(ADP) == [NEW, NEW, OTHER]

    def test_no_published_table_holds_the_new_id(self, keyed_store, monkeypatch, capsys):
        run_in_step_writers()
        self.wire(monkeypatch)
        plan = self.held()
        rp.rekey_gsis_links(plan, CHAINS_WITH_KEYED, [], {})
        assert {XW, ADP} <= set(plan["publish"]) and plan["failed"].keys() == {"nflverse"}
        assert {t: NEW in ids(t) for t in published_tables(plan)} == {XW: False, ADP: False}
        assert ids(XW) == [OLD, OTHER] and ids(ADP) == [OLD, OLD, OTHER]
        assert "put back" in capsys.readouterr().out

    def test_only_the_id_column_changes_and_the_row_order_stays(self, keyed_store, monkeypatch):
        run_in_step_writers()
        before = etl.read_table(ADP)
        self.wire(monkeypatch)
        rp.rekey_gsis_links(self.held(), CHAINS_WITH_KEYED, [], {})
        after = etl.read_table(ADP)
        assert after.drop(columns="gsis_id").equals(before.drop(columns="gsis_id"))

    def test_the_link_rows_the_snapshot_holds_are_kept(self, keyed_store, monkeypatch):
        run_in_step_writers()
        published = pd.DataFrame([(OLD, NEW, "smart_id", "2026-11-20")], columns=etl.GSIS_LINK_COLUMNS)
        self.wire(monkeypatch, published_links=published)
        plan = self.held()
        rp.rekey_gsis_links(plan, CHAINS_WITH_KEYED, [], {})
        assert ids(XW) == [NEW, OTHER] and ids(ADP) == [NEW, NEW, OTHER]

    def test_a_chain_of_unpublished_links_goes_back_to_the_first_published_id(self, keyed_store, monkeypatch):
        put(NPL, [("MID1",), (NEW,), (OTHER,), (OLD,)], ["gsis_id"])
        put(LINK, [(OLD, "MID1", "smart_id", "2026-11-24"), ("MID1", NEW, "smart_id", "2026-11-25")],
            etl.GSIS_LINK_COLUMNS)
        put(XW, [("s1", NEW), ("s2", OTHER)], ["scorer_id", "gsis_id"])
        self.wire(monkeypatch)
        plan = self.held()
        rp.rekey_gsis_links(plan, CHAINS_WITH_KEYED, [], {})
        assert ids(XW) == [OLD, OTHER]

    def test_a_table_that_cannot_go_back_holds_its_own_chain_only(self, keyed_store, monkeypatch, capsys):
        run_in_step_writers()
        put(KEYED, [("2025", OLD), ("2025", NEW)], ["season", "gsis_id"])
        self.wire(monkeypatch)
        plan = self.held(passed=("fantrax_core", "rookie"))
        rp.rekey_gsis_links(plan, CHAINS_WITH_KEYED, [], {})
        assert plan["passed"] == ["fantrax_core"] and set(plan["failed"]) == {"nflverse", "rookie"}
        assert "sharing a key" in plan["failed"]["rookie"][0] and NEW not in plan["failed"]["rookie"][0]
        assert KEYED in plan["restore"] and KEYED not in plan["publish"]
        assert ids(KEYED) == [OLD, NEW]
        assert ids(XW) == [OLD, OTHER] and {XW, ADP} <= set(plan["publish"])

    def test_a_table_that_fails_its_gate_after_the_put_back_holds_its_chain(self, keyed_store, monkeypatch):
        run_in_step_writers()
        self.wire(monkeypatch, gate_fails=(XW,))
        plan = self.held()
        rp.rekey_gsis_links(plan, CHAINS_WITH_KEYED, [], {})
        assert plan["passed"] == [] and "Gate failed" in plan["failed"]["fantrax_core"][0]
        assert plan["publish"] == [] and {XW, ADP} <= set(plan["restore"])

    def test_a_step_that_raises_holds_every_passing_chain(self, keyed_store, monkeypatch):
        run_in_step_writers()
        self.wire(monkeypatch)

        def boom(unpublished, valid, only=None, dry_run=False):
            raise RuntimeError("boom")

        monkeypatch.setattr(etl, "put_back_gsis_tables", boom)
        plan = self.held()
        rp.rekey_gsis_links(plan, CHAINS_WITH_KEYED, [], {})
        assert plan["passed"] == [] and "a step raised" in plan["failed"]["fantrax_core"][0]
        assert plan["publish"] == [] and {XW, ADP} <= set(plan["restore"])

    def test_published_rows_that_cannot_be_read_hold_every_passing_chain(self, keyed_store, monkeypatch):
        run_in_step_writers()

        def unreadable(tables, cwd=None):
            raise RuntimeError("git could not list data/ at HEAD")

        monkeypatch.setattr(rp, "read_published", unreadable)
        plan = self.held()
        rp.rekey_gsis_links(plan, CHAINS_WITH_KEYED, [], {})
        assert plan["passed"] == [] and plan["publish"] == []

    def test_with_no_link_row_unpublished_nothing_is_read_back_or_written(self, keyed_store, monkeypatch):
        run_in_step_writers()
        published = etl.read_table(LINK)
        self.wire(monkeypatch, published_links=published)
        plan = self.held()
        rp.rekey_gsis_links(plan, CHAINS_WITH_KEYED, [], {})
        assert plan["passed"] == ["fantrax_core"] and ids(XW) == [NEW, OTHER]

    def test_with_nflverse_passing_the_put_back_stays_out_of_the_rekey(self, keyed_store):
        plan = plan_of()

        def never(tables, dry_run):
            raise AssertionError("put_back called")

        assert rp.put_back_unpublished_ids(plan, CHAINS_WITH_KEYED, never, lambda t: []) == []


class TestUnpublishedLinks:
    def test_the_rows_the_snapshot_does_not_hold_are_the_unpublished_ones(self):
        stored = pd.DataFrame([("A", "B", "smart_id", "d1"), ("B", "C", "smart_id", "d2")],
                              columns=etl.GSIS_LINK_COLUMNS)
        published = stored.iloc[:1]
        out = etl.unpublished_gsis_links(stored, published)
        assert out[["old_gsis_id", "new_gsis_id"]].values.tolist() == [["B", "C"]]

    def test_with_no_published_table_every_row_is_unpublished(self):
        stored = pd.DataFrame([("A", "B", "smart_id", "d1")], columns=etl.GSIS_LINK_COLUMNS)
        assert len(etl.unpublished_gsis_links(stored, None)) == 1

    def test_a_loop_among_unpublished_links_refuses_each_table(self, keyed_store):
        run_in_step_writers()
        loop = pd.DataFrame([(OLD, NEW, "smart_id", "d"), (NEW, OLD, "smart_id", "d")],
                            columns=etl.GSIS_LINK_COLUMNS)
        done = etl.put_back_gsis_tables(loop, {OLD, OTHER})
        assert set(done["refused"]) == {XW, ADP} and done["changed"] == []
        assert all(OLD not in why and NEW not in why for why in done["refused"].values())

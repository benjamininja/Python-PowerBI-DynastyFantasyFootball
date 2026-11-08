"""#431: the Record a crosswalk override script checks its inputs, then writes one
row through the seam. Synthetic ids only. Parquet backend here; the same write on
the throwaway Postgres is in test_record_crosswalk_override_pg.py.
"""
import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd
import pytest
import yaml

import etl_helpers as etl

rec = importlib.import_module("record_crosswalk_override")

NOW = pd.Timestamp("2026-11-08 12:00:00.123456", tz="UTC")
OVERRIDE = OVERRIDE_TABLE = rec.OVERRIDE_TABLE


def crosswalk(*pairs):
    return pd.DataFrame(pairs, columns=["scorer_id", "gsis_id"])


def players(*ids):
    return pd.DataFrame({"gsis_id": list(ids)})


def overrides(*pairs):
    return pd.DataFrame(pairs, columns=["scorer_id", "gsis_id"])


XW = crosswalk(("aaaaa", None), ("bbbbb", "G2"), ("ccccc", None))
PLAYERS = players("G1", "G2", "G3")
NONE = overrides()
LINKS = pd.DataFrame({"old_gsis_id": ["OLD1"], "new_gsis_id": ["G1"]})


def check(scorer="aaaaa", gsis="G1", replace=False, xw=XW, over=NONE, links=None):
    return rec.validate(scorer, gsis, replace, xw, PLAYERS, over, links)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("ETL_STORAGE", raising=False)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    return tmp_path


def env(scorer="aaaaa", gsis="G1", replace="false", run="123456789"):
    return {"SCORER_ID": scorer, "GSIS_ID": gsis, "REPLACE": replace, "GITHUB_RUN_ID": run}


def go(inputs, store, **kw):
    lines = []
    code = rec.run(env(**kw), out=lines.append, now=NOW, inputs=inputs)
    return code, lines


INPUTS = (XW, PLAYERS, NONE, None)


class TestShapes:
    @pytest.mark.parametrize("bad", ["", "AAAAA", "aaaa", "aaaaaa", "aa aa", "aaaa;", "<b>x1</b>"])
    def test_a_scorer_id_that_is_not_five_lowercase_alphanumerics_is_refused(self, bad):
        assert rec.shape_problems(bad, "G1", "false", "1") == [
            "scorer_id is not a Fantrax id (five lowercase letters or digits)"]

    @pytest.mark.parametrize("bad", ["", "G 1", "G1;rm", "x" * 25, "new!", "NEW1 2"])
    def test_a_gsis_id_that_is_not_an_id_shape_is_refused(self, bad):
        assert rec.shape_problems("aaaaa", bad, "false", "1") == ["gsis_id is neither a registry id nor new"]

    @pytest.mark.parametrize("good", ["00-0040715", "CAR787213", "new", "G1"])
    def test_registry_id_shapes_and_new_pass(self, good):
        assert rec.shape_problems("aaaaa", good, "false", "1") == []

    def test_replace_is_true_false_or_blank(self):
        assert rec.shape_problems("aaaaa", "G1", "maybe", "1") == ["replace is neither true nor false"]
        assert rec.shape_problems("aaaaa", "G1", "", "1") == []

    @pytest.mark.parametrize("bad", ["", "abc", "12 3"])
    def test_a_run_id_is_digits(self, bad):
        assert rec.shape_problems("aaaaa", "G1", "true", bad) == ["GITHUB_RUN_ID is not a run id"]

    def test_every_published_crosswalk_id_has_the_shape(self):
        published = etl.read_stored("dim_fantrax_crosswalk", REPO / "data")
        bad = [s for s in published["scorer_id"] if not rec.SCORER_SHAPE.fullmatch(s)]
        assert bad == []


class TestValidate:
    def test_a_known_scorer_and_a_registry_id_are_clean(self):
        assert check() == []

    def test_a_scorer_id_not_in_the_crosswalk_is_refused(self):
        assert check(scorer="zzzzz") == ["scorer_id zzzzz is not in dim_fantrax_crosswalk"]

    def test_a_gsis_id_not_in_the_registry_is_refused(self):
        assert check(gsis="G9") == ["gsis_id G9 is not in dim_nfl_players and is not new"]

    def test_new_needs_no_registry_row(self):
        assert check(gsis="new") == []

    def test_two_scorers_may_both_be_new(self):
        assert check(gsis="new", over=overrides(("ccccc", "new")), xw=crosswalk(("aaaaa", None), ("ccccc", "new"))) == []

    def test_a_gsis_id_the_crosswalk_gives_another_scorer_is_refused(self):
        assert check(gsis="G2") == ["gsis_id G2 is already claimed by scorer_id bbbbb in dim_fantrax_crosswalk"]

    def test_a_gsis_id_another_override_holds_is_refused(self):
        got = check(gsis="G3", over=overrides(("ccccc", "G3")))
        assert got == ["gsis_id G3 is already claimed by scorer_id ccccc in dim_fantrax_crosswalk_override"]

    def test_the_scorers_own_rows_do_not_collide_with_it(self):
        own = crosswalk(("aaaaa", "G1"), ("bbbbb", "G2"))
        assert check(gsis="G1", xw=own, over=overrides(("aaaaa", "G1")), replace=True) == []

    def test_an_old_id_is_compared_through_its_link(self):
        taken = crosswalk(("aaaaa", None), ("bbbbb", "G1"))
        assert check(gsis="OLD1", xw=taken, links=LINKS) == [
            "gsis_id OLD1 is already claimed by scorer_id bbbbb in dim_fantrax_crosswalk"]

    def test_an_old_id_with_a_link_is_a_known_id(self):
        assert check(gsis="OLD1", links=LINKS) == []
        assert check(gsis="OLD1") == ["gsis_id OLD1 is not in dim_nfl_players and is not new"]

    def test_an_existing_override_needs_the_replace_tick(self):
        mine = overrides(("aaaaa", "G3"))
        assert check(over=mine) == ["scorer_id aaaaa already has an override; tick replace to change it"]
        assert check(over=mine, replace=True) == []

    def test_every_problem_is_listed(self):
        assert len(check(scorer="zzzzz", gsis="G9")) == 2


class TestRun:
    def test_a_good_write_is_one_form_row_with_the_run_id(self, store):
        code, lines = go(INPUTS, store)
        assert code == 0
        got = etl.read_table(OVERRIDE_TABLE)
        assert got.to_dict("records") == [{"scorer_id": "aaaaa", "gsis_id": "G1", "note": "run 123456789",
                                           "recorded_at": NOW.floor("us"), "origin": "form"}]
        assert lines[-3:] == ["recorded: scorer_id aaaaa -> G1 (origin form, run 123456789)",
                              "replaced an earlier override: no", "wrote dim_fantrax_crosswalk_override: 1 row(s)"]

    def test_the_new_mark_is_written_as_new(self, store):
        assert go(INPUTS, store, gsis="new")[0] == 0
        assert etl.read_table(OVERRIDE_TABLE)["gsis_id"].tolist() == ["new"]

    def test_a_second_scorer_is_added_beside_the_first(self, store):
        assert go(INPUTS, store)[0] == 0
        again = (XW, PLAYERS, overrides(("aaaaa", "G1")), None)
        assert go(again, store, scorer="ccccc", gsis="G3")[0] == 0
        assert sorted(etl.read_table(OVERRIDE_TABLE)["scorer_id"]) == ["aaaaa", "ccccc"]

    def test_a_replace_changes_the_row_and_says_so(self, store):
        assert go(INPUTS, store)[0] == 0
        held = (XW, PLAYERS, overrides(("aaaaa", "G1")), None)
        code, lines = go(held, store, gsis="G3", replace="true", run="42")
        assert code == 0 and "replaced an earlier override: yes" in lines
        got = etl.read_table(OVERRIDE_TABLE)
        assert got[["scorer_id", "gsis_id", "note"]].to_dict("records") == [
            {"scorer_id": "aaaaa", "gsis_id": "G3", "note": "run 42"}]

    def test_a_replace_without_the_tick_writes_nothing(self, store):
        assert go(INPUTS, store)[0] == 0
        before = (store / f"{OVERRIDE}.parquet").read_bytes()
        held = (XW, PLAYERS, overrides(("aaaaa", "G1")), None)
        code, lines = go(held, store, gsis="G3")
        assert code == 1 and lines[-1] == "nothing was written"
        assert (store / f"{OVERRIDE}.parquet").read_bytes() == before

    @pytest.mark.parametrize("kw", [{"scorer": "zzzzz"}, {"gsis": "G9"}, {"gsis": "G2"}])
    def test_a_failed_check_writes_nothing(self, store, kw):
        code, lines = go(INPUTS, store, **kw)
        assert code == 1 and lines[-1] == "nothing was written"
        assert not etl.table_exists(OVERRIDE)

    def test_a_bad_shape_stops_before_any_read_and_echoes_nothing(self, store):
        lines = []
        code = rec.run(env(scorer="Bad Input <b>", gsis="also bad!"), out=lines.append, inputs=None)
        assert code == 1 and lines[-1] == "nothing was written"
        text = "\n".join(lines)
        assert "Bad Input" not in text and "also bad" not in text

    def test_a_good_log_holds_ids_and_counts_only(self, store):
        _, lines = go(INPUTS, store)
        assert lines[:2] == ["storage: parquet", "read: 3 crosswalk row(s), 3 player(s), 0 override(s)"]

    def test_an_unexpected_error_prints_its_type_only(self, store, monkeypatch, capsys):
        def boom():
            raise RuntimeError("postgresql://user:SECRET@host/db")
        monkeypatch.setattr(rec, "stored_inputs", boom)
        for key, value in env().items():
            monkeypatch.setenv(key, value)
        assert rec.main() == 1
        printed = capsys.readouterr().out
        assert "RuntimeError" in printed and "SECRET" not in printed


class TestStoredInputs:
    @pytest.fixture
    def tables(self, store, monkeypatch):
        reg = yaml.safe_load((REPO / "docs" / "data_model.yml").read_text(encoding="utf-8"))
        small = [
            {"name": "dim_fantrax_crosswalk", "type": "dim", "grain": "scorer_id", "pk": ["scorer_id"],
             "columns": [{"name": c, "dtype": "str"} for c in ("scorer_id", "gsis_id")]},
            {"name": "dim_nfl_players", "type": "dim", "grain": "gsis_id", "pk": ["gsis_id"],
             "columns": [{"name": "gsis_id", "dtype": "str"}]},
        ]
        keep = [t for t in reg["tables"] if t["name"] in (OVERRIDE, etl.GSIS_LINK_TABLE)]
        path = store / "registry.yml"
        path.write_text(yaml.safe_dump({"tables": small + keep}), encoding="utf-8")
        monkeypatch.setattr(etl, "REGISTRY_PATH", path)
        etl.write_table("dim_fantrax_crosswalk", XW)
        etl.write_table("dim_nfl_players", PLAYERS)
        return store

    def test_the_run_reads_the_stored_tables_and_writes_through_the_seam(self, tables):
        lines = []
        assert rec.run(env(), out=lines.append, now=NOW) == 0
        assert lines[1] == "read: 3 crosswalk row(s), 3 player(s), 0 override(s)"
        assert etl.read_table(OVERRIDE)["origin"].tolist() == ["form"]

    def test_the_second_run_sees_the_first_row(self, tables):
        assert rec.run(env(), out=lambda _: None, now=NOW) == 0
        lines = []
        assert rec.run(env(), out=lines.append, now=NOW) == 1
        assert "stopped: scorer_id aaaaa already has an override; tick replace to change it" in lines

    def test_a_row_that_lands_after_the_preflight_is_caught_by_the_check_at_the_write(self, tables, monkeypatch):
        assert rec.run(env(), out=lambda _: None, now=NOW) == 0
        monkeypatch.setattr(rec, "stored_inputs", lambda: (XW, PLAYERS, NONE, None))
        lines = []
        assert rec.run(env(scorer="bbbbb", gsis="G1"), out=lines.append, now=NOW) == 1
        assert lines[-2:] == ["stopped: gsis_id G1 is already claimed by scorer_id aaaaa in "
                              "dim_fantrax_crosswalk_override", "nothing was written"]
        assert etl.read_table(OVERRIDE)["scorer_id"].tolist() == ["aaaaa"]

    def test_a_lock_wait_that_times_out_stops_and_says_so(self, tables, monkeypatch):
        def gave_up(*args, **kw):
            raise etl.LockWaitTimeout("dim_fantrax_crosswalk_override: ops.dim_fantrax_crosswalk_override: "
                                      "waited 10s for a lock, gave up (lock_timeout); not retried")
        monkeypatch.setattr(etl, "write_table_checked", gave_up)
        lines = []
        assert rec.run(env(), out=lines.append, now=NOW) == 1
        assert lines[-2].startswith("stopped: dim_fantrax_crosswalk_override: ops.dim_fantrax_crosswalk_override: waited 10s")
        assert lines[-1] == "nothing was written"
        assert not etl.table_exists(OVERRIDE)

    def test_the_registry_allows_the_form_origin(self):
        entry = etl._table_entry(OVERRIDE)
        assert "origin IN ('csv', 'apply_script', 'form')" in entry["checks"]

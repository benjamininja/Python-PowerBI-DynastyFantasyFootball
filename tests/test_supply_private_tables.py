"""#93 brief 6: 02d and 04z read the Startup draft and the crosswalk overrides
from private tables, not from data/raw. Synthetic payloads only: every id,
name and note here is invented.

Parquet cases run everywhere. The same reads through the seam on the
throwaway Postgres are in test_supply_pg.py.
"""
import importlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd
import pytest
import yaml
from thefuzz import fuzz, process

import etl_checks as ec
import etl_helpers as etl

loader = importlib.import_module("load_draft_and_overrides")
compare = importlib.import_module("compare_loader_output")
rt = importlib.import_module("02d_fact_roster_transactions")

PRIVATE = ("dim_fantrax_crosswalk_override", "fact_startup_draft_slot", "dim_startup_draft_scorer")
NOTE = "SYNTHETIC NOTE about Pat Invented"
TEAM_NAME = "SYNTHETIC TEAM NAME"


def slot(div, rnd, pick, scorer, ms=1781138250000, **extra):
    row = {"divisionId": div, "round": rnd, "pickNumber": pick, "teamId": f"t{div}{pick}",
           "scorerId": scorer, "modifiedDate": ms}
    return {**row, **extra}


def payload(slots, scorers=()):
    return {"responses": [{"data": {"draftPicksOrdered": list(slots), "scorers": list(scorers)}}]}


def scorer(sid, name="Invented Player", pos="<b>WR</b>,DB", team="XYZ", rookie=True):
    return {"scorerId": sid, "name": name, "posShortNames": pos, "teamShortName": team,
            "rookie": rookie, "ownerName": TEAM_NAME}


def grid(divisions=("dvA", "dvB"), rounds=2, per=3, unmade=1):
    out, n = [], 0
    for div in divisions:
        for rnd in range(1, rounds + 1):
            for pick in range(1, per + 1):
                n += 1
                made = n > unmade
                out.append(slot(div, rnd, pick, f"s{n:03d}" if made else None,
                                ms=1781138250000 + n if made else None,
                                teamName=TEAM_NAME, isCommissioner=True, accountId="acct"))
    return out


def crosswalk(manual=(), new=()):
    rows = [(s, g, "manual") for s, g in manual] + [(s, None, "new") for s in new]
    return pd.DataFrame(rows, columns=["scorer_id", "gsis_id", "match_method"])


@pytest.fixture
def store(tmp_path, monkeypatch):
    """The real registry, parquet backend, in a temp data dir."""
    monkeypatch.delenv("ETL_STORAGE", raising=False)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    return tmp_path


class TestSlotsFromPayloads:
    def test_columns_are_the_slot_and_nothing_of_the_capture(self):
        slots = loader.slots_from_payloads([payload(grid())])
        assert list(slots.columns) == ["division_id", "round", "pick_in_round", "team_id",
                                       "scorer_id", "picked_at"]
        assert TEAM_NAME not in slots.to_csv() and "acct" not in slots.to_csv()

    def test_an_unmade_slot_has_no_scorer_and_no_time(self):
        slots = loader.slots_from_payloads([payload(grid(unmade=2))])
        unmade = slots[slots["scorer_id"].isna()]
        assert len(unmade) == 2 and unmade["picked_at"].isna().all()
        assert str(slots["picked_at"].dtype).endswith("UTC]")

    def test_the_latest_capture_wins_a_repeated_slot(self):
        later = grid()
        later[0]["teamId"] = "recaptured"
        slots = loader.slots_from_payloads([payload(grid()), payload(later)])
        assert len(slots) == 12
        assert slots.set_index(loader.SLOT_KEY).loc[("dvA", 1, 1), "team_id"] == "recaptured"

    def test_pick_time_is_the_capture_time_to_the_millisecond(self):
        slots = loader.slots_from_payloads([payload(grid())])
        made = slots[slots["scorer_id"].notna()].iloc[0]
        assert made["picked_at"] == pd.Timestamp(1781138250002, unit="ms", tz="UTC")


class TestScorersFromPayloads:
    def test_markup_is_stripped_and_the_first_capture_wins(self):
        a = payload([], [scorer("s1", name="First Name"), scorer("s2")])
        b = payload([], [scorer("s1", name="Second Name")])
        out = loader.scorers_from_payloads([a, b]).set_index("scorer_id")
        assert out.loc["s1", "player_name"] == "First Name"
        assert out.loc["s2", "position_raw"] == "WR,DB"
        assert list(out.columns) == ["player_name", "position_raw", "nfl_team", "is_rookie"]
        assert TEAM_NAME not in out.to_csv()


class TestDraftProblems:
    def frames(self, slots=980, unmade=5):
        scorers = [None] * unmade + [f"s{i}" for i in range(slots - unmade)]
        frame = pd.DataFrame({"scorer_id": scorers})
        return frame, pd.DataFrame({"scorer_id": ["s1"]})

    def test_980_slots_975_made_5_unmade_is_clean(self):
        assert loader.draft_problems(*self.frames()) == []

    def test_each_count_off_is_a_problem(self):
        assert len(loader.draft_problems(*self.frames(slots=979))) == 2   # slots and made
        assert len(loader.draft_problems(*self.frames(unmade=4))) == 2    # made and unmade

    def test_no_players_is_a_problem(self):
        slots, _ = self.frames()
        assert loader.draft_problems(slots, pd.DataFrame({"scorer_id": []}))


class TestOverrides:
    def test_the_apply_script_decisions_are_read_without_running_it(self):
        decisions = loader.decisions_from_script()
        assert len(decisions) == loader.MANUAL + loader.NEW
        assert sum(v == "new" for v in decisions.values()) == loader.NEW

    def test_csv_rows_and_decisions_merge_with_their_origin(self):
        csv = pd.DataFrame({"scorer_id": ["a", "b"], "gsis_id": ["G1", "new"], "note": [NOTE, None]})
        out, problems = loader.overrides_from(csv, {"a": "G1", "c": "G3"}, pd.Timestamp("2026-11-07", tz="UTC"))
        assert problems == []
        by = out.set_index("scorer_id")
        assert by["origin"].to_dict() == {"a": "csv", "b": "csv", "c": "apply_script"}
        assert by.loc["a", "note"] == NOTE and pd.isna(by.loc["c", "note"])
        assert list(out.columns) == ["scorer_id", "gsis_id", "note", "recorded_at", "origin"]

    def test_a_disagreement_a_blank_and_a_double_answer_are_problems_by_id(self):
        csv = pd.DataFrame({"scorer_id": ["a", "a", "b", None], "gsis_id": ["G1", "G2", "G9", "G4"],
                            "note": None})
        _, problems = loader.overrides_from(csv, {"b": "G5"}, pd.Timestamp("2026-11-07", tz="UTC"))
        text = "\n".join(problems)
        assert "scorer_id a has two answers" in text
        assert "scorer_id b differs between the CSV and DECISIONS" in text
        assert "1 CSV row(s) with no scorer_id" in text

    def overrides(self):
        csv = pd.DataFrame({"scorer_id": ["a", "b", "n"], "gsis_id": ["G1", "G2", "new"], "note": None})
        return loader.overrides_from(csv, {}, pd.Timestamp("2026-11-07", tz="UTC"))[0]

    def test_overrides_that_match_the_crosswalk_are_clean(self, monkeypatch):
        monkeypatch.setattr(loader, "MANUAL", 2)
        monkeypatch.setattr(loader, "NEW", 1)
        assert loader.crosswalk_problems(self.overrides(), crosswalk([("a", "G1"), ("b", "G2")], ["n"])) == []

    def test_a_mismatch_is_listed_by_count_and_scorer_id(self, monkeypatch):
        monkeypatch.setattr(loader, "MANUAL", 2)
        monkeypatch.setattr(loader, "NEW", 1)
        problems = loader.crosswalk_problems(self.overrides(), crosswalk([("a", "G1"), ("z", "G7")], ["n"]))
        text = "\n".join(problems)
        assert "1 manual row(s), expected 2" not in text and "crosswalk: 2 manual" not in text
        assert "scorer_id b is not a manual row" in text and "scorer_id z is a manual row with no override" in text
        assert crosswalk_has_no_names(problems)
        changed = loader.crosswalk_problems(self.overrides(), crosswalk([("a", "G1"), ("b", "OTHER")], ["n"]))
        assert changed == ["overrides: scorer_id b gsis_id differs from the crosswalk"]


def crosswalk_has_no_names(problems):
    return all("Pat" not in p and "Invented" not in p for p in problems)


class TestLoad:
    @pytest.fixture
    def raw(self, tmp_path, monkeypatch):
        folder = tmp_path / "raw"
        folder.mkdir()
        (folder / "fantrax_draftresults_2026.json").write_text(
            json.dumps(payload(grid(), [scorer(f"s{i:03d}") for i in range(2, 13)])), encoding="utf-8")
        pd.DataFrame({"scorer_id": ["a", "n"], "gsis_id": ["G1", "new"], "note": [NOTE, None],
                      "ignored": ["x", "y"]}).to_csv(folder / loader.OVERRIDES_FILE, index=False)
        for name, value in (("SLOTS", 12), ("MADE", 11), ("UNMADE", 1), ("MANUAL", 1), ("NEW", 1)):
            monkeypatch.setattr(loader, name, value)
        return folder

    def run(self, raw, store, **kw):
        lines = []
        code = loader.load(raw, decisions={}, crosswalk=crosswalk([("a", "G1")], ["n"]),
                           now=pd.Timestamp("2026-11-07", tz="UTC"), out=lines.append, **kw)
        return code, lines

    def test_it_writes_the_three_tables_through_the_seam_and_prints_no_value(self, raw, store):
        code, lines = self.run(raw, store)
        assert code == 0
        assert len(etl.read_table("fact_startup_draft_slot")) == 12
        assert len(etl.read_table("dim_startup_draft_scorer")) == 11
        got = etl.read_table("dim_fantrax_crosswalk_override").set_index("scorer_id")
        assert got["origin"].to_dict() == {"a": "csv", "n": "csv"} and got.loc["a", "note"] == NOTE
        text = "\n".join(lines)
        assert NOTE not in text and TEAM_NAME not in text and "Invented" not in text
        assert [l for l in lines if l.startswith("wrote")] == [
            "wrote dim_startup_draft_scorer: 11 row(s)", "wrote fact_startup_draft_slot: 12 row(s)",
            "wrote dim_fantrax_crosswalk_override: 2 row(s)"]

    def test_check_writes_nothing(self, raw, store):
        code, lines = self.run(raw, store, check_only=True)
        assert code == 0 and not any(etl.table_exists(t) for t in PRIVATE)
        assert "nothing was written (--check)" in lines[-1]

    def test_it_refuses_to_write_over_a_table_that_holds_rows(self, raw, store):
        assert self.run(raw, store)[0] == 0
        before = (store / "fact_startup_draft_slot.parquet").read_bytes()
        code, lines = self.run(raw, store)
        assert code == 1 and "fact_startup_draft_slot already holds rows" in "\n".join(lines)
        assert lines[-1] == "nothing was written"
        assert (store / "fact_startup_draft_slot.parquet").read_bytes() == before

    def test_a_draft_count_off_writes_nothing(self, raw, store, monkeypatch):
        monkeypatch.setattr(loader, "SLOTS", 980)
        code, lines = self.run(raw, store)
        assert code == 1 and not any(etl.table_exists(t) for t in PRIVATE)
        assert "draft: 12 slots, expected 980" in "\n".join(lines)

    def test_an_overrides_mismatch_stops_the_run_by_scorer_id(self, raw, store):
        lines = []
        code = loader.load(raw, decisions={}, crosswalk=crosswalk([("zz", "G1")], ["n"]),
                           now=pd.Timestamp("2026-11-07", tz="UTC"), out=lines.append)
        assert code == 1 and not any(etl.table_exists(t) for t in PRIVATE)
        assert "scorer_id a is not a manual row of the crosswalk" in "\n".join(lines)

    def test_a_missing_capture_or_csv_stops_before_any_read(self, tmp_path, store):
        lines = []
        assert loader.load(tmp_path, decisions={}, crosswalk=crosswalk(), out=lines.append) == 1
        assert len(lines) == 2 and all(l.startswith("stopped") for l in lines)


class TestPrivateTablesStayPrivate:
    registry = yaml.safe_load((REPO / "docs" / "data_model.yml").read_text(encoding="utf-8"))

    def test_they_are_declared_in_the_ops_schema_with_no_chain(self):
        by_name = {t["name"]: t for t in self.registry["tables"]}
        for name in PRIVATE:
            assert by_name[name]["schema"] == "ops" and "chain" not in by_name[name], name

    def test_they_are_in_no_chain_and_not_published(self):
        chained = {t for ts in ec.chain_tables(ec.load_registry()).values() for t in ts}
        assert not chained & set(PRIVATE)
        assert not set(etl.published_names()) & set(PRIVATE)

    def test_the_suite_default_skips_them(self, tmp_path):
        entry = {"name": "a", "grain": "k", "columns": [{"name": "k", "dtype": "int64"}]}
        registry = {"a": entry, "p": {**entry, "name": "p", "schema": "ops"}}
        pd.DataFrame({"k": [1]}).to_parquet(tmp_path / "a.parquet", index=False)
        results = ec.run_suite(registry=registry, data_dir=tmp_path, head_rows=lambda n: None)
        assert {r.table for r in results} == {"a"}

    @pytest.mark.parametrize("name", PRIVATE)
    def test_a_parquet_copy_is_git_ignored(self, name):
        done = subprocess.run(["git", "check-ignore", "-q", f"data/{name}.parquet"], cwd=REPO)
        assert done.returncode == 0

    def test_the_validator_refuses_a_chain_on_a_private_table(self, capsys):
        cdm = importlib.import_module("check_data_model")
        data = {**self.registry, "tables": [
            {**t, "chain": "fantrax_core"} if t["name"] == PRIVATE[0] else t
            for t in self.registry["tables"]]}
        assert cdm.validate(data) == 1
        assert "a private table" in capsys.readouterr().out


class TestGates:
    PLAYERS = pd.DataFrame({"gsis_id": ["G1", "G2"]})
    LINKS = pd.DataFrame({"old_gsis_id": ["OLD"], "new_gsis_id": ["G2"]})

    def overrides(self, *pairs):
        return pd.DataFrame(pairs, columns=["scorer_id", "gsis_id"])

    def test_an_empty_decisions_table_is_a_gate_error_naming_the_loader(self):
        assert "load_draft_and_overrides" in ec.overrides_errors(pd.DataFrame())[0]

    def test_the_overrides_gate_has_no_fixed_count(self):
        # 33 today; #431 adds rows, and one more must not fail the Gate.
        players = pd.DataFrame({"gsis_id": [f"G{i}" for i in range(40)]})
        many = self.overrides(*[(f"s{i}", f"G{i}") for i in range(40)])
        assert ec.overrides_errors(many, players) == []
        assert ec.overrides_errors(pd.concat([many, self.overrides(("extra", "new"))]), players) == []

    def test_new_and_a_registry_id_and_a_linked_old_id_pass(self):
        ok = self.overrides(("a", "G1"), ("b", "new"), ("c", "new"), ("d", "OLD"))
        assert ec.overrides_errors(ok, self.PLAYERS, self.LINKS) == []

    def test_an_id_that_is_neither_registered_nor_new_fails(self):
        bad = self.overrides(("a", "G1"), ("b", "NOWHERE"))
        errs = ec.overrides_errors(bad, self.PLAYERS, self.LINKS)
        assert len(errs) == 1 and "neither in dim_nfl_players nor new" in errs[0]

    def test_a_gsis_id_claimed_by_two_scorers_fails_but_two_new_do_not(self):
        twice = self.overrides(("a", "G1"), ("b", "G1"))
        assert ec.overrides_errors(twice, self.PLAYERS) == ["1 gsis_id(s) are claimed by more than one scorer_id"]

    def test_the_draft_copy_must_hold_980_slots_with_5_unmade(self):
        ok = pd.DataFrame({"scorer_id": [None] * 5 + ["s"] * 975})
        assert ec.draft_copy_errors(ok) == []
        assert len(ec.draft_copy_errors(ok.iloc[:-1])) == 1
        assert len(ec.draft_copy_errors(pd.DataFrame({"scorer_id": ["s"] * 980}))) == 1

    def test_a_store_without_the_private_table_is_not_compared(self, store):
        def load(name):
            return etl.read_stored(name, store)
        with pytest.raises(ec.NotComparable):
            ec.private_table(load, "fact_startup_draft_slot")

    def test_both_checks_are_gates_on_published_tables(self):
        checks = {c.name: c for c in ec.DOMAIN_CHECKS}
        assert (checks["overrides_present"].tier, checks["overrides_present"].table) == ("gate", "dim_fantrax_crosswalk")
        assert (checks["draft_copy"].tier, checks["draft_copy"].table) == ("gate", "fact_draft_pick")


class TestCompareLoaderOutput:
    ENTRY = {"name": "t", "grain": "k", "pk": ["k"],
             "columns": [{"name": "k", "dtype": "int64"}, {"name": "v", "dtype": "str"}]}

    def test_equal_frames_have_nothing_apart(self):
        a = pd.DataFrame({"k": [1, 2], "v": ["x", None]})
        assert compare.compare(a, a.copy(), self.ENTRY) == {
            "live_rows": 2, "new_rows": 2, "only_live": 0, "only_new": 0,
            "differing": 0, "columns_apart": 0}

    def test_keys_and_cells_that_differ_are_counted_not_shown(self):
        live = pd.DataFrame({"k": [1, 2, 3], "v": ["x", "y", "z"]})
        new = pd.DataFrame({"k": [2, 3, 4], "v": ["y", "CHANGED", "w"]})
        got = compare.compare(live, new, self.ENTRY)
        assert (got["only_live"], got["only_new"], got["differing"]) == (1, 1, 1)

    def test_the_report_prints_counts_only_and_reads_the_store_read_only(self, store, monkeypatch):
        reg = {"tables": [{"name": "dim_t", "type": "dim", "grain": "k", "pk": ["k"],
                           "columns": [{"name": "k", "dtype": "int64"}, {"name": "v", "dtype": "str"}]}]}
        path = store / "registry.yml"
        path.write_text(yaml.safe_dump(reg), encoding="utf-8")
        monkeypatch.setattr(etl, "REGISTRY_PATH", path)
        etl.write_table("dim_t", pd.DataFrame({"k": [1, 2], "v": ["SECRETVALUE", "b"]}))
        cap = store / "cap"
        cap.mkdir()
        with etl.capturing(cap):
            etl.write_table("dim_t", pd.DataFrame({"k": [1, 2], "v": ["OTHERVALUE", "b"]}))
        lines = []
        assert compare.report(cap, tables=("dim_t",), out=lines.append) == 1
        text = "\n".join(lines)
        assert "keys with differing cells 1" in text and "VALUE" not in text

    def test_the_comparison_opens_the_store_read_only_and_writes_review_files_elsewhere(self):
        source = (REPO / "scripts" / "compare_loader_output.py").read_text(encoding="utf-8")
        assert "pg.session_read_only()" in source and "etl.capturing(" in source
        assert "run_pipeline" not in source.split('"""', 2)[2]      # no run-log, no review rows


class TestCaptureMode:
    def test_a_capture_applies_every_write_mode_to_a_copy_and_leaves_the_store(self, store, monkeypatch):
        reg = {"tables": [{"name": "dim_t", "type": "dim", "grain": "k", "pk": ["k"],
                           "columns": [{"name": "k", "dtype": "int64"}, {"name": "v", "dtype": "str"}]}]}
        path = store / "registry.yml"
        path.write_text(yaml.safe_dump(reg), encoding="utf-8")
        monkeypatch.setattr(etl, "REGISTRY_PATH", path)
        etl.write_table("dim_t", pd.DataFrame({"k": [1, 2], "v": ["a", "b"]}))
        before = (store / "dim_t.parquet").read_bytes()
        cap = store / "cap"
        cap.mkdir()
        with etl.capturing(cap):
            assert etl.write_table("dim_t", pd.DataFrame({"k": [2, 3], "v": ["B", "c"]}), mode="upsert") == 3
            assert etl.read_table("dim_t")["v"].tolist() == ["a", "B", "c"]       # reads see the capture
            assert etl.read_stored("dim_t")["v"].tolist() == ["a", "b"]           # the store is untouched
        assert (store / "dim_t.parquet").read_bytes() == before
        assert etl.read_table("dim_t")["v"].tolist() == ["a", "b"]                # mode off again

    def test_capture_mode_does_not_nest(self, store):
        with etl.capturing(store):
            with pytest.raises(etl.StorageError):
                with etl.capturing(store):
                    pass


class TestReferencedIdsSkipPrivateTables:
    @pytest.fixture
    def tables(self, store, monkeypatch):
        reg = yaml.safe_load((REPO / "docs" / "data_model.yml").read_text(encoding="utf-8"))
        override = next(t for t in reg["tables"] if t["name"] == "dim_fantrax_crosswalk_override")
        people = {"name": "dim_nfl_players", "type": "dim", "grain": "gsis_id", "pk": ["gsis_id"],
                  "columns": [{"name": "gsis_id", "dtype": "str"}, {"name": "status", "dtype": "str"}]}
        path = store / "registry.yml"
        path.write_text(yaml.safe_dump({"tables": [people, override]}), encoding="utf-8")
        monkeypatch.setattr(etl, "REGISTRY_PATH", path)
        etl.write_table("dim_fantrax_crosswalk_override", pd.DataFrame({
            "scorer_id": ["a", "b"], "gsis_id": ["ONLYOVERRIDE", "new"], "note": [None, None],
            "recorded_at": [pd.Timestamp("2026-11-07", tz="UTC")] * 2, "origin": ["csv", "csv"]}))
        etl.write_table("dim_nfl_players", pd.DataFrame({"gsis_id": ["ONLYOVERRIDE", "FRESH"],
                                                         "status": ["ACT", "ACT"]}))

    def test_new_is_never_a_referenced_id(self, tables):
        assert "new" not in etl.referenced_ids("dim_nfl_players")
        assert etl.referenced_ids("dim_nfl_players") == set()

    def test_a_gsis_id_only_the_overrides_table_holds_is_not_kept(self, tables):
        fresh = pd.DataFrame({"gsis_id": ["FRESH"], "status": ["ACT"]})
        assert etl.keep_dropped_ids("dim_nfl_players", fresh)["gsis_id"].tolist() == ["FRESH"]


class TestTheLoaderWritesAllOrNothing:
    def frames(self):
        scorers = loader.scorers_from_payloads([payload([], [scorer("s1")])])
        slots = loader.slots_from_payloads([payload(grid())])
        overrides, _ = loader.overrides_from(
            pd.DataFrame({"scorer_id": ["a"], "gsis_id": ["G1"], "note": [None]}), {},
            pd.Timestamp("2026-11-07", tz="UTC"))
        return {loader.SCORER_TABLE: scorers, loader.SLOT_TABLE: slots, loader.OVERRIDE_TABLE: overrides}

    def test_a_failure_on_the_last_write_leaves_every_target_empty(self, store, monkeypatch):
        real, calls = etl._write_parquet, []

        def fail_third(*args, **kwargs):
            calls.append(1)
            if len(calls) == 3:
                raise OSError("disk full")
            return real(*args, **kwargs)

        monkeypatch.setattr(etl, "_write_parquet", fail_third)
        with pytest.raises(OSError):
            etl.write_tables_once(self.frames())
        assert not any(etl.table_exists(t) for t in PRIVATE)

    def test_a_table_that_already_holds_rows_refuses_the_whole_write(self, store):
        frames = self.frames()
        etl.write_table(loader.SLOT_TABLE, frames[loader.SLOT_TABLE])
        with pytest.raises(etl.StorageError, match="already hold rows"):
            etl.write_tables_once(frames)
        assert not etl.table_exists(loader.SCORER_TABLE) and not etl.table_exists(loader.OVERRIDE_TABLE)

    def test_a_batch_that_breaks_a_table_writes_nothing(self, store):
        frames = self.frames()
        frames[loader.OVERRIDE_TABLE] = frames[loader.OVERRIDE_TABLE].drop(columns="origin")
        with pytest.raises(etl.StorageError):
            etl.write_tables_once(frames)
        assert not any(etl.table_exists(t) for t in PRIVATE)


class TestOnlyThePrivateTablesAreLoaded:
    def test_02d_names_the_loader_when_the_slot_table_is_empty(self, store):
        with pytest.raises(etl.TableNotFound, match="load_draft_and_overrides"):
            rt.load_draft()


# ---- 04z: the shipped load cell, against stored tables ---------------------------------
def cell(notebook_cell):
    nb = json.loads((REPO / "notebooks" / "04z_fantrax_crosswalk.ipynb").read_text(encoding="utf-8"))
    source = next(c for c in nb["cells"] if c["id"] == notebook_cell)["source"]
    return source if isinstance(source, str) else "".join(source)


class Test04zReadsThePrivateTables:
    ADP = pd.DataFrame({"season": [2026], "week": ["DRAFT"], "scorer_id": ["known"],
                        "player_name": ["Known Person"], "position_raw": ["WR"],
                        "nfl_team": ["DAL"], "is_rookie": [False]})

    @pytest.fixture
    def tables(self, store, monkeypatch):
        reg = yaml.safe_load((REPO / "docs" / "data_model.yml").read_text(encoding="utf-8"))
        keep = {"dim_fantrax_crosswalk_override", "fact_startup_draft_slot",
                "dim_startup_draft_scorer", "dim_player_alias"}
        small = [
            {"name": "fact_fantrax_adp", "type": "fact", "grain": "(season, week, scorer_id)",
             "columns": [{"name": c, "dtype": "int64" if c == "season" else "bool" if c == "is_rookie" else "str"}
                         for c in self.ADP.columns]},
            {"name": "dim_nfl_players", "type": "dim", "grain": "gsis_id",
             "columns": [{"name": c, "dtype": "str"} for c in ("gsis_id", "display_name")]},
            {"name": "dim_rookie_prospect", "type": "dim", "grain": "player_key",
             "columns": [{"name": c, "dtype": "str"} for c in ("player_key", "player_name")]},
        ]
        path = store / "registry.yml"
        path.write_text(yaml.safe_dump({"tables": small + [t for t in reg["tables"] if t["name"] in keep]}),
                        encoding="utf-8")
        monkeypatch.setattr(etl, "REGISTRY_PATH", path)
        etl.write_table("fact_fantrax_adp", self.ADP)
        etl.write_table("dim_nfl_players", pd.DataFrame({"gsis_id": ["G1"], "display_name": ["Known Person"]}))
        etl.write_table("dim_rookie_prospect", pd.DataFrame({"player_key": ["k"], "player_name": ["Zed"]}))
        return store

    def put(self, overrides=True, scorers=True):
        if overrides:
            etl.write_table("dim_fantrax_crosswalk_override", pd.DataFrame({
                "scorer_id": ["m1"], "gsis_id": ["G9"], "note": [None],
                "recorded_at": [pd.Timestamp("2026-11-07", tz="UTC")], "origin": ["csv"]}))
        if scorers:
            etl.write_table("dim_startup_draft_scorer", pd.DataFrame({
                "scorer_id": ["known", "draftonly"], "player_name": ["Known Person", "Draft Only"],
                "position_raw": ["WR", "LB"], "nfl_team": ["DAL", "XYZ"], "is_rookie": [False, True]}))

    def run(self, tables):
        ns = {"pd": pd, "etl": etl, "CFG": etl.CFG, "DATA": tables, "REVIEW": tables, "fuzz": fuzz,
              "process": process, "clean_name_for_match": etl.clean_name_for_match}
        exec(cell("13c9d22d"), ns)
        ns.update(etl=etl, DATA=tables)
        exec(cell("253b3f55"), ns)
        return ns

    def test_overrides_and_draft_only_scorers_come_from_the_tables(self, tables):
        self.put()
        ns = self.run(tables)
        assert ns["overrides"] == {"m1": "G9"}
        assert sorted(ns["fact_latest"]["scorer_id"]) == ["draftonly", "known"]
        row = ns["fact_latest"].set_index("scorer_id").loc["draftonly"]
        assert (row["position_raw"], row["nfl_team"], bool(row["is_rookie"])) == ("LB", "XYZ", True)

    def test_no_data_raw_is_needed(self, tables):
        self.put()
        assert not (tables / "raw").exists()
        self.run(tables)

    def test_empty_overrides_stop_the_run_naming_the_loader(self, tables):
        self.put(overrides=False)
        with pytest.raises(etl.TableNotFound, match="load_draft_and_overrides"):
            self.run(tables)

    def test_no_draft_scorers_stop_the_run_naming_the_loader(self, tables):
        self.put(scorers=False)
        with pytest.raises(etl.TableNotFound, match="load_draft_and_overrides"):
            self.run(tables)

    def test_the_cell_reads_no_raw_override_or_draft_file(self):
        source = cell("253b3f55")
        assert "fantrax_crosswalk_overrides" not in source and "fantrax_draftresults" not in source
        assert "fantrax_txn_history" in source      # the transaction capture stays a same-run read

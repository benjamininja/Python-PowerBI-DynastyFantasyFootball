"""#300 Brief 4: scripts/rekey_gsis_history.py on fixture tables only.

Every case runs the shipped script's main() against a temporary store with its
own registry, through the seam. The script is new, so no test here holds
behaviour that predates it; the tests that guard the existing behaviour it
relies on are tests/test_gsis_link.py (current_gsis, the chain and the loop),
tests/test_writers_apply_link.py and tests/test_etl_storage.py (the seam's
grain check).
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest
import yaml

import etl_helpers as etl

_spec = importlib.util.spec_from_file_location("rekey_gsis_history", REPO / "scripts" / "rekey_gsis_history.py")
rk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rk)

FACT, XW, RANK, PROS = rk.TABLES
OLD, NEW, OLD2, MID, END, LIVE = "OLD1", "NEW1", "OLD2", "MID1", "END1", "LIVE1"
FACT_COLS = ["snapshot_date", "source_name", "source_player_id", "format", "source_uid",
             "gsis_id", "metric_key", "metric_num"]
XW_COLS = ["source", "source_player_id", "gsis_id", "source_uid"]
RANK_COLS = ["player_key", "gsis_id", "source_name", "phase", "draft_year"]


def entry(name, cols, pk, dtypes=None):
    dtypes = dtypes or {}
    return {"name": name, "type": "fact", "grain": ", ".join(pk), "pk": pk,
            "columns": [{"name": c, "dtype": dtypes.get(c, "str")} for c in cols]}


REGISTRY = {"tables": [
    entry("dim_nfl_players", ["gsis_id"], ["gsis_id"]),
    entry(etl.GSIS_LINK_TABLE, etl.GSIS_LINK_COLUMNS, ["old_gsis_id"]),
    entry(FACT, FACT_COLS, ["snapshot_date", "source_name", "source_player_id", "format", "metric_key"],
          {"metric_num": "float64"}),
    entry(XW, XW_COLS, ["source_uid"]),
    entry(RANK, RANK_COLS, ["player_key", "source_name", "phase", "draft_year"], {"draft_year": "Int64"}),
    entry(PROS, ["player_key", "gsis_id"], ["player_key"], {"gsis_id": "object"}),
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


def put_links(*pairs):
    put(etl.GSIS_LINK_TABLE, [(o, n, "smart_id", "2026-11-01") for o, n in pairs], etl.GSIS_LINK_COLUMNS)


def put_players(*ids):
    put("dim_nfl_players", [(i,) for i in ids], ["gsis_id"])


def comp(gsis, metric="m1", snap="2026-10-01", spid=None, uid=None):
    return (snap, "Composite", spid or gsis, "sf", uid or f"Composite|{gsis}", gsis, metric, 1.0)


def ktc(spid, gsis, metric="m1", snap="2026-10-01"):
    return (snap, "KTC", spid, "sf", f"KTC|{spid}", gsis, metric, 2.0)


def put_all(fact_rows, xw_rows=(), rank_rows=(), pros_rows=()):
    put(FACT, fact_rows, FACT_COLS)
    put(XW, xw_rows, XW_COLS)
    put(RANK, rank_rows, RANK_COLS)
    etl.write_table(PROS, pd.DataFrame(pros_rows, columns=["player_key", "gsis_id"]).astype({"gsis_id": object}))


def snapshot(store):
    return {n: (store / f"{n}.parquet").read_bytes() for n in rk.TABLES}


def run(capsys, *args):
    code = rk.main(list(args))
    return code, capsys.readouterr().out


class TestComposite:
    def test_composite_row_is_rewritten_in_all_three_columns(self, store, capsys):
        put_players(NEW, LIVE)
        put_links((OLD, NEW))
        put_all([comp(OLD), comp(LIVE)])
        code, _ = run(capsys)
        out = etl.read_table(FACT)
        assert code == 0
        row = out.iloc[0]
        assert (row["gsis_id"], row["source_player_id"], row["source_uid"]) == (NEW, NEW, f"Composite|{NEW}")
        assert out.iloc[1]["source_uid"] == f"Composite|{LIVE}"

    def test_a_chain_ends_on_the_newest_id_in_all_three_columns(self, store, capsys):
        put_players(END)
        put_links((OLD, MID), (MID, END))
        put_all([comp(OLD)])
        run(capsys)
        row = etl.read_table(FACT).iloc[0]
        assert (row["gsis_id"], row["source_player_id"], row["source_uid"]) == (END, END, f"Composite|{END}")

    def test_other_sources_keep_their_source_ids_and_uid(self, store, capsys):
        put_players(NEW)
        put_links((OLD, NEW))
        put_all([ktc(OLD, OLD)])
        run(capsys)
        row = etl.read_table(FACT).iloc[0]
        assert row["gsis_id"] == NEW
        assert (row["source_player_id"], row["source_uid"]) == (OLD, f"KTC|{OLD}")

    def test_a_composite_uid_without_its_prefix_is_left_alone(self, store, capsys):
        put_players(NEW)
        put_links((OLD, NEW))
        put_all([comp(OLD, uid=OLD)])
        code, _ = run(capsys)
        row = etl.read_table(FACT).iloc[0]
        assert code == 0
        assert (row["gsis_id"], row["source_player_id"], row["source_uid"]) == (NEW, NEW, OLD)


class TestRankingsAndCrosswalks:
    def test_the_crosswalk_rookie_rankings_and_prospects_move_to_the_new_id(self, store, capsys):
        put_players(NEW, LIVE)
        put_links((OLD, NEW))
        put_all([comp(LIVE)],
                xw_rows=[("KTC", "7", OLD, "KTC|7"), ("KTC", "8", LIVE, "KTC|8")],
                rank_rows=[("pk1", OLD, "s1", "pre", 2026), ("pk2", None, "s1", "pre", 2026)],
                pros_rows=[("pk1", OLD), ("pk2", None)])
        run(capsys)
        assert etl.read_table(XW)["gsis_id"].tolist() == [NEW, LIVE]
        assert etl.read_table(RANK)["gsis_id"].tolist()[0] == NEW
        assert pd.isna(etl.read_table(RANK)["gsis_id"].iloc[1])
        assert etl.read_table(PROS)["gsis_id"].tolist()[0] == NEW
        assert pd.isna(etl.read_table(PROS)["gsis_id"].iloc[1])

    def test_only_the_id_columns_change_and_the_rows_stay_in_order(self, store, capsys):
        put_players(NEW, LIVE)
        put_links((OLD, NEW))
        put_all([comp(LIVE, metric="m2"), comp(OLD, metric="m1"), ktc("9", OLD)],
                xw_rows=[("KTC", "7", OLD, "KTC|7")])
        before = {n: etl.read_table(n) for n in (FACT, XW)}
        run(capsys)
        for name, ids in ((FACT, ["gsis_id", "source_player_id", "source_uid"]), (XW, ["gsis_id"])):
            after = etl.read_table(name)
            rest = [c for c in before[name].columns if c not in ids]
            assert list(after.columns) == list(before[name].columns)
            assert len(after) == len(before[name])
            assert after[rest].equals(before[name][rest])

    def test_an_unlinked_id_and_a_null_stay_as_they_are(self, store, capsys):
        put_players(NEW, "STAY1")
        put_links((OLD, NEW))
        put_all([comp("STAY1")], xw_rows=[("KTC", "7", "STAY1", "KTC|7"), ("KTC", "8", None, "KTC|8")])
        code, out = run(capsys)
        assert code == 0
        assert etl.read_table(XW)["gsis_id"].iloc[0] == "STAY1"
        assert pd.isna(etl.read_table(XW)["gsis_id"].iloc[1])
        assert "unchanged, not written" in out


class TestRefusals:
    def test_a_key_collision_writes_nothing_in_any_table(self, store, capsys):
        put_players(NEW)
        put_links((OLD, NEW))
        put_all([comp(OLD), comp(NEW)], xw_rows=[("KTC", "7", OLD, "KTC|7")],
                rank_rows=[("pk1", OLD, "s1", "pre", 2026)], pros_rows=[("pk1", OLD)])
        before = snapshot(store)
        code, out = run(capsys)
        assert code == 1
        assert "REFUSED, nothing written" in out
        assert snapshot(store) == before

    def test_a_link_to_an_id_dim_nfl_players_lacks_writes_nothing(self, store, capsys):
        put_players(LIVE, OLD)
        put_links((OLD, NEW))
        put_all([comp(LIVE)], xw_rows=[("KTC", "7", OLD, "KTC|7")])
        before = snapshot(store)
        code, out = run(capsys)
        assert code == 1
        assert "REFUSED" in out
        assert snapshot(store) == before

    def test_a_link_loop_raises_before_any_write(self, store, capsys):
        put_players(NEW)
        put_links((OLD, NEW), (NEW, OLD))
        put_all([comp(OLD)])
        before = snapshot(store)
        with pytest.raises(ValueError):
            rk.main([])
        assert snapshot(store) == before


class TestRepeatRuns:
    def test_a_second_run_changes_nothing(self, store, capsys):
        put_players(NEW, END)
        put_links((OLD, NEW), (OLD2, MID), (MID, END))
        put_all([comp(OLD), comp(OLD2, metric="m2"), ktc("3", OLD2)],
                xw_rows=[("KTC", "7", OLD, "KTC|7")],
                rank_rows=[("pk1", OLD2, "s1", "pre", 2026)], pros_rows=[("pk1", OLD)])
        first_code, first = run(capsys)
        after_first = snapshot(store)
        second_code, second = run(capsys)
        assert first_code == second_code == 0
        assert "written" in first and "unchanged, not written" not in first
        assert snapshot(store) == after_first
        assert second.count("unchanged, not written") == len(rk.TABLES)
        assert "rows still on an old id 0" in second

    def test_no_link_table_changes_nothing(self, store, capsys):
        put_players(LIVE)
        put_all([comp(LIVE)])
        before = snapshot(store)
        code, out = run(capsys)
        assert code == 0
        assert snapshot(store) == before
        assert out.count("unchanged, not written") == len(rk.TABLES)

    def test_dry_run_reports_and_writes_nothing(self, store, capsys):
        put_players(NEW)
        put_links((OLD, NEW))
        put_all([comp(OLD)])
        before = snapshot(store)
        code, out = run(capsys, "--dry-run")
        assert code == 0
        assert snapshot(store) == before
        assert "would be written (dry run)" in out


class TestOutput:
    def test_it_prints_counts_and_no_id(self, store, capsys):
        put_players(OLD, NEW)
        put_links((OLD, NEW))
        put_all([comp(OLD)], xw_rows=[("KTC", "7", OLD, "KTC|7")])
        _, out = run(capsys)
        assert OLD not in out and NEW not in out
        assert "gsis_id not in dim_nfl_players before 0, after 0" in out

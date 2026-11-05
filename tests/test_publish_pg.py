"""The publish step under ETL_STORAGE=postgres (#136, ADR-0014 decisions 2 and 3):
the Gates read the database, a failed Chain is reloaded from the snapshot at
HEAD, and the passing Chains are exported to data/ for commit_data.

The database cases run against TEST_DATABASE_URL only (the throwaway Postgres
of the storage-pg CI job, reached as etl_writer) and skip without it;
REQUIRE_TEST_DATABASE=1 makes that a failure. Each case builds a throwaway git
repo whose data/ is a copy of the published snapshot, committed as HEAD, and
loads the database from the same snapshot. Nothing reaches the real project:
the conftest autouse fixture removes SUPABASE_DB_URL.
"""
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd
import pytest

import backfill_postgres as backfill
import etl_checks
import etl_helpers as etl
import etl_storage_pg as pg
import run_pipeline as rp
from conftest import git
from test_etl_storage import TABLES, database_url

CHAINS = etl_checks.chain_tables(etl_checks.load_registry())
NEW_ID = "00-0TESTNEW"


@pytest.fixture(scope="module")
def frames():
    return backfill.published_frames()


@pytest.fixture
def db(monkeypatch):
    """The test database with every football table empty, before and after,
    and the seam pointed at it."""
    url = database_url()
    pg.clear_published(url, TABLES)
    monkeypatch.setenv(pg.URL_ENV, url)
    monkeypatch.setenv("ETL_STORAGE", "postgres")
    try:
        yield url
    finally:
        pg.clear_published(url, TABLES)


@pytest.fixture
def world(db, git_repo, frames):
    """A repo whose HEAD holds the published snapshot, and a database holding
    the same rows: the state a run starts from."""
    for table in TABLES:
        shutil.copyfile(REPO / "data" / f"{table}.parquet", git_repo / "data" / f"{table}.parquet")
    git(git_repo, "add", "data")
    git(git_repo, "commit", "-q", "-m", "snapshot")
    assert pg.load_published(db, frames, replace=True).problems == []
    return SimpleNamespace(repo=git_repo, url=db)


def plan_of(passed, failed):
    return {"passed": list(passed), "failed": {c: ["boom"] for c in failed},
            "publish": sorted(t for c in passed for t in CHAINS[c]),
            "restore": sorted(t for c in failed for t in CHAINS[c])}


def stored(table):
    entry = etl._table_entry(table)
    got = pg.read(entry)
    return None if got is None else etl._coerce(got, entry)


def equals_snapshot(table, frames):
    return pg.differences(stored(table), frames[table], etl._table_entry(table)) == []


def drop_first_row(table):
    etl.write_table(table, etl.read_table(table).iloc[1:], mode="replace")


def add_row(table, **changes):
    frame = etl.read_table(table)
    row = frame.iloc[[0]].copy()
    for column, value in changes.items():
        row[column] = value
    etl.write_table(table, pd.concat([frame, row], ignore_index=True), mode="replace")


def changed_at_head(repo):
    return git(repo, "diff", "--name-only", "HEAD").stdout.split()


class TestAFailedChainIsRestoredAndThePassingOneIsExported:
    def test_chain_a_passes_and_chain_b_fails(self, world, frames):
        assert "fact_rookie_rankings" in CHAINS["rookie"]
        assert "fact_dynasty_ranking_metrics" in CHAINS["dynasty_profile"]
        drop_first_row("fact_rookie_rankings")
        drop_first_row("fact_dynasty_ranking_metrics")
        plan = plan_of(["rookie"], ["dynasty_profile"])

        assert rp.publish_postgres(plan, cwd=world.repo) is None

        for table in CHAINS["dynasty_profile"]:
            assert equals_snapshot(table, frames), table
        assert not equals_snapshot("fact_rookie_rankings", frames)
        assert len(stored("fact_rookie_rankings")) == len(frames["fact_rookie_rankings"]) - 1
        assert plan["publish"] == sorted(CHAINS["rookie"]) and plan.get("notes") == []

        exported = etl.read_stored("fact_rookie_rankings", world.repo / "data")
        assert len(exported) == len(frames["fact_rookie_rankings"]) - 1
        assert changed_at_head(world.repo) != []
        assert set(changed_at_head(world.repo)) <= {f"data/{t}.parquet" for t in CHAINS["rookie"]}

        line = rp.commit_data("INSEASON", "8", push=False, publish=plan["publish"],
                              restore=plan["restore"], cwd=world.repo)
        assert line.startswith("committed") and "push skipped" in line
        staged = git(world.repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
        assert "data/fact_rookie_rankings.parquet" in staged
        assert set(staged) <= {f"data/{t}.parquet" for t in CHAINS["rookie"]}
        assert changed_at_head(world.repo) == []

    def test_a_reload_refused_by_a_foreign_key_reloads_every_written_table_and_publishes_nothing(
            self, world, frames):
        add_row("dim_nfl_players", gsis_id=NEW_ID)
        add_row("fact_rookie_rankings", gsis_id=NEW_ID, player_key="test-key")
        plan = plan_of(["rookie"], ["nflverse"])

        assert rp.publish_postgres(plan, cwd=world.repo) is None

        for table in set(CHAINS["nflverse"]) | set(CHAINS["rookie"]):
            assert equals_snapshot(table, frames), table
        assert plan["publish"] == []
        assert len(plan["notes"]) == 1 and "nothing published" in plan["notes"][0]
        assert "FOREIGN KEY" in plan["notes"][0] and NEW_ID not in plan["notes"][0]
        assert changed_at_head(world.repo) == []
        line = rp.commit_data("INSEASON", "8", push=False, publish=plan["publish"],
                              restore=plan["restore"], cwd=world.repo)
        assert line == "no data changes — commit skipped"

    def test_a_reload_refused_twice_aborts_with_the_first_line_and_publishes_nothing(
            self, world, frames):
        add_row("dim_nfl_players", gsis_id=NEW_ID)
        add_row("fact_rookie_rankings", gsis_id=NEW_ID, player_key="test-key")
        add_row("fact_dynasty_ranking_metrics", gsis_id=NEW_ID, source_player_id="test-sp")
        plan = plan_of(["rookie"], ["nflverse"])

        line = rp.publish_postgres(plan, cwd=world.repo)

        assert line.startswith("ABORTED: reload from the snapshot refused: FOREIGN KEY ")
        assert "\n" not in line and NEW_ID not in line and "test-sp" not in line
        assert plan["publish"] == []
        assert len(stored("dim_nfl_players")) == len(frames["dim_nfl_players"]) + 1
        assert changed_at_head(world.repo) == []

    def test_a_snapshot_that_is_not_at_head_is_not_reloaded_from(self, world):
        shutil.copyfile(REPO / "data" / "dim_season.parquet", world.repo / "data" / "dim_nfl_teams.parquet")
        plan = plan_of(["rookie"], ["nflverse"])
        plan["restore"] = ["dim_nfl_teams"]
        drop_first_row("fact_rookie_rankings")
        before = len(stored("fact_rookie_rankings"))

        line = rp.publish_postgres(plan, cwd=world.repo)

        assert line.startswith("ABORTED: 1 file(s) under data/ differ from HEAD")
        assert plan["publish"] == []
        assert len(stored("fact_rookie_rankings")) == before


class TestTheExport:
    def test_an_export_of_unchanged_tables_gives_no_data_diff(self, world, frames):
        plan = {"passed": [], "failed": {}, "publish": list(TABLES), "restore": []}

        assert rp.publish_postgres(plan, cwd=world.repo) is None

        for table in TABLES:
            entry = etl._table_entry(table)
            exported = etl.read_stored(table, world.repo / "data")
            snapshot = frames[table]
            assert list(exported.columns) == list(snapshot.columns), table
            assert exported.dtypes.astype(str).to_dict() == snapshot.dtypes.astype(str).to_dict(), table
            pd.testing.assert_frame_equal(pg.prepared(exported, entry), pg.prepared(snapshot, entry),
                                          check_exact=True, obj=table)
            in_order = exported.sort_values(etl.table_grain(entry), kind="stable").reset_index(drop=True)
            pd.testing.assert_frame_equal(exported, in_order, obj=f"{table} in pk order")

    def test_a_table_the_database_holds_empty_is_exported_as_an_empty_file(self, world, frames):
        pg.clear_published(world.url, ["fact_matchup"])
        plan = {"passed": [], "failed": {}, "publish": ["fact_matchup"], "restore": []}
        assert rp.publish_postgres(plan, cwd=world.repo) is None
        exported = etl.read_stored("fact_matchup", world.repo / "data")
        assert len(exported) == 0 and list(exported.columns) == list(frames["fact_matchup"].columns)

    def test_a_failed_export_reloads_the_database_and_aborts(self, world, frames, monkeypatch):
        drop_first_row("fact_rookie_rankings")

        def refuse(names, data_dir):
            raise RuntimeError("cannot write 'secret-cell'")

        monkeypatch.setattr(pg, "export_published", refuse)
        plan = plan_of(["rookie"], [])
        line = rp.publish_postgres(plan, cwd=world.repo)
        assert line == "ABORTED: export failed: RuntimeError: cannot write <quoted>"
        assert plan["publish"] == []
        assert equals_snapshot("fact_rookie_rankings", frames)


class TestTheGatesReadTheDatabase:
    def test_read_stored_reads_the_database_without_a_data_dir_and_a_folder_with_one(self, world, frames):
        entry = etl._table_entry("dim_season")
        assert pg.differences(etl.read_stored("dim_season"), frames["dim_season"], entry) == []
        drop_first_row("fact_rookie_rankings")
        assert len(etl.read_stored("fact_rookie_rankings")) == len(frames["fact_rookie_rankings"]) - 1
        assert len(etl.read_stored("fact_rookie_rankings", world.repo / "data")) == len(frames["fact_rookie_rankings"])

    def test_an_empty_table_reads_as_an_empty_frame_with_the_registry_columns(self, db):
        entry = etl._table_entry("fact_matchup")
        got = etl.read_stored("fact_matchup")
        assert len(got) == 0 and list(got.columns) == [c["name"] for c in entry["columns"]]

    def test_the_suite_reads_the_database_when_data_dir_is_none(self, world, frames):
        assert len(frames["fact_matchup"]) > 0
        pg.clear_published(world.url, ["fact_matchup"])
        head_rows = lambda name: len(frames[name])

        from_database = etl_checks.run_suite(["fact_matchup"], data_dir=None, head_rows=head_rows)
        from_folder = etl_checks.run_suite(["fact_matchup"], data_dir=world.repo / "data", head_rows=head_rows)

        assert [r.check for r in from_database if r.check == "shrink" and not r.ok] == ["shrink"]
        assert all(r.ok for r in from_folder if r.check in ("schema", "grain", "shrink"))


class TestWithoutADatabase:
    def test_the_parquet_backend_reads_the_folder_as_before(self, tmp_path):
        pd.DataFrame({"a": [3, 1, 2]}).to_parquet(tmp_path / "t.parquet", index=False)
        got = etl.read_stored("t", tmp_path)
        assert got["a"].tolist() == [3, 1, 2]

    def test_a_data_dir_still_reads_parquet_under_postgres_with_no_url(self, monkeypatch):
        monkeypatch.setenv("ETL_STORAGE", "postgres")
        got = etl.read_stored("dim_season", REPO / "data")
        assert len(got) == len(pd.read_parquet(REPO / "data" / "dim_season.parquet"))

    def test_storage_is_postgres_only_when_asked(self, monkeypatch):
        assert rp.storage_is_postgres() is False
        monkeypatch.setenv("ETL_STORAGE", "parquet")
        assert rp.storage_is_postgres() is False
        monkeypatch.setenv("ETL_STORAGE", "postgres")
        assert rp.storage_is_postgres() is True

    def test_no_url_aborts_and_publishes_nothing(self):
        plan = plan_of(["rookie"], ["nflverse"])
        line = rp.publish_postgres(plan)
        assert line.startswith("ABORTED: reload from the snapshot failed: RuntimeError: SUPABASE_DB_URL is not set")
        assert plan["publish"] == []

    def test_load_published_does_not_replace_unless_asked(self):
        import inspect
        assert inspect.signature(pg.load_published).parameters["replace"].default is False

    @pytest.mark.parametrize("storage, kwargs, publishes", [
        ("postgres", {"data_dir": None}, True),
        ("parquet", {}, False),
    ])
    def test_main_wires_the_gates_and_the_publish_step(self, monkeypatch, tmp_path, storage, kwargs, publishes):
        seen = {}
        step = {"name": "s_rookie", "cmd": [], "phases": {"INSEASON"}, "needs": [],
                "chain": "rookie", "group": "rookie"}
        monkeypatch.setenv("ETL_STORAGE", storage)
        monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--phase", "INSEASON", "--no-push"])
        monkeypatch.setattr(rp, "_load_04a", lambda: SimpleNamespace(derive_week_label=lambda cfg: "8", CFG=None))
        monkeypatch.setattr(rp, "build_steps", lambda profile: [step])
        monkeypatch.setattr(rp, "run_steps", lambda *a, **k: [{"name": "s_rookie", "status": "ok", "detail": ""}])
        monkeypatch.setattr(rp.etl_checks, "run_suite", lambda tables, shrink, **kw: seen.update(kw=kw) or [])
        monkeypatch.setattr(rp.etl_checks, "file_review",
                            lambda *a, **k: {"open": 0, "opened": 0, "cleared": 0, "repeated": 0})
        monkeypatch.setattr(rp, "publish_postgres", lambda plan: seen.update(plan=dict(plan)))
        monkeypatch.setattr(rp, "commit_data", lambda *a, **k: "no data changes — commit skipped")
        monkeypatch.setattr(rp, "notify", lambda text: None)
        monkeypatch.setattr(rp, "review_counts", lambda: {})
        monkeypatch.setattr(rp, "OUT_DIR", tmp_path)

        assert rp.main() == 0

        assert seen["kw"] == kwargs
        assert ("plan" in seen) is publishes
        if publishes:
            assert seen["plan"]["publish"] == sorted(CHAINS["rookie"])

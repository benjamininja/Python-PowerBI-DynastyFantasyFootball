"""migrate.yml holds a destructive migration on a push (#534, ADR-0018 decision 12).

On a push to main the push job reads the applied versions, then
`scripts/migration_gate.py` takes the first pending migration holding DROP
COLUMN or DROP TABLE, and every pending one after it, out of the checkout
before `supabase db push`, and the job fails naming it. A run by
`workflow_dispatch` (the owner's Action) skips the gate and applies everything.
No case connects to a database.
"""
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import migration_gate as mg

WORKFLOW = REPO / ".github" / "workflows" / "migrate.yml"
SHA = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")

ORDINARY = "-- registry_state sha256: x\n\nALTER TABLE football.t ADD COLUMN c text;\n"
WIDENING = ("-- registry_state sha256: x\n\nALTER TABLE ops.r DROP CONSTRAINT r_chk_1;\n\n"
            "ALTER TABLE ops.r ADD CONSTRAINT r_chk_2 CHECK (s IN ('a', 'b'));\n")
COLUMN_DROP = "-- registry_state sha256: x\n\nALTER TABLE football.t DROP COLUMN c;\n"
TABLE_DROP = "-- registry_state sha256: x\n\nDROP TABLE football.t;\n"

HELD_FORMS = {
    "drop column": COLUMN_DROP,
    "drop table": TABLE_DROP,
    "lower case": "alter table football.t drop column c;",
    "drop without COLUMN": "ALTER TABLE football.t DROP c;",
    "alter table if exists": "ALTER TABLE IF EXISTS football.t DROP COLUMN c;",
    "alter table only": "ALTER TABLE ONLY football.t DROP COLUMN c;",
    "drop table if exists": "DROP TABLE IF EXISTS football.t;",
    "multi-action drop": "ALTER TABLE football.t ADD COLUMN a integer, DROP COLUMN b;",
    "drop after another statement on one line": "SELECT 1; DROP TABLE football.t;",
    "drop across lines": "ALTER TABLE football.t\n    DROP\n    COLUMN c;",
    "drop schema": "DROP SCHEMA archive;",
    "drop type": "DROP TYPE football.kind;",
    "drop function": "DROP FUNCTION shared.pii_token_hashes();",
    "drop index": "DROP INDEX football.t_c_idx;",
    "drop policy": "DROP POLICY etl_writer_all ON football.t;",
    "lone drop constraint": "ALTER TABLE ops.r DROP CONSTRAINT r_chk_1;",
    "drop constraint then add on another table": (
        "ALTER TABLE ops.r DROP CONSTRAINT r_chk_1;\n"
        "ALTER TABLE ops.s ADD CONSTRAINT s_chk_2 CHECK (s IN ('a'));"),
    "drop constraint then a non-check add": (
        "ALTER TABLE ops.r DROP CONSTRAINT r_pkey;\n"
        "ALTER TABLE ops.r ADD CONSTRAINT r_pkey PRIMARY KEY (a);"),
    "drop constraint not directly followed": (
        "ALTER TABLE ops.r DROP CONSTRAINT r_chk_1;\nSELECT 1;\n"
        "ALTER TABLE ops.r ADD CONSTRAINT r_chk_2 CHECK (s IN ('a'));"),
    "drop constraint if exists": (
        "ALTER TABLE ops.r DROP CONSTRAINT IF EXISTS r_chk_1;\n"
        "ALTER TABLE ops.r ADD CONSTRAINT r_chk_2 CHECK (s IN ('a'));"),
    "truncate": "TRUNCATE football.t;",
    "truncate table": "truncate table football.t restart identity;",
    "delete": "DELETE FROM football.t WHERE a = 1;",
    "delete in a cte": "WITH gone AS (DELETE FROM football.t RETURNING *) SELECT count(*) FROM gone;",
    "rename table": "ALTER TABLE football.t RENAME TO u;",
    "rename column": "ALTER TABLE football.t RENAME COLUMN a TO b;",
    "alter column type": "ALTER TABLE football.t ALTER COLUMN a TYPE integer;",
    "alter column set data type": "ALTER TABLE football.t ALTER COLUMN a SET DATA TYPE text;",
    "alter without COLUMN type": "ALTER TABLE football.t ALTER a TYPE integer USING a::integer;",
    "alter quoted column type": 'ALTER TABLE football.t ALTER COLUMN "a b" TYPE integer;',
    "alter type": "ALTER TYPE football.kind RENAME VALUE 'a' TO 'b';",
    "drop inside a dollar body": "DO $do$ BEGIN EXECUTE 'DROP TABLE football.t'; END $do$;",
    "drop after a comment on the same line": "/* note */ DROP TABLE football.t;",
    "drop after a quoted dashes string": "SELECT '--'; DROP TABLE football.t;",
}

PASSED_FORMS = {
    "ordinary": ORDINARY,
    "the #443 widening pair": WIDENING,
    "two widening pairs": (
        "ALTER TABLE ops.r DROP CONSTRAINT r_chk_1;\n\n"
        "ALTER TABLE ops.r ADD CONSTRAINT r_chk_2 CHECK (s IN ('a', 'b'));\n\n"
        "ALTER TABLE ops.q DROP CONSTRAINT q_chk_1;\n\n"
        "ALTER TABLE ops.q ADD CONSTRAINT q_chk_2 CHECK (t IN (1, 2));\n"),
    "a grant naming delete": "GRANT SELECT, INSERT, UPDATE, DELETE ON football.t TO etl_writer;",
    "drop only in a comment": "-- DROP TABLE football.t\nALTER TABLE football.t ADD COLUMN c text;",
    "drop only in a block comment": "/* DROP TABLE x; */ CREATE INDEX t_c_idx ON football.t (c);",
    "a word that starts with drop": "ALTER TABLE football.t ADD COLUMN dropped_at timestamptz;",
}


def folder(tmp_path, **files):
    out = tmp_path / "migrations"
    out.mkdir()
    for name, sql in files.items():
        (out / f"{name}.sql").write_text(sql, encoding="utf-8")
    return out


def gate(tmp_path, out, applied, capsys, remove=True):
    applied_file = tmp_path / "applied.txt"
    applied_file.write_text("".join(f"{v}\n" for v in applied), encoding="utf-8")
    args = ["--applied", str(applied_file), "--migrations", str(out)] + (["--remove"] if remove else [])
    assert mg.main(args) == 0
    return capsys.readouterr()


def names(out):
    return sorted(p.name for p in out.glob("*.sql"))


class TestTheGate:
    def test_a_pending_column_drop_is_held_on_push(self, tmp_path, capsys):
        out = folder(tmp_path, **{"20261101000000_a": ORDINARY, "20261102000000_drop": COLUMN_DROP,
                                  "20261103000000_b": ORDINARY})
        result = gate(tmp_path, out, ["20261101000000"], capsys)
        assert result.out == "held=20261102000000_drop.sql\n"
        assert "20261102000000_drop.sql" in result.err and "20261103000000_b.sql" in result.err
        assert names(out) == ["20261101000000_a.sql"]

    def test_a_pending_table_drop_is_held_and_the_ordinary_ones_before_it_stay(self, tmp_path, capsys):
        out = folder(tmp_path, **{"20261101000000_a": ORDINARY, "20261102000000_b": ORDINARY,
                                  "20261103000000_drop": TABLE_DROP})
        result = gate(tmp_path, out, ["20261101000000"], capsys)
        assert result.out == "held=20261103000000_drop.sql\n"
        assert names(out) == ["20261101000000_a.sql", "20261102000000_b.sql"]

    def test_an_applied_drop_is_not_held(self, tmp_path, capsys):
        out = folder(tmp_path, **{"20261101000000_drop": COLUMN_DROP, "20261102000000_b": ORDINARY})
        result = gate(tmp_path, out, ["20261101000000"], capsys)
        assert result.out == "held=\n"
        assert names(out) == ["20261101000000_drop.sql", "20261102000000_b.sql"]

    def test_ordinary_migrations_and_a_check_widening_are_not_held(self, tmp_path, capsys):
        out = folder(tmp_path, **{"20261101000000_a": ORDINARY, "20261102000000_w": WIDENING})
        assert gate(tmp_path, out, [], capsys).out == "held=\n"
        assert len(names(out)) == 2

    def test_without_remove_nothing_is_deleted(self, tmp_path, capsys):
        out = folder(tmp_path, **{"20261101000000_drop": COLUMN_DROP})
        assert gate(tmp_path, out, [], capsys, remove=False).out == "held=20261101000000_drop.sql\n"
        assert names(out) == ["20261101000000_drop.sql"]

    def test_the_first_pending_drop_holds_a_later_one_too(self, tmp_path, capsys):
        out = folder(tmp_path, **{"20261101000000_d1": TABLE_DROP, "20261102000000_d2": COLUMN_DROP})
        assert gate(tmp_path, out, [], capsys).out == "held=20261101000000_d1.sql\n"
        assert names(out) == []

    @pytest.mark.parametrize("sql", HELD_FORMS.values(), ids=list(HELD_FORMS))
    def test_a_destructive_form_is_held(self, sql):
        assert mg.is_destructive(sql), sql

    @pytest.mark.parametrize("sql", PASSED_FORMS.values(), ids=list(PASSED_FORMS))
    def test_a_safe_form_passes(self, sql):
        assert not mg.is_destructive(sql), mg.destructive(sql)

    def test_a_held_form_in_a_pending_file_holds_it_on_push(self, tmp_path, capsys):
        out = folder(tmp_path, **{"20261101000000_a": ORDINARY,
                                  "20261102000000_hand": HELD_FORMS["multi-action drop"]})
        assert gate(tmp_path, out, [], capsys).out == "held=20261102000000_hand.sql\n"

    def test_statements_strip_comments_and_keep_quotes_whole(self):
        sql = "SELECT 'a;--b' /* x; DROP */ ; -- DROP TABLE t;\nSELECT $f$ ; $f$ ;"
        assert mg.statements(sql) == ["SELECT 'a;--b'", "SELECT $f$ ; $f$"]

    def test_the_generator_drop_lines_are_destructive(self):
        import generate_migrations as gm
        changes = {k: [] for k in ("schemas", "roles", "tables", "columns", "check_swaps", "checks",
                                   "fks", "indexes", "functions", "column_drops", "table_drops")}
        changes["column_drops"] = [("football.t", "c")]
        assert mg.is_destructive(gm.render(changes))
        changes["column_drops"], changes["table_drops"] = [], ["football.t"]
        assert mg.is_destructive(gm.render(changes))

    def test_no_committed_migration_is_held_today(self, tmp_path, capsys):
        assert not any(mg.is_destructive(p.read_text(encoding="utf-8"))
                       for p in (REPO / "supabase" / "migrations").glob("*.sql"))


def _load():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _on(wf):
    return wf.get("on", wf.get(True))


def _push_steps():
    return _load()["jobs"]["push"]["steps"]


def _step(name):
    return next(s for s in _push_steps() if s.get("name") == name)


class TestTheWorkflow:
    def test_it_starts_on_a_pr_a_push_to_main_or_by_hand(self):
        on = _on(_load())
        assert set(on) == {"pull_request", "push", "workflow_dispatch"}
        assert on["push"]["branches"] == ["main"]
        assert on["workflow_dispatch"] is None

    def test_a_change_to_the_gate_runs_the_workflow(self):
        on = _on(_load())
        assert "scripts/migration_gate.py" in on["pull_request"]["paths"]
        assert "scripts/migration_gate.py" in on["push"]["paths"]

    def test_the_push_job_runs_from_main_only(self):
        assert _load()["jobs"]["push"]["if"] == (
            "(github.event_name == 'push' || github.event_name == 'workflow_dispatch') "
            "&& github.ref == 'refs/heads/main'")

    def test_the_gate_runs_on_a_push_only_and_before_the_push(self):
        steps = [s.get("name") for s in _push_steps()]
        gate_at = steps.index("Hold a destructive migration for the owner's dispatch")
        push_at = steps.index("Push the migrations to the real project")
        stop_at = steps.index("Stop at the held migration")
        assert gate_at < push_at < stop_at
        gate_step = _step("Hold a destructive migration for the owner's dispatch")
        assert gate_step["if"] == "github.event_name == 'push'"
        assert gate_step["id"] == "gate"
        assert "scripts/migration_gate.py" in gate_step["run"] and "--remove" in gate_step["run"]
        assert "supabase_migrations.schema_migrations" in gate_step["run"]
        assert "ON_ERROR_STOP=1" in gate_step["run"]

    def test_a_dispatch_skips_the_gate_and_pushes_everything(self):
        push = _step("Push the migrations to the real project")
        assert "if" not in push
        assert push["run"] == 'supabase db push --yes --db-url "$SUPABASE_MIGRATE_DB_URL"'

    def test_a_held_migration_fails_the_job_by_name(self):
        stop = _step("Stop at the held migration")
        assert stop["if"] == "steps.gate.outputs.held != ''"
        assert stop["env"] == {"HELD": "${{ steps.gate.outputs.held }}"}
        assert "exit 1" in stop["run"] and "$HELD" in stop["run"]

    def test_no_expression_is_inside_a_run_line(self):
        for job in _load()["jobs"].values():
            for step in job["steps"]:
                if "run" in step:
                    assert "${{" not in step["run"], step["run"]

    def test_it_names_one_secret_and_keeps_its_permissions(self):
        wf = _load()
        text = WORKFLOW.read_text(encoding="utf-8")
        assert set(re.findall(r"secrets\.(\w+)", text)) == {"SUPABASE_MIGRATE_DB_URL"}
        assert wf["permissions"] == {"contents": "read"}
        push = wf["jobs"]["push"]
        assert push["environment"] == "etl"
        assert push["concurrency"] == {"group": "migrate-push", "cancel-in-progress": False}

    def test_every_action_is_pinned_or_first_party(self):
        for job in _load()["jobs"].values():
            for step in job["steps"]:
                uses = step.get("uses")
                if uses and not uses.startswith("actions/"):
                    assert SHA.match(uses.split(" ")[0]), uses

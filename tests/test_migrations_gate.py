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
R1, R2 = "r_chk_0123abcd", "r_chk_89abcdef"
WIDENING = (f"-- registry_state sha256: x\n\nALTER TABLE ops.r DROP CONSTRAINT {R1};\n\n"
            f"ALTER TABLE ops.r ADD CONSTRAINT {R2} CHECK (s IN ('a', 'b'));\n")
ADD_R2 = f"ALTER TABLE ops.r ADD CONSTRAINT {R2} CHECK (s IN ('a'));"
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
    "a check dropped with none added": f"ALTER TABLE ops.r DROP CONSTRAINT {R1};",
    "a check dropped then an ordinary statement": (
        f"ALTER TABLE ops.r DROP CONSTRAINT {R1};\nALTER TABLE ops.r ADD COLUMN z text;"),
    "a pair across tables": (
        f"ALTER TABLE ops.r DROP CONSTRAINT {R1};\n"
        "ALTER TABLE ops.s ADD CONSTRAINT s_chk_12345678 CHECK (s IN ('a'));"),
    "a primary key dropped then a check added": f"ALTER TABLE ops.r DROP CONSTRAINT r_pkey;\n{ADD_R2}",
    "a foreign key dropped then a check added": (
        f"ALTER TABLE ops.r DROP CONSTRAINT r_team_key_fkey;\n{ADD_R2}"),
    "a unique constraint dropped then a check added": (
        f"ALTER TABLE ops.r DROP CONSTRAINT r_a_key;\n{ADD_R2}"),
    "a primary key swapped for a primary key": (
        "ALTER TABLE ops.r DROP CONSTRAINT r_pkey;\n"
        "ALTER TABLE ops.r ADD CONSTRAINT r_pkey PRIMARY KEY (a);"),
    "another table's check name dropped": (
        f"ALTER TABLE ops.r DROP CONSTRAINT s_chk_0123abcd;\n{ADD_R2}"),
    "a check name with a longer prefix": (
        f"ALTER TABLE ops.r DROP CONSTRAINT xr_chk_0123abcd;\n{ADD_R2}"),
    "a check name with seven hex": f"ALTER TABLE ops.r DROP CONSTRAINT r_chk_0123abc;\n{ADD_R2}",
    "a check name with a non-hex": f"ALTER TABLE ops.r DROP CONSTRAINT r_chk_0123abcg;\n{ADD_R2}",
    "an added check with a non-generator name": (
        f"ALTER TABLE ops.r DROP CONSTRAINT {R1};\n"
        "ALTER TABLE ops.r ADD CONSTRAINT r_status CHECK (s IN ('a'));"),
    "a check dropped not directly followed": (
        f"ALTER TABLE ops.r DROP CONSTRAINT {R1};\nSELECT 1;\n{ADD_R2}"),
    "a check dropped if exists": f"ALTER TABLE ops.r DROP CONSTRAINT IF EXISTS {R1};\n{ADD_R2}",
    "a check dropped with cascade": f"ALTER TABLE ops.r DROP CONSTRAINT {R1} CASCADE;\n{ADD_R2}",
    "truncate": "TRUNCATE football.t;",
    "truncate table": "truncate table football.t restart identity;",
    "delete": "DELETE FROM football.t WHERE a = 1;",
    "delete from only": "delete  from\n only football.t;",
    "delete in a cte": "WITH gone AS (DELETE FROM football.t RETURNING *) SELECT count(*) FROM gone;",
    "rename table": "ALTER TABLE football.t RENAME TO u;",
    "rename column": "ALTER TABLE football.t RENAME COLUMN a TO b;",
    "alter column type": "ALTER TABLE football.t ALTER COLUMN a TYPE integer;",
    "alter column set data type": "ALTER TABLE football.t ALTER COLUMN a SET DATA TYPE text;",
    "alter without COLUMN type": "ALTER TABLE football.t ALTER a TYPE integer USING a::integer;",
    "alter quoted column type": 'ALTER TABLE football.t ALTER COLUMN "a b" TYPE integer;',
    "alter type": "ALTER TYPE football.kind RENAME VALUE 'a' TO 'b';",
    "merge with delete": ("MERGE INTO football.t USING football.u ON t.a = u.a "
                          "WHEN MATCHED THEN DELETE;"),
    "merge with update": ("merge into football.t t using football.u u on t.a = u.a "
                          "when matched then update set b = u.b;"),
    "update": "UPDATE football.t SET a = NULL;",
    "update only": "update only football.t set a = 1 where b = 2;",
    "update with an alias": "UPDATE football.t AS x SET a = 1;",
    "update with a bare alias": "UPDATE football.t x SET a = 1;",
    "update across lines": "UPDATE football.t\n   SET a = NULL;",
    "update of a quoted name with no space": 'UPDATE"t" SET a=1;',
    "update of a quoted name touching SET": 'UPDATE football."t"SET a=1;',
    "update only of a quoted name": 'UPDATE ONLY"t"SET a=1;',
    "update with a quoted alias touching SET": 'UPDATE football.t AS"x"SET a=1;',
    "update of a starred table": "UPDATE football.t* SET a=1;",
    "an escape string hiding a drop": "SELECT E'a\\'-- '; DROP TABLE football.t; --';",
    "a lower-case escape string hiding a drop": "SELECT e'a\\'/* '; DROP TABLE football.t; -- */';",
    "a plain string with a backslash": "SELECT 'a\\';",
    "an escape string with a backslash": "SELECT E'line\\n';",
    "a non-ascii dollar tag hiding a drop behind --": "SELECT $é$ -- $é$; DROP TABLE football.t;",
    "a non-ascii dollar tag hiding a drop behind /*": "SELECT $é$ /* $é$; DROP TABLE football.t; -- */",
    "a lone dollar": "SELECT $ ;",
    "an unterminated dollar body": "SELECT $f$ never closed;",
    "a dollar after an identifier": "SELECT a$b FROM football.t;",
    "an identifier ending in $$ hiding a drop": "SELECT 1 AS x$$; DROP TABLE football.t; SELECT 1 AS y$$;",
    "an identifier ending in a tag hiding a drop": (
        "SELECT 1 AS x$f$; DROP TABLE football.t; SELECT 1 AS y$f$;"),
    "a dollar after a non-ascii letter": "SELECT 1 AS é$$; SELECT 2 AS z$$;",
    "a dollar after a digit": "SELECT 1 AS a1$$; SELECT 2 AS b$$;",
    "update in a cte": "WITH u AS (UPDATE football.t SET a = 1 RETURNING *) SELECT 1;",
    "detach partition": "ALTER TABLE football.t DETACH PARTITION football.t_2026;",
    "set schema": "ALTER TABLE football.t SET SCHEMA archive;",
    "a digit dollar tag keeps its body whole": (
        "DO $a1$ BEGIN PERFORM 1; END $a1$;\nDROP TABLE football.t;"),
    "drop inside a dollar body": "DO $do$ BEGIN EXECUTE 'DROP TABLE football.t'; END $do$;",
    "drop after a comment on the same line": "/* note */ DROP TABLE football.t;",
    "drop after a quoted dashes string": "SELECT '--'; DROP TABLE football.t;",
}

PASSED_FORMS = {
    "ordinary": ORDINARY,
    "the #443 widening pair": WIDENING,
    "two widening pairs": (
        f"ALTER TABLE ops.r DROP CONSTRAINT {R1};\n\n"
        f"ALTER TABLE ops.r ADD CONSTRAINT {R2} CHECK (s IN ('a', 'b'));\n\n"
        "ALTER TABLE ops.q DROP CONSTRAINT q_chk_00000001;\n\n"
        "ALTER TABLE ops.q ADD CONSTRAINT q_chk_ffffffff CHECK (t IN (1, 2));\n"),
    "a widening on an unqualified table": (
        f"ALTER TABLE r DROP CONSTRAINT {R1};\n{ADD_R2.replace('ops.r', 'r')}"),
    "a grant naming delete": "GRANT SELECT, INSERT, UPDATE, DELETE ON football.t TO etl_writer;",
    "a revoke": "REVOKE EXECUTE ON FUNCTION shared.pii_token_hashes() FROM PUBLIC;",
    "a revoke of table rights": "REVOKE UPDATE, DELETE ON football.t FROM etl_reader;",
    "a policy for update": "CREATE POLICY p ON football.t FOR UPDATE TO etl_writer USING (true);",
    "a select for update": "SELECT a FROM football.t FOR UPDATE;",
    "a foreign key on update cascade": (
        "ALTER TABLE football.t ADD CONSTRAINT t_a_fkey FOREIGN KEY (a) "
        "REFERENCES football.u (a) ON UPDATE CASCADE;"),
    "a column named updated_at": "ALTER TABLE football.t ADD COLUMN updated_at timestamptz;",
    "a positional parameter": (
        "CREATE FUNCTION f(int) RETURNS int LANGUAGE sql AS $f$ SELECT $1 $f$;\nSELECT 1 WHERE $1 = 2;"),
    "an empty dollar tag": "CREATE FUNCTION f() RETURNS int LANGUAGE sql AS $$ SELECT 1 $$;",
    "a function with a digit dollar tag": (
        "CREATE FUNCTION f() RETURNS int LANGUAGE sql AS $f1$ SELECT 1; SELECT 2 $f1$;"),
    "drop only in a comment": "-- DROP TABLE football.t\nALTER TABLE football.t ADD COLUMN c text;",
    "drop only in a block comment": "/* DROP TABLE x; */ CREATE INDEX t_c_idx ON football.t (c);",
    "a word that starts with drop": "ALTER TABLE football.t ADD COLUMN dropped_at timestamptz;",
}


def _registry_with_check(check):
    return {"tables": [], "other_tables": [
        {"name": "run_log", "schema": "ops", "pk": ["run_id"],
         "columns": [{"name": "run_id", "sql_type": "uuid"}, {"name": "status", "sql_type": "text"}],
         "checks": [check]}]}


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

    def test_the_generator_real_widening_output_passes(self):
        import generate_migrations as gm
        old = gm.desired_model(_registry_with_check("status IN ('running', 'failed')"))
        new = gm.desired_model(_registry_with_check("status IN ('running', 'failed', 'done')"))
        sql = gm.render(gm.diff(old, new))
        assert "DROP CONSTRAINT run_log_chk_" in sql and "ADD CONSTRAINT run_log_chk_" in sql
        assert not mg.is_destructive(sql), mg.destructive(sql)

    def test_the_committed_widening_migration_passes(self):
        widenings = [p for p in (REPO / "supabase" / "migrations").glob("*.sql")
                     if "DROP CONSTRAINT" in p.read_text(encoding="utf-8")]
        assert widenings
        assert not any(mg.is_destructive(p.read_text(encoding="utf-8")) for p in widenings)

    def test_a_held_form_in_a_pending_file_holds_it_on_push(self, tmp_path, capsys):
        out = folder(tmp_path, **{"20261101000000_a": ORDINARY,
                                  "20261102000000_hand": HELD_FORMS["multi-action drop"]})
        assert gate(tmp_path, out, [], capsys).out == "held=20261102000000_hand.sql\n"

    def test_an_escape_string_is_read_as_postgres_reads_it(self):
        stmts, ambiguous = mg._scan("SELECT E'a\\'-- '; DROP TABLE football.t; --';")
        assert ambiguous
        assert stmts[0] == "SELECT E'a\\'-- '"
        assert stmts[1] == "DROP TABLE football.t"
        assert mg.destructive("SELECT E'x\\\\';")[0] == mg.AMBIGUOUS

    def test_a_name_ending_in_e_is_not_an_escape_prefix(self):
        stmts, _ = mg._scan("SELECT name'a\\' ; SELECT 2;")
        assert stmts == ["SELECT name'a\\'", "SELECT 2"]

    def test_a_backslash_in_a_dollar_body_or_quoted_name_is_not_ambiguous(self):
        assert not mg._scan("SELECT $f$ a\\b $f$;")[1]
        assert not mg._scan('SELECT "a\\b";')[1]

    @pytest.mark.parametrize("opener", ["--", "/*"])
    def test_a_non_ascii_dollar_tag_holds_the_file(self, opener):
        sql = f"SELECT $é$ {opener} $é$; DROP TABLE football.t;"
        assert mg.destructive(sql)[0] == mg.AMBIGUOUS

    @pytest.mark.parametrize("tag", ["$$", "$f$"])
    def test_an_identifier_dollar_holds_the_file(self, tag):
        sql = f"SELECT 1 AS x{tag}; DROP TABLE football.t; SELECT 1 AS y{tag};"
        assert mg.destructive(sql)[0] == mg.AMBIGUOUS

    def test_the_initial_schema_dollar_bodies_still_pass(self):
        initial = next((REPO / "supabase" / "migrations").glob("*_initial_schema.sql"))
        text = initial.read_text(encoding="utf-8")
        assert "$do$" in text and "$fn$" in text
        stmts, ambiguous = mg._scan(text)
        assert not ambiguous
        assert not mg.is_destructive(text)

    def test_a_digit_dollar_tag_is_one_statement(self):
        assert mg.statements("DO $a1$ BEGIN PERFORM 1; END $a1$; SELECT 2;") == [
            "DO $a1$ BEGIN PERFORM 1; END $a1$", "SELECT 2"]

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

    def test_every_committed_held_migration_is_a_flagged_drop(self):
        import generate_migrations as gm
        flagged = gm.registry_drops(yaml.safe_load((REPO / "docs" / "data_model.yml").read_text(encoding="utf-8")))
        column_drop = re.compile(r"ALTER TABLE ([a-z_]+\.[a-z0-9_]+) DROP COLUMN ([a-z][a-z0-9_]*)")
        table_drop = re.compile(r"DROP TABLE (?:[a-z_]+\.)?([a-z][a-z0-9_]*)")
        for path in sorted((REPO / "supabase" / "migrations").glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            if not mg.is_destructive(sql):
                continue
            for stmt in mg.statements(sql):
                col, tab = column_drop.fullmatch(stmt), table_drop.fullmatch(stmt)
                assert col or tab, f"{path.name}: a held migration holds only drops, found {stmt!r}"
                if col:
                    assert (col.group(1), col.group(2)) in flagged["columns"], \
                        f"{path.name}: {stmt!r} has no drops entry in docs/data_model.yml"
                else:
                    assert tab.group(1) in flagged["tables"], \
                        f"{path.name}: {stmt!r} has no dropped_tables entry in docs/data_model.yml"


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

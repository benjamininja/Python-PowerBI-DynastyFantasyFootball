"""migrate.yml holds a destructive migration on a push (#534, ADR-0018 decision 12).

On a push to main the push job reads the applied versions, then
`scripts/migration_gate.py` takes the first pending destructive migration, and
every pending one after it, out of the checkout before `supabase db push`; the
job ends green, naming it. The held files apply in `apply-held` (#744), which
waits for the owner's approval in the `migrate-held` environment and applies
this run's commit only if the gate still names the same file. A run by
`workflow_dispatch` (the owner's fallback) skips the gate and applies
everything. No case connects to a database.
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
                     if "DROP CONSTRAINT" in p.read_text(encoding="utf-8")
                     and not any(_MOVE.fullmatch(s) for s in mg.statements(p.read_text(encoding="utf-8")))]
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

    def test_a_held_file_of_a_flagged_move_and_retired_function_passes_and_an_extra_addition_does_not(self):
        moves = {("shared.r", "role", "old_word", "new_word")}
        retired = {"shared.is_old": ("()", "shared.is_new", 675)}
        held = mg.statements(
            "ALTER TABLE shared.r DROP CONSTRAINT r_chk_0123abcd;\n"
            "UPDATE shared.r SET role = 'new_word' WHERE role = 'old_word';\n"
            "ALTER TABLE shared.r ADD CONSTRAINT r_chk_89abcdef CHECK (role IN ('new_word'));\n"
            "CREATE FUNCTION shared.is_new() RETURNS boolean LANGUAGE sql AS $fn$ SELECT true $fn$;\n"
            "REVOKE EXECUTE ON FUNCTION shared.is_new() FROM PUBLIC;\n"
            "GRANT USAGE ON SCHEMA shared TO authenticated;\n"
            "GRANT EXECUTE ON FUNCTION shared.is_new() TO authenticated;\n"
            "CREATE OR REPLACE FUNCTION shared.load_r(p text[]) RETURNS integer LANGUAGE plpgsql AS "
            "$fn$ BEGIN INSERT INTO shared.r SELECT 1; RETURN 0; END $fn$;\n"
            "DROP FUNCTION shared.is_old();\n")
        flagged = _flagged_change("t.sql", held, moves, retired)
        assert all(flagged(s) for s in held), [s for s in held if not flagged(s)]
        for extra in ("ALTER TABLE football.t ADD COLUMN c text",
                      "ALTER TABLE shared.other ADD CONSTRAINT other_chk_0123abcd CHECK (x > 0)",
                      "CREATE FUNCTION shared.unrelated() RETURNS boolean LANGUAGE sql AS $fn$ SELECT true $fn$",
                      "UPDATE shared.r SET role = 'third' WHERE role = 'old_word'",
                      "DROP FUNCTION shared.not_retired()"):
            assert not flagged(extra), extra

    def test_a_held_file_of_a_retargeted_key_and_a_recreated_function_passes_and_others_do_not(self):
        recreated = {"shared.load_r": ("(text[])", 675)}
        retargeted = {("shared.c", "c_team_key_fkey"): (True, 675)}
        held = mg.statements(
            "ALTER TABLE shared.c DROP CONSTRAINT c_team_key_fkey;\n"
            "DELETE FROM shared.c WHERE true;\n"
            "ALTER TABLE shared.c ADD CONSTRAINT c_team_key_fkey FOREIGN KEY (team_key) REFERENCES shared.t (team_key) "
            "DEFERRABLE INITIALLY DEFERRED;\n"
            "DROP FUNCTION shared.load_r(text[]);\n"
            "CREATE FUNCTION shared.load_r(p text[], q text[]) RETURNS integer LANGUAGE plpgsql AS "
            "$fn$ BEGIN RETURN 0; END $fn$;\n"
            "REVOKE EXECUTE ON FUNCTION shared.load_r(text[], text[]) FROM PUBLIC;\n"
            "GRANT USAGE ON SCHEMA shared TO etl_writer;\n"
            "GRANT EXECUTE ON FUNCTION shared.load_r(text[], text[]) TO etl_writer;\n"
            "CREATE OR REPLACE FUNCTION shared.load_c(p text[]) RETURNS integer LANGUAGE plpgsql AS "
            "$fn$ BEGIN INSERT INTO shared.c SELECT 1; RETURN 0; END $fn$;\n")
        flagged = _flagged_change("t.sql", held, set(), {}, recreated, retargeted)
        assert all(flagged(s) for s in held), [s for s in held if not flagged(s)]
        for extra in ("DELETE FROM shared.other WHERE true",
                      "ALTER TABLE shared.other DROP CONSTRAINT other_team_key_fkey",
                      "DROP FUNCTION shared.load_r(text[], text[])",
                      "DROP FUNCTION shared.load_other(text[])",
                      "CREATE FUNCTION shared.unrelated() RETURNS boolean LANGUAGE sql AS $fn$ SELECT true $fn$"):
            assert not flagged(extra), extra
        kept = {("shared.c", "c_team_key_fkey"): (False, 675)}
        assert not _flagged_change("t.sql", held, set(), {}, recreated, kept)("DELETE FROM shared.c WHERE true")

    def test_every_committed_held_migration_is_a_flagged_drop(self):
        import generate_migrations as gm
        flagged = gm.registry_drops(yaml.safe_load((REPO / "docs" / "data_model.yml").read_text(encoding="utf-8")))
        column_drop = re.compile(r"ALTER TABLE ([a-z_]+\.[a-z0-9_]+) DROP COLUMN ([a-z][a-z0-9_]*)")
        table_drop = re.compile(r"DROP TABLE (?:[a-z_]+\.)?([a-z][a-z0-9_]*)")
        default_drop = re.compile(r"ALTER TABLE ([a-z_]+\.[a-z0-9_]+) ALTER COLUMN ([a-z][a-z0-9_]*) DROP DEFAULT")
        registry = yaml.safe_load((REPO / "docs" / "data_model.yml").read_text(encoding="utf-8"))
        filled = {(f"{t.get('schema') or 'football'}.{t['name']}", c["name"])
                  for section in ("tables", "other_tables") for t in registry.get(section) or []
                  for c in t["columns"] if c.get("fill")}
        moves = {(f"{t.get('schema') or 'football'}.{t['name']}", m["column"], m["from"], m["to"])
                 for section in ("tables", "other_tables") for t in registry.get(section) or []
                 for m in t.get("moves") or []}
        for path in sorted((REPO / "supabase" / "migrations").glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            if not mg.is_destructive(sql):
                continue
            stmts = mg.statements(sql)
            is_flagged = _flagged_change(path.name, stmts, moves, gm.RETIRED_FUNCTIONS,
                                         gm.RECREATED_FUNCTIONS, gm.RETARGETED_FKS)
            for stmt in stmts:
                if is_flagged(stmt):
                    continue
                col, tab = column_drop.fullmatch(stmt), table_drop.fullmatch(stmt)
                dflt = default_drop.fullmatch(stmt)
                assert col or tab or dflt, (f"{path.name}: a held migration holds only flagged drops and flagged "
                                            f"changes with what cannot apply apart from them, found {stmt!r}")
                if dflt:
                    assert (dflt.group(1), dflt.group(2)) in filled, \
                        f"{path.name}: {stmt!r} ends no fill declared in docs/data_model.yml"
                elif col:
                    assert (col.group(1), col.group(2)) in flagged["columns"], \
                        f"{path.name}: {stmt!r} has no drops entry in docs/data_model.yml"
                else:
                    assert tab.group(1) in flagged["tables"], \
                        f"{path.name}: {stmt!r} has no dropped_tables entry in docs/data_model.yml"


_MOVE = re.compile(r"UPDATE ([a-z_]+\.[a-z0-9_]+) SET ([a-z][a-z0-9_]*) = '([a-z][a-z0-9_]*)' "
                   r"WHERE ([a-z][a-z0-9_]*) = '([a-z][a-z0-9_]*)'")
_FN_DROP = re.compile(r"DROP FUNCTION ([a-z_]+\.[a-z0-9_]+)(\(.*\))")
_CHECK = re.compile(r"ALTER TABLE ([a-z_]+\.[a-z0-9_]+) (?:DROP CONSTRAINT [a-z0-9_]+|ADD CONSTRAINT [a-z0-9_]+ CHECK \(.*\))")
_FN_CREATE = re.compile(r"CREATE (?:OR REPLACE )?FUNCTION ([a-z_]+\.[a-z0-9_]+)\(.*", re.DOTALL)
_FN_GRANT = re.compile(r"(?:REVOKE|GRANT) EXECUTE ON FUNCTION ([a-z_]+\.[a-z0-9_]+)\(.*\) (?:FROM|TO) [A-Za-z_, ]+")
_USAGE = re.compile(r"GRANT USAGE ON SCHEMA [a-z_]+ TO [a-z_]+")
_FK_DROP = re.compile(r"ALTER TABLE ([a-z_]+\.[a-z0-9_]+) DROP CONSTRAINT ([a-z0-9_]+_fkey)")
_FK_ADD = re.compile(r"ALTER TABLE ([a-z_]+\.[a-z0-9_]+) ADD CONSTRAINT ([a-z0-9_]+_fkey) FOREIGN KEY \([a-z0-9_, ]+\) "
                     r"REFERENCES [a-z_]+\.[a-z0-9_]+ \([a-z0-9_, ]+\) DEFERRABLE INITIALLY DEFERRED")
_EMPTY = re.compile(r"DELETE FROM ([a-z_]+\.[a-z0-9_]+) WHERE true")


def _flagged_change(name, stmts, moves, retired, recreated=None, retargeted=None):
    """ADR-0018 decision 3 as amended 2026-11-26 (#675): beside flagged drops, a held
    file may hold a change the registry or a named constant flags (a value move, a
    retired function) and what stands on the same table or function: the checks of a
    moved table, the functions whose body names a moved table, a retired function's
    successor, their EXECUTE grants, and the schema USAGE their grants need. Also a
    foreign key a constant retargets (its drop, the emptying of its table when the entry
    says so, and its add) and a function a constant recreates (its drop by the old
    argument list, its create and grants). Returns a test of one statement."""
    recreated = recreated or {}
    retargeted = retargeted or {}
    moved, functions, retargets = set(), set(), set()
    for stmt in stmts:
        move = _MOVE.fullmatch(stmt)
        if move and move.group(2) == move.group(4) and \
                (move.group(1), move.group(2), move.group(5), move.group(3)) in moves:
            moved.add(move.group(1))
        drop = _FN_DROP.fullmatch(stmt)
        if drop and drop.group(1) in retired and retired[drop.group(1)][0] == drop.group(2):
            functions.add(retired[drop.group(1)][1])
        if drop and drop.group(1) in recreated and recreated[drop.group(1)][0] == drop.group(2):
            functions.add(drop.group(1))
        fk_drop = _FK_DROP.fullmatch(stmt)
        if fk_drop and (fk_drop.group(1), fk_drop.group(2)) in retargeted:
            retargets.add((fk_drop.group(1), fk_drop.group(2)))
            moved.add(fk_drop.group(1))
    for stmt in stmts:
        create = _FN_CREATE.fullmatch(stmt)
        if create and any(re.search(rf"(?<![a-z0-9_.]){re.escape(t)}(?![a-z0-9_])", stmt) for t in moved):
            functions.add(create.group(1))

    def flagged(stmt):
        move, drop = _MOVE.fullmatch(stmt), _FN_DROP.fullmatch(stmt)
        if move:
            return move.group(1) in moved and move.group(2) == move.group(4) and \
                (move.group(1), move.group(2), move.group(5), move.group(3)) in moves
        if drop:
            name, args = drop.group(1), drop.group(2)
            if name in recreated:
                return recreated[name][0] == args and name in functions
            return name in retired and retired[name][0] == args and retired[name][1] in functions
        fk_drop, fk_add, empty = _FK_DROP.fullmatch(stmt), _FK_ADD.fullmatch(stmt), _EMPTY.fullmatch(stmt)
        if fk_drop or fk_add:
            found = fk_drop or fk_add
            return (found.group(1), found.group(2)) in retargets
        if empty:
            return any(t == empty.group(1) and retargeted[(t, n)][0] for t, n in retargets)
        check = _CHECK.fullmatch(stmt)
        if check:
            bare = check.group(1).split(".")[1]
            return check.group(1) in moved and re.search(rf"CONSTRAINT {re.escape(bare)}_chk_[0-9a-f]{{8}}\b", stmt) is not None
        for pattern in (_FN_CREATE, _FN_GRANT):
            found = pattern.fullmatch(stmt)
            if found:
                return found.group(1) in functions
        return bool(_USAGE.fullmatch(stmt)) and bool(moved or functions)

    return flagged


def _load_function(name, body="DELETE FROM shared.app_role WHERE true;", head="CREATE FUNCTION"):
    return (f"{head} {name}(p_a text[], p_b text[]) RETURNS integer\nLANGUAGE plpgsql SECURITY DEFINER "
            f"SET search_path = ''\nAS $fn$\nBEGIN\n    {body}\n    RETURN 0;\nEND\n$fn$;\n"
            f"REVOKE EXECUTE ON FUNCTION {name}(text[], text[]) FROM PUBLIC;\n")


class TestTheLoadFunctionExemption:
    """The one exemption (#700, the owner's Decision): the body of two named functions."""

    def test_the_exempt_names_are_exactly_the_four_load_functions(self):
        assert mg.EXEMPT_BODIES == ("shared.load_app_roles", "shared.load_owner_crosswalk", "shared.load_leagues",
                                    "shared.load_teams")

    @pytest.mark.parametrize("name", mg.EXEMPT_BODIES)
    @pytest.mark.parametrize("head", ["CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", "create function"])
    def test_a_named_function_with_a_delete_in_its_body_is_not_held(self, name, head):
        assert not mg.is_destructive(_load_function(name, head=head)), mg.destructive(_load_function(name, head=head))

    @pytest.mark.parametrize("name", ["shared.load_something_else", "shared.load_app_roles_two",
                                      "ops.load_app_roles", "shared.load_owner_crosswalk2", "shared.pii_token_hashes"])
    def test_a_third_function_with_a_delete_in_its_body_is_still_held(self, name):
        assert mg.is_destructive(_load_function(name))

    @pytest.mark.parametrize("body", ["DELETE FROM shared.app_role;", "TRUNCATE shared.app_role;",
                                      "UPDATE shared.app_role SET role = 'x';"])
    def test_a_destructive_body_of_a_third_function_is_held_in_every_form(self, body):
        assert mg.is_destructive(_load_function("shared.some_function", body))

    def test_a_destructive_statement_beside_a_named_function_is_still_held(self):
        sql = _load_function("shared.load_app_roles") + "DROP TABLE shared.app_role;\n"
        assert mg.is_destructive(sql)
        sql = _load_function("shared.load_app_roles") + "DELETE FROM shared.app_role;\n"
        assert mg.is_destructive(sql)

    def test_a_destructive_form_in_the_header_of_a_named_function_is_still_held(self):
        sql = ("CREATE FUNCTION shared.load_app_roles(p_a text[]) RETURNS integer LANGUAGE sql "
               "DROP AS $fn$ SELECT 1 $fn$;")
        assert mg.is_destructive(sql)

    def test_a_named_function_that_runs_on_in_the_same_statement_is_still_read(self):
        sql = ("CREATE FUNCTION shared.load_app_roles(p_a text[]) RETURNS integer LANGUAGE sql AS $fn$ SELECT 1 $fn$ "
               "DROP TABLE shared.app_role;")
        assert mg.is_destructive(sql)

    def test_a_named_function_is_not_held_on_push_and_the_migrations_after_it_apply(self, tmp_path, capsys):
        out = folder(tmp_path, **{"20261101000000_a": ORDINARY,
                                  "20261102000000_load": _load_function("shared.load_app_roles"),
                                  "20261103000000_b": ORDINARY})
        assert gate(tmp_path, out, ["20261101000000"], capsys).out == "held=\n"
        assert len(names(out)) == 3

    def test_a_third_function_holds_itself_and_the_migrations_after_it(self, tmp_path, capsys):
        out = folder(tmp_path, **{"20261102000000_load": _load_function("shared.other_load"),
                                  "20261103000000_b": ORDINARY})
        assert gate(tmp_path, out, [], capsys).out == "held=20261102000000_load.sql\n"
        assert names(out) == []

    def test_the_committed_load_functions_are_not_held_and_hold_nothing_but_their_own_delete(self):
        import generate_migrations as gm
        registry = yaml.safe_load((REPO / "docs" / "data_model.yml").read_text(encoding="utf-8"))
        moves = {(f"{t.get('schema') or 'football'}.{t['name']}", m["column"], m["from"], m["to"])
                 for section in ("tables", "other_tables") for t in registry.get(section) or []
                 for m in t.get("moves") or []}
        found = set()
        for path in sorted((REPO / "supabase" / "migrations").glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            stmts = mg.statements(sql)
            for stmt in stmts:
                if mg._EXEMPT_HEAD.match(stmt):
                    found.add(mg._EXEMPT_HEAD.match(stmt).group(1))
                    assert not mg._hits(stmt), path.name
                    assert stmt.count("DELETE FROM") == 1 and "TRUNCATE" not in stmt and "UPDATE" not in stmt
                    is_flagged = _flagged_change(path.name, stmts, moves, gm.RETIRED_FUNCTIONS,
                                                 gm.RECREATED_FUNCTIONS, gm.RETARGETED_FKS)
                    held = [s for s in mg.destructive(sql) if not is_flagged(s)]
                    assert not held, f"{path.name}: a load function sits in a file held for {held}"
        assert found == set(mg.EXEMPT_BODIES)


def _load():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _on(wf):
    return wf.get("on", wf.get(True))


def _push_steps():
    return _load()["jobs"]["push"]["steps"]


def _step(name, job="push"):
    return next(s for s in _load()["jobs"][job]["steps"] if s.get("name") == name)


GATE_STEP = "Hold a destructive migration for the owner's approval"
RECHECK_STEP = "The gate still names the held migration"
HELD_PUSH_STEP = "Apply the held migrations of this run's commit"


class TestTheWorkflow:
    def test_it_starts_on_a_pr_a_push_to_main_or_by_hand(self):
        on = _on(_load())
        assert set(on) == {"pull_request", "push", "workflow_dispatch"}
        assert on["push"]["branches"] == ["main"]
        assert on["workflow_dispatch"] is None

    def test_a_change_to_the_gate_runs_the_workflow(self):
        wf = _load()
        on = _on(wf)
        diff = next(s for s in wf["jobs"]["scope"]["steps"] if s.get("id") == "diff")
        run_line = next(l.strip() for l in diff["run"].splitlines() if l.strip().endswith(") run=true ;;"))
        listed = [p.strip() for p in run_line[: -len(") run=true ;;")].split("|")]
        assert "scripts/migration_gate.py" in listed
        assert wf["jobs"]["validate"]["needs"] == "scope"
        assert "needs.scope.outputs.run == 'true'" in wf["jobs"]["validate"]["if"]
        assert "scripts/migration_gate.py" in on["push"]["paths"]

    def test_the_push_job_runs_from_main_only(self):
        assert _load()["jobs"]["push"]["if"] == (
            "(github.event_name == 'push' || github.event_name == 'workflow_dispatch') "
            "&& github.ref == 'refs/heads/main'")

    def test_the_gate_runs_on_a_push_only_and_before_the_push(self):
        steps = [s.get("name") for s in _push_steps()]
        gate_at = steps.index(GATE_STEP)
        push_at = steps.index("Push the migrations to the real project")
        name_at = steps.index("Name the held migration")
        assert gate_at < push_at < name_at
        gate_step = _step(GATE_STEP)
        assert gate_step["if"] == "github.event_name == 'push'"
        assert gate_step["id"] == "gate"
        assert "scripts/migration_gate.py" in gate_step["run"] and "--remove" in gate_step["run"]
        assert "supabase_migrations.schema_migrations" in gate_step["run"]
        assert "ON_ERROR_STOP=1" in gate_step["run"]

    def test_a_dispatch_skips_the_gate_and_pushes_everything(self):
        push = _step("Push the migrations to the real project")
        assert "if" not in push
        assert push["run"] == 'supabase db push --yes --db-url "$SUPABASE_MIGRATE_DB_URL"'

    def test_unheld_files_apply_and_a_held_one_ends_the_push_job_green_by_name(self):
        named = _step("Name the held migration")
        assert named["if"] == "steps.gate.outputs.held != ''"
        assert named["env"] == {"HELD": "${{ steps.gate.outputs.held }}"}
        assert "::notice::$HELD" in named["run"] and "$GITHUB_STEP_SUMMARY" in named["run"]
        assert "exit 1" not in named["run"] and "::error::" not in named["run"]
        assert not any("exit 1" in s.get("run", "") for s in _push_steps())
        assert _load()["jobs"]["push"]["outputs"] == {"held": "${{ steps.gate.outputs.held }}"}

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


class TestTheApproval:
    """#744: the held files wait for the owner's approval in their own environment."""

    def _job(self):
        return _load()["jobs"]["apply-held"]

    def test_it_runs_after_push_on_a_push_to_main_with_a_held_file_only(self):
        job = self._job()
        assert job["needs"] == "push"
        assert job["if"] == ("github.event_name == 'push' && github.ref == 'refs/heads/main' "
                             "&& needs.push.outputs.held != ''")

    def test_a_dispatch_never_reaches_it(self):
        assert "workflow_dispatch" not in self._job()["if"]
        assert _step(GATE_STEP)["if"] == "github.event_name == 'push'"

    def test_it_waits_in_its_own_environment_and_shares_the_apply_lock(self):
        job = self._job()
        assert job["environment"] == "migrate-held"
        assert _load()["jobs"]["push"]["environment"] == "etl"
        assert job["concurrency"] == _load()["jobs"]["push"]["concurrency"] == {
            "group": "migrate-push", "cancel-in-progress": False}

    def test_it_checks_out_the_commit_of_its_own_run(self):
        checkout = next(s for s in self._job()["steps"] if s.get("uses", "").startswith("actions/checkout"))
        assert checkout["with"] == {"ref": "${{ github.sha }}", "persist-credentials": False}

    def test_it_applies_only_when_the_gate_still_names_the_same_file(self):
        steps = [s.get("name") for s in self._job()["steps"]]
        assert steps.index(RECHECK_STEP) < steps.index(HELD_PUSH_STEP)
        recheck = _step(RECHECK_STEP, "apply-held")
        assert recheck["id"] == "recheck"
        assert recheck["env"] == {"SUPABASE_MIGRATE_DB_URL": "${{ secrets.SUPABASE_MIGRATE_DB_URL }}",
                                  "HELD": "${{ needs.push.outputs.held }}"}
        run = recheck["run"]
        assert "scripts/migration_gate.py --applied" in run and "--remove" not in run
        assert "supabase_migrations.schema_migrations" in run and "ON_ERROR_STOP=1" in run
        assert '"$now" = "$HELD"' in run and 'echo "apply=true"' in run
        assert '-z "$now"' in run and 'echo "apply=false"' in run and "exit 1" in run
        push = _step(HELD_PUSH_STEP, "apply-held")
        assert push["if"] == "steps.recheck.outputs.apply == 'true'"
        assert push["run"] == 'supabase db push --yes --db-url "$SUPABASE_MIGRATE_DB_URL"'
        assert sum("supabase db push" in s.get("run", "") for s in self._job()["steps"]) == 1

    def test_the_recheck_reads_the_gate_output_the_gate_writes(self, tmp_path, capsys):
        out = folder(tmp_path, **{"20261101000000_a": ORDINARY, "20261102000000_drop": COLUMN_DROP})
        assert gate(tmp_path, out, ["20261101000000"], capsys, remove=False).out == "held=20261102000000_drop.sql\n"
        assert gate(tmp_path, out, ["20261101000000", "20261102000000"], capsys, remove=False).out == "held=\n"
        assert names(out) == ["20261101000000_a.sql", "20261102000000_drop.sql"]

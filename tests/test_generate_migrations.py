"""The migration generator (#108 Brief 1, ADR-0018 decision 3).

Every case runs on a fixture registry. No case reads docs/data_model.yml, and
none connects to a database: the SQL is checked as text.
"""
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import generate_migrations as gm

NOW = datetime(2026, 10, 31, 12, 0, 5, tzinfo=timezone.utc)
LATER = datetime(2026, 11, 1, 9, 30, 0, tzinfo=timezone.utc)


def col(name, sql_type="text"):
    return {"name": name, "dtype": "str", "sql_type": sql_type}


def fixture_registry():
    return {
        "tables": [
            {"name": "dim_team", "type": "dim", "grain": "team_key", "pk": ["team_key"],
             "required_keys": ["conference"],
             "columns": [col("team_key"), col("conference"), col("nickname")]},
            {"name": "dim_player", "type": "dim", "grain": "gsis_id", "pk": "gsis_id",
             "columns": [col("gsis_id"), col("display_name")]},
            {"name": "fact_score", "type": "fact", "grain": "(team_key, week)",
             "pk": ["team_key", "week"],
             "columns": [col("team_key"), col("week", "integer"), col("gsis_id"),
                         col("points", "double precision"), col("is_home", "boolean"),
                         col("day", "date"), col("seen_at", "timestamp")],
             "fk": [{"columns": ["team_key"], "to": "dim_team", "ref": "team_key"},
                    {"columns": "gsis_id", "to": "dim_player", "ref": ["gsis_id"]}],
             "checks": ["points >= 0"],
             "indexes": [{"columns": ["gsis_id"]},
                         {"name": "fact_score_open_idx", "columns": ["week"], "unique": True,
                          "where": "points > 0"}]},
            {"name": "resolver_alias", "type": "resolver", "grain": "alias", "pk": ["alias"],
             "columns": [col("alias")]},
        ],
        "other_tables": [
            {"name": "owner", "schema": "shared", "pk": ["owner_id"],
             "columns": [col("owner_id"), col("team_key"), col("human_name"),
                         col("email"), col("fantrax_username")]},
            {"name": "run_log", "schema": "ops", "pk": ["run_id"],
             "columns": [col("run_id", "uuid"), col("status"), col("rows_written", "jsonb"),
                         col("started_at", "timestamptz")],
             "checks": ["status IN ('running', 'failed')"]},
        ],
    }


def table(registry, name):
    for section in ("tables", "other_tables"):
        for entry in registry.get(section, []):
            if entry["name"] == name:
                return entry
    raise KeyError(name)


def model(registry=None):
    return gm.desired_model(registry or fixture_registry())


def full_sql(registry=None):
    return gm.render(gm.diff(gm.EMPTY_MODEL, model(registry)))


@pytest.fixture(autouse=True)
def never_the_real_registry(monkeypatch, tmp_path):
    """A case that forgot --registry fails loudly instead of reading the real file."""
    monkeypatch.setattr(gm, "REGISTRY_FILE", tmp_path / "no_such_registry.yml")
    monkeypatch.setattr(gm, "OUT_DIR", tmp_path / "no_such_out")


def run(tmp_path, registry, *extra, now=NOW):
    reg_file = tmp_path / "registry.yml"
    reg_file.write_text(yaml.safe_dump(registry), encoding="utf-8")
    return gm.main(["--registry", str(reg_file), "--out", str(tmp_path / "supabase"), *extra], now=now)


def migrations(tmp_path):
    return sorted((tmp_path / "supabase" / "migrations").glob("*"))


class TestDesiredModel:
    def test_holds_the_three_schemas_and_two_roles(self):
        m = model()
        assert m["schemas"] == ["football", "shared", "ops"]
        assert m["roles"] == ["etl_writer", "etl_reader"]

    def test_tables_are_keyed_by_schema_and_name(self):
        assert set(model()["tables"]) == {
            "football.dim_team", "football.dim_player", "football.fact_score",
            "football.resolver_alias", "shared.owner", "ops.run_log"}

    def test_every_dim_fact_and_resolver_table_goes_in_football(self):
        m = model()
        assert {t["schema"] for k, t in m["tables"].items() if k.startswith("football.")} == {"football"}
        assert m["tables"]["football.resolver_alias"]["schema"] == "football"

    def test_pk_and_required_keys_are_not_null(self):
        cols = {c["name"]: c["not_null"] for c in model()["tables"]["football.dim_team"]["columns"]}
        assert cols == {"team_key": True, "conference": True, "nickname": False}

    def test_a_pk_may_be_a_bare_name(self):
        assert model()["tables"]["football.dim_player"]["pk"] == ["gsis_id"]

    def test_a_fk_points_at_the_qualified_table(self):
        fks = {f["name"]: f for f in model()["tables"]["football.fact_score"]["fks"]}
        assert fks["fact_score_team_key_fkey"] == {
            "name": "fact_score_team_key_fkey", "columns": ["team_key"],
            "to": "football.dim_team", "ref": ["team_key"]}
        assert fks["fact_score_gsis_id_fkey"]["to"] == "football.dim_player"

    def test_an_index_gets_a_default_name(self):
        names = [i["name"] for i in model()["tables"]["football.fact_score"]["indexes"]]
        assert names == ["fact_score_gsis_id_idx", "fact_score_open_idx"]

    def test_the_model_survives_the_state_file(self):
        m = model()
        assert json.loads(gm.dump_state(m)) == m

    def test_the_same_registry_gives_the_same_state(self):
        assert gm.dump_state(model()) == gm.dump_state(model())

    def test_the_pii_function_is_present_with_the_owner_table(self):
        assert list(model()["functions"]) == ["shared.pii_token_hashes"]

    def test_no_function_without_the_owner_table(self):
        reg = fixture_registry()
        reg["other_tables"] = [t for t in reg["other_tables"] if t["name"] != "owner"]
        assert model(reg)["functions"] == {}


def _broken(mutate):
    reg = fixture_registry()
    mutate(reg)
    return reg


REFUSED_REGISTRIES = {
    "uppercase table": lambda r: table(r, "dim_team").update(name="Dim_Team"),
    "quoted column": lambda r: table(r, "dim_team")["columns"].append(col('"nick"')),
    "dashed column": lambda r: table(r, "dim_team")["columns"].append(col("nick-name")),
    "leading digit": lambda r: table(r, "dim_team")["columns"].append(col("1st")),
    "camel case": lambda r: table(r, "dim_team")["columns"].append(col("camelCase")),
    "too long": lambda r: table(r, "dim_team")["columns"].append(col("a" * 64)),
    "reserved select": lambda r: table(r, "dim_team")["columns"].append(col("select")),
    "reserved user": lambda r: table(r, "dim_team")["columns"].append(col("user")),
    "reserved table name": lambda r: table(r, "dim_team").update(name="table"),
    "reserved join-type": lambda r: table(r, "dim_team")["columns"].append(col("left")),
    "bad index name": lambda r: table(r, "fact_score")["indexes"][0].update(name="Bad Name"),
    "bigint": lambda r: table(r, "dim_team")["columns"].append(col("big", "bigint")),
    "no sql_type": lambda r: table(r, "dim_team")["columns"].append({"name": "x", "dtype": "str"}),
    "no pk": lambda r: table(r, "dim_team").pop("pk"),
    "pk on an unknown column": lambda r: table(r, "dim_team").update(pk=["nope"]),
    "required key unknown": lambda r: table(r, "dim_team").update(required_keys=["nope"]),
    "duplicate column": lambda r: table(r, "dim_team")["columns"].append(col("nickname")),
    "duplicate table": lambda r: r["tables"].append(copy.deepcopy(table(r, "dim_team"))),
    "table also in other_tables": lambda r: r["other_tables"].append(
        {**copy.deepcopy(table(r, "dim_team")), "schema": "ops"}),
    "unknown schema": lambda r: table(r, "run_log").update(schema="public"),
    "other table with no schema": lambda r: table(r, "run_log").pop("schema"),
    "fk to an unknown table": lambda r: table(r, "fact_score")["fk"][0].update(to="dim_nowhere"),
    "fk from an unknown column": lambda r: table(r, "fact_score")["fk"][0].update(columns=["nope"]),
    "fk to an unknown column": lambda r: table(r, "fact_score")["fk"][0].update(ref="nope"),
    "fk of different widths": lambda r: table(r, "fact_score")["fk"][0].update(ref=["team_key", "conference"]),
    "fk of different types": lambda r: table(r, "fact_score")["fk"][0].update(columns=["week"]),
    "check holding a semicolon": lambda r: table(r, "fact_score").update(checks=["points > 0; DROP TABLE x"]),
    "check holding a comment": lambda r: table(r, "fact_score").update(checks=["points > 0 -- x"]),
    "index predicate holding a block comment": lambda r: table(r, "fact_score")["indexes"][1].update(where="a /* b */"),
    "same check twice": lambda r: table(r, "fact_score").update(checks=["points >= 0", "points >= 0"]),
    "owner without human_name": lambda r: table(r, "owner")["columns"].remove(col("human_name")),
    "index on an unknown column": lambda r: table(r, "fact_score")["indexes"][0].update(columns=["nope"]),
    "no tables": lambda r: (r.update(tables=[]), r.update(other_tables=[])),
}


SNAKE = "not unquoted snake_case"
REFUSAL_TEXT = {
    "uppercase table": SNAKE, "quoted column": SNAKE, "dashed column": SNAKE,
    "leading digit": SNAKE, "camel case": SNAKE, "bad index name": SNAKE,
    "too long": "longer than 63 characters",
    "reserved select": "a Postgres reserved word", "reserved user": "a Postgres reserved word",
    "reserved table name": "a Postgres reserved word", "reserved join-type": "a Postgres reserved word",
    "bigint": "sql_type 'bigint'", "no sql_type": "sql_type None",
    "no pk": "no pk",
    "pk on an unknown column": "unknown column 'nope'",
    "required key unknown": "unknown column 'nope'",
    "duplicate column": "declared twice", "duplicate table": "declared twice",
    "table also in other_tables": "declared twice", "same check twice": "declared twice",
    "unknown schema": "schema 'public' is not one of",
    "other table with no schema": "schema None is not one of",
    "fk to an unknown table": "unknown table 'dim_nowhere'",
    "fk from an unknown column": "unknown column 'nope'",
    "fk to an unknown column": "unknown column 'nope'",
    "fk of different widths": "differ in length",
    "fk of different types": "week is integer, team_key is text",
    "check holding a semicolon": "may not hold",
    "check holding a comment": "may not hold",
    "index predicate holding a block comment": "may not hold",
    "owner without human_name": "unknown column 'human_name'",
    "index on an unknown column": "unknown column 'nope'",
    "no tables": "declares no tables",
}


class TestIdentifierAndRegistryRules:
    def test_every_refused_registry_has_its_reason(self):
        assert set(REFUSAL_TEXT) == set(REFUSED_REGISTRIES)

    @pytest.mark.parametrize("name", REFUSED_REGISTRIES)
    def test_the_registry_is_refused(self, name):
        with pytest.raises(gm.RegistryError, match=re.escape(REFUSAL_TEXT[name])):
            model(_broken(REFUSED_REGISTRIES[name]))

    def test_the_fixture_itself_is_accepted(self):
        assert model()

    def test_a_column_named_like_a_non_reserved_keyword_is_accepted(self):
        reg = fixture_registry()
        table(reg, "dim_team")["columns"] += [col("position"), col("trigger"), col("status"), col("name")]
        assert model(reg)


class TestRenderFromEmpty:
    def test_schemas_come_first_in_order(self):
        sql = full_sql()
        a, b, c = (sql.index(f"CREATE SCHEMA {s};") for s in ("football", "shared", "ops"))
        assert a < b < c < sql.index("CREATE TABLE")

    def test_roles_are_created_only_when_missing_and_cannot_bypass_rls(self):
        sql = full_sql()
        for role in ("etl_writer", "etl_reader"):
            assert f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}')" in sql
            assert f"CREATE ROLE {role} LOGIN NOBYPASSRLS;" in sql
        assert "PASSWORD" not in sql.upper()
        assert "BYPASSRLS;" not in sql.replace("NOBYPASSRLS;", "")

    def test_roles_come_before_tables(self):
        sql = full_sql()
        assert sql.index("CREATE ROLE etl_reader") < sql.index("CREATE TABLE")

    def test_a_table_has_typed_columns_not_null_pk_and_check(self):
        sql = full_sql()
        assert "CREATE TABLE football.dim_team (\n    team_key text NOT NULL,\n    conference text NOT NULL,\n    nickname text,\n" in sql
        assert "CONSTRAINT dim_team_pkey PRIMARY KEY (team_key)" in sql
        assert "CONSTRAINT fact_score_pkey PRIMARY KEY (team_key, week)" in sql
        assert "    week integer NOT NULL,\n" in sql
        assert "    points double precision,\n" in sql
        assert "    is_home boolean,\n    day date,\n    seen_at timestamp,\n" in sql
        assert re.search(r"CONSTRAINT fact_score_chk_[0-9a-f]{8} CHECK \(points >= 0\)", sql)
        assert "CREATE TABLE ops.run_log" in sql
        assert "    run_id uuid NOT NULL,\n" in sql
        assert "    rows_written jsonb,\n    started_at timestamptz,\n" in sql
        assert re.search(r"CHECK \(status IN \('running', 'failed'\)\)", sql)

    def test_every_table_is_created_once_in_its_schema(self):
        sql = full_sql()
        for qualified in ("football.dim_team", "football.dim_player", "football.fact_score",
                          "football.resolver_alias", "shared.owner", "ops.run_log"):
            assert sql.count(f"CREATE TABLE {qualified} (") == 1

    def test_fks_come_after_every_table_and_are_deferrable(self):
        sql = full_sql()
        fks = re.findall(r"^ALTER TABLE .* FOREIGN KEY .*$", sql, flags=re.M)
        assert len(fks) == 2
        assert all(fk.endswith("DEFERRABLE INITIALLY DEFERRED;") for fk in fks)
        assert ("ALTER TABLE football.fact_score ADD CONSTRAINT fact_score_team_key_fkey FOREIGN KEY "
                "(team_key) REFERENCES football.dim_team (team_key) DEFERRABLE INITIALLY DEFERRED;") in sql
        assert sql.rindex("CREATE TABLE") < sql.index("FOREIGN KEY")

    def test_rls_is_on_for_every_table(self):
        sql = full_sql()
        enabled = re.findall(r"^ALTER TABLE (\S+) ENABLE ROW LEVEL SECURITY;$", sql, flags=re.M)
        assert sorted(enabled) == sorted(model()["tables"])
        assert sql.index("FOREIGN KEY") < sql.index("ENABLE ROW LEVEL SECURITY")

    def test_football_and_ops_grant_the_writer_dml_and_the_reader_select(self):
        sql = full_sql()
        for schema in ("football", "ops"):
            assert f"GRANT USAGE ON SCHEMA {schema} TO etl_writer, etl_reader;" in sql
        for qualified in ("football.dim_team", "football.fact_score", "football.resolver_alias", "ops.run_log"):
            assert f"GRANT SELECT, INSERT, UPDATE, DELETE ON {qualified} TO etl_writer;" in sql
            assert f"GRANT SELECT ON {qualified} TO etl_reader;" in sql
            assert (f"CREATE POLICY etl_writer_all ON {qualified} FOR ALL TO etl_writer "
                    "USING (true) WITH CHECK (true);") in sql
            assert f"CREATE POLICY etl_reader_select ON {qualified} FOR SELECT TO etl_reader USING (true);" in sql

    def test_no_truncate_is_granted(self):
        assert "TRUNCATE" not in full_sql().upper()

    def test_anon_and_authenticated_are_never_named(self):
        assert not re.search(r"\b(anon|authenticated|service_role)\b", full_sql())

    def test_shared_owner_has_rls_and_no_policy_and_no_table_grant(self):
        sql = full_sql()
        assert "ALTER TABLE shared.owner ENABLE ROW LEVEL SECURITY;" in sql
        assert not re.search(r"POLICY .* ON shared\.", sql)
        assert not re.search(r"GRANT .* ON shared\.owner", sql)
        assert "GRANT USAGE ON SCHEMA shared TO etl_writer, etl_reader" not in sql

    def test_the_reader_gets_nothing_in_shared(self):
        sql = full_sql()
        assert [ln for ln in sql.splitlines() if "shared" in ln and "etl_reader" in ln] == []

    def test_the_pii_function(self):
        sql = full_sql()
        assert "CREATE FUNCTION shared.pii_token_hashes() RETURNS SETOF text" in sql
        assert "SECURITY DEFINER" in sql
        assert "SET search_path = ''" in sql
        assert "sha256(" in sql
        assert "lower(o.human_name)" in sql and "lower(o.fantrax_username)" in sql
        assert "pgcrypto" not in sql and "digest(" not in sql
        assert "REVOKE EXECUTE ON FUNCTION shared.pii_token_hashes() FROM PUBLIC;" in sql
        assert "GRANT USAGE ON SCHEMA shared TO etl_writer;" in sql
        assert "GRANT EXECUTE ON FUNCTION shared.pii_token_hashes() TO etl_writer;" in sql

    def test_the_function_comes_after_the_owner_table_and_before_the_indexes(self):
        sql = full_sql()
        assert sql.index("CREATE TABLE shared.owner") < sql.index("CREATE FUNCTION")
        assert sql.index("GRANT EXECUTE ON FUNCTION") < sql.index("INDEX")

    def test_indexes_including_the_partial_unique_one_come_last(self):
        sql = full_sql()
        assert "CREATE INDEX fact_score_gsis_id_idx ON football.fact_score (gsis_id);" in sql
        assert ("CREATE UNIQUE INDEX fact_score_open_idx ON football.fact_score (week) "
                "WHERE points > 0;") in sql
        assert sql.index("CREATE POLICY") < sql.index("CREATE INDEX")

    def test_the_sections_follow_the_brief_in_order(self):
        sql = full_sql()
        marks = ["CREATE SCHEMA football", "CREATE ROLE etl_writer", "CREATE TABLE football.dim_team",
                 "FOREIGN KEY", "ENABLE ROW LEVEL SECURITY", "GRANT USAGE ON SCHEMA football",
                 "CREATE POLICY", "CREATE FUNCTION", "CREATE INDEX"]
        positions = [sql.index(m) for m in marks]
        assert positions == sorted(positions)

    def test_the_output_is_stable(self):
        assert full_sql() == full_sql()


class TestDiffAdditions:
    def test_the_same_model_changes_nothing(self):
        changes = gm.diff(model(), model())
        assert not gm.has_changes(changes)
        assert changes["refusals"] == []

    def test_a_model_read_back_from_the_state_file_changes_nothing(self):
        stored = json.loads(gm.dump_state(model()))
        assert not gm.has_changes(gm.diff(stored, model()))

    def test_a_new_table_comes_with_its_fk_rls_grants_and_index(self):
        reg = fixture_registry()
        reg["tables"].append({
            "name": "fact_extra", "pk": ["team_key"],
            "columns": [col("team_key"), col("note")],
            "fk": [{"columns": ["team_key"], "to": "dim_team", "ref": "team_key"}],
            "indexes": [{"columns": ["note"]}]})
        sql = gm.render(gm.diff(model(), model(reg)))
        assert "CREATE TABLE football.fact_extra (" in sql
        assert "FOREIGN KEY (team_key) REFERENCES football.dim_team (team_key)" in sql
        assert "ALTER TABLE football.fact_extra ENABLE ROW LEVEL SECURITY;" in sql
        assert "CREATE POLICY etl_writer_all ON football.fact_extra" in sql
        assert "CREATE INDEX fact_extra_note_idx ON football.fact_extra (note);" in sql
        assert "CREATE SCHEMA" not in sql and "CREATE ROLE" not in sql

    def test_a_new_column_is_an_alter(self):
        reg = fixture_registry()
        table(reg, "dim_player")["columns"].append(col("born", "date"))
        sql = gm.render(gm.diff(model(), model(reg)))
        assert sql.strip() == "ALTER TABLE football.dim_player ADD COLUMN born date;"

    def test_a_new_not_null_column_says_so(self):
        reg = fixture_registry()
        table(reg, "dim_player")["columns"].append(col("born", "date"))
        table(reg, "dim_player")["required_keys"] = ["born"]
        sql = gm.render(gm.diff(model(), model(reg)))
        assert "ADD COLUMN born date NOT NULL;" in sql

    def test_a_new_check_on_an_existing_table_is_an_alter(self):
        reg = fixture_registry()
        table(reg, "fact_score")["checks"].append("week > 0")
        sql = gm.render(gm.diff(model(), model(reg)))
        assert re.fullmatch(r"ALTER TABLE football\.fact_score ADD CONSTRAINT fact_score_chk_[0-9a-f]{8} CHECK \(week > 0\);\n", sql)

    def test_a_new_fk_on_an_existing_table_is_an_alter(self):
        reg = fixture_registry()
        table(reg, "dim_team")["columns"].append(col("owner_id"))
        table(reg, "dim_team")["fk"] = [{"columns": ["owner_id"], "to": "owner", "ref": "owner_id"}]
        sql = gm.render(gm.diff(model(), model(reg)))
        assert "ADD CONSTRAINT dim_team_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES shared.owner (owner_id)" in sql

    def test_a_new_index_on_an_existing_table(self):
        reg = fixture_registry()
        table(reg, "dim_team")["indexes"] = [{"columns": ["conference", "nickname"], "unique": True}]
        sql = gm.render(gm.diff(model(), model(reg)))
        assert sql.strip() == "CREATE UNIQUE INDEX dim_team_conference_nickname_idx ON football.dim_team (conference, nickname);"

    def test_the_pii_function_arrives_with_a_later_owner_table(self):
        reg = fixture_registry()
        without = copy.deepcopy(reg)
        without["other_tables"] = [t for t in without["other_tables"] if t["name"] != "owner"]
        sql = gm.render(gm.diff(model(without), model(reg)))
        assert "CREATE TABLE shared.owner" in sql
        assert sql.index("CREATE TABLE shared.owner") < sql.index("CREATE FUNCTION")

    def test_a_check_may_be_reordered_without_a_change(self):
        reg = fixture_registry()
        table(reg, "fact_score")["checks"] = ["week > 0", "points >= 0"]
        base = copy.deepcopy(reg)
        table(base, "fact_score")["checks"] = ["points >= 0", "week > 0"]
        assert not gm.has_changes(gm.diff(model(base), model(reg)))


def drop_column(reg):
    table(reg, "dim_team")["columns"].remove(col("nickname"))


def drop_table(reg):
    reg["tables"].remove(table(reg, "resolver_alias"))


def rename_table(reg):
    table(reg, "resolver_alias")["name"] = "resolver_aliases"


def rename_column(reg):
    for c in table(reg, "dim_team")["columns"]:
        if c["name"] == "nickname":
            c["name"] = "short_name"


def change_type(reg):
    table(reg, "dim_team")["columns"][2]["sql_type"] = "integer"


def drop_check(reg):
    table(reg, "fact_score")["checks"] = []


def drop_fk(reg):
    table(reg, "fact_score")["fk"].pop()


def retarget_fk(reg):
    table(reg, "fact_score")["fk"][0].update(to="dim_player", ref="gsis_id")


def drop_index(reg):
    table(reg, "fact_score")["indexes"].pop()


def change_index(reg):
    table(reg, "fact_score")["indexes"][1].update(where="points > 1")


def change_pk(reg):
    table(reg, "dim_team").update(pk=["team_key", "conference"])


def loosen_not_null(reg):
    table(reg, "dim_team").update(required_keys=[])


REFUSED_CHANGES = {
    "drop of table": (drop_table, "football.resolver_alias: drop of table"),
    "rename of table": (rename_table, "rename of table to football.resolver_aliases"),
    "drop of column": (drop_column, "football.dim_team: drop of column nickname"),
    "rename of column": (rename_column, "rename of column nickname to short_name"),
    "type change": (change_type, "football.dim_team.nickname: type change from text to integer"),
    "drop of check": (drop_check, "football.fact_score: drop of check points >= 0"),
    "drop of fk": (drop_fk, "football.fact_score: drop of foreign key fact_score_gsis_id_fkey"),
    "change of fk": (retarget_fk, "football.fact_score: change of foreign key fact_score_team_key_fkey"),
    "drop of index": (drop_index, "football.fact_score: drop of index fact_score_open_idx"),
    "change of index": (change_index, "football.fact_score: change of index fact_score_open_idx"),
    "change of pk": (change_pk, "football.dim_team: change of primary key"),
    "change of not null": (loosen_not_null, "football.dim_team.conference: change of NOT NULL"),
}


class TestDiffRefusals:
    @pytest.mark.parametrize("case", REFUSED_CHANGES)
    def test_the_change_is_refused_and_named(self, case):
        mutate, message = REFUSED_CHANGES[case]
        changed = _broken(mutate)
        refusals = gm.diff(model(), model(changed))["refusals"]
        assert any(message in r for r in refusals), refusals

    def test_a_dropped_schema_is_refused(self):
        old = model()
        old["schemas"] = old["schemas"] + ["archive"]
        assert "drop of schema archive" in gm.diff(old, model())["refusals"]

    def test_a_dropped_role_is_refused(self):
        old = model()
        old["roles"] = old["roles"] + ["etl_extra"]
        assert "drop of role etl_extra" in gm.diff(old, model())["refusals"]

    def test_a_changed_function_body_is_refused(self):
        old = model()
        old["functions"]["shared.pii_token_hashes"] = "CREATE FUNCTION shared.pii_token_hashes() ..."
        assert gm.diff(old, model())["refusals"] == ["shared.pii_token_hashes: change of function body"]

    def test_a_dropped_function_is_refused(self):
        old = model()
        old["functions"]["shared.other"] = "x"
        assert gm.diff(old, model())["refusals"] == ["shared.other: drop of function"]


class TestMain:
    def test_the_first_run_writes_a_migration_and_the_state_file(self, tmp_path, capsys):
        assert run(tmp_path, fixture_registry()) == 0
        files = migrations(tmp_path)
        assert [f.name for f in files] == ["20261031120005_initial_schema.sql"]
        state = (tmp_path / "supabase" / "registry_state.json").read_text(encoding="utf-8")
        assert json.loads(state) == model()
        assert "wrote" in capsys.readouterr().out

    def test_line_one_holds_the_sha256_of_the_state_file(self, tmp_path):
        run(tmp_path, fixture_registry())
        state_bytes = (tmp_path / "supabase" / "registry_state.json").read_bytes()
        first = migrations(tmp_path)[0].read_text(encoding="utf-8").splitlines()[0]
        assert first == f"-- registry_state sha256: {hashlib.sha256(state_bytes).hexdigest()}"

    def test_the_file_is_what_render_gives(self, tmp_path):
        run(tmp_path, fixture_registry())
        body = migrations(tmp_path)[0].read_text(encoding="utf-8").split("\n\n", 1)[1]
        assert body == full_sql()

    def test_files_use_unix_line_endings(self, tmp_path):
        run(tmp_path, fixture_registry())
        assert b"\r" not in migrations(tmp_path)[0].read_bytes()
        assert b"\r" not in (tmp_path / "supabase" / "registry_state.json").read_bytes()

    def test_the_state_file_is_outside_the_migrations_folder(self, tmp_path):
        run(tmp_path, fixture_registry())
        assert all(f.suffix == ".sql" for f in migrations(tmp_path))
        assert (tmp_path / "supabase" / "registry_state.json").exists()

    def test_no_change_writes_nothing(self, tmp_path, capsys):
        run(tmp_path, fixture_registry())
        state = tmp_path / "supabase" / "registry_state.json"
        before_state, before_files = state.read_bytes(), migrations(tmp_path)
        capsys.readouterr()
        assert run(tmp_path, fixture_registry(), now=LATER) == 0
        assert migrations(tmp_path) == before_files
        assert state.read_bytes() == before_state
        assert "no change" in capsys.readouterr().out

    def test_an_empty_registry_exits_2_and_writes_nothing(self, tmp_path):
        assert run(tmp_path, {"tables": []}) == 2
        assert not (tmp_path / "supabase").exists()

    def test_a_change_writes_a_second_migration_and_updates_the_state(self, tmp_path):
        run(tmp_path, fixture_registry())
        reg = fixture_registry()
        table(reg, "dim_player")["columns"].append(col("born", "date"))
        assert run(tmp_path, reg, now=LATER) == 0
        files = migrations(tmp_path)
        assert [f.name for f in files] == ["20261031120005_initial_schema.sql",
                                           "20261101093000_registry_update.sql"]
        second = files[1].read_text(encoding="utf-8")
        assert second.endswith("ALTER TABLE football.dim_player ADD COLUMN born date;\n")
        state_bytes = (tmp_path / "supabase" / "registry_state.json").read_bytes()
        assert second.splitlines()[0] == f"-- registry_state sha256: {hashlib.sha256(state_bytes).hexdigest()}"
        assert json.loads(state_bytes) == model(reg)

    def test_a_name_may_be_given(self, tmp_path):
        assert run(tmp_path, fixture_registry(), "--name", "first_cut") == 0
        assert migrations(tmp_path)[0].name == "20261031120005_first_cut.sql"

    @pytest.mark.parametrize("bad", ["Has Space", "1st", "a-b"])
    def test_a_bad_name_is_refused(self, tmp_path, bad):
        assert run(tmp_path, fixture_registry(), "--name", bad) == 2
        assert not (tmp_path / "supabase").exists()

    @pytest.mark.parametrize("case", REFUSED_CHANGES)
    def test_a_refused_change_exits_1_and_writes_nothing(self, tmp_path, capsys, case):
        run(tmp_path, fixture_registry())
        state = tmp_path / "supabase" / "registry_state.json"
        before_state, before_files = state.read_bytes(), migrations(tmp_path)
        capsys.readouterr()
        mutate, message = REFUSED_CHANGES[case]
        assert run(tmp_path, _broken(mutate), now=LATER) == 1
        assert message in capsys.readouterr().err
        assert migrations(tmp_path) == before_files
        assert state.read_bytes() == before_state

    def test_a_registry_that_breaks_a_rule_exits_2_and_writes_nothing(self, tmp_path, capsys):
        assert run(tmp_path, _broken(REFUSED_REGISTRIES["reserved select"])) == 2
        assert "reserved word" in capsys.readouterr().err
        assert not (tmp_path / "supabase").exists()

    def test_a_missing_registry_file_exits_2(self, tmp_path):
        assert gm.main(["--registry", str(tmp_path / "none.yml"), "--out", str(tmp_path / "s")]) == 2

    def test_a_damaged_state_file_exits_2(self, tmp_path):
        run(tmp_path, fixture_registry())
        (tmp_path / "supabase" / "registry_state.json").write_text("{not json", encoding="utf-8")
        assert run(tmp_path, fixture_registry(), now=LATER) == 2

    def test_an_existing_migration_of_the_same_second_is_not_overwritten(self, tmp_path):
        run(tmp_path, fixture_registry())
        reg = fixture_registry()
        table(reg, "dim_player")["columns"].append(col("born", "date"))
        before = migrations(tmp_path)[0].read_bytes()
        assert run(tmp_path, reg, "--name", "initial_schema") == 2
        assert migrations(tmp_path)[0].read_bytes() == before

    def test_the_default_paths_are_the_real_registry_and_supabase_folder(self, monkeypatch):
        monkeypatch.undo()
        assert gm.REGISTRY_FILE == REPO / "docs" / "data_model.yml"
        assert gm.OUT_DIR == REPO / "supabase"

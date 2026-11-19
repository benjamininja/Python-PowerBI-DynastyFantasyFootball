"""The generator's forms for schema `app` (ADR-0025, #548 brief 2): a schema not
granted the blanket way, a policy named in the registry, a column default, and a
trigger with its function. Every case runs on a fixture registry and reads the
SQL as text; none connects to a database."""
import copy
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import generate_migrations as gm
from test_generate_migrations import NOW, LATER, col, fixture_registry, migrations, run

STAMP = {"name": "stamped_at", "sql_type": "timestamptz", "default": "clock_timestamp()"}
USING = "EXISTS (SELECT 1 FROM ops.deadline d WHERE d.season_id = choices.season_id)"
STAMP_BODY = "BEGIN\n    NEW.stamped_at := clock_timestamp();\n    RETURN NEW;\nEND;"
GUARD_BODY = "BEGIN\n    RETURN NULL;\nEND;"


def app_registry():
    reg = fixture_registry()
    reg["other_tables"] += [
        {"name": "choices", "schema": "app", "pk": ["season_id", "team_key"],
         "required_keys": ["choice", "stamped_at"],
         "columns": [col("season_id"), col("team_key"), col("choice"), copy.deepcopy(STAMP)],
         "fk": [{"columns": ["team_key"], "to": "dim_team", "ref": ["team_key"]}],
         "grants": [{"role": "etl_writer", "privileges": ["SELECT"]}],
         "policies": [{"name": "etl_writer_select_open", "role": "etl_writer", "command": "SELECT",
                       "using": USING}],
         "triggers": [{"name": "choices_stamp", "timing": "BEFORE", "events": ["UPDATE"],
                       "level": "ROW", "function": "ops.stamp"}]},
        {"name": "deadline", "schema": "ops", "pk": ["season_id"],
         "columns": [col("season_id"), col("deadline_at", "timestamptz")],
         "triggers": [{"name": "deadline_guard", "timing": "BEFORE", "events": ["DELETE", "UPDATE"],
                       "level": "ROW", "function": "ops.guard"},
                      {"name": "deadline_empty", "timing": "BEFORE", "events": ["TRUNCATE"],
                       "level": "STATEMENT", "function": "ops.guard"}]},
    ]
    reg["trigger_functions"] = [{"name": "ops.stamp", "body": STAMP_BODY},
                                {"name": "ops.guard", "body": GUARD_BODY}]
    return reg


def sql_of(reg=None):
    return gm.render(gm.diff(gm.EMPTY_MODEL, gm.desired_model(reg or app_registry())))


def entry(reg, name):
    return next(t for t in reg["other_tables"] if t["name"] == name)


def broken(mutate):
    reg = app_registry()
    mutate(reg)
    return reg


def refused(reg, fragment):
    with pytest.raises(gm.RegistryError, match=fragment):
        gm.desired_model(reg)


class TestASchemaNotGrantedTheBlanketWay:
    def test_the_schema_is_created_and_the_table_has_row_level_security(self):
        sql = sql_of()
        assert "CREATE SCHEMA app;" in sql
        assert "ALTER TABLE app.choices ENABLE ROW LEVEL SECURITY;" in sql

    def test_the_writer_gets_usage_once_and_the_one_grant_the_table_names(self):
        sql = sql_of()
        assert sql.count("GRANT USAGE ON SCHEMA app TO etl_writer;") == 1
        assert "GRANT SELECT ON app.choices TO etl_writer;" in sql

    def test_no_role_but_the_writer_is_granted_anything_on_app(self):
        sql = sql_of()
        app_lines = [s for s in sql.split("\n\n") if "app" in s and ("GRANT" in s or "POLICY" in s)]
        assert app_lines and all("etl_writer" in s for s in app_lines)
        for word in ("etl_reader", "anon", "authenticated", "PUBLIC"):
            assert not any(word in s for s in app_lines)

    def test_no_blanket_grant_and_no_open_policy_on_app(self):
        sql = sql_of()
        assert "ON app.choices TO etl_writer;" in sql
        assert "GRANT SELECT, INSERT, UPDATE, DELETE ON app." not in sql
        assert "etl_writer_all ON app." not in sql and "etl_reader_select ON app." not in sql
        assert "USING (true)" not in "".join(s for s in sql.split("\n\n") if "app.choices" in s)

    def test_a_table_in_app_with_no_grants_is_granted_nothing(self):
        reg = broken(lambda r: [entry(r, "choices").pop(k) for k in ("grants", "policies")])
        sql = sql_of(reg)
        assert "ENABLE ROW LEVEL SECURITY" in sql
        assert not [s for s in sql.split("\n\n") if "app" in s and ("GRANT" in s or "POLICY" in s)]

    def test_football_and_ops_still_take_the_blanket_grant(self):
        sql = sql_of()
        assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ops.deadline TO etl_writer;" in sql
        assert "CREATE POLICY etl_reader_select ON ops.deadline FOR SELECT TO etl_reader USING (true);" in sql

    def test_the_state_holds_the_schema_last(self):
        assert gm.desired_model(app_registry())["schemas"] == ["football", "shared", "ops", "app"]


class TestANamedPolicy:
    def test_renders_one_policy_for_the_command_and_role(self):
        assert (f"CREATE POLICY etl_writer_select_open ON app.choices FOR SELECT TO etl_writer "
                f"USING ({USING});") in sql_of()

    def test_an_insert_policy_takes_a_check(self):
        def mutate(r):
            t = entry(r, "choices")
            t["grants"][0]["privileges"] = ["INSERT", "SELECT"]
            t["policies"].append({"name": "put", "role": "etl_writer", "command": "INSERT", "check": "true"})
        assert "FOR INSERT TO etl_writer WITH CHECK (true);" in sql_of(broken(mutate))

    def test_an_update_policy_takes_both(self):
        def mutate(r):
            t = entry(r, "choices")
            t["grants"][0]["privileges"] = ["SELECT", "UPDATE"]
            t["policies"].append({"name": "change", "role": "etl_writer", "command": "UPDATE",
                                  "using": "true", "check": "choice <> ''"})
        assert "FOR UPDATE TO etl_writer USING (true) WITH CHECK (choice <> '');" in sql_of(broken(mutate))

    def test_privileges_are_written_in_one_order(self):
        def mutate(r):
            entry(r, "choices")["grants"][0]["privileges"] = ["UPDATE", "SELECT"]
            entry(r, "choices")["policies"] = []
        assert "GRANT SELECT, UPDATE ON app.choices TO etl_writer;" in sql_of(broken(mutate))

    def test_a_policy_needs_a_grant_of_its_command(self):
        def mutate(r):
            entry(r, "choices")["policies"][0]["command"] = "DELETE"
        refused(broken(mutate), "no DELETE grant")

    def test_a_policy_with_no_grant_to_its_role_is_refused(self):
        refused(broken(lambda r: entry(r, "choices").pop("grants")), "no SELECT grant")

    def test_a_select_policy_takes_no_check(self):
        refused(broken(lambda r: entry(r, "choices")["policies"][0].update(check="true")), "takes no check")

    def test_an_insert_policy_takes_no_using(self):
        def mutate(r):
            t = entry(r, "choices")
            t["grants"][0]["privileges"] = ["INSERT"]
            t["policies"] = [{"name": "put", "role": "etl_writer", "command": "INSERT", "using": "true"}]
        refused(broken(mutate), "takes no using")

    def test_a_policy_needs_an_expression(self):
        refused(broken(lambda r: entry(r, "choices")["policies"][0].pop("using")), "needs using")

    @pytest.mark.parametrize("bad", ["true; DROP TABLE x", "true -- x", "true /* x */", ""])
    def test_an_expression_may_not_hold_a_statement_or_a_comment(self, bad):
        refused(broken(lambda r: entry(r, "choices")["policies"][0].update(using=bad)), "expression|may not hold")

    def test_a_policy_name_is_declared_once(self):
        def mutate(r):
            t = entry(r, "choices")
            t["policies"].append(dict(t["policies"][0]))
        refused(broken(mutate), "declared twice")

    def test_a_policy_in_a_blanket_schema_is_refused(self):
        def mutate(r):
            entry(r, "deadline")["policies"] = [{"name": "p", "role": "etl_writer", "command": "SELECT",
                                                 "using": "true"}]
        refused(broken(mutate), "policies are for a table in app only")

    def test_a_policy_for_another_role_is_refused(self):
        refused(broken(lambda r: entry(r, "choices")["policies"][0].update(role="etl_reader")), "not one of etl_writer")


class TestGrantRules:
    def test_a_grant_in_a_blanket_schema_is_refused(self):
        refused(broken(lambda r: entry(r, "deadline").update(grants=[{"role": "etl_writer", "privileges": ["SELECT"]}])),
                "grants are for a table in app only")

    def test_a_grant_on_shared_is_refused(self):
        refused(broken(lambda r: entry(r, "owner").update(grants=[{"role": "etl_writer", "privileges": ["SELECT"]}])),
                "grants are for a table in app only")

    @pytest.mark.parametrize("role", ["etl_reader", "anon", "authenticated", "public", None])
    def test_a_grant_to_any_role_but_the_writer_is_refused(self, role):
        refused(broken(lambda r: entry(r, "choices").update(grants=[{"role": role, "privileges": ["SELECT"]}])),
                "not one of etl_writer")

    def test_a_privilege_outside_the_four_is_refused(self):
        refused(broken(lambda r: entry(r, "choices")["grants"][0].update(privileges=["TRUNCATE"])), "is not one of SELECT")

    def test_a_role_is_granted_once(self):
        def mutate(r):
            t = entry(r, "choices")
            t["grants"].append(dict(t["grants"][0]))
        refused(broken(mutate), "two grants to etl_writer")

    def test_a_grant_with_no_privilege_is_refused(self):
        refused(broken(lambda r: entry(r, "choices")["grants"][0].pop("privileges")), "expected a column name")


class TestAColumnDefault:
    def test_renders_after_not_null(self):
        assert "stamped_at timestamptz NOT NULL DEFAULT clock_timestamp()" in sql_of()

    def test_a_column_without_a_default_renders_as_before(self):
        assert "    choice text NOT NULL,\n" in sql_of()

    def test_the_state_holds_a_default_only_where_one_is_declared(self):
        cols = {c["name"]: c for c in gm.desired_model(app_registry())["tables"]["app.choices"]["columns"]}
        assert cols["stamped_at"]["default"] == "clock_timestamp()"
        assert "default" not in cols["choice"]

    def test_a_new_column_with_a_default_is_added_with_it(self):
        old = gm.desired_model(fixture_registry())
        reg = fixture_registry()
        reg["tables"][0]["columns"].append({"name": "seen", "dtype": "str", "sql_type": "timestamptz",
                                            "default": "clock_timestamp()"})
        assert ("ALTER TABLE football.dim_team ADD COLUMN seen timestamptz DEFAULT clock_timestamp();"
                in gm.render(gm.diff(old, gm.desired_model(reg))))

    @pytest.mark.parametrize("bad", ["now(); DROP", "now() -- x", ""])
    def test_a_default_may_not_hold_a_statement_or_a_comment(self, bad):
        reg = broken(lambda r: entry(r, "choices")["columns"][3].update(default=bad))
        refused(reg, "default")

    def test_adding_a_default_to_a_column_already_there_is_refused(self):
        old = gm.desired_model(app_registry())
        new = copy.deepcopy(old)
        new["tables"]["app.choices"]["columns"][2]["default"] = "''"
        assert "app.choices.choice: change of default" in gm.diff(old, new)["refusals"]

    def test_changing_or_removing_a_default_is_refused(self):
        old = gm.desired_model(app_registry())
        changed = copy.deepcopy(old)
        changed["tables"]["app.choices"]["columns"][3]["default"] = "now()"
        removed = copy.deepcopy(old)
        del removed["tables"]["app.choices"]["columns"][3]["default"]
        for new in (changed, removed):
            assert "app.choices.stamped_at: change of default" in gm.diff(old, new)["refusals"]


class TestATriggerWithItsFunction:
    def test_the_function_is_in_ops_with_the_search_path_empty_and_is_not_a_definer(self):
        sql = sql_of()
        assert ("CREATE FUNCTION ops.stamp() RETURNS trigger\nLANGUAGE plpgsql SET search_path = ''\n"
                f"AS $fn$\n{STAMP_BODY}\n$fn$;") in sql
        assert "SECURITY DEFINER" not in sql.split("CREATE FUNCTION ops.stamp")[1].split("CREATE TRIGGER")[0]

    def test_execute_is_revoked_from_public_and_granted_to_no_one(self):
        sql = sql_of()
        assert "REVOKE EXECUTE ON FUNCTION ops.stamp() FROM PUBLIC;" in sql
        assert "REVOKE EXECUTE ON FUNCTION ops.guard() FROM PUBLIC;" in sql
        assert "GRANT EXECUTE ON FUNCTION ops.stamp" not in sql
        assert "GRANT EXECUTE ON FUNCTION ops.guard" not in sql

    def test_each_function_comes_before_the_triggers(self):
        sql = sql_of()
        first_trigger = sql.index("CREATE TRIGGER")
        assert sql.index("CREATE FUNCTION ops.stamp") < first_trigger
        assert sql.index("CREATE FUNCTION ops.guard") < first_trigger

    def test_renders_a_row_trigger_with_its_events_in_one_order(self):
        assert ("CREATE TRIGGER deadline_guard BEFORE UPDATE OR DELETE ON ops.deadline FOR EACH ROW "
                "EXECUTE FUNCTION ops.guard();") in sql_of()
        assert ("CREATE TRIGGER choices_stamp BEFORE UPDATE ON app.choices FOR EACH ROW "
                "EXECUTE FUNCTION ops.stamp();") in sql_of()

    def test_renders_a_statement_trigger_for_a_truncate(self):
        assert ("CREATE TRIGGER deadline_empty BEFORE TRUNCATE ON ops.deadline FOR EACH STATEMENT "
                "EXECUTE FUNCTION ops.guard();") in sql_of()

    def test_two_triggers_may_share_a_function(self):
        sql = sql_of()
        assert sql.count("EXECUTE FUNCTION ops.guard();") == 2 and sql.count("CREATE FUNCTION ops.guard") == 1

    def test_the_state_holds_the_function_sql(self):
        model = gm.desired_model(app_registry())
        assert list(model["trigger_functions"]) == ["ops.guard", "ops.stamp"]
        assert json.loads(gm.dump_state(model)) == model

    def test_a_function_outside_ops_is_refused(self):
        for name in ("app.stamp", "shared.stamp"):
            reg = broken(lambda r: r["trigger_functions"][0].update(name=name))
            refused(reg, "lives in ops")

    def test_a_function_name_is_schema_dot_name(self):
        refused(broken(lambda r: r["trigger_functions"][0].update(name="stamp")), "expected schema.name")

    def test_a_function_needs_a_body(self):
        refused(broken(lambda r: r["trigger_functions"][0].update(body="  ")), "needs a body")

    def test_a_body_may_not_close_the_quote_early(self):
        refused(broken(lambda r: r["trigger_functions"][0].update(body="BEGIN $fn$ END;")), r"\$fn\$")

    def test_a_function_is_declared_once(self):
        refused(broken(lambda r: r["trigger_functions"].append(dict(r["trigger_functions"][0]))), "declared twice")

    def test_a_trigger_names_a_declared_function(self):
        reg = broken(lambda r: entry(r, "choices")["triggers"][0].update(function="ops.missing"))
        refused(reg, "unknown trigger function")

    def test_a_truncate_trigger_stands_alone_at_statement_level(self):
        refused(broken(lambda r: entry(r, "deadline")["triggers"][1].update(level="ROW")), "TRUNCATE stands alone")
        refused(broken(lambda r: entry(r, "deadline")["triggers"][1].update(events=["TRUNCATE", "DELETE"])),
                "TRUNCATE stands alone")

    @pytest.mark.parametrize("field,value,fragment", [
        ("timing", "INSTEAD OF", "timing"), ("level", "TABLE", "level"), ("events", ["SELECT"], "event")])
    def test_a_trigger_field_outside_its_values_is_refused(self, field, value, fragment):
        refused(broken(lambda r: entry(r, "choices")["triggers"][0].update({field: value})), fragment)

    def test_a_trigger_name_is_declared_once(self):
        def mutate(r):
            t = entry(r, "deadline")
            t["triggers"][1]["name"] = t["triggers"][0]["name"]
        refused(broken(mutate), "declared twice")


class TestChangesToAnExistingTable:
    def old(self):
        return gm.desired_model(app_registry())

    def test_the_same_registry_gives_the_same_sql_and_no_change_after_it(self):
        assert sql_of() == sql_of()
        model = self.old()
        assert not gm.has_changes(gm.diff(model, gm.desired_model(app_registry())))

    @pytest.mark.parametrize("field", ["grants", "policies", "triggers"])
    def test_a_change_to_grants_policies_or_triggers_is_refused(self, field):
        old = self.old()
        new = copy.deepcopy(old)
        new["tables"]["app.choices"].pop(field)
        assert f"app.choices: change of {field}" in gm.diff(old, new)["refusals"]

    def test_a_changed_function_body_is_refused(self):
        old = self.old()
        reg = broken(lambda r: r["trigger_functions"][0].update(body="BEGIN RETURN NEW; END;"))
        assert "ops.stamp: change of function body" in gm.diff(old, gm.desired_model(reg))["refusals"]

    def test_a_dropped_trigger_function_is_refused(self):
        old = self.old()
        new = copy.deepcopy(old)
        del new["trigger_functions"]["ops.stamp"]
        assert "ops.stamp: drop of function" in gm.diff(old, new)["refusals"]

    def test_a_state_file_from_before_trigger_functions_loads_as_none(self, tmp_path):
        old = gm.desired_model(fixture_registry())
        legacy = {k: v for k, v in old.items() if k != "trigger_functions"}
        path = tmp_path / gm.STATE_FILE
        path.write_text(json.dumps(legacy), encoding="utf-8")
        assert gm.load_state(path) == old

    def test_a_state_file_with_a_stray_key_is_still_refused(self, tmp_path):
        path = tmp_path / gm.STATE_FILE
        path.write_text(json.dumps({**gm.EMPTY_MODEL, "stray": 1}), encoding="utf-8")
        with pytest.raises(gm.RegistryError):
            gm.load_state(path)

    def test_the_old_tables_keep_their_state_entry_when_they_declare_none_of_it(self):
        entries = gm.desired_model(app_registry())["tables"]
        for key, spec in entries.items():
            if key not in ("app.choices", "ops.deadline"):
                assert not {"grants", "policies", "triggers"} & set(spec), key
                assert all("default" not in c for c in spec["columns"]), key


class TestTheChecker:
    def test_a_registry_the_generator_takes_has_no_error(self):
        import check_data_model as cdm
        assert cdm.model_errors(app_registry()) == []

    def test_the_generators_refusal_is_the_checkers_failure(self):
        import check_data_model as cdm
        errs = cdm.model_errors(broken(lambda r: entry(r, "choices")["grants"][0].update(role="etl_reader")))
        assert len(errs) == 1 and errs[0].startswith("[generator]") and "etl_reader" in errs[0]

    def test_the_checker_takes_its_schemas_from_the_generator(self):
        import check_data_model as cdm
        assert cdm.SCHEMAS == gm.SCHEMAS and "app" in cdm.SCHEMAS


class TestMainOnTheNewForms:
    def test_one_run_writes_the_migration_and_a_second_run_writes_nothing(self, tmp_path):
        reg = app_registry()
        assert run(tmp_path, reg, now=NOW) == 0
        (path,) = migrations(tmp_path)[:1] or [None]
        assert path is not None and "CREATE SCHEMA app;" in path.read_text(encoding="utf-8")
        before = sorted(p.name for p in (tmp_path / "supabase").rglob("*"))
        assert run(tmp_path, reg, now=LATER) == 0
        assert sorted(p.name for p in (tmp_path / "supabase").rglob("*")) == before

    def test_a_broken_registry_exits_2_and_writes_nothing(self, tmp_path):
        reg = broken(lambda r: entry(r, "choices")["grants"][0].update(role="etl_reader"))
        assert run(tmp_path, reg, now=NOW) == 2
        assert not (tmp_path / "supabase").exists()

    def test_a_later_change_to_a_policy_exits_1_and_writes_nothing_new(self, tmp_path):
        assert run(tmp_path, app_registry(), now=NOW) == 0
        before = sorted(p.name for p in (tmp_path / "supabase").rglob("*"))
        reg = broken(lambda r: entry(r, "choices")["policies"][0].update(using="true"))
        assert run(tmp_path, reg, now=LATER) == 1
        assert sorted(p.name for p in (tmp_path / "supabase").rglob("*")) == before

    def test_a_first_run_from_the_committed_state_adds_only_what_the_registry_adds(self):
        committed = gm.load_state(REPO / "supabase" / gm.STATE_FILE)
        assert "app.contract_choices" in committed["tables"] and "ops.choice_deadline" in committed["tables"]
        assert set(committed["trigger_functions"]) == {"ops.refuse_passed_deadline_change", "ops.set_changed_at"}

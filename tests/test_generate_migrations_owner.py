"""The generator's forms for the owner write path (ADR-0025, #548 brief 3): column
grants, grants and policies added to a table that exists, the owner crosswalk and
the two SECURITY DEFINER functions of `shared`. Every case runs on a fixture
registry and reads the SQL as text; none connects to a database."""
import copy
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import generate_migrations as gm
from test_generate_migrations import col
from test_generate_migrations_app import app_registry, broken, entry, refused, sql_of

AUTH = {"role": "authenticated", "privileges": ["SELECT", "INSERT", "UPDATE"],
        "columns": {"INSERT": ["season_id", "team_key", "choice"], "UPDATE": ["choice"]}}
OWN = {"name": "signed_in_select", "role": "authenticated", "command": "SELECT",
       "using": "team_key IN (SELECT shared.caller_team_keys())"}


def crosswalk_registry():
    reg = app_registry()
    reg["other_tables"].append(
        {"name": "owner_crosswalk", "schema": "shared", "pk": ["team_key", "discord_user_id"],
         "columns": [col("team_key"), col("discord_user_id")],
         "fk": [{"columns": ["team_key"], "to": "dim_team", "ref": ["team_key"]}]})
    return reg


def with_authenticated(reg):
    entry(reg, "choices")["grants"].append(copy.deepcopy(AUTH))
    entry(reg, "choices")["policies"].append(copy.deepcopy(OWN))
    return reg


class TestAColumnGrant:
    def test_a_privilege_with_columns_is_granted_on_those_columns_and_the_rest_on_the_table(self):
        sql = sql_of(with_authenticated(app_registry()))
        assert "GRANT SELECT ON app.choices TO authenticated;" in sql
        assert "GRANT INSERT (season_id, team_key, choice) ON app.choices TO authenticated;" in sql
        assert "GRANT UPDATE (choice) ON app.choices TO authenticated;" in sql
        assert "ON app.choices TO authenticated;" in sql and "GRANT INSERT, " not in sql

    def test_a_grant_with_no_columns_key_renders_as_before(self):
        assert "GRANT SELECT ON app.choices TO etl_writer;" in sql_of()

    def test_the_state_holds_the_columns_only_where_declared(self):
        grants = gm.desired_model(with_authenticated(app_registry()))["tables"]["app.choices"]["grants"]
        assert grants[0] == {"role": "etl_writer", "privileges": ["SELECT"]}
        assert grants[1]["columns"] == {"INSERT": ["season_id", "team_key", "choice"], "UPDATE": ["choice"]}

    @pytest.mark.parametrize("columns,fragment", [
        ({"INSERT": ["nope"]}, "unknown column"),
        ({"SELECT": ["choice"]}, "is not one of INSERT, UPDATE"),
        ({"DELETE": ["choice"]}, "is not one of INSERT, UPDATE"),
        ({}, "expected a mapping"),
        ({"INSERT": []}, "expected a column name"),
        ({"INSERT": ["choice", "choice"]}, "named twice")])
    def test_a_columns_key_that_breaks_a_rule_is_refused(self, columns, fragment):
        reg = with_authenticated(app_registry())
        entry(reg, "choices")["grants"][1]["columns"] = columns
        refused(reg, fragment)

    def test_a_column_privilege_the_grant_does_not_hold_is_refused(self):
        reg = with_authenticated(app_registry())
        entry(reg, "choices")["grants"][1]["privileges"] = ["SELECT", "INSERT"]
        refused(reg, "which the grant does not hold")


class TestTheFirstGrantToAuthenticated:
    def test_the_schema_usage_comes_with_a_revoke_of_what_anon_could_inherit(self):
        sql = sql_of(with_authenticated(app_registry()))
        assert sql.count("GRANT USAGE ON SCHEMA app TO authenticated;") == 1
        for line in ("REVOKE ALL ON SCHEMA app FROM anon;", "REVOKE ALL ON ALL TABLES IN SCHEMA app FROM anon;",
                     "ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE ALL ON TABLES FROM anon;"):
            assert sql.count(line) == 1

    def test_no_revoke_is_written_while_no_authenticated_grant_exists(self):
        assert "FROM anon" not in sql_of()

    def test_nothing_is_ever_granted_to_anon_or_to_public(self):
        sql = sql_of(with_authenticated(app_registry()))
        assert not [s for s in sql.split("\n\n") if s.startswith("GRANT") and (" anon" in s or "PUBLIC" in s)]


class TestGrantsAndPoliciesAddedToATableThatExists:
    def old(self):
        return gm.desired_model(app_registry())

    def new(self):
        return gm.desired_model(with_authenticated(app_registry()))

    def test_a_new_role_grant_and_a_new_policy_name_are_additions(self):
        changes = gm.diff(self.old(), self.new())
        assert changes["refusals"] == []
        assert [(k, g["role"]) for k, g in changes["grants"]] == [("app.choices", "authenticated")]
        assert [(k, p["name"]) for k, p in changes["policies"]] == [("app.choices", "signed_in_select")]

    def test_they_render_after_the_functions_the_policies_call(self):
        reg = with_authenticated(crosswalk_registry())
        old = gm.desired_model(crosswalk_registry())
        old["functions"] = {}
        sql = gm.render(gm.diff(old, gm.desired_model(reg)))
        assert sql.index("CREATE FUNCTION shared.caller_team_keys") < sql.index("CREATE POLICY signed_in_select")
        assert "GRANT SELECT ON app.choices TO authenticated;" in sql

    def test_the_same_registry_is_no_change(self):
        assert not gm.has_changes(gm.diff(self.new(), self.new()))

    def test_a_changed_existing_policy_is_refused(self):
        old, new = self.new(), self.new()
        new["tables"]["app.choices"]["policies"][-1]["using"] = "true"
        assert "app.choices: change of policies" in gm.diff(old, new)["refusals"]

    def test_a_removed_policy_or_grant_is_refused(self):
        old = self.new()
        for field in ("policies", "grants"):
            new = copy.deepcopy(old)
            new["tables"]["app.choices"][field].pop()
            assert f"app.choices: change of {field}" in gm.diff(old, new)["refusals"]

    def test_widening_an_existing_grant_is_refused(self):
        old = self.new()
        new = copy.deepcopy(old)
        new["tables"]["app.choices"]["grants"][0]["privileges"] = ["SELECT", "UPDATE"]
        assert "app.choices: change of grants" in gm.diff(old, new)["refusals"]

    def test_a_changed_trigger_is_still_refused(self):
        old = self.new()
        new = copy.deepcopy(old)
        new["tables"]["app.choices"]["triggers"] = []
        assert "app.choices: change of triggers" in gm.diff(old, new)["refusals"]


class TestTheOwnerCrosswalkAndItsFunctions:
    def sql(self):
        return sql_of(crosswalk_registry())

    def test_the_crosswalk_has_rls_on_and_no_grant_and_no_policy(self):
        sql = self.sql()
        assert "ALTER TABLE shared.owner_crosswalk ENABLE ROW LEVEL SECURITY;" in sql
        assert not [s for s in sql.split("\n\n") if "shared.owner_crosswalk" in s and
                    (s.startswith("GRANT") or s.startswith("CREATE POLICY"))]

    def test_two_definer_functions_are_written_with_the_search_path_empty(self):
        model = gm.desired_model(crosswalk_registry())
        assert set(model["functions"]) == {"shared.pii_token_hashes", "shared.caller_team_keys",
                                           "shared.choice_window"}
        for name in ("shared.caller_team_keys", "shared.choice_window"):
            sql = model["functions"][name]
            assert "SECURITY DEFINER SET search_path = ''" in sql

    def test_execute_is_revoked_from_public_and_granted_to_authenticated_only(self):
        sql = self.sql()
        for call in ("shared.caller_team_keys()", "shared.choice_window(text, text)"):
            assert f"REVOKE EXECUTE ON FUNCTION {call} FROM PUBLIC;" in sql
            assert f"GRANT EXECUTE ON FUNCTION {call} TO authenticated;" in sql
            assert f"GRANT EXECUTE ON FUNCTION {call} TO etl_writer;" not in sql
        assert "GRANT EXECUTE ON FUNCTION shared.pii_token_hashes() TO etl_writer;" in sql
        assert "GRANT EXECUTE ON FUNCTION shared.pii_token_hashes() TO authenticated;" not in sql

    def test_authenticated_gets_usage_on_shared_once_and_nothing_else_there(self):
        sql = self.sql()
        assert sql.count("GRANT USAGE ON SCHEMA shared TO authenticated;") == 1
        assert "ON shared.owner" not in "".join(s for s in sql.split("\n\n") if s.startswith("GRANT"))

    def test_the_id_comes_from_auth_identities_and_never_from_metadata(self):
        sql = gm.desired_model(crosswalk_registry())["functions"]["shared.caller_team_keys"]
        assert "auth.identities" in sql and "i.provider = 'discord'" in sql
        assert "i.provider_id = c.discord_user_id" in sql and "i.user_id = auth.uid()" in sql
        assert "metadata" not in sql.lower()

    def test_the_window_function_has_four_answers_and_no_row_is_none(self):
        sql = gm.desired_model(crosswalk_registry())["functions"]["shared.choice_window"]
        for word in ("'open'", "'passed'", "'final'", "'none'"):
            assert word in sql
        assert "d.final_at <= clock_timestamp()" in sql and "d.deadline_at > clock_timestamp()" in sql
        assert sql.index("'final'") < sql.index("'open'") < sql.index("'passed'")

    def test_a_crosswalk_with_a_deadline_table_that_has_no_final_at_is_refused(self):
        reg = crosswalk_registry()
        entry(reg, "choice_deadline")["columns"] = [c for c in entry(reg, "choice_deadline")["columns"]
                                                    if c["name"] != "final_at"]
        refused(reg, "unknown column 'final_at'")

    def test_no_function_is_added_when_the_crosswalk_is_not_declared(self):
        assert set(gm.desired_model(app_registry())["functions"]) == {"shared.pii_token_hashes"}

    def test_a_crosswalk_without_the_deadline_table_is_refused(self):
        reg = crosswalk_registry()
        reg["other_tables"] = [t for t in reg["other_tables"] if t["name"] != "choice_deadline"]
        refused(reg, "ops.choice_deadline, which is not declared")

    def test_a_crosswalk_without_its_two_columns_is_refused(self):
        reg = crosswalk_registry()
        entry(reg, "owner_crosswalk")["columns"][1]["name"] = "other"
        entry(reg, "owner_crosswalk")["pk"] = ["team_key", "other"]
        refused(reg, "unknown column 'discord_user_id'")

    def test_a_grant_on_the_crosswalk_is_refused(self):
        reg = crosswalk_registry()
        entry(reg, "owner_crosswalk")["grants"] = [{"role": "authenticated", "privileges": ["SELECT"]}]
        refused(reg, "grants are for a table in app")


class TestThePiiHashFunctionGainsTheCrosswalk:
    def test_with_the_crosswalk_the_list_also_holds_each_id_and_still_splits_names(self):
        sql = gm.desired_model(crosswalk_registry())["functions"]["shared.pii_token_hashes"]
        assert "SELECT c.discord_user_id FROM shared.owner_crosswalk c" in sql
        assert "regexp_split_to_table(lower(o.human_name), '[[:space:]]+')" in sql
        assert "lower(o.fantrax_username)" in sql

    def test_the_function_body_has_no_backslash_the_gate_would_hold(self):
        assert "\\" not in gm.desired_model(crosswalk_registry())["functions"]["shared.pii_token_hashes"]

    def test_without_the_crosswalk_the_body_is_the_old_one(self):
        assert gm.desired_model(app_registry())["functions"]["shared.pii_token_hashes"] == gm.PII_FUNCTION_SQL

    def test_a_state_with_the_old_body_gets_create_or_replace_and_nothing_else(self):
        old = gm.desired_model(crosswalk_registry())
        old["functions"]["shared.pii_token_hashes"] = gm.PII_FUNCTION_SQL
        changes = gm.diff(old, gm.desired_model(crosswalk_registry()))
        assert changes["refusals"] == []
        sql = gm.render(changes)
        assert sql.startswith("CREATE OR REPLACE FUNCTION shared.pii_token_hashes() RETURNS SETOF text")
        assert sql.count("CREATE ") == 1 and "GRANT" not in sql and "REVOKE" not in sql

    def test_a_changed_definer_function_body_is_still_refused(self):
        old = gm.desired_model(crosswalk_registry())
        new = copy.deepcopy(old)
        new["functions"]["shared.caller_team_keys"] += " "
        assert "shared.caller_team_keys: change of function body" in gm.diff(old, new)["refusals"]


def roles_registry():
    reg = crosswalk_registry()
    reg["tables"].append({"name": "dim_fantasy_teams", "type": "dim", "grain": "team_key", "pk": ["team_key"],
                          "columns": [col("team_key")]})
    reg["other_tables"].append(
        {"name": "app_role", "schema": "shared", "pk": ["discord_user_id", "role", "league_key"],
         "columns": [col("discord_user_id"), col("role"), col("league_key")]})
    return reg


class TestTheRoleTableAndItsTwoChecks:
    """shared.app_role (#662, ADR-0026 decisions 1 to 3): no grant, no policy, two
    definer functions after shared.caller_team_keys, and its ids in the hash list."""
    def sql(self):
        return sql_of(roles_registry())

    def test_the_table_has_rls_on_and_no_grant_and_no_policy(self):
        sql = self.sql()
        assert "ALTER TABLE shared.app_role ENABLE ROW LEVEL SECURITY;" in sql
        assert not [s for s in sql.split("\n\n") if "shared.app_role" in s and
                    (s.startswith("GRANT") or s.startswith("CREATE POLICY"))]

    def test_a_grant_or_a_policy_on_the_role_table_is_refused(self):
        reg = roles_registry()
        entry(reg, "app_role")["grants"] = [{"role": "authenticated", "privileges": ["SELECT"]}]
        refused(reg, "grants are for a table in app")

    def test_the_two_functions_are_added_beside_the_three_and_no_others(self):
        model = gm.desired_model(roles_registry())
        assert set(model["functions"]) == {"shared.pii_token_hashes", "shared.caller_team_keys",
                                           "shared.choice_window", "shared.caller_is_commissioner_for",
                                           "shared.caller_is_site_admin"}
        assert gm.desired_model(crosswalk_registry())["functions"].keys() == {
            "shared.pii_token_hashes", "shared.caller_team_keys", "shared.choice_window"}

    def test_both_are_definers_with_the_search_path_empty_and_execute_for_authenticated_alone(self):
        sql = self.sql()
        model = gm.desired_model(roles_registry())
        for name, call in (("shared.caller_is_commissioner_for", "shared.caller_is_commissioner_for(text)"),
                           ("shared.caller_is_site_admin", "shared.caller_is_site_admin()")):
            assert "SECURITY DEFINER SET search_path = ''" in model["functions"][name]
            assert f"REVOKE EXECUTE ON FUNCTION {call} FROM PUBLIC;" in sql
            assert f"GRANT EXECUTE ON FUNCTION {call} TO authenticated;" in sql
            assert f"GRANT EXECUTE ON FUNCTION {call} TO etl_writer;" not in sql
        assert sql.count("GRANT USAGE ON SCHEMA shared TO authenticated;") == 1

    def test_the_commissioner_check_takes_the_team_and_never_asks_about_the_person_alone(self):
        sql = gm.desired_model(roles_registry())["functions"][gm.COMMISSIONER_FUNCTION]
        assert "(p_team_key text) RETURNS boolean" in sql
        assert "JOIN football.dim_fantasy_teams t ON t.team_key = p_team_key" in sql
        assert "r.role = 'commissioner'" in sql and f"r.league_key = '{gm.LEAGUE_PLACEHOLDER}'" in sql

    def test_the_site_admin_check_asks_for_the_role_and_every_league(self):
        sql = gm.desired_model(roles_registry())["functions"][gm.ADMIN_FUNCTION]
        assert "shared.caller_is_site_admin() RETURNS boolean" in sql
        assert "r.role = 'site_admin'" in sql and f"r.league_key = '{gm.ALL_LEAGUES}'" in sql

    def test_both_read_the_id_from_auth_identities_for_the_caller_and_never_from_metadata(self):
        model = gm.desired_model(roles_registry())
        for name in (gm.COMMISSIONER_FUNCTION, gm.ADMIN_FUNCTION):
            sql = model["functions"][name]
            assert "auth.identities" in sql and "i.provider = 'discord'" in sql
            assert "i.provider_id = r.discord_user_id" in sql and "i.user_id = auth.uid()" in sql
            assert "metadata" not in sql.lower()

    def test_the_hash_list_also_holds_each_role_id_and_the_body_has_no_backslash(self):
        sql = gm.desired_model(roles_registry())["functions"][gm.PII_FUNCTION]
        assert "SELECT r.discord_user_id FROM shared.app_role r" in sql
        assert "SELECT c.discord_user_id FROM shared.owner_crosswalk c" in sql
        assert "encode(sha256(convert_to(s.token, 'UTF8')), 'hex')" in sql and "\\" not in sql

    def test_a_state_with_the_crosswalk_only_gets_the_two_functions_and_a_replacement_of_the_hash_list(self):
        old = gm.desired_model(crosswalk_registry())
        old["tables"]["football.dim_fantasy_teams"] = gm.desired_model(roles_registry())["tables"][
            "football.dim_fantasy_teams"]
        changes = gm.diff(old, gm.desired_model(roles_registry()))
        assert changes["refusals"] == []
        sql = gm.render(changes)
        assert sql.count("CREATE FUNCTION") == 2 and sql.count("CREATE OR REPLACE FUNCTION shared.pii_token_hashes") == 1
        assert "GRANT EXECUTE ON FUNCTION shared.pii_token_hashes" not in sql

    def test_the_role_table_without_the_crosswalk_is_refused(self):
        reg = roles_registry()
        reg["other_tables"] = [t for t in reg["other_tables"] if t["name"] != "owner_crosswalk"]
        refused(reg, "the owner crosswalk is not declared")

    def test_the_role_table_without_the_teams_table_is_refused(self):
        reg = roles_registry()
        reg["tables"] = [t for t in reg["tables"] if t["name"] != "dim_fantasy_teams"]
        refused(reg, "football.dim_fantasy_teams, which is not declared")

    def test_the_role_table_without_its_three_columns_is_refused(self):
        reg = roles_registry()
        entry(reg, "app_role")["columns"][2]["name"] = "other"
        entry(reg, "app_role")["pk"] = ["discord_user_id", "role", "other"]
        refused(reg, "unknown column 'league_key'")

    def test_a_changed_body_of_either_check_is_refused(self):
        old = gm.desired_model(roles_registry())
        for name in (gm.COMMISSIONER_FUNCTION, gm.ADMIN_FUNCTION):
            new = copy.deepcopy(old)
            new["functions"][name] += " "
            assert f"{name}: change of function body" in gm.diff(old, new)["refusals"]


class TestTheWindowFunctionGainsFinal:
    """shared.choice_window() is replaced in place (#661): CREATE OR REPLACE keeps its
    REVOKE and its one GRANT, so the migration writes neither again."""
    OLD_BODY = ("CREATE FUNCTION shared.choice_window(p_season_id text, p_choice_kind text) RETURNS text\n"
                "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''\nAS $fn$\n"
                "    SELECT coalesce((SELECT CASE WHEN d.deadline_at > clock_timestamp() THEN 'open' ELSE 'passed' END\n"
                "         FROM ops.choice_deadline d\n"
                "         WHERE d.season_id = p_season_id AND d.choice_kind = p_choice_kind), 'none')\n$fn$;")

    def test_the_function_is_on_the_replaceable_list_beside_the_pii_hash(self):
        assert gm.REPLACEABLE_FUNCTIONS == (gm.PII_FUNCTION, gm.OPEN_FUNCTION)

    def test_a_state_with_the_old_body_gets_create_or_replace_and_nothing_else(self):
        old = gm.desired_model(crosswalk_registry())
        old["functions"][gm.OPEN_FUNCTION] = self.OLD_BODY
        changes = gm.diff(old, gm.desired_model(crosswalk_registry()))
        assert changes["refusals"] == []
        sql = gm.render(changes)
        assert sql.startswith("CREATE OR REPLACE FUNCTION shared.choice_window(p_season_id text, p_choice_kind text)")
        assert "WHEN d.final_at <= clock_timestamp() THEN 'final'" in sql
        assert sql.count("CREATE ") == 1 and "GRANT" not in sql and "REVOKE" not in sql

    def test_a_replacement_keeps_the_function_a_definer_with_the_search_path_empty(self):
        sql = gm.desired_model(crosswalk_registry())["functions"][gm.OPEN_FUNCTION]
        assert "SECURITY DEFINER SET search_path = ''" in sql

    def test_the_other_definer_function_stays_non_replaceable(self):
        old = gm.desired_model(crosswalk_registry())
        new = copy.deepcopy(old)
        new["functions"][gm.TEAMS_FUNCTION] += " "
        assert f"{gm.TEAMS_FUNCTION}: change of function body" in gm.diff(old, new)["refusals"]


class TestTheRealRegistry:
    @pytest.fixture()
    def model(self):
        real = yaml.safe_load((REPO / "docs" / "data_model.yml").read_text(encoding="utf-8"))
        return gm.desired_model(real)

    def test_the_crosswalk_holds_no_grant_and_no_policy_to_any_role(self, model):
        spec = model["tables"]["shared.owner_crosswalk"]
        assert not {"grants", "policies", "triggers"} & set(spec)
        assert spec["pk"] == ["team_key", "discord_user_id"]
        assert [f["to"] for f in spec["fks"]] == ["football.dim_fantasy_teams"]

    def test_both_app_tables_grant_authenticated_by_column_and_never_locked_value_or_changed_at(self, model):
        for key in ("app.contract_choices", "app.team_choice_sharing"):
            (grant,) = [g for g in model["tables"][key]["grants"] if g["role"] == "authenticated"]
            assert grant["privileges"] == ["SELECT", "INSERT", "UPDATE"] and "DELETE" not in grant["privileges"]
            for privilege in ("INSERT", "UPDATE"):
                assert not {"locked_value", "changed_at"} & set(grant["columns"][privilege])
            assert grant["columns"]["UPDATE"][0] in ("choice", "shared")

    def test_no_table_grants_anon_or_etl_reader_anything_on_app(self, model):
        for key, spec in model["tables"].items():
            if spec["schema"] != "app":
                continue
            for item in spec.get("grants", []) + spec.get("policies", []):
                assert item["role"] in ("etl_writer", "authenticated"), key

    def test_the_writer_has_nothing_on_the_sharing_table(self, model):
        assert all(g["role"] != "etl_writer" for g in model["tables"]["app.team_choice_sharing"]["grants"])
        assert all(p["role"] != "etl_writer" for p in model["tables"]["app.team_choice_sharing"]["policies"])

    def test_every_write_policy_holds_changed_by_to_the_caller_and_the_window_open(self, model):
        for key in ("app.contract_choices", "app.team_choice_sharing"):
            for policy in model["tables"][key]["policies"]:
                if policy["command"] in ("INSERT", "UPDATE") and policy["role"] == "authenticated":
                    assert "changed_by = auth.uid()" in policy["check"]
                    assert "shared.caller_team_keys()" in policy["check"] and "'open'" in policy["check"]
        for policy in model["tables"]["app.contract_choices"]["policies"]:
            if policy["command"] in ("INSERT", "UPDATE") and policy["role"] == "authenticated":
                assert "origin = 'app'" in policy["check"]

    def test_the_read_after_the_deadline_asks_for_passed_or_final_so_none_reads_nothing(self, model):
        (policy,) = [p for p in model["tables"]["app.contract_choices"]["policies"]
                     if p["name"] == "signed_in_select_after_deadline"]
        assert policy["using"] == "shared.choice_window(season_id, choice_kind) IN ('passed', 'final')"
        assert "NOT" not in policy["using"]

    def test_the_owner_write_policies_still_ask_for_open_only(self, model):
        for key in ("app.contract_choices", "app.team_choice_sharing"):
            for policy in model["tables"][key]["policies"]:
                if policy["command"] in ("INSERT", "UPDATE") and policy["role"] == "authenticated":
                    assert "'passed'" not in policy["check"] and "'final'" not in policy["check"]
                    assert "origin = 'app'" in policy["check"] or key == "app.team_choice_sharing"

    def test_the_history_table_mirrors_the_three_authenticated_select_policies_and_grants_select_only(self, model):
        choices = {p["name"]: p for p in model["tables"]["app.contract_choices"]["policies"]
                   if p["role"] == "authenticated" and p["command"] == "SELECT"}
        history = {p["name"]: p for p in model["tables"]["app.contract_choice_history"]["policies"]}
        assert sorted(history) == sorted(choices) and len(history) == 3
        for name, policy in history.items():
            assert policy["role"] == "authenticated" and policy["command"] == "SELECT"
            assert policy["using"].replace("contract_choice_history", "contract_choices") == choices[name]["using"]
        assert model["tables"]["app.contract_choice_history"]["grants"] == [
            {"role": "authenticated", "privileges": ["SELECT"]}]

    def test_the_history_table_has_no_etl_grant_and_no_write_grant_to_anyone(self, model):
        spec = model["tables"]["app.contract_choice_history"]
        assert all(g["role"] == "authenticated" and g["privileges"] == ["SELECT"] for g in spec["grants"])
        assert all(p["role"] == "authenticated" for p in spec["policies"])

    def test_the_history_key_columns_are_required_and_the_action_id_is_not(self, model):
        cols = {c["name"]: c for c in model["tables"]["app.contract_choice_history"]["columns"]}
        for name in ("history_id", "season_id", "team_key", "scorer_id", "choice_kind", "choice", "origin",
                     "changed_at", "recorded_at"):
            assert cols[name]["not_null"], name
        assert not cols["action_id"]["not_null"] and not cols["changed_by"]["not_null"]

    def test_the_history_writer_is_the_one_definer_trigger_function_and_its_body_names_every_schema(self, model):
        sql = model["trigger_functions"]["ops.record_choice_history"]
        assert "LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''" in sql
        assert "RETURNS trigger" in sql
        assert [n for n, s in model["trigger_functions"].items() if "SECURITY DEFINER" in s] == \
            ["ops.record_choice_history"]
        assert " FROM contract_choice_history" not in sql and "INTO contract_choice_history" not in sql
        assert "INTO app.contract_choice_history" in sql

    def test_the_deadline_row_that_exists_takes_the_owners_final_instant_by_fill_and_the_check_holds(self, model):
        spec = model["tables"]["ops.choice_deadline"]
        (final,) = [c for c in spec["columns"] if c["name"] == "final_at"]
        assert final["not_null"] and "default" not in final
        assert final["fill"] == "timestamptz '2027-03-01 04:59:59+00'"
        assert "final_at > deadline_at" in spec["checks"]

    def test_origin_accepts_commissioner_and_the_owner_policies_still_hold_it_to_app(self, model):
        spec = model["tables"]["app.contract_choices"]
        assert "origin IN ('loader', 'app', 'commissioner')" in spec["checks"]
        assert "commissioner" not in "".join(str(p.get("check", "")) + str(p.get("using", ""))
                                             for p in spec["policies"])

    def test_the_rule_for_shared_names_exactly_five_functions(self, model):
        assert sorted(gm.FUNCTION_ACCESS) == sorted(model["functions"])
        assert {n.split(".")[0] for n in model["functions"]} == {"shared"}
        grantees = {n: set(roles) for n, (_, roles) in gm.FUNCTION_ACCESS.items()}
        assert grantees == {"shared.pii_token_hashes": {"etl_writer"},
                            "shared.caller_team_keys": {"authenticated"},
                            "shared.choice_window": {"authenticated"},
                            "shared.caller_is_commissioner_for": {"authenticated"},
                            "shared.caller_is_site_admin": {"authenticated"}}

    def test_the_role_table_holds_no_grant_and_no_policy_and_the_league_is_in_its_key(self, model):
        spec = model["tables"]["shared.app_role"]
        assert not {"grants", "policies", "triggers"} & set(spec) and spec["fks"] == []
        assert spec["pk"] == ["discord_user_id", "role", "league_key"]
        assert all(c["not_null"] for c in spec["columns"])
        assert "role IN ('commissioner', 'site_admin')" in spec["checks"]
        assert ("(role = 'site_admin' AND league_key = '*') OR "
                "(role = 'commissioner' AND league_key <> '*')") in spec["checks"]

    def test_no_policy_calls_either_role_check_yet(self, model):
        for key, spec in model["tables"].items():
            for policy in spec.get("policies", []):
                text = f"{policy.get('using', '')} {policy.get('check', '')}"
                assert "caller_is_commissioner_for" not in text and "caller_is_site_admin" not in text, key
        for sql in model["trigger_functions"].values():
            assert "caller_is_" not in sql

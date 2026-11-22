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

    def test_the_window_function_has_three_answers_and_no_row_is_none(self):
        sql = gm.desired_model(crosswalk_registry())["functions"]["shared.choice_window"]
        for word in ("'open'", "'passed'", "'none'"):
            assert word in sql
        assert "d.deadline_at > clock_timestamp()" in sql

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

    def test_the_read_after_the_deadline_asks_for_passed_so_none_reads_nothing(self, model):
        (policy,) = [p for p in model["tables"]["app.contract_choices"]["policies"]
                     if p["name"] == "signed_in_select_after_deadline"]
        assert policy["using"] == "shared.choice_window(season_id, choice_kind) = 'passed'"
        assert "NOT" not in policy["using"]

    def test_the_rule_for_shared_names_exactly_three_functions(self, model):
        assert sorted(gm.FUNCTION_ACCESS) == sorted(model["functions"])
        assert {n.split(".")[0] for n in model["functions"]} == {"shared"}
        grantees = {n: set(roles) for n, (_, roles) in gm.FUNCTION_ACCESS.items()}
        assert grantees == {"shared.pii_token_hashes": {"etl_writer"},
                            "shared.caller_team_keys": {"authenticated"},
                            "shared.choice_window": {"authenticated"}}

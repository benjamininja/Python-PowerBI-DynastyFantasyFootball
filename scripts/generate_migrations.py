"""Generate a Supabase migration from the registry (#108, ADR-0018 decision 3).

    generate_migrations.py [--registry FILE] [--out DIR] [--name NAME]

`desired_model` reads the registry into a plain dict. `diff` compares it with
`<out>/registry_state.json`, the record of what the migrations already hold.
`render` turns the additions into SQL. A drop, a rename or a type change is
refused: the script names it, exits 1 and writes nothing. The one exception
(#443): a check `<col> IN (<literals>)` replaced by another on the same column
whose list holds every old literal is a widening; it becomes DROP CONSTRAINT
then ADD CONSTRAINT in one migration. Anything not exactly that form is
refused as before. The drop path (#534): a column the registry names in its
table's `drops:` list, or a table it names in `dropped_tables:`, becomes
DROP COLUMN or DROP TABLE when the state file still holds it; an entry whose
item the state no longer holds is history and writes nothing. Drops go in a
migration of their own, after the run's other changes. Every other drop
stays refused. A table in a schema in OWN_GRANT_SCHEMAS (ADR-0025) is not
granted the blanket way: it names its own `grants` (to etl_writer or
authenticated, never anon, with an optional `columns` key per privilege) and
`policies`, and so does the one `ops` table in OWN_GRANT_TABLES, which then gets
no blanket grant. On a table that exists, a grant to a role it has none for and
a policy of a new name are added; any other change to them stays refused. The
registry's `shared.owner_crosswalk` brings the two SECURITY DEFINER functions of
FUNCTION_ACCESS, EXECUTE for authenticated only, and the first grant to
authenticated on `app` revokes what anon could inherit there. The registry's
`shared.app_role` (#662) brings two more of them, the commissioner check per team
and the site admin check, and puts its ids in `shared.pii_token_hashes()` (a
replacement of that function). A column may
carry a `default`, a table `triggers`, and the registry `trigger_functions`
(each in `ops`, `search_path` pinned empty, EXECUTE revoked from PUBLIC, and
SECURITY DEFINER only with `definer: true`, #661). On a table that exists, a
trigger of a new name is added too; a change to or a drop of an existing one is
refused. A required column carries a `fill` (#661) when it is added to a table
that has rows: ADD COLUMN with the fill as its default, so no UPDATE runs and no
trigger is touched, then DROP DEFAULT in the migration of its own that holds the
drops (#534; the gate holds it for the owner's dispatch). The one policy of
REPLACEABLE_POLICIES is changed in place with ALTER POLICY, and
`shared.choice_window` is replaced with CREATE OR REPLACE (REPLACEABLE_FUNCTIONS).
Other later changes to those fields on an existing table are refused. No change
writes nothing and exits 0. A registry that breaks a rule exits 2.

Writes `<out>/migrations/<14-digit UTC time>_<name>.sql` and the state file.
Line 1 of the migration holds the sha256 of the state file it produces. The
script connects to no database.
"""
import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
REGISTRY_FILE = REPO / "docs" / "data_model.yml"
OUT_DIR = REPO / "supabase"
STATE_FILE = "registry_state.json"

SCHEMAS = ("football", "shared", "ops", "app")
GRANTED_SCHEMAS = ("football", "ops")
OWN_GRANT_SCHEMAS = ("app",)
OWN_GRANT_TABLES = ("ops.choice_deadline",)
OWN_GRANT_ROLES = ("etl_writer", "authenticated")
NEVER_GRANTED = ("anon",)
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE")
COLUMN_PRIVILEGES = ("INSERT", "UPDATE")
TRIGGER_SCHEMA = "ops"
TRIGGER_TIMINGS = ("BEFORE", "AFTER")
TRIGGER_EVENTS = ("INSERT", "UPDATE", "DELETE", "TRUNCATE")
TRIGGER_LEVELS = ("ROW", "STATEMENT")
ROLES = ("etl_writer", "etl_reader")
SQL_TYPES = ("text", "integer", "double precision", "boolean", "date",
             "timestamp", "timestamptz", "jsonb", "uuid")
MAX_IDENT = 63
IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
RESERVED = frozenset("""
all analyse analyze and any array as asc asymmetric both case cast check collate
column constraint create current_catalog current_date current_role current_time
current_timestamp current_user default deferrable desc distinct do else end
except false fetch for foreign from grant group having in initially intersect
into lateral leading limit localtime localtimestamp not null offset on only or
order placing primary references returning select session_user some symmetric
system_user table then to trailing true union unique user using variadic when
where window with authorization binary collation concurrently cross
current_schema freeze full ilike inner is isnull join left like natural notnull
outer overlaps right similar tablesample verbose
""".split())

PII_FUNCTION = "shared.pii_token_hashes"
PII_FUNCTION_SQL = """CREATE FUNCTION shared.pii_token_hashes() RETURNS SETOF text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT encode(sha256(convert_to(s.token, 'UTF8')), 'hex')
    FROM (
        SELECT regexp_split_to_table(lower(o.human_name), '\\s+') AS token FROM shared.owner o
        UNION
        SELECT lower(o.fantrax_username) FROM shared.owner o
    ) s
    WHERE s.token IS NOT NULL AND s.token <> ''
$fn$;"""
# With the owner crosswalk declared (ADR-0025 decision 5) the list also holds each
# Discord id, so the data-commit check fails a commit that carries one. The split
# class is written `[[:space:]]`, the same set `\s` names, because the migration
# gate holds any single-quoted string with a backslash.
PII_FUNCTION_CROSSWALK_SQL = """CREATE FUNCTION shared.pii_token_hashes() RETURNS SETOF text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT encode(sha256(convert_to(s.token, 'UTF8')), 'hex')
    FROM (
        SELECT regexp_split_to_table(lower(o.human_name), '[[:space:]]+') AS token FROM shared.owner o
        UNION
        SELECT lower(o.fantrax_username) FROM shared.owner o
        UNION
        SELECT c.discord_user_id FROM shared.owner_crosswalk c
    ) s
    WHERE s.token IS NOT NULL AND s.token <> ''
$fn$;"""

CROSSWALK_TABLE = "shared.owner_crosswalk"
TEAMS_FUNCTION = "shared.caller_team_keys"
TEAMS_FUNCTION_SQL = """CREATE FUNCTION shared.caller_team_keys() RETURNS SETOF text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT c.team_key
    FROM shared.owner_crosswalk c
    JOIN auth.identities i ON i.provider = 'discord' AND i.provider_id = c.discord_user_id
    WHERE i.user_id = auth.uid()
$fn$;"""
OPEN_FUNCTION = "shared.choice_window"
OPEN_FUNCTION_SQL = """CREATE FUNCTION shared.choice_window(p_season_id text, p_choice_kind text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT coalesce(
        (SELECT CASE WHEN d.final_at <= clock_timestamp() THEN 'final'
                     WHEN d.deadline_at > clock_timestamp() THEN 'open'
                     ELSE 'passed' END
         FROM ops.choice_deadline d
         WHERE d.season_id = p_season_id AND d.choice_kind = p_choice_kind),
        'none')
$fn$;"""
# With the role table declared (ADR-0026 decision 2, #662) the list holds its ids too.
PII_FUNCTION_ROLES_SQL = PII_FUNCTION_CROSSWALK_SQL.replace(
    "        SELECT c.discord_user_id FROM shared.owner_crosswalk c\n",
    "        SELECT c.discord_user_id FROM shared.owner_crosswalk c\n"
    "        UNION\n"
    "        SELECT r.discord_user_id FROM shared.app_role r\n")

# The role table and the two checks policies will call (ADR-0026 decisions 1 to 3,
# #662). A commissioner row names its league; a site admin row holds ALL_LEAGUES.
# LEAGUE_PLACEHOLDER is the one league there is until #658 decides the key. That
# issue changes the values the loader writes and the body of COMMISSIONER_FUNCTION_SQL
# (the literal becomes the team's league), and no key and no policy. The function
# is not in REPLACEABLE_FUNCTIONS today, so the generator refuses a changed body:
# #658 adds COMMISSIONER_FUNCTION to that tuple in the same change.
ROLE_TABLE = "shared.app_role"
COMMISSIONER_FUNCTION = "shared.caller_is_commissioner_for"
ADMIN_FUNCTION = "shared.caller_is_site_admin"
LEAGUE_PLACEHOLDER = "main"
ALL_LEAGUES = "*"
TEAMS_TABLE = "football.dim_fantasy_teams"
COMMISSIONER_FUNCTION_SQL = f"""CREATE FUNCTION shared.caller_is_commissioner_for(p_team_key text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT EXISTS (
        SELECT 1
        FROM shared.app_role r
        JOIN auth.identities i ON i.provider = 'discord' AND i.provider_id = r.discord_user_id
        JOIN football.dim_fantasy_teams t ON t.team_key = p_team_key
        WHERE r.role = 'commissioner' AND r.league_key = '{LEAGUE_PLACEHOLDER}' AND i.user_id = auth.uid()
    )
$fn$;"""
ADMIN_FUNCTION_SQL = f"""CREATE FUNCTION shared.caller_is_site_admin() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT EXISTS (
        SELECT 1
        FROM shared.app_role r
        JOIN auth.identities i ON i.provider = 'discord' AND i.provider_id = r.discord_user_id
        WHERE r.role = 'site_admin' AND r.league_key = '{ALL_LEAGUES}' AND i.user_id = auth.uid()
    )
$fn$;"""
# The functions whose body a later registry may change: generator-owned text,
# written as CREATE OR REPLACE, which keeps the grants. shared.choice_window()
# gained its fourth state, `final`, this way (ADR-0026 decision 6, #661).
REPLACEABLE_FUNCTIONS = (PII_FUNCTION, OPEN_FUNCTION)
# The one policy a later registry may change in place (ADR-0026 decision 6, #661):
# written as ALTER POLICY, which keeps its name, role and command. A change to any
# other policy, or to this one's role or command, stays refused.
REPLACEABLE_POLICIES = (("app.contract_choices", "signed_in_select_after_deadline"),)
# Per `shared` function: the argument list its REVOKE and GRANT name, and the
# roles (and only those) that hold EXECUTE (ADR-0025 decision 6).
FUNCTION_ACCESS = {
    PII_FUNCTION: ("()", ("etl_writer",)),
    TEAMS_FUNCTION: ("()", ("authenticated",)),
    OPEN_FUNCTION: ("(text, text)", ("authenticated",)),
    COMMISSIONER_FUNCTION: ("(text)", ("authenticated",)),
    ADMIN_FUNCTION: ("()", ("authenticated",)),
}


class RegistryError(Exception):
    pass


def _ident(value, what):
    if not isinstance(value, str) or not IDENT.match(value):
        raise RegistryError(f"{what} {value!r}: not unquoted snake_case ({IDENT.pattern})")
    if len(value) > MAX_IDENT:
        raise RegistryError(f"{what} {value!r}: longer than {MAX_IDENT} characters")
    if value in RESERVED:
        raise RegistryError(f"{what} {value!r}: a Postgres reserved word")
    return value


def _fragment(value, what):
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{what}: expected a SQL expression")
    if ";" in value or "--" in value or "/*" in value:
        raise RegistryError(f"{what}: an expression may not hold ';', '--' or '/*'")
    return value.strip()


def _names(value, what):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        raise RegistryError(f"{what}: expected a column name or a list of them")
    if len(set(value)) != len(value):
        raise RegistryError(f"{what}: a column is named twice")
    return list(value)


def _known(columns, names, what):
    missing = [n for n in names if n not in columns]
    if missing:
        raise RegistryError(f"{what}: unknown column {missing[0]!r}")


def _own_roles(schema, name):
    """The roles a table may name in its own grants, or None when it takes the
    blanket grant: a table of a schema in OWN_GRANT_SCHEMAS may name the roles of
    OWN_GRANT_ROLES (never anon, never etl_reader); a table in OWN_GRANT_TABLES
    (a blanket schema's one exception, ADR-0025) may name both ETL roles."""
    if schema in OWN_GRANT_SCHEMAS:
        return OWN_GRANT_ROLES
    if f"{schema}.{name}" in OWN_GRANT_TABLES:
        return ROLES
    return None


def _grants(entry, where, roles, types):
    """The table's own grants, `[{role, privileges, columns?}]`, only to a role
    `roles` names. `columns` is `{INSERT: [...], UPDATE: [...]}`: a privilege it
    names is granted on those columns alone, and the others on the whole table."""
    raw = entry.get("grants")
    if raw is None:
        return []
    if roles is None:
        raise RegistryError(f"{where}: grants are for a table in {', '.join(OWN_GRANT_SCHEMAS)} "
                            f"or one of {', '.join(OWN_GRANT_TABLES)} only")
    if not isinstance(raw, list):
        raise RegistryError(f"{where}: grants: expected a list")
    grants, seen = [], set()
    for grant in raw:
        if not isinstance(grant, dict):
            raise RegistryError(f"{where}: grant {grant!r}: expected a mapping")
        role = grant.get("role")
        if role in NEVER_GRANTED:
            raise RegistryError(f"{where}: grant to {role}: {role} is never granted anything")
        if role not in roles:
            raise RegistryError(f"{where}: grant to {role!r}: not one of {', '.join(roles)}")
        if role in seen:
            raise RegistryError(f"{where}: two grants to {role}")
        seen.add(role)
        privileges = _names(grant.get("privileges"), f"{where} grant to {role}")
        bad = [p for p in privileges if p not in PRIVILEGES]
        if bad:
            raise RegistryError(f"{where}: grant to {role}: {bad[0]!r} is not one of {', '.join(PRIVILEGES)}")
        spec = {"role": role, "privileges": sorted(privileges, key=PRIVILEGES.index)}
        if grant.get("columns") is not None:
            by_privilege = grant["columns"]
            if not isinstance(by_privilege, dict) or not by_privilege:
                raise RegistryError(f"{where}: grant to {role}: columns: expected a mapping of privilege to columns")
            for privilege, names in by_privilege.items():
                if privilege not in COLUMN_PRIVILEGES:
                    raise RegistryError(f"{where}: grant to {role}: columns: {privilege!r} is not one of "
                                        f"{', '.join(COLUMN_PRIVILEGES)}")
                if privilege not in privileges:
                    raise RegistryError(f"{where}: grant to {role}: columns names {privilege}, "
                                        f"which the grant does not hold")
                _known(types, _names(names, f"{where} grant to {role} {privilege} columns"),
                       f"{where} grant to {role} {privilege} columns")
            spec["columns"] = {p: _names(by_privilege[p], f"{where} grant to {role} {p} columns")
                               for p in COLUMN_PRIVILEGES if p in by_privilege}
        grants.append(spec)
    return grants


def _policies(entry, where, roles, grants):
    """The table's named policies, `[{name, role, command, using?, check?}]`. A
    policy needs a grant of its command's privilege to its role."""
    raw = entry.get("policies")
    if raw is None:
        return []
    if roles is None:
        raise RegistryError(f"{where}: policies are for a table in {', '.join(OWN_GRANT_SCHEMAS)} "
                            f"or one of {', '.join(OWN_GRANT_TABLES)} only")
    if not isinstance(raw, list):
        raise RegistryError(f"{where}: policies: expected a list")
    held = {g["role"]: g["privileges"] for g in grants}
    policies, names = [], set()
    for policy in raw:
        if not isinstance(policy, dict):
            raise RegistryError(f"{where}: policy {policy!r}: expected a mapping")
        name = _ident(policy.get("name"), f"{where} policy name")
        if name in names:
            raise RegistryError(f"{where}: policy {name!r} is declared twice")
        names.add(name)
        role, command = policy.get("role"), policy.get("command")
        if role in NEVER_GRANTED:
            raise RegistryError(f"{where}: policy {name}: {role} is never granted anything")
        if role not in roles:
            raise RegistryError(f"{where}: policy {name}: role {role!r} is not one of {', '.join(roles)}")
        if command not in PRIVILEGES:
            raise RegistryError(f"{where}: policy {name}: command {command!r} is not one of {', '.join(PRIVILEGES)}")
        if command not in held.get(role, []):
            raise RegistryError(f"{where}: policy {name}: {role} has no {command} grant on the table")
        wants = {"SELECT": ("using",), "DELETE": ("using",), "INSERT": ("check",), "UPDATE": ("using", "check")}[command]
        spec = {"name": name, "role": role, "command": command}
        for key in ("using", "check"):
            if policy.get(key) is None:
                continue
            if key not in wants:
                raise RegistryError(f"{where}: policy {name}: a {command} policy takes no {key}")
            spec[key] = _fragment(policy[key], f"{where} policy {name} {key}")
        if not any(k in spec for k in wants):
            raise RegistryError(f"{where}: policy {name}: needs {' or '.join(wants)}")
        policies.append(spec)
    return policies


def _triggers(entry, where):
    """The table's triggers, `[{name, timing, events, level, function}]`. The
    function is checked against the declared ones in `desired_model`."""
    raw = entry.get("triggers")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RegistryError(f"{where}: triggers: expected a list")
    triggers, names = [], set()
    for trigger in raw:
        if not isinstance(trigger, dict):
            raise RegistryError(f"{where}: trigger {trigger!r}: expected a mapping")
        name = _ident(trigger.get("name"), f"{where} trigger name")
        if name in names:
            raise RegistryError(f"{where}: trigger {name!r} is declared twice")
        names.add(name)
        timing, level = trigger.get("timing"), trigger.get("level")
        if timing not in TRIGGER_TIMINGS:
            raise RegistryError(f"{where}: trigger {name}: timing {timing!r} is not one of {', '.join(TRIGGER_TIMINGS)}")
        if level not in TRIGGER_LEVELS:
            raise RegistryError(f"{where}: trigger {name}: level {level!r} is not one of {', '.join(TRIGGER_LEVELS)}")
        events = _names(trigger.get("events"), f"{where} trigger {name} events")
        bad = [e for e in events if e not in TRIGGER_EVENTS]
        if bad:
            raise RegistryError(f"{where}: trigger {name}: event {bad[0]!r} is not one of {', '.join(TRIGGER_EVENTS)}")
        if "TRUNCATE" in events and (events != ["TRUNCATE"] or level != "STATEMENT"):
            raise RegistryError(f"{where}: trigger {name}: TRUNCATE stands alone, at level STATEMENT")
        function = trigger.get("function")
        if not isinstance(function, str):
            raise RegistryError(f"{where}: trigger {name}: needs a function")
        triggers.append({"name": name, "timing": timing,
                         "events": sorted(events, key=TRIGGER_EVENTS.index),
                         "level": level, "function": function})
    return triggers


def _table_spec(entry, default_schema):
    if not isinstance(entry, dict):
        raise RegistryError(f"table entry {entry!r}: expected a mapping")
    name = _ident(entry.get("name"), "table name")
    schema = entry.get("schema") or default_schema
    if schema not in SCHEMAS:
        raise RegistryError(f"{name}: schema {schema!r} is not one of {', '.join(SCHEMAS)}")
    where = f"{schema}.{name}"
    raw_columns = entry.get("columns")
    if not isinstance(raw_columns, list) or not raw_columns:
        raise RegistryError(f"{where}: no columns")
    pk = _names(entry.get("pk"), f"{where} pk") if entry.get("pk") else None
    if pk is None:
        raise RegistryError(f"{where}: no pk")
    required = _names(entry["required_keys"], f"{where} required_keys") if entry.get("required_keys") else []
    columns, types = [], {}
    for col in raw_columns:
        col_name = _ident(col.get("name") if isinstance(col, dict) else None, f"{where} column name")
        if col_name in types:
            raise RegistryError(f"{where}: column {col_name!r} is declared twice")
        sql_type = col.get("sql_type")
        if sql_type not in SQL_TYPES:
            raise RegistryError(f"{where}.{col_name}: sql_type {sql_type!r} is not one of {', '.join(SQL_TYPES)}")
        types[col_name] = sql_type
        column = {"name": col_name, "sql_type": sql_type, "not_null": False}
        if col.get("default") is not None:
            column["default"] = _fragment(col["default"], f"{where}.{col_name} default")
        if col.get("fill") is not None:
            column["fill"] = _fragment(col["fill"], f"{where}.{col_name} fill")
        columns.append(column)
    _known(types, pk, f"{where} pk")
    _known(types, required, f"{where} required_keys")
    for col in columns:
        col["not_null"] = col["name"] in pk or col["name"] in required
        if "fill" in col and not col["not_null"]:
            raise RegistryError(f"{where}.{col['name']}: fill is for a required column only")
        if "fill" in col and "default" in col:
            raise RegistryError(f"{where}.{col['name']}: a column holds a default or a fill, not both")
    checks = []
    for expr in entry.get("checks") or []:
        expr = _fragment(expr, f"{where} check")
        if expr in checks:
            raise RegistryError(f"{where}: check {expr!r} is declared twice")
        checks.append(expr)
    fks, fk_names = [], set()
    for fk in entry.get("fk") or []:
        if not isinstance(fk, dict):
            raise RegistryError(f"{where}: fk {fk!r}: expected a mapping")
        fk_cols = _names(fk.get("columns"), f"{where} fk columns")
        _known(types, fk_cols, f"{where} fk")
        fk_name = _ident(f"{name}_{'_'.join(fk_cols)}_fkey", "foreign key name")
        if fk_name in fk_names:
            raise RegistryError(f"{where}: two foreign keys on {fk_cols}")
        fk_names.add(fk_name)
        fks.append({"name": fk_name, "columns": fk_cols, "to": fk.get("to"),
                    "ref": _names(fk.get("ref"), f"{where} fk ref")})
    indexes = []
    for idx in entry.get("indexes") or []:
        if not isinstance(idx, dict):
            raise RegistryError(f"{where}: index {idx!r}: expected a mapping")
        idx_cols = _names(idx.get("columns"), f"{where} index columns")
        _known(types, idx_cols, f"{where} index")
        idx_name = _ident(idx.get("name") or f"{name}_{'_'.join(idx_cols)}_idx", "index name")
        predicate = _fragment(idx["where"], f"{where} index {idx_name} where") if idx.get("where") else None
        indexes.append({"name": idx_name, "columns": idx_cols,
                        "unique": bool(idx.get("unique")), "where": predicate})
    spec = {"schema": schema, "name": name, "columns": columns, "pk": pk,
            "checks": checks, "fks": fks, "indexes": indexes}
    roles = _own_roles(schema, name)
    grants = _grants(entry, where, roles, types)
    for key, items in (("grants", grants), ("policies", _policies(entry, where, roles, grants)),
                       ("triggers", _triggers(entry, where))):
        if items:
            spec[key] = items
    return spec


def _trigger_function(entry):
    if not isinstance(entry, dict):
        raise RegistryError(f"trigger function {entry!r}: expected a mapping")
    name = entry.get("name")
    if not isinstance(name, str) or name.count(".") != 1:
        raise RegistryError(f"trigger function {name!r}: expected schema.name")
    schema, bare = name.split(".")
    if schema != TRIGGER_SCHEMA:
        raise RegistryError(f"trigger function {name}: lives in {TRIGGER_SCHEMA}, not {schema}")
    _ident(bare, "trigger function name")
    body = entry.get("body")
    if not isinstance(body, str) or not body.strip():
        raise RegistryError(f"trigger function {name}: needs a body")
    if "$fn$" in body:
        raise RegistryError(f"trigger function {name}: the body may not hold $fn$")
    definer = entry.get("definer", False)
    if not isinstance(definer, bool):
        raise RegistryError(f"trigger function {name}: definer: expected true or false")
    security = " SECURITY DEFINER" if definer else ""
    sql = (f"CREATE FUNCTION {name}() RETURNS trigger\nLANGUAGE plpgsql{security} SET search_path = ''\n"
           f"AS $fn$\n{body.strip()}\n$fn$;")
    return name, sql


def desired_model(registry):
    """The registry as the plain dict the state file holds."""
    if not isinstance(registry, dict):
        raise RegistryError("the registry is not a mapping")
    specs = {}
    for section, default_schema in (("tables", "football"), ("other_tables", None)):
        for entry in registry.get(section) or []:
            spec = _table_spec(entry, default_schema)
            if spec["name"] in {s["name"] for s in specs.values()}:
                raise RegistryError(f"table {spec['name']!r} is declared twice")
            specs[f"{spec['schema']}.{spec['name']}"] = spec
    if not specs:
        raise RegistryError("the registry declares no tables")
    by_name = {s["name"]: s for s in specs.values()}
    index_names = set()
    for spec in specs.values():
        for fk in spec["fks"]:
            target = by_name.get(fk["to"])
            where = f"{spec['schema']}.{spec['name']} fk {fk['name']}"
            if target is None:
                raise RegistryError(f"{where}: unknown table {fk['to']!r}")
            target_types = {c["name"]: c["sql_type"] for c in target["columns"]}
            own_types = {c["name"]: c["sql_type"] for c in spec["columns"]}
            _known(target_types, fk["ref"], where)
            if len(fk["ref"]) != len(fk["columns"]):
                raise RegistryError(f"{where}: columns and ref differ in length")
            for col, ref in zip(fk["columns"], fk["ref"]):
                if own_types[col] != target_types[ref]:
                    raise RegistryError(f"{where}: {col} is {own_types[col]}, {ref} is {target_types[ref]}")
            fk["to"] = f"{target['schema']}.{target['name']}"
        for idx in spec["indexes"]:
            key = (spec["schema"], idx["name"])
            if key in index_names:
                raise RegistryError(f"index {idx['name']!r} is declared twice in {spec['schema']}")
            index_names.add(key)
    functions = {}
    owner = specs.get("shared.owner")
    if owner is not None:
        _known({c["name"] for c in owner["columns"]}, ["human_name", "fantrax_username"], "shared.owner")
        functions[PII_FUNCTION] = PII_FUNCTION_SQL
    crosswalk = specs.get(CROSSWALK_TABLE)
    if crosswalk is not None:
        _known({c["name"] for c in crosswalk["columns"]}, ["team_key", "discord_user_id"], CROSSWALK_TABLE)
        if "ops.choice_deadline" not in specs:
            raise RegistryError(f"{CROSSWALK_TABLE}: the definer functions read ops.choice_deadline, which is not declared")
        _known({c["name"] for c in specs["ops.choice_deadline"]["columns"]}, ["deadline_at", "final_at"],
               "ops.choice_deadline")
        functions[PII_FUNCTION] = PII_FUNCTION_CROSSWALK_SQL
        functions[TEAMS_FUNCTION] = TEAMS_FUNCTION_SQL
        functions[OPEN_FUNCTION] = OPEN_FUNCTION_SQL
    roles = specs.get(ROLE_TABLE)
    if roles is not None:
        if crosswalk is None:
            raise RegistryError(f"{ROLE_TABLE}: the owner crosswalk is not declared")
        _known({c["name"] for c in roles["columns"]}, ["discord_user_id", "role", "league_key"], ROLE_TABLE)
        if TEAMS_TABLE not in specs:
            raise RegistryError(f"{ROLE_TABLE}: the commissioner check reads {TEAMS_TABLE}, which is not declared")
        _known({c["name"] for c in specs[TEAMS_TABLE]["columns"]}, ["team_key"], TEAMS_TABLE)
        functions[PII_FUNCTION] = PII_FUNCTION_ROLES_SQL
        functions[COMMISSIONER_FUNCTION] = COMMISSIONER_FUNCTION_SQL
        functions[ADMIN_FUNCTION] = ADMIN_FUNCTION_SQL
    raw_functions = registry.get("trigger_functions") or []
    if not isinstance(raw_functions, list):
        raise RegistryError("trigger_functions: expected a list")
    trigger_functions = {}
    for entry in raw_functions:
        name, sql = _trigger_function(entry)
        if name in trigger_functions or name in functions:
            raise RegistryError(f"function {name} is declared twice")
        trigger_functions[name] = sql
    for spec in specs.values():
        for trigger in spec.get("triggers", []):
            if trigger["function"] not in trigger_functions:
                raise RegistryError(f"{spec['schema']}.{spec['name']} trigger {trigger['name']}: "
                                    f"unknown trigger function {trigger['function']!r}")
    return {"schemas": list(SCHEMAS), "roles": list(ROLES),
            "tables": dict(sorted(specs.items())), "functions": functions,
            "trigger_functions": dict(sorted(trigger_functions.items()))}


EMPTY_MODEL = {"schemas": [], "roles": [], "tables": {}, "functions": {}, "trigger_functions": {}}
NO_DROPS = {"columns": {}, "tables": {}}


def _ticket(entry, what):
    ticket = entry.get("ticket")
    if isinstance(ticket, bool) or not isinstance(ticket, int) or ticket < 1:
        raise RegistryError(f"{what}: needs a ticket number")
    return ticket


def registry_drops(registry):
    """The drops the registry flags (#534): {"columns": {(table key, column):
    ticket}, "tables": {table name: ticket}}. A flagged item still declared is
    an error. Table names are unique across the schemas, so a name is enough."""
    if not isinstance(registry, dict):
        raise RegistryError("the registry is not a mapping")
    declared_tables, columns, tables = set(), {}, {}
    for section, default_schema in (("tables", "football"), ("other_tables", None)):
        for entry in registry.get(section) or []:
            if not isinstance(entry, dict):
                continue
            declared_tables.add(entry.get("name"))
            key = f"{entry.get('schema') or default_schema}.{entry.get('name')}"
            declared = {c.get("name") for c in entry.get("columns") or [] if isinstance(c, dict)}
            raw = entry.get("drops") or []
            if not isinstance(raw, list):
                raise RegistryError(f"{key} drops: expected a list")
            for drop in raw:
                if not isinstance(drop, dict):
                    raise RegistryError(f"{key} drops: {drop!r}: expected a mapping")
                name = _ident(drop.get("column"), f"{key} drops column")
                ticket = _ticket(drop, f"{key} drops {name}")
                if name in declared:
                    raise RegistryError(f"{key} drops {name}: the column is still declared")
                if (key, name) in columns:
                    raise RegistryError(f"{key} drops {name}: named twice")
                columns[(key, name)] = ticket
    raw = registry.get("dropped_tables") or []
    if not isinstance(raw, list):
        raise RegistryError("dropped_tables: expected a list")
    for drop in raw:
        if not isinstance(drop, dict):
            raise RegistryError(f"dropped_tables: {drop!r}: expected a mapping")
        name = _ident(drop.get("table"), "dropped_tables table")
        ticket = _ticket(drop, f"dropped_tables {name}")
        if name in declared_tables:
            raise RegistryError(f"dropped_tables {name}: the table is still declared")
        if name in tables:
            raise RegistryError(f"dropped_tables {name}: named twice")
        tables[name] = ticket
    return {"columns": columns, "tables": tables}


def _by_name(items):
    return {i["name"]: i for i in items}


_LITERAL = r"'[^']*'|-?[0-9]+"
_IN_LIST = re.compile(rf"([a-z][a-z0-9_]*) IN \(\s*((?:{_LITERAL})(?:\s*,\s*(?:{_LITERAL}))*)\s*\)")


def _in_list(expr):
    """(column, literals) when `expr` is exactly `<column> IN (<literals>)`, else None."""
    found = _IN_LIST.fullmatch(expr)
    if found is None:
        return None
    return found.group(1), re.findall(_LITERAL, found.group(2))


def _widens(old_expr, new_expr):
    """True when both are IN-lists on one column and the new holds every old literal."""
    before, after = _in_list(old_expr), _in_list(new_expr)
    return (before is not None and after is not None and before[0] == after[0]
            and set(before[1]) <= set(after[1]))


def _table_changes(key, old, new, out, flagged):
    refuse = out["refusals"]
    old_cols, new_cols = _by_name(old["columns"]), _by_name(new["columns"])
    removed = [c for c in old["columns"] if c["name"] not in new_cols]
    added = [c for c in new["columns"] if c["name"] not in old_cols]
    claimed = set()
    for col in removed:
        if (key, col["name"]) in flagged:
            out["column_drops"].append((key, col["name"]))
            continue
        twin = next((a for a in added if a["sql_type"] == col["sql_type"] and a["name"] not in claimed), None)
        if twin is not None:
            claimed.add(twin["name"])
            refuse.append(f"{key}: rename of column {col['name']} to {twin['name']}")
        else:
            refuse.append(f"{key}: drop of column {col['name']}")
    for col in new["columns"]:
        before = old_cols.get(col["name"])
        if before is None:
            out["columns"].append((key, col))
            if col.get("fill"):
                out["default_drops"].append((key, col["name"]))
            continue
        if before["sql_type"] != col["sql_type"]:
            refuse.append(f"{key}.{col['name']}: type change from {before['sql_type']} to {col['sql_type']}")
        if before["not_null"] != col["not_null"]:
            refuse.append(f"{key}.{col['name']}: change of NOT NULL")
        if before.get("default") != col.get("default"):
            refuse.append(f"{key}.{col['name']}: change of default")
    for field, ident in (("grants", "role"), ("policies", "name"), ("triggers", "name")):
        before, after = {i[ident]: i for i in old.get(field, [])}, {i[ident]: i for i in new.get(field, [])}
        changed = [name for name, item in before.items() if after.get(name) != item]
        replaced = [n for n in changed if field == "policies" and (key, n) in REPLACEABLE_POLICIES and n in after
                    and all(after[n][k] == before[n][k] for k in ("role", "command"))]
        if len(replaced) < len(changed):
            refuse.append(f"{key}: change of {field}")
        else:
            out["policy_replacements"] += [(key, after[name]) for name in replaced]
            out[field] += [(key, item) for name, item in after.items() if name not in before]
    if old["pk"] != new["pk"]:
        refuse.append(f"{key}: change of primary key from {old['pk']} to {new['pk']}")
    gone = [e for e in old["checks"] if e not in new["checks"]]
    fresh = [e for e in new["checks"] if e not in old["checks"]]
    partners = {e: [f for f in fresh if _widens(e, f)] for e in gone}
    swapped = set()
    for expr in gone:
        match = partners[expr]
        if len(match) == 1 and sum(match[0] in p for p in partners.values()) == 1:
            out["check_swaps"].append((key, expr, match[0]))
            swapped.add(match[0])
        else:
            refuse.append(f"{key}: drop of check {expr}")
    for expr in fresh:
        if expr not in swapped:
            out["checks"].append((key, expr))
    for kind, label in (("fks", "foreign key"), ("indexes", "index")):
        before, after = _by_name(old[kind]), _by_name(new[kind])
        for name, item in before.items():
            if name not in after:
                refuse.append(f"{key}: drop of {label} {name}")
            elif after[name] != item:
                refuse.append(f"{key}: change of {label} {name}")
        for name, item in after.items():
            if name not in before:
                out[kind].append((key, item))


def diff(old, new, drops=NO_DROPS):
    """What `new` adds to `old`, the drops `drops` flags (#534), and the
    changes it holds that a migration may not make (`refusals`)."""
    out = {"schemas": [], "roles": [], "tables": [], "columns": [], "check_swaps": [],
           "checks": [], "fks": [], "indexes": [], "functions": [], "trigger_functions": [],
           "column_drops": [], "table_drops": [], "grants": [], "policies": [], "function_replacements": [],
           "triggers": [], "policy_replacements": [], "default_drops": [], "refusals": []}
    for kind in ("schemas", "roles"):
        out[kind] = [n for n in new[kind] if n not in old[kind]]
        out["refusals"] += [f"drop of {kind[:-1]} {n}" for n in old[kind] if n not in new[kind]]
    added = [k for k in new["tables"] if k not in old["tables"]]
    for key in old["tables"]:
        if key in new["tables"]:
            continue
        if key.split(".", 1)[1] in drops["tables"]:
            out["table_drops"].append(key)
            continue
        columns = [c["name"] for c in old["tables"][key]["columns"]]
        twin = next((a for a in added if [c["name"] for c in new["tables"][a]["columns"]] == columns), None)
        out["refusals"].append(f"{key}: rename of table to {twin}" if twin else f"{key}: drop of table")
    for key, spec in new["tables"].items():
        if key in old["tables"]:
            _table_changes(key, old["tables"][key], spec, out, drops["columns"])
        else:
            out["tables"].append(spec)
            out["fks"] += [(key, fk) for fk in spec["fks"]]
            out["indexes"] += [(key, idx) for idx in spec["indexes"]]
    for name, sql in new["functions"].items():
        if name not in old["functions"]:
            out["functions"].append((name, sql))
        elif old["functions"][name] != sql:
            if name in REPLACEABLE_FUNCTIONS:
                out["function_replacements"].append((name, sql))
            else:
                out["refusals"].append(f"{name}: change of function body")
    out["refusals"] += [f"{n}: drop of function" for n in old["functions"] if n not in new["functions"]]
    old_triggers, new_triggers = old.get("trigger_functions", {}), new.get("trigger_functions", {})
    for name, sql in new_triggers.items():
        if name not in old_triggers:
            out["trigger_functions"].append((name, sql))
        elif old_triggers[name] != sql:
            out["refusals"].append(f"{name}: change of function body")
    out["refusals"] += [f"{n}: drop of function" for n in old_triggers if n not in new_triggers]
    return out


def has_changes(changes):
    return any(changes[k] for k in changes if k != "refusals")


def _check_name(table, expr):
    return f"{table}_chk_{hashlib.sha256(expr.encode('utf-8')).hexdigest()[:8]}"


def _column_sql(col):
    default = f" DEFAULT {col['default']}" if col.get("default") else ""
    return f"{col['name']} {col['sql_type']}{' NOT NULL' if col['not_null'] else ''}{default}"


def _create_table(spec):
    lines = [f"    {_column_sql(c)}" for c in spec["columns"]]
    lines.append(f"    CONSTRAINT {spec['name']}_pkey PRIMARY KEY ({', '.join(spec['pk'])})")
    lines += [f"    CONSTRAINT {_check_name(spec['name'], e)} CHECK ({e})" for e in spec["checks"]]
    return f"CREATE TABLE {spec['schema']}.{spec['name']} (\n" + ",\n".join(lines) + "\n);"


def _role(name):
    return (f"DO $do$\nBEGIN\n    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{name}') THEN\n"
            f"        CREATE ROLE {name} LOGIN NOBYPASSRLS;\n    END IF;\nEND\n$do$;")


def render(changes):
    """The SQL body for a diff with no refusals, in the order of the brief."""
    out = [f"CREATE SCHEMA {s};" for s in changes["schemas"]]
    out += [_role(r) for r in changes["roles"]]
    out += [_create_table(spec) for spec in changes["tables"]]
    for key, col in changes["columns"]:
        shown = {**col, "default": col["fill"]} if col.get("fill") else col
        out.append(f"ALTER TABLE {key} ADD COLUMN {_column_sql(shown)};")
    for key, old_expr, new_expr in changes["check_swaps"]:
        table_name = key.split(".")[1]
        out.append(f"ALTER TABLE {key} DROP CONSTRAINT {_check_name(table_name, old_expr)};")
        out.append(f"ALTER TABLE {key} ADD CONSTRAINT {_check_name(table_name, new_expr)} CHECK ({new_expr});")
    for key, expr in changes["checks"]:
        out.append(f"ALTER TABLE {key} ADD CONSTRAINT {_check_name(key.split('.')[1], expr)} CHECK ({expr});")
    for key, fk in changes["fks"]:
        out.append(f"ALTER TABLE {key} ADD CONSTRAINT {fk['name']} FOREIGN KEY ({', '.join(fk['columns'])}) "
                   f"REFERENCES {fk['to']} ({', '.join(fk['ref'])}) DEFERRABLE INITIALLY DEFERRED;")
    out += [f"ALTER TABLE {s['schema']}.{s['name']} ENABLE ROW LEVEL SECURITY;" for s in changes["tables"]]
    out += [f"GRANT USAGE ON SCHEMA {s} TO etl_writer, etl_reader;" for s in changes["schemas"] if s in GRANTED_SCHEMAS]
    for spec in changes["tables"]:
        if spec["schema"] not in GRANTED_SCHEMAS or spec.get("grants"):
            continue
        qualified = f"{spec['schema']}.{spec['name']}"
        out += [f"GRANT SELECT, INSERT, UPDATE, DELETE ON {qualified} TO etl_writer;",
                f"GRANT SELECT ON {qualified} TO etl_reader;",
                f"CREATE POLICY etl_writer_all ON {qualified} FOR ALL TO etl_writer USING (true) WITH CHECK (true);",
                f"CREATE POLICY etl_reader_select ON {qualified} FOR SELECT TO etl_reader USING (true);"]
    usage = []
    for name, sql in changes["functions"]:
        sig, roles = FUNCTION_ACCESS[name]
        schema = name.split(".")[0]
        out += [sql, f"REVOKE EXECUTE ON FUNCTION {name}{sig} FROM PUBLIC;"]
        for role in roles:
            if (schema, role) not in usage:
                usage.append((schema, role))
                out.append(f"GRANT USAGE ON SCHEMA {schema} TO {role};")
            out.append(f"GRANT EXECUTE ON FUNCTION {name}{sig} TO {role};")
    out += [sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
            for _, sql in changes.get("function_replacements", [])]

    def grant_lines(schema, qualified, grant):
        lines = []
        if schema not in GRANTED_SCHEMAS and (schema, grant["role"]) not in usage:
            usage.append((schema, grant["role"]))
            lines.append(f"GRANT USAGE ON SCHEMA {schema} TO {grant['role']};")
            if grant["role"] == "authenticated" and schema in OWN_GRANT_SCHEMAS:
                lines += [f"REVOKE ALL ON SCHEMA {schema} FROM anon;",
                          f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM anon;",
                          f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE ALL ON TABLES FROM anon;"]
        columns = grant.get("columns", {})
        whole = [p for p in grant["privileges"] if p not in columns]
        if whole:
            lines.append(f"GRANT {', '.join(whole)} ON {qualified} TO {grant['role']};")
        lines += [f"GRANT {p} ({', '.join(columns[p])}) ON {qualified} TO {grant['role']};"
                  for p in COLUMN_PRIVILEGES if p in columns]
        return lines

    def policy_line(qualified, policy):
        clauses = "".join(f" {word} ({policy[key]})" for key, word in (("using", "USING"), ("check", "WITH CHECK"))
                          if key in policy)
        return f"CREATE POLICY {policy['name']} ON {qualified} FOR {policy['command']} TO {policy['role']}{clauses};"

    for spec in changes["tables"]:
        qualified = f"{spec['schema']}.{spec['name']}"
        for grant in spec.get("grants", []):
            out += grant_lines(spec["schema"], qualified, grant)
        out += [policy_line(qualified, p) for p in spec.get("policies", [])]
    for key, grant in changes.get("grants", []):
        out += grant_lines(key.split(".")[0], key, grant)
    out += [policy_line(key, p) for key, p in changes.get("policies", [])]
    for key, policy in changes.get("policy_replacements", []):
        clauses = "".join(f" {word} ({policy[field]})" for field, word in (("using", "USING"), ("check", "WITH CHECK"))
                          if field in policy)
        out.append(f"ALTER POLICY {policy['name']} ON {key}{clauses};")
    for name, sql in changes.get("trigger_functions", []):
        out += [sql, f"REVOKE EXECUTE ON FUNCTION {name}() FROM PUBLIC;"]

    def trigger_line(qualified, trigger):
        return (f"CREATE TRIGGER {trigger['name']} {trigger['timing']} {' OR '.join(trigger['events'])} "
                f"ON {qualified} FOR EACH {trigger['level']} EXECUTE FUNCTION {trigger['function']}();")

    for spec in changes["tables"]:
        out += [trigger_line(f"{spec['schema']}.{spec['name']}", t) for t in spec.get("triggers", [])]
    out += [trigger_line(key, t) for key, t in changes.get("triggers", [])]
    for key, idx in changes["indexes"]:
        where = f" WHERE {idx['where']}" if idx["where"] else ""
        out.append(f"CREATE {'UNIQUE ' if idx['unique'] else ''}INDEX {idx['name']} ON {key} "
                   f"({', '.join(idx['columns'])}){where};")
    out += [f"ALTER TABLE {key} DROP COLUMN {name};" for key, name in changes["column_drops"]]
    out += [f"ALTER TABLE {key} ALTER COLUMN {name} DROP DEFAULT;" for key, name in changes.get("default_drops", [])]
    out += [f"DROP TABLE {key};" for key in changes["table_drops"]]
    return "\n\n".join(out) + "\n"


# A DROP DEFAULT (the end of a `fill`, #661) is held by the destructive gate like
# any DROP, and a held migration holds only drops (#534), so it goes in the
# migration of its own with the column and table drops.
DROP_KINDS = ("column_drops", "table_drops", "default_drops")


def _with_dropped(old, new, changes):
    """`new` with the flagged items still in place: the state after the ordinary
    migration applies and before the drop migration does."""
    state = copy.deepcopy(new)
    for key, name in changes["column_drops"]:
        kept = {c["name"] for c in state["tables"][key]["columns"]} | {name}
        before = [c for c in old["tables"][key]["columns"] if c["name"] in kept]
        added = [c for c in state["tables"][key]["columns"] if c["name"] not in _by_name(before)]
        state["tables"][key]["columns"] = copy.deepcopy(before) + added
    for key in changes["table_drops"]:
        state["tables"][key] = copy.deepcopy(old["tables"][key])
    state["tables"] = dict(sorted(state["tables"].items()))
    return state


def split_drops(old, new, changes):
    """[(changes, state it produces)], one per migration file. A drop sits in a
    migration of its own (#534, planner ruling on PR #536): when a run holds
    drops and other changes, the ordinary changes come first and the drops
    alone follow, so the push gate holds only the drops."""
    drops = {k: changes[k] for k in DROP_KINDS}
    ordinary = {**changes, **{k: [] for k in DROP_KINDS}}
    if not any(drops.values()) or not has_changes(ordinary):
        return [(changes, new)]
    only_drops = {**{k: [] for k in changes}, **drops}
    return [(ordinary, _with_dropped(old, new, changes)), (only_drops, new)]


def newest_stamp(folder):
    """The time of the newest migration in `folder`, or None. A drop file is
    stamped after it, so it never sorts before a version already applied
    (#536 audit A5)."""
    stamps = [p.name[:14] for p in Path(folder).glob("*.sql")
              if p.name[:14].isdigit() and p.name[14:15] == "_"]
    if not stamps:
        return None
    return datetime.strptime(max(stamps), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def dump_state(model):
    return json.dumps(model, indent=2, sort_keys=True) + "\n"


def state_sha(model):
    return hashlib.sha256(dump_state(model).encode("utf-8")).hexdigest()


def load_state(path):
    path = Path(path)
    if not path.exists():
        return EMPTY_MODEL
    try:
        model = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise RegistryError(f"{path.name}: not valid JSON ({exc})") from exc
    if isinstance(model, dict) and set(model) == set(EMPTY_MODEL) - {"trigger_functions"}:
        model = {**model, "trigger_functions": {}}
    if not isinstance(model, dict) or set(model) != set(EMPTY_MODEL):
        raise RegistryError(f"{path.name}: not a registry state")
    return model


def main(argv=None, now=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--registry", default=str(REGISTRY_FILE))
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--name")
    args = parser.parse_args(argv)
    out = Path(args.out)
    try:
        registry = yaml.safe_load(Path(args.registry).read_text(encoding="utf-8"))
        new = desired_model(registry)
        drops = registry_drops(registry)
        old = load_state(out / STATE_FILE)
        name = _ident(args.name or ("registry_update" if old["tables"] else "initial_schema"), "migration name")
    except (RegistryError, OSError, yaml.YAMLError) as exc:
        print(f"generate_migrations: {exc}", file=sys.stderr)
        return 2
    changes = diff(old, new, drops)
    if changes["refusals"]:
        print("generate_migrations: refused, no file written:", file=sys.stderr)
        for line in changes["refusals"]:
            print(f"  {line}", file=sys.stderr)
        return 1
    if not has_changes(changes):
        print("generate_migrations: no change")
        return 0
    start = now or datetime.now(timezone.utc)
    newest = newest_stamp(out / "migrations")
    files = []
    for i, (part, state) in enumerate(split_drops(old, new, changes)):
        when = start + timedelta(seconds=i)
        if any(part[k] for k in DROP_KINDS) and newest is not None and when <= newest:
            when = newest + timedelta(seconds=1)
        stamp = when.strftime("%Y%m%d%H%M%S")
        suffix = "_drops" if i else ""
        files.append((out / "migrations" / f"{stamp}_{name}{suffix}.sql", part, state))
    try:
        files[0][0].parent.mkdir(parents=True, exist_ok=True)
        taken = [p for p, _, _ in files if p.exists()]
        if taken:
            raise FileExistsError(f"{taken[0]} already exists")
        for path, part, state in files:
            with path.open("x", encoding="utf-8", newline="\n") as fh:
                fh.write(f"-- registry_state sha256: {state_sha(state)}\n\n{render(part)}")
    except OSError as exc:
        print(f"generate_migrations: {exc}", file=sys.stderr)
        return 2
    with (out / STATE_FILE).open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(dump_state(new))
    for path, _, _ in files:
        print(f"generate_migrations: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

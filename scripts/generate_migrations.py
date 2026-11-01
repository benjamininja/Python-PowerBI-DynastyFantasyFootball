"""Generate a Supabase migration from the registry (#108, ADR-0018 decision 3).

    generate_migrations.py [--registry FILE] [--out DIR] [--name NAME]

`desired_model` reads the registry into a plain dict. `diff` compares it with
`<out>/registry_state.json`, the record of what the migrations already hold.
`render` turns the additions into SQL. A drop, a rename or a type change is
refused: the script names it, exits 1 and writes nothing. No change writes
nothing and exits 0. A registry that breaks a rule exits 2.

Writes `<out>/migrations/<14-digit UTC time>_<name>.sql` and the state file.
Line 1 of the migration holds the sha256 of the state file it produces. The
script connects to no database.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
REGISTRY_FILE = REPO / "docs" / "data_model.yml"
OUT_DIR = REPO / "supabase"
STATE_FILE = "registry_state.json"

SCHEMAS = ("football", "shared", "ops")
GRANTED_SCHEMAS = ("football", "ops")
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
        columns.append({"name": col_name, "sql_type": sql_type, "not_null": False})
    _known(types, pk, f"{where} pk")
    _known(types, required, f"{where} required_keys")
    for col in columns:
        col["not_null"] = col["name"] in pk or col["name"] in required
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
    return {"schema": schema, "name": name, "columns": columns, "pk": pk,
            "checks": checks, "fks": fks, "indexes": indexes}


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
    return {"schemas": list(SCHEMAS), "roles": list(ROLES),
            "tables": dict(sorted(specs.items())), "functions": functions}


EMPTY_MODEL = {"schemas": [], "roles": [], "tables": {}, "functions": {}}


def _by_name(items):
    return {i["name"]: i for i in items}


def _table_changes(key, old, new, out):
    refuse = out["refusals"]
    old_cols, new_cols = _by_name(old["columns"]), _by_name(new["columns"])
    removed = [c for c in old["columns"] if c["name"] not in new_cols]
    added = [c for c in new["columns"] if c["name"] not in old_cols]
    claimed = set()
    for col in removed:
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
            continue
        if before["sql_type"] != col["sql_type"]:
            refuse.append(f"{key}.{col['name']}: type change from {before['sql_type']} to {col['sql_type']}")
        if before["not_null"] != col["not_null"]:
            refuse.append(f"{key}.{col['name']}: change of NOT NULL")
    if old["pk"] != new["pk"]:
        refuse.append(f"{key}: change of primary key from {old['pk']} to {new['pk']}")
    for expr in old["checks"]:
        if expr not in new["checks"]:
            refuse.append(f"{key}: drop of check {expr}")
    for expr in new["checks"]:
        if expr not in old["checks"]:
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


def diff(old, new):
    """What `new` adds to `old`, and the changes it holds that a migration may
    not make (`refusals`)."""
    out = {"schemas": [], "roles": [], "tables": [], "columns": [], "checks": [],
           "fks": [], "indexes": [], "functions": [], "refusals": []}
    for kind in ("schemas", "roles"):
        out[kind] = [n for n in new[kind] if n not in old[kind]]
        out["refusals"] += [f"drop of {kind[:-1]} {n}" for n in old[kind] if n not in new[kind]]
    added = [k for k in new["tables"] if k not in old["tables"]]
    for key in old["tables"]:
        if key in new["tables"]:
            continue
        columns = [c["name"] for c in old["tables"][key]["columns"]]
        twin = next((a for a in added if [c["name"] for c in new["tables"][a]["columns"]] == columns), None)
        out["refusals"].append(f"{key}: rename of table to {twin}" if twin else f"{key}: drop of table")
    for key, spec in new["tables"].items():
        if key in old["tables"]:
            _table_changes(key, old["tables"][key], spec, out)
        else:
            out["tables"].append(spec)
            out["fks"] += [(key, fk) for fk in spec["fks"]]
            out["indexes"] += [(key, idx) for idx in spec["indexes"]]
    for name, sql in new["functions"].items():
        if name not in old["functions"]:
            out["functions"].append((name, sql))
        elif old["functions"][name] != sql:
            out["refusals"].append(f"{name}: change of function body")
    out["refusals"] += [f"{n}: drop of function" for n in old["functions"] if n not in new["functions"]]
    return out


def has_changes(changes):
    return any(changes[k] for k in changes if k != "refusals")


def _check_name(table, expr):
    return f"{table}_chk_{hashlib.sha256(expr.encode('utf-8')).hexdigest()[:8]}"


def _create_table(spec):
    lines = [f"    {c['name']} {c['sql_type']}{' NOT NULL' if c['not_null'] else ''}" for c in spec["columns"]]
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
        out.append(f"ALTER TABLE {key} ADD COLUMN {col['name']} {col['sql_type']}"
                   f"{' NOT NULL' if col['not_null'] else ''};")
    for key, expr in changes["checks"]:
        out.append(f"ALTER TABLE {key} ADD CONSTRAINT {_check_name(key.split('.')[1], expr)} CHECK ({expr});")
    for key, fk in changes["fks"]:
        out.append(f"ALTER TABLE {key} ADD CONSTRAINT {fk['name']} FOREIGN KEY ({', '.join(fk['columns'])}) "
                   f"REFERENCES {fk['to']} ({', '.join(fk['ref'])}) DEFERRABLE INITIALLY DEFERRED;")
    out += [f"ALTER TABLE {s['schema']}.{s['name']} ENABLE ROW LEVEL SECURITY;" for s in changes["tables"]]
    out += [f"GRANT USAGE ON SCHEMA {s} TO etl_writer, etl_reader;" for s in changes["schemas"] if s in GRANTED_SCHEMAS]
    for spec in changes["tables"]:
        if spec["schema"] not in GRANTED_SCHEMAS:
            continue
        qualified = f"{spec['schema']}.{spec['name']}"
        out += [f"GRANT SELECT, INSERT, UPDATE, DELETE ON {qualified} TO etl_writer;",
                f"GRANT SELECT ON {qualified} TO etl_reader;",
                f"CREATE POLICY etl_writer_all ON {qualified} FOR ALL TO etl_writer USING (true) WITH CHECK (true);",
                f"CREATE POLICY etl_reader_select ON {qualified} FOR SELECT TO etl_reader USING (true);"]
    for name, sql in changes["functions"]:
        out += [sql, f"REVOKE EXECUTE ON FUNCTION {name}() FROM PUBLIC;",
                f"GRANT USAGE ON SCHEMA {name.split('.')[0]} TO etl_writer;",
                f"GRANT EXECUTE ON FUNCTION {name}() TO etl_writer;"]
    for key, idx in changes["indexes"]:
        where = f" WHERE {idx['where']}" if idx["where"] else ""
        out.append(f"CREATE {'UNIQUE ' if idx['unique'] else ''}INDEX {idx['name']} ON {key} "
                   f"({', '.join(idx['columns'])}){where};")
    return "\n\n".join(out) + "\n"


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
        old = load_state(out / STATE_FILE)
        name = _ident(args.name or ("registry_update" if old["tables"] else "initial_schema"), "migration name")
    except (RegistryError, OSError, yaml.YAMLError) as exc:
        print(f"generate_migrations: {exc}", file=sys.stderr)
        return 2
    changes = diff(old, new)
    if changes["refusals"]:
        print("generate_migrations: refused, no file written:", file=sys.stderr)
        for line in changes["refusals"]:
            print(f"  {line}", file=sys.stderr)
        return 1
    if not has_changes(changes):
        print("generate_migrations: no change")
        return 0
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
    path = out / "migrations" / f"{stamp}_{name}.sql"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as fh:
            fh.write(f"-- registry_state sha256: {state_sha(new)}\n\n{render(changes)}")
    except OSError as exc:
        print(f"generate_migrations: {exc}", file=sys.stderr)
        return 2
    with (out / STATE_FILE).open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(dump_state(new))
    print(f"generate_migrations: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

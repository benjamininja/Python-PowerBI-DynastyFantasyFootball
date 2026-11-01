#!/usr/bin/env python
"""check_data_model.py — validate and render the logical data-model manifest.

docs/data_model.yml is the SSOT for the star-schema graph. This script:

  validate (default)  schema-check all tables; assert each table's declared
                      columns match the real data/{name}.parquet schema
                      (name + dtype); assert every edge target/via resolves
                      to a declared table; assert every column has a
                      sql_type that fits its dtype, every pk equals its
                      grain, every fk resolves to a key of the same type,
                      and the other_tables (no parquet file) are well
                      formed. Exit 1 on any failure.
  --render            regenerate the Mermaid flowchart region in
                      docs/DATA_MODEL.md from the yaml (between the
                      BEGIN/END GENERATED markers).
  --check             render in-memory and diff against DATA_MODEL.md; exit 1
                      if stale (CI guard against a hand-edited / forgotten
                      diagram, or a parquet schema that drifted out from
                      under it).

Run via the .venv (PyYAML lives there):
    .\\run.ps1 scripts/check_data_model.py
    .\\run.ps1 scripts/check_data_model.py --render
    .\\run.ps1 scripts/check_data_model.py --check
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parent.parent
# The schema rule is shared with the publish gate (notebooks/etl_checks.py).
sys.path.insert(0, str(REPO / "notebooks"))
import etl_checks  # noqa: E402
import etl_helpers  # noqa: E402

MODEL_YML = REPO / "docs" / "data_model.yml"
MODEL_MD = REPO / "docs" / "DATA_MODEL.md"

VALID_TYPES = {"dim", "fact", "resolver"}
# Every column declares one of these (ADR-0018 decision 8). There is no
# bigint: a value past the integer range is a finding, not a wider type.
SQL_TYPES = {"text", "integer", "double precision", "boolean", "date",
             "timestamp", "timestamptz", "jsonb", "uuid"}
SCHEMAS = ("football", "shared", "ops")
# The types a pandas dtype may be declared as. `object` holds no value yet,
# so it may be any. A string column of ISO dates is `date`; a whole-number
# float column is `integer`. A zone-aware datetime is `timestamptz`
# (decision 8, amended 2026-10-31); a naive one is `timestamp`.
DTYPE_SQL_TYPES = {
    "str": {"text", "date"}, "string": {"text", "date"},
    "int32": {"integer"}, "int64": {"integer"}, "Int64": {"integer"},
    "float64": {"double precision", "integer"},
    "bool": {"boolean"},
}
REQUIRED_FIELDS = ("name", "type", "grain", "columns")
OTHER_REQUIRED_FIELDS = ("name", "schema", "columns", "pk")
MARKER_GROUP = "data-model-graph"


# --- markers -----------------------------------------------------------
def _markers() -> tuple[str, str]:
    begin = f"<!-- BEGIN GENERATED {MARKER_GROUP} — regen: python scripts/check_data_model.py --render -->"
    end = f"<!-- END GENERATED {MARKER_GROUP} -->"
    return begin, end


# --- io ------------------------------------------------------------------
def load_yaml() -> dict:
    with MODEL_YML.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --- validation ------------------------------------------------------------
def _fits(dtype: str, sql_type: str) -> bool:
    if dtype.startswith("datetime64"):
        return sql_type == ("timestamptz" if "," in dtype else "timestamp")
    allowed = DTYPE_SQL_TYPES.get(dtype)
    return allowed is None or sql_type in allowed


def sql_type_errors(table: dict) -> list[str]:
    """Every column declares a known `sql_type` that fits its dtype."""
    errs = []
    for col in table.get("columns") or []:
        sql_type = col.get("sql_type")
        dtype = str(col.get("dtype"))
        where = f"[{table.get('name')}] {col.get('name')}"
        if sql_type is None:
            errs.append(f"{where}: needs a sql_type")
        elif sql_type not in SQL_TYPES:
            errs.append(f"{where}: sql_type {sql_type!r} is not one of {sorted(SQL_TYPES)}")
        elif not _fits(dtype, sql_type):
            errs.append(f"{where}: sql_type {sql_type!r} does not fit dtype {dtype}")
    return errs


def _names(value) -> list[str] | None:
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return value
    return None


def key_errors(table: dict, by_name: dict[str, dict]) -> list[str]:
    """`pk`, `required_keys`, `fk`, `checks` and `indexes` of one table.

    `by_name` holds every declared table (`tables` and `other_tables`), for the
    foreign-key targets."""
    name = table.get("name")
    errs: list[str] = []
    types = {c.get("name"): c.get("sql_type") for c in table.get("columns") or []}

    def known(cols, what):
        errs.extend(f"[{name}] {what} column {c!r} is not a column of the table"
                    for c in cols if c not in types)

    pk = _names(table.get("pk"))
    if pk is None:
        errs.append(f"[{name}] pk must be a list of columns")
    else:
        known(pk, "pk")
        if "grain" in table:
            grain = etl_helpers.table_grain({"grain": table["grain"]})
            if pk != grain:
                errs.append(f"[{name}] pk {pk} differs from grain {grain}")
    if table.get("required_keys") is not None:
        required = _names(table["required_keys"])
        if required is None:
            errs.append(f"[{name}] required_keys must be a list of columns")
        else:
            known(required, "required_keys")

    for fk in table.get("fk") or []:
        cols, ref, to = _names(fk.get("columns")), _names(fk.get("ref")), fk.get("to")
        where = f"[{name}] fk {fk.get('columns')} -> {to}"
        target = by_name.get(to)
        if cols is None or ref is None:
            errs.append(f"{where}: columns and ref must be lists of columns")
        elif target is None:
            errs.append(f"{where}: target is not a declared table")
        else:
            known(cols, "fk")
            target_types = {c.get("name"): c.get("sql_type") for c in target.get("columns") or []}
            if len(cols) != len(ref):
                errs.append(f"{where}: columns and ref differ in length")
            elif any(r not in target_types for r in ref):
                errs.append(f"{where}: ref {ref} is not a column of {to}")
            else:
                if sorted(ref) != sorted(target.get("pk") or []):
                    errs.append(f"{where}: ref {ref} is not the primary key of {to}")
                for c, r in zip(cols, ref):
                    if c in types and types[c] != target_types[r]:
                        errs.append(f"{where}: {c} is {types[c]}, {to}.{r} is {target_types[r]}")

    for expr in table.get("checks") or []:
        if not isinstance(expr, str) or not expr.strip():
            errs.append(f"[{name}] a check must be a SQL expression")
    for idx in table.get("indexes") or []:
        cols = _names(idx.get("columns")) if isinstance(idx, dict) else None
        if cols is None:
            errs.append(f"[{name}] an index needs a list of columns")
        else:
            known(cols, "index")
    return errs


def other_table_errors(table: dict, seen: set[str]) -> list[str]:
    """A table with no parquet file: its fields, schema and name."""
    name = table.get("name")
    errs = [f"[{name}] missing required field '{f}'" for f in OTHER_REQUIRED_FIELDS if f not in table]
    if table.get("schema") not in SCHEMAS:
        errs.append(f"[{name}] schema must be one of {list(SCHEMAS)}, got {table.get('schema')!r}")
    if not isinstance(table.get("columns", []), list):
        errs.append(f"[{name}] columns must be a list")
    if name in seen:
        errs.append(f"[{name}] duplicate name")
    return errs


def validate(data: dict) -> int:
    tables = data.get("tables", []) or []
    errors: list[str] = []

    seen_names: set[str] = set()
    for i, t in enumerate(tables):
        tag = t.get("name", f"<index {i}>")
        for field in REQUIRED_FIELDS:
            if field not in t:
                errors.append(f"[{tag}] missing required field '{field}'")
        name = t.get("name")
        if name in seen_names:
            errors.append(f"[{tag}] duplicate name")
        seen_names.add(name)
        if t.get("type") not in VALID_TYPES:
            errors.append(f"[{tag}] type must be one of {sorted(VALID_TYPES)}, got {t.get('type')!r}")
        if not isinstance(t.get("columns", []), list):
            errors.append(f"[{tag}] columns must be a list")

    others = data.get("other_tables", []) or []
    by_name = {t.get("name"): t for t in tables + others}
    for t in tables:
        errors += sql_type_errors(t)
        errors += key_errors(t, by_name)
    for t in others:
        errors += other_table_errors(t, seen_names)
        seen_names.add(t.get("name"))
        errors += sql_type_errors(t)
        errors += key_errors(t, by_name)

    # column-drift check: declared columns vs real parquet schema
    for t in tables:
        name = t.get("name")
        try:
            stored = etl_helpers.read_stored(name)   # uncast: this is the drift check
        except FileNotFoundError:
            errors.append(f"[{name}] no data/{name}.parquet found on disk")
            continue
        real_cols = {c: str(d) for c, d in stored.dtypes.items()}
        errors += etl_checks.schema_errors(t, real_cols)

    # edge-target check: every edge.to / edge.via must be a declared table
    for t in tables:
        tag = t.get("name")
        for edge in t.get("edges") or []:
            to = edge.get("to")
            via = edge.get("via")
            if to not in seen_names:
                errors.append(f"[{tag}] edge target '{to}' not a declared table")
            if via not in ("direct", None) and via not in seen_names:
                errors.append(f"[{tag}] edge via '{via}' not a declared table")

    for e in errors:
        print(f"FAIL  {e}")
    n_tables = len(tables)
    if errors:
        print(f"\n{len(errors)} failure(s) — {n_tables} tables checked.")
        return 1
    print(f"OK — {n_tables} tables validated against real parquet schemas.")
    return 0


# --- render ----------------------------------------------------------------
def _node_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def _node_decl(t: dict) -> str:
    name = t["name"]
    nid = _node_id(name)
    ttype = t["type"]
    if ttype == "resolver":
        return f"{nid}{{{{{name}}}}}"
    if ttype == "fact":
        return f"{nid}[({name})]"
    return f"{nid}[{name}]"


def render_mermaid(data: dict) -> str:
    tables = data.get("tables", []) or []
    by_name = {t["name"]: t for t in tables}
    lines = ["```mermaid", "graph LR"]

    for t in tables:
        lines.append(f"    {_node_decl(t)}")

    seen_edges: set[tuple[str, str, str]] = set()
    for t in tables:
        src = _node_id(t["name"])
        for edge in t.get("edges") or []:
            to = edge["to"]
            via = edge.get("via", "direct")
            dst = _node_id(to)
            key = (src, dst, via)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            if via == "direct":
                lines.append(f"    {src} --> {dst}")
            else:
                via_id = _node_id(via)
                lines.append(f"    {src} -.via {via}.-> {dst}")

    lines.append("")
    lines.append("    classDef resolver fill:#3b2f4f,stroke:#a78bfa,stroke-width:2px;")
    lines.append("    classDef fact fill:#1e3a5f,stroke:#60a5fa,stroke-width:1px;")
    lines.append("    classDef dim fill:#1f2937,stroke:#9ca3af,stroke-width:1px;")
    for t in tables:
        nid = _node_id(t["name"])
        lines.append(f"    class {nid} {t['type']};")

    lines.append("```")
    return "\n".join(lines)


def render_md(data: dict, current: str) -> str:
    begin, end = _markers()
    block = f"{begin}\n{render_mermaid(data)}\n{end}"
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(current):
        raise SystemExit(f"marker pair not found in {MODEL_MD.name}")
    return pattern.sub(lambda _m, b=block: b, current)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--render", action="store_true", help="regenerate the DATA_MODEL.md Mermaid region")
    ap.add_argument("--check", action="store_true", help="fail if DATA_MODEL.md is stale vs the yaml")
    args = ap.parse_args()

    data = load_yaml()

    if args.render:
        new = render_md(data, MODEL_MD.read_text(encoding="utf-8"))
        MODEL_MD.write_text(new, encoding="utf-8", newline="\n")
        print(f"rendered graph into {MODEL_MD.relative_to(REPO)}")
        return 0

    if args.check:
        current = MODEL_MD.read_text(encoding="utf-8")
        if render_md(data, current) != current:
            print("FAIL  DATA_MODEL.md is stale — run: python scripts/check_data_model.py --render")
            return 1
        print("OK — DATA_MODEL.md matches data_model.yml.")
        return 0

    return validate(data)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""check_data_model.py — validate and render the logical data-model manifest.

docs/data_model.yml is the SSOT for the star-schema graph. This script:

  validate (default)  schema-check all tables; assert each table's declared
                      columns match the real data/{name}.parquet schema
                      (name + dtype); assert every edge target/via resolves
                      to a declared table. Exit 1 on any failure.
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
MODEL_YML = REPO / "docs" / "data_model.yml"
MODEL_MD = REPO / "docs" / "DATA_MODEL.md"
DATA_DIR = REPO / "data"

VALID_TYPES = {"dim", "fact", "resolver"}
REQUIRED_FIELDS = ("name", "type", "grain", "columns")
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

    # column-drift check: declared columns vs real parquet schema
    for t in tables:
        name = t.get("name")
        parquet_path = DATA_DIR / f"{name}.parquet"
        if not parquet_path.exists():
            errors.append(f"[{name}] no data/{name}.parquet found on disk")
            continue
        real_cols = {c: str(d) for c, d in pd.read_parquet(parquet_path).dtypes.items()}
        declared = {c["name"]: str(c["dtype"]) for c in (t.get("columns") or [])}
        missing = set(real_cols) - set(declared)
        extra = set(declared) - set(real_cols)
        if missing:
            errors.append(f"[{name}] parquet has undeclared columns: {sorted(missing)}")
        if extra:
            errors.append(f"[{name}] yaml declares columns not in parquet: {sorted(extra)}")
        for col, dtype in declared.items():
            if col in real_cols and real_cols[col] != dtype:
                errors.append(
                    f"[{name}].{col}: yaml dtype '{dtype}' != parquet dtype '{real_cols[col]}'"
                )

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

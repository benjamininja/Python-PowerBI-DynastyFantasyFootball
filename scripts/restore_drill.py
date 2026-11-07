"""The restore drill (#138; ADR-0014, ADR-0018, #135 Q4).

Rebuilds the football schema from the published snapshot in the throwaway
database of the storage-pg CI job (TEST_DATABASE_URL, the migrations already
applied), proves the load equals the snapshot, and prints one line per table:

  <table> <rows> <md5>

The manager runs the same checksum query, printed by --print-sql, against the
live project through the read-only supabase-dynasty server and compares the
two sets of lines table by table. Nothing here connects to the live project:
the URL must be exactly TEST_DATABASE_URL, and --print-sql connects to nothing.

  1. The login must be etl_writer, without BYPASSRLS or superuser, with
     row-level security on every football table, and every football table
     must be empty. Otherwise exit 2, nothing written.
  2. Every data/*.parquet is loaded in one transaction and read back equal
     (replace=False, verify=True). A problem exits 1 with nothing committed.
  3. The checksum query runs on the committed load and prints the lines.
  4. The football tables are emptied again, whatever happened.

The output holds table names, counts and checksums only, never a cell, and a
failure prints one scrubbed line with no traceback: the CI log is public.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))
import backfill_postgres as backfill  # noqa: E402
import etl_helpers as etl  # noqa: E402
import etl_storage_pg as pg  # noqa: E402

EMPTY = hashlib.md5(b"").hexdigest()
STAMP = 'YYYY-MM-DD"T"HH24:MI:SS.US'
_SHA = re.compile(r"[0-9a-f]{7,64}")


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _shown(column: str, sql_type: str) -> str:
    """One column as text, the same on every server and in every session:
    no DateStyle, extra_float_digits or time zone is read."""
    ident = _ident(column)
    if sql_type == "text":
        return ident
    if sql_type == "double precision":
        return f"encode(float8send({ident}), 'hex')"
    if sql_type == "date":
        return f"to_char({ident}, 'YYYY-MM-DD')"
    if sql_type == "timestamp":
        return f"to_char({ident}, '{STAMP}')"
    if sql_type == "timestamptz":
        return f"to_char({ident} AT TIME ZONE 'UTC', '{STAMP}')"
    return f"{ident}::text"


def checksum_sql(tables) -> str:
    """One read-only SELECT, one row per table: its name, its row count and
    the md5 of its rows' md5s taken in primary-key order (an empty table gives
    the md5 of the empty string). Columns run in docs/data_model.yml order.
    No SET, temp object or function is created, so it runs in a read-only
    transaction, in CI and on the live project alike."""
    state = pg._state()
    branches = []
    for name in tables:
        spec = state.get(name)
        if spec is None:
            raise ValueError(f"{name}: not in supabase/registry_state.json")
        types = {c["name"]: c["sql_type"] for c in spec["columns"]}
        columns = [c["name"] for c in etl._table_entry(name)["columns"]]
        if set(columns) != set(types):
            raise ValueError(f"{name}: the registry and registry_state.json declare different columns")
        row = ", ".join(_shown(c, types[c]) for c in columns)
        order = ", ".join(f'({_shown(c, types[c])}) COLLATE "C"' for c in spec["pk"])
        branches.append(
            f"SELECT {_literal(name)} AS table_name, count(*) AS row_count, "
            f"coalesce(md5(string_agg(md5(ROW({row})::text), ',' ORDER BY {order})), "
            f"{_literal(EMPTY)}) AS checksum "
            f"FROM {_ident(spec['schema'])}.{_ident(name)}")
    return "\nUNION ALL\n".join(branches) + "\nORDER BY 1"


def checksum_lines(conn, tables) -> list[str]:
    """`<table> <rows> <md5>` for each of `tables`, in the order given."""
    found = {name: (rows, digest) for name, rows, digest in conn.execute(checksum_sql(tables)).fetchall()}
    return [f"{name} {found[name][0]} {found[name][1]}" for name in tables]


def snapshot_commit() -> str:
    sha = os.environ.get("GITHUB_SHA", "")
    if not _SHA.fullmatch(sha):
        try:
            done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                                  text=True, timeout=30, check=False)
            sha = done.stdout.strip() if done.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            sha = ""
    return sha if _SHA.fullmatch(sha) else "unknown"


def run(url: str, frames: dict, out=print) -> int:
    psycopg, _ = pg._psycopg()
    tables = sorted(frames)
    allowed = os.environ.get(pg.TEST_URL_ENV)
    if not allowed or url != allowed:
        out(f"refused: the drill runs only against {pg.TEST_URL_ENV}")
        out("nothing was written")
        return 2
    with psycopg.connect(url, prepare_threshold=None) as conn:
        refusals = pg.login_problems(pg.login_facts(conn), tables)
        if not refusals:
            refusals = [f"{pg.SCHEMA}.{name} already holds rows; the drill needs an empty schema"
                        for name in pg.nonempty(conn, tables)]
    if refusals:
        for line in refusals:
            out(f"refused: {line}")
        out("nothing was written")
        return 2
    try:
        loaded = pg.load_published(url, frames, replace=False, verify=True)
        if loaded.problems:
            for line in loaded.problems:
                out(f"failed: {line}")
            out("rolled back; nothing was committed")
            return 1
        with psycopg.connect(url, prepare_threshold=None) as conn:
            lines = checksum_lines(conn, tables)
        for line in lines:
            out(line)
        out(f"snapshot {snapshot_commit()} {len(tables)} table(s), "
            f"{sum(loaded.counts.values())} row(s) loaded and read back equal")
        return 0
    finally:
        pg.clear_published(url, tables)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print-sql", action="store_true",
                    help="print the checksum query and exit; connects to nothing")
    args = ap.parse_args(argv)
    try:
        if args.print_sql:
            print(checksum_sql(etl.published_names()))
            return 0
        url = os.environ.get(pg.TEST_URL_ENV)
        if not url:
            print(f"refused: {pg.TEST_URL_ENV} is not set")
            return 2
        return run(url, backfill.published_frames())
    except backfill.Refused as exc:
        print(f"refused: {pg.scrub(exc)}")
        return 2
    except Exception as exc:
        print(f"stopped: {pg.describe(exc)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

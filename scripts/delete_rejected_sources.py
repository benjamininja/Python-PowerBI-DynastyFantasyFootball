"""Delete the rows of the rejected sources, KeepTradeCut and FantasyPros, from
the five football tables that still hold them (#459, B10; ADR-0014, ADR-0018).

The owner runs this, never an agent, once, against the database in
SUPABASE_DB_URL (the environment variable, or the line in the repo's .env, as
scripts/run_pipeline.py reads it). The login is etl_writer, which holds DELETE
and an ALL policy on these tables (supabase/migrations/20261101154326_initial_schema.sql).

  .\\run.ps1 scripts\\delete_rejected_sources.py           dry run (the default)
  .\\run.ps1 scripts\\delete_rejected_sources.py --apply   delete

  1. The login must be etl_writer, without BYPASSRLS or superuser, and every
     football table must have row-level security on (as backfill_postgres.py).
  2. The dry run opens a read-only session. It prints, per table and per source,
     the count it would delete beside the count #459 expects, and exits 1 if any
     count differs.
  3. --apply counts first, inside its transaction, and rolls back with exit 1
     before any DELETE if any count differs from #459's (there is no override).
     Otherwise it deletes in the same transaction, the fact rows before
     dim_dynasty_metric (the foreign key), checks the foreign keys, counts again,
     and rolls back unless every count is zero.

Exit 0: dry run matched, or committed. Exit 1: a count differs, rolled back or
failed. Exit 2: refused before any write. The output holds table names, source
names and counts only, never a cell, and a failure prints one scrubbed line with
no traceback and never the database URL.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
import etl_run_log  # noqa: E402
import etl_storage_pg as pg  # noqa: E402


class Target(NamedTuple):
    table: str
    column: str
    sources: tuple  # (source literal, count #459 expects)


# Delete order: the fact rows first, dim_dynasty_metric last (the foreign key
# fact_dynasty_ranking_metrics.metric_key -> dim_dynasty_metric.metric_key).
TARGETS = (
    Target("fact_dynasty_ranking_metrics", "source_name", (("KTC", 15730), ("FantasyPros", 3966))),
    Target("fact_rookie_rankings", "source_site", (("KeepTradeCut", 54), ("FantasyPros", 422))),
    Target("dim_dynasty_crosswalk", "source", (("KTC", 464), ("FantasyPros", 661))),
    Target("dim_pick_value_curve", "source_name", (("KTC", 36),)),
    Target("dim_dynasty_metric", "source_name", (("KTC", 17), ("FantasyPros", 6))),
)


def database_url() -> str | None:
    return os.environ.get(pg.URL_ENV) or etl_run_log.env_value(pg.URL_ENV)


def described(exc: BaseException, url: str) -> str:
    """`pg.describe(exc)` with the URL, and its user, password and host, taken out of an
    error that is not a psycopg one (those print class, SQLSTATE and names only).
    The redaction runs before the scrub, which cuts at the first line and 200 characters."""
    psycopg, _ = pg._psycopg()
    if isinstance(exc, psycopg.Error):
        return pg.describe(exc)
    parts = urlsplit(url)
    text = str(exc)
    for secret in (url, parts.netloc, parts.password, parts.username, parts.hostname):
        if secret:
            text = text.replace(secret, "<url>")
    return f"{type(exc).__name__}: {pg.scrub(text)}"


def connect(url: str):
    psycopg, _ = pg._psycopg()
    return psycopg.connect(url, prepare_threshold=None)


def count(conn, target: Target, source: str) -> int:
    return conn.execute(
        f'SELECT count(*) FROM {pg.SCHEMA}."{target.table}" WHERE "{target.column}" = %s',
        (source,)).fetchone()[0]


def counts(conn) -> dict:
    return {(t.table, source): count(conn, t, source) for t in TARGETS for source, _ in t.sources}


def show(out, found: dict, verb: str) -> bool:
    """One line per table and source; True when every count is #459's."""
    same = True
    for t in TARGETS:
        for source, expected in t.sources:
            n = found[(t.table, source)]
            same = same and n == expected
            out(f"{t.table} where {t.column} = {source}: {n} row(s) {verb} "
                f"(#459 expects {expected}: {'match' if n == expected else 'DIFFERS'})")
    return same


def run(url: str, *, apply: bool = False, out=print, connector=None) -> int:
    connector = connector or connect
    tables = [t.table for t in TARGETS]
    with connector(url) as conn:
        if not apply:
            conn.read_only = True
        refusals = pg.login_problems(pg.login_facts(conn), tables)
        if refusals:
            for line in refusals:
                out(f"refused: {line}")
            out("nothing was deleted")
            return 2
        before = counts(conn)
        same = show(out, before, "found" if apply else "would be deleted")
        if not apply:
            out("counts match #459's" if same else "counts DIFFER from #459's: do not --apply")
            out("dry run: nothing was deleted")
            return 0 if same else 1
        if not same:
            conn.rollback()
            out("counts DIFFER from #459's; rolled back; nothing was deleted")
            return 1
        pg.bound_locks(conn)
        for t in TARGETS:
            cur = conn.execute(
                f'DELETE FROM {pg.SCHEMA}."{t.table}" WHERE "{t.column}" = ANY(%s)',
                ([source for source, _ in t.sources],))
            out(f"{t.table}: {cur.rowcount} row(s) deleted")
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
        after = counts(conn)
        left = {key: n for key, n in after.items() if n}
        if left:
            conn.rollback()
            for (table, source), n in sorted(left.items()):
                out(f"{table} where source = {source}: {n} row(s) left")
            out("rolled back; nothing was deleted")
            return 1
        conn.commit()
        out(f"committed: {sum(before.values())} row(s) deleted from {len(TARGETS)} table(s); "
            f"every count is zero")
        return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="delete (the default is a dry run that deletes nothing)")
    args = ap.parse_args(argv)
    url = database_url()
    if not url:
        print(f"refused: {pg.URL_ENV} is not set")
        return 2
    try:
        return run(url, apply=args.apply)
    except Exception as exc:
        print(f"stopped, nothing was committed: {described(exc, url)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

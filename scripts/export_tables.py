"""Write named tables from the database to the published snapshot (#459, B10;
ADR-0014).

The owner runs this, never an agent, against the database in SUPABASE_DB_URL
(the environment variable, or the line in the repo's .env). It calls
etl_storage_pg.export_published, the exporter the pipeline's publish step uses:
rows sorted by primary key, columns and dtypes following the snapshot already in
the folder. It is the way to re-export a table the pipeline does not stage,
such as the manual-only dim_pick_value_curve.

  .\\run.ps1 scripts\\export_tables.py TABLE [TABLE ...] [--out DIR]

--out is an existing folder and defaults to data/. The session is read-only.
Every table is read before any file is written.

Exit 0: written. Exit 1: failed. Exit 2: refused before any read. The output
holds table names and counts only, never a cell, and never the database URL.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
import etl_helpers as etl  # noqa: E402
import etl_run_log  # noqa: E402
import etl_storage_pg as pg  # noqa: E402


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


def run(names, out_dir, *, out=print) -> int:
    changes: dict = {}
    with pg.session_read_only():
        written = pg.export_published(names, out_dir, changes)
    for name in names:
        out(f"{name}: {written[name]} row(s) written")
    for name, change in sorted(changes.items()):
        out(f"{name}: snapshot columns changed, added {change['added']} dropped {change['dropped']}")
    out(f"wrote {len(names)} table(s)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tables", nargs="+", metavar="table", help="a published table, by name")
    ap.add_argument("--out", metavar="DIR", default=None,
                    help="an existing folder to write <table>.parquet into (default: data/)")
    args = ap.parse_args(argv)
    names = list(dict.fromkeys(args.tables))
    published = etl.published_names()
    unknown = [n for n in names if n not in published]
    if unknown:
        print(f"refused: not a published table: {', '.join(unknown)}")
        return 2
    out_dir = Path(args.out) if args.out else Path(etl.DATA)
    if not out_dir.is_dir():
        print("refused: --out is not an existing folder")
        return 2
    url = database_url()
    if not url:
        print(f"refused: {pg.URL_ENV} is not set")
        return 2
    os.environ[pg.URL_ENV] = url
    try:
        return run(names, out_dir)
    except Exception as exc:
        print(f"stopped: {described(exc, url)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Load the published snapshot into the football schema of the database in
SUPABASE_DB_URL (#135, B3; ADR-0014, ADR-0018).

Run by .github/workflows/backfill.yml when the owner starts it, as the
etl_writer login. Nothing here is run by an agent against the real project.

  1. The login must be etl_writer, without BYPASSRLS or superuser, and every
     football table must have row-level security on.
  2. Every football table must be empty, unless --replace is passed. That
     check runs inside the load transaction, under a table lock.
  3. Every data/*.parquet is read as stored and loaded in ONE transaction (the
     foreign keys are deferred, so the order does not matter). Each table is
     then read back inside that transaction and compared with the snapshot,
     rows sorted by key. An empty table is compared too.
  4. Any refusal, difference or error rolls the whole load back.

Exit 0: committed. Exit 1: rolled back or failed. Exit 2: refused before any
write. The output holds table names and counts only, never a cell, and a
failure prints one scrubbed line with no traceback: the workflow log is public.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
import etl_helpers as etl  # noqa: E402
import etl_storage_pg as pg  # noqa: E402


class Refused(Exception):
    """A refusal before any write. The message holds names and counts only."""


def published_frames(data_dir: Path | str | None = None) -> dict:
    """Every table of the registry, as the snapshot in `data_dir` stores it."""
    folder = Path(data_dir) if data_dir is not None else Path(etl.DATA)
    declared = sorted(etl._registry())
    stored = sorted(p.stem for p in folder.glob("*.parquet"))
    if stored != declared:
        raise Refused("the snapshot and the registry name different tables -- "
                      f"no snapshot for [{', '.join(sorted(set(declared) - set(stored)))}], "
                      f"not in the registry [{', '.join(sorted(set(stored) - set(declared)))}]")
    return {name: etl.read_stored(name, folder) for name in declared}


def run(url: str, frames: dict, *, replace: bool = False, out=print) -> int:
    psycopg, _ = pg._psycopg()
    tables = sorted(frames)
    with psycopg.connect(url, prepare_threshold=None) as conn:
        refusals = pg.login_problems(pg.login_facts(conn), tables)
    if refusals:
        for line in refusals:
            out(f"refused: {line}")
        out("nothing was written")
        return 2
    loaded = pg.load_published(url, frames, replace=replace, verify=True, empty_only=not replace)
    if loaded.refused:
        for line in loaded.problems:
            out(f"refused: {line}")
        out("nothing was written")
        return 2
    if loaded.problems:
        for line in loaded.problems:
            out(f"failed: {line}")
        out("rolled back; nothing was committed")
        return 1
    for name in tables:
        out(f"{name}: {loaded.counts[name]} row(s) loaded and read back equal to the snapshot")
    out(f"committed {len(tables)} table(s), {sum(loaded.counts.values())} row(s)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replace", action="store_true",
                    help="empty each table first, instead of refusing a table that holds rows")
    args = ap.parse_args(argv)
    url = os.environ.get(pg.URL_ENV)
    if not url:
        print(f"refused: {pg.URL_ENV} is not set")
        return 2
    try:
        return run(url, published_frames(), replace=args.replace)
    except Refused as exc:
        print(f"refused: {pg.scrub(exc)}")
        return 2
    except Exception as exc:
        print(f"stopped, nothing was committed: {pg.describe(exc)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

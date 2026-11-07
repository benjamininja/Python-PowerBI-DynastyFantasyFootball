"""Compare what 02d and 04z left in the store with the published snapshot (#93, brief 6).

    compare_loader_output.py [--snapshot DIR]

The owner runs it after the one-time loader and after 02d and 04z have run with
ETL_STORAGE=postgres. For each of the four tables they write, it reads the
store through the seam (the database under ETL_STORAGE=postgres) and the
snapshot folder (default data/, which a Postgres run leaves at HEAD), and
prints one line: the table name, both row counts, the keys held on one side
only, and the keys whose cells differ. Names and counts only: no cell value,
no column name, no key value. Exit 0 when every table matches, 1 otherwise.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
import etl_helpers as etl  # noqa: E402
import etl_storage_pg as pg  # noqa: E402
sys.path.insert(0, str(REPO / "scripts"))
import load_draft_and_overrides as loader  # noqa: E402

TABLES = ("fact_roster_transactions", "dim_roster_asset", "fact_draft_pick",
          "dim_fantrax_crosswalk")


def compare(store: pd.DataFrame, snapshot: pd.DataFrame, entry: dict) -> dict:
    """Counts of how `store` differs from `snapshot` on the table's key."""
    key = etl.table_grain(entry)
    columns = [c for c in snapshot.columns if c in store.columns]
    left = pg.prepared(store, entry).set_index(key)
    right = pg.prepared(snapshot, entry).set_index(key)
    both = left.index.intersection(right.index)
    differing = pd.Series(False, index=both)
    for col in columns:
        if col not in key:
            differing |= pg._unequal(left.loc[both, col], right.loc[both, col])
    return {"store_rows": len(store), "snapshot_rows": len(snapshot),
            "only_store": len(left.index.difference(right.index)),
            "only_snapshot": len(right.index.difference(left.index)),
            "differing": int(differing.sum()),
            "columns_apart": len(set(store.columns) ^ set(snapshot.columns))}


def run(snapshot_dir: Path, tables=TABLES, out=print) -> int:
    bad = 0
    for name in tables:
        entry = etl._table_entry(name)
        try:
            store = etl.read_stored(name)
            snapshot = etl.read_stored(name, snapshot_dir)
        except etl.TableNotFound:
            out(f"MISSING   {name}")
            bad += 1
            continue
        c = compare(store, snapshot, entry)
        same = not (c["only_store"] or c["only_snapshot"] or c["differing"]
                    or c["columns_apart"] or c["store_rows"] != c["snapshot_rows"])
        bad += not same
        out(f"{'identical' if same else 'DIFFERS':9s} {name}: store {c['store_rows']} row(s), "
            f"snapshot {c['snapshot_rows']}, keys only in store {c['only_store']}, "
            f"only in snapshot {c['only_snapshot']}, keys with differing cells {c['differing']}, "
            f"columns apart {c['columns_apart']}")
    out(f"tables {len(tables)}: differing {bad}")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--snapshot", type=Path, default=etl.DATA,
                    help="folder holding the published parquet files (default: data/)")
    args = ap.parse_args(argv)
    try:
        print(f"storage: {loader.use_env_file()}")
        return run(args.snapshot)
    except Exception as exc:
        print(f"stopped: {type(exc).__name__} (no detail printed: it may hold a value)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

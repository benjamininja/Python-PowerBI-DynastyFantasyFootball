"""Compare the crosswalk 04z WOULD write from a saved getPlayerIds response
with the live crosswalk (#519).

    compare_playerids_crosswalk.py <saved getPlayerIds response (JSON)>

The owner (or the manager, from the owner's word) runs it. It writes nothing
and fetches nothing:

  - the connection is read-only, as in compare_loader_output.py;
  - 04z runs in capture mode against the tables the store holds, with
    `etl.fantrax_player_ids` reading the saved file instead of calling Fantrax;
  - the crosswalk it would write is compared with the one the store holds.

It prints counts only: how many keys exist on one side only, how many keys
have any differing cell, and how many differ in each column. No key value and
no cell value. Exit 0 when the crosswalk is identical, 1 otherwise.
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_loader_output as base  # noqa: E402

etl = base.etl
pg = base.pg
TABLE = "dim_fantrax_crosswalk"


def column_differences(live: pd.DataFrame, new: pd.DataFrame, entry: dict) -> dict:
    """Per column, how many keys held by both sides differ in that column."""
    key = etl.table_grain(entry)
    left = pg.prepared(live, entry).set_index(key)
    right = pg.prepared(new, entry).set_index(key)
    both = left.index.intersection(right.index)
    return {col: int(pg._unequal(left.loc[both, col], right.loc[both, col]).sum())
            for col in left.columns if col in right.columns}


def run_from_file(raw_path: Path, work: Path) -> Path:
    """04z against the stores, its ids read from `raw_path`; its output discarded."""
    captured, review = work / "captured", work / "review"
    captured.mkdir()
    review.mkdir()
    real_review, real_ids = etl.REVIEW, etl.fantrax_player_ids
    etl.REVIEW = review
    etl.fantrax_player_ids = lambda: real_ids(raw_path=raw_path)
    try:
        with etl.capturing(captured), contextlib.redirect_stdout(io.StringIO()):
            base.run_04z()
    finally:
        etl.REVIEW, etl.fantrax_player_ids = real_review, real_ids
    return captured


def report(captured: Path, out=print) -> int:
    entry = etl._table_entry(TABLE)
    live = etl.read_stored(TABLE)
    new = etl.read_captured(TABLE, captured)
    c = base.compare(live, new, entry)
    columns = column_differences(live, new, entry)
    same = not (c["only_live"] or c["only_new"] or c["differing"] or c["columns_apart"])
    out(f"{'identical' if same else 'DIFFERS':9s} {TABLE}: live {c['live_rows']} row(s), "
        f"would write {c['new_rows']}, keys only live {c['only_live']}, "
        f"only in the new output {c['only_new']}, keys with differing cells {c['differing']}, "
        f"columns apart {c['columns_apart']}")
    for col, n in columns.items():
        out(f"  column {col}: {n} key(s) differ")
    return 0 if same else 1


def main(argv=None) -> int:
    if not argv or len(argv) != 1:
        print("usage: compare_playerids_crosswalk.py <saved getPlayerIds response>")
        return 2
    raw_path = Path(argv[0])
    if not raw_path.is_file():
        print("stopped: the saved response is not a file")
        return 2
    try:
        print(f"storage: {base.loader.use_env_file()}")
        with pg.session_read_only(), tempfile.TemporaryDirectory(prefix="compare_playerids_") as work:
            return report(run_from_file(raw_path, Path(work)))
    except Exception as exc:
        print(f"stopped: {type(exc).__name__} (no detail printed: it may hold a value)")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

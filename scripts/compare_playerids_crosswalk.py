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
have any differing cell, how many differ in each column (resolved_date, which
04z sets to today, is left out), and, for the live crosswalk's ids the response
does not list, how many are on a current roster and how many hold a gsis_id.
No key value and no cell value. Exit 0 when the crosswalk is identical, 1
otherwise. position_raw is not taken from the response, so its column line
must read 0.
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


def without_resolved_date(frame: pd.DataFrame, entry: dict):
    """04z stamps resolved_date with today's date, so it differs on every key
    unless the store was written today; it is left out of the comparison."""
    kept = [c for c in entry["columns"] if c["name"] != "resolved_date"]
    return frame.drop(columns="resolved_date", errors="ignore"), {**entry, "columns": kept}


def missing_id_counts(live: pd.DataFrame, ids: pd.DataFrame, rostered: pd.Series) -> dict:
    """Of the live crosswalk's scorer_ids the saved response does not list: how
    many there are, how many are on a current roster, how many hold a gsis_id."""
    missing = live[~live["scorer_id"].isin(ids["scorer_id"])]
    return {"missing": len(missing),
            "rostered": int(missing["scorer_id"].isin(rostered).sum()),
            "with_gsis_id": int(missing["gsis_id"].notna().sum())}


def mapping_counts(live: pd.DataFrame, new: pd.DataFrame, rostered: pd.Series) -> dict:
    """Counts of how the mapping columns move, by scorer_id, with no key or value:
    keys only in the store, and keys held by both whose gsis_id differs."""
    left, right = live.set_index("scorer_id"), new.set_index("scorer_id")
    only_live = left.loc[left.index.difference(right.index)]
    both = left.index.intersection(right.index)
    old_g, new_g = left.loc[both, "gsis_id"], right.loc[both, "gsis_id"]
    old_m, new_m = left.loc[both, "match_method"], right.loc[both, "match_method"]
    set_to_empty = old_g.notna() & new_g.isna()
    empty_to_set = old_g.isna() & new_g.notna()
    one_to_another = (old_g.notna() & new_g.notna() & (old_g != new_g)).fillna(False).astype(bool)
    gsis_differs = set_to_empty | empty_to_set | one_to_another
    method_differs = (old_m.isna() != new_m.isna()) | (
        (old_m.notna() & new_m.notna() & (old_m != new_m)).fillna(False).astype(bool))
    return {
        "only_live": len(only_live),
        "only_live_rostered": int(only_live.index.isin(rostered).sum()),
        "only_live_with_gsis_id": int(only_live["gsis_id"].notna().sum()),
        "gsis_differs": int(gsis_differs.sum()),
        "gsis_differs_rostered": int((gsis_differs & both.isin(rostered)).sum()),
        "set_to_empty": int(set_to_empty.sum()),
        "empty_to_set": int(empty_to_set.sum()),
        "one_to_another": int(one_to_another.sum()),
        "gsis_and_method_differ": int((gsis_differs & method_differs).sum()),
    }


def run_from_file(raw_path: Path, work: Path):
    """04z against the stores, its ids read from `raw_path`; its output discarded.
    Returns the folder of captured tables and the ids frame it used."""
    captured, review = work / "captured", work / "review"
    captured.mkdir()
    review.mkdir()
    ids = etl.fantrax_player_ids(raw_path=raw_path)
    real_review, real_ids = etl.REVIEW, etl.fantrax_player_ids
    etl.REVIEW = review
    etl.fantrax_player_ids = lambda: ids
    try:
        with etl.capturing(captured), contextlib.redirect_stdout(io.StringIO()):
            base.run_04z()
    finally:
        etl.REVIEW, etl.fantrax_player_ids = real_review, real_ids
    return captured, ids


def report(captured: Path, ids: pd.DataFrame, out=print) -> int:
    entry = etl._table_entry(TABLE)
    full_live = etl.read_stored(TABLE)
    live, entry = without_resolved_date(full_live, entry)
    new, _ = without_resolved_date(etl.read_captured(TABLE, captured), entry)
    c = base.compare(live, new, entry)
    columns = column_differences(live, new, entry)
    same = not (c["only_live"] or c["only_new"] or c["differing"] or c["columns_apart"])
    out(f"{'identical' if same else 'DIFFERS':9s} {TABLE} (resolved_date not compared): "
        f"live {c['live_rows']} row(s), would write {c['new_rows']}, keys only live {c['only_live']}, "
        f"only in the new output {c['only_new']}, keys with differing cells {c['differing']}, "
        f"columns apart {c['columns_apart']}")
    for col, n in columns.items():
        out(f"  column {col}: {n} key(s) differ")
    rostered = etl.read_stored("fact_fantasy_teams")["scorer_id"]
    m = missing_id_counts(full_live, ids, rostered)
    out(f"ids the response does not list: {m['missing']}, on a current roster {m['rostered']}, "
        f"with a gsis_id {m['with_gsis_id']}")
    k = mapping_counts(live, new, rostered)
    out(f"keys only in the store: {k['only_live']}, on a current roster {k['only_live_rostered']}, "
        f"with a gsis_id {k['only_live_with_gsis_id']}")
    out(f"keys whose gsis_id differs: {k['gsis_differs']}, on a current roster {k['gsis_differs_rostered']}, "
        f"set to empty {k['set_to_empty']}, empty to set {k['empty_to_set']}, "
        f"one id to another {k['one_to_another']}")
    out(f"keys that differ on both gsis_id and match_method: {k['gsis_and_method_differ']}")
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
            captured, ids = run_from_file(raw_path, Path(work))
            return report(captured, ids)
    except Exception as exc:
        print(f"stopped: {type(exc).__name__} (no detail printed: it may hold a value)")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

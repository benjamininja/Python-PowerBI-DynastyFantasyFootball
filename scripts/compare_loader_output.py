"""Compare what 02d and 04z WOULD write with the live tables (#93, brief 6).

    compare_loader_output.py

The owner runs it after the one-time loader. It writes nothing:

  - the connection is read-only (every transaction is BEGIN READ ONLY), so any
    write raises;
  - 04z and then 02d run against the loaded tables in capture mode
    (`etl.capturing`): `write_table` goes to a temp folder outside data/, and
    their review files go to a temp folder too;
  - no run-log row and no review row is written (run_pipeline.py is not used);
  - the captured tables are compared with the tables as the store holds them,
    read in the same session.

It prints, for each of the four tables, the table name, both row counts, the
keys held on one side only and the keys whose cells differ. Counts only: no
cell value, no column name, no key value; the steps' own output is discarded.
Exit 0 when every table matches, 1 otherwise.
"""
import contextlib
import importlib
import io
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))
import etl_helpers as etl  # noqa: E402
import etl_storage_pg as pg  # noqa: E402
import load_draft_and_overrides as loader  # noqa: E402

TABLES = ("fact_roster_transactions", "dim_roster_asset", "fact_draft_pick",
          "dim_fantrax_crosswalk")
NOTEBOOK_04Z = REPO / "notebooks" / "04z_fantrax_crosswalk.ipynb"


def compare(live: pd.DataFrame, new: pd.DataFrame, entry: dict) -> dict:
    """Counts of how `new` (what the steps would write) differs from `live`."""
    key = etl.table_grain(entry)
    columns = [c for c in live.columns if c in new.columns]
    left = pg.prepared(live, entry).set_index(key)
    right = pg.prepared(new, entry).set_index(key)
    both = left.index.intersection(right.index)
    differing = pd.Series(False, index=both)
    for col in columns:
        if col not in key:
            differing |= pg._unequal(left.loc[both, col], right.loc[both, col])
    return {"live_rows": len(live), "new_rows": len(new),
            "only_live": len(left.index.difference(right.index)),
            "only_new": len(right.index.difference(left.index)),
            "differing": int(differing.sum()),
            "columns_apart": len(set(live.columns) ^ set(new.columns))}


def run_04z() -> None:
    """The notebook's code cells, in order, in one namespace."""
    notebook = json.loads(NOTEBOOK_04Z.read_text(encoding="utf-8"))
    scope = {"__name__": "__main__"}
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            source = cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
            exec(compile(source, "04z_fantrax_crosswalk", "exec"), scope)


def run_02d(review_dir: Path) -> None:
    ledger = importlib.import_module("02d_fact_roster_transactions")
    ledger.PICK_REVIEW_PATH = review_dir / "review_trade_log_picks.csv"
    ledger.PICK_OWNER_REVIEW_PATH = review_dir / "review_pick_ownership.csv"
    ledger.main()


def capture(work: Path) -> Path:
    """Run 04z, then 02d, capturing every table they write into `work`. Their
    printed output is discarded (it holds names)."""
    captured, review = work / "captured", work / "review"
    captured.mkdir()
    review.mkdir()
    real_review = etl.REVIEW
    etl.REVIEW = review
    try:
        with etl.capturing(captured), contextlib.redirect_stdout(io.StringIO()):
            run_04z()
            run_02d(review)
    finally:
        etl.REVIEW = real_review
    return captured


def report(captured: Path, tables=TABLES, out=print) -> int:
    bad = 0
    for name in tables:
        entry = etl._table_entry(name)
        path = etl.captured_path(name, captured)
        if not path.exists():
            out(f"MISSING   {name}: the steps wrote nothing")
            bad += 1
            continue
        try:
            live = etl.read_stored(name)
        except etl.TableNotFound:
            out(f"MISSING   {name}: the store holds nothing")
            bad += 1
            continue
        c = compare(live, etl.read_captured(name, captured), entry)
        same = not (c["only_live"] or c["only_new"] or c["differing"] or c["columns_apart"]
                    or c["live_rows"] != c["new_rows"])
        bad += not same
        out(f"{'identical' if same else 'DIFFERS':9s} {name}: live {c['live_rows']} row(s), "
            f"would write {c['new_rows']}, keys only live {c['only_live']}, "
            f"only in the new output {c['only_new']}, keys with differing cells {c['differing']}, "
            f"columns apart {c['columns_apart']}")
    out(f"tables {len(tables)}: differing {bad}")
    return 1 if bad else 0


def run(out=print) -> int:
    with pg.session_read_only(), tempfile.TemporaryDirectory(prefix="compare_loader_") as work:
        return report(capture(Path(work)), out=out)


def main(argv=None) -> int:
    if argv:
        print("usage: compare_loader_output.py (no arguments)")
        return 2
    try:
        print(f"storage: {loader.use_env_file()}")
        return run()
    except Exception as exc:
        print(f"stopped: {type(exc).__name__} (no detail printed: it may hold a value)")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""One-time rewrite of history onto the newest gsis_id (#300 Brief 4).

    rekey_gsis_history.py [--dry-run]

Each gsis_id of fact_dynasty_ranking_metrics, dim_dynasty_crosswalk,
fact_rookie_rankings and dim_rookie_prospect that is an old_gsis_id of
dim_gsis_link becomes its newest id (etl.current_gsis). On the Composite rows
of fact_dynasty_ranking_metrics, source_player_id and the id after
"Composite|" in source_uid move with it, as 04y builds them.

Only those id columns can change: the columns, their order, the row count and
the row order stay as read. Before any write, every table is checked: its
registry key must stay unique and non-null, no gsis_id may newly miss
dim_nfl_players, and no Composite row may newly disagree with itself. A failed
check writes nothing, in any table, and exits 1. A table is written through
etl.write_table only when an id changes, so a second run writes nothing.
--dry-run does the checks and writes nothing. Prints counts only, never an
id. No network, no scrape, no data/raw read.

The remap and its checks live in etl_helpers (rekey_frame, rekey_check, #639);
the pipeline calls etl.rekey_gsis_tables for every published table with a
gsis_id column. This script keeps its four tables and its all-or-nothing write.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

for _p in (Path(__file__).resolve().parent.parent / "notebooks", Path.cwd() / "notebooks", Path.cwd()):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p))
        break
import etl_helpers as etl

TABLES = ("fact_dynasty_ranking_metrics", "dim_dynasty_crosswalk",
          "fact_rookie_rankings", "dim_rookie_prospect")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="check and report, write nothing")
    dry_run = parser.parse_args(argv).dry_run

    links = (etl.read_table(etl.GSIS_LINK_TABLE) if etl.table_exists(etl.GSIS_LINK_TABLE)
             else pd.DataFrame(columns=etl.GSIS_LINK_COLUMNS))
    valid = set(etl.read_table("dim_nfl_players")["gsis_id"].dropna())
    print(f"dim_gsis_link: {len(links)} link(s)")
    plan = {}
    try:
        for name in TABLES:
            before = etl.read_table(name)
            after = etl.rekey_frame(name, before, links)
            plan[name] = (after, etl.rekey_check(name, before, after, valid, links), len(before))
    except etl.RekeyRefused as exc:
        print(f"REFUSED, nothing written: {exc}")
        return 1

    for name, (after, stats, rows) in plan.items():
        moved = ", ".join(f"{c} {n}" for c, n in stats["changed"].items())
        print(f"{name}: rows {rows}, changed {moved}; gsis_id not in dim_nfl_players "
              f"before {stats['orphans'][0]}, after {stats['orphans'][1]}; "
              f"rows still on an old id {stats['still_old']}")
    for name, (after, stats, _) in plan.items():
        if not any(stats["changed"].values()):
            print(f"{name}: unchanged, not written")
        elif dry_run:
            print(f"{name}: would be written (dry run)")
        else:
            etl.write_table(name, after)
            print(f"{name}: written")
    return 0


if __name__ == "__main__":
    sys.exit(main())

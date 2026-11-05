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
COMPOSITE_TABLE = "fact_dynasty_ranking_metrics"
COMPOSITE = "Composite"
COMPOSITE_PREFIX = COMPOSITE + "|"


class Refused(Exception):
    pass


def rekey_frame(name: str, df: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["gsis_id"] = etl.current_gsis(out["gsis_id"], links)
    if name == COMPOSITE_TABLE:
        comp = out["source_name"] == COMPOSITE
        out.loc[comp, "source_player_id"] = etl.current_gsis(out.loc[comp, "source_player_id"], links)
        uid = out.loc[comp, "source_uid"]
        tagged = uid.str.startswith(COMPOSITE_PREFIX)
        moved = COMPOSITE_PREFIX + etl.current_gsis(uid.str[len(COMPOSITE_PREFIX):], links)
        out.loc[comp, "source_uid"] = uid.where(~tagged, moved)
    return out


def id_columns(name: str) -> list[str]:
    cols = ["gsis_id"]
    return cols + ["source_player_id", "source_uid"] if name == COMPOSITE_TABLE else cols


def changed_cells(before: pd.DataFrame, after: pd.DataFrame, col: str) -> int:
    same = (before[col] == after[col]) | (before[col].isna() & after[col].isna())
    return int((~same).sum())


def orphans(df: pd.DataFrame, valid: set) -> int:
    ids = df["gsis_id"].dropna()
    return int((~ids.isin(valid)).sum())


def split_rows(df: pd.DataFrame) -> int:
    comp = df[df["source_name"] == COMPOSITE]
    agree = (comp["source_player_id"] == comp["gsis_id"]) & \
            (comp["source_uid"] == COMPOSITE_PREFIX + comp["gsis_id"].astype(str))
    return int((~agree).sum())


def check(name: str, before: pd.DataFrame, after: pd.DataFrame, valid: set, links: pd.DataFrame) -> dict:
    assert list(after.columns) == list(before.columns) and len(after) == len(before)
    ids = id_columns(name)
    rest = [c for c in before.columns if c not in ids]
    if not after[rest].equals(before[rest]):
        raise Refused(f"{name}: a column other than the id columns changed")
    key = etl.table_grain(etl._table_entry(name))
    nulls = int(after[key].isna().any(axis=1).sum())
    dupes = int(after.duplicated(subset=key, keep=False).sum())
    if nulls or dupes:
        raise Refused(f"{name}: key {tuple(key)} would break -- {nulls} row(s) with a null key, "
                      f"{dupes} row(s) sharing a key")
    orphans_before, orphans_after = orphans(before, valid), orphans(after, valid)
    if orphans_after > orphans_before:
        raise Refused(f"{name}: gsis_id missing from dim_nfl_players would rise "
                      f"{orphans_before} -> {orphans_after}")
    if name == COMPOSITE_TABLE:
        split_before, split_after = split_rows(before), split_rows(after)
        if split_after > split_before:
            raise Refused(f"{name}: Composite rows whose three id columns disagree would rise "
                          f"{split_before} -> {split_after}")
    return {"orphans": (orphans_before, orphans_after),
            "still_old": int(after["gsis_id"].isin(set(links["old_gsis_id"])).sum()),
            "changed": {c: changed_cells(before, after, c) for c in ids}}


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
            after = rekey_frame(name, before, links)
            plan[name] = (after, check(name, before, after, valid, links), len(before))
    except Refused as exc:
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

"""Recompute fact_rookie_rankings.gsis_id from the two dims (#301).

    recompute_rookie_gsis.py

Each row's gsis_id becomes dim_nfl_players.gsis_id for the pfr_id that
dim_rookie_prospect holds for the row's player_key, or null when either link
is missing. Only that column can change: the columns, their order, the row
count and the row order stay as read. The table is written through
etl.write_table, and only when at least one gsis_id changes. Prints counts
only, never an id. No network, no scrape, no data/raw read.
"""
import sys
from pathlib import Path

import pandas as pd

for _p in (Path(__file__).resolve().parent.parent / "notebooks", Path.cwd() / "notebooks", Path.cwd()):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p))
        break
import etl_helpers as etl

TABLE = "fact_rookie_rankings"


def recompute(fact: pd.DataFrame, prospect: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    pairs = nfl[["pfr_id", "gsis_id"]].dropna()
    pfr_to_gsis = dict(zip(pairs["pfr_id"], pairs["gsis_id"]))
    key_to_pfr = dict(zip(prospect["player_key"], prospect["pfr_id"]))
    dtype = object if pd.api.types.is_numeric_dtype(fact["gsis_id"]) else fact["gsis_id"].dtype
    out = fact.copy()
    out["gsis_id"] = out["player_key"].map(key_to_pfr).map(pfr_to_gsis).astype(dtype)
    return out


def changed_rows(before: pd.DataFrame, after: pd.DataFrame) -> int:
    same = (before["gsis_id"] == after["gsis_id"]) | (before["gsis_id"].isna() & after["gsis_id"].isna())
    return int((~same).sum())


def main() -> int:
    fact = etl.read_table(TABLE)
    fixed = recompute(fact, etl.read_table("dim_rookie_prospect"), etl.read_table("dim_nfl_players"))
    assert list(fixed.columns) == list(fact.columns) and len(fixed) == len(fact)
    others = [c for c in fact.columns if c != "gsis_id"]
    assert fixed[others].equals(fact[others])
    changed = changed_rows(fact, fixed)
    print(f"{TABLE}: rows {len(fact)}, gsis_id changed {changed}, "
          f"gsis_id null before {int(fact['gsis_id'].isna().sum())}, after {int(fixed['gsis_id'].isna().sum())}")
    if changed:
        etl.write_table(TABLE, fixed)
        print(f"{TABLE}: written")
    else:
        print(f"{TABLE}: unchanged, not written")
    return 0


if __name__ == "__main__":
    sys.exit(main())

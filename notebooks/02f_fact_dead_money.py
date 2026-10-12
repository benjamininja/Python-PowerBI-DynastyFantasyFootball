# %% [markdown]
# # 02f_fact_dead_money  (drops in the ledger -> Dead Money by season)
#
# **Purpose:** derive `fact_dead_money` from the drop Roster Moves of
# `fact_roster_transactions` (ADR-0016 decision 5; built in #96). A drop of a
# guaranteed contract leaves the rest of that contract's guaranteed years
# owed, each charged to the season it falls in.
#
# **Schedule:** read from `dim_contract`, nothing hard-coded: the rows of the
# dropped contract's `contract_type` with `contract_year` at or after its own
# and `guaranteed` true, each at its `cap_hit_pct` of the salary at the drop.
# A `1st` drop charges .50 this season and .40 the next; `2nd` .40; `Tag`
# .50; `3rd`, `X`, `FA`, `Minor` nothing. Year k lands in the drop's season
# plus (k - the year at the drop), by `dim_season`.
#
# **Not charged:** a drop that ends no stint (`contract_source = no_stint`,
# #96 decision 2: no draft pick, claim or trade into that team before it; its
# row carries terms that are not that team's, so it is skipped by the source
# and never by its terms), and a drop with no salary. Re-claiming the player
# does not cancel the charge.
#
# **Output:** `fact_dead_money.parquet`, grain `(transaction_id, scorer_id,
# team_key, season_id)`, rewritten whole on every run. `season_id` is the
# season charged; `contract_id` the contract at the drop; `charge_contract_id`
# the schedule row that prices this season.
#
# **Run:**  python notebooks/02f_fact_dead_money.py   (after 02d)

# %%
import sys
from pathlib import Path

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
from etl_helpers import DATA, read_table, write_table

OUT_PATH = DATA / "fact_dead_money.parquet"

DROP = "drop"
NO_STINT = "no_stint"
KEY = ["transaction_id", "scorer_id", "team_key", "season_id"]
COLUMNS = ["transaction_id", "scorer_id", "team_key", "season_id", "drop_date",
           "drop_period", "gsis_id", "contract_id", "contract_value",
           "charge_contract_id", "cap_hit_pct", "dead_money", "contract_source"]
DTYPES = {"transaction_id": "str", "scorer_id": "str", "team_key": "str",
          "season_id": "str", "drop_date": "datetime64[us]", "drop_period": "Int64",
          "gsis_id": "str", "contract_id": "str", "contract_value": "float64",
          "charge_contract_id": "str", "cap_hit_pct": "float64",
          "dead_money": "float64", "contract_source": "str"}


# %%
def schedule(contracts: pd.DataFrame) -> dict[str, list[tuple[int, str, float]]]:
    """contract_id -> [(seasons after the drop, charging contract_id, pct)].

    The guaranteed rows of the same `contract_type` from the dropped
    contract's year on. A contract with no year (`Minor`) or with no
    guaranteed year left maps to an empty list.
    """
    out = {}
    for c in contracts.itertuples():
        charges = []
        if pd.notna(c.contract_year):
            later = contracts[(contracts["contract_type"] == c.contract_type)
                              & (contracts["contract_year"] >= c.contract_year)
                              & contracts["guaranteed"].astype(bool)]
            charges = [(int(r.contract_year) - int(c.contract_year), r.contract_id,
                        float(r.cap_hit_pct))
                       for r in later.sort_values("contract_year").itertuples()]
        out[c.contract_id] = charges
    return out


def season_after(seasons: pd.DataFrame, season_id: str, offset: int) -> str:
    """The season `offset` seasons after `season_id`. Raises when dim_season
    lacks either one."""
    order = seasons.sort_values("season_start_year")["season_id"].tolist()
    if season_id not in order:
        raise ValueError(f"season {season_id} is not in dim_season")
    i = order.index(season_id) + offset
    if i >= len(order):
        raise ValueError(f"dim_season has no season {offset} after {season_id} "
                         "-- run 01f to extend it")
    return order[i]


def chargeable(ledger: pd.DataFrame) -> pd.DataFrame:
    """The drops that can owe Dead Money: every drop that ends a stint and
    carries a salary."""
    drops = ledger[ledger["event_type"] == DROP]
    return drops[(drops["contract_source"] != NO_STINT) & drops["contract_value"].notna()]


def build_dead_money(ledger: pd.DataFrame, contracts: pd.DataFrame,
                     seasons: pd.DataFrame) -> pd.DataFrame:
    """fact_dead_money rows from the ledger's drops."""
    sched = schedule(contracts)
    rows = []
    for d in chargeable(ledger).itertuples():
        if d.contract_id not in sched:
            raise ValueError(f"drop {d.transaction_id}: contract_id {d.contract_id!r} "
                             "is not in dim_contract")
        for offset, charge_id, pct in sched[d.contract_id]:
            rows.append({
                "transaction_id": d.transaction_id,
                "scorer_id": d.scorer_id,
                "team_key": d.team_key,
                "season_id": season_after(seasons, d.season_id, offset),
                "drop_date": d.event_date,
                "drop_period": d.period,
                "gsis_id": d.gsis_id,
                "contract_id": d.contract_id,
                "contract_value": d.contract_value,
                "charge_contract_id": charge_id,
                "cap_hit_pct": pct,
                "dead_money": round(pct * d.contract_value, 2),
                "contract_source": d.contract_source,
            })
    df = pd.DataFrame(rows, columns=COLUMNS).astype(DTYPES)
    dupes = int(df.duplicated(KEY).sum())
    if dupes:
        raise ValueError(f"{dupes} fact_dead_money rows repeat the key {KEY}")
    return (df.sort_values(["season_id", "team_key", "drop_date", "transaction_id", "scorer_id"])
            .reset_index(drop=True))


# %%
def main() -> int:
    ledger = read_table("fact_roster_transactions")
    dead = build_dead_money(ledger, read_table("dim_contract"), read_table("dim_season"))
    write_table("fact_dead_money", dead)

    drops = ledger[ledger["event_type"] == DROP]
    print(f"[ok] fact_dead_money: {len(dead)} rows from "
          f"{dead[['transaction_id', 'scorer_id', 'team_key']].drop_duplicates().shape[0]} "
          f"of {len(drops)} drops ({int((drops['contract_source'] == NO_STINT).sum())} "
          f"end no stint) -> {OUT_PATH.name}")
    for season_id, rows in dead.groupby("season_id"):
        by_team = rows.groupby("team_key")["dead_money"].sum()
        print(f"  {season_id}: {by_team.sum():,.0f} on {len(by_team)} team(s): "
              + ", ".join(f"{t} {v:,.0f}" for t, v in by_team.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

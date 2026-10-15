"""The league's cap rules, computed once, in the ETL (ADR-0016 decision 8, #97).

Pure functions on DataFrames: no I/O. `02e` stamps each roster row's charge
with them, the cap table's writer sums them, and the checks in `etl_checks`
replay the ledger with them. The bot and trade-bud import none of this; they
read the published tables.
"""
from __future__ import annotations

import pandas as pd

# Roster Slots (fact_roster_state vocabulary) whose salary is not counted
# against this season's cap, whatever the contract (owner's ruling
# 2026-10-12, #97; reverses ADR-0011's "IR charges full salary"). Dropping an
# IR player still makes Dead Money: that is fact_dead_money's, not a slot rule.
EXEMPT_SLOTS = frozenset({"Minors", "IR"})

# The contract that carries into next season with no term on dim_contract
# (ADR-0019: Minor is the stage before 1st; its years are null).
MINOR = "Minor"

INBOUND = frozenset({"startup_draft", "claim", "trade"})
OUTBOUND = frozenset({"drop", "trade_away"})


def stamp_cap(slots: pd.Series, contract_value: pd.Series) -> pd.DataFrame:
    """Per roster row: `cap_exempt` (its slot is exempt) and `cap_hit` (0 when
    exempt, else the full contract value). A null slot is charged."""
    exempt = slots.isin(EXEMPT_SLOTS).fillna(False).astype(bool)
    hit = contract_value.astype("float64").where(~exempt, 0.0)
    return pd.DataFrame({"cap_exempt": exempt, "cap_hit": hit}, index=slots.index)


def carries_next_season(contract_ids: pd.Series, contracts: pd.DataFrame) -> pd.Series:
    """Does the contract have a following year? `Minor` does; a termed
    contract does while contract_year < total_years; FA, Tag, X and a last
    year do not. An unknown contract does not."""
    terms = contracts.set_index("contract_id")
    year = contract_ids.map(terms["contract_year"])
    total = contract_ids.map(terms["total_years"])
    termed = (year.notna() & total.notna()
              & (pd.to_numeric(year) < pd.to_numeric(total))).fillna(False).astype(bool)
    return (contract_ids.eq(MINOR).fillna(False) | termed).astype(bool)


def dead_money_by_team(dead: pd.DataFrame, season_id: str) -> pd.Series:
    """One season's Dead Money per team: only that season's rows are summed."""
    rows = dead[dead["season_id"] == season_id]
    return rows.groupby("team_key")["dead_money"].sum().rename("dead_money")


def open_stints(ledger: pd.DataFrame) -> pd.DataFrame:
    """Replay the ledger: for each (team_key, scorer_id) whose newest move is
    inbound, that move's ledger row (it opened the stint). A copy whose newest
    move is a drop or a trade-away has no open stint on that team."""
    moves = ledger[ledger["event_type"].isin(INBOUND | OUTBOUND)]
    last = (moves.sort_values("event_seq", kind="stable")
                 .drop_duplicates(["team_key", "scorer_id"], keep="last"))
    return last[last["event_type"].isin(INBOUND)].reset_index(drop=True)


def membership_differences(roster: pd.DataFrame, stints: pd.DataFrame) -> tuple[list, list]:
    """(roster rows with no open stint, open stints with no roster row), each
    a sorted list of (team_key, scorer_id)."""
    on_roster = set(zip(roster["team_key"], roster["scorer_id"]))
    on_ledger = set(zip(stints["team_key"], stints["scorer_id"]))
    return sorted(on_roster - on_ledger), sorted(on_ledger - on_roster)

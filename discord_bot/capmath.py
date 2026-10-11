"""Live salary-cap math shared by cap.py and roster.py.

dim_fantasy_teams.parquet no longer carries a pre-computed roster/cap rollup
(active_roster_salary, remaining_cap_current_yr, remaining_cap_next_yr) --
that was an ETL-frozen snapshot written once per 02e run, which drifted from
Fact_FantasyTeams whenever the Power BI report applied a filter. This
computes the same formula live from the ledger-derived fact, mirroring the
DAX measures in _Measures.tmdl ('Active Roster Salary', 'Remaining Salary
Cap') so there's exactly one definition of "remaining cap", not three.

fact_fantasy_teams.parquet also no longer stores `cap_hit` (removed
2026-07-11, same reasoning). A KEPT player's cap charge is the full
ContractValue -- CapHitPct on dim_contract is a DEAD-MONEY-ONLY number (it
prices what's still owed if you CUT the player); it has no bearing on what a
kept player costs. That matches the DAX 'Active Roster Salary' comment in
_Measures.tmdl verbatim (the 2026-07-13 cap-ledger audit caught this module
still multiplying by CapHitPct -- a 2x understatement vs the report).
"""

from __future__ import annotations

import pandas as pd

from config import Config
from github_fetch import fetch_parquet

_TEAMS_PATH = "data/dim_fantasy_teams.parquet"
_ROSTER_PATH = "data/fact_fantasy_teams.parquet"
_DEAD_MONEY_PATH = "data/fact_dead_money.parquet"


def roster_with_cap_hit(cfg: Config) -> pd.DataFrame:
    """fact_fantasy_teams with a computed cap_hit column -- mirrors the DAX
    'Active Roster Salary' measure: a kept player charges the FULL
    ContractValue (CapHitPct is dead-money-only, never applied here). Use this
    instead of fetch_parquet(fact_fantasy_teams) directly whenever per-player
    cap_hit is needed.

    Minors-squad placement is CAP-EXEMPT (roster_status == "Minors", stamped by
    02e from the newest Scoring Period in fact_roster_state): those rows keep
    their contract_value but get cap_hit 0 and cap_exempt True. Placement is
    the ONLY exemption lever -- a Minor-CONTRACT player kept on the active
    roster is charged in full. A null/absent roster_status charges normally —
    the safe default."""
    roster = fetch_parquet(_ROSTER_PATH, cfg)
    if roster.empty:
        return roster
    roster = roster.copy()
    roster["cap_hit"] = roster["contract_value"]
    if "roster_status" in roster.columns:
        roster["cap_exempt"] = roster["roster_status"].eq("Minors").fillna(False)
    else:  # pre-2026-07-13 fact without the column
        roster["cap_exempt"] = False
    roster.loc[roster["cap_exempt"], "cap_hit"] = 0.0
    return roster


def _next_season(season_id: str) -> str:
    """'2026-2027' -> '2027-2028' (dim_season's season_id format)."""
    start = int(season_id.split("-")[0]) + 1
    return f"{start}-{start + 1}"


def teams_with_cap(cfg: Config) -> pd.DataFrame:
    """dim_fantasy_teams joined with live cap figures computed from
    fact_fantasy_teams and fact_dead_money. Dead Money is its own fact
    (ADR-0016 decision 5; 02f derives it from the ledger's drops, one row per
    season charged): this season's rows per team are `dead_money` and come off
    current cap room; next season's rows come off remaining_cap_next_yr. The
    season is the roster's own `season`. remaining_cap_next_yr has no year-2
    contract tracking yet, so it's original_cap - active_roster_salary - next
    season's Dead Money."""
    teams = fetch_parquet(_TEAMS_PATH, cfg)
    if teams.empty:
        return teams

    roster = roster_with_cap_hit(cfg)
    if roster.empty:
        roll = pd.DataFrame(columns=["team_key", "active_roster_salary",
                                     "dead_money", "dead_money_next_yr"])
    else:
        seasons = roster["season"].dropna()
        season = seasons.max() if len(seasons) else None   # no season: nothing to charge
        dead = fetch_parquet(_DEAD_MONEY_PATH, cfg)
        by_season = {
            col: dead[dead["season_id"] == s].groupby("team_key")["dead_money"].sum().rename(col)
            for col, s in (("dead_money", season),
                           ("dead_money_next_yr", _next_season(season) if season else None))
        }
        roll = (
            roster.groupby("team_key")
            .agg(active_roster_salary=("cap_hit", "sum"))
            .join(by_season["dead_money"], how="outer")
            .join(by_season["dead_money_next_yr"], how="outer")
            .rename_axis("team_key")
            .reset_index()
        )

    t = teams.merge(roll, on="team_key", how="left")
    for col in ("active_roster_salary", "dead_money", "dead_money_next_yr"):
        t[col] = t[col].fillna(0)
    t["remaining_cap_current_yr"] = t["original_cap"] - (
        t["active_roster_salary"] + t["dead_money"] + t["reinvestment_cap"]
    )
    t["remaining_cap_next_yr"] = t["original_cap"] - (
        t["active_roster_salary"] + t["dead_money_next_yr"]
    )
    return t

"""Readers for the published cap tables, shared by cap.py and roster.py.

No cap figure is computed here (ADR-0016's #97 amendment, decisions 1 and 8).
The ETL's cap module (notebooks/etl_cap.py) computes every figure once, and
the pipeline publishes it: `cap_hit` and `cap_exempt` on fact_fantasy_teams,
and one row per team per season on fact_team_cap, where is_current_season
marks this season. These two functions read those tables and join them to the
team dimension, under the column names the commands and trade-bud already use.
Which contracts carry into next season, which slots are exempt and what Dead
Money is charged are the ETL's rules, not this module's.
"""

from __future__ import annotations

import pandas as pd

from config import Config
from github_fetch import fetch_parquet

_TEAMS_PATH = "data/dim_fantasy_teams.parquet"
_ROSTER_PATH = "data/fact_fantasy_teams.parquet"
_CAP_PATH = "data/fact_team_cap.parquet"

_THIS_SEASON = {
    "charged_salary": "active_roster_salary",
    "cap_room": "remaining_cap_current_yr",
    "dead_money": "dead_money",
    "ir_salary": "ir_salary",
    "minors_salary": "minors_salary",
}
_NEXT_SEASON = {
    "cap_room": "remaining_cap_next_yr",
    "dead_money": "dead_money_next_yr",
}


def roster_with_cap_hit(cfg: Config) -> pd.DataFrame:
    """fact_fantasy_teams as published. `cap_hit` and `cap_exempt` are stored
    columns, stamped by 02e with the ETL's slot rule; nothing is recomputed."""
    return fetch_parquet(_ROSTER_PATH, cfg)


def _season_rows(cap: pd.DataFrame, current: bool, columns: dict[str, str]) -> pd.DataFrame:
    rows = cap[cap["is_current_season"] == current]
    return rows[["team_key", *columns]].rename(columns=columns)


def teams_with_cap(cfg: Config) -> pd.DataFrame:
    """dim_fantasy_teams with its two fact_team_cap rows per team beside it.

    The current-season row gives `active_roster_salary` (the table's
    charged_salary), `remaining_cap_current_yr` (cap_room), `dead_money`,
    `ir_salary` and `minors_salary`. The other row gives
    `remaining_cap_next_yr` (cap_room) and `dead_money_next_yr`. Each merge is
    one-to-one and fills nothing: the table's Gate guarantees every team has
    both rows. The dimension's own `original_cap` and `reinvestment_cap`
    stay."""
    teams = fetch_parquet(_TEAMS_PATH, cfg)
    if teams.empty:
        return teams
    cap = fetch_parquet(_CAP_PATH, cfg)
    return (
        teams
        .merge(_season_rows(cap, True, _THIS_SEASON), on="team_key",
               how="left", validate="one_to_one")
        .merge(_season_rows(cap, False, _NEXT_SEASON), on="team_key",
               how="left", validate="one_to_one")
    )

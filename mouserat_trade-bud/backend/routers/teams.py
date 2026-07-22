from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import data_access as da
import profiles

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("")
def list_teams() -> list[dict]:
    teams = da.read_parquet("dim_fantasy_teams")
    cols = ["team_key", "team_name", "team_abbr", "conference", "division"]
    return teams[cols].to_dict(orient="records")


def _require_team(team_key: str) -> None:
    teams = da.read_parquet("dim_fantasy_teams")
    if team_key not in set(teams["team_key"]):
        raise HTTPException(status_code=404, detail=f"Unknown team_key {team_key!r}")


@router.get("/{team_key}/profile")
def team_profile(team_key: str, mode: str = Query("my", pattern="^(my|counterparty)$")) -> dict:
    _require_team(team_key)
    return profiles.build_profile(team_key, mode)

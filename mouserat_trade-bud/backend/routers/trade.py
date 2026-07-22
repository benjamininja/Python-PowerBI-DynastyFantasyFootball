from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import data_access as da
import pareto

router = APIRouter(prefix="/trade", tags=["trade"])


class TradeAsset(BaseModel):
    asset_type: str  # "player" | "pick"
    asset_id: str


class TradeRequest(BaseModel):
    my_team: str
    counterparty_team: str
    give: list[TradeAsset]
    receive: list[TradeAsset]


def _asset_owners() -> tuple[set[tuple[str, str]], dict[str, str]]:
    """{(gsis_id, team_key)} roster memberships, pick_ref -> current_owner.

    This is a duplicate-player league (confirmed in
    .claude/memory/data-model.md's fact_roster_placement grain note): the
    same gsis_id can be legitimately rostered by one team in each
    conference at once, so ownership is a membership check, not a
    single-valued lookup.
    """
    roster = da.read_parquet("fact_fantasy_teams")
    player_membership = set(zip(roster["gsis_id"], roster["team_key"]))
    inv = da.draft_pick_inventory()
    pick_owner = dict(zip(inv["pick_ref"], inv["current_owner"]))
    return player_membership, pick_owner


def _owned_by(
    asset: TradeAsset, team_key: str, player_membership: set, pick_owner: dict
) -> bool:
    if asset.asset_type == "player":
        return (asset.asset_id, team_key) in player_membership
    return pick_owner.get(asset.asset_id) == team_key


@router.post("/evaluate")
def evaluate_trade(req: TradeRequest) -> dict:
    teams = da.read_parquet("dim_fantasy_teams")
    team_conf = dict(zip(teams["team_key"], teams["conference"]))
    if req.my_team not in team_conf:
        raise HTTPException(status_code=400, detail=f"Unknown team_key {req.my_team!r}")
    if req.counterparty_team not in team_conf:
        raise HTTPException(
            status_code=400, detail=f"Unknown team_key {req.counterparty_team!r}"
        )
    if team_conf[req.my_team] != team_conf[req.counterparty_team]:
        raise HTTPException(
            status_code=400,
            detail="Teams are not in the same conference -- cross-conference trades are not allowed",
        )

    player_membership, pick_owner = _asset_owners()
    for asset in req.give:
        if not _owned_by(asset, req.my_team, player_membership, pick_owner):
            raise HTTPException(
                status_code=400,
                detail=f"Give asset {asset.asset_id!r} is not owned by {req.my_team!r}",
            )
    for asset in req.receive:
        if not _owned_by(asset, req.counterparty_team, player_membership, pick_owner):
            raise HTTPException(
                status_code=400,
                detail=f"Receive asset {asset.asset_id!r} is not owned by {req.counterparty_team!r}",
            )

    return pareto.evaluate_trade(
        give=[a.model_dump() for a in req.give],
        receive=[a.model_dump() for a in req.receive],
    )

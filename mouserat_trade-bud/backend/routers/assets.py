"""Player + pick roster listing for the give/receive selector (decision #9:
draft picks are first-class tradeable assets alongside players)."""

from __future__ import annotations

from fastapi import APIRouter

import data_access as da
import pareto
import pick_value as pv

router = APIRouter(prefix="/teams", tags=["assets"])

_FORMAT_BY_POSITION_GROUP = {
    "QB": "SF", "RB": "SF", "WR": "SF", "TE": "SF",
    "DL": "IDP", "LB": "IDP", "DB": "IDP",
}


@router.get("/{team_key}/assets")
def team_assets(team_key: str) -> dict:
    roster = da.read_parquet("fact_fantasy_teams")
    roster = roster[roster["team_key"] == team_key]
    players_dim = da.read_parquet("dim_nfl_players")[
        ["gsis_id", "display_name", "position", "position_group", "team_abbr"]
    ]
    roster = roster.merge(players_dim, on="gsis_id", how="left")

    players_out = []
    for _, r in roster.iterrows():
        players_out.append(
            {
                "asset_type": "player",
                "asset_id": r["gsis_id"],
                "name": r.get("display_name"),
                "position": r.get("position_group"),
                "nfl_team": r.get("team_abbr"),
                "contract_value": r.get("contract_value"),
                "roster_status": r.get("roster_status"),
                "value": pareto.asset_value("player", r["gsis_id"]),
            }
        )

    inv = da.draft_pick_inventory()
    tradeable_picks = inv[
        (inv["current_owner"] == team_key) & ((~inv["is_made"]) | inv["is_synthetic"])
    ]
    picks_out = []
    for _, r in tradeable_picks.iterrows():
        picks_out.append(
            {
                "asset_type": "pick",
                "asset_id": r["pick_ref"],
                "draft_season": r["draft_season"],
                "round": int(r["round"]),
                "is_synthetic": bool(r["is_synthetic"]),
                "value": pv.value_for_pick_row(r, inv),
            }
        )

    return {"players": players_out, "picks": picks_out}

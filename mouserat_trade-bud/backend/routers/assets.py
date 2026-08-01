"""Player + pick roster listing for the give/receive selector (decision #9:
draft picks are first-class tradeable assets alongside players)."""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter

import data_access as da
import pick_value as pv

router = APIRouter(prefix="/teams", tags=["assets"])


def _values_by_stance() -> dict[str, dict[str, float]]:
    """{stance: {gsis_id: value}} for all three stances.

    Built once per request rather than calling pareto.asset_value per player:
    that helper re-derives the whole league's valuation for a single lookup,
    which is fine for a trade of a few assets but quadratic over a 45-man
    roster x 3 stances.
    """
    return {
        stance: dict(zip(v["gsis_id"], v["value"]))
        for stance in da.STANCES
        for v in [da.player_values(stance)]
    }


def _position_sort_order() -> pd.DataFrame:
    """position_group -> (side_of_ball_sort_order, position_sort_order), per
    dim_position -- the data-model's own display order, not alphabetical.
    Includes the "Pick" group (side_of_ball_sort_order=3,
    position_sort_order=999), so draft-pick assets sort last, after every
    real position, same as the Positional Overview panels."""
    dp = da.read_parquet("dim_position")[
        ["position_group", "side_of_ball_sort_order", "position_sort_order"]
    ]
    return dp.drop_duplicates("position_group").set_index("position_group")


@router.get("/{team_key}/assets")
def team_assets(team_key: str) -> dict:
    roster = da.roster_with_cap_hit()
    roster = roster[roster["team_key"] == team_key]
    players_dim = da.read_parquet("dim_nfl_players")[
        ["gsis_id", "display_name", "position", "position_group", "team_abbr", "birth_date"]
    ]
    roster = roster.merge(players_dim, on="gsis_id", how="left")
    crosswalk = da.read_parquet("dim_fantrax_crosswalk")[["gsis_id", "position_raw"]].drop_duplicates("gsis_id")
    roster = roster.merge(crosswalk, on="gsis_id", how="left")
    sort_order = _position_sort_order()
    values = _values_by_stance()

    players_out = []
    for _, r in roster.iterrows():
        pos_sort = sort_order.reindex([r.get("position_group")]).iloc[0]
        # Dual-eligible players (dim_fantrax_crosswalk.position_raw is
        # comma-separated, e.g. "DL,LB") display all eligible positions here;
        # side_of_ball_sort_order/position_sort_order still key off the single
        # canonical position_group, so sort order is unaffected.
        position_raw = r.get("position_raw")
        display_position = (
            position_raw.replace(",", "/") if pd.notna(position_raw) and position_raw else r.get("position_group")
        )
        players_out.append(
            {
                "asset_type": "player",
                "asset_id": r["gsis_id"],
                "name": r.get("display_name"),
                "position": display_position,
                "side_of_ball_sort_order": int(pos_sort["side_of_ball_sort_order"]) if pd.notna(pos_sort["side_of_ball_sort_order"]) else 999,
                "position_sort_order": int(pos_sort["position_sort_order"]) if pd.notna(pos_sort["position_sort_order"]) else 999,
                "nfl_team": r.get("team_abbr"),
                "contract_value": r.get("contract_value"),
                "cap_hit": float(r["cap_hit"]) if pd.notna(r.get("cap_hit")) else 0.0,
                "cap_exempt": bool(r.get("cap_exempt")),
                "roster_status": r.get("roster_status"),
                "age": da.player_age(r["gsis_id"], players=players_dim),
                # One value per stance -- the static export ships all three so
                # the stance chips switch instantly with no refetch.
                "values": {
                    s: float(values[s].get(r["gsis_id"], 0.0)) for s in da.STANCES
                },
            }
        )

    inv = da.draft_pick_inventory()
    tradeable_picks = inv[
        (inv["current_owner"] == team_key) & ((~inv["is_made"]) | (~inv["is_slotted"]))
    ]
    pick_sort = sort_order.reindex(["Pick"]).iloc[0]
    picks_out = []
    for _, r in tradeable_picks.iterrows():
        pick_vals = {s: pv.value_for_pick_row(r, inv, s) for s in da.STANCES}
        picks_out.append(
            {
                "asset_type": "pick",
                "asset_id": r["pick_ref"],
                "draft_season": r["draft_season"],
                "round": int(r["round"]),
                "is_slotted": bool(r["is_slotted"]),
                "side_of_ball_sort_order": int(pick_sort["side_of_ball_sort_order"]),
                "position_sort_order": int(pick_sort["position_sort_order"]),
                "cap_hit": 0.0,
                "cap_exempt": True,
                # Same shape as a player asset so the frontend has one value
                # accessor. A pick has no board to choose between, so the
                # stance enters as a scalar (pick_value._STANCE_SCALAR).
                "values": pick_vals,
            }
        )

    return {"players": players_out, "picks": picks_out}

"""Pareto-asymmetry trade diagnostic (decision #11): compares total value
given vs. received per side, on the shared 0-100 scale used for both players
(data_access.player_values) and picks (pick_value.resolve_pick_value) so the
two asset types are directly comparable in a mixed give/receive package
(decision #9).

Every value is stance-scoped. There is no format routing here any more: player
value is `position_ceiling x within-position percentile`, which is already one
currency across all seven position groups, so offense and IDP no longer need
(and must not get) separate pools summed as if they were commensurable.
"""

from __future__ import annotations

import data_access as da
import pick_value as pv


def _player_value(gsis_id: str, stance: str) -> float:
    values = da.player_values(stance)
    match = values[values["gsis_id"] == gsis_id]
    return float(match["value"].iloc[0]) if not match.empty else 0.0


def _pick_value(pick_ref: str, stance: str) -> float:
    inv = da.draft_pick_inventory()
    row = inv[inv["pick_ref"] == pick_ref]
    if row.empty:
        return 0.0
    return pv.value_for_pick_row(row.iloc[0], inv, stance)


def asset_value(asset_type: str, asset_id: str, stance: str = "balanced") -> float:
    if asset_type == "player":
        return _player_value(asset_id, stance)
    if asset_type == "pick":
        # There is no redraft-vs-dynasty board to choose between for a pick --
        # it is a player who does not exist yet -- so the stance enters as a
        # scalar on the market curve instead (pick_value._STANCE_SCALAR).
        return _pick_value(asset_id, stance)
    raise ValueError(f"unknown asset_type {asset_type!r}")


def evaluate_trade(
    give: list[dict], receive: list[dict], stance: str = "balanced"
) -> dict:
    """give/receive: [{"asset_type": "player"|"pick", "asset_id": ...}, ...]

    give = what "my" team sends away, receive = what "my" team gets back.
    """
    give_assets = [
        {**a, "value": asset_value(a["asset_type"], a["asset_id"], stance)} for a in give
    ]
    receive_assets = [
        {**a, "value": asset_value(a["asset_type"], a["asset_id"], stance)}
        for a in receive
    ]
    give_total = sum(a["value"] for a in give_assets)
    receive_total = sum(a["value"] for a in receive_assets)
    delta = receive_total - give_total
    denom = max(give_total, receive_total, 1e-9)
    asymmetry_pct = abs(delta) / denom * 100

    return {
        "give": give_assets,
        "receive": receive_assets,
        "give_total": give_total,
        "receive_total": receive_total,
        "delta": delta,
        "asymmetry_pct": asymmetry_pct,
        "favors": "receiving_side" if delta > 0 else ("giving_side" if delta < 0 else "even"),
    }

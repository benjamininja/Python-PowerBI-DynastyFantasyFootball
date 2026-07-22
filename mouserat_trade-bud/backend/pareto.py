"""Pareto-asymmetry trade diagnostic (decision #11): compares total blended
value given vs. received per side, on the shared 0-100-ish scale used for
both players (data_access.player_blended_values) and picks
(pick_value.resolve_pick_value) so the two asset types are directly
comparable in a mixed give/receive package (decision #9).
"""

from __future__ import annotations

import data_access as da
import pick_value as pv

_FORMAT_BY_POSITION_GROUP = {
    "QB": "SF", "RB": "SF", "WR": "SF", "TE": "SF",
    "DL": "IDP", "LB": "IDP", "DB": "IDP",
}


def _player_value(gsis_id: str) -> float:
    players = da.read_parquet("dim_nfl_players")[["gsis_id", "position_group"]]
    row = players[players["gsis_id"] == gsis_id]
    pos = row["position_group"].iloc[0] if not row.empty else None
    fmt = _FORMAT_BY_POSITION_GROUP.get(pos, "SF")
    values = da.player_blended_values(fmt)
    match = values[values["gsis_id"] == gsis_id]
    return float(match["blended_value"].iloc[0]) if not match.empty else 0.0


def _pick_value(pick_ref: str) -> float:
    inv = da.draft_pick_inventory()
    row = inv[inv["pick_ref"] == pick_ref]
    if row.empty:
        return 0.0
    return pv.value_for_pick_row(row.iloc[0], inv)


def asset_value(asset_type: str, asset_id: str) -> float:
    if asset_type == "player":
        return _player_value(asset_id)
    if asset_type == "pick":
        return _pick_value(asset_id)
    raise ValueError(f"unknown asset_type {asset_type!r}")


def evaluate_trade(give: list[dict], receive: list[dict]) -> dict:
    """give/receive: [{"asset_type": "player"|"pick", "asset_id": ...}, ...]

    give = what "my" team sends away, receive = what "my" team gets back.
    """
    give_assets = [
        {**a, "value": asset_value(a["asset_type"], a["asset_id"])} for a in give
    ]
    receive_assets = [
        {**a, "value": asset_value(a["asset_type"], a["asset_id"])} for a in receive
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

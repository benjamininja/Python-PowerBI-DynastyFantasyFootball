"""Resolves a real/synthetic draft pick to a blended 0-100 market-value
percentile -- the same 0-100 scale data_access.player_values produces, so
picks and players are directly comparable for Pareto math (decision #11).

Both curve sources in dim_pick_value_curve (KTC, DraftSharks -- see
notebooks/04d_draftpick_value_curve.ipynb and the plan's decision #10)
publish generic (year, round[, tier]) buckets on a 12-team grid. This league
drafts 14 teams per division, so a pick's within-round slot is fit onto the
source's tier boundaries proportionally rather than assumed 1:1 (the plan's
"fit our 14 to the 12" note).
"""

from __future__ import annotations

import pandas as pd

import data_access as da

_TIERS = ["Early", "Mid", "Late"]

# What a pick is worth depends on who is holding it: a contending team is
# trying to win now and a pick is a player who does not exist yet, while a
# future-focused team is buying exactly that. The curve sources publish one
# market price, so this is a hand-set scalar (decision 2026-07-31) and the
# matching knob to the future-stance age tilt in data_access. Applied last, so
# picks stay on the same 0-100 scale as players.
_STANCE_SCALAR = {"contending": 0.85, "balanced": 1.00, "future": 1.25}


def _latest_curve() -> pd.DataFrame:
    curve = da.read_parquet("dim_pick_value_curve")
    latest = curve["snapshot_date"].max()
    return curve[curve["snapshot_date"] == latest]


def _with_percentiles(curve: pd.DataFrame) -> pd.DataFrame:
    curve = curve.copy()
    curve["percentile"] = curve.groupby("source_name")["value"].transform(
        lambda s: (s - s.min()) / (s.max() - s.min()) * 100 if s.max() > s.min() else 50.0
    )
    return curve


def _tier_for_slot(pick_in_round: int, n_teams: int) -> str:
    idx = min(2, int((pick_in_round - 1) * 3 / n_teams))
    return _TIERS[idx]


def resolve_pick_value(
    draft_year: int, round_num: int, pick_in_round: int, n_teams: int,
    stance: str = "balanced",
) -> float:
    """Blended 0-100 percentile value for one pick, scaled by stance.

    Averages whichever curve sources have data for this draft_year. A round
    beyond a source's covered range (KTC tops out at 4, DraftSharks at 5)
    falls back to that source's last covered round for the same year --
    dynasty pick value flattens out fast past round 4-5, so this is a
    reasonable floor rather than a cliff to zero.
    """
    scalar = _STANCE_SCALAR[stance]
    curve = _with_percentiles(_latest_curve())
    year_curve = curve[curve["draft_year"] == draft_year]
    if year_curve.empty:
        return 50.0 * scalar  # no market data at all for this year -- neutral fallback

    percentiles = []
    for source in year_curve["source_name"].unique():
        src = year_curve[year_curve["source_name"] == source]
        max_round = int(src["round"].max())
        rnd = min(round_num, max_round)
        rows = src[src["round"] == rnd]
        flat = rows[rows["tier"] == "All"]
        if not flat.empty:
            percentiles.append(float(flat["percentile"].iloc[0]))
            continue
        tier = _tier_for_slot(pick_in_round, n_teams)
        match = rows[rows["tier"] == tier]
        if not match.empty:
            percentiles.append(float(match["percentile"].iloc[0]))

    blended = sum(percentiles) / len(percentiles) if percentiles else 50.0
    return blended * scalar


def value_for_pick_row(
    row: pd.Series, inventory: pd.DataFrame, stance: str = "balanced"
) -> float:
    """Convenience wrapper for a fact_draft_pick-shaped row (slotted or
    unslotted future pick, as returned by data_access.draft_pick_inventory).

    Unslotted future picks (is_slotted=False) have no real pick_in_round yet
    (the draft hasn't happened) -- fall back to the division's middle slot,
    which resolves to the "Mid" tier via _tier_for_slot. A neutral estimate,
    not a real slot -- refined once the pick is actually made/traded to a slot.
    """
    n_teams = inventory[inventory["divisionId"] == row["divisionId"]]["current_owner"].nunique()
    draft_year = int(str(row["draft_season"]).split("-")[0])
    if row.get("is_slotted", True) and pd.notna(row.get("pick_in_round")):
        pick_in_round = int(row["pick_in_round"])
    else:
        pick_in_round = (n_teams + 1) // 2
    return resolve_pick_value(
        draft_year, int(row["round"]), pick_in_round, int(n_teams), stance
    )

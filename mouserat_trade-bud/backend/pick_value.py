"""Resolves a real/synthetic draft pick to a 0-100 our-scale value,
commensurate with data_access.player_values (ADR-0013 decision 4) so picks
and players are directly comparable for Pareto math (decision #11).

Both curve sources in dim_pick_value_curve (KTC, DraftSharks -- see
notebooks/04d_draftpick_value_curve.ipynb and the plan's decision #10)
publish generic (year, round[, tier]) buckets on a 12-team grid. This league
drafts 14 teams per division, so a pick's within-round slot is fit onto the
source's tier boundaries proportionally rather than assumed 1:1 (the plan's
"fit our 14 to the 12" note).

A pick's curve value is on that source's own arbitrary points scale (e.g.
KTC 0-9999), not directly comparable to our-scale player values. Each pick
is quantile-mapped instead: find its percentile within the source's own
covered *player* pool (same source, same points scale), then read off the
value at that percentile of our-scale player value restricted to that same
pool. Monotone by construction, no hand-set curve-to-scale constant.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data_access as da

_TIERS = ["Early", "Mid", "Late"]

# What a pick is worth depends on who is holding it: a contending team is
# trying to win now and a pick is a player who does not exist yet, while a
# future-focused team is buying exactly that. The curve sources publish one
# market price, so this is a hand-set scalar (decision 2026-07-31) and the
# matching knob to the future-stance age tilt in data_access. Applied after
# quantile mapping, so picks stay on the same 0-100 scale as players.
_STANCE_SCALAR = {"contending": 0.85, "balanced": 1.00, "future": 1.25}

# Pick-curve source_name -> the (source_name, metric_key) on
# fact_dynasty_ranking_metrics that carries that same source's player pool
# on the same points scale. The pick-curve label ("DraftSharks") and the
# fact-table label ("DynastySharks") are the same entity, named differently
# by the two ingest pipelines.
_SOURCE_METRIC = {
    "KTC": ("KTC", "value"),
    "DraftSharks": ("DynastySharks", "ds_value"),
}


def _latest_curve() -> pd.DataFrame:
    curve = da.read_parquet("dim_pick_value_curve")
    latest = curve["snapshot_date"].max()
    return curve[curve["snapshot_date"] == latest]


def _percentile_of(value: float, sorted_arr: np.ndarray) -> float:
    """Percentile (0-100) of `value` within `sorted_arr` (ascending),
    linear interpolation between order statistics -- the inverse of
    numpy.percentile."""
    n = len(sorted_arr)
    idx = int(np.searchsorted(sorted_arr, value))
    if idx <= 0:
        return 0.0
    if idx >= n:
        return 100.0
    lo, hi = sorted_arr[idx - 1], sorted_arr[idx]
    frac = (value - lo) / (hi - lo) if hi > lo else 0.0
    return (idx - 1 + frac) / (n - 1) * 100


def _source_pool(source_name: str, stance: str) -> tuple[np.ndarray, np.ndarray, float]:
    """A pick-curve source's covered player pool: (source's raw points
    sorted ascending, our-scale values index-aligned by gsis_id, our-scale
    pool max), restricted to players data_access.player_values(stance)
    actually prices. Empty arrays if there's no gsis-resolved overlap.
    """
    metric_source, metric_key = _SOURCE_METRIC[source_name]
    eav = da.read_parquet("fact_dynasty_ranking_metrics")
    raw = eav[(eav["source_name"] == metric_source) & (eav["metric_key"] == metric_key)]
    latest = raw["snapshot_date"].max()
    raw = raw[raw["snapshot_date"] == latest].dropna(subset=["gsis_id"])
    # A source's player pool is scored once per format on the same points
    # scale -- average across formats rather than double-counting.
    raw = raw.groupby("gsis_id")["metric_num"].mean()

    values = da.player_values(stance).set_index("gsis_id")["value"]
    aligned = raw.to_frame("raw_value").join(values, how="inner").sort_values("raw_value")
    if aligned.empty:
        return np.array([]), np.array([]), 0.0
    return (
        aligned["raw_value"].to_numpy(),
        aligned["value"].to_numpy(),
        float(aligned["value"].max()),
    )


def _tier_for_slot(pick_in_round: int, n_teams: int) -> str:
    idx = min(2, int((pick_in_round - 1) * 3 / n_teams))
    return _TIERS[idx]


def resolve_pick_value(
    draft_year: int, round_num: int, pick_in_round: int, n_teams: int,
    stance: str = "balanced",
) -> float:
    """Blended 0-100 our-scale value for one pick, scaled by stance.

    Averages whichever curve sources have data for this draft_year, each
    quantile-mapped onto our-scale player value within that source's own
    covered player pool (ADR-0013 decision 4). A round beyond a source's
    covered range (KTC tops out at 4, DraftSharks at 5) falls back to that
    source's last covered round for the same year -- dynasty pick value
    flattens out fast past round 4-5, so this is a reasonable floor rather
    than a cliff to zero.

    The blended, stance-scaled result is clamped at the highest our-scale
    value among the pool(s) it was anchored against -- no pick, under any
    stance, prices above the best player it was quantile-mapped relative to.
    """
    scalar = _STANCE_SCALAR[stance]
    curve = _latest_curve()
    year_curve = curve[curve["draft_year"] == draft_year]
    if year_curve.empty:
        return 50.0 * scalar  # no market data at all for this year -- neutral fallback

    mapped_values = []
    pool_maxes = []
    for source in year_curve["source_name"].unique():
        src = year_curve[year_curve["source_name"] == source]
        max_round = int(src["round"].max())
        rnd = min(round_num, max_round)
        rows = src[src["round"] == rnd]
        flat = rows[rows["tier"] == "All"]
        if not flat.empty:
            curve_value = float(flat["value"].iloc[0])
        else:
            tier = _tier_for_slot(pick_in_round, n_teams)
            match = rows[rows["tier"] == tier]
            if match.empty:
                continue
            curve_value = float(match["value"].iloc[0])

        raw_sorted, our_sorted, pool_max = _source_pool(source, stance)
        if raw_sorted.size == 0:
            continue
        pct = _percentile_of(curve_value, raw_sorted)
        mapped_values.append(float(np.percentile(our_sorted, pct)))
        pool_maxes.append(pool_max)

    if not mapped_values:
        return 50.0 * scalar  # no source resolved to a usable player pool -- neutral fallback

    blended = sum(mapped_values) / len(mapped_values) * scalar
    return min(blended, max(pool_maxes))


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

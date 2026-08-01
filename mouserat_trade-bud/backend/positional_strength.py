"""Per-team, per-position strength ranking -- the football analog of the
baseball reference app's rotisserie category-gap table (decision #4).

One ranking axis per position: teams are ranked 1..N by average value of
their rostered players at that position. Rank near 1 = surplus (sell-high
candidate), rank near N = need -- one ranking serves both, no separate
surplus computation.

All seven positions are computed in a single stance-scoped pass.
data_access.player_values already scores every position group on one currency
(position ceiling x within-position percentile), so the old split into an SF
offense pass and an IDP pass -- which produced two incomparable scales and
made a DL rank mean something different from a WR rank -- is gone.
"""

from __future__ import annotations

import pandas as pd

import data_access as da

_POSITIONS = ["QB", "RB", "WR", "TE", "DL", "LB", "DB"]


def _position_sort_order() -> pd.DataFrame:
    """One row per position_group with its side_of_ball_sort_order +
    position_sort_order, per dim_position (the transformer table -- the
    data-model's own display order, not alphabetical). Side of ball is the
    primary sort key, position within a side is secondary -- offense before
    defense before special teams/picks, matching dim_position's own grain."""
    dp = da.read_parquet("dim_position")[
        ["position_group", "side_of_ball_sort_order", "position_sort_order"]
    ]
    return dp.drop_duplicates("position_group")


def _multi_position_counts(positions: list[str]) -> pd.DataFrame:
    """One row per (team_key, position_group) with a headcount that credits
    dual-eligible players to every position they qualify for, not just their
    single canonical position_group. Source: dim_fantrax_crosswalk's
    position_raw (comma-separated for dual-eligible players, e.g. "DL,LB"),
    exploded and mapped through dim_position -- every raw token found there
    already resolves to a position_group in `positions`, confirmed directly
    against the data (no unmapped tokens)."""
    roster = da.read_parquet("fact_fantasy_teams")[["team_key", "gsis_id"]]
    crosswalk = da.read_parquet("dim_fantrax_crosswalk")[["gsis_id", "position_raw"]]
    dp_map = da.read_parquet("dim_position")[["position_raw", "position_group"]].drop_duplicates("position_raw")

    r = roster.merge(crosswalk, on="gsis_id", how="left")
    r = r.assign(position_raw=r["position_raw"].fillna("").str.split(",")).explode("position_raw")
    r["position_raw"] = r["position_raw"].str.strip()
    r = r.merge(dp_map, on="position_raw", how="left")
    r = r[r["position_group"].isin(positions)]

    return (
        r.groupby(["team_key", "position_group"])["gsis_id"]
        .nunique()
        .rename("position_count")
        .reset_index()
    )


def _team_position_strength(stance: str, positions: list[str]) -> pd.DataFrame:
    roster = da.read_parquet("fact_fantasy_teams")
    players = da.read_parquet("dim_nfl_players")[["gsis_id", "position_group"]]
    values = da.player_values(stance)[["gsis_id", "value"]]
    all_team_keys = da.read_parquet("dim_fantasy_teams")["team_key"].unique()

    r = roster.merge(players, on="gsis_id", how="left").merge(
        values, on="gsis_id", how="left"
    )
    r = r[r["position_group"].isin(positions)].copy()
    r["value"] = r["value"].fillna(0)

    agg = (
        r.groupby(["team_key", "position_group"])["value"]
        .mean()
        .rename("avg_value")
        .reset_index()
    )
    # A team with zero rostered players at a position produces no group
    # above and would otherwise vanish from that position's table entirely
    # (the DL-shows-26/28-teams bug) instead of correctly ranking last as
    # the clearest possible "need" signal -- reindex the full team x
    # position cross before ranking so every position group always covers
    # every team in the league.
    full_index = pd.MultiIndex.from_product(
        [all_team_keys, positions], names=["team_key", "position_group"]
    )
    agg = agg.set_index(["team_key", "position_group"]).reindex(
        full_index, fill_value=0
    ).reset_index()

    agg["rank"] = agg.groupby("position_group")["avg_value"].rank(
        ascending=False, method="min"
    ).astype(int)
    agg["n_teams"] = agg.groupby("position_group")["team_key"].transform("nunique")

    counts = _multi_position_counts(positions)
    agg = agg.merge(counts, on=["team_key", "position_group"], how="left")
    agg["position_count"] = agg["position_count"].fillna(0).astype(int)

    agg = agg.merge(_position_sort_order(), on="position_group", how="left")
    agg["side_of_ball_sort_order"] = agg["side_of_ball_sort_order"].fillna(999).astype(int)
    agg["position_sort_order"] = agg["position_sort_order"].fillna(999).astype(int)
    return agg


def _label(rank: int, n_teams: int) -> str:
    if rank <= max(1, n_teams // 3):
        return "surplus"
    if rank > n_teams - max(1, n_teams // 3):
        return "need"
    return "neutral"


def league_positional_strength(stance: str = "balanced") -> pd.DataFrame:
    """All teams x all positions -- computed once, sliced per-team by
    callers so the league-wide ranks stay consistent across requests."""
    combined = _team_position_strength(stance, _POSITIONS)
    combined["label"] = combined.apply(
        lambda r: _label(int(r["rank"]), int(r["n_teams"])), axis=1
    )
    return combined


def positional_strength(team_key: str, stance: str = "balanced") -> list[dict]:
    combined = league_positional_strength(stance)
    mine = combined[combined["team_key"] == team_key].sort_values(
        ["side_of_ball_sort_order", "position_sort_order"]
    )
    return mine.to_dict(orient="records")

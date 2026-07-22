"""Per-team, per-position strength ranking -- the football analog of the
baseball reference app's rotisserie category-gap table (decision #4).

One ranking axis per position: teams are ranked 1..N by average blended
dynasty value of their rostered players at that position. Rank near 1 =
surplus (sell-high candidate), rank near N = need -- one ranking serves
both, no separate surplus computation.

Offense positions use format SF (this league's base dynasty format);
IDP positions (DL/LB/DB) use format IDP, which is FantasyPros-only --
mirrors discord_bot/rankings.py's established per-format scoping (no single
format+source spans both offense and IDP, confirmed in that module's
docstring).
"""

from __future__ import annotations

import pandas as pd

import data_access as da

_OFFENSE_POSITIONS = ["QB", "RB", "WR", "TE"]
_IDP_POSITIONS = ["DL", "LB", "DB"]
_OFFENSE_FORMAT = "SF"
_IDP_FORMAT = "IDP"


def _team_position_strength(fmt: str, positions: list[str]) -> pd.DataFrame:
    roster = da.read_parquet("fact_fantasy_teams")
    players = da.read_parquet("dim_nfl_players")[["gsis_id", "position_group"]]
    values = da.player_blended_values(fmt)
    all_team_keys = da.read_parquet("dim_fantasy_teams")["team_key"].unique()

    r = roster.merge(players, on="gsis_id", how="left").merge(
        values, on="gsis_id", how="left"
    )
    r = r[r["position_group"].isin(positions)].copy()
    r["blended_value"] = r["blended_value"].fillna(0)

    agg = (
        r.groupby(["team_key", "position_group"])["blended_value"]
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
    return agg


def _label(rank: int, n_teams: int) -> str:
    if rank <= max(1, n_teams // 3):
        return "surplus"
    if rank > n_teams - max(1, n_teams // 3):
        return "need"
    return "neutral"


def league_positional_strength() -> pd.DataFrame:
    """All teams x all positions -- computed once, sliced per-team by
    callers so the league-wide ranks stay consistent across requests."""
    offense = _team_position_strength(_OFFENSE_FORMAT, _OFFENSE_POSITIONS)
    idp = _team_position_strength(_IDP_FORMAT, _IDP_POSITIONS)
    combined = pd.concat([offense, idp], ignore_index=True)
    combined["label"] = combined.apply(
        lambda r: _label(int(r["rank"]), int(r["n_teams"])), axis=1
    )
    return combined


def positional_strength(team_key: str) -> list[dict]:
    combined = league_positional_strength()
    mine = combined[combined["team_key"] == team_key].sort_values("position_group")
    return mine.to_dict(orient="records")

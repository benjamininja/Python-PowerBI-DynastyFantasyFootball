"""Parquet + cap-math access layer for the trade-diagnostic backend.

Reads this repo's data/ parquet directly (no network) and reuses
discord_bot/capmath.py's cap-hit/dead-money formulas instead of
reimplementing them (decision #2). discord_bot's own fetch_parquet hits the
GitHub Contents API -- that's necessary for the deployed bot, which has no
local repo checkout, but doesn't apply here since this backend runs inside
the repo. We monkeypatch capmath's module-level fetch_parquet to a local
reader so the cap formulas stay the single source of truth while I/O reads
local files directly.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

_discord_bot_dir = REPO_ROOT / "discord_bot"
if str(_discord_bot_dir) not in sys.path:
    sys.path.insert(0, str(_discord_bot_dir))

import capmath  # noqa: E402 -- needs discord_bot on sys.path first
import github_fetch  # noqa: E402


def _local_fetch_parquet(path: str, cfg=None) -> pd.DataFrame:
    return pd.read_parquet(REPO_ROOT / path)


# capmath.py did `from github_fetch import fetch_parquet`, binding the name
# into its own module namespace -- patching capmath.fetch_parquet (not just
# github_fetch.fetch_parquet) is what actually redirects its calls.
github_fetch.fetch_parquet = _local_fetch_parquet
capmath.fetch_parquet = _local_fetch_parquet


class _LocalConfig:
    """Placeholder passed to capmath's functions -- they only touch cfg for
    fetch_parquet's cache key/URL building, which we've replaced above."""

    github_ref = "local"


CFG = _LocalConfig()


def read_parquet(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / f"{name}.parquet")


def teams_with_cap() -> pd.DataFrame:
    return capmath.teams_with_cap(CFG)


def roster_with_cap_hit() -> pd.DataFrame:
    return capmath.roster_with_cap_hit(CFG)


STANCES = ("contending", "balanced", "future")

# Stance primarily selects a ranking *source*: a contending team is buying this
# season's production (DraftSharks' redraft tree), everyone else is buying the
# dynasty asset. There is exactly one dynasty board set, so balanced and future
# read the same boards -- which made them price identically, two of three
# stance chips a visible no-op. Future is therefore differentiated by an age
# tilt below (decision 2026-07-31); it is the one hand-set knob on the player
# side, and picks carry the matching one in pick_value.
_STANCE_RANK_KEYS = {
    "contending": ("dsr_overall_rank",),
    "balanced": ("ds_overall_rank", "ktc_overall_rank", "fp_overall_rank"),
    "future": ("ds_overall_rank", "ktc_overall_rank", "fp_overall_rank"),
}

# Only `future` tilts. Continuous in age rather than bucketed so nobody loses a
# chunk of value overnight on a birthday, and clamped at both ends so the tilt
# can shade a close trade without ever inverting a board's own ordering by more
# than the clamp allows. Pivot 26 = roughly the age at which a dynasty asset
# stops appreciating.
_AGE_PIVOT = 26.0
_AGE_SLOPE = 0.03
_AGE_CLAMP = (0.70, 1.20)
_STANCE_AGE_TILT = {"contending": False, "balanced": False, "future": True}


def _age_multiplier(ages: pd.Series) -> pd.Series:
    """Per-player youth premium for the future stance. Unknown birth_date -> 1.0
    (no tilt): a missing date is ignorance, not evidence that a player is old."""
    tilt = 1 + (_AGE_PIVOT - ages) * _AGE_SLOPE
    return tilt.clip(*_AGE_CLAMP).fillna(1.0)


def _player_ages() -> pd.DataFrame:
    """gsis_id -> age in years, from dim_nfl_players.birth_date."""
    players = read_parquet("dim_nfl_players")[["gsis_id", "birth_date"]].copy()
    born = pd.to_datetime(players["birth_date"], errors="coerce")
    players["age"] = (pd.Timestamp(date.today()) - born).dt.days / 365.25
    return players[["gsis_id", "age"]]


def _latest_overall_ranks(rank_keys: tuple[str, ...]) -> pd.DataFrame:
    """The requested *_overall_rank rows, at each series' own latest snapshot.

    Not a single global max(snapshot_date): the sources refresh on independent
    cadences (DraftSharks was re-pulled 2026-07-31, KTC/FantasyPros last on
    2026-06-13), so a global max would silently drop every source but the most
    recently scraped one. A series here is (source_name, format, metric_key) --
    the same source ranks several formats, each its own board.
    """
    eav = read_parquet("fact_dynasty_ranking_metrics")
    ranks = eav[eav["metric_key"].isin(rank_keys)].copy()
    if ranks.empty:
        return ranks
    series = ["source_name", "format", "metric_key"]
    newest = ranks.groupby(series)["snapshot_date"].transform("max")
    return ranks[ranks["snapshot_date"] == newest].dropna(subset=["gsis_id"])


def _position_fpts() -> pd.DataFrame:
    """gsis_id -> fantasy points, from the newest Fantrax player-universe
    capture. This is the fallback ordering for players no expert board covers
    (~3% of rostered copies on the dynasty pool, ~8% on redraft, worst at QB)."""
    adp = read_parquet("fact_fantrax_adp")
    adp = adp[adp["capture_date"] == adp["capture_date"].max()]
    adp = adp.dropna(subset=["gsis_id", "fpts"])
    return (
        adp.sort_values("fpts", ascending=False)
        .drop_duplicates("gsis_id")[["gsis_id", "fpts"]]
    )


def position_ceilings() -> pd.DataFrame:
    """position_group -> ceiling (0-100), the cross-position scarcity
    multiplier from dim_position_ceiling's conference-averaged `ALL` row."""
    c = read_parquet("dim_position_ceiling")
    c = c[c["snapshot_date"] == c["snapshot_date"].max()]
    return c[c["conference"] == "ALL"][["position_group", "ceiling"]]


def player_values(stance: str) -> pd.DataFrame:
    """One row per gsis_id: `value` = position ceiling x within-position percentile.

    Columns: gsis_id, position_group, percentile, ceiling, value, is_ranked.

    The percentile is computed **within a position group**, never across a
    whole format pool. That is the fix for the defect this module used to
    have: the old blend ranked a DB against every other DB *and* against every
    WR in the same pool depending on format, then summed offense and IDP
    percentiles as if they were one currency. An 80th-percentile DB and an
    80th-percentile QB are drawn from unrelated pools; only after each is
    multiplied by its position's ceiling are the two numbers comparable.

    Players no board covers fall back to their within-position fantasy-points
    percentile, on the same 0-1 scale, so the tail is ordered by production
    rather than dropped to zero.

    The `future` stance additionally applies `_age_multiplier` to the finished
    value -- the only place a hand-set number touches a player price.
    """
    if stance not in _STANCE_RANK_KEYS:
        raise ValueError(f"unknown stance {stance!r}; expected one of {STANCES}")

    players = read_parquet("dim_nfl_players")[["gsis_id", "position_group"]]
    ceilings = position_ceilings()
    positions = set(ceilings["position_group"])

    ranks = _latest_overall_ranks(_STANCE_RANK_KEYS[stance])
    ranks = ranks.merge(players, on="gsis_id", how="left")
    ranks = ranks[ranks["position_group"].isin(positions)]

    # Percentile within (board, position): each board is scored on its own
    # depth at that position, so a 52-QB board and a 206-WR board contribute
    # equally instead of the deeper board dominating the average.
    board = ["source_name", "format", "metric_key", "position_group"]
    n = ranks.groupby(board)["metric_num"].transform("size")
    # metric_num is a rank -- 1 is best, so invert. Denominator n keeps the
    # last-ranked player just above 0 rather than at it; being ranked at all
    # should outvalue being unranked with the same production.
    place = ranks.groupby(board)["metric_num"].rank(method="min", ascending=True)
    ranks = ranks.assign(percentile=(n - place + 1) / n)

    ranked = (
        ranks.groupby(["gsis_id", "position_group"], as_index=False)["percentile"]
        .mean()
        .assign(is_ranked=True)
    )

    # Unranked players are ordered among themselves by fantasy points, then
    # compressed into the band *below* the worst ranked player at that
    # position. Ranking them on the open 0-1 scale instead would put the best
    # unranked QB at 1.0 -- ahead of every quarterback the experts actually
    # rated -- because his pool is only the leftovers. The boards run ~900
    # deep, so unranked means deep bench, and the floor is the right ceiling
    # for them.
    floor = (
        ranked.groupby("position_group")["percentile"].min().rename("floor")
    )
    fpts = _position_fpts().merge(players, on="gsis_id", how="left")
    fpts = fpts[fpts["position_group"].isin(positions)]
    fpts = fpts[~fpts["gsis_id"].isin(set(ranked["gsis_id"]))].copy()
    fpts["within"] = fpts.groupby("position_group")["fpts"].rank(pct=True)
    fpts = fpts.merge(floor, on="position_group", how="left")
    fpts["percentile"] = fpts["within"] * fpts["floor"].fillna(1.0)
    fallback = fpts[["gsis_id", "position_group", "percentile"]].assign(is_ranked=False)

    out = pd.concat([ranked, fallback], ignore_index=True)
    out = out.merge(ceilings, on="position_group", how="left")
    out["value"] = out["ceiling"] * out["percentile"]

    if _STANCE_AGE_TILT[stance]:
        out = out.merge(_player_ages(), on="gsis_id", how="left")
        out["value"] = out["value"] * _age_multiplier(out["age"])
        out = out.drop(columns="age")

    return out


def draft_pick_inventory() -> pd.DataFrame:
    """Real fact_draft_pick (completed 2026 startup draft, slotted) + real
    fact_draft_pick_future (2027-2028 rounds 1-5, unslotted -- pre-draft picks
    have no pick_in_round/overall_slot yet). Both are real Fantrax data as of
    2026-07-18 (notebooks/04u_fantrax_public_api.py, getDraftPicks): the
    future table's `current_owner` already reflects any pick-for-pick trades
    executed on-platform. `is_slotted` replaces the old `is_synthetic` flag
    now that nothing here is synthesized.
    """
    real = read_parquet("fact_draft_pick").copy()
    real["is_slotted"] = True

    future = read_parquet("fact_draft_pick_future").copy()

    return pd.concat([real, future], ignore_index=True)


def player_age(gsis_id: str, players: pd.DataFrame | None = None) -> float | None:
    players = read_parquet("dim_nfl_players") if players is None else players
    row = players[players["gsis_id"] == gsis_id]
    if row.empty or pd.isna(row["birth_date"].iloc[0]):
        return None
    today = pd.Timestamp(date.today())
    return float((today - pd.to_datetime(row["birth_date"].iloc[0])).days / 365.25)

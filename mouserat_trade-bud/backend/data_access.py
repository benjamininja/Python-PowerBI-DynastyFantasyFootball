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


def player_blended_values(fmt: str) -> pd.DataFrame:
    """One row per gsis_id: a blended dynasty value on a 0-100 scale.

    No pre-computed cross-source blended value exists in the EAV fact (only
    KTC carries a raw point-value metric; other sources only carry ranks) --
    per user decision, this blends each source's *_overall_rank for the
    given format by converting rank -> a within-source percentile (so a
    KTC pool of ~500 and a DynastySharks pool of a different size count
    equally) and averaging whichever sources cover the player. Missing
    sources are excluded from a player's average, not zero-filled.
    """
    eav = read_parquet("fact_dynasty_ranking_metrics")
    rank_keys = [k for k in eav["metric_key"].unique() if k.endswith("_overall_rank")]
    ranks = eav[(eav["format"] == fmt) & (eav["metric_key"].isin(rank_keys))]
    if ranks.empty:
        return pd.DataFrame(columns=["gsis_id", "blended_value"])

    latest = ranks["snapshot_date"].max()
    ranks = ranks[ranks["snapshot_date"] == latest].dropna(subset=["gsis_id"])

    ranks = ranks.copy()
    ranks["percentile"] = ranks.groupby("source_name")["metric_num"].transform(
        lambda s: (s.max() - s + 1) / s.max() * 100
    )
    blended = (
        ranks.groupby("gsis_id")["percentile"]
        .mean()
        .rename("blended_value")
        .reset_index()
    )
    return blended


_FUTURE_YEARS = (2027, 2028)
_FUTURE_ROUNDS = range(1, 6)  # curve coverage (04d) tops out around here


def draft_pick_inventory() -> pd.DataFrame:
    """Real dim_draft_pick rows + a synthesized future-pick baseline.

    dim_draft_pick currently only has the completed 2026-2027 draft (no
    forward-looking pick ledger exists -- fact_roster_transactions has
    exactly one event_type, startup_draft; confirmed 2026-07-17, no
    pick-for-pick trade feed has been ETL'd yet even though Fantrax's live
    draft-pick trading may already be active on-platform). Until that ETL
    exists, 2027/2028 rounds 1-5 are synthesized as one pick per team per
    division-round with original_owner == current_owner (no trades
    reflected). is_synthetic flags these so callers never confuse them with
    real trade history.
    """
    real = read_parquet("dim_draft_pick").copy()
    real["is_synthetic"] = False

    div_teams = real.groupby("divisionId")["current_owner"].unique().to_dict()
    rows = []
    for div_id, teams in div_teams.items():
        n_teams = len(teams)
        for year in _FUTURE_YEARS:
            for rnd in _FUTURE_ROUNDS:
                for slot, team in enumerate(sorted(teams), start=1):
                    rows.append(
                        {
                            "pick_ref": f"{year}|{div_id}|synthetic-R{rnd}-{team}",
                            "draft_season": f"{year}-{year + 1}",
                            "round": rnd,
                            "pick_in_round": slot,
                            "overall_slot": (rnd - 1) * n_teams + slot,
                            "original_owner": team,
                            "divisionId": div_id,
                            "current_owner": team,
                            "is_made": False,
                            "is_synthetic": True,
                        }
                    )
    future = pd.DataFrame(rows)
    return pd.concat([real, future], ignore_index=True)


def player_age(gsis_id: str, players: pd.DataFrame | None = None) -> float | None:
    players = read_parquet("dim_nfl_players") if players is None else players
    row = players[players["gsis_id"] == gsis_id]
    if row.empty or pd.isna(row["birth_date"].iloc[0]):
        return None
    today = pd.Timestamp(date.today())
    return float((today - pd.to_datetime(row["birth_date"].iloc[0])).days / 365.25)

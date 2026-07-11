"""The `rankings` command — a format-scoped, per-position dynasty board.

Data grain reality (see the skill's data-model.md): no single format+source spans
all positions. SF/TEPP hold offense (QB/RB/WR/TE); IDP holds defense
(DE/DT/LB/CB/S, FantasyPros only). So the board is scoped to ONE format, and the
source defaults to the primary one available for that format.

Layout/pagination and privacy delivery are shared (render.py / delivery.py); this
module is just the query + column mapping.
"""

from __future__ import annotations

import logging

import discord
import pandas as pd
from discord.ext import commands

import render
from config import Config
from delivery import CommandError, respond_with_embeds
from github_fetch import fetch_parquet

log = logging.getLogger("league-bot.rankings")

_METRICS_PATH = "data/fact_dynasty_ranking_metrics.parquet"
_PLAYERS_PATH = "data/dim_nfl_players.parquet"

# Each dynasty source folds its positional rank into the single EAV fact under a
# source-prefixed metric key (e.g. KTC -> "ktc_positional_rank").
_SOURCE_PREFIX = {"KTC": "ktc", "DynastySharks": "ds", "FantasyPros": "fp"}

# Display order. Grouping uses dim_nfl_players.position_group, which matches how
# each source ranks within positions: offense QB/RB/WR/TE, IDP DL/LB/DB. Grouping
# by the granular `position` instead fragments a source's single rank sequence
# (e.g. FantasyPros' one DL list) across many fields with duplicate-looking #1s —
# verified against the data. Anything unlisted is appended by _order_positions.
_POSITION_ORDER = ["QB", "RB", "WR", "TE", "DL", "LB", "DB"]

# Preferred source per format when the user doesn't specify one.
_PREFERRED_SOURCE = {"SF": "KTC", "TEPP": "KTC", "IDP": "FantasyPros"}

_DEFAULT_FORMAT = "SF"
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 25


def _order_positions(positions: list[str]) -> list[str]:
    known = [p for p in _POSITION_ORDER if p in positions]
    extra = sorted(p for p in positions if p not in _POSITION_ORDER)
    return known + extra


def _pick_source(df: pd.DataFrame, fmt: str, source: str | None) -> str:
    available = sorted(df["source_name"].unique())
    if not available:
        raise CommandError(f"No rankings found for **{fmt}** in the latest snapshot.")
    if source:
        if source not in available:
            raise CommandError(
                f"Source **{source}** has no **{fmt}** data. "
                f"Available for {fmt}: {', '.join(available)}."
            )
        return source
    preferred = _PREFERRED_SOURCE.get(fmt)
    if preferred and preferred in available:
        return preferred
    return available[0]


def _format_field(rows: pd.DataFrame) -> str:
    lines = [
        f"{render.fmt_int(r.positional_rank)}  {render.safe_str(r.player_name, 20):<20} "
        f"{render.safe_str(r.nfl_team, 3):<3}"
        for r in rows.itertuples()
    ]
    return render.mono_block(lines)


def build_rankings_embeds(
    cfg: Config,
    fmt: str = _DEFAULT_FORMAT,
    source: str | None = None,
    position: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[discord.Embed]:
    fmt = fmt.upper()
    limit = max(1, min(limit, _MAX_LIMIT))

    eav = fetch_parquet(_METRICS_PATH, cfg)
    players = fetch_parquet(_PLAYERS_PATH, cfg)

    formats = sorted(eav["format"].dropna().unique())
    if fmt not in formats:
        raise CommandError(f"Unknown format **{fmt}**. Available: {', '.join(formats)}.")

    # Pull just each source's positional-rank rows for this format — one row per
    # player per source. metric_num carries the rank.
    rank_keys = {f"{p}_positional_rank" for p in _SOURCE_PREFIX.values()}
    ranks = eav[(eav["format"] == fmt) & (eav["metric_key"].isin(rank_keys))]
    if ranks.empty:
        raise CommandError(f"No rankings found for **{fmt}** yet.")

    # Latest snapshot only — the fact is a manual-cadence time series.
    latest = ranks["snapshot_date"].max()
    ranks = ranks[ranks["snapshot_date"] == latest]

    src = _pick_source(ranks, fmt, source)
    ranks = ranks[ranks["source_name"] == src]

    # Identity (name / position group / team) lives on dim_nfl_players now — join
    # on gsis_id. Inner join drops any rank row whose gsis didn't resolve.
    if "gsis_id" not in ranks.columns:
        raise CommandError(
            f"Rankings for **{fmt}** are missing player identity — the dynasty "
            "pipeline likely needs its post-refactor re-run."
        )
    ident = players[["gsis_id", "display_name", "position_group", "team_abbr"]]
    board = ranks.merge(ident, on="gsis_id", how="inner")

    board = board.rename(
        columns={
            "metric_num": "positional_rank",
            "display_name": "player_name",
            "team_abbr": "nfl_team",
            "position_group": "position",
        }
    )
    board = board.sort_values("positional_rank").drop_duplicates("gsis_id")
    if board.empty:
        raise CommandError(f"No rankings to show for {fmt}/{src}.")

    # Re-rank 1..N within each displayed group. A source can rank sub-positions
    # separately (FantasyPros ranks DE and DT on their own), which would show
    # co-ranked #1s once merged into the registry's DL/LB/DB groups; ranking by
    # the source order within the group yields a clean sequence. No-op for offense.
    board["positional_rank"] = (
        board.groupby("position")["positional_rank"].rank(method="first").astype(int)
    )

    if position:
        position = position.upper()
        if position not in set(board["position"]):
            avail = ", ".join(_order_positions(sorted(board["position"].dropna().unique())))
            raise CommandError(f"No **{position}** in {fmt}/{src}. Positions: {avail}.")
        positions = [position]
    else:
        positions = _order_positions(sorted(board["position"].dropna().unique()))

    fields: list[tuple[str, str]] = []
    for pos in positions:
        rows = board[board["position"] == pos].sort_values("positional_rank").head(limit)
        if rows.empty:
            continue
        fields.append((pos, _format_field(rows)))

    latest_label = f"{pd.Timestamp(latest):%Y-%m-%d}"
    embeds = render.paginate_fields(
        title=f"Dynasty Rankings — {fmt} ({src})",
        fields=fields,
        footer=f"Source: {src} · Format: {fmt} · Snapshot: {latest_label}",
    )
    if not embeds:
        raise CommandError(f"No rankings to show for {fmt}/{src}.")
    return embeds


class Rankings(commands.Cog):
    def __init__(self, bot: commands.Bot, cfg: Config):
        self.bot = bot
        self.cfg = cfg

    @commands.hybrid_command(
        name="rankings",
        description="Per-position dynasty board (private to you unless you share).",
    )
    @discord.app_commands.describe(
        fmt="League format: SF (default), TEPP, or IDP.",
        position="Filter to one position (e.g. QB, LB). Omit for all.",
        source="Ranking source override (default: best available for the format).",
        limit="Players per position (default 10, max 25).",
        share="Post the result publicly in the channel (default: private to you).",
    )
    async def rankings(
        self,
        ctx: commands.Context,
        fmt: str = _DEFAULT_FORMAT,
        position: str | None = None,
        source: str | None = None,
        limit: int = _DEFAULT_LIMIT,
        share: bool = False,
    ) -> None:
        await respond_with_embeds(
            ctx, share, build_rankings_embeds, self.cfg, fmt, source, position, limit
        )


async def setup_rankings(bot: commands.Bot, cfg: Config) -> None:
    await bot.add_cog(Rankings(bot, cfg))

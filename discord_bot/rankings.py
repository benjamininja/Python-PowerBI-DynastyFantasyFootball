"""The `rankings` command — a format-scoped, per-position dynasty board.

Data grain reality (see the skill's data-model.md): no single format+source spans
all positions. SF/TEPP hold offense (QB/RB/WR/TE); IDP holds defense
(DE/DT/LB/CB/S, FantasyPros only). So the board is scoped to ONE format, and the
source defaults to the primary one available for that format.
"""

from __future__ import annotations

import discord
import pandas as pd
from discord.ext import commands

from config import Config
from github_fetch import fetch_parquet

_RANKINGS_PATH = "data/fact_dynasty_rankings.parquet"

# Display order: offense first, then defense/IDP. Unknown positions appended.
_POSITION_ORDER = ["QB", "RB", "WR", "TE", "DE", "DT", "LB", "CB", "S"]

# Preferred source per format when the user doesn't specify one.
_PREFERRED_SOURCE = {"SF": "KTC", "TEPP": "KTC", "IDP": "FantasyPros"}

_DEFAULT_FORMAT = "SF"
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 25

# Discord embed limits (leave headroom).
_MAX_FIELDS_PER_EMBED = 25
_MAX_EMBED_CHARS = 5500
_MAX_FIELD_VALUE = 1024


class RankingsError(Exception):
    """User-facing problem (bad arg, no data) — message is safe to show."""


def _order_positions(positions: list[str]) -> list[str]:
    known = [p for p in _POSITION_ORDER if p in positions]
    extra = sorted(p for p in positions if p not in _POSITION_ORDER)
    return known + extra


def _pick_source(df: pd.DataFrame, fmt: str, source: str | None) -> str:
    available = sorted(df["source_name"].unique())
    if source:
        if source not in available:
            raise RankingsError(
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
        f"{int(r.positional_rank):>2}  {str(r.player_name)[:20]:<20} {str(r.nfl_team or ''):<3}"
        for r in rows.itertuples()
    ]
    body = "\n".join(lines)
    block = f"```\n{body}\n```"
    if len(block) > _MAX_FIELD_VALUE:  # defensive: trim to fit one field
        block = block[: _MAX_FIELD_VALUE - 4] + "\n```"
    return block


def build_rankings_embeds(
    cfg: Config,
    fmt: str = _DEFAULT_FORMAT,
    source: str | None = None,
    position: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[discord.Embed]:
    fmt = fmt.upper()
    limit = max(1, min(limit, _MAX_LIMIT))

    df = fetch_parquet(_RANKINGS_PATH, cfg)

    formats = sorted(df["format"].unique())
    if fmt not in formats:
        raise RankingsError(
            f"Unknown format **{fmt}**. Available: {', '.join(formats)}."
        )

    df = df[df["format"] == fmt]

    # Latest snapshot only — the table is a manual-cadence time series.
    latest = df["snapshot_date"].max()
    df = df[df["snapshot_date"] == latest]

    src = _pick_source(df, fmt, source)
    df = df[df["source_name"] == src]

    if position:
        position = position.upper()
        positions = [position] if position in set(df["position_raw"]) else []
        if not positions:
            avail = ", ".join(_order_positions(sorted(df["position_raw"].unique())))
            raise RankingsError(
                f"No **{position}** in {fmt}/{src}. Positions: {avail}."
            )
    else:
        positions = _order_positions(sorted(df["position_raw"].unique()))

    if df.empty:
        raise RankingsError(f"No rankings found for {fmt}/{src}.")

    # Build one field per position, splitting into multiple embeds if needed.
    embeds: list[discord.Embed] = []

    def _new_embed() -> discord.Embed:
        e = discord.Embed(
            title=f"Dynasty Rankings — {fmt} ({src})",
            color=0x5865F2,
        )
        e.set_footer(text=f"Source: {src} · Format: {fmt} · Snapshot: {latest}")
        return e

    current = _new_embed()
    running = len(current.title or "")
    for pos in positions:
        rows = (
            df[df["position_raw"] == pos]
            .sort_values("positional_rank")
            .head(limit)
        )
        if rows.empty:
            continue
        value = _format_field(rows)
        # Start a new embed if this field would overflow field count or chars.
        if len(current.fields) >= _MAX_FIELDS_PER_EMBED or (
            running + len(pos) + len(value) > _MAX_EMBED_CHARS
        ):
            embeds.append(current)
            current = _new_embed()
            running = len(current.title or "")
        current.add_field(name=pos, value=value, inline=False)
        running += len(pos) + len(value)

    if current.fields:
        embeds.append(current)
    if not embeds:
        raise RankingsError(f"No rankings to show for {fmt}/{src}.")
    return embeds


class Rankings(commands.Cog):
    def __init__(self, bot: commands.Bot, cfg: Config):
        self.bot = bot
        self.cfg = cfg

    @commands.hybrid_command(
        name="rankings",
        description="Per-position dynasty board for a league format.",
    )
    @discord.app_commands.describe(
        fmt="League format: SF (default), TEPP, or IDP.",
        position="Filter to one position (e.g. QB, LB). Omit for all.",
        source="Ranking source override (default: best available for the format).",
        limit="Players per position (default 10, max 25).",
    )
    async def rankings(
        self,
        ctx: commands.Context,
        fmt: str = _DEFAULT_FORMAT,
        position: str | None = None,
        source: str | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> None:
        # Defer: fetch + parse can exceed the 3s slash-interaction ack window.
        await ctx.defer()
        try:
            embeds = build_rankings_embeds(self.cfg, fmt, source, position, limit)
        except RankingsError as e:
            await ctx.reply(str(e))
            return
        except Exception:
            await ctx.reply(
                "Couldn't reach the rankings data right now — try again shortly."
            )
            return
        for embed in embeds:
            await ctx.reply(embed=embed)


async def setup_rankings(bot: commands.Bot, cfg: Config) -> None:
    await bot.add_cog(Rankings(bot, cfg))

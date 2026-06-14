"""The `rankings` command — a format-scoped, per-position dynasty board.

Data grain reality (see the skill's data-model.md): no single format+source spans
all positions. SF/TEPP hold offense (QB/RB/WR/TE); IDP holds defense
(DE/DT/LB/CB/S, FantasyPros only). So the board is scoped to ONE format, and the
source defaults to the primary one available for that format.
"""

from __future__ import annotations

import asyncio
import logging

import discord
import pandas as pd
from discord.ext import commands

from config import Config
from github_fetch import fetch_parquet

log = logging.getLogger("league-bot.rankings")

_METRICS_PATH = "data/fact_dynasty_ranking_metrics.parquet"
_PLAYERS_PATH = "data/dim_nfl_players.parquet"

# Each dynasty source folds its positional rank into the single EAV fact under a
# source-prefixed metric key (e.g. KTC -> "ktc_positional_rank"). This maps the
# source's display name to that prefix.
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

# Discord embed limits. The total cap (6000) covers title + fields + footer;
# `len(discord.Embed)` reports that exact total, so we measure against it
# directly instead of hand-summing a subset of the parts.
_MAX_FIELDS_PER_EMBED = 25
_EMBED_TOTAL_LIMIT = 6000
_MAX_FIELD_VALUE = 1024


class RankingsError(Exception):
    """User-facing problem (bad arg, no data) — message is safe to show."""


def _order_positions(positions: list[str]) -> list[str]:
    known = [p for p in _POSITION_ORDER if p in positions]
    extra = sorted(p for p in positions if p not in _POSITION_ORDER)
    return known + extra


def _pick_source(df: pd.DataFrame, fmt: str, source: str | None) -> str:
    available = sorted(df["source_name"].unique())
    if not available:
        raise RankingsError(f"No rankings found for **{fmt}** in the latest snapshot.")
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


def _fmt_rank(value: object) -> str:
    # positional_rank is int today, but a future data gap (NaN / non-numeric)
    # must not crash the whole board — degrade that one row to "?".
    try:
        return f"{int(value):>2}"
    except (TypeError, ValueError):
        return " ?"


def _format_field(rows: pd.DataFrame) -> str:
    # `x or ''` is wrong for pandas missing values: NaN is truthy and pd.NA
    # raises in a boolean test. Use pd.isna so a missing nfl_team renders blank.
    lines = [
        f"{_fmt_rank(r.positional_rank)}  {str(r.player_name)[:20]:<20} "
        f"{('' if pd.isna(r.nfl_team) else str(r.nfl_team))[:3]:<3}"
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

    eav = fetch_parquet(_METRICS_PATH, cfg)
    players = fetch_parquet(_PLAYERS_PATH, cfg)

    formats = sorted(eav["format"].dropna().unique())
    if fmt not in formats:
        raise RankingsError(
            f"Unknown format **{fmt}**. Available: {', '.join(formats)}."
        )

    # The board is each source's positional rank, which the dynasty ETL folds
    # into the single EAV fact as source-prefixed metric keys
    # ("ktc_/ds_/fp_positional_rank"). Pull just those rows for this format —
    # one row per player per source. metric_num carries the rank.
    rank_keys = {f"{p}_positional_rank" for p in _SOURCE_PREFIX.values()}
    ranks = eav[(eav["format"] == fmt) & (eav["metric_key"].isin(rank_keys))]
    if ranks.empty:
        raise RankingsError(f"No rankings found for **{fmt}** yet.")

    # Latest snapshot only — the fact is a manual-cadence time series.
    latest = ranks["snapshot_date"].max()
    ranks = ranks[ranks["snapshot_date"] == latest]

    src = _pick_source(ranks, fmt, source)
    ranks = ranks[ranks["source_name"] == src]

    # Identity (name / position group / team) lives on dim_nfl_players now, not on
    # the fact — join it on gsis_id. An inner join drops any rank row whose gsis
    # didn't resolve; those players aren't in the model anyway.
    if "gsis_id" not in ranks.columns:
        raise RankingsError(
            f"Rankings for **{fmt}** are missing player identity — the dynasty "
            "pipeline likely needs its post-refactor re-run."
        )
    ident = players[["gsis_id", "display_name", "position_group", "team_abbr"]]
    board = ranks.merge(ident, on="gsis_id", how="inner")

    # Normalize to the column names the field renderer expects, then collapse any
    # accidental duplicate (one gsis reached via two source ids) to its best rank.
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
        raise RankingsError(f"No rankings to show for {fmt}/{src}.")

    # Re-rank 1..N within each displayed group. A source can rank sub-positions
    # separately (FantasyPros ranks DE and DT on their own), which would show
    # co-ranked #1s once merged into the registry's DL/LB/DB groups. Ranking by
    # the source order within the group yields a clean sequence; for offense,
    # where the source already ranks within QB/RB/WR/TE, this is a no-op.
    board["positional_rank"] = (
        board.groupby("position")["positional_rank"].rank(method="first").astype(int)
    )

    if position:
        position = position.upper()
        positions = [position] if position in set(board["position"]) else []
        if not positions:
            avail = ", ".join(
                _order_positions(sorted(board["position"].dropna().unique()))
            )
            raise RankingsError(
                f"No **{position}** in {fmt}/{src}. Positions: {avail}."
            )
    else:
        positions = _order_positions(sorted(board["position"].dropna().unique()))

    # Build one field per position, splitting into multiple embeds if needed.
    embeds: list[discord.Embed] = []
    latest_label = f"{pd.Timestamp(latest):%Y-%m-%d}"

    def _new_embed() -> discord.Embed:
        e = discord.Embed(
            title=f"Dynasty Rankings — {fmt} ({src})",
            color=0x5865F2,
        )
        e.set_footer(text=f"Source: {src} · Format: {fmt} · Snapshot: {latest_label}")
        return e

    current = _new_embed()
    for pos in positions:
        rows = (
            board[board["position"] == pos]
            .sort_values("positional_rank")
            .head(limit)
        )
        if rows.empty:
            continue
        value = _format_field(rows)
        # Roll to a new embed when adding this field would exceed the field-count
        # or the total-character cap. `len(current)` is Discord's own accounting
        # (title + every field + footer), so the check stays exact as the layout
        # changes. Only split when the current embed already holds a field — a
        # single field always fits (its value is capped at 1024), so this can
        # never spin creating empty embeds.
        if current.fields and (
            len(current.fields) >= _MAX_FIELDS_PER_EMBED
            or len(current) + len(pos) + len(value) > _EMBED_TOTAL_LIMIT
        ):
            embeds.append(current)
            current = _new_embed()
        current.add_field(name=pos, value=value, inline=False)

    if current.fields:
        embeds.append(current)
    if not embeds:
        raise RankingsError(f"No rankings to show for {fmt}/{src}.")
    return embeds


class ShareView(discord.ui.View):
    """A 'Post publicly' button attached to a private (ephemeral) result.

    Lets the requester opt into making their otherwise-private board public with
    one deliberate click — the explicit share gate for the slash path. Restricted
    to the original requester so nobody else can publish someone's private query.
    """

    def __init__(self, embeds: list[discord.Embed], author_id: int):
        super().__init__(timeout=300)  # button stops working after 5 min
        self._embeds = embeds
        self._author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._author_id:
            await interaction.response.send_message(
                "Only the person who ran the command can post it publicly.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Post publicly", style=discord.ButtonStyle.primary, emoji="📢")
    async def post_publicly(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        try:
            # Attribute the share so a public post is never anonymous.
            await interaction.channel.send(
                content=f"📢 Rankings shared by {interaction.user.mention}",
                embed=self._embeds[0],
            )
            for embed in self._embeds[1:]:
                await interaction.channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to post in this channel.", ephemeral=True
            )
            return
        button.disabled = True
        button.label = "Posted publicly"
        await interaction.response.edit_message(view=self)  # retire the button
        self.stop()


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
        # Privacy model: results are private by default. Slash → ephemeral; prefix
        # in a public channel → DM the requester. Public only when explicitly
        # asked (share=True, or the slash "Post publicly" button).
        is_slash = ctx.interaction is not None
        if is_slash:
            # Ephemerality is fixed at defer time, so decide it up front. Defer
            # because fetch + parse can exceed the 3s slash ack window.
            await ctx.defer(ephemeral=not share)

        try:
            # Run the (cache-missable) sync fetch + pandas parse off the event
            # loop so a slow GitHub response can't block the gateway.
            embeds = await asyncio.to_thread(
                build_rankings_embeds, self.cfg, fmt, source, position, limit
            )
        except RankingsError as e:
            await self._deliver_text(ctx, is_slash, share, str(e))
            return
        except Exception:
            log.exception("rankings build failed")  # detail to logs, not the user
            await self._deliver_text(
                ctx, is_slash, share,
                "Couldn't reach the rankings data right now — try again shortly.",
            )
            return

        await self._deliver_embeds(ctx, is_slash, share, embeds)

    async def _deliver_embeds(
        self, ctx: commands.Context, is_slash: bool, share: bool,
        embeds: list[discord.Embed],
    ) -> None:
        if share:
            # Explicit public — post in the channel (slash defer was non-ephemeral).
            for embed in embeds:
                await ctx.send(embed=embed)
            return
        if is_slash:
            # Private ephemeral result + a button to opt into posting publicly.
            view = ShareView(embeds, ctx.author.id)
            last = len(embeds) - 1
            for i, embed in enumerate(embeds):
                await ctx.send(
                    embed=embed, ephemeral=True, view=view if i == last else None
                )
            return
        if ctx.guild is None:
            # Prefix in a DM — the channel is already private.
            for embed in embeds:
                await ctx.send(embed=embed)
            return
        # Prefix in a public channel can't be ephemeral → DM the requester.
        try:
            for embed in embeds:
                await ctx.author.send(embed=embed)
        except discord.Forbidden:
            await ctx.reply(
                "Your DMs are closed, so I can't send this privately. Enable DMs "
                "from server members, use `/rankings` for a private result, or add "
                "`true` (share) to post it here publicly."
            )
            return
        await self._react_dm_sent(ctx)

    async def _deliver_text(
        self, ctx: commands.Context, is_slash: bool, share: bool, content: str,
    ) -> None:
        # Same privacy routing as embeds. (Error/notice text carries no ranking
        # data, so the closed-DM fallback can safely show it in-channel.)
        if share or is_slash:
            await ctx.send(content, ephemeral=is_slash and not share)
            return
        if ctx.guild is None:
            await ctx.send(content)
            return
        try:
            await ctx.author.send(content)
        except discord.Forbidden:
            await ctx.reply(content)
            return
        await self._react_dm_sent(ctx)

    @staticmethod
    async def _react_dm_sent(ctx: commands.Context) -> None:
        # Signal "check your DMs" without echoing any data into the channel.
        try:
            await ctx.message.add_reaction("📬")
        except discord.HTTPException:
            pass


async def setup_rankings(bot: commands.Bot, cfg: Config) -> None:
    await bot.add_cog(Rankings(bot, cfg))

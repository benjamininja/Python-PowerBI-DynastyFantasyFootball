"""The `cap` command — league salary-cap standings.

A board of every team's cap position, grouped by conference (one field each) and
sorted by current spend. Conference letters are labelled with the real division
names from dim_division (the read-side table built for exactly this kind of
join), falling back to "Conference {letter}" if that table isn't available.
"""

from __future__ import annotations

import logging

import discord
import pandas as pd
from discord.ext import commands

import render
from capmath import teams_with_cap
from config import Config
from delivery import CommandError, respond_with_embeds
from github_fetch import fetch_parquet

log = logging.getLogger("league-bot.cap")

_DIVISION_PATH = "data/dim_division.parquet"


def _division_labels(cfg: Config) -> dict[str, str]:
    """conference letter -> division name, for the latest season. Empty on miss."""
    try:
        div = fetch_parquet(_DIVISION_PATH, cfg)
    except Exception:
        log.warning("dim_division unavailable; labelling conferences by letter", exc_info=True)
        return {}
    if div.empty:
        return {}
    latest = div[div["season_id"] == div["season_id"].max()]
    return dict(zip(latest["conference"], latest["division_name"]))


def _team_line(row: pd.Series) -> str:
    name = render.safe_str(row["team_name"], 18)
    spent = render.fmt_money(row["active_roster_salary"])
    rem_cur = render.fmt_money(row["remaining_cap_current_yr"])
    rem_next = render.fmt_money(row["remaining_cap_next_yr"])
    return f"{name:<18} {spent:>8} {rem_cur:>9} {rem_next:>9}"


def build_cap_embeds(cfg: Config) -> list[discord.Embed]:
    teams = teams_with_cap(cfg)
    if teams.empty:
        raise CommandError("No team cap data available.")
    labels = _division_labels(cfg)

    header = f"{'Team':<18} {'Spent':>8} {'Rem(cur)':>9} {'Rem(nxt)':>9}"
    fields: list[tuple[str, str]] = []
    for conf in sorted(teams["conference"].dropna().unique()):
        block = (
            teams[teams["conference"] == conf]
            .sort_values("active_roster_salary", ascending=False)
        )
        lines = [header] + [_team_line(r) for _, r in block.iterrows()]
        title = labels.get(conf, f"Conference {conf}")
        fields.append((title, render.mono_block(lines)))

    embeds = render.paginate_fields(
        title="League Cap Standings",
        fields=fields,
        footer="Spent = active roster salary · sorted by spend",
    )
    if not embeds:
        raise CommandError("No cap standings to show.")
    return embeds


class Cap(commands.Cog):
    def __init__(self, bot: commands.Bot, cfg: Config):
        self.bot = bot
        self.cfg = cfg

    @commands.hybrid_command(
        name="cap",
        description="League salary-cap standings by conference (private unless you share).",
    )
    @discord.app_commands.describe(
        share="Post the result publicly in the channel (default: private to you).",
    )
    async def cap(self, ctx: commands.Context, share: bool = False) -> None:
        await respond_with_embeds(ctx, share, build_cap_embeds, self.cfg)


async def setup_cap(bot: commands.Bot, cfg: Config) -> None:
    await bot.add_cog(Cap(bot, cfg))

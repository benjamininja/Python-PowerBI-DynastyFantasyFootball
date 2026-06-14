"""The `roster` command — one team's roster and contracts.

Resolve a team by abbreviation or name (disambiguating on a collision, like
`player`), then list its players by cap hit with their contracts. A team that
hasn't drafted yet (only one division has so far) gets a friendly note with its
available cap rather than an empty board.
"""

from __future__ import annotations

import logging
import re

import discord
import pandas as pd
from discord.ext import commands

import render
from config import Config
from delivery import CommandError, respond_with_embeds
from github_fetch import fetch_parquet

log = logging.getLogger("league-bot.roster")

_TEAMS_PATH = "data/dim_fantasy_teams.parquet"
_OWNERSHIP_PATH = "data/fact_fantasy_teams.parquet"
_PLAYERS_PATH = "data/dim_nfl_players.parquet"

_PLAYERS_PER_FIELD = 15


def _resolve_team(teams: pd.DataFrame, query: str) -> pd.Series:
    q = query.strip().lower()
    if not q:
        raise CommandError("Give me a team, e.g. `/roster BIGL` or `/roster Big L`.")
    exact_abbr = teams[teams["team_abbr"].fillna("").str.lower() == q]
    if len(exact_abbr) == 1:
        return exact_abbr.iloc[0]
    by_name = teams[teams["team_name"].fillna("").str.lower().str.contains(re.escape(q))]
    hits = pd.concat([exact_abbr, by_name]).drop_duplicates("team_key")
    if hits.empty:
        raise CommandError(f"No team matches **{query}**.")
    if len(hits) > 1:
        listed = ", ".join(
            f"{r.team_name} (`{render.safe_str(r.team_abbr)}`)" for r in hits.head(10).itertuples()
        )
        raise CommandError(f"Multiple teams match **{query}**: {listed}. Be more specific.")
    return hits.iloc[0]


def _player_line(row: pd.Series) -> str:
    cap_hit = render.fmt_money(row.get("cap_hit"))
    name = render.safe_str(row.get("player_name"), 18) or "(unknown)"
    pos = render.safe_str(row.get("position_group"), 3) or "?"
    contract = render.fmt_money(row.get("contract_value"))
    status = render.safe_str(row.get("status"), 6) or "—"
    return f"{cap_hit:>8} {name:<18} {pos:<3} {contract:>8} {status}"


def build_roster_embeds(cfg: Config, team: str) -> list[discord.Embed]:
    teams = fetch_parquet(_TEAMS_PATH, cfg)
    if teams.empty:
        raise CommandError("No team data available.")
    t = _resolve_team(teams, team)
    tname = render.safe_str(t["team_name"])

    owned = fetch_parquet(_OWNERSHIP_PATH, cfg)
    mine = owned[owned["team_key"] == t["team_key"]] if not owned.empty else owned
    if mine is None or mine.empty:
        # Prefer remaining cap; fall back to original only when it's actually
        # missing (not when it's a legitimate 0).
        rem = t.get("remaining_cap_current_yr")
        avail = render.fmt_money(t.get("original_cap") if pd.isna(rem) else rem)
        raise CommandError(f"**{tname}** hasn't drafted yet — {avail} cap available.")

    # Join player identity for name + position.
    players = fetch_parquet(_PLAYERS_PATH, cfg)[["gsis_id", "display_name", "position_group"]]
    board = mine.merge(players, on="gsis_id", how="left").rename(
        columns={"display_name": "player_name"}
    )
    board = board.sort_values("cap_hit", ascending=False).reset_index(drop=True)

    header = f"{'Cap':>8} {'Player':<18} {'Pos':<3} {'Salary':>8} Status"
    fields: list[tuple[str, str]] = []
    for start in range(0, len(board), _PLAYERS_PER_FIELD):
        chunk = board.iloc[start : start + _PLAYERS_PER_FIELD]
        lines = ([header] if start == 0 else []) + [_player_line(r) for _, r in chunk.iterrows()]
        label = f"Roster #{start + 1}–{start + len(chunk)}" if start else "Roster"
        fields.append((label, render.mono_block(lines)))

    spent = render.fmt_money(t.get("active_roster_salary"))
    rem = render.fmt_money(t.get("remaining_cap_current_yr"))
    embeds = render.paginate_fields(
        title=f"{tname} — Roster ({len(board)})",
        fields=fields,
        footer=f"Spent {spent} · Remaining {rem}",
    )
    return embeds


class Roster(commands.Cog):
    def __init__(self, bot: commands.Bot, cfg: Config):
        self.bot = bot
        self.cfg = cfg

    @commands.hybrid_command(
        name="roster",
        description="A team's roster and contracts (private unless you share).",
    )
    @discord.app_commands.describe(
        team="Team abbreviation or name (e.g. BIGL or Big L).",
        share="Post the result publicly in the channel (default: private to you).",
    )
    async def roster(
        self, ctx: commands.Context, *, team: str, share: bool = False,
    ) -> None:
        await respond_with_embeds(ctx, share, build_roster_embeds, self.cfg, team)


async def setup_roster(bot: commands.Bot, cfg: Config) -> None:
    await bot.add_cog(Roster(bot, cfg))

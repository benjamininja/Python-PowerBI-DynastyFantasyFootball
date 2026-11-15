"""The `contract-moves` command: the commissioners' contract lists, for any member.

Reads the published `fact_contract_move` snapshot (and `dim_fantasy_teams` for
the team names) through `github_fetch` and renders it with `contract_moves`, as
the table lines in embeds or as the xlsx. The reply is private unless
`share: true`, through `delivery`. The bot only reads.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

import discord
import pandas as pd
from discord import app_commands
from discord.ext import commands

import contract_moves as cm
import render
from config import Config
from delivery import CommandError, FileReply, respond_with_embeds
from github_fetch import fetch_parquet
from roster import _resolve_team

log = logging.getLogger("league-bot.contract-moves")

_MOVES_PATH = "data/fact_contract_move.parquet"
_TEAMS_PATH = "data/dim_fantasy_teams.parquet"

ListName = Literal["minor-to-1st", "expiring", "decision"]
Format = Literal["xlsx", "table"]


def _rows(cfg: Config, list_name: str, team: str | None) -> tuple[pd.DataFrame, str | None]:
    """The list's rows (one team when asked) and that team's name. An empty list
    raises the user-facing message that says why."""
    teams = fetch_parquet(_TEAMS_PATH, cfg)
    moves = fetch_parquet(_MOVES_PATH, cfg)
    team_key = team_name = None
    if team and team.strip():
        found = _resolve_team(teams, team)
        team_key, team_name = found["team_key"], render.safe_str(found["team_name"])
    rows = cm.prepare(moves, teams, list_name, team_key)
    if rows.empty:
        list_is_empty = team_key is None or cm.prepare(moves, teams, list_name).empty
        raise CommandError(cm.empty_message(list_name, None if list_is_empty else team_name))
    return rows, team_name


def build_table_embeds(cfg: Config, list_name: str, team: str | None = None) -> list[discord.Embed]:
    rows, team_name = _rows(cfg, list_name, team)
    chunks = cm.table_chunks(rows)
    fields: list[tuple[str, str]] = []
    first = 1
    for chunk in chunks:
        last = first + len(chunk) - 2
        fields.append((f"Rows {first}–{last}", render.mono_block(chunk)))
        first = last + 1
    title = f"Contract moves — {cm.LIST_LABELS[list_name]} ({len(rows)})"
    if team_name:
        title += f" · {team_name}"
    return render.paginate_fields(title=title, fields=fields, footer=cm.status_summary(rows))


def build_xlsx_reply(cfg: Config, list_name: str, team: str | None = None) -> FileReply:
    rows, team_name = _rows(cfg, list_name, team)
    scope = f" for {team_name}" if team_name else ""
    return FileReply(
        filename=f"contract-moves-{list_name}.xlsx",
        data=cm.xlsx_bytes(rows),
        content=f"Contract moves — {cm.LIST_LABELS[list_name]}{scope}: {len(rows)} rows. "
                f"{cm.status_summary(rows)}",
    )


def build_reply(cfg: Config, list_name: str, fmt: str, team: str | None = None):
    if fmt == "xlsx":
        return build_xlsx_reply(cfg, list_name, team)
    return build_table_embeds(cfg, list_name, team)


class ContractMoves(commands.Cog):
    def __init__(self, bot: commands.Bot, cfg: Config):
        self.bot = bot
        self.cfg = cfg

    @commands.hybrid_command(
        name="contract-moves",
        description="The contract moves due: Minor to 1st, expiring, decisions (private unless you share).",
    )
    @app_commands.describe(
        list_name="Which list: minor-to-1st, expiring or decision.",
        fmt="xlsx (one tab per conference) or table (in Discord).",
        team="Only this team: abbreviation or name (e.g. BIGL or Big L).",
        share="Post the result publicly in the channel (default: private to you).",
    )
    @app_commands.rename(list_name="list", fmt="format")
    async def contract_moves(
        self, ctx: commands.Context, list_name: ListName, fmt: Format = "table",
        *, team: Optional[str] = None, share: bool = False,
    ) -> None:
        await respond_with_embeds(ctx, share, build_reply, self.cfg, list_name, fmt, team)


async def setup_contract_moves(bot: commands.Bot, cfg: Config) -> None:
    await bot.add_cog(ContractMoves(bot, cfg))

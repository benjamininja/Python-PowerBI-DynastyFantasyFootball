"""Offline tests for the bot-wide `on_command_error` (#593): bad input gets the usage
line, any other failure gets the generic notice and a server-side log, an unknown
command gets nothing. No Discord round-trip.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from discord.ext import commands

_BOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BOT_DIR))

import bot  # noqa: E402
from config import Config  # noqa: E402

CFG = Config(
    discord_bot_token="x", discord_guild_id=1, github_pat="x",
    github_owner="o", github_repo="r", github_ref="main", command_prefix="!",
)

SECRET = "member-typed-secret"


class FakeCtx:
    def __init__(self, slash: bool = False, guild: bool = True):
        self.interaction = object() if slash else None
        self.guild = object() if guild else None
        self.prefix = "!"
        self.command = SimpleNamespace(qualified_name="toy", signature="<team> [fmt=table]")
        self.author = SimpleNamespace(id=7, send=AsyncMock())
        self.defer, self.send, self.reply = AsyncMock(), AsyncMock(), AsyncMock()
        self.message = SimpleNamespace(add_reaction=AsyncMock())


def _handle(ctx: FakeCtx, error: Exception) -> None:
    league_bot = bot.LeagueBot(CFG)
    asyncio.run(league_bot.on_command_error(ctx, error))


def _sent(ctx: FakeCtx) -> str:
    return " ".join(str(c) for c in ctx.author.send.await_args_list + ctx.send.await_args_list)


@pytest.mark.parametrize("error", [
    commands.UserInputError(SECRET),
    commands.BadArgument(SECRET),
])
def test_bad_input_gets_the_usage_line_and_echoes_nothing(error):
    ctx = FakeCtx()
    _handle(ctx, error)
    ctx.author.send.assert_awaited_once_with("Usage: `!toy <team> [fmt=table]`")
    assert SECRET not in _sent(ctx)


def test_bad_input_on_a_slash_call_is_ephemeral():
    ctx = FakeCtx(slash=True)
    _handle(ctx, commands.BadArgument(SECRET))
    ctx.send.assert_awaited_once_with("Usage: `!toy <team> [fmt=table]`", ephemeral=True)


def test_any_other_error_gets_the_generic_message_and_is_logged(caplog):
    ctx = FakeCtx()
    boom = RuntimeError(SECRET)
    with caplog.at_level(logging.ERROR, logger="league-bot"):
        _handle(ctx, commands.CommandInvokeError(boom))
    ctx.author.send.assert_awaited_once_with(bot.GENERIC_ERROR)
    assert SECRET not in _sent(ctx)
    records = [r for r in caplog.records if r.name == "league-bot" and r.levelno == logging.ERROR]
    assert len(records) == 1 and records[0].exc_info is not None


def test_an_unknown_command_gets_no_reply_and_no_log(caplog):
    ctx = FakeCtx()
    with caplog.at_level(logging.ERROR, logger="league-bot"):
        _handle(ctx, commands.CommandNotFound(SECRET))
    ctx.author.send.assert_not_awaited()
    ctx.send.assert_not_awaited()
    ctx.reply.assert_not_awaited()
    assert not [r for r in caplog.records if r.name == "league-bot"]

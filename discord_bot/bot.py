"""League bot entrypoint.

A discord.py command bot: registers hybrid commands (slash + prefix) and runs
the gateway. The process must stay alive to answer commands (hence Railway as an
always-on worker).
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from config import Config, load_config
from rankings import setup_rankings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("league-bot")


class LeagueBot(commands.Bot):
    def __init__(self, cfg: Config):
        self.cfg = cfg
        intents = discord.Intents.default()
        # Privileged: required for the PREFIX side of hybrid commands. Toggle it
        # on in the Developer Portal (Bot -> Privileged Gateway Intents) or
        # prefix commands receive empty content and silently do nothing.
        intents.message_content = True
        super().__init__(command_prefix=cfg.command_prefix, intents=intents)

    async def setup_hook(self) -> None:
        await setup_rankings(self, self.cfg)
        # Guild-scoped sync is instant; global can take ~1h. Copy globals to the
        # league guild and sync there so commands appear immediately.
        guild = discord.Object(id=self.cfg.discord_guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        log.info("Slash commands synced to guild %s", self.cfg.discord_guild_id)

    async def on_ready(self) -> None:
        log.info("Logged in as %s (id=%s)", self.user, getattr(self.user, "id", "?"))


async def main() -> None:
    cfg = load_config()
    bot = LeagueBot(cfg)
    async with bot:
        await bot.start(cfg.discord_bot_token)


if __name__ == "__main__":
    asyncio.run(main())

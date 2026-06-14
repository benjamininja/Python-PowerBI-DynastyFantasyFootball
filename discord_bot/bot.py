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
        try:
            await self.tree.sync(guild=guild)
        except discord.Forbidden as e:
            # Caught here, at the one call that can 403 for an invite/scope
            # reason — not around the whole gateway lifetime, where a runtime
            # 403 would be unrelated and the message misleading.
            log.error(
                "Slash-command sync was refused (403 %s). The bot must be in "
                "guild %s AND invited with the applications.commands scope. "
                "Re-invite with scope=bot+applications.commands and confirm "
                "DISCORD_GUILD_ID — retrying will not fix an invite/scope problem.",
                e,
                self.cfg.discord_guild_id,
            )
            raise SystemExit(1) from None
        log.info("Slash commands synced to guild %s", self.cfg.discord_guild_id)

    async def on_ready(self) -> None:
        log.info("Logged in as %s (id=%s)", self.user, getattr(self.user, "id", "?"))


async def main() -> None:
    # Fail fast and loud on unrecoverable startup errors. On Railway these exits
    # are bounded by the restart policy in railway.json (restartPolicyMaxRetries),
    # so a bad token or missing intent can't become an endless crash-restart loop
    # that hammers the Discord login endpoint and gets the token rate-limited.
    try:
        cfg = load_config()
    except RuntimeError as e:
        log.error("Configuration error — fix the variable(s) before redeploying: %s", e)
        raise SystemExit(1) from None

    bot = LeagueBot(cfg)
    # Setup-time failures (e.g. slash-sync 403) are handled in setup_hook. Here we
    # catch the login-time errors so a bad token / missing intent fails fast with
    # a clear message instead of an opaque traceback that crash-loops on Railway.
    try:
        async with bot:
            await bot.start(cfg.discord_bot_token)
    except discord.LoginFailure:
        log.error(
            "Discord login failed: DISCORD_BOT_TOKEN is invalid. Reset it in the "
            "Developer Portal and update the variable before redeploying — "
            "retrying with a bad token will not help."
        )
        raise SystemExit(1) from None
    except discord.PrivilegedIntentsRequired:
        log.error(
            "Message Content intent is not enabled. Turn it on in the Developer "
            "Portal (Bot -> Privileged Gateway Intents) before redeploying."
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    asyncio.run(main())

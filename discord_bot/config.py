"""Bot configuration.

Reads settings from the environment. Locally, python-dotenv loads
discord_bot/.env; on Railway the same names are injected as real env vars (no
.env present, which is correct). Fail loud on a missing required var — a bot
that boots half-configured and dies on first command is harder to diagnose than
one that refuses to start with a clear message.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env that sits next to this file (local dev only; absent on Railway).
load_dotenv(Path(__file__).resolve().parent / ".env")

_REQUIRED = ("DISCORD_BOT_TOKEN", "DISCORD_GUILD_ID", "GITHUB_PAT")


@dataclass(frozen=True)
class Config:
    discord_bot_token: str
    discord_guild_id: int
    github_pat: str
    github_owner: str
    github_repo: str
    github_ref: str
    command_prefix: str


def load_config() -> Config:
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Set them in discord_bot/.env (local) or as Railway service "
            "variables (production)."
        )
    return Config(
        discord_bot_token=os.environ["DISCORD_BOT_TOKEN"],
        discord_guild_id=int(os.environ["DISCORD_GUILD_ID"]),
        github_pat=os.environ["GITHUB_PAT"],
        github_owner=os.environ.get("GITHUB_OWNER", "benjamininja"),
        github_repo=os.environ.get(
            "GITHUB_REPO", "Python-PowerBI-DynastyFantasyFootball"
        ),
        github_ref=os.environ.get("GITHUB_REF", "main"),
        command_prefix=os.environ.get("DISCORD_COMMAND_PREFIX", "!"),
    )

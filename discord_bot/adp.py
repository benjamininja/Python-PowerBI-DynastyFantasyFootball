"""The `adp` command — Fantrax average-draft-position board.

ADP is fundamentally draft order, not a per-position ranking, so this is one
overall board sorted by `adp` ascending (optionally filtered to a position),
rather than the per-position shape of `rankings`. Each player is shown over two
lines so all the requested context fits without a row too wide for mobile:

     1.44  Bijan Robinson      RB · ATL · 23yo
           $19.2M · ovr 4 · 🏈 Big L (R)

The owner line is a draft-prep overlay: the player's owner in OUR league, joined
from the ledger. It is blank for anyone not yet drafted (only one division has
drafted so far), and fills in as more teams draft.
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

log = logging.getLogger("league-bot.adp")

_ADP_PATH = "data/fact_fantrax_adp.parquet"
_PLAYERS_PATH = "data/dim_nfl_players.parquet"
_OWNERSHIP_PATH = "data/fact_fantasy_teams.parquet"
_TEAMS_PATH = "data/dim_fantasy_teams.parquet"

_DEFAULT_LIMIT = 15
_MAX_LIMIT = 50
_PLAYERS_PER_FIELD = 10  # two lines each → ~10 keeps a field well under 1024 chars


def _owner_map(cfg: Config) -> dict[str, str]:
    """gsis_id -> owning team name (our league). Empty if the ledger is empty."""
    try:
        owned = fetch_parquet(_OWNERSHIP_PATH, cfg)
        teams = fetch_parquet(_TEAMS_PATH, cfg)
    except Exception:
        log.warning("owner overlay unavailable; rendering adp without it", exc_info=True)
        return {}
    if owned.empty or "gsis_id" not in owned.columns:
        return {}
    merged = owned.merge(teams[["team_key", "team_name"]], on="team_key", how="left")
    merged = merged[merged["gsis_id"].notna()]
    return dict(zip(merged["gsis_id"], merged["team_name"]))


def _entry_lines(row: pd.Series, owner: str) -> list[str]:
    adp = f"{float(row['adp']):5.2f}" if not pd.isna(row["adp"]) else "  ?  "
    name = render.safe_str(row["player_name"], 20)
    pos = render.safe_str(row["position"], 4) or "?"
    team = render.safe_str(row["nfl_team"], 3) or "FA"
    age = "" if pd.isna(row["age"]) else f"{int(row['age'])}yo"
    head = f"{adp}  {name:<20} {pos} · {team}" + (f" · {age}" if age else "")
    ovr = render.fmt_int(row["overall_rank"], width=1)
    salary = render.fmt_money(row["salary"])
    owner_part = f" · 🏈 {owner[:18]}" if owner else ""
    detail = f"       {salary} · ovr {ovr}{owner_part}"
    return [head, detail]


def build_adp_embeds(
    cfg: Config, position: str | None = None, limit: int = _DEFAULT_LIMIT,
) -> list[discord.Embed]:
    limit = max(1, min(limit, _MAX_LIMIT))

    adp = fetch_parquet(_ADP_PATH, cfg)
    if adp.empty:
        raise CommandError("No ADP data available yet.")

    # Latest capture only — fact_fantrax_adp is a manual-cadence time series.
    latest = adp["capture_date"].max()
    adp = adp[adp["capture_date"] == latest].copy()

    # Position group for grouping/filtering comes from the player registry (the
    # source's own position_raw carries messy IDP multi-tokens like "DL,LB").
    # Left-join so a player missing from the registry still appears, falling back
    # to position_raw.
    players = fetch_parquet(_PLAYERS_PATH, cfg)[["gsis_id", "position_group"]]
    adp = adp.merge(players, on="gsis_id", how="left")
    adp["position"] = adp["position_group"].fillna(adp["position_raw"])

    if position:
        position = position.upper()
        match = adp[adp["position"].str.upper() == position]
        if match.empty:
            avail = ", ".join(sorted(adp["position"].dropna().str.upper().unique()))
            raise CommandError(f"No **{position}** in ADP. Positions: {avail}.")
        adp = match

    board = adp.sort_values("adp").head(limit).reset_index(drop=True)
    owners = _owner_map(cfg)

    # Chunk the two-line entries into fields so each stays under the 1024 cap.
    fields: list[tuple[str, str]] = []
    for start in range(0, len(board), _PLAYERS_PER_FIELD):
        chunk = board.iloc[start : start + _PLAYERS_PER_FIELD]
        lines: list[str] = []
        for _, row in chunk.iterrows():
            lines.extend(_entry_lines(row, owners.get(row["gsis_id"], "")))
        name = f"#{start + 1}–{start + len(chunk)}"
        fields.append((name, render.mono_block(lines)))

    scope = f" — {position}" if position else ""
    latest_label = f"{pd.Timestamp(latest):%Y-%m-%d}"
    embeds = render.paginate_fields(
        title=f"Fantrax ADP{scope}",
        fields=fields,
        footer=f"Snapshot: {latest_label} · owner = your league",
    )
    if not embeds:
        raise CommandError("No ADP to show.")
    return embeds


class Adp(commands.Cog):
    def __init__(self, bot: commands.Bot, cfg: Config):
        self.bot = bot
        self.cfg = cfg

    @commands.hybrid_command(
        name="adp",
        description="Fantrax ADP board with league-ownership overlay (private unless you share).",
    )
    @discord.app_commands.describe(
        position="Filter to one position (e.g. QB, LB). Omit for the overall board.",
        limit="Players to show (default 15, max 50).",
        share="Post the result publicly in the channel (default: private to you).",
    )
    async def adp(
        self,
        ctx: commands.Context,
        position: str | None = None,
        limit: int = _DEFAULT_LIMIT,
        share: bool = False,
    ) -> None:
        await respond_with_embeds(ctx, share, build_adp_embeds, self.cfg, position, limit)


async def setup_adp(bot: commands.Bot, cfg: Config) -> None:
    await bot.add_cog(Adp(bot, cfg))

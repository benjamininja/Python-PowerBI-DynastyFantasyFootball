"""The `player` command — a curated single-player card.

A player carries dozens of EAV rows across sources/formats; this distils them to
one card: dynasty ranks + value per source (for the relevant format), ADP
context, and the player's contract in our league if owned. Name resolution is
self-contained (the bot can't import the ETL helpers): normalize, match on the
registry, and on a collision (e.g. two Josh Allens) ask the user to be specific.
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

log = logging.getLogger("league-bot.player")

_METRICS_PATH = "data/fact_dynasty_ranking_metrics.parquet"
_PLAYERS_PATH = "data/dim_nfl_players.parquet"
_ADP_PATH = "data/fact_fantrax_adp.parquet"
_OWNERSHIP_PATH = "data/fact_fantasy_teams.parquet"
_TEAMS_PATH = "data/dim_fantasy_teams.parquet"

# position_group → the format whose ranks make sense for that player. Defense is
# only ranked in IDP; offense defaults to Superflex (the league's primary board).
_DEFENSE = {"DL", "LB", "DB"}
_DEFAULT_OFFENSE_FORMAT = "SF"

# Source → (positional_rank key, overall_rank key, value key | None).
_SOURCE_KEYS = {
    "KTC": ("ktc_positional_rank", "ktc_overall_rank", "value"),
    "DynastySharks": ("ds_positional_rank", "ds_overall_rank", "ds_value"),
    "FantasyPros": ("fp_positional_rank", "fp_overall_rank", None),
}
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _norm(name: str) -> str:
    name = re.sub(r"[^a-z0-9 ]", "", name.lower())
    return " ".join(t for t in name.split() if t not in _SUFFIXES)


def _resolve_player(players: pd.DataFrame, query: str) -> pd.Series:
    q = _norm(query)
    if not q:
        raise CommandError("Give me a player name, e.g. `/player Bijan Robinson`.")
    norm = players["display_name"].fillna("").map(_norm)
    exact = players[norm == q]
    hits = exact if not exact.empty else players[norm.str.contains(re.escape(q))]
    if hits.empty:
        raise CommandError(f"No player matches **{query}**.")
    if len(hits) > 1:
        listed = ", ".join(
            f"{r.display_name} ({render.safe_str(r.position_group)}"
            f" {render.safe_str(r.team_abbr)})"
            for r in hits.head(8).itertuples()
        )
        more = " …" if len(hits) > 8 else ""
        raise CommandError(f"Multiple players match **{query}**: {listed}{more}. Be more specific.")
    return hits.iloc[0]


def _age(birth_date: object) -> str:
    if pd.isna(birth_date):
        return ""
    days = (pd.Timestamp.now() - pd.Timestamp(birth_date)).days
    return f"{days // 365}yo" if days > 0 else ""


def _metric_lookup(rows: pd.DataFrame) -> dict[tuple[str, str], float]:
    return {
        (r.source_name, r.metric_key): r.metric_num
        for r in rows.itertuples()
        if not pd.isna(r.metric_num)
    }


def _dynasty_lines(metrics: dict, fmt: str) -> list[str]:
    lines: list[str] = []
    for source, (pos_key, ovr_key, val_key) in _SOURCE_KEYS.items():
        pos = metrics.get((source, pos_key))
        ovr = metrics.get((source, ovr_key))
        if pos is None and ovr is None:
            continue
        parts = [f"{source:<13}"]
        if pos is not None:
            parts.append(f"pos {int(pos)}")
        if ovr is not None:
            parts.append(f"ovr {int(ovr)}")
        if val_key and (val := metrics.get((source, val_key))) is not None:
            parts.append(f"val {int(val)}")
        lines.append(" · ".join(parts))
    return lines or ["No dynasty ranks for this format."]


def build_player_embeds(cfg: Config, name: str) -> list[discord.Embed]:
    players = fetch_parquet(_PLAYERS_PATH, cfg)
    p = _resolve_player(players, name)
    gsis = p["gsis_id"]
    pos_group = render.safe_str(p["position_group"]) or "?"
    fmt = "IDP" if pos_group in _DEFENSE else _DEFAULT_OFFENSE_FORMAT

    # Dynasty block — this player's rows for the chosen format, latest snapshot.
    eav = fetch_parquet(_METRICS_PATH, cfg)
    mine = eav[(eav["gsis_id"] == gsis) & (eav["format"] == fmt)]
    if not mine.empty:
        mine = mine[mine["snapshot_date"] == mine["snapshot_date"].max()]
    metrics = _metric_lookup(mine)

    # ADP block — composite (dynasty) + Fantrax (redraft) where available.
    composite_adp = metrics.get(("Composite", "composite_adp"))
    adp_df = fetch_parquet(_ADP_PATH, cfg)
    fantrax_adp = None
    if not adp_df.empty:
        latest = adp_df[adp_df["capture_date"] == adp_df["capture_date"].max()]
        hit = latest[latest["gsis_id"] == gsis]
        if not hit.empty and not pd.isna(hit.iloc[0]["adp"]):
            fantrax_adp = float(hit.iloc[0]["adp"])

    title = f"{p['display_name']} — {pos_group} · {render.safe_str(p['team_abbr']) or 'FA'}"
    age = _age(p.get("birth_date"))
    bits = [f"Age {age}"] if age else []
    if not pd.isna(p.get("years_of_experience")):
        bits.append(f"exp {int(p['years_of_experience'])}")
    if not pd.isna(p.get("college_name")):
        bits.append(render.safe_str(p["college_name"]))
    identity = " · ".join(bits) or "—"

    fields: list[tuple[str, str]] = [(f"Dynasty ({fmt})", render.mono_block(_dynasty_lines(metrics, fmt)))]
    adp_lines = []
    if composite_adp is not None:
        adp_lines.append(f"Composite ADP  {composite_adp:.1f}")
    if fantrax_adp is not None:
        adp_lines.append(f"Fantrax ADP    {fantrax_adp:.2f}")
    if adp_lines:
        fields.append(("ADP", render.mono_block(adp_lines)))

    league_lines = _league_lines(cfg, gsis)
    if league_lines:
        fields.append(("Your league", render.mono_block(league_lines)))

    embeds = render.paginate_fields(title=title, fields=fields, footer=identity)
    return embeds


def _league_lines(cfg: Config, gsis: str) -> list[str]:
    try:
        owned = fetch_parquet(_OWNERSHIP_PATH, cfg)
        teams = fetch_parquet(_TEAMS_PATH, cfg)
    except Exception:
        log.warning("league overlay unavailable for player card", exc_info=True)
        return []
    if owned.empty or "gsis_id" not in owned.columns:
        return []
    row = owned[owned["gsis_id"] == gsis]
    if row.empty:
        return ["Not rostered in your league."]
    r = row.iloc[0]
    tname = teams.loc[teams["team_key"] == r["team_key"], "team_name"]
    owner = tname.iloc[0] if not tname.empty else r["team_key"]
    return [
        f"Owner    {render.safe_str(owner, 24)}",
        f"Contract {render.fmt_money(r.get('contract_value'))}"
        f" · cap {render.fmt_money(r.get('cap_hit'))}"
        f" · {render.safe_str(r.get('status')) or '—'}",
    ]


class Player(commands.Cog):
    def __init__(self, bot: commands.Bot, cfg: Config):
        self.bot = bot
        self.cfg = cfg

    @commands.hybrid_command(
        name="player",
        description="A player's dynasty ranks, ADP, and league contract (private unless you share).",
    )
    @discord.app_commands.describe(
        name="Player name (e.g. Bijan Robinson).",
        share="Post the result publicly in the channel (default: private to you).",
    )
    async def player(
        self, ctx: commands.Context, *, name: str, share: bool = False,
    ) -> None:
        await respond_with_embeds(ctx, share, build_player_embeds, self.cfg, name)


async def setup_player(bot: commands.Bot, cfg: Config) -> None:
    await bot.add_cog(Player(bot, cfg))

"""Embed rendering helpers shared by every command.

Pure presentation: turn prepared `(name, value)` fields into as many Discord
embeds as the hard limits require, and format individual cells null-safely. Knows
nothing about queries, data sources, or privacy — that keeps the command modules
free of duplicated layout code and keeps the limit accounting in one place.
"""

from __future__ import annotations

import discord
import pandas as pd

# Discord hard limits. The 6000 total covers title + every field + footer;
# `len(discord.Embed)` reports that exact total, so we measure against it
# directly instead of hand-summing a subset of the parts.
MAX_FIELDS_PER_EMBED = 25
EMBED_TOTAL_LIMIT = 6000
MAX_FIELD_VALUE = 1024

EMBED_COLOR = 0x5865F2


def mono_block(lines: list[str]) -> str:
    """Join lines into a monospace code block, trimmed to fit one embed field."""
    block = "```\n" + "\n".join(lines) + "\n```"
    if len(block) > MAX_FIELD_VALUE:  # defensive: a single field caps at 1024
        block = block[: MAX_FIELD_VALUE - 4] + "\n```"
    return block


def paginate_fields(
    title: str,
    fields: list[tuple[str, str]],
    *,
    footer: str | None = None,
    color: int = EMBED_COLOR,
) -> list[discord.Embed]:
    """Pack `(name, value)` fields into as many embeds as the limits require.

    Rolls to a new embed only once the current one already holds a field — a
    single field always fits (its value is capped at 1024), so this can never
    spin creating empty embeds.
    """
    embeds: list[discord.Embed] = []

    def _new() -> discord.Embed:
        e = discord.Embed(title=title, color=color)
        if footer:
            e.set_footer(text=footer)
        return e

    current = _new()
    for name, value in fields:
        if current.fields and (
            len(current.fields) >= MAX_FIELDS_PER_EMBED
            or len(current) + len(name) + len(value) > EMBED_TOTAL_LIMIT
        ):
            embeds.append(current)
            current = _new()
        current.add_field(name=name, value=value, inline=False)
    if current.fields:
        embeds.append(current)
    return embeds


def fmt_int(value: object, width: int = 2) -> str:
    # Degrade a missing / non-numeric cell to "?" rather than crash the row.
    try:
        return f"{int(value):>{width}}"
    except (TypeError, ValueError):
        return "?".rjust(width)


def fmt_money(value: object) -> str:
    # Fantrax salaries run into the tens of millions; abbreviate for narrow rows.
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.0f}"


def safe_str(value: object, width: int | None = None) -> str:
    # `x or ''` is wrong for pandas missing values: NaN is truthy and pd.NA
    # raises in a boolean test. Use pd.isna so a missing cell renders blank.
    s = "" if pd.isna(value) else str(value)
    return s[:width] if width else s

"""Privacy-aware delivery + the command-execution wrapper.

Every command routes its reply through here so the private-by-default policy is
implemented exactly once. The hard constraint that shapes this: ephemeral is
interaction-only — it works for slash responses, never for normal (prefix)
messages. So privacy is delivered differently per surface:

- Slash    -> ephemeral result + an opt-in "Post publicly" button.
- Prefix in a public channel -> DM the requester (📬 react, no data in-channel).
- Prefix in a DM            -> reply in place (already private).

Public only on explicit opt-in (`share=True`, or the button). Keeping this in one
place is the whole point: new commands reuse `respond_with_embeds` instead of
re-deciding privacy ad hoc, so they can't drift into a leakier implementation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

import discord
from discord.ext import commands

log = logging.getLogger("league-bot.delivery")


class CommandError(Exception):
    """User-facing problem (bad arg, no data) — its message is safe to show."""


class ShareView(discord.ui.View):
    """A 'Post publicly' button attached to a private (ephemeral) result.

    Lets the requester opt into making their otherwise-private reply public with
    one deliberate click — the explicit share gate for the slash path. Restricted
    to the original requester so nobody else can publish someone's private query.
    """

    def __init__(self, embeds: list[discord.Embed], author_id: int):
        super().__init__(timeout=300)  # button stops working after 5 min
        self._embeds = embeds
        self._author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._author_id:
            await interaction.response.send_message(
                "Only the person who ran the command can post it publicly.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Post publicly", style=discord.ButtonStyle.primary, emoji="📢")
    async def post_publicly(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        try:
            # Attribute the share so a public post is never anonymous.
            await interaction.channel.send(
                content=f"📢 Shared by {interaction.user.mention}",
                embed=self._embeds[0],
            )
            for embed in self._embeds[1:]:
                await interaction.channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to post in this channel.", ephemeral=True
            )
            return
        button.disabled = True
        button.label = "Posted publicly"
        await interaction.response.edit_message(view=self)  # retire the button
        self.stop()


async def respond_with_embeds(
    ctx: commands.Context,
    share: bool,
    build_fn: Callable[..., list[discord.Embed]],
    *build_args: object,
) -> None:
    """Run a (sync, cache-missable) embed builder and deliver it, privately by default.

    Defers the slash interaction up front (fetch + parse can exceed the 3s ack
    window) and runs the builder off the event loop so a slow GitHub response
    can't block the gateway heartbeat. CommandError messages are shown to the
    user; any other exception is logged in full and replaced with a generic
    notice so a stack trace never leaks into the channel.
    """
    is_slash = ctx.interaction is not None
    if is_slash:
        # Ephemerality is fixed at defer time, so decide it up front.
        await ctx.defer(ephemeral=not share)
    try:
        embeds = await asyncio.to_thread(build_fn, *build_args)
    except CommandError as e:
        await deliver_text(ctx, is_slash, share, str(e))
        return
    except Exception:
        log.exception("%s build failed", getattr(build_fn, "__name__", build_fn))
        await deliver_text(
            ctx, is_slash, share,
            "Couldn't reach the data right now — try again shortly.",
        )
        return
    await deliver_embeds(ctx, is_slash, share, embeds)


async def deliver_embeds(
    ctx: commands.Context, is_slash: bool, share: bool, embeds: list[discord.Embed],
) -> None:
    if share:
        # Explicit public — post in the channel (slash defer was non-ephemeral).
        for embed in embeds:
            await ctx.send(embed=embed)
        return
    if is_slash:
        # Private ephemeral result + a button to opt into posting publicly.
        view = ShareView(embeds, ctx.author.id)
        last = len(embeds) - 1
        for i, embed in enumerate(embeds):
            await ctx.send(embed=embed, ephemeral=True, view=view if i == last else None)
        return
    if ctx.guild is None:
        # Prefix in a DM — the channel is already private.
        for embed in embeds:
            await ctx.send(embed=embed)
        return
    # Prefix in a public channel can't be ephemeral → DM the requester.
    try:
        for embed in embeds:
            await ctx.author.send(embed=embed)
    except discord.Forbidden:
        await ctx.reply(
            "Your DMs are closed, so I can't send this privately. Enable DMs from "
            "server members, use the slash command for a private result, or pass "
            "`share: true` to post it here publicly."
        )
        return
    await _react_dm_sent(ctx)


async def deliver_text(
    ctx: commands.Context, is_slash: bool, share: bool, content: str,
) -> None:
    # Same privacy routing as embeds. (Error/notice text carries no data, so the
    # closed-DM fallback can safely show it in-channel.)
    if share or is_slash:
        await ctx.send(content, ephemeral=is_slash and not share)
        return
    if ctx.guild is None:
        await ctx.send(content)
        return
    try:
        await ctx.author.send(content)
    except discord.Forbidden:
        await ctx.reply(content)
        return
    await _react_dm_sent(ctx)


async def _react_dm_sent(ctx: commands.Context) -> None:
    # Signal "check your DMs" without echoing any data into the channel.
    try:
        await ctx.message.add_reaction("📬")
    except discord.HTTPException:
        pass

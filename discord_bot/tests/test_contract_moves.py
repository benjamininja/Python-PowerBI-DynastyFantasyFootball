"""Offline tests for `/contract-moves` (#545): the formatter, the builders and the
private-by-default delivery. No Discord round-trip and no network: the cog's
`fetch_parquet` is patched to a frame built here, or to the repo's local parquet.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pandas as pd
import pytest
from discord.ext import commands
from discord.ext.commands.view import StringView
from openpyxl import load_workbook

_BOT_DIR = Path(__file__).resolve().parent.parent
_DATA = _BOT_DIR.parent / "data"
sys.path.insert(0, str(_BOT_DIR))

import contract_cmd  # noqa: E402
import contract_moves as cm  # noqa: E402
from config import Config  # noqa: E402
from delivery import CommandError, FileReply, ShareView, respond_with_embeds  # noqa: E402

CFG = Config(
    discord_bot_token="x", discord_guild_id=1, github_pat="x",
    github_owner="o", github_repo="r", github_ref="main", command_prefix="!",
)

TEAMS = pd.DataFrame({
    "team_key": ["A01", "A02", "B01"],
    "team_name": ["Alpha", "Apex", "Bravo"],
    "team_abbr": ["ALP", "APX", "BRV"],
})

HEADERS = ["Team", "Division", "Player", "Pos", "NFL Team", "List", "Contract now",
           "Move to", "Why", "NFL games", "Roster slot", "Salary", "Status"]


def _row(list_name: str, conference: str, team_key: str, player: str, **kw) -> dict:
    row = {
        "list_name": list_name, "conference": conference, "division": "East",
        "team_key": team_key, "scorer_id": f"s-{player}", "gsis_id": f"g-{player}",
        "player_name": player, "position": "WR", "nfl_team": "AAA",
        "contract_now": "FA", "move_to": "Keep (X next season), or let go at season's end",
        "reason": "FA pickup: keep it by the re-sign deadline, or it returns to the pool at season's end",
        "nfl_games": 40, "roster_slot": "active", "salary": 1_500_000.0, "status": "Due now",
    }
    row.update(kw)
    return row


def _moves(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=list(_row("decision", "A", "A01", "x")))
    frame["nfl_games"] = frame["nfl_games"].astype("Int64")
    frame["salary"] = frame["salary"].astype("float64")
    return frame


MOVES = _moves([
    _row("decision", "A", "A01", "Zed Zee"),
    _row("decision", "A", "A01", "Amy Ant", status="Due within 7 days"),
    _row("decision", "A", "A02", "Cal Cox", contract_now="2nd"),
    _row("decision", "B", "B01", "Bob Bee"),
    _row("minor-to-1st", "A", "A01", "Dee Dot", contract_now="Minor", move_to="1st"),
    _row("minor-to-1st", "B", "B01", "Eve Elm", contract_now="Minor", move_to="1st"),
    _row("expiring", "B", "B01", "Fay Fox", contract_now="X", move_to="Tag or expire"),
])


def _patch(monkeypatch, moves: pd.DataFrame = MOVES, teams: pd.DataFrame = TEAMS) -> None:
    def fetch(path: str, _cfg: Config) -> pd.DataFrame:
        return moves if "fact_contract_move" in path else teams
    monkeypatch.setattr(contract_cmd, "fetch_parquet", fetch)


def _book(reply: FileReply):
    return load_workbook(BytesIO(reply.data))


def _fields(embeds) -> str:
    return "\n".join(f.value for e in embeds for f in e.fields)


def _check_limits(embeds) -> None:
    assert embeds
    for e in embeds:
        assert len(e) <= 6000
        assert len(e.fields) <= 25
        for f in e.fields:
            assert len(f.value) <= 1024


class TestXlsx:
    def test_one_tab_per_conference_each_an_excel_table_with_filters(self, monkeypatch):
        _patch(monkeypatch)
        book = _book(contract_cmd.build_xlsx_reply(CFG, "decision"))
        assert book.sheetnames == ["Conference A", "Conference B"]
        for ws in book.worksheets:
            assert len(ws.tables) == 1
            table = next(iter(ws.tables.values()))
            assert table.autoFilter is not None
            assert table.ref.startswith("A1:M")

    def test_columns_are_in_the_tickets_order(self, monkeypatch):
        _patch(monkeypatch)
        book = _book(contract_cmd.build_xlsx_reply(CFG, "decision"))
        for ws in book.worksheets:
            assert [c.value for c in ws[1]] == HEADERS

    def test_one_row_per_copy_by_conference_in_team_then_player_order(self, monkeypatch):
        _patch(monkeypatch)
        book = _book(contract_cmd.build_xlsx_reply(CFG, "decision"))
        a, b = book["Conference A"], book["Conference B"]
        assert [r[2].value for r in a.iter_rows(min_row=2)] == ["Amy Ant", "Zed Zee", "Cal Cox"]
        assert [r[0].value for r in a.iter_rows(min_row=2)] == ["Alpha", "Alpha", "Apex"]
        assert [r[2].value for r in b.iter_rows(min_row=2)] == ["Bob Bee"]

    def test_cells_hold_the_published_values(self, monkeypatch):
        _patch(monkeypatch)
        ws = _book(contract_cmd.build_xlsx_reply(CFG, "minor-to-1st"))["Conference A"]
        values = [c.value for c in ws[2]]
        assert values[HEADERS.index("List")] == "Minor → 1st"
        assert values[HEADERS.index("Contract now")] == "Minor"
        assert values[HEADERS.index("Move to")] == "1st"
        assert values[HEADERS.index("NFL games")] == 40
        assert values[HEADERS.index("Salary")] == 1_500_000
        assert ws.cell(row=2, column=HEADERS.index("Salary") + 1).number_format == "$#,##0"

    def test_missing_cells_are_blank_never_nan(self, monkeypatch):
        gappy = _moves([_row("decision", "A", "A01", "Gap Guy", position=None, nfl_team=None,
                             move_to=None, reason=float("nan"), nfl_games=None, salary=float("nan"))])
        _patch(monkeypatch, gappy)
        ws = _book(contract_cmd.build_xlsx_reply(CFG, "decision"))["Conference A"]
        for header in ("Pos", "NFL Team", "Move to", "Why", "NFL games", "Salary"):
            assert ws.cell(row=2, column=HEADERS.index(header) + 1).value in (None, "")

    def test_an_infinite_number_is_blank_like_a_missing_one(self, monkeypatch):
        odd = _moves([_row("decision", "A", "A01", "Inf Ivy", salary=float("inf"), nfl_games=3)])
        _patch(monkeypatch, odd)
        ws = _book(contract_cmd.build_xlsx_reply(CFG, "decision"))["Conference A"]
        assert ws.cell(row=2, column=HEADERS.index("Salary") + 1).value is None
        assert ws.cell(row=2, column=HEADERS.index("NFL games") + 1).value == 3
        assert cm.number(float("-inf")) is None

    def test_a_conference_with_no_rows_keeps_its_tab_with_a_header(self, monkeypatch):
        only_a = MOVES[MOVES["conference"] == "A"]
        _patch(monkeypatch, only_a)
        book = _book(contract_cmd.build_xlsx_reply(CFG, "decision"))
        assert book.sheetnames == ["Conference A", "Conference B"]
        assert [c.value for c in book["Conference B"][1]] == HEADERS
        assert book["Conference B"].max_row == 1

    def test_a_team_in_neither_conference_is_not_dropped(self, monkeypatch):
        odd = _moves([_row("decision", "A", "A01", "Amy Ant"),
                      _row("decision", None, "A02", "Lost Lou")])
        _patch(monkeypatch, odd)
        book = _book(contract_cmd.build_xlsx_reply(CFG, "decision"))
        assert book.sheetnames == ["Conference A", "Conference B", "Unassigned"]
        assert book["Unassigned"]["C2"].value == "Lost Lou"

    def test_the_reply_is_a_file_with_a_short_line(self, monkeypatch):
        _patch(monkeypatch)
        reply = contract_cmd.build_xlsx_reply(CFG, "decision")
        assert reply.filename == "contract-moves-decision.xlsx"
        assert reply.content.startswith("Contract moves — Decision: 4 rows.")
        assert "Due now 3" in reply.content and "Due within 7 days 1" in reply.content


class TestTable:
    def test_the_three_lists_each_show_only_their_own_rows(self, monkeypatch):
        _patch(monkeypatch)
        decision = _fields(contract_cmd.build_table_embeds(CFG, "decision"))
        minor = _fields(contract_cmd.build_table_embeds(CFG, "minor-to-1st"))
        expiring = _fields(contract_cmd.build_table_embeds(CFG, "expiring"))
        assert all(n in decision for n in ("Zed Zee", "Amy Ant", "Cal Cox", "Bob Bee"))
        assert "Dee Dot" not in decision and "Fay Fox" not in decision
        assert "Dee Dot" in minor and "Eve Elm" in minor and "Zed Zee" not in minor
        assert "Fay Fox" in expiring and "Eve Elm" not in expiring

    def test_the_lines_carry_the_six_columns_in_order(self, monkeypatch):
        _patch(monkeypatch)
        embeds = contract_cmd.build_table_embeds(CFG, "minor-to-1st")
        header, first = embeds[0].fields[0].value.split("\n")[1:3]
        assert header.split() == ["Team", "Player", "Pos", "Contract", "now", "Move", "to", "Status"]
        assert first.split()[:2] == ["Alpha", "Dee"]
        assert first.split()[-2:] == ["Due", "now"]
        assert "Minor" in first and "1st" in first

    def test_title_and_footer_count_the_rows_by_status(self, monkeypatch):
        _patch(monkeypatch)
        embed = contract_cmd.build_table_embeds(CFG, "decision")[0]
        assert embed.title == "Contract moves — Decision (4)"
        assert embed.footer.text == "Due now 3 · Due within 7 days 1"

    def test_the_team_filter_resolves_by_abbreviation_or_name(self, monkeypatch):
        _patch(monkeypatch)
        for query in ("ALP", "alpha"):
            embeds = contract_cmd.build_table_embeds(CFG, "decision", query)
            body = _fields(embeds)
            assert "Zed Zee" in body and "Amy Ant" in body
            assert "Cal Cox" not in body and "Bob Bee" not in body
            assert embeds[0].title == "Contract moves — Decision (2) · Alpha"

    def test_the_team_filter_applies_to_the_xlsx_too(self, monkeypatch):
        _patch(monkeypatch)
        book = _book(contract_cmd.build_xlsx_reply(CFG, "decision", "BRV"))
        assert [r[2].value for r in book["Conference B"].iter_rows(min_row=2)] == ["Bob Bee"]
        assert book["Conference A"].max_row == 1

    def test_an_unknown_team_is_a_user_facing_error(self, monkeypatch):
        _patch(monkeypatch)
        with pytest.raises(CommandError, match="No team matches"):
            contract_cmd.build_table_embeds(CFG, "decision", "zzzz")

    def test_a_blank_team_means_no_filter(self, monkeypatch):
        _patch(monkeypatch)
        assert len(contract_cmd.build_table_embeds(CFG, "decision", "  ")[0].title) > 0
        assert "(4)" in contract_cmd.build_table_embeds(CFG, "decision", "  ")[0].title

    def test_missing_cells_render_blank_never_nan(self, monkeypatch):
        gappy = _moves([_row("decision", "A", "A01", "Gap Guy", position=None, move_to=float("nan"),
                             contract_now=None)])
        _patch(monkeypatch, gappy)
        body = _fields(contract_cmd.build_table_embeds(CFG, "decision"))
        assert "Gap Guy" in body
        assert "nan" not in body.lower() and "None" not in body and "<NA>" not in body

    def test_a_long_list_splits_inside_discords_limits_and_loses_no_row(self, monkeypatch):
        many = _moves([
            _row("decision", "A" if i % 2 else "B", "A01" if i % 2 else "B01", f"Player Number {i:03d}",
                 move_to="Keep (X next season), or let go at season's end" * 2)
            for i in range(400)
        ])
        _patch(monkeypatch, many)
        embeds = contract_cmd.build_table_embeds(CFG, "decision")
        assert len(embeds) > 1
        _check_limits(embeds)
        body = _fields(embeds)
        assert all(f"Player Number {i:03d}" in body for i in range(400))
        for embed in embeds:
            for f in embed.fields:
                assert f.value.startswith("```\nTeam") and f.value.endswith("\n```")
        assert embeds[0].title == "Contract moves — Decision (400)"

    def test_every_chunk_repeats_the_header_and_stays_under_the_field_cap(self):
        rows = cm.prepare(_moves([_row("decision", "A", "A01", f"P{i:03d}") for i in range(120)]), TEAMS)
        chunks = cm.table_chunks(rows)
        assert len(chunks) > 1
        assert sum(len(c) - 1 for c in chunks) == 120
        for chunk in chunks:
            assert chunk[0].startswith("Team")
            assert len("```\n" + "\n".join(chunk) + "\n```") <= 1024


class TestEmptyList:
    def test_an_empty_list_says_nothing_is_due(self, monkeypatch):
        _patch(monkeypatch, MOVES[MOVES["list_name"] != "expiring"])
        for build in (contract_cmd.build_table_embeds, contract_cmd.build_xlsx_reply):
            with pytest.raises(CommandError) as err:
                build(CFG, "expiring")
            assert str(err.value) == "Nothing due on the Expiring list."

    def test_a_published_table_with_no_rows_is_an_empty_list(self, monkeypatch):
        _patch(monkeypatch, MOVES.iloc[0:0])
        with pytest.raises(CommandError, match="Nothing due on the Decision list"):
            contract_cmd.build_table_embeds(CFG, "decision")

    def test_a_team_with_nothing_due_is_named(self, monkeypatch):
        _patch(monkeypatch)
        with pytest.raises(CommandError) as err:
            contract_cmd.build_table_embeds(CFG, "expiring", "ALP")
        assert str(err.value) == "Nothing due for Alpha on the Expiring list."

    def test_before_its_window_opens_the_message_says_when(self):
        message = cm.empty_message("expiring", opens=date(2026, 12, 31), today=date(2026, 11, 15))
        assert message == "Nothing due yet. Expiring contracts appear from 2026-12-31."

    def test_once_the_window_is_open_it_says_only_that_nothing_is_due(self):
        message = cm.empty_message("expiring", opens=date(2026, 12, 31), today=date(2026, 12, 31))
        assert message == "Nothing due on the Expiring list."


class FakeCtx:
    def __init__(self, slash: bool = True, guild: bool = True):
        self.interaction = object() if slash else None
        self.guild = object() if guild else None
        self.author = SimpleNamespace(id=7, send=AsyncMock())
        self.defer, self.send, self.reply = AsyncMock(), AsyncMock(), AsyncMock()
        self.message = SimpleNamespace(add_reaction=AsyncMock())


def _run(ctx: FakeCtx, share: bool, build, *args) -> None:
    asyncio.run(respond_with_embeds(ctx, share, build, *args))


class TestPrivacy:
    def test_a_slash_xlsx_is_ephemeral_with_a_share_button(self, monkeypatch):
        _patch(monkeypatch)
        ctx = FakeCtx()
        _run(ctx, False, contract_cmd.build_reply, CFG, "decision", "xlsx", None)
        ctx.defer.assert_awaited_once_with(ephemeral=True)
        (content,), kwargs = ctx.send.await_args
        assert kwargs["ephemeral"] is True
        assert isinstance(kwargs["file"], discord.File)
        assert kwargs["file"].filename == "contract-moves-decision.xlsx"
        assert isinstance(kwargs["view"], ShareView)
        assert content.startswith("Contract moves — Decision")

    def test_a_slash_table_is_ephemeral_with_a_share_button(self, monkeypatch):
        _patch(monkeypatch)
        ctx = FakeCtx()
        _run(ctx, False, contract_cmd.build_reply, CFG, "decision", "table", None)
        ctx.defer.assert_awaited_once_with(ephemeral=True)
        assert all(c.kwargs["ephemeral"] is True for c in ctx.send.await_args_list)
        assert isinstance(ctx.send.await_args_list[-1].kwargs["view"], ShareView)

    def test_share_true_posts_in_the_channel(self, monkeypatch):
        _patch(monkeypatch)
        for fmt in ("xlsx", "table"):
            ctx = FakeCtx()
            _run(ctx, True, contract_cmd.build_reply, CFG, "decision", fmt, None)
            ctx.defer.assert_awaited_once_with(ephemeral=False)
            ctx.send.assert_awaited()
            assert all("ephemeral" not in c.kwargs for c in ctx.send.await_args_list)
            ctx.author.send.assert_not_awaited()

    def test_a_prefix_command_in_a_public_channel_dms_the_requester(self, monkeypatch):
        _patch(monkeypatch)
        for fmt in ("xlsx", "table"):
            ctx = FakeCtx(slash=False)
            _run(ctx, False, contract_cmd.build_reply, CFG, "decision", fmt, None)
            ctx.author.send.assert_awaited()
            ctx.send.assert_not_awaited()
            ctx.message.add_reaction.assert_awaited_once_with("📬")

    def test_closed_dms_get_the_redirect_and_no_data(self, monkeypatch):
        _patch(monkeypatch)
        ctx = FakeCtx(slash=False)
        ctx.author.send.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason=""), "closed")
        _run(ctx, False, contract_cmd.build_reply, CFG, "decision", "xlsx", None)
        ctx.reply.assert_awaited_once()
        assert "Zed Zee" not in str(ctx.reply.await_args)
        ctx.send.assert_not_awaited()

    def test_the_share_button_reposts_the_file_with_an_attribution(self, monkeypatch):
        _patch(monkeypatch)
        reply = contract_cmd.build_xlsx_reply(CFG, "decision")

        async def click() -> AsyncMock:
            view = ShareView([], 7, file=reply)
            channel = SimpleNamespace(send=AsyncMock())
            interaction = SimpleNamespace(
                channel=channel, user=SimpleNamespace(id=7, mention="<@7>"),
                response=SimpleNamespace(edit_message=AsyncMock(), send_message=AsyncMock()),
            )
            await view.post_publicly.callback(interaction)
            return channel.send

        send = asyncio.run(click())
        kwargs = send.await_args.kwargs
        assert kwargs["content"].startswith("📢 Shared by <@7>")
        assert kwargs["file"].filename == "contract-moves-decision.xlsx"

    def test_an_empty_list_reply_is_private_text(self, monkeypatch):
        _patch(monkeypatch, MOVES[MOVES["list_name"] != "expiring"])
        ctx = FakeCtx()
        _run(ctx, False, contract_cmd.build_reply, CFG, "expiring", "xlsx", None)
        ctx.send.assert_awaited_once_with("Nothing due on the Expiring list.", ephemeral=True)

    def test_a_failed_fetch_gives_the_generic_message_not_a_trace(self, monkeypatch):
        def boom(path, _cfg):
            raise RuntimeError("secret detail")
        monkeypatch.setattr(contract_cmd, "fetch_parquet", boom)
        ctx = FakeCtx()
        _run(ctx, False, contract_cmd.build_reply, CFG, "decision", "xlsx", None)
        assert "secret detail" not in str(ctx.send.await_args)
        assert "Couldn't reach the data" in ctx.send.await_args.args[0]


class TestCommand:
    def test_the_slash_command_has_the_three_options_and_share(self):
        async def build():
            bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
            await contract_cmd.setup_contract_moves(bot, CFG)
            return bot.tree.get_command("contract-moves")

        command = asyncio.run(build())
        options = {p.display_name: p for p in command.parameters}
        assert list(options) == ["list", "format", "team", "share"]
        assert [c.value for c in options["list"].choices] == ["minor-to-1st", "expiring", "decision"]
        assert [c.value for c in options["format"].choices] == ["xlsx", "table"]
        assert options["list"].required and not options["team"].required
        assert options["share"].default is False

    def test_a_prefix_call_with_a_team_and_no_format_gets_the_usage_reply(self):
        import bot

        async def drive():
            league_bot = bot.LeagueBot(CFG)
            await contract_cmd.setup_contract_moves(league_bot, CFG)
            command = league_bot.get_command("contract-moves")
            ctx = commands.Context(
                message=MagicMock(), bot=league_bot, view=StringView("expiring ALP"),
                prefix="!", command=command, invoked_with="contract-moves",
            )
            with pytest.raises(commands.UserInputError) as raised:
                await command.prepare(ctx)
            reply = FakeCtx(slash=False)
            reply.command, reply.prefix = command, "!"
            await league_bot.on_command_error(reply, raised.value)
            return reply

        reply = asyncio.run(drive())
        reply.author.send.assert_awaited_once()
        text = reply.author.send.await_args.args[0]
        assert text.startswith("Usage: `!contract-moves ")
        assert "xlsx" in text and "table" in text and "ALP" not in text

    def test_the_bots_setup_hook_calls_the_setup(self):
        import bot

        assert "await setup_contract_moves(self, self.cfg)" in inspect.getsource(bot.LeagueBot.setup_hook)


@pytest.mark.skipif(not (_DATA / "fact_contract_move.parquet").exists(), reason="snapshot not present")
def test_the_published_snapshot_renders_in_both_formats(monkeypatch):
    def fetch(path: str, _cfg: Config) -> pd.DataFrame:
        return pd.read_parquet(_DATA / Path(path).name)
    monkeypatch.setattr(contract_cmd, "fetch_parquet", fetch)
    published = fetch("data/fact_contract_move.parquet", CFG)
    for list_name in cm.LISTS:
        want = int((published["list_name"] == list_name).sum())
        if not want:
            with pytest.raises(CommandError):
                contract_cmd.build_table_embeds(CFG, list_name)
            continue
        embeds = contract_cmd.build_table_embeds(CFG, list_name)
        _check_limits(embeds)
        assert f"({want})" in embeds[0].title
        book = _book(contract_cmd.build_xlsx_reply(CFG, list_name))
        assert book.sheetnames == ["Conference A", "Conference B"]
        assert sum(ws.max_row - 1 for ws in book.worksheets) == want

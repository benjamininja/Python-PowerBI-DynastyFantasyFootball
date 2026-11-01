"""trade-bud reads the published cap tables, as the bot does (#97 Brief 3,
ADR-0016's #97 amendment, decisions 1 and 7).

The acceptance test compares the bot's reader, trade-bud's reader and the
published table for all 28 teams. The text guards hold the rest: trade-bud
reaches nothing in discord_bot/, neither side names the ETL cap module, and
the what-if sheds the giver's charge and charges the receiver the salary.
The repo has no JavaScript runner, so the what-if guard reads text only; its
behaviour is not run here.
"""
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "mouserat_trade-bud" / "backend"
INDEX = REPO / "mouserat_trade-bud" / "frontend" / "index.html"
sys.path.insert(0, str(REPO / "discord_bot"))
sys.path.insert(0, str(BACKEND))

import pandas as pd
import pytest

import capmath
import data_access as da
import profiles
from config import Config

CFG = Config(discord_bot_token="x", discord_guild_id=1, github_pat="x", github_owner="o",
             github_repo="r", github_ref="main", command_prefix="!")


@pytest.fixture
def bot_reads_local(monkeypatch):
    monkeypatch.setattr(capmath, "fetch_parquet",
                        lambda path, _cfg: pd.read_parquet(REPO / path))


def _table_room(cap: pd.DataFrame, current: bool) -> pd.Series:
    rows = cap[cap["is_current_season"] == current]
    return rows.set_index("team_key")["cap_room"].sort_index()


class TestTwentyEightTeams:
    def test_bot_trade_bud_and_the_table_agree_on_cap_room(self, bot_reads_local):
        cap = da.read_parquet("fact_team_cap")
        bot = capmath.teams_with_cap(CFG).set_index("team_key").sort_index()
        bud = da.teams_with_cap().set_index("team_key").sort_index()

        assert len(bud) == 28
        assert bot.index.tolist() == bud.index.tolist() == _table_room(cap, True).index.tolist()
        for column, current in (("remaining_cap_current_yr", True),
                                ("remaining_cap_next_yr", False)):
            table = _table_room(cap, current).rename(column)
            pd.testing.assert_series_equal(bud[column], table, check_exact=True)
            pd.testing.assert_series_equal(bot[column], table, check_exact=True)

    def test_the_whole_team_frame_matches_the_bot_column_for_column(self, bot_reads_local):
        bot = capmath.teams_with_cap(CFG).reset_index(drop=True)
        bud = da.teams_with_cap().reset_index(drop=True)
        pd.testing.assert_frame_equal(bud, bot, check_exact=True)

    def test_the_roster_matches_the_bots_and_the_published_table(self, bot_reads_local):
        bud = da.roster_with_cap_hit()
        pd.testing.assert_frame_equal(bud, capmath.roster_with_cap_hit(CFG), check_exact=True)
        pd.testing.assert_frame_equal(
            bud, pd.read_parquet(REPO / "data" / "fact_fantasy_teams.parquet"), check_exact=True)

    def test_every_team_has_both_figures(self):
        bud = da.teams_with_cap()
        assert bud[["remaining_cap_current_yr", "remaining_cap_next_yr"]].notna().all().all()

    def test_editing_a_result_leaves_a_memoized_read_alone(self, monkeypatch):
        memo = {}

        def memoized(name):
            if name not in memo:
                memo[name] = pd.read_parquet(da.DATA_DIR / f"{name}.parquet")
            return memo[name]

        monkeypatch.setattr(da, "read_parquet", memoized)
        da.teams_with_cap()
        da.roster_with_cap_hit()
        before = {name: frame.copy() for name, frame in memo.items()}
        assert {"dim_fantasy_teams", "fact_team_cap", "fact_fantasy_teams"} <= set(before)

        roster = da.roster_with_cap_hit()
        roster["cap_hit"] = -1.0
        teams = da.teams_with_cap()
        teams["original_cap"] = -1.0
        for name, frame in before.items():
            pd.testing.assert_frame_equal(memo[name], frame)


TEAMS = pd.DataFrame({"team_key": ["A01", "B01"], "original_cap": [300.0, 310.0],
                      "reinvestment_cap": [7.0, 0.0]})
CAP = pd.DataFrame({
    "season_id": ["S1", "S1", "S2", "S2"],
    "team_key": ["A01", "B01", "A01", "B01"],
    "is_current_season": [True, True, False, False],
    "charged_salary": [111.0, 222.0, 333.0, 444.0],
    "ir_salary": [11.0, 22.0, 0.0, 0.0],
    "minors_salary": [5.0, 6.0, 0.0, 0.0],
    "dead_money": [10.0, 20.0, 8.0, 4.0],
    "cap_room": [1001.0, 1002.0, 1003.0, 1004.0],
})


class TestReaderOnSyntheticFrames:
    @pytest.fixture
    def serve(self, monkeypatch):
        frames = {"dim_fantasy_teams": TEAMS, "fact_team_cap": CAP}

        def put(**swap):
            frames.update(swap)
            monkeypatch.setattr(da, "read_parquet", lambda name: frames[name].copy())
        put()
        return put

    def test_each_season_row_maps_to_its_names(self, serve):
        a = da.teams_with_cap().set_index("team_key").loc["A01"]
        assert (a["active_roster_salary"], a["remaining_cap_current_yr"]) == (111.0, 1001.0)
        assert (a["dead_money"], a["ir_salary"], a["minors_salary"]) == (10.0, 11.0, 5.0)
        assert (a["remaining_cap_next_yr"], a["dead_money_next_yr"]) == (1003.0, 8.0)
        assert (a["original_cap"], a["reinvestment_cap"]) == (300.0, 7.0)

    def test_the_season_comes_from_the_flag_not_the_row_order_or_the_label(self, serve):
        serve(fact_team_cap=CAP.iloc[::-1].assign(season_id=lambda d: d["season_id"].str[::-1]))
        a = da.teams_with_cap().set_index("team_key").loc["A01"]
        assert (a["remaining_cap_current_yr"], a["remaining_cap_next_yr"]) == (1001.0, 1003.0)

    def test_nothing_is_filled_in_for_a_missing_row(self, serve):
        serve(fact_team_cap=CAP[~((CAP["team_key"] == "B01") & ~CAP["is_current_season"])])
        b = da.teams_with_cap().set_index("team_key").loc["B01"]
        assert pd.isna(b["remaining_cap_next_yr"]) and b["remaining_cap_current_yr"] == 1002.0

    def test_a_team_twice_on_one_season_fails(self, serve):
        serve(fact_team_cap=pd.concat([CAP, CAP.iloc[[0]]]))
        with pytest.raises(pd.errors.MergeError):
            da.teams_with_cap()

    def test_no_teams_come_back_empty(self, serve):
        serve(dim_fantasy_teams=TEAMS.iloc[0:0])
        assert da.teams_with_cap().empty


class TestRiskThreshold:
    def test_cap_room_pct_is_the_tables_cap_room_over_original_cap(self):
        cap = da.read_parquet("fact_team_cap")
        room = _table_room(cap, True)
        original = da.read_parquet("dim_fantasy_teams").set_index("team_key")["original_cap"]
        assert len(room) == 28
        for team_key, cap_room in room.items():
            got = profiles.infer_risk_threshold(team_key)["cap_room_pct"]
            assert got == float(cap_room / original[team_key]), team_key


class TestTextGuards:
    def test_data_access_reaches_nothing_in_discord_bot(self):
        text = (BACKEND / "data_access.py").read_text(encoding="utf-8")
        for name in ("discord_bot", "capmath", "github_fetch", "sys.path"):
            assert name not in text, name

    def test_no_trade_bud_file_imports_what_only_the_bot_needed(self):
        for path in (REPO / "mouserat_trade-bud").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert not re.search(r"^\s*(import|from)\s+(httpx|dotenv)\b", text, re.M), path
        reqs = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
        assert "httpx" not in reqs and "dotenv" not in reqs

    @pytest.mark.parametrize("folder", ["discord_bot", "mouserat_trade-bud"])
    def test_no_consumer_imports_the_etl_cap_module(self, folder):
        # Imports, not mentions: capmath.py's docstring names notebooks/etl_cap.py
        # as the place the figures are computed, which is not an import (decision 1).
        files = list((REPO / folder).rglob("*.py"))
        assert files
        for path in files:
            assert "etl_cap" not in imported_names(path.read_text(encoding="utf-8")), path

    def test_no_trade_bud_file_imports_the_bot(self):
        # CLAUDE.md: the backend imports nothing from discord_bot/. Every file,
        # not only data_access.py.
        files = list((REPO / "mouserat_trade-bud").rglob("*.py"))
        assert (BACKEND / "data_access.py") in files
        for path in files:
            reached = imported_names(path.read_text(encoding="utf-8")) & {
                "discord_bot", "capmath", "github_fetch"}
            assert not reached, (path, reached)


def imported_names(source: str) -> set[str]:
    """Every name an import statement in `source` could be reaching: each dotted
    component of the module, and each alias name of a from-import (which may
    itself be dotted). Relative imports count: `from . import x` gives x."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            names.update((node.module or "").split("."))
            for alias in node.names:
                names.update(alias.name.split("."))
    names.discard("")
    return names


class TestImportedNames:
    @pytest.mark.parametrize("source", [
        "import etl_cap",
        "import etl_cap as cap",
        "from etl_cap import team_cap",
        "from notebooks import etl_cap",
        "from notebooks import etl_cap as cap",
        "import notebooks.etl_cap",
        "import os, notebooks.etl_cap",
        "from notebooks.etl_cap import team_cap",
        "from . import etl_cap",
        "from .etl_cap import team_cap",
        "from .. import etl_cap",
        "def f():\n    import etl_cap",
    ])
    def test_every_import_form_of_etl_cap_is_caught(self, source):
        assert "etl_cap" in imported_names(source)

    @pytest.mark.parametrize("source, name", [
        ("import capmath", "capmath"),
        ("from capmath import teams_with_cap", "capmath"),
        ("from discord_bot import capmath", "capmath"),
        ("from discord_bot import capmath", "discord_bot"),
        ("import discord_bot.capmath", "discord_bot"),
        ("import discord_bot.capmath", "capmath"),
        ("from discord_bot.github_fetch import fetch_parquet", "discord_bot"),
        ("from discord_bot.github_fetch import fetch_parquet", "github_fetch"),
        ("import github_fetch as gf", "github_fetch"),
        ("from . import github_fetch", "github_fetch"),
        ("from .capmath import teams_with_cap", "capmath"),
    ])
    def test_every_import_form_of_the_bot_modules_is_caught(self, source, name):
        assert name in imported_names(source)

    def test_a_mention_is_not_an_import(self):
        source = '"""computed in notebooks/etl_cap.py"""\nx = "etl_cap"  # etl_cap\n'
        assert imported_names(source) == set()

    def test_unrelated_imports_are_not_flagged(self):
        assert not imported_names("import pandas as pd\nfrom pathlib import Path") & {
            "etl_cap", "discord_bot", "capmath", "github_fetch"}


def _function(text: str, name: str) -> str:
    start = text.index(f"function {name}(")
    return text[start:text.index("\n}\n", start)]


class TestWhatIfText:
    text = INDEX.read_text(encoding="utf-8")

    def test_render_cap_cards_reads_both_figures(self):
        body = _function(self.text, "renderCapCards")
        assert "cap_hit" in body and "contract_value" in body

    def test_the_giver_sheds_the_charge_and_the_receiver_takes_the_salary(self):
        body = " ".join(_function(self.text, "renderCapCards").split())
        charges = re.search(r"const sumCharges = [^;]*a\.cap_hit", body)
        salaries = re.search(r"const sumSalaries = [^;]*a\.contract_value", body)
        assert charges and salaries
        assert re.search(r"capCard-my.*remaining_cap_current_yr \+ giveCharges - receiveSalaries", body)
        assert re.search(r"capCard-cp.*remaining_cap_current_yr \+ receiveCharges - giveSalaries", body)

    def test_the_lines_say_cap_room(self):
        card = _function(self.text, "capCardHtml")
        assert "Cap Room:" in card and "Cap Room After Trade:" in card
        assert "Team Salary" not in card

    def test_the_card_states_its_assumption_on_both_teams(self):
        card = _function(self.text, "capCardHtml")
        assert "Assumes received players go on the active roster." in card
        render = _function(self.text, "renderCapCards")
        assert render.count("capCardHtml(") == 2

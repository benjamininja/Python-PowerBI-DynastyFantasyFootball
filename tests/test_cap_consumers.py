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

    def test_every_team_has_both_figures(self):
        bud = da.teams_with_cap()
        assert bud[["remaining_cap_current_yr", "remaining_cap_next_yr"]].notna().all().all()

    def test_the_roster_comes_back_as_published(self):
        pd.testing.assert_frame_equal(da.roster_with_cap_hit(),
                                      da.read_parquet("fact_fantasy_teams"))

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
        for path in (REPO / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    modules = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                assert not [m for m in modules if m.split(".")[0] == "etl_cap"], path


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

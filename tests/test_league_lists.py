"""scripts/league_lists.py (#675, ADR-0026 decision 2 as amended 2026-11-26): the
League Associations tab and the team tab as the access loads read them. Every league,
team and id is made up; nothing reads a sheet or connects to a database."""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import etl_helpers as etl  # noqa: E402
import league_lists as ll  # noqa: E402

FOOTBALL_ID = "made-up-football"


def leagues_tab(sports=("Football", "Baseball", "Basketball"), names=("F", "B", "K"),
                ids=(FOOTBALL_ID, "made-up-b", "made-up-k")):
    return pd.DataFrame({"Sport": list(sports), "League Name": list(names), "League ID": list(ids),
                         "Helper": ["x"] * len(sports)})


def resolve_leagues(frame):
    return ll.resolve_leagues(frame, football_id=FOOTBALL_ID, football_key="football")


LEAGUES = resolve_leagues(leagues_tab())[0]


def teams_tab(team_ids, names, divisions=None):
    count = len(team_ids)
    return pd.DataFrame({"Sport": ["s"] * count, "League Name": names,
                         "Division": divisions if divisions is not None else ["D"] * count,
                         "Team Name": [f"n{i}" for i in range(count)], "Team ID": team_ids,
                         "Fantrax-TeamId": [f"f{i}" for i in range(count)], "Roster": ["r"] * count})


class TestTheLeagueTab:
    def test_three_leagues_load_and_each_key_is_the_sport_trimmed_and_lowercased(self):
        rows, problems = resolve_leagues(leagues_tab(sports=(" Football", "BASEBALL ", "Basketball")))
        assert problems == []
        assert rows == [("baseball", "BASEBALL", "B", "made-up-b"), ("basketball", "Basketball", "K", "made-up-k"),
                        ("football", "Football", "F", FOOTBALL_ID)]

    def test_two_rows_with_one_sport_stop_the_load(self):
        _, problems = resolve_leagues(leagues_tab(sports=("Football", "football", "Basketball")))
        assert problems == ["1 row(s) repeating a key or a League ID (rows 3)"]

    @pytest.mark.parametrize("sport", [None, "", "  ", "Ice Hockey", "4ball", "foot-ball"])
    def test_a_row_that_gives_no_plain_key_stops_the_load(self, sport):
        _, problems = resolve_leagues(leagues_tab(sports=("Football", sport, "Basketball")))
        assert problems == ["1 row(s) whose Sport gives no plain lowercase key (rows 3)"]

    def test_a_blank_or_repeated_league_id_stops_the_load(self):
        _, problems = resolve_leagues(leagues_tab(ids=(FOOTBALL_ID, None, FOOTBALL_ID)))
        assert problems == ["1 row(s) with no League ID (rows 3)", "1 row(s) repeating a key or a League ID (rows 4)"]

    def test_league_config_and_the_league_row_must_agree(self):
        _, problems = ll.resolve_leagues(leagues_tab(), football_id="made-up-b", football_key="football")
        assert problems == ["the league of LeagueConfig.fantrax_league_id does not have the key "
                            "LeagueConfig.football_league_key"]
        _, problems = ll.resolve_leagues(leagues_tab(), football_id="not-on-the-tab", football_key="football")
        assert len(problems) == 1

    def test_the_real_config_names_football_and_the_all_leagues_word(self):
        assert etl.CFG.football_league_key == "football" and etl.CFG.app_roles_all_leagues == "_ALL"
        rows, problems = ll.resolve_leagues(leagues_tab(ids=(etl.CFG.fantrax_league_id, "b", "k")))
        assert problems == [] and dict((r[3], r[0]) for r in rows)[etl.CFG.fantrax_league_id] == "football"

    def test_an_empty_tab_or_a_missing_column_stops_and_names_no_value(self):
        assert resolve_leagues(leagues_tab(sports=(), names=(), ids=()))[1] == ["the League Associations tab has no rows"]
        assert resolve_leagues(leagues_tab().drop(columns=["Sport"]))[1] == [
            "the League Associations tab lacks the column(s) Sport"]

    def test_a_problem_names_counts_and_row_numbers_never_a_value(self):
        _, problems = resolve_leagues(leagues_tab(sports=("Football", "football", "Ice Hockey"),
                                                  ids=(FOOTBALL_ID, "secret-id", "other-id")))
        text = "\n".join(problems)
        assert "secret-id" not in text and "Ice Hockey" not in text and "football" not in text


class TestTheTeamTab:
    def test_every_leagues_teams_load_each_with_its_league_from_the_league_name(self):
        rows, problems = ll.resolve_teams(teams_tab(["T1", "B1", "K1"], ["F", "B", "K"]), LEAGUES)
        assert problems == []
        assert [(r[0], r[1]) for r in rows] == [("B1", "baseball"), ("K1", "basketball"), ("T1", "football")]
        assert rows[2] == ("T1", "football", "f0", "n0", "D")

    def test_a_team_key_is_unique_across_leagues(self):
        _, problems = ll.resolve_teams(teams_tab(["T1", "T1"], ["F", "B"]), LEAGUES)
        assert problems == ["1 row(s) repeating a Team ID (rows 3)"]

    def test_a_league_name_the_league_tab_does_not_hold_or_a_blank_team_id_stops(self):
        _, problems = ll.resolve_teams(teams_tab(["T1", "T2", None], ["F", "Nowhere", "F"]), LEAGUES)
        assert problems == ["1 row(s) with no Team ID (rows 4)",
                            "1 row(s) whose League Name the League Associations tab does not hold (rows 3)"]

    def test_blank_rows_are_skipped_and_blank_cells_load_as_null(self):
        frame = teams_tab(["T1", None], ["F", None], ["", None])
        frame.loc[1, :] = None
        rows, problems = ll.resolve_teams(frame, LEAGUES)
        assert problems == [] and rows == [("T1", "football", "f0", "n0", None)]

    def test_an_empty_tab_or_a_missing_column_stops(self):
        assert ll.resolve_teams(teams_tab([], []), LEAGUES)[1] == ["the team tab has no rows"]
        assert ll.resolve_teams(teams_tab(["T1"], ["F"]).drop(columns=["Team ID"]), LEAGUES)[1] == [
            "the team tab lacks the column(s) Team ID"]


class TestFootballsTwoTeamTables:
    """ADR-0026 decision 2 as amended: football's rows of the team list and the published
    dim_fantasy_teams are held equal by a test."""

    TEAMS = [("T1", "football", None, None, None), ("T2", "football", None, None, None),
             ("B1", "baseball", None, None, None)]

    def test_they_agree_when_footballs_team_keys_are_the_same(self):
        assert ll.football_disagreement(self.TEAMS, pd.DataFrame({"team_key": ["T2", "T1 "]}), "football") == 0

    def test_a_made_up_disagreement_is_counted_both_ways(self):
        assert ll.football_disagreement(self.TEAMS, pd.DataFrame({"team_key": ["T1"]}), "football") == 1
        assert ll.football_disagreement(self.TEAMS, pd.DataFrame({"team_key": ["T1", "T2", "T3"]}), "football") == 1
        assert ll.football_disagreement(self.TEAMS, pd.DataFrame({"team_key": ["T1", "T9"]}), "football") == 2

    def test_other_leagues_teams_never_count(self):
        assert ll.football_disagreement(self.TEAMS, pd.DataFrame({"team_key": ["T1", "T2", "B1"]}), "football") == 1


class TestTheReaders:
    def test_each_list_tab_is_read_on_its_own_gid_of_the_team_workbook(self, monkeypatch):
        calls = []
        monkeypatch.setattr(etl, "read_sheet_tab", lambda sheet, gid, columns, optional=(), **kw:
                            calls.append((sheet, gid, list(columns), kw)) or pd.DataFrame())
        ll.read_leagues()
        ll.read_teams()
        assert calls == [(etl.CFG.team_sheet_id, etl.CFG.league_assoc_sheet_gid, ll.LEAGUE_COLUMNS,
                          {"text": ["League ID"]}),
                         (etl.CFG.team_sheet_id, etl.CFG.team_sheet_gid, ll.TEAM_COLUMNS, {})]

    def test_the_module_names_no_database_client(self):
        text = (REPO / "scripts" / "league_lists.py").read_text(encoding="utf-8")
        for word in ("psycopg", "sqlalchemy", "DATABASE_URL", "connect("):
            assert word not in text

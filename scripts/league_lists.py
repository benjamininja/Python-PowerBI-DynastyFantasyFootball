"""The League Associations tab and the team tab, as the access loads read them (#675).

ADR-0026 decision 2 as amended 2026-11-26: the team-manifest workbook holds every
league. A league's key is its League Associations row's `Sport`, trimmed and
lowercased; the tab gains no column. The team list holds every league's teams, each
found its league by its `League Name` on the League Associations tab (the join
`01c` uses). `scripts/load_access_tables.py` and `scripts/load_app_roles.py` read
both tabs through this module.

Each `resolve_*` checks everything and returns the rows and the problems found. A
problem is a count and the tab's row numbers (the header is row 1), never a value:
the run's notice is public. Nothing here connects to a database.
"""
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
import etl_helpers as etl  # noqa: E402
from etl_helpers import CFG  # noqa: E402

SPORT, LEAGUE_NAME, LEAGUE_ID = "Sport", "League Name", "League ID"
LEAGUE_COLUMNS = [SPORT, LEAGUE_NAME, LEAGUE_ID]
TEAM_ID, FANTRAX_TEAM_ID, TEAM_NAME, DIVISION = "Team ID", "Fantrax-TeamId", "Team Name", "Division"
TEAM_COLUMNS = [LEAGUE_NAME, DIVISION, TEAM_NAME, TEAM_ID, FANTRAX_TEAM_ID]
KEY = re.compile(r"^[a-z][a-z0-9_]*$")


def _text(value) -> str:
    return "" if value is None or (not isinstance(value, str) and pd.isna(value)) else str(value).strip()


def _problems(labels: dict, where: dict) -> list[str]:
    return [f"{len(where[k])} {labels[k]} (rows {', '.join(str(n) for n in where[k])})" for k in labels if where[k]]


def read_leagues() -> pd.DataFrame:
    return etl.read_sheet_tab(CFG.team_sheet_id, CFG.league_assoc_sheet_gid, LEAGUE_COLUMNS, text=[LEAGUE_ID])


def read_teams() -> pd.DataFrame:
    return etl.read_sheet_tab(CFG.team_sheet_id, CFG.team_sheet_gid, TEAM_COLUMNS)


def resolve_leagues(frame: pd.DataFrame, football_id: str = CFG.fantrax_league_id,
                    football_key: str = CFG.football_league_key) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    """The (league_key, sport, league_name, fantrax_league_id) rows and the problems.
    The league whose Fantrax id is `football_id` must have the key `football_key`:
    LeagueConfig and the league table agree, or the load stops."""
    missing = [c for c in LEAGUE_COLUMNS if frame is None or c not in frame.columns]
    if missing:
        return [], [f"the League Associations tab lacks the column(s) {', '.join(missing)}"]
    frame = frame[LEAGUE_COLUMNS].dropna(how="all")
    if frame.empty:
        return [], ["the League Associations tab has no rows"]
    labels = {"key": "row(s) whose Sport gives no plain lowercase key",
              "id": "row(s) with no League ID",
              "twice": "row(s) repeating a key or a League ID"}
    where = {k: [] for k in labels}
    rows, keys, ids = [], set(), set()
    for number, sport, name, league_id in zip(frame.index + 2, frame[SPORT], frame[LEAGUE_NAME], frame[LEAGUE_ID]):
        sport, name, league_id = _text(sport), _text(name), _text(league_id)
        key = sport.lower()
        if not KEY.match(key):
            where["key"].append(number)
            continue
        if not league_id:
            where["id"].append(number)
            continue
        if key in keys or league_id in ids:
            where["twice"].append(number)
            continue
        keys.add(key)
        ids.add(league_id)
        rows.append((key, sport, name, league_id))
    problems = _problems(labels, where)
    if not problems:
        football = [key for key, _, _, league_id in rows if league_id == football_id]
        if football != [football_key]:
            problems.append("the league of LeagueConfig.fantrax_league_id does not have the key "
                            "LeagueConfig.football_league_key")
    return sorted(rows), problems


def resolve_teams(frame: pd.DataFrame, leagues: list[tuple[str, str, str, str]]
                  ) -> tuple[list[tuple[str, str, str, str, str]], list[str]]:
    """The (team_key, league_key, fantrax_team_id, team_name, division) rows and the
    problems. A team's league is the league whose League Name it names."""
    missing = [c for c in TEAM_COLUMNS if frame is None or c not in frame.columns]
    if missing:
        return [], [f"the team tab lacks the column(s) {', '.join(missing)}"]
    frame = frame[TEAM_COLUMNS].dropna(how="all")
    if frame.empty:
        return [], ["the team tab has no rows"]
    league_of = {name: key for key, _, name, _ in leagues}
    labels = {"blank": "row(s) with no Team ID",
              "league": "row(s) whose League Name the League Associations tab does not hold",
              "twice": "row(s) repeating a Team ID"}
    where = {k: [] for k in labels}
    rows, seen = [], set()
    for number, record in zip(frame.index + 2, frame.itertuples(index=False)):
        values = dict(zip(TEAM_COLUMNS, (_text(v) for v in record)))
        team_key = values[TEAM_ID]
        if not team_key:
            where["blank"].append(number)
            continue
        if values[LEAGUE_NAME] not in league_of:
            where["league"].append(number)
            continue
        if team_key in seen:
            where["twice"].append(number)
            continue
        seen.add(team_key)
        rows.append((team_key, league_of[values[LEAGUE_NAME]], values[FANTRAX_TEAM_ID] or None,
                     values[TEAM_NAME] or None, values[DIVISION] or None))
    return sorted(rows), _problems(labels, where)


def league_of_id(leagues: list[tuple[str, str, str, str]]) -> dict[str, str]:
    """Each Fantrax league id's key."""
    return {league_id: key for key, _, _, league_id in leagues}


def football_disagreement(teams: list[tuple[str, str, str, str, str]], published: pd.DataFrame,
                          football_key: str = CFG.football_league_key) -> int:
    """How many team keys are in only one of football's rows of the team list and the
    published dim_fantasy_teams. Zero when the two agree (ADR-0026 decision 2 as
    amended: a test holds them equal)."""
    listed = {team_key for team_key, league_key, _, _, _ in teams if league_key == football_key}
    held = {_text(k) for k in published["team_key"]} - {""}
    return len(listed ^ held)

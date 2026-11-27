"""The scheduled run's step that loads the access tables (#700, #675).

    load_access_tables.py

ADR-0026 decision 2 as amended 2026-11-25 and 2026-11-26: the run reads four tabs of
the team-manifest workbook as the Sheets service account (`etl.read_sheet_tab`): the
League Associations tab, the team tab, the owner tab and the App roles tab. It
checks all four first (`league_lists.resolve_leagues` and `resolve_teams`,
`load_owner_crosswalk.resolve_counted`, `load_app_roles.resolve`), then calls
`shared.load_leagues`, `shared.load_teams`, `shared.load_owner_crosswalk` and
`shared.load_app_roles` as `etl_writer`, which holds no grant on any of the four
tables. Each function replaces its table's rows and returns row counts only. The four
calls run in one transaction, in that order, committed only when all succeed: a failed
sheet read, a failed check or a refusal by any function leaves all four tables as they
were, and no data Chain is held.

An owner-tab row with no id is skipped and counted. The run also reports whether
football's rows of the team list agree with the published dim_fantasy_teams; that is
a notice line, never a stop.

Every line this script prints starts with `access:` and holds counts, tab names and
row numbers, never an id and never a name: `run_pipeline.py` keeps only those lines
as the step's detail, in the run's notice. It writes no file and keeps no id past the
call. It exits 1 on any failure. The two manual loaders stay as a fallback.
"""
import os
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))
import etl_helpers as etl  # noqa: E402
import etl_storage_pg as pg  # noqa: E402
import league_lists  # noqa: E402
from etl_helpers import CFG  # noqa: E402
import load_app_roles as roles  # noqa: E402
import load_owner_crosswalk as crosswalk  # noqa: E402

PREFIX = "access:"
LEAGUES_TAB = "League Associations tab"
TEAMS_TAB = "team tab"
OWNER_TAB = "owner tab"
ROLES_TAB = "App roles tab"
PUBLISHED_TEAMS = "dim_fantasy_teams"
LEAGUES_CALL = ("SELECT rows_before, rows_after FROM shared.load_leagues("
                "%s::text[], %s::text[], %s::text[], %s::text[])")
TEAMS_CALL = ("SELECT rows_before, rows_after FROM shared.load_teams("
              "%s::text[], %s::text[], %s::text[], %s::text[], %s::text[])")
OWNER_CALL = "SELECT rows_before, rows_after FROM shared.load_owner_crosswalk(%s::text[], %s::text[])"
ROLES_CALL = "SELECT rows_before, rows_after FROM shared.load_app_roles(%s::text[], %s::text[], %s::text[])"
RAISE_EXCEPTION = "P0001"
FAILED = "load failed, nothing was loaded and the four tables are as they were"


def say(line: str) -> None:
    print(f"{PREFIX} {line}")


class Stop(Exception):
    """A stop whose text holds a tab name and counts only."""


def _sheet(read) -> object:
    """The tab's frame, or a Stop naming the cause in words with no value."""
    try:
        return read()
    except etl.SheetsNumberCells as exc:
        raise Stop(f"{crosswalk.AS_NUMBERS} ({exc})") from None
    except (etl.SheetsAuthError, RuntimeError) as exc:
        raise Stop(pg.scrub((str(exc).splitlines() or [""])[0])) from None


def read_league_rows():
    return league_lists.resolve_leagues(_sheet(league_lists.read_leagues))


def read_team_rows(leagues):
    return league_lists.resolve_teams(_sheet(league_lists.read_teams), leagues)


def read_owner_pairs(teams):
    frame = _sheet(lambda: etl.read_sheet_tab(CFG.team_sheet_id, CFG.owner_sheet_gid, crosswalk.COLUMNS,
                                              text=[crosswalk.ID_COLUMN]))
    return crosswalk.resolve_counted(frame, pd.DataFrame({"team_key": [t[0] for t in teams]}))


def read_role_rows(leagues):
    frame = _sheet(lambda: etl.read_sheet_tab(CFG.team_sheet_id, CFG.app_roles_sheet_gid, roles.COLUMNS,
                                              text=[roles.ID_COLUMN, roles.LEAGUE_COLUMN]))
    return roles.resolve(frame, leagues)


def read_published():
    return etl.read_table(PUBLISHED_TEAMS, ["team_key"])


def connect():
    url = os.environ.get(pg.URL_ENV)
    if not url:
        raise Stop(f"{pg.URL_ENV} is not set")
    psycopg, _ = pg._psycopg()
    return psycopg.connect(url, prepare_threshold=None)


def _why(exc: BaseException) -> str:
    """A failure in words that carry no value. A refusal by one of the four
    functions (SQLSTATE P0001) is their own fixed message, a count and a tab name;
    any other database error is its class, SQLSTATE and the object it names."""
    psycopg, _ = pg._psycopg()
    if isinstance(exc, Stop):
        return str(exc)
    if isinstance(exc, psycopg.Error):
        if getattr(exc, "sqlstate", None) == RAISE_EXCEPTION:
            return pg.scrub(exc.diag.message_primary or str(exc))
        return pg.describe(exc)
    return type(exc).__name__


def _changed(before: int, after: int) -> str:
    return "unchanged" if before == after else "CHANGED"


def _columns(rows, width):
    return tuple([row[i] for row in rows] for i in range(width))


def run(read_leagues=read_league_rows, read_teams=read_team_rows, read_owner=read_owner_pairs,
        read_roles=read_role_rows, read_football=read_published, connect_to=connect, out=say) -> int:
    """0 when the four loads committed, 1 on any failure, with the four tables unchanged."""
    failed = False

    def checked(tab, read, *args):
        nonlocal failed
        try:
            found = read(*args)
        except Exception as exc:
            out(f"{tab}: not read ({_why(exc)})")
            failed = True
            return None
        for problem in found[1]:
            out(f"{tab}: stopped, {problem}")
        if found[1]:
            failed = True
            return None
        return found

    leagues = checked(LEAGUES_TAB, read_leagues)
    teams = owner = role_rows = None
    if leagues is None:
        out(f"{TEAMS_TAB} and {ROLES_TAB}: not checked, they name leagues the {LEAGUES_TAB} gives")
    else:
        teams = checked(TEAMS_TAB, read_teams, leagues[0])
        role_rows = checked(ROLES_TAB, read_roles, leagues[0])
    if teams is None:
        out(f"{OWNER_TAB}: not checked, it names teams the {TEAMS_TAB} gives")
    else:
        owner = checked(OWNER_TAB, read_owner, teams[0])
    if failed or None in (leagues, teams, owner, role_rows):
        out(FAILED)
        return 1
    calls = ((LEAGUES_CALL, _columns(leagues[0], 4)), (TEAMS_CALL, _columns(teams[0], 5)),
             (OWNER_CALL, _columns(owner[0], 2)), (ROLES_CALL, _columns(role_rows[0], 3)))
    try:
        with connect_to() as conn:
            counts = [conn.execute(sql, params).fetchone() for sql, params in calls]
    except Exception as exc:
        out(f"load failed, the four tables are as they were ({_why(exc)})")
        return 1
    for name, (before, after) in zip(("leagues", "team list", "owner crosswalk", "app roles"), counts):
        out(f"{name}: {before} rows before, {after} after, {_changed(before, after)}")
    out(f"{OWNER_TAB}: {owner[2]} row(s) with no id, skipped")
    try:
        differ = league_lists.football_disagreement(teams[0], read_football())
        out("football teams: the team list and dim_fantasy_teams agree" if not differ else
            f"football teams: {differ} team key(s) differ between the team list and dim_fantasy_teams")
    except Exception as exc:
        out(f"football teams: not compared ({type(exc).__name__})")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        return run()
    except Exception as exc:
        say(f"load failed, the four tables are as they were ({type(exc).__name__})")
        return 1


if __name__ == "__main__":
    sys.exit(main())

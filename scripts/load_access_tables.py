"""The scheduled run's step that loads the role table and the owner crosswalk (#700).

    load_access_tables.py

ADR-0026 decision 2 as amended: the run reads the owner tab and the App roles tab
of the team-manifest workbook as the Sheets service account (`etl.read_sheet_tab`),
checks both with the checks the two manual loaders hold (`load_owner_crosswalk.resolve`
and `load_app_roles.resolve`), then calls `shared.load_owner_crosswalk` and
`shared.load_app_roles` as `etl_writer`, which holds no grant on either table. Each
function replaces its table's rows and returns row counts only. Both calls run in one
transaction, committed only when both succeed: a failed sheet read, a failed check or
a refusal by either function leaves both tables as they were.

Every line this script prints starts with `access:` and holds counts, tab names and
row numbers, never an id and never a name: `run_pipeline.py` keeps only those lines
as the step's detail, in the run's notice. It writes no file and keeps no id past the
call. It exits 1 on any failure. The two manual loaders stay as a fallback.
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))
import etl_helpers as etl  # noqa: E402
import etl_storage_pg as pg  # noqa: E402
from etl_helpers import CFG  # noqa: E402
import load_app_roles as roles  # noqa: E402
import load_owner_crosswalk as crosswalk  # noqa: E402

PREFIX = "access:"
OWNER_TAB = "owner tab"
ROLES_TAB = "App roles tab"
OWNER_CALL = "SELECT rows_before, rows_after FROM shared.load_owner_crosswalk(%s::text[], %s::text[])"
ROLES_CALL = "SELECT rows_before, rows_after FROM shared.load_app_roles(%s::text[], %s::text[])"
RAISE_EXCEPTION = "P0001"


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


def read_owner_pairs() -> tuple[list[tuple[str, str]], list[str]]:
    frame = _sheet(lambda: etl.read_sheet_tab(CFG.team_sheet_id, CFG.owner_sheet_gid, crosswalk.COLUMNS,
                                              text=[crosswalk.ID_COLUMN]))
    teams = etl.read_table(crosswalk.TEAMS_TABLE, ["team_key"])
    return crosswalk.resolve(frame, teams)


def read_role_rows() -> tuple[list[tuple[str, str, str]], list[str]]:
    frame = _sheet(lambda: etl.read_sheet_tab(CFG.team_sheet_id, CFG.app_roles_sheet_gid, roles.COLUMNS,
                                              text=[roles.ID_COLUMN]))
    return roles.resolve(frame)


def connect():
    url = os.environ.get(pg.URL_ENV)
    if not url:
        raise Stop(f"{pg.URL_ENV} is not set")
    psycopg, _ = pg._psycopg()
    return psycopg.connect(url, prepare_threshold=None)


def _why(exc: BaseException) -> str:
    """A failure in words that carry no value. A refusal by one of the two
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


def run(read_owner=read_owner_pairs, read_roles=read_role_rows, connect_to=connect, out=say) -> int:
    """0 when both loads committed, 1 on any failure, with both tables unchanged."""
    loads = []
    failed = False
    for tab, read in ((OWNER_TAB, read_owner), (ROLES_TAB, read_roles)):
        try:
            rows, problems = read()
        except Exception as exc:
            out(f"{tab}: not read ({_why(exc)})")
            failed = True
            continue
        if problems:
            failed = True
            for problem in problems:
                out(f"{tab}: stopped, {problem}")
        else:
            loads.append((tab, rows))
    if failed:
        out("load failed, nothing was loaded and both tables are as they were")
        return 1
    owner_rows, role_rows = dict(loads)[OWNER_TAB], dict(loads)[ROLES_TAB]
    try:
        with connect_to() as conn:
            before_owner, after_owner = conn.execute(
                OWNER_CALL, ([k for k, _ in owner_rows], [i for _, i in owner_rows])).fetchone()
            before_roles, after_roles = conn.execute(
                ROLES_CALL, ([i for i, _, _ in role_rows], [r for _, r, _ in role_rows])).fetchone()
    except Exception as exc:
        out(f"load failed, both tables are as they were ({_why(exc)})")
        return 1
    out(f"owner crosswalk: {before_owner} rows before, {after_owner} after, {_changed(before_owner, after_owner)}")
    out(f"app roles: {before_roles} rows before, {after_roles} after, {_changed(before_roles, after_roles)}")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        return run()
    except Exception as exc:
        say(f"load failed, both tables are as they were ({type(exc).__name__})")
        return 1


if __name__ == "__main__":
    sys.exit(main())

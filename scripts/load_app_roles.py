"""Write the SQL for the app role table (ADR-0026 decision 2; #662).

    load_app_roles.py --gid GID --out PATH

Reads the `App roles` tab of the team-manifest workbook live, as the Sheets
service account (`etl.read_sheet_tab`, the reader the crosswalk loader uses), on
the tab's two columns `Discord` and `Role`: one row per person and role. `Discord`
is digits only, 17 to 20 long, plain text; `Role` is `owner`, `commissioner` or
`app_admin`, exactly (generate_migrations.ROLE_WORDS; ADR-0026 decision 2 as
amended 2026-11-26). The tab's gid exists only once the owner has made the tab,
so it is an argument. It checks everything first and writes nothing unless every
check passes: a blank cell, an id that is not 17 to 20 digits, a role that is
none of the three words, a repeated (id, role) pair, an id that arrives as a number (a
spreadsheet keeps 15 significant digits of a number, so the id is already wrong:
the column must be plain text) or an empty tab stops it, and so does a sign-in
failure (the `SheetsAuthError` line, which names no path and no key).

Each owner and commissioner row gets the one league there is until the second PR
of #675 adds the league table (generate_migrations.LEAGUE_PLACEHOLDER), and each
app admin row gets generate_migrations.ALL_LEAGUES. That PR reads the tab's league
column and turns it into a league key.

It connects to nothing and reads no table (only the sheet), so ETL_STORAGE does not
matter to it. It writes one new SQL file to PATH, which must not exist and must lie outside every git
repository: one transaction that deletes every row of shared.app_role and inserts
the tab's rows (so a role removed from the tab is gone), and ends in a SELECT of
the row counts. The owner runs it in the Supabase SQL editor and deletes it. The
file holds Discord ids. The script prints the path and counts (rows, people,
owners, commissioners, app admins) and a stop prints row numbers and counts: never an id.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))
import etl_helpers as etl  # noqa: E402
from etl_helpers import CFG  # noqa: E402
from generate_migrations import ADMIN_ROLE, ALL_LEAGUES, LEAGUE_PLACEHOLDER, ROLE_WORDS  # noqa: E402
from load_contract_choices import inside_git_repo, literal  # noqa: E402
from load_owner_crosswalk import AS_NUMBERS, id_text, is_id  # noqa: E402

TARGET = "shared.app_role"
ID_COLUMN = "Discord"
ROLE_COLUMN = "Role"
COLUMNS = [ID_COLUMN, ROLE_COLUMN]
LEAGUE_OF = {role: ALL_LEAGUES if role == ADMIN_ROLE else LEAGUE_PLACEHOLDER for role in ROLE_WORDS}


def resolve(frame: pd.DataFrame) -> tuple[list[tuple[str, str, str]], list[str]]:
    """The (id, role, league_key) rows and the problems found. A problem is a count
    and the tab's row numbers (the header is row 1), never a value."""
    missing = [c for c in COLUMNS if frame is None or c not in frame.columns]
    if missing:
        return [], [f"the App roles tab lacks the column(s) {', '.join(missing)}"]
    frame = frame[COLUMNS].dropna(how="all")
    if frame.empty:
        return [], ["the App roles tab has no rows"]
    ids = id_text(frame[ID_COLUMN])
    if ids is None:
        return [], [AS_NUMBERS]
    labels = {"blank": "row(s) with a blank id or role",
              "id": "row(s) whose id is not 17 to 20 digits",
              "role": "row(s) whose role is not owner, commissioner or app_admin",
              "twice": "row(s) repeating an id and role pair"}
    where = {k: [] for k in labels}
    rows, seen = [], set()
    for number, person, role in zip(frame.index + 2, ids, frame[ROLE_COLUMN]):
        role = "" if pd.isna(role) else str(role).strip()
        if not person or not role:
            where["blank"].append(number)
            continue
        if not is_id(person):
            where["id"].append(number)
            continue
        if role not in LEAGUE_OF:
            where["role"].append(number)
            continue
        if (person, role) in seen:
            where["twice"].append(number)
            continue
        seen.add((person, role))
        rows.append((person, role, LEAGUE_OF[role]))
    problems = [f"{len(where[k])} {labels[k]} (rows {', '.join(str(n) for n in where[k])})" for k in labels if where[k]]
    return sorted(rows), problems


def counts(rows: list[tuple[str, str, str]]) -> dict:
    return {"rows": len(rows), "people": len({person for person, _, _ in rows}),
            "owners": sum(1 for _, role, _ in rows if role == "owner"),
            "commissioners": sum(1 for _, role, _ in rows if role == "commissioner"),
            "app_admins": sum(1 for _, role, _ in rows if role == ADMIN_ROLE)}


def sql_file(rows: list[tuple[str, str, str]]) -> str:
    values = ",\n".join(f"    ({literal(person)}, {literal(role)}, {literal(league)})" for person, role, league in rows)
    return ("BEGIN;\n"
            f"DELETE FROM {TARGET};\n"
            f"INSERT INTO {TARGET} (discord_user_id, role, league_key)\nVALUES\n{values};\n"
            f"SELECT count(*) AS rows_loaded, count(DISTINCT discord_user_id) AS people FROM {TARGET};\n"
            "COMMIT;\n")


def load(out_path: Path, gid: str, *, out=print) -> int:
    """Run the checks, then write the file. Returns 0 on success, 1 on a stop."""
    out_path = Path(out_path)
    stops = []
    if not str(gid).isascii() or not str(gid).isdigit():
        stops.append("--gid is not the digits of the App roles tab's gid")
    resolved = out_path.resolve()
    if inside_git_repo(out_path) or REPO == resolved or REPO in resolved.parents:
        stops.append("--out lies inside a git repository; name a path outside every repository")
    elif not out_path.parent.is_dir():
        stops.append("the folder of --out does not exist")
    elif out_path.exists():
        stops.append("--out already exists; name a path that does not, so an earlier file is never left to paste")
    if stops:
        for line in stops:
            out(f"stopped: {line}")
        out("nothing was written")
        return 1
    try:
        frame = etl.read_sheet_tab(CFG.team_sheet_id, str(gid), COLUMNS, text=[ID_COLUMN])
    except etl.SheetsNumberCells as exc:
        out(f"stopped: {AS_NUMBERS}")
        out(f"stopped: {exc}")
        out("nothing was written")
        return 1
    except (etl.SheetsAuthError, RuntimeError) as exc:
        out(f"stopped: {(str(exc).splitlines() or [''])[0]}")
        out("nothing was written")
        return 1
    rows, problems = resolve(frame)
    if problems:
        for line in problems:
            out(f"stopped: {line}")
        out("nothing was written")
        return 1
    out_path.write_text(sql_file(rows), encoding="utf-8", newline="\n")
    found = counts(rows)
    out(f"wrote: {out_path}")
    out(f"rows: {found['rows']}")
    out(f"people: {found['people']}")
    out(f"owners: {found['owners']}")
    out(f"commissioners: {found['commissioners']}")
    out(f"app admins: {found['app_admins']}")
    out("when run, the file replaces every row of the role table and returns rows_loaded and people")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gid", required=True, help="the gid of the App roles tab (the number after gid= in its address)")
    ap.add_argument("--out", type=Path, required=True, help="the SQL file to write, outside every repository")
    args = ap.parse_args(argv)
    try:
        return load(args.out, args.gid)
    except etl.StorageError as exc:
        print(f"stopped: {type(exc).__name__}: {(str(exc).splitlines() or [''])[0]}")
        return 1
    except Exception as exc:
        print(f"stopped: {type(exc).__name__} (no detail printed: it may hold a value)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

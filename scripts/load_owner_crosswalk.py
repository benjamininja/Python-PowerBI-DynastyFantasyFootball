"""Write the SQL for the owner crosswalk (ADR-0025 decisions 5 and 7; #548 brief 3).

    load_owner_crosswalk.py --out PATH

Reads the owner tab of the team-manifest workbook live, as the Sheets service
account (`etl.read_sheet_tab`, the reader 01c uses), on the two columns `team`
and `discord_user_id`: one row per owner per team. It reads no xlsx. `team`
resolves to a team_key through dim_fantasy_teams (exact team_name, one team);
`discord_user_id` is digits only, 17 to 20 long. It checks everything first and
writes nothing unless every check passes: a team that does not resolve, an id
that is not 17 to 20 digits, a blank cell, a duplicate (team, id) pair, an id
that arrives as a number (a spreadsheet keeps 15 significant digits of a number,
so the id is already wrong: the column must be plain text), or an empty tab
stops it, and so does a sign-in failure (the `SheetsAuthError` line,
which names no path and no key).

It connects to nothing, and stops when ETL_STORAGE selects the database: it
reads the published snapshot only. It writes one new SQL file to PATH, which
must not exist and must lie outside every git repository: one transaction that
deletes every row of shared.owner_crosswalk and inserts the tab's rows (so an
owner removed from the tab loses access), and ends in a SELECT of the row count.
The owner runs it in the Supabase SQL editor and deletes it. The file holds
Discord ids. The script prints the path and counts (rows, teams, co-owned teams)
and a stop prints row numbers and counts: never an id and never a name.
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))
import etl_helpers as etl  # noqa: E402
from etl_helpers import CFG  # noqa: E402
from load_contract_choices import inside_git_repo, literal  # noqa: E402

TEAMS_TABLE = "dim_fantasy_teams"
TARGET = "shared.owner_crosswalk"
ID_COLUMN = "discord_user_id"
COLUMNS = ["team", ID_COLUMN]
ID_LENGTHS = range(17, 21)


AS_NUMBERS = ("discord_user_id is stored as numbers, and a spreadsheet keeps only 15 significant digits of a "
              "number, so those ids are wrong; format the discord_user_id column as plain text "
              "(Format, Number, Plain text) and re-enter the ids")


def id_text(series: pd.Series) -> list[str] | None:
    """The id column as trimmed text, or None when any value is not text: every
    Discord id has 17 digits or more, and a spreadsheet keeps 15 significant
    digits of a number, so an id that arrives as a number is already wrong. An
    all-blank column gives blanks (the caller reports them as blank cells)."""
    if series.isna().all():
        return [""] * len(series)
    if series.dtype.kind != "O":
        return None
    out = []
    for value in series:
        if pd.isna(value):
            out.append("")
        elif isinstance(value, str):
            out.append(value.strip())
        else:
            return None
    return out


def is_id(value: str) -> bool:
    return len(value) in ID_LENGTHS and value.isascii() and value.isdigit()


def resolve(frame: pd.DataFrame, teams: pd.DataFrame) -> tuple[list[tuple[str, str]], list[str]]:
    """The (team_key, id) pairs and the problems found. A problem is a count and
    the tab's row numbers (the header is row 1), never a value."""
    missing = [c for c in COLUMNS if frame is None or c not in frame.columns]
    if missing:
        return [], [f"the owner tab lacks the column(s) {', '.join(missing)}"]
    frame = frame[COLUMNS].dropna(how="all")
    if frame.empty:
        return [], ["the owner tab has no rows"]
    ids = id_text(frame["discord_user_id"])
    if ids is None:
        return [], [AS_NUMBERS]
    by_team = {}
    for team_key, name in zip(teams["team_key"], teams["team_name"]):
        by_team.setdefault(str(name).strip(), []).append(team_key)
    labels = {"blank": "row(s) with a blank team or id",
              "team": "row(s) whose team does not resolve to one team",
              "id": "row(s) whose id is not 17 to 20 digits",
              "twice": "row(s) repeating a team and id pair"}
    where = {k: [] for k in labels}
    pairs, seen = [], set()
    for number, name, owner in zip(frame.index + 2, frame["team"], ids):
        name = "" if pd.isna(name) else str(name).strip()
        if not name or not owner:
            where["blank"].append(number)
            continue
        keys = by_team.get(name, [])
        if len(keys) != 1:
            where["team"].append(number)
            continue
        if not is_id(owner):
            where["id"].append(number)
            continue
        if (keys[0], owner) in seen:
            where["twice"].append(number)
            continue
        seen.add((keys[0], owner))
        pairs.append((keys[0], owner))
    problems = [f"{len(where[k])} {labels[k]} (rows {', '.join(str(n) for n in where[k])})" for k in labels if where[k]]
    return sorted(pairs), problems


def counts(pairs: list[tuple[str, str]]) -> dict:
    per_team = {}
    for team_key, _ in pairs:
        per_team[team_key] = per_team.get(team_key, 0) + 1
    return {"rows": len(pairs), "teams": len(per_team), "co_owned": sum(1 for n in per_team.values() if n > 1)}


def sql_file(pairs: list[tuple[str, str]]) -> str:
    values = ",\n".join(f"    ({literal(team_key)}, {literal(owner)})" for team_key, owner in pairs)
    return ("BEGIN;\n"
            f"DELETE FROM {TARGET};\n"
            f"INSERT INTO {TARGET} (team_key, discord_user_id)\nVALUES\n{values};\n"
            f"SELECT count(*) AS rows_loaded, count(DISTINCT team_key) AS teams FROM {TARGET};\n"
            "COMMIT;\n")


def load(out_path: Path, *, tables: dict | None = None, out=print) -> int:
    """Run the checks, then write the file. Returns 0 on success, 1 on a stop."""
    out_path = Path(out_path)
    stops = []
    if (os.environ.get("ETL_STORAGE") or "parquet") != "parquet":
        stops.append("ETL_STORAGE selects the database; the loader reads the published snapshot only")
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
        frame = etl.read_sheet_tab(CFG.team_sheet_id, CFG.owner_sheet_gid, COLUMNS, text=[ID_COLUMN])
    except etl.SheetsNumberCells as exc:
        out(f"stopped: {AS_NUMBERS}")
        out(f"stopped: {exc}")
        out("nothing was written")
        return 1
    except (etl.SheetsAuthError, RuntimeError) as exc:
        out(f"stopped: {(str(exc).splitlines() or [''])[0]}")
        out("nothing was written")
        return 1
    teams = etl.read_table(TEAMS_TABLE, ["team_key", "team_name"]) if tables is None else tables["teams"]
    pairs, problems = resolve(frame, teams)
    if problems:
        for line in problems:
            out(f"stopped: {line}")
        out("nothing was written")
        return 1
    out_path.write_text(sql_file(pairs), encoding="utf-8", newline="\n")
    found = counts(pairs)
    out(f"wrote: {out_path}")
    out(f"rows: {found['rows']}")
    out(f"teams: {found['teams']}")
    out(f"co-owned teams: {found['co_owned']}")
    out("when run, the file replaces every row of the crosswalk and returns rows_loaded and teams")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True, help="the SQL file to write, outside every repository")
    args = ap.parse_args(argv)
    try:
        return load(args.out)
    except etl.StorageError as exc:
        print(f"stopped: {type(exc).__name__}: {(str(exc).splitlines() or [''])[0]}")
        return 1
    except Exception as exc:
        print(f"stopped: {type(exc).__name__} (no detail printed: it may hold a value)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

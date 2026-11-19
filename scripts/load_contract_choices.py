"""Write the SQL for the 2026 FA keep choices (ADR-0025 decision 7, ADR-0024 decision 5; #548 brief 2).

    load_contract_choices.py XLSX --season SEASON_ID --out PATH [--tabs Riddell,Wilson]

XLSX is the commissioners' re-sign workbook, read as it is from the path given
and never committed. It is read on the tabs named by --tabs; each row is one FA
copy, with a team column whose header starts `Team`, a `Fantrax ID` column and
a `Resign` column. `Resign` Yes is keep and No is let_go (case-insensitive,
trimmed); a blank writes no row and counts as no choice; any other value stops.
The team resolves to a team_key through dim_fantasy_teams (exact team_name),
and the Fantrax ID is the scorer_id, so a copy is (team_key, scorer_id) and
must be an FA copy in fact_fantasy_teams. A No on a copy no longer an FA copy
on that team is skipped and counted; a Yes on one stops. `locked_value` is the copy's
salary in the price list for the season after SEASON_ID (the list's season is
a start year, so dim_season's season_start_year plus one).

The script connects to nothing, and stops when ETL_STORAGE selects the
database: it reads the published snapshot only. It checks everything first and
writes nothing unless every check passes. It writes one new SQL file to PATH,
which must not exist and must lie outside every git repository: one
transaction of inserts into app.contract_choices (choice_kind fa_keep, origin
loader, changed_by null). On a key already there the row is updated (choice and
locked_value) only where its origin is `loader`, so an owner's own choice is
never overwritten, and a second run leaves the same rows. When the owner runs
the file in the Supabase SQL editor it returns rows_written and
keys_left_alone (keys an owner's own row held). A copy the file does not list
gets no row: no row means no choice made (ADR-0025 decision 7). A stop prints
the tab name and the workbook's row numbers per problem, and counts otherwise:
never a name, a team or a cell.
"""
import argparse
import math
import os
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
import etl_helpers as etl  # noqa: E402

TEAMS_TABLE = "dim_fantasy_teams"
ROSTER_TABLE = "fact_fantasy_teams"
SEASON_TABLE = "dim_season"
TARGET = "app.contract_choices"
KEY = "(season_id, team_key, scorer_id, choice_kind)"
DEFAULT_TABS = "Riddell,Wilson"
CHOICES = {"yes": "keep", "no": "let_go"}
SEASON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def text(value) -> str:
    return " ".join(str(value).split()) if pd.notna(value) else ""


def inside_git_repo(path: Path) -> bool:
    """True when `path`, or any folder above it, holds a .git."""
    folder = Path(path).resolve().parent
    return any((p / ".git").exists() for p in (folder, *folder.parents))


def read_workbook(path: Path, tabs: list[str]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Per named tab, its team, scorer_id and resign columns as trimmed text,
    blank rows dropped, each row indexed by its spreadsheet row number (the
    header is row 1); and the structural problems (a tab or column missing),
    which name the tab and never a cell."""
    book = pd.ExcelFile(path)
    frames, problems = {}, []
    for tab in tabs:
        if tab not in book.sheet_names:
            problems.append(f"tab {tab}: the tab is not in the workbook")
            continue
        raw = pd.read_excel(book, sheet_name=tab, dtype=object)
        heads = {str(c).strip().casefold(): c for c in raw.columns}
        team_cols = [c for h, c in heads.items() if h.startswith("team")]
        missing = []
        if len(team_cols) != 1:
            missing.append("a single column whose header starts with Team")
        for want in ("fantrax id", "resign"):
            if want not in heads:
                missing.append(f"the {want.title() if want == 'resign' else 'Fantrax ID'} column")
        if missing:
            problems.append(f"tab {tab}: missing {', '.join(missing)}")
            continue
        frame = raw[[team_cols[0], heads["fantrax id"], heads["resign"]]].dropna(how="all")
        frame.columns = ["team", "scorer_id", "resign"]
        frame = frame.map(text)
        frame = frame[(frame != "").any(axis=1)]
        frame.index = frame.index + 2
        frames[tab] = frame
    return frames, problems


def literal(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NULL"
    if isinstance(value, float):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def resolve(frames: dict[str, pd.DataFrame], teams: pd.DataFrame, roster: pd.DataFrame,
            prices: pd.Series | None) -> tuple[list[dict], list[str], dict]:
    """The rows to write, the problems found (each a tab, a count and the
    workbook's row numbers, `frames` being indexed by them, never a value) and
    the counts: read, no choice, skipped (a No on a copy no longer FA there) and
    the FA copies the workbook does not list."""
    by_team = {}
    for team_key, name in zip(teams["team_key"], teams["team_name"]):
        by_team.setdefault(str(name).strip(), []).append(team_key)
    free = {(t, s) for t, s, c in zip(roster["team_key"], roster["scorer_id"], roster["contract_id"]) if c == "FA"}
    rows, listed = [], set()
    counts = {"read": 0, "no_choice": 0, "skipped": 0}
    labels = {"team": "row(s) whose team does not resolve to one team",
              "id": "row(s) with no Fantrax ID",
              "choice": "row(s) whose Resign is not Yes, No or blank",
              "twice": "row(s) listing a copy already listed",
              "kind": "row(s) with Yes on a copy that is not an FA copy on that team",
              "price": "row(s) whose copy has no price-list row"}
    problems = []
    for tab, frame in frames.items():
        where = {k: [] for k in labels}
        counts["read"] += len(frame)
        for number, team, scorer_id, resign in zip(frame.index, frame["team"], frame["scorer_id"], frame["resign"]):
            keys = by_team.get(team, [])
            if len(keys) != 1:
                where["team"].append(number)
                continue
            if not scorer_id:
                where["id"].append(number)
                continue
            if resign and resign.casefold() not in CHOICES:
                where["choice"].append(number)
                continue
            pair = (keys[0], scorer_id)
            if pair in listed:
                where["twice"].append(number)
                continue
            listed.add(pair)
            picked = CHOICES.get(resign.casefold())
            if picked is None:
                counts["no_choice"] += 1
            elif pair not in free:
                if picked == "let_go":
                    counts["skipped"] += 1
                else:
                    where["kind"].append(number)
            elif prices is None or scorer_id not in prices.index or pd.isna(prices[scorer_id]):
                where["price"].append(number)
            else:
                rows.append({"team_key": pair[0], "scorer_id": scorer_id, "choice": picked,
                             "locked_value": float(prices[scorer_id])})
        problems += [f"tab {tab}: {len(where[k])} {labels[k]} (rows {', '.join(str(n) for n in where[k])})"
                     for k in labels if where[k]]
    counts["unlisted"] = len(free - listed)
    return sorted(rows, key=lambda r: (r["team_key"], r["scorer_id"])), problems, counts


def sql_file(season_id: str, rows: list[dict]) -> str:
    values = ",\n".join(
        "    (" + ", ".join((literal(season_id), literal(r["team_key"]), literal(r["scorer_id"]),
                             "'fa_keep'", literal(r["choice"]), literal(r["locked_value"]),
                             "'loader'", "NULL")) + ")" for r in rows)
    short = TARGET.split(".")[1]
    return ("BEGIN;\n"
            "WITH written AS (\n"
            f"INSERT INTO {TARGET} (season_id, team_key, scorer_id, choice_kind, choice, locked_value, "
            "origin, changed_by)\nVALUES\n" + values + "\n"
            f"ON CONFLICT {KEY} DO UPDATE SET choice = EXCLUDED.choice, "
            "locked_value = EXCLUDED.locked_value\n"
            f"WHERE {short}.origin = 'loader'\n"
            "RETURNING 1\n)\n"
            f"SELECT count(*) AS rows_written, {len(rows)} - count(*) AS keys_left_alone FROM written;\n"
            "COMMIT;\n")


def price_season(seasons: pd.DataFrame, season_id: str) -> int | None:
    found = seasons[seasons["season_id"] == season_id]
    if found.empty or pd.isna(found["season_start_year"].iloc[0]):
        return None
    return int(found["season_start_year"].iloc[0]) + 1


def read_tables(season_id: str) -> dict:
    """The inputs, through the storage seam: the published snapshot."""
    seasons = etl.read_table(SEASON_TABLE, ["season_id", "season_start_year"])
    year = price_season(seasons, season_id)
    prices = None
    if year is not None:
        try:
            prices = etl.price_list(year)
        except etl.TableNotFound:
            prices = None
    return {"seasons": seasons, "prices": prices,
            "teams": etl.read_table(TEAMS_TABLE, ["team_key", "team_name"]),
            "roster": etl.read_table(ROSTER_TABLE, ["team_key", "scorer_id", "contract_id"])}


def load(xlsx: Path, season_id: str, out_path: Path, *, tabs: str = DEFAULT_TABS,
         tables: dict | None = None, out=print) -> int:
    """Run the checks, then write the file. Returns 0 on success, 1 on a stop."""
    xlsx, out_path = Path(xlsx), Path(out_path)
    stops = []
    if (os.environ.get("ETL_STORAGE") or "parquet") != "parquet":
        stops.append("ETL_STORAGE selects the database; the loader reads the published snapshot only")
    if not SEASON_ID.match(season_id):
        stops.append("--season is not a season id")
    if not xlsx.is_file():
        stops.append("the keep file path is not a file")
    if inside_git_repo(out_path):
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
    names = [t.strip() for t in tabs.split(",") if t.strip()]
    if not names:
        out("stopped: --tabs names no tab")
        out("nothing was written")
        return 1
    frames, problems = read_workbook(xlsx, names)
    if problems:
        for line in problems:
            out(f"stopped: {line}")
        out("nothing was written")
        return 1
    tables = read_tables(season_id) if tables is None else tables
    if price_season(tables["seasons"], season_id) is None:
        problems.append("--season is not a season of dim_season")
    if not sum(len(f) for f in frames.values()):
        problems.append("the workbook holds no row on the named tabs")
    rows, found, counts = resolve(frames, tables["teams"], tables["roster"], tables["prices"])
    problems += found
    out(f"read: {counts['read']} row(s)")
    if problems:
        for line in problems:
            out(f"stopped: {line}")
        out("nothing was written")
        return 1
    out_path.write_text(sql_file(season_id, rows), encoding="utf-8", newline="\n")
    out(f"no choice (blank Resign): {counts['no_choice']} row(s)")
    out(f"skipped (No on a copy no longer an FA copy on that team): {counts['skipped']} row(s)")
    out(f"wrote: {len(rows)} row(s) to the file")
    out(f"FA copies on the roster that the workbook does not list: {counts['unlisted']}")
    out("when run, the file returns rows_written and keys_left_alone (keys an owner's own row holds)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("xlsx", type=Path, help="the commissioners' re-sign workbook, read from this path")
    ap.add_argument("--tabs", default=DEFAULT_TABS,
                    help="comma-separated tabs to read (each with a Team..., Fantrax ID and Resign column)")
    ap.add_argument("--season", required=True, help="the season_id of dim_season the choices are made in")
    ap.add_argument("--out", type=Path, required=True, help="the SQL file to write, outside every repository")
    args = ap.parse_args(argv)
    try:
        return load(args.xlsx, args.season, args.out, tabs=args.tabs)
    except etl.StorageError as exc:
        print(f"stopped: {type(exc).__name__}: {(str(exc).splitlines() or [''])[0]}")
        return 1
    except Exception as exc:
        print(f"stopped: {type(exc).__name__} (no detail printed: it may hold a value)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

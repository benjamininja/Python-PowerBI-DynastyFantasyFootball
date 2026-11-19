"""Write the SQL for the 2026 FA keep choices (ADR-0025 decision 7, ADR-0024 decision 5; #548 brief 2).

    load_contract_choices.py XLSX --season SEASON_ID --out PATH

XLSX is the owner's keep file: columns `team`, `player` and `choice` (keep or
let go), one row per FA copy. It is read from the path given and is never
committed. `team` resolves to a team_key through dim_fantasy_teams, and
`player` to a scorer_id among that team's FA copies in fact_fantasy_teams
(player names come from dim_fantrax_crosswalk). `locked_value` is the copy's
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
the keep file's row numbers per problem, and counts otherwise: never a name, a
team or a cell.
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
CROSSWALK_TABLE = "dim_fantrax_crosswalk"
SEASON_TABLE = "dim_season"
TARGET = "app.contract_choices"
KEY = "(season_id, team_key, scorer_id, choice_kind)"
HEADERS = ("team", "player", "choice")
CHOICES = {"keep": "keep", "let go": "let_go"}
SEASON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def squash(value) -> str:
    return " ".join(str(value).split()).casefold() if pd.notna(value) else ""


def inside_git_repo(path: Path) -> bool:
    """True when `path`, or any folder above it, holds a .git."""
    folder = Path(path).resolve().parent
    return any((p / ".git").exists() for p in (folder, *folder.parents))


def read_file(path: Path) -> pd.DataFrame | None:
    """The file's team, player and choice columns, as text, with blank rows
    dropped and each row indexed by its spreadsheet row number (the header is
    row 1); None when a header is missing."""
    raw = pd.read_excel(path, sheet_name=0, dtype=object)
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    if not set(HEADERS) <= set(raw.columns):
        return None
    frame = raw[list(HEADERS)].dropna(how="all")
    frame.index = frame.index + 2
    return frame


def literal(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NULL"
    if isinstance(value, float):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def resolve(frame: pd.DataFrame, teams: pd.DataFrame, roster: pd.DataFrame,
            names: pd.DataFrame, prices: pd.Series | None) -> tuple[list[dict], list[str]]:
    """The rows to write and the problems found, each problem a count and the
    keep file's row numbers (`frame` is indexed by them), never a value."""
    by_team = {}
    for team_key, name in zip(teams["team_key"], teams["team_name"]):
        by_team.setdefault(squash(name), []).append(team_key)
    called = dict(zip(names["scorer_id"], names["player_name"]))
    held = roster.assign(_name=roster["scorer_id"].map(lambda s: etl.clean_player_name(called.get(s))))
    rows, listed = [], set()
    where = {k: [] for k in ("team", "player", "twice", "two", "kind", "choice", "price")}
    for number, team, player, choice in zip(frame.index, frame["team"], frame["player"], frame["choice"]):
        keys = by_team.get(squash(team), [])
        if len(keys) != 1:
            where["team"].append(number)
            continue
        team_key = keys[0]
        picked = CHOICES.get(squash(choice))
        if picked is None:
            where["choice"].append(number)
        wanted = etl.clean_player_name(player)
        if not wanted:
            where["player"].append(number)
            continue
        mine = held[(held["team_key"] == team_key) & (held["_name"] == wanted)]
        free = mine[mine["contract_id"] == "FA"]
        if free.empty and mine.empty:
            where["player"].append(number)
            continue
        if free.empty:
            where["kind"].append(number)
            continue
        if len(free) > 1:
            where["two"].append(number)
            continue
        scorer_id = free["scorer_id"].iloc[0]
        if (team_key, scorer_id) in listed:
            where["twice"].append(number)
            continue
        listed.add((team_key, scorer_id))
        if prices is None or scorer_id not in prices.index or pd.isna(prices[scorer_id]):
            where["price"].append(number)
            continue
        if picked is not None:
            rows.append({"team_key": team_key, "scorer_id": scorer_id, "choice": picked,
                         "locked_value": float(prices[scorer_id])})
    labels = {"team": "row(s) whose team does not resolve to one team",
              "player": "row(s) whose player is not on that team's roster",
              "kind": "row(s) whose player is on that team's roster but not as an FA contract",
              "two": "row(s) whose player matches two FA copies on that team",
              "twice": "row(s) listing a copy already listed",
              "choice": "row(s) whose choice is not keep or let go",
              "price": "row(s) whose copy has no price-list row"}
    problems = [f"{len(where[k])} {labels[k]} (file rows {', '.join(str(n) for n in where[k])})"
                for k in labels if where[k]]
    return sorted(rows, key=lambda r: (r["team_key"], r["scorer_id"])), problems


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
            "roster": etl.read_table(ROSTER_TABLE, ["team_key", "scorer_id", "contract_id"]),
            "names": etl.read_table(CROSSWALK_TABLE, ["scorer_id", "player_name"])}


def load(xlsx: Path, season_id: str, out_path: Path, *, tables: dict | None = None, out=print) -> int:
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
    frame = read_file(xlsx)
    if frame is None:
        out(f"stopped: the file has no {', '.join(HEADERS)} header row")
        out("nothing was written")
        return 1
    out(f"read: {len(frame)} row(s)")
    tables = read_tables(season_id) if tables is None else tables
    problems = []
    if price_season(tables["seasons"], season_id) is None:
        problems.append("--season is not a season of dim_season")
    if not len(frame):
        problems.append("the file holds no row")
    rows, found = resolve(frame, tables["teams"], tables["roster"], tables["names"], tables["prices"])
    problems += found
    if problems:
        for line in problems:
            out(f"stopped: {line}")
        out("nothing was written")
        return 1
    out_path.write_text(sql_file(season_id, rows), encoding="utf-8", newline="\n")
    free = tables["roster"][tables["roster"]["contract_id"] == "FA"]
    unlisted = len(free) - len({(r["team_key"], r["scorer_id"]) for r in rows})
    out(f"wrote: {len(rows)} row(s) to the file")
    out(f"FA copies on the roster that the file does not list: {unlisted}")
    out("when run, the file returns rows_written and keys_left_alone (keys an owner's own row holds)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("xlsx", type=Path, help="the owner's keep file, read from this path")
    ap.add_argument("--season", required=True, help="the season_id of dim_season the choices are made in")
    ap.add_argument("--out", type=Path, required=True, help="the SQL file to write, outside every repository")
    args = ap.parse_args(argv)
    try:
        return load(args.xlsx, args.season, args.out)
    except etl.StorageError as exc:
        print(f"stopped: {type(exc).__name__}: {(str(exc).splitlines() or [''])[0]}")
        return 1
    except Exception as exc:
        print(f"stopped: {type(exc).__name__} (no detail printed: it may hold a value)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

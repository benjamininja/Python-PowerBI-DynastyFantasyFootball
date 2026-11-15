"""Loader for the yearly price list (#554; map #557 decisions 8.2 to 8.4).

    load_price_list.py XLSX --season N --pulled-on YYYY-MM-DD [--check]

XLSX is the owner's hand Players export, taken once a year right after the
commissioners run Recalculate Salaries. It is read from the path given and is
never committed. Only its ID and Salary columns are kept, one row per player,
rostered or not. --season is the season the prices take effect for, as a start
year (2027 for 2027-28); --pulled-on is the day of the export.

Checks first, writes after: nothing is written unless every check passes, and a
season that already holds rows is refused, so a season is loaded once. The
season check runs again inside the write (etl.write_table_checked, under the
table lock on Postgres), so two overlapping runs cannot replace each other.
--check runs the checks and stops. It prints counts, never an id, a name or a
salary. The rows go to fact_salary_price_list through the storage seam, one
season at a time, so earlier seasons stay.
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))
import etl_helpers as etl  # noqa: E402
from load_draft_and_overrides import use_env_file  # noqa: E402

TABLE = etl.PRICE_LIST_TABLE
CROSSWALK_TABLE = "dim_fantrax_crosswalk"
ID_HEADER, SALARY_HEADER = "id", "salary"
HEADER_SCAN_ROWS = 20
_MONEY = re.compile(r"[$,\s]")


def find_header(raw: pd.DataFrame) -> int | None:
    """The first row, within the top rows, whose cells include both an ID and a
    Salary header (any case, spaces trimmed); None when there is none."""
    for i in range(min(HEADER_SCAN_ROWS, len(raw))):
        cells = {str(c).strip().lower() for c in raw.iloc[i] if pd.notna(c)}
        if {ID_HEADER, SALARY_HEADER} <= cells:
            return i
    return None


def read_export(path: Path) -> pd.DataFrame | None:
    """The export's `id` and `salary` columns as they are in the sheet, or None
    when no header row holds both. Every other column is dropped here."""
    raw = pd.read_excel(path, sheet_name=0, header=None, dtype=object)
    top = find_header(raw)
    if top is None:
        return None
    names = [str(c).strip().lower() if pd.notna(c) else "" for c in raw.iloc[top]]
    body = raw.iloc[top + 1:].reset_index(drop=True)
    body.columns = names
    return body[[ID_HEADER, SALARY_HEADER]].rename(columns={ID_HEADER: "scorer_id"})


def clean_id(value) -> str | None:
    """A Fantrax id as scorer_id: trimmed, with the asterisks Fantrax wraps it
    in taken off. A blank is None."""
    if pd.isna(value):
        return None
    text = str(value).strip().strip("*").strip()
    return text or None


def parse_salary(value) -> float:
    """A number, or text like `15,460,000` or `$15,460,000`, as dollars rounded
    to the cent; NaN when it is neither."""
    if value is None or isinstance(value, bool) or (not isinstance(value, str) and pd.isna(value)):
        return float("nan")
    if isinstance(value, str):
        value = _MONEY.sub("", value)
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return float("nan")


def build_table(raw: pd.DataFrame, season: int, pulled_on: str) -> tuple[pd.DataFrame, list[str]]:
    """The table's rows and the problems found building them, by count only."""
    problems = []
    frame = pd.DataFrame({"scorer_id": raw["scorer_id"].map(clean_id),
                          "salary": raw["salary"].map(parse_salary),
                          "has_salary": raw["salary"].notna()})
    frame = frame[frame["scorer_id"].notna() | frame["has_salary"]].reset_index(drop=True)
    blank = int(frame["scorer_id"].isna().sum())
    if blank:
        problems.append(f"{blank} row(s) with a Salary and no ID")
    frame = frame[frame["scorer_id"].notna()]
    unreadable = int(frame["salary"].isna().sum())
    if unreadable:
        problems.append(f"{unreadable} row(s) whose Salary is blank or not a number")
    negative = int((frame["salary"] < 0).sum())
    if negative:
        problems.append(f"{negative} row(s) with a negative Salary")
    repeated = int(frame["scorer_id"].duplicated(keep=False).sum())
    if repeated:
        problems.append(f"{repeated} row(s) share an ID with another row")
    if not len(frame):
        problems.append("the export holds no player row")
    out = pd.DataFrame({"season": pd.Series(season, index=frame.index, dtype="int64"),
                        "scorer_id": frame["scorer_id"],
                        "salary": frame["salary"].astype("float64"),
                        "pulled_on": pulled_on})
    return out.reset_index(drop=True), problems


def argument_problems(season: int, pulled_on: str) -> list[str]:
    problems = []
    try:
        day = date.fromisoformat(pulled_on)
    except ValueError:
        return [f"--pulled-on is not a YYYY-MM-DD date: {pulled_on!r}"]
    if day.isoformat() != pulled_on:
        problems.append(f"--pulled-on is not a YYYY-MM-DD date: {pulled_on!r}")
    if day.year not in (season - 1, season):
        problems.append(f"--pulled-on {pulled_on} is not in {season - 1} or {season}, the years "
                        f"a pull for season {season} falls in")
    return problems


def held_problems(season: int, stored: dict) -> list[str]:
    """The stop when the stored table (`{TABLE: frame or None}`) holds `season`."""
    frame = stored.get(TABLE)
    if frame is not None and bool((frame["season"] == season).any()):
        return [f"{TABLE} already holds rows for season {season}; a season is loaded once"]
    return []


def load(path: Path, season: int, pulled_on: str, *, check_only: bool = False, out=print) -> int:
    """Run the checks, then the write. Returns 0 on success, 1 on a stop."""
    path = Path(path)
    if not path.is_file():
        out("stopped: the export path is not a file")
        return 1
    problems = argument_problems(season, pulled_on)
    raw = read_export(path)
    if raw is None:
        problems.append(f"no header row holds both an {ID_HEADER.upper()} and a "
                        f"{SALARY_HEADER.capitalize()} column")
        table = None
    else:
        table, built = build_table(raw, season, pulled_on)
        problems += built
        out(f"read: {len(table)} player row(s)")
    problems += held_problems(season, {TABLE: etl.read_table(TABLE, ["season"])
                                       if etl.table_exists(TABLE) else None})
    if table is not None and etl.table_exists(CROSSWALK_TABLE):
        known = etl.read_table(CROSSWALK_TABLE, ["scorer_id"])["scorer_id"]
        out(f"info: {int((~table['scorer_id'].isin(known)).sum())} id(s) not in {CROSSWALK_TABLE}")
    if problems:
        for line in problems:
            out(f"stopped: {line}")
        out("nothing was written")
        return 1
    try:
        etl._check_batch(table, etl._table_entry(TABLE))
    except etl.StorageError as exc:
        out(f"stopped: {str(exc).splitlines()[0]}")
        out("nothing was written")
        return 1
    if check_only:
        out("checks passed; nothing was written (--check)")
        return 0
    try:
        checked = etl.write_table_checked(TABLE, table, reads={TABLE: ["season"]},
                                          check=lambda stored: held_problems(season, stored))
    except etl.LockWaitTimeout as exc:
        out(f"stopped: {exc}")
        out("nothing was written")
        return 1
    except etl.StorageError as exc:
        out(f"stopped: {(str(exc).splitlines() or [''])[0]}")
        out("nothing was written")
        return 1
    if checked.problems:
        for line in checked.problems:
            out(f"stopped: {line}")
        out("nothing was written")
        return 1
    out(f"wrote {TABLE}: {len(table)} row(s) for season {season}; the table holds {checked.total}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("xlsx", type=Path, help="the Players export, read from this path")
    ap.add_argument("--season", type=int, required=True,
                    help="the season the prices take effect for, as a start year")
    ap.add_argument("--pulled-on", required=True, help="the day of the export, YYYY-MM-DD")
    ap.add_argument("--check", action="store_true", help="run the checks, write nothing")
    args = ap.parse_args(argv)
    print(f"storage: {use_env_file()}")
    try:
        return load(args.xlsx, args.season, args.pulled_on, check_only=args.check)
    except etl.StorageError as exc:
        print(f"stopped: {type(exc).__name__}: {(str(exc).splitlines() or [''])[0]}")
        return 1
    except Exception as exc:
        print(f"stopped: {type(exc).__name__} (no detail printed: it may hold a value)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

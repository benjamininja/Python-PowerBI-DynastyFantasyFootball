# %% [markdown]
# # 02h_fact_team_cap  (the published per-team cap table)
#
# **Purpose:** `fact_team_cap`, one team's cap figures for this season and the
# next (ADR-0016's #97 amendment, decisions 4 and 5). The rules are `etl_cap`'s.
# This season is the `season` on `fact_fantasy_teams`, never the calendar.
#
# **Fantrax's Salary Remaining** sits on the current-season row, parsed from
# the newest `standings` reply `04s` saved for that season. No such file leaves
# it null. The Review check `salary_remaining` compares it.
#
# **Grain:** `(season_id, team_key)`, rewritten whole through the storage seam.
#
# **Run:**  python notebooks/02h_fact_team_cap.py [--raw-dir DIR]
#   (after 02f and 02e; no network.)

# %%
import argparse
import importlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
import etl_cap as cap
import etl_helpers as etl

rs = importlib.import_module("04r_fantrax_roster_state")

STANDINGS_FILE = re.compile(r"fantrax_inseason_(\d{4})_p(\d+)\.json$")
SALARY_KEY = "salaryRem"
MONEY = re.compile(r"-?\$?-?\d[\d,]*(\.\d+)?")

COLUMNS = cap.TEAM_CAP_COLUMNS + ["roster_captured_at", "fantrax_salary_remaining",
                                  "fantrax_captured_at", "fantrax_period"]


# %%
def parse_money(text) -> float:
    """A served Salary Remaining ("$1,234,567.00") as a number. A value that
    is not plainly money raises; the message never holds a raw value."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    s = str(text).strip()
    if not MONEY.fullmatch(s):
        raise ValueError(f"standings: a {SALARY_KEY} cell is not an amount")
    return float(s.replace("$", "").replace(",", ""))


def parse_salary_remaining(reply: dict, teams: pd.DataFrame) -> pd.Series:
    """A plain getStandings reply -> team_key -> Salary Remaining. The first
    table holds the league; the column is found by its header key. The teams
    must be exactly dim_fantasy_teams'."""
    table = reply["responses"][0]["data"]["tableList"][0]
    keys = [c.get("key") for c in table["header"]["cells"]]
    if SALARY_KEY not in keys:
        raise ValueError(f"standings: no {SALARY_KEY} column in the header")
    col = keys.index(SALARY_KEY)
    key_of = dict(zip(teams["fantrax_team_id"], teams["team_key"]))
    out = {}
    for row in table["rows"]:
        ids = [c["teamId"] for c in row.get("fixedCells", []) if c.get("teamId")]
        if len(ids) != 1 or ids[0] not in key_of:
            raise ValueError("standings: a row does not name one known team")
        if key_of[ids[0]] in out:
            raise ValueError("standings: a team is listed twice")
        out[key_of[ids[0]]] = parse_money(row["cells"][col]["content"])
    missing = sorted(set(teams["team_key"]) - set(out))
    if missing:
        raise ValueError(f"standings: {len(missing)} team(s) missing: {missing}")
    return pd.Series(out, name="fantrax_salary_remaining", dtype="float64")


def newest_standings(raw_dir, season_id: str) -> tuple[Path, dict] | None:
    """The newest saved period file of this season that holds a standings
    reply, by its `captured_at`; None when there is none. A closed period's
    file keeps its last capture, so the file's own stamp decides."""
    year = int(season_id.split("-")[0])
    found = []
    for path in Path(raw_dir).glob("fantrax_inseason_*_p*.json"):
        m = STANDINGS_FILE.search(path.name)
        if not m or int(m.group(1)) != year:
            continue
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            print(f"[warn] {path.name} is not valid JSON: skipped")
            continue
        if body.get("captured_at") and body.get("standings"):
            found.append((pd.Timestamp(body["captured_at"]), path, body))
    if not found:
        return None
    _, path, body = max(found, key=lambda f: (f[0], f[1].name))
    return path, body


def with_fantrax(table: pd.DataFrame, roster: pd.DataFrame, newest,
                 teams: pd.DataFrame) -> pd.DataFrame:
    """Stamp the current-season rows with the roster read and with Fantrax's
    number, its capture instant and its period. Other rows stay null. The
    number only feeds a Review check, so a reply that cannot be read leaves it
    null with a warning and never holds the Chain."""
    out = table.copy()
    current = out["is_current_season"]
    read = pd.to_datetime(roster["roster_captured_at"], utc=True).max()
    out["roster_captured_at"] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[us, UTC]")
    out["fantrax_captured_at"] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[us, UTC]")
    out["fantrax_salary_remaining"] = pd.Series(float("nan"), index=out.index, dtype="float64")
    out["fantrax_period"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out.loc[current, "roster_captured_at"] = read
    if newest is not None:
        path, body = newest
        try:
            remaining = parse_salary_remaining(body["standings"], teams)
            period = int(body["period"])
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:
            print(f"[warn] {path.name}: standings not read ({type(e).__name__}: {e}); "
                  "Salary Remaining left null")
        else:
            out.loc[current, "fantrax_salary_remaining"] = (
                out.loc[current, "team_key"].map(remaining))
            out.loc[current, "fantrax_captured_at"] = pd.Timestamp(body["captured_at"])
            out.loc[current, "fantrax_period"] = period
    return out[COLUMNS]


# %%
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build fact_team_cap.")
    ap.add_argument("--raw-dir", type=Path, default=None,
                    help="where 04s's raw files are (default: 04a's raw dir)")
    args = ap.parse_args(argv)
    raw_dir = Path(args.raw_dir or rs.FX_CFG.raw_dir)

    roster = etl.read_table("fact_fantasy_teams")
    teams = etl.read_table("dim_fantasy_teams")
    table = cap.team_cap(roster, etl.read_table("fact_dead_money"), teams,
                         etl.read_table("dim_contract"), etl.read_table("dim_season"))
    season_id = cap.roster_season(roster)
    newest = newest_standings(raw_dir, season_id)
    fact = with_fantrax(table, roster, newest, teams)
    total = etl.write_table("fact_team_cap", fact)

    now_row = fact[fact["is_current_season"]]
    print(f"[ok] fact_team_cap: {total} rows, {now_row['team_key'].nunique()} teams, "
          f"this season {season_id} (the roster's)")
    print("[info] standings: " + (f"{newest[0].name}, captured {newest[1]['captured_at']}"
                                  if newest else f"none for {season_id} in {raw_dir}"))
    over = now_row[now_row["cap_room"] < 0]
    print(f"[info] cap room: min {now_row['cap_room'].min():,.0f}, {len(over)} team(s) over; "
          f"Dead Money {now_row['dead_money'].sum():,.0f}; "
          f"IR salary {now_row['ir_salary'].sum():,.0f}; "
          f"reinvestment {now_row['reinvestment_cap'].sum():,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

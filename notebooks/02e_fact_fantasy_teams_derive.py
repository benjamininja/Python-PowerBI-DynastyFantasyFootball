# %% [markdown]
# # 02e_fact_fantasy_teams_derive  (current roster + provenance + cap charge)
#
# **Purpose:** the current Roster State, `fact_fantasy_teams`, all year
# (ADR-0016 decision 8 and its #97 amendment). The roster is Fantrax's as
# observed: the newest getTeamRosters reply `04r` saved (it reads the
# current roster on every run). The ledger adds provenance: how and when the
# copy joined the team. `etl_cap` stamps each row's charge: salary in the
# Minors or IR slot is cap-exempt (owner's ruling 2026-10-12).
#
# **Grain:** `(team_key, scorer_id)`, one row per player copy (one copy per
# Conference). Written through the storage seam.
#
# **Provenance:** `acquired_method` / `acquired_date` come from the ledger move
# that opened the copy's open stint on that team. A roster row with no open
# stint is `unknown`, never guessed. Membership is checked by `etl_checks`
# (`roster_membership`, Review), which reads `roster_captured_at` and
# `ledger_captured_at`.
#
# **No saved reply:** in the regular season or the playoffs the run fails.
# Otherwise it builds from the ledger replay with slots blank (every salary
# charged), and the Review check files one finding.
#
# **Run:**  python notebooks/02e_fact_fantasy_teams_derive.py [--raw-dir DIR]
#   (after 04r, 02d and 02f; no network.)

# %%
import argparse
import importlib
import sys
from pathlib import Path

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
import etl_cap as cap
import etl_helpers as etl

rs = importlib.import_module("04r_fantrax_roster_state")

TXN_FILES = "fantrax_txn_history_*.json"
UNKNOWN = "unknown"

COLUMNS = ["team_key", "scorer_id", "gsis_id", "player_key", "contract_id",
           "contract_value", "contract_year", "cap_hit", "cap_exempt",
           "acquired_method", "acquired_date", "roster_slot", "season",
           "roster_captured_at", "ledger_captured_at"]


# %%
def in_season(periods: pd.DataFrame, now) -> bool:
    """Is `now` inside a season's Scoring Periods (regular season or playoffs)?"""
    bounds = periods.groupby("season_id").agg(start=("start_at", "min"), end=("end_at", "max"))
    return bool(((bounds["start"] <= now) & (now <= bounds["end"])).any())


def ledger_captured_at(raw_dir) -> pd.Timestamp:
    """When the newest transaction capture was written (04t stamps no time of
    its own), or NaT when there is none."""
    files = list(Path(raw_dir).glob(TXN_FILES))
    if not files:
        return pd.NaT
    return pd.Timestamp(max(f.stat().st_mtime for f in files), unit="s", tz="UTC")


def identity(scorer_ids: pd.Series, assets: pd.DataFrame,
             crosswalk: pd.DataFrame) -> pd.DataFrame:
    """scorer_id -> gsis_id / player_key: the ledger's player asset first,
    then dim_fantrax_crosswalk."""
    out = pd.DataFrame({"scorer_id": scorer_ids})
    for src in (assets[assets["scorer_id"].notna()], crosswalk):
        ids = src.drop_duplicates("scorer_id").set_index("scorer_id")
        for col in ("gsis_id", "player_key"):
            got = out["scorer_id"].map(ids[col])
            out[col] = out[col].fillna(got) if col in out else got
    return out[["gsis_id", "player_key"]].set_axis(scorer_ids.index)


def finish(rows: pd.DataFrame, stints: pd.DataFrame, contracts: pd.DataFrame,
           assets: pd.DataFrame, crosswalk: pd.DataFrame, season_id: str,
           roster_at, ledger_at) -> pd.DataFrame:
    """Roster rows (team_key, scorer_id, roster_slot, salary, contract_id) ->
    fact_fantasy_teams: provenance, identity, contract year and cap charge."""
    opened = stints.set_index(["team_key", "scorer_id"])
    key = pd.MultiIndex.from_frame(rows[["team_key", "scorer_id"]])
    method = pd.Series(opened["event_type"].reindex(key).to_numpy(), index=rows.index)
    when = pd.Series(opened["event_date"].reindex(key).to_numpy(), index=rows.index)
    ids = identity(rows["scorer_id"], assets, crosswalk)
    charge = cap.stamp_cap(rows["roster_slot"], rows["salary"])
    year = rows["contract_id"].map(contracts.set_index("contract_id")["contract_year"])
    fact = pd.DataFrame({
        "team_key": rows["team_key"].astype("str"),
        "scorer_id": rows["scorer_id"].astype("str"),
        "gsis_id": ids["gsis_id"],
        "player_key": ids["player_key"],
        "contract_id": rows["contract_id"],
        "contract_value": rows["salary"].astype("float64"),
        "contract_year": pd.to_numeric(year).astype("float64"),
        "cap_hit": charge["cap_hit"],
        "cap_exempt": charge["cap_exempt"],
        "acquired_method": method.fillna(UNKNOWN).astype("str"),
        "acquired_date": pd.to_datetime(when).astype("datetime64[us]"),
        "roster_slot": rows["roster_slot"].astype("object"),
        "season": season_id,
        "roster_captured_at": pd.Series(roster_at, index=rows.index,
                                        dtype="datetime64[us, UTC]"),
        "ledger_captured_at": pd.Series(ledger_at, index=rows.index,
                                        dtype="datetime64[us, UTC]"),
    })
    return fact.sort_values(["team_key", "scorer_id"], ignore_index=True)[COLUMNS]


def from_reply(body: dict, season_id: str, stints, teams, contracts, assets,
               crosswalk, roster_at, ledger_at) -> pd.DataFrame:
    """The saved getTeamRosters reply -> fact_fantasy_teams. Parsed by 04r's
    own checks and parser, so a reply it would refuse is refused here too."""
    rs.check_reply(body, None, set(teams["fantrax_team_id"]))
    rows = rs.rosters_to_state(body, teams, set(contracts["contract_id"]), season_id,
                               int(body["period"]), rs.league_day(roster_at))
    return finish(rows, stints, contracts, assets, crosswalk, season_id, roster_at, ledger_at)


def from_replay(ledger: pd.DataFrame, stints, contracts, assets, crosswalk,
                ledger_at) -> pd.DataFrame:
    """No saved reply, out of season: the open stints, at their ledger terms,
    with no Roster Slot (so every salary is charged)."""
    season_id = ledger["season_id"].dropna().max()
    rows = pd.DataFrame({
        "team_key": stints["team_key"], "scorer_id": stints["scorer_id"],
        "roster_slot": pd.Series(pd.NA, index=stints.index, dtype="object"),
        "salary": stints["contract_value"], "contract_id": stints["contract_id"]})
    return finish(rows, stints, contracts, assets, crosswalk, season_id, pd.NaT, ledger_at)


def cap_summary(fact: pd.DataFrame, dead: pd.DataFrame | None,
                teams: pd.DataFrame) -> pd.DataFrame:
    """Per team, this season only (the roster's own `season`): charged salary,
    this season's Dead Money and the cap room left. Printed, not published
    (the cap table is fact_team_cap's)."""
    season = fact["season"].iloc[0] if len(fact) else None
    roll = fact.groupby("team_key")["cap_hit"].sum().rename("charged_salary")
    out = teams.set_index("team_key")[["original_cap", "reinvestment_cap"]].join(roll)
    dm = (cap.dead_money_by_team(dead, season) if dead is not None
          else pd.Series(dtype="float64", name="dead_money"))
    out = out.join(dm).fillna({"charged_salary": 0.0, "dead_money": 0.0})
    out["cap_room"] = (out["original_cap"] - out["charged_salary"]
                       - out["dead_money"] - out["reinvestment_cap"]).round(2)
    return out.reset_index()


# %%
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build fact_fantasy_teams.")
    ap.add_argument("--raw-dir", type=Path, default=None,
                    help="where 04r's and 04t's raw files are (default: 04a's raw dir)")
    args = ap.parse_args(argv)
    raw_dir = Path(args.raw_dir or rs.FX_CFG.raw_dir)
    now = pd.Timestamp.now(tz="UTC")

    ledger = etl.read_table("fact_roster_transactions")
    assets = etl.read_table("dim_roster_asset")
    teams = etl.read_table("dim_fantasy_teams")
    contracts = etl.read_table("dim_contract")
    crosswalk = etl.read_table("dim_fantrax_crosswalk")
    periods = etl.read_table("dim_scoring_period")
    stints = cap.open_stints(ledger)
    ledger_at = ledger_captured_at(raw_dir)

    newest = rs.newest_reply(raw_dir)
    if newest is not None:
        path, body, roster_at, season_id = newest
        fact = from_reply(body, season_id, stints, teams, contracts, assets, crosswalk,
                          roster_at, ledger_at)
        print(f"[info] roster: {path.name} (period {int(body['period'])}, {season_id}, "
              f"read {roster_at.isoformat()}"
              f"{'' if body.get('captured_at') else ', the file time: no stamp'})")
    elif in_season(periods, now):
        raise FileNotFoundError(f"no saved getTeamRosters reply in {raw_dir} during the "
                                "season -- run 04r")
    else:
        fact = from_replay(ledger, stints, contracts, assets, crosswalk, ledger_at)
        print(f"[warn] no saved roster reply in {raw_dir}: built from the ledger replay, "
              "slots blank (every salary charged)")

    total = etl.write_table("fact_fantasy_teams", fact)
    by_method = fact["acquired_method"].value_counts().to_dict()
    exempt = fact[fact["cap_exempt"]].groupby("roster_slot").size().to_dict()
    print(f"[ok] fact_fantasy_teams: {total} rows; acquired {by_method}; "
          f"cap-exempt by slot {exempt}; ledger captured {ledger_at}")

    dead = etl.read_table("fact_dead_money") if etl.table_exists("fact_dead_money") else None
    if dead is None:
        print("[warn] no fact_dead_money -- run 02f; the summary charges no Dead Money")
    summary = cap_summary(fact, dead, teams)
    over = summary[summary["cap_room"] < 0]
    print(f"[info] cap room ({fact['season'].iloc[0] if len(fact) else 'no season'}): "
          f"min {summary['cap_room'].min():,.0f}, {len(over)} team(s) over the cap"
          + (f": {sorted(over['team_key'])}" if len(over) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

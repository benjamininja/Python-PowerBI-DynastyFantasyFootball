# %% [markdown]
# # 04r_fantrax_roster_state  (public fxea getTeamRosters -- no auth)
#
# **Purpose:** the Roster State of each regular-season Scoring Period, read
# from Fantrax's public, no-login API (ADR-0016 decision 3 and its 2026-10-03
# amendment, decisions 3 and 14; built in #117). One call per period,
# `getTeamRosters?period=N` -> `fact_roster_state`: one row per player copy
# per period, with its Roster Slot, salary and contract.
#
# **Which periods are read:** the regular-season periods of the league's own
# season that have started, are not `closed` in `dim_scoring_period`, and are
# not past the period Fantrax calls current (the `period` a call with no
# period echoes). Fantrax answers a request for a future period with the
# current roster under the future number, so a period is read only when the
# calendar and Fantrax both say it has started. Before period 1 starts
# nothing is read. Each period read is replaced whole, so a late correction
# to a `closing` period lands on the next run; a `closed` period is frozen.
#
# **`capture_date`:** the day, on the league's Eastern clock, the period was
# last read. A period that has ended shows its final roster; the period in
# play shows the roster on that day.
#
# **Fails, and writes nothing, when:** a reply echoes a period other than the
# one asked for; a reply's teams are not exactly dim_fantasy_teams' teams; a
# team has no roster rows; a row has no player id or no salary; a status is
# not one of the four Roster Slots; a contract is not in dim_contract.
#
# **Outputs:**
# - `data/raw/fantrax_public_rosters_{year}_p{NN}.json` -- verbatim responses
#   (untracked)
# - `fact_roster_state.parquet` -- grain `(season_id, period, team_key,
#   scorer_id)`, replace-by-`(season_id, period)`
#
# **Run:**  python notebooks/04r_fantrax_roster_state.py

# %%
import importlib
import json
import random
import sys
import time
from pathlib import Path

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
from etl_helpers import DATA, fantrax_public_get, load_replace_partition

# league_id/raw_dir live on 04a's own LeagueConfig. The season id, the league
# clock and the Update-Set states are 04p's.
fx = importlib.import_module("04a_fantrax_weekly_scrape")
lg = importlib.import_module("04p_fantrax_league_info")
FX_CFG = fx.CFG

STATE_PATH = DATA / "fact_roster_state.parquet"
RAW_NAME = "fantrax_public_rosters_{year}_p{period:02d}.json"

# Fantrax's roster status -> Roster Slot (CONTEXT.md; ADR-0016 decision 2).
ROSTER_SLOT = {"ACTIVE": "Starter", "RESERVE": "Bench",
               "INJURED_RESERVE": "IR", "MINORS": "Minors"}

STATE_COLUMNS = ["season_id", "period", "team_key", "scorer_id", "roster_slot",
                 "salary", "contract_id", "capture_date"]

PULL_DELAY_S = (0.5, 1.5)     # jittered pause between public calls


# %%
def league_day(now) -> pd.Timestamp:
    """`now` (tz-aware) as a day on the league's Eastern clock."""
    return now.tz_convert(lg.LEAGUE_TZ).tz_localize(None).normalize()


def period_in_play(periods: pd.DataFrame, now) -> int | None:
    """The period whose bounds hold `now` (playoff periods count), or None
    between two periods and out of season."""
    hit = periods[(periods["start_at"] <= now) & (now <= periods["end_at"])]
    return int(hit["period"].iloc[0]) if len(hit) else None


def periods_to_pull(periods: pd.DataFrame, current: int, now) -> list[int]:
    """The periods whose Roster State is read this run.

    `periods` is one season's dim_scoring_period rows; `current` is the period
    Fantrax calls current. A period is read when it is a regular-season
    period, has started by `now`, is not `closed`, and is not past `current`.
    The last two are the guard against Fantrax's future-period reply: both
    the calendar and Fantrax must say the period has started.
    """
    started = ~periods["is_playoff"] & (periods["start_at"] <= now)
    closed = periods["update_set_state"].eq(lg.CLOSED)
    due = periods[started & ~closed & (periods["period"] <= current)]
    return sorted(int(p) for p in due["period"])


def check_reply(body: dict, period: int | None, team_ids) -> int:
    """Raise unless `body` is the roster of `period` for exactly `team_ids`.
    `period` None is the call that asked for no period. Returns the period
    the reply echoes."""
    echoed = int(body["period"])
    if period is not None and echoed != period:
        raise ValueError(f"getTeamRosters period={period} echoed period {echoed}")
    got, want = set(body["rosters"]), set(team_ids)
    if got != want:
        raise ValueError(
            f"getTeamRosters period {echoed}: {len(got)} teams, expected {len(want)} "
            f"(missing {sorted(want - got)}; not in dim_fantasy_teams {sorted(got - want)})")
    return echoed


def rosters_to_state(payload: dict, teams: pd.DataFrame, contract_ids,
                     season_id: str, period: int, capture_date) -> pd.DataFrame:
    """One getTeamRosters reply -> fact_roster_state rows for `period`.

    `teams` is dim_fantasy_teams (`fantrax_team_id` -> `team_key`);
    `contract_ids` is dim_contract's key set. One row per (team, player): the
    same player sits on one team in each Conference, so the player alone is
    not a key. Raises on a team the dim lacks, a team with no rows, a row
    with no player id or salary, an unknown status or an unknown contract.
    """
    key_of = dict(zip(teams["fantrax_team_id"], teams["team_key"]))
    recs = []
    for team_id, roster in payload["rosters"].items():
        if team_id not in key_of:
            raise ValueError(f"roster team {team_id} is not in dim_fantasy_teams")
        items = roster.get("rosterItems") or []
        if not items:
            raise ValueError(f"period {period}: team {team_id} has no roster rows")
        for item in items:
            where = f"period {period} team {team_id}"
            scorer_id = item.get("id")
            if not scorer_id:
                raise ValueError(f"{where}: a roster row has no player id")
            status = item.get("status")
            if status not in ROSTER_SLOT:
                raise ValueError(f"{where} player {scorer_id}: unknown roster status {status!r}")
            contract = (item.get("contract") or {}).get("name")
            if contract not in contract_ids:
                raise ValueError(f"{where} player {scorer_id}: contract {contract!r} "
                                 "is not in dim_contract")
            if item.get("salary") is None:
                raise ValueError(f"{where} player {scorer_id}: no salary")
            recs.append((key_of[team_id], scorer_id, ROSTER_SLOT[status],
                         float(item["salary"]), contract))

    rows = pd.DataFrame.from_records(
        recs, columns=["team_key", "scorer_id", "roster_slot", "salary", "contract_id"])
    rows = (rows.drop_duplicates(["team_key", "scorer_id"], keep="first")
                .sort_values(["team_key", "scorer_id"], ignore_index=True))
    df = pd.DataFrame({
        "season_id": pd.Series(season_id, index=rows.index, dtype="str"),
        "period": pd.Series(period, index=rows.index, dtype="int64"),
        "team_key": rows["team_key"].astype("str"),
        "scorer_id": rows["scorer_id"].astype("str"),
        "roster_slot": rows["roster_slot"].astype("str"),
        "salary": rows["salary"].astype("float64"),
        "contract_id": rows["contract_id"].astype("str"),
        "capture_date": pd.Series(capture_date, index=rows.index, dtype="datetime64[us]"),
    })
    return df[STATE_COLUMNS]


def collect(fetch, periods: pd.DataFrame, teams: pd.DataFrame, contract_ids,
            season_id: str, now) -> tuple[pd.DataFrame, int]:
    """Read every period due this run.

    `fetch(period)` returns one getTeamRosters reply; `fetch(None)` asks for
    no period and tells which one Fantrax calls current. That reply is reused
    for the current period. Returns (fact_roster_state rows, the current
    period). Every reply is checked and parsed before anything is returned, so
    a bad one leaves nothing to write.
    """
    team_ids = set(teams["fantrax_team_id"])
    newest = fetch(None)
    current = check_reply(newest, None, team_ids)
    day = league_day(now)
    frames = []
    for period in periods_to_pull(periods, current, now):
        reply = newest if period == current else fetch(period)
        check_reply(reply, period, team_ids)
        frames.append(rosters_to_state(reply, teams, contract_ids, season_id, period, day))
    if not frames:                     # no period is due: nothing to write
        return pd.DataFrame(columns=STATE_COLUMNS), current
    return pd.concat(frames, ignore_index=True), current


# %%
def main() -> int:
    now = pd.Timestamp.now(tz="UTC")
    # The season is the league's own (getLeagueInfo.seasonYear), not a config
    # value: a league id carried into a new season must never write its
    # rosters under the old season's periods.
    info = fantrax_public_get("getLeagueInfo", FX_CFG.league_id, expect=("seasonYear",))
    season_id = lg.season_id_of(info)
    year = int(info["seasonYear"])
    periods = pd.read_parquet(lg.PERIODS_PATH) if lg.PERIODS_PATH.exists() else None
    if periods is None or season_id not in set(periods["season_id"]):
        raise ValueError(f"season {season_id} is not in dim_scoring_period -- run 04p first")
    periods = periods[periods["season_id"] == season_id]
    teams = pd.read_parquet(DATA / "dim_fantasy_teams.parquet")
    contract_ids = set(pd.read_parquet(DATA / "dim_contract.parquet")["contract_id"])

    raw_dir = Path(FX_CFG.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    calls = 0

    def fetch(period):
        nonlocal calls
        if calls:
            time.sleep(random.uniform(*PULL_DELAY_S))
        calls += 1
        params = {} if period is None else {"period": period}
        reply = fantrax_public_get("getTeamRosters", FX_CFG.league_id,
                                   expect=("period", "rosters"), **params)
        # Saved before any check, under the period the reply echoes, so a
        # reply that fails a check is still on disk to look at.
        name = RAW_NAME.format(year=year, period=int(reply["period"]))
        (raw_dir / name).write_text(json.dumps(reply, indent=2), encoding="utf-8")
        return reply

    state, current = collect(fetch, periods, teams, contract_ids, season_id, now)

    in_play = period_in_play(periods, now)
    if in_play is not None and in_play != current:
        print(f"[warn] dim_scoring_period has period {in_play} in play; Fantrax calls "
              f"period {current} current. Read only the periods both agree have started.")
    if state.empty:
        print(f"[ok] fact_roster_state: no regular-season period of {season_id} to read "
              f"(Fantrax's current period is {current})")
        return 0

    total = load_replace_partition(state, STATE_PATH, part_cols=("season_id", "period"))
    per_period = state.groupby("period").size().to_dict()
    newest = state[state["period"] == state["period"].max()]
    print(f"[ok] fact_roster_state: {len(state)} rows for {season_id}, periods {per_period} "
          f"(Fantrax's current period is {current}; newest period slots "
          f"{newest['roster_slot'].value_counts().to_dict()}) "
          f"-> {total} total rows -> {STATE_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

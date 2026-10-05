# %% [markdown]
# # 04p_fantrax_league_info  (public fxea getLeagueInfo -- no auth)
#
# **Purpose:** one public, no-login call (`getLeagueInfo`) feeds the two
# tables every in-season fact hangs off (ADR-0016 amendment 2026-10-03,
# decisions 2, 12 and 14; built in #117):
#
# - `scoringPeriods` -> `dim_scoring_period`: all 17 Scoring Periods of the
#   season, with the Update-Set state of each regular-season period.
# - `teamInfo[].division` -> `dim_division`: the season's Division name per
#   Conference, taken from Fantrax instead of the Sheet (retires `01g`).
#
# **Update-Set state** (CONTEXT.md): `open` while the period is in play,
# `closing` once it has ended on the league's clock, `closed` once the
# following period has ended and its Close checks pass. Future and playoff
# periods have none (null). A `closed` period stays closed: there is no
# re-open here (#93 adds `--reclose`).
#
# **Close checks** (`etl_checks.close_errors`; ADR-0008 amendment decision 7,
# ADR-0016 amendment decision 10), run on the tables as they stand on disk
# for each period the calendar lets close: its Roster State covers 28 teams;
# its Matchups hold every team once and each pair mirrors; each team's
# Matchup score is its Starter sum in Period Scoring. A period that fails
# stays `closing` and is logged with the reasons (the alert is #116). This
# step runs before 04r and 04s, so a period closes on the rows the previous
# run wrote, and 04r and 04s then skip it.
#
# **Division Gate:** each Fantrax division must map to exactly one Conference
# and each Conference to one division. A violation raises here, so the step
# fails, the Chain is held and nothing is written.
#
# **Outputs:**
# - `data/raw/fantrax_public_leagueinfo.json` -- verbatim response (untracked)
# - `dim_scoring_period.parquet` -- grain `(season_id, period)`
# - `dim_division.parquet` -- grain `(season_id, conference)`
#
# **Run:**  python notebooks/04p_fantrax_league_info.py

# %%
import importlib
import json
import sys
from pathlib import Path

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
import etl_checks as ec
from etl_helpers import DATA, fantrax_public_get, load_replace_partition

# league_id/raw_dir live on 04a's own LeagueConfig -- same import-by-file
# pattern 04u and 04w use.
fx = importlib.import_module("04a_fantrax_weekly_scrape")
FX_CFG = fx.CFG

PERIODS_PATH = DATA / "dim_scoring_period.parquet"
DIVISION_PATH = DATA / "dim_division.parquet"
RAW_NAME = "fantrax_public_leagueinfo.json"

# Fantrax serves period bounds with an Eastern offset; the calendar dates
# (`start_date`, `end_date`) are days on that clock.
LEAGUE_TZ = "America/New_York"

OPEN, CLOSING, CLOSED = "open", "closing", "closed"

PERIOD_COLUMNS = ["season_id", "period", "start_date", "end_date", "start_at",
                  "end_at", "is_playoff", "update_set_state", "closed_at"]
DIVISION_COLUMNS = ["season_id", "conference", "division_name"]


# %%
def season_id_of(info: dict) -> str:
    year = int(info["seasonYear"])
    return f"{year}-{year + 1}"


def update_set_state(start_at, end_at, next_end_at, now, is_playoff,
                     prior=None, checks_pass=False):
    """The Update-Set state of one Scoring Period at `now`.

    closed   already closed (frozen: only an explicit re-close changes it), or
             the following period has ended and this period's Close checks pass
    None     a playoff period, or one that has not started
    open     in play
    closing  ended, not yet closed
    A period with no following period (`next_end_at` None) never closes here.
    """
    if prior == CLOSED:
        return CLOSED
    if is_playoff or now < start_at:
        return None
    if now <= end_at:
        return OPEN
    if checks_pass and next_end_at is not None and now > next_end_at:
        return CLOSED
    return CLOSING


def first_playoff_period(info: dict) -> int:
    playoffs = info.get("playoffs") or {}
    if "firstPlayoffPeriod" not in playoffs:
        raise ValueError("getLeagueInfo.playoffs has no firstPlayoffPeriod")
    first = int(playoffs["firstPlayoffPeriod"])
    last_regular = playoffs.get("lastRegularSeasonPeriod")
    if last_regular is not None and int(last_regular) + 1 != first:
        raise ValueError(f"playoffs: lastRegularSeasonPeriod {last_regular} is not "
                         f"the period before firstPlayoffPeriod {first}")
    return first


def parse_scoring_periods(info: dict, now, prior: pd.DataFrame | None = None,
                          checks_passed=frozenset()) -> pd.DataFrame:
    """getLeagueInfo.scoringPeriods -> dim_scoring_period rows for the season.

    `now` is a tz-aware timestamp. `prior` is the published dim (any seasons);
    its state and `closed_at` carry a closed period forward. `checks_passed`
    is the set of periods whose Close checks pass.
    """
    season_id = season_id_of(info)
    first_playoff = first_playoff_period(info)
    periods = sorted(info["scoringPeriods"], key=lambda p: int(p["number"]))
    numbers = [int(p["number"]) for p in periods]
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError(f"scoringPeriods are not numbered 1..n: {numbers}")
    start_at = pd.to_datetime([p["startDate"] for p in periods], utc=True).as_unit("us")
    end_at = pd.to_datetime([p["endDate"] for p in periods], utc=True).as_unit("us")
    for i, n in enumerate(numbers):
        if not start_at[i] < end_at[i]:
            raise ValueError(f"period {n} does not start before it ends")
        if i and start_at[i] < end_at[i - 1]:
            raise ValueError(f"period {n} starts before period {n - 1} ends")

    was = {}
    if prior is not None and len(prior):
        mine = prior[prior["season_id"] == season_id]
        was = {int(r.period): (r.update_set_state, r.closed_at) for r in mine.itertuples()}

    states, closed_at = [], []
    for i, n in enumerate(numbers):
        prior_state, prior_closed_at = was.get(n, (None, pd.NaT))
        state = update_set_state(
            start_at[i], end_at[i], end_at[i + 1] if i + 1 < len(numbers) else None,
            now, n >= first_playoff, prior=prior_state, checks_pass=n in checks_passed)
        states.append(state)
        if state != CLOSED:
            closed_at.append(pd.NaT)
        else:
            closed_at.append(prior_closed_at if prior_state == CLOSED else now)

    def local_day(ts):
        return ts.tz_convert(LEAGUE_TZ).tz_localize(None).normalize()

    df = pd.DataFrame({
        "season_id": season_id,
        "period": pd.Series(numbers, dtype="int64"),
        "start_date": local_day(start_at),
        "end_date": local_day(end_at),
        "start_at": start_at,
        "end_at": end_at,
        "is_playoff": [n >= first_playoff for n in numbers],
        "update_set_state": pd.Series(states, dtype="str"),
        "closed_at": pd.to_datetime(pd.Series(closed_at), utc=True).dt.as_unit("us"),
    })
    return df[PERIOD_COLUMNS]


def periods_due(info: dict, now, prior: pd.DataFrame | None = None) -> list[int]:
    """The periods that close at `now` if their Close checks pass. Asked of
    the state machine itself: the periods that are closed when every check
    passes and not closed when none does."""
    every = {int(p["number"]) for p in info["scoringPeriods"]}
    held = parse_scoring_periods(info, now, prior)
    freed = parse_scoring_periods(info, now, prior, checks_passed=every)
    due = freed["update_set_state"].eq(CLOSED) & ~held["update_set_state"].eq(CLOSED)
    return [int(n) for n in freed.loc[due, "period"]]


def close_checks(season_id: str, due: list[int], load) -> dict[int, list[str]]:
    """Each period of `due` -> its Close-check errors (none: it may close).
    `load` is a table loader (name -> DataFrame). A check that cannot run,
    such as a table not on disk, is a failure: the period stays closing."""
    out = {}
    for n in due:
        try:
            out[n] = ec.close_errors(season_id, n, load)
        except Exception as e:
            out[n] = [f"check raised: {e}"]
    return out


def parse_divisions(info: dict, teams: pd.DataFrame, season_id: str) -> pd.DataFrame:
    """getLeagueInfo.teamInfo -> dim_division rows for the season.

    Each team's Conference comes from dim_fantasy_teams (`fantrax_team_id`).
    Raises on a team the dim lacks, a team with no division, a Conference
    with no team, or a division and a Conference that are not one-to-one
    (the Gate of ADR-0016 amendment decision 12).
    """
    conference_of = dict(zip(teams["fantrax_team_id"], teams["conference"]))
    team_info = info["teamInfo"]
    items = list(team_info.values()) if isinstance(team_info, dict) else list(team_info)
    pairs = set()
    for t in items:
        team_id = t["id"]
        if team_id not in conference_of:
            raise ValueError(f"teamInfo team {team_id} is not in dim_fantasy_teams")
        name = (t.get("division") or "").strip()   # Fantrax pads one name with a space
        if not name:
            raise ValueError(f"teamInfo team {team_id} has no division")
        pairs.add((conference_of[team_id], name))

    conferences = [c for c, _ in pairs]
    names = [n for _, n in pairs]
    if len(set(conferences)) != len(pairs) or len(set(names)) != len(pairs):
        raise ValueError("a Fantrax division and a Conference are not one-to-one: "
                         f"{sorted(pairs)}")
    missing = set(teams["conference"]) - set(conferences)
    if missing:
        raise ValueError(f"no teamInfo team in Conference(s) {sorted(missing)}")

    df = pd.DataFrame(sorted(pairs), columns=["conference", "division_name"])
    df.insert(0, "season_id", season_id)
    return df[DIVISION_COLUMNS]


# %%
def main() -> int:
    info = fantrax_public_get(
        "getLeagueInfo", FX_CFG.league_id,
        expect=("seasonYear", "scoringPeriods", "playoffs", "teamInfo"))
    raw_dir = Path(FX_CFG.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / RAW_NAME).write_text(json.dumps(info, indent=2), encoding="utf-8")

    # Parse both tables before writing either: a failed Gate writes nothing.
    now = pd.Timestamp.now(tz="UTC")
    prior = pd.read_parquet(PERIODS_PATH) if PERIODS_PATH.exists() else None
    season_id = season_id_of(info)
    tables: dict[str, pd.DataFrame] = {}

    def load(name: str) -> pd.DataFrame:
        if name not in tables:
            tables[name] = pd.read_parquet(DATA / f"{name}.parquet")
        return tables[name]

    checked = close_checks(season_id, periods_due(info, now, prior), load)
    periods = parse_scoring_periods(
        info, now, prior, checks_passed={n for n, errs in checked.items() if not errs})
    if season_id not in set(pd.read_parquet(DATA / "dim_season.parquet")["season_id"]):
        raise ValueError(f"season {season_id} is not in dim_season -- run 01f first")
    divisions = parse_divisions(
        info, pd.read_parquet(DATA / "dim_fantasy_teams.parquet"), season_id)

    n_periods = load_replace_partition(periods, PERIODS_PATH, part_cols=("season_id",))
    n_divisions = load_replace_partition(divisions, DIVISION_PATH, part_cols=("season_id",))

    for n, errs in checked.items():
        if errs:
            print(f"[hold] period {n} stays closing, Close checks fail: {'; '.join(errs)}")
        else:
            print(f"[ok] period {n} closed: Close checks pass")
    counts = periods["update_set_state"].value_counts(dropna=False).to_dict()
    in_play = periods.loc[periods["update_set_state"] == OPEN, "period"].tolist()
    print(f"[ok] dim_scoring_period: {len(periods)} periods for {season_id} "
          f"({int((~periods['is_playoff']).sum())} regular season; states {counts}; "
          f"open {in_play}) -> {n_periods} total rows -> {PERIODS_PATH.name}")
    print(f"[ok] dim_division: {len(divisions)} divisions for {season_id} "
          f"-> {n_divisions} total rows -> {DIVISION_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

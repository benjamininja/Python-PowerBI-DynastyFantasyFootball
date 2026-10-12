# %% [markdown]
# # 02g_nflverse_inseason  (nflverse -> snap counts and injuries, current season)
#
# **Purpose:** the two nflverse facts of ADR-0017 (built in #86). nflverse
# supplies only what Fantrax cannot: snaps by Unit and the injury report.
# Points and games played stay with Fantrax.
#
# **`fact_nfl_snap_counts`**, grain `(gsis_id, game_id)`: offense, defense and
# special-teams snaps and their share of the team's snaps, per game.
# `load_snap_counts` knows a player only by his pfr id; `load_rosters_weekly`
# maps it to `gsis_id`. A row with no mapping is dropped and counted (almost
# all are offensive linemen and long snappers, who cannot be rostered).
#
# **`fact_nfl_injuries`**, grain `(gsis_id, season, week)`: the game status
# and the practice status of the week's injury report.
#
# **`period`** on both: the Scoring Period the game falls in, read off
# `dim_scoring_period` (04p writes it from the public `getLeagueInfo`). A
# snap row uses its game's date; an injury row uses the date of its team's
# game that week. A date inside no Scoring Period leaves `period` empty.
#
# **Lifecycle:** each run replaces the current season. These facts are not
# Update-Sets: nothing is frozen, and an nflverse correction simply lands.
#
# **Run:**  python notebooks/02g_nflverse_inseason.py   (no login; after 01e and 04p)

# %%
import sys
from pathlib import Path

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
from etl_helpers import read_table, write_table

SNAP_TABLE = "fact_nfl_snap_counts"
INJURY_TABLE = "fact_nfl_injuries"

SNAP_KEY = ["gsis_id", "game_id"]
SNAP_DTYPES = {"gsis_id": "str", "game_id": "str", "season": "int64", "week": "int64",
               "team": "str", "offense_snaps": "float64", "offense_pct": "float64",
               "defense_snaps": "float64", "defense_pct": "float64",
               "st_snaps": "float64", "st_pct": "float64", "period": "Int64"}
INJURY_KEY = ["gsis_id", "season", "week"]
INJURY_DTYPES = {"gsis_id": "str", "season": "int64", "week": "int64", "game_type": "str",
                 "team": "str", "report_status": "str", "report_primary_injury": "str",
                 "practice_status": "str", "period": "Int64"}


# %%
def current_season(periods: pd.DataFrame) -> tuple[int, pd.DataFrame]:
    """The NFL season of the newest league season on dim_scoring_period, and
    that season's periods. `season_id` reads `2026-2027`; the NFL season is
    its first year."""
    season_id = periods["season_id"].max()
    return int(str(season_id)[:4]), periods[periods["season_id"] == season_id]


def stamp_period(dates: pd.Series, periods: pd.DataFrame) -> pd.Series:
    """The Scoring Period each date falls in: `start_date` <= date <
    `end_date` (a period ends on the day the next one starts). Empty where
    the date is missing or inside no period."""
    days = pd.to_datetime(dates).dt.normalize()
    out = pd.Series(pd.NA, index=dates.index, dtype="Int64")
    for p in periods.itertuples():
        out[(days >= p.start_date) & (days < p.end_date)] = p.period
    return out


def build_snap_counts(snaps: pd.DataFrame, rosters: pd.DataFrame, schedule: pd.DataFrame,
                      periods: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """fact_nfl_snap_counts from the nflverse frames, and the rows dropped
    for want of a gsis_id, counted by position."""
    pairs = rosters.dropna(subset=["pfr_id", "gsis_id"]).drop_duplicates(["pfr_id", "gsis_id"])
    twice = sorted(pairs.loc[pairs.duplicated("pfr_id", keep=False), "pfr_id"].unique())
    if twice:
        raise ValueError(f"{len(twice)} pfr id(s) map to more than one gsis_id in "
                         f"load_rosters_weekly: {twice[:5]}")
    df = snaps.assign(gsis_id=snaps["pfr_player_id"].map(pairs.set_index("pfr_id")["gsis_id"]))
    unmapped = df.loc[df["gsis_id"].isna(), "position"].fillna("?").value_counts().to_dict()
    df = df[df["gsis_id"].notna()]
    df = df.assign(period=stamp_period(df["game_id"].map(schedule.set_index("game_id")["gameday"]),
                                       periods))
    df = df[list(SNAP_DTYPES)].astype(SNAP_DTYPES)
    dupes = int(df.duplicated(SNAP_KEY).sum())
    if dupes:
        raise ValueError(f"{dupes} {SNAP_TABLE} rows repeat the key {SNAP_KEY}")
    return df.sort_values(["season", "week", "game_id", "gsis_id"]).reset_index(drop=True), unmapped


def build_injuries(injuries: pd.DataFrame, schedule: pd.DataFrame,
                   periods: pd.DataFrame) -> pd.DataFrame:
    """fact_nfl_injuries from the nflverse frames. The game date of a row is
    its team's game that week; a team with none that week takes the week's
    first game day."""
    games = pd.concat([schedule.rename(columns={"home_team": "team"})[["week", "team", "gameday"]],
                       schedule.rename(columns={"away_team": "team"})[["week", "team", "gameday"]]])
    by_team = games.groupby(["week", "team"])["gameday"].min()
    by_week = schedule.groupby("week")["gameday"].min()
    df = injuries[injuries["gsis_id"].notna()].copy()
    day = pd.Series(pd.MultiIndex.from_frame(df[["week", "team"]]).map(by_team), index=df.index)
    df["period"] = stamp_period(day.fillna(df["week"].map(by_week)), periods)
    df = df[list(INJURY_DTYPES)].astype(INJURY_DTYPES)
    dupes = int(df.duplicated(INJURY_KEY).sum())
    if dupes:
        raise ValueError(f"{dupes} {INJURY_TABLE} rows repeat the key {INJURY_KEY}")
    return df.sort_values(["season", "week", "team", "gsis_id"]).reset_index(drop=True)


# %%
def load_nflverse(season: int) -> dict[str, pd.DataFrame]:
    """The four nflverse frames of one season, as pandas."""
    import nflreadpy as nfl

    frames = {}
    for name, load in (("snaps", nfl.load_snap_counts), ("injuries", nfl.load_injuries),
                       ("rosters", nfl.load_rosters_weekly), ("schedule", nfl.load_schedules)):
        try:
            frames[name] = load(seasons=season).to_pandas()
        except Exception as exc:
            raise RuntimeError(f"nflverse {name} for {season} could not be loaded: {exc}") from exc
    return frames


def main() -> int:
    season, periods = current_season(read_table("dim_scoring_period"))
    nfl = load_nflverse(season)

    snaps, unmapped = build_snap_counts(nfl["snaps"], nfl["rosters"], nfl["schedule"], periods)
    total = write_table(SNAP_TABLE, snaps, mode="replace_partition", partition={"season": [season]})
    print(f"[ok] {SNAP_TABLE}: {len(snaps)} rows for {season}, weeks "
          f"{sorted(snaps['week'].unique().tolist())} ({total} total) -> {SNAP_TABLE}.parquet")
    print(f"[info] {sum(unmapped.values())} snap row(s) dropped with no gsis_id, by position: {unmapped}")
    print(f"[info] {int(snaps['period'].isna().sum())} snap row(s) fall in no Scoring Period")

    injuries = build_injuries(nfl["injuries"], nfl["schedule"], periods)
    total = write_table(INJURY_TABLE, injuries, mode="replace_partition",
                        partition={"season": [season]})
    print(f"[ok] {INJURY_TABLE}: {len(injuries)} rows for {season}, weeks "
          f"{sorted(injuries['week'].unique().tolist())} ({total} total) -> {INJURY_TABLE}.parquet")
    print(f"[info] game status: {injuries['report_status'].value_counts(dropna=False).to_dict()}")
    print(f"[info] {int(injuries['period'].isna().sum())} injury row(s) fall in no Scoring Period")

    # Both facts point at dim_nfl_players. 01e runs first on the schedule; a
    # stale player dim shows up here as ids it does not hold yet.
    known = set(read_table("dim_nfl_players", columns=["gsis_id"])["gsis_id"])
    for name, df in ((SNAP_TABLE, snaps), (INJURY_TABLE, injuries)):
        missing = df.loc[~df["gsis_id"].isin(known), "gsis_id"]
        if len(missing):
            print(f"[warn] {name}: {len(missing)} row(s) of {missing.nunique()} player(s) have a "
                  f"gsis_id that dim_nfl_players does not hold -- run 01e to refresh it")
    return 0


if __name__ == "__main__":
    sys.exit(main())

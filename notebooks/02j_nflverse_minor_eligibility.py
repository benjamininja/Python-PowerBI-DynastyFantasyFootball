# %% [markdown]
# # 02j_nflverse_minor_eligibility  (nflverse -> Minors eligibility of every player)
#
# **Purpose:** the replacement for the logged-in `04v` (#524, #429 round 4
# Q10). A player is Minors-eligible while his career regular-season games
# played, this season included, are 19 or fewer (ADR-0019 decision 1; the
# league setting reads "Career+Current regular season total GP <= 19"). This
# step works that count out for every player, rostered or free agent, from
# nflverse. It signs in nowhere.
#
# **What counts as a game (planner ruling on #524, 2026-11-12, the rule #473
# Q7 sets for the scored history):**
# - 2012 on: a regular-season game in which the player took a snap, from
#   `load_snap_counts` (any Unit; offense, defense and special-teams snaps
#   added, greater than 0). Stats rows undercount games by about 14 percent,
#   so they are not used from 2012 on.
# - Before 2012: a regular-season stats row, from `load_player_stats` at the
#   `reg` level (its `games` column).
# - A playoff game never counts, as the league's setting says "regular season".
#
# **Players:** every `dim_nfl_players` row whose `last_season` is this NFL
# season or the one before (the offseason still holds last year's players), and
# that is not an old id replaced by a newer one (`dim_gsis_link`). A player
# with no game yet has 0 and is eligible.
#
# **`fact_nfl_minor_eligibility`**, grain `(gsis_id, season, week)`: the count
# and the verdict per player. `week` is the Scoring Period holding the run
# (two digits), or PRE when none does; each run replaces its own `(season,
# week)`, as `04v` does, so the table keeps one capture per period. Every row
# of a run carries the same `capture_date`. `02d` does not read it yet: its
# Minor default stays on Fantrax's `fact_minor_eligibility` (owner's ruling on
# PR #535, 2026-11-12). The drift check in `etl_checks.py` compares the two
# while `04v` still runs; the switch is the owner's call after a week of drift
# data.
#
# **Safe on a bad load:** an empty snap-count load would make every player look
# fresh and eligible, so the step stops instead of writing.
#
# **Run:**  python notebooks/02j_nflverse_minor_eligibility.py   (no login; after 01e and 04p)

# %%
import sys
from pathlib import Path

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
import etl_helpers as etl
from etl_helpers import read_table, write_table

TABLE = "fact_nfl_minor_eligibility"
GAMES_LIMIT = 19          # eligible while the count is this or fewer (ADR-0019 decision 1)
SNAPS_FROM = 2012         # load_snap_counts starts here; earlier seasons use stats rows
STATS_FROM = 1999         # load_player_stats starts here
REGULAR = "REG"
PRESEASON_LABEL = "PRE"   # the week label of a run no Scoring Period holds
POOL_LOOKBACK = 1         # seasons back a player may have last played and still be in the pool
SNAP_COLUMNS = ["offense_snaps", "defense_snaps", "st_snaps"]

KEY = ["gsis_id", "season", "week"]
DTYPES = {"gsis_id": "str", "season": "int64", "week": "str", "capture_date": "str",
          "career_games": "int64", "eligible": "bool"}


# %%
def current_season(periods: pd.DataFrame) -> int:
    """The NFL season of the newest league season on dim_scoring_period;
    `season_id` reads `2026-2027`, and the NFL season is its first year."""
    return int(str(periods["season_id"].max())[:4])


def week_label(day, periods: pd.DataFrame) -> str:
    """The Scoring Period holding `day`, two digits, or PRE when none does."""
    period = etl.scoring_period_on(day, periods)
    return PRESEASON_LABEL if period is None else f"{int(period['period']):02d}"


def pfr_lookup(players: pd.DataFrame, ids: pd.DataFrame) -> pd.Series:
    """pfr_id -> gsis_id. `load_snap_counts` knows a player only by his pfr id.
    `dim_nfl_players` and nflverse's id table (`load_ff_playerids`) both carry
    the pair; a pfr id they map differently takes the player dim's answer."""
    parts = [frame.dropna(subset=["pfr_id", "gsis_id"]).drop_duplicates("pfr_id", keep="last")
             .set_index("pfr_id")["gsis_id"] for frame in (ids, players)]
    both = pd.concat(parts)
    return both[~both.index.duplicated(keep="last")]


def snap_games(snaps: pd.DataFrame, lookup: pd.Series) -> tuple[pd.Series, dict[str, int]]:
    """Regular-season games with a snap, from 2012 on, per gsis_id, and the
    snap rows with no gsis_id counted by position (almost all offensive
    linemen and long snappers)."""
    reg = snaps[(snaps["game_type"] == REGULAR) & (snaps["season"] >= SNAPS_FROM)]
    taken = reg[reg[SNAP_COLUMNS].fillna(0).sum(axis=1) > 0]
    gsis = taken["pfr_player_id"].map(lookup)
    unmapped = taken.loc[gsis.isna(), "position"].fillna("?").value_counts().to_dict()
    got = taken.assign(gsis_id=gsis).dropna(subset=["gsis_id"]).drop_duplicates(["gsis_id", "game_id"])
    return got.groupby("gsis_id").size(), {k: int(v) for k, v in unmapped.items()}


def stat_games(stats: pd.DataFrame) -> pd.Series:
    """Regular-season games before 2012 per gsis_id: the `games` column of the
    `reg` stats frame is the count of the player's stat rows that season."""
    old = stats[(stats["season"] < SNAPS_FROM) & stats["player_id"].notna()]
    return old.groupby("player_id")["games"].sum()


def career_games(snap: pd.Series, stat: pd.Series, links: pd.DataFrame) -> pd.Series:
    """The two counts added per player, each id first moved to its newest
    (`dim_gsis_link`), so a player nflverse re-numbered keeps one count."""
    both = pd.concat([snap, stat])
    newest = etl.current_gsis(pd.Series(both.index, dtype="object"), links)
    return pd.Series(both.to_numpy(), index=newest.to_numpy()).groupby(level=0).sum()


def build_eligibility(players: pd.DataFrame, games: pd.Series, season: int, week: str,
                      capture_date: str, links: pd.DataFrame) -> pd.DataFrame:
    """fact_nfl_minor_eligibility for one run. Raises when `games` is empty:
    that is a failed load, and it would make every player eligible."""
    if games.empty:
        raise ValueError("no career games counted: the nflverse loads came back empty")
    pool = players[players["last_season"] >= season - POOL_LOOKBACK]
    pool = pool[etl.current_gsis(pool["gsis_id"], links) == pool["gsis_id"]]
    df = pd.DataFrame({"gsis_id": pool["gsis_id"].drop_duplicates().to_numpy()})
    df["career_games"] = df["gsis_id"].map(games).fillna(0)
    df["eligible"] = df["career_games"] <= GAMES_LIMIT
    df["season"], df["week"], df["capture_date"] = season, week, capture_date
    df = df[list(DTYPES)].astype(DTYPES)
    dupes = int(df.duplicated(KEY).sum())
    if dupes:
        raise ValueError(f"{dupes} {TABLE} rows repeat the key {KEY}")
    return df.sort_values("gsis_id").reset_index(drop=True)


# %%
def load_nflverse(season: int) -> dict[str, pd.DataFrame]:
    """The three nflverse frames, as pandas. The newest season asked for is the
    one nflverse has started (`get_current_season`), so a league season that
    has not begun leaves the count at last season's."""
    import nflreadpy as nfl

    last = min(season, int(nfl.get_current_season()))
    loads = {
        "snaps": lambda: nfl.load_snap_counts(seasons=list(range(SNAPS_FROM, last + 1))),
        "stats": lambda: nfl.load_player_stats(seasons=list(range(STATS_FROM, SNAPS_FROM)),
                                               summary_level="reg"),
        "ids": lambda: nfl.load_ff_playerids(),
    }
    frames = {}
    for name, load in loads.items():
        try:
            frames[name] = load().to_pandas()
        except Exception as exc:
            raise RuntimeError(f"nflverse {name} could not be loaded: {exc}") from exc
    return frames


def main() -> int:
    periods = read_table("dim_scoring_period")
    players = read_table("dim_nfl_players")
    links = read_table(etl.GSIS_LINK_TABLE) if etl.table_exists(etl.GSIS_LINK_TABLE) else pd.DataFrame()
    season, day = current_season(periods), etl.league_date()
    week, capture_date = week_label(day, periods), day.isoformat()
    nfl = load_nflverse(season)

    snap, unmapped = snap_games(nfl["snaps"], pfr_lookup(players, nfl["ids"]))
    stat = stat_games(nfl["stats"])
    games = career_games(snap, stat, links)
    df = build_eligibility(players, games, season, week, capture_date, links)

    total = write_table(TABLE, df, mode="replace_partition", keys=("season", "week"))
    print(f"[ok] {TABLE}: {len(df)} players for {season} week {week} on {capture_date}, "
          f"{int(df['eligible'].sum())} minors-eligible ({total} rows in all) -> {TABLE}.parquet")
    print(f"[info] games counted for {len(games)} players: {len(snap)} with snaps from "
          f"{SNAPS_FROM}, {len(stat)} with stats rows before it")
    print(f"[info] {sum(unmapped.values())} snap row(s) with no gsis_id, by position: {unmapped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# %% [markdown]
# # 02i_nflverse_scored_history  (nflverse counts scored with Fantrax's rules)
#
# **Purpose:** the scored history of the MouseRatPresents Baseline (#473 brief
# 4, ADR-0023). Each player's regular-season counts from nflverse
# (`load_player_stats`, `reg` level), for the 15 most recent full seasons plus
# the current one, scored with the league's own rules: the newest season of
# `dim_fantrax_scoring_rule`, the player's league position, and the nflverse
# columns `dim_scoring_category` maps to each Scoring Category. A rule change
# rescores every season; `rules_season_id` records which rules scored a row.
#
# **`fact_scored_season_stat`**, grain `(gsis_id, season, category_id)`: the
# count and its points. A row only where the count is not 0. A category with
# no nflverse column scores 0 and has no row; each run names it.
#
# **`fact_scored_player_season`**, grain `(gsis_id, season)`: games, the
# league position and where it came from, and the rules season. Position is
# the crosswalk's Fantrax position (the first listed one), else nflverse's,
# both through `dim_position`; a player with no league position (OL, K, P)
# has no rules row and is left out, counted. Games are the regular-season
# games with a snap from 2012 on (`load_snap_counts`), stats rows before
# (#473 Q7); a player-season with stats rows and no mapped snap game takes
# its stats-row count.
#
# **Fails by name** on a mapped nflverse column the frame lacks, and on a
# rules category `dim_scoring_category` has no row for.
#
# **The drift check**, after scoring and before any write: our points
# against Fantrax's stored figures. 2025: season totals against
# `fact_fantrax_adp` (season 2025, week YTD, 8 games or more). Each season
# `fact_period_scoring` holds: points per closed Scoring Period it holds,
# nflverse week rows stamped to a period. Fantrax's figure is one per scorer
# and period, never a sum over teams: a player rostered in both Conferences
# has two rows, which must agree within 0.01; a disagreement or a third row
# fails the step. A player passes when the gap is at
# most 1 point plus 5 percent of Fantrax's figure; the step fails when fewer
# than 90 percent pass in a season, or when a Fantrax position's summed
# points differ by more than 2 percent (the owner's bar, 2026-11-09). The
# figures print as counts and rates first, with the share inside the tighter
# 0.5 plus 2 percent and the exact share, how the misses miss, the stored rows
# per player and period, the NFL weeks each period holds, and a 2025 fit of
# the tackle points per IDP position (#473 issuecomment-7244034527).
#
# **Change detection:** the current season is pulled every run and compared
# with the stored rows; past seasons are pulled only when absent or when the
# rules changed. Nothing changed: nothing is written.
#
# **Run:**  python notebooks/02i_nflverse_scored_history.py   (no login; after 01e, 04p and 01h)

# %%
import sys
from pathlib import Path

import numpy as np
import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
import etl_helpers as etl
from etl_helpers import read_table, stamp_period, write_table

STAT_TABLE = "fact_scored_season_stat"
PLAYER_TABLE = "fact_scored_player_season"
SEASONS_BACK = 15         # full seasons before the current one
SNAPS_FROM = 2012         # load_snap_counts starts here; earlier seasons count stats rows
REGULAR = "REG"
LEAGUE_POSITIONS = ("QB", "RB", "WR", "TE", "DL", "LB", "DB")
SNAP_COLUMNS = ["offense_snaps", "defense_snaps", "st_snaps"]
NO_GROUP = "(no points)"

STAT_KEY = ["gsis_id", "season", "category_id"]
STAT_DTYPES = {"gsis_id": "str", "season": "int64", "category_id": "str",
               "stat_count": "float64", "points": "float64"}
PLAYER_KEY = ["gsis_id", "season"]
PLAYER_DTYPES = {"gsis_id": "str", "season": "int64", "games": "int64", "position": "str",
                 "position_source": "str", "rules_season_id": "str"}

YTD_SEASON = 2025         # Fantrax's 2025 actuals in this league's scoring (04a YTD_SEASON_CODES)
YTD_WEEK = "YTD"
YTD_MIN_GAMES = 8
EXACT = 0.05              # the exact share: within this many points
BAR_POINTS, BAR_PCT, BAR_SHARE, BAR_POSITION = 1.0, 0.05, 0.90, 0.02   # the owner's bar, 2026-11-09
TIGHT_POINTS, TIGHT_PCT = 0.5, 0.02           # the tighter per-player bar, printed only
HALF, EQUAL = (0.4, 0.6), (0.9, 1.1)          # ratio bands of a miss, ours over Fantrax's
TACKLE_CODES = ("TkS", "TkA")                 # solo, assisted
IDP_POSITIONS = ("DL", "LB", "DB")
ROW_AGREE = 0.01          # a scorer's two rows (one per Conference) agree within this
MAX_ROWS = 2              # rows per scorer and period: one per Conference
UNIT_COLUMNS = {"Offense": "fpts_offense", "Defense": "fpts_defense",
                "Special Teams": "fpts_special_teams"}


class DriftError(RuntimeError):
    """Our points miss Fantrax's past the fixed threshold."""


# %%
def current_season(periods: pd.DataFrame) -> int:
    """The NFL season of the newest league season on dim_scoring_period;
    `season_id` reads `2026-2027`, and the NFL season is its first year."""
    return int(str(periods["season_id"].max())[:4])


def nfl_season(season_id: str) -> int:
    return int(str(season_id)[:4])


def rule_points(rules: pd.DataFrame, categories: pd.DataFrame) -> tuple[str, pd.Series]:
    """The newest rules season and its points per (category_id, position).
    Raises naming every rules category dim_scoring_category has no row for."""
    season_id = str(rules["season_id"].max())
    newest = rules[rules["season_id"] == season_id]
    missing = sorted(set(newest["category_id"]) - set(categories["category_id"]))
    if missing:
        raise ValueError(f"{len(missing)} rules category id(s) have no dim_scoring_category row: "
                         f"{missing} -- add a row in 01h")
    return season_id, newest.set_index(["category_id", "position"])["points"].astype(float)


def column_map(categories: pd.DataFrame, points: pd.Series) -> tuple[dict[str, list[str]], list[str]]:
    """category_id -> the nflverse columns whose sum is its count, for the
    categories the rules score; and the scored categories with no column,
    which score 0."""
    scored = set(points.index.get_level_values("category_id"))
    colmap, unmapped = {}, []
    for row in categories[categories["category_id"].isin(scored)].itertuples():
        cols = row.nflverse_columns
        if isinstance(cols, str) and cols.strip():
            colmap[row.category_id] = [c.strip() for c in cols.split("+")]
        else:
            unmapped.append(row.category_id)
    return colmap, sorted(unmapped)


def check_columns(frame: pd.DataFrame, colmap: dict[str, list[str]], what: str) -> list[str]:
    """The mapped columns, each found in `frame`. Raises naming every mapped
    column the frame lacks."""
    wanted = sorted({c for cols in colmap.values() for c in cols})
    missing = [c for c in wanted if c not in frame.columns]
    if missing:
        raise ValueError(f"{len(missing)} mapped nflverse column(s) missing from the {what} frame: "
                         f"{missing} -- fix the map in dim_scoring_category (01h)")
    return wanted


# %%
def to_players(stats: pd.DataFrame, keys: list[str], cols: list[str], links: pd.DataFrame,
               known: set) -> tuple[pd.DataFrame, int]:
    """nflverse stat rows summed per `keys`, each id moved to its newest
    (`dim_gsis_link`). Rows with no player id are dropped; ids
    dim_nfl_players lacks are dropped and their count returned."""
    df = stats[stats["player_id"].notna()].copy()
    df["gsis_id"] = etl.current_gsis(df["player_id"].astype(str), links)
    unknown = ~df["gsis_id"].isin(known)
    dropped = int(df.loc[unknown, "gsis_id"].nunique())
    df = df[~unknown]
    df[cols] = df[cols].fillna(0)
    return df.groupby(keys, as_index=False)[cols].sum(), dropped


def fantrax_positions(crosswalk: pd.DataFrame, lookup: pd.Series, links: pd.DataFrame) -> pd.Series:
    """gsis_id -> league position from the crosswalk: the first listed
    position of `position_raw`, through dim_position. A gsis_id with several
    scorer ids takes the first by scorer_id."""
    xw = crosswalk.dropna(subset=["gsis_id", "position_raw"]).copy()
    xw["gsis_id"] = etl.current_gsis(xw["gsis_id"].astype(str), links)
    xw = xw.sort_values("scorer_id").drop_duplicates("gsis_id")
    first = xw["position_raw"].astype(str).str.split(",").str[0].str.strip()
    return pd.Series(first.map(lookup).to_numpy(), index=xw["gsis_id"].to_numpy()).dropna()


def assign_positions(players: pd.DataFrame, fantrax: pd.Series,
                     lookup: pd.Series) -> tuple[pd.DataFrame, dict[str, int], dict[str, int]]:
    """`players` (gsis_id, season, nflverse `position`) with the league
    position and its source. Returns the rows with a league position, the
    raw nflverse values dim_position lacks (counted), and the player-seasons
    left out for want of a league position, by group."""
    out = players.copy()
    nfl = out["position"].map(lookup)
    ft = out["gsis_id"].map(fantrax)
    unknown = out.loc[ft.isna() & nfl.isna(), "position"].fillna("(none)").value_counts().to_dict()
    out["position_source"] = np.where(ft.notna(), "fantrax", "nflverse")
    out["position"] = ft.fillna(nfl)
    off = ~out["position"].isin(LEAGUE_POSITIONS)
    left = out.loc[off, "position"].fillna("(none)").value_counts().to_dict()
    return out[~off], {k: int(v) for k, v in unknown.items()}, {k: int(v) for k, v in left.items()}


def season_games(stats: pd.DataFrame, snaps: pd.DataFrame, pfr: dict,
                 links: pd.DataFrame) -> tuple[pd.Series, int]:
    """Games per (gsis_id, season): snaps above 0 from 2012, the stats-row
    count before. From 2012 a player-season with no mapped snap game takes
    its stats-row count; how many did is returned."""
    stat = stats.set_index(PLAYER_KEY)["games"]
    if snaps.empty:
        snap = pd.Series(dtype="int64")
    else:
        reg = snaps[(snaps["game_type"] == REGULAR) & (snaps["season"] >= SNAPS_FROM)]
        taken = reg[reg[SNAP_COLUMNS].fillna(0).sum(axis=1) > 0].copy()
        taken["gsis_id"] = etl.current_gsis(taken["pfr_player_id"].map(pfr), links)
        taken = taken.dropna(subset=["gsis_id"]).drop_duplicates(["gsis_id", "game_id"])
        snap = taken.groupby(PLAYER_KEY).size()
    seasons = stat.index.get_level_values("season")
    from_snaps = pd.Series(seasons >= SNAPS_FROM, index=stat.index)
    snap_games = snap.reindex(stat.index)
    fallback = int((from_snaps & snap_games.isna()).sum())
    games = stat.where(~from_snaps | snap_games.isna(), snap_games)
    return games.fillna(0).astype("int64"), fallback


def score(frame: pd.DataFrame, keys: list[str], colmap: dict[str, list[str]],
          points: pd.Series) -> pd.DataFrame:
    """Long rows, one per `keys` and category where the count is not 0, with
    `stat_count` and `points` (count times the rules' points for the row's
    `position`)."""
    parts = []
    for cat, cols in colmap.items():
        count = frame[cols].fillna(0).sum(axis=1).astype(float)
        part = frame[keys + ["position"]].assign(category_id=cat, stat_count=count)
        parts.append(part[part["stat_count"] != 0])
    long = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=keys + ["position", "category_id", "stat_count"])
    idx = pd.MultiIndex.from_frame(long[["category_id", "position"]])
    long["points"] = long["stat_count"] * points.reindex(idx).to_numpy()
    if long["points"].isna().any():
        bad = long.loc[long["points"].isna(), ["category_id", "position"]].drop_duplicates()
        raise ValueError(f"no rules points for {len(bad)} (category, position) pair(s): "
                         f"{bad.to_records(index=False).tolist()[:5]}")
    return long


def build_history(stats: pd.DataFrame, snaps: pd.DataFrame, players: pd.DataFrame,
                  crosswalk: pd.DataFrame, positions: pd.DataFrame, colmap: dict[str, list[str]],
                  points: pd.DataFrame, rules_season_id: str,
                  links: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The two tables for the seasons in `stats` (a `reg` frame)."""
    cols = sorted({c for cs in colmap.values() for c in cs})
    known = set(players["gsis_id"].dropna())
    frame = stats.copy()
    frame["games"] = frame["games"].fillna(0)
    agg, dropped = to_players(frame, PLAYER_KEY, cols + ["games"], links, known)
    pos = (frame[frame["player_id"].notna()]
           .assign(gsis_id=lambda d: etl.current_gsis(d["player_id"].astype(str), links))
           .dropna(subset=["position"]).drop_duplicates(PLAYER_KEY)[PLAYER_KEY + ["position"]])
    agg = agg.merge(pos, on=PLAYER_KEY, how="left")
    lookup = positions.drop_duplicates("position_raw").set_index("position_raw")["position_group"]
    agg, unknown, left = assign_positions(agg, fantrax_positions(crosswalk, lookup, links), lookup)
    games, fallback = season_games(agg, snaps, etl.pfr_to_gsis_map(players), links)
    stat_rows = score(agg, PLAYER_KEY, colmap, points)
    player_rows = agg[PLAYER_KEY + ["position", "position_source"]].copy()
    player_rows = player_rows.merge(games.rename("games").reset_index(), on=PLAYER_KEY, how="left")
    player_rows["rules_season_id"] = rules_season_id
    stat_df = stat_rows[list(STAT_DTYPES)].astype(STAT_DTYPES).sort_values(STAT_KEY).reset_index(drop=True)
    player_df = (player_rows[list(PLAYER_DTYPES)].astype(PLAYER_DTYPES)
                 .sort_values(PLAYER_KEY).reset_index(drop=True))
    for name, df, key in ((STAT_TABLE, stat_df, STAT_KEY), (PLAYER_TABLE, player_df, PLAYER_KEY)):
        dupes = int(df.duplicated(key).sum())
        if dupes:
            raise ValueError(f"{dupes} {name} rows repeat the key {key}")
    orphan = ~pd.MultiIndex.from_frame(stat_df[PLAYER_KEY]).isin(
        pd.MultiIndex.from_frame(player_df[PLAYER_KEY]))
    if orphan.any():
        raise ValueError(f"{int(orphan.sum())} {STAT_TABLE} rows have no {PLAYER_TABLE} row")
    info = {"dropped_ids": dropped, "unknown_positions": unknown, "no_league_position": left,
            "games_from_stats_rows": fallback}
    return stat_df, player_df, info


# %%
def rules_changed(stored_stats: pd.DataFrame, stored_players: pd.DataFrame, points: pd.Series,
                  rules_season_id: str, colmap: dict[str, list[str]]) -> bool:
    """Were the stored rows scored with other rules (or another map) than now?"""
    if stored_players.empty:
        return False
    if (stored_players["rules_season_id"] != rules_season_id).any():
        return True
    if not set(stored_stats["category_id"]) <= set(colmap):
        return True
    rows = stored_stats.merge(stored_players[PLAYER_KEY + ["position"]], on=PLAYER_KEY, how="left")
    idx = pd.MultiIndex.from_frame(rows[["category_id", "position"]])
    expect = rows["stat_count"].to_numpy() * points.reindex(idx).to_numpy()
    return not np.allclose(expect, rows["points"].to_numpy(), rtol=0, atol=1e-9)


def same_rows(a: pd.DataFrame, b: pd.DataFrame, key: list[str]) -> bool:
    """Do the two frames hold the same rows, floats within 1e-9?"""
    if len(a) != len(b) or list(a.columns) != list(b.columns):
        return False
    a = a.sort_values(key).reset_index(drop=True)
    b = b.sort_values(key).reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(a, b, check_dtype=False, check_exact=False, rtol=0, atol=1e-9)
    except AssertionError:
        return False
    return True


# %%
def dominant_group(rows: pd.DataFrame, keys: list[str], categories: pd.DataFrame) -> pd.Series:
    """Per `keys`, the Category Group that gives most of the player's points."""
    if rows.empty:
        return pd.Series(dtype="object")
    group = rows["category_id"].map(categories.set_index("category_id")["category_group"])
    by = rows.assign(category_group=group).groupby(keys + ["category_group"])["points"].sum()
    top = by.reset_index().sort_values("points", ascending=False).drop_duplicates(keys)
    return top.set_index(keys)["category_group"]


def inside(ours: pd.Series, theirs: pd.Series) -> pd.Series:
    """Does each player pass the bar: a gap of at most 1 point plus 5 percent?"""
    return (ours - theirs).abs() <= BAR_POINTS + BAR_PCT * theirs.abs()


def figures(df: pd.DataFrame) -> dict:
    """Counts and rates of one comparison. `df` holds `ours`, `theirs`,
    `position` and `group`, one row per compared player (and period)."""
    gap = df["ours"] - df["theirs"]
    passed = inside(df["ours"], df["theirs"])
    tight = gap.abs() <= TIGHT_POINTS + TIGHT_PCT * df["theirs"].abs()
    by_pos = {}
    for pos, part in df.assign(gap=gap).groupby("position"):
        theirs = float(part["theirs"].sum())
        by_pos[pos] = (float(part["gap"].sum()), theirs)
    by_group = df.assign(gap=gap).groupby("group")["gap"].sum().to_dict()
    n = len(df)
    return {"compared": n,
            "exact_share": float((gap.abs() <= EXACT).mean()) if n else None,
            "pass_share": float(passed.mean()) if n else None,
            "tight_share": float(tight.mean()) if n else None,
            "by_position": by_pos, "by_group": {k: float(v) for k, v in by_group.items()}}


def failures(label: str, fig: dict) -> list[str]:
    """The ways one season's figures miss the threshold."""
    out = []
    if fig["compared"] and fig["pass_share"] < BAR_SHARE:
        out.append(f"{label}: {fig['pass_share']:.1%} of {fig['compared']} compared pass, "
                   f"under {BAR_SHARE:.0%}")
    for pos, (gap, theirs) in sorted(fig["by_position"].items()):
        rel = abs(gap) / abs(theirs) if theirs else (0.0 if gap == 0 else float("inf"))
        if rel > BAR_POSITION:
            out.append(f"{label}: {pos} summed points differ by {rel:.2%}, over {BAR_POSITION:.0%}")
    return out


def ytd_comparison(adp: pd.DataFrame, history: pd.DataFrame, categories: pd.DataFrame,
                   lookup: pd.Series, links: pd.DataFrame) -> pd.DataFrame:
    """Our 2025 season points against Fantrax's YTD actuals, players with 8
    games or more."""
    a = adp[(adp["season"] == YTD_SEASON) & (adp["week"] == YTD_WEEK)
            & (adp["games_played"] >= YTD_MIN_GAMES) & adp["gsis_id"].notna()].copy()
    a["gsis_id"] = etl.current_gsis(a["gsis_id"].astype(str), links)
    a = a.sort_values("scorer_id").drop_duplicates("gsis_id")
    rows = history[history["season"] == YTD_SEASON]
    ours = rows.groupby("gsis_id")["points"].sum()
    group = dominant_group(rows, ["gsis_id"], categories)
    first = a["position_raw"].astype(str).str.split(",").str[0].str.strip()
    return pd.DataFrame({"gsis_id": a["gsis_id"].to_numpy(),
                         "theirs": a["fpts"].fillna(0).to_numpy(),
                         "ours": a["gsis_id"].map(ours).fillna(0).to_numpy(),
                         "position": first.map(lookup).fillna("(none)").to_numpy(),
                         "group": a["gsis_id"].map(group).fillna(NO_GROUP).to_numpy()})


def one_figure(scoring: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """One Fantrax figure per scorer and period, never a sum over teams. The
    league keeps one copy of a player per Conference, so a player rostered
    in both has two rows, one per team; their `fpts` must agree within 0.01.
    Returns the rows (the first team_key's), the scorer-periods with more
    than two rows, and those whose rows disagree."""
    cols = ["fpts", *UNIT_COLUMNS.values()]
    by = scoring.groupby(["scorer_id", "period"])
    too_many = int((by.size() > MAX_ROWS).sum())
    disagree = int(((by["fpts"].max() - by["fpts"].min()) > ROW_AGREE + 1e-9).sum())
    one = (scoring.sort_values(["scorer_id", "period", "team_key"])
           .drop_duplicates(["scorer_id", "period"])[["scorer_id", "period", *cols]].reset_index(drop=True))
    return one, too_many, disagree


def period_comparison(weeks: pd.DataFrame, schedule: pd.DataFrame, periods: pd.DataFrame,
                      scoring: pd.DataFrame, crosswalk: pd.DataFrame, player_positions: pd.Series,
                      fantrax_pos: pd.Series, colmap: dict[str, list[str]], points: pd.Series,
                      categories: pd.DataFrame, links: pd.DataFrame,
                      known: set) -> tuple[pd.DataFrame, dict]:
    """Our points per player and closed Scoring Period against
    fact_period_scoring, for one league season. Only periods the stored rows
    hold and dim_scoring_period marks closed are compared."""
    held = sorted(scoring["period"].unique().tolist())
    closed = set(periods.loc[periods["update_set_state"] == "closed", "period"])
    compared = [p for p in held if p in closed]
    last = max(held) if held else None
    later = sorted(set(periods.loc[~periods["is_playoff"], "period"].tolist()) - set(held))
    info = {"held": held, "compared": compared, "not_closed": [p for p in held if p not in closed],
            "after_last_frozen": [p for p in later if last is None or p > last]}
    rows_per = scoring[scoring["period"].isin(compared)].groupby(["period", "scorer_id"]).size()
    info["rows_per_player"] = {int(p): {"players": int(len(s)), "more_than_one": int((s > 1).sum()),
                                        "max_rows": int(s.max())}
                               for p, s in rows_per.groupby(level="period")}
    games = schedule.copy()
    if "game_type" in games.columns:
        games = games[games["game_type"] == REGULAR]
    games["period"] = stamp_period(games["gameday"], periods)
    stamped = games.dropna(subset=["period"]).groupby("period")["week"].nunique()
    span = periods.set_index("period")
    info["weeks"] = {int(p): {"span_days": int((span.at[p, "end_date"] - span.at[p, "start_date"]).days),
                              "nfl_weeks_stamped": int(stamped.get(p, 0)),
                              "games_stamped": int((games["period"] == p).sum())}
                     for p in compared}
    theirs, info["too_many_rows"], info["rows_disagree"] = one_figure(
        scoring[scoring["period"].isin(compared)])
    xw = crosswalk.dropna(subset=["gsis_id"]).set_index("scorer_id")["gsis_id"]
    theirs["gsis_id"] = theirs["scorer_id"].map(xw)
    info["no_gsis_id"] = int(theirs["gsis_id"].isna().sum())
    theirs = theirs.dropna(subset=["gsis_id"])
    theirs["gsis_id"] = etl.current_gsis(theirs["gsis_id"].astype(str), links)
    theirs = theirs.sort_values("scorer_id").drop_duplicates(["gsis_id", "period"])

    cols = sorted({c for cs in colmap.values() for c in cs})
    wk = weeks[weeks["season_type"] == REGULAR].copy()
    wk["period"] = stamp_period(wk["game_id"].map(schedule.set_index("game_id")["gameday"]), periods)
    wk = wk[wk["period"].notna()].astype({"period": "int64"})
    wk = wk[wk["period"].isin(compared)]
    wk, _ = to_players(wk, ["gsis_id", "period"], cols, links, known)
    wk["position"] = wk["gsis_id"].map(player_positions).fillna(wk["gsis_id"].map(fantrax_pos))
    wk = wk[wk["position"].isin(LEAGUE_POSITIONS)]
    rows = score(wk, ["gsis_id", "period"], colmap, points)
    rows["unit"] = rows["category_id"].map(categories.set_index("category_id")["unit"])
    ours = rows.groupby(["gsis_id", "period"])["points"].sum()
    units = (rows.groupby(["gsis_id", "period", "unit"])["points"].sum().unstack("unit")
             if len(rows) else pd.DataFrame())
    group = dominant_group(rows, ["gsis_id", "period"], categories)
    key = pd.MultiIndex.from_frame(theirs[["gsis_id", "period"]])
    df = pd.DataFrame({"period": theirs["period"].to_numpy(),
                       "theirs": theirs["fpts"].to_numpy(),
                       "ours": ours.reindex(key).fillna(0).to_numpy(),
                       "position": theirs["gsis_id"].map(fantrax_pos).fillna("(none)").to_numpy(),
                       "group": group.reindex(key).fillna(NO_GROUP).to_numpy(),
                       "joined": key.isin(ours.index)})
    for unit, col in UNIT_COLUMNS.items():
        df[f"theirs_{unit}"] = theirs[col].to_numpy()
        mine = units[unit] if unit in units.columns else pd.Series(dtype=float)
        df[f"ours_{unit}"] = mine.reindex(key).fillna(0).to_numpy()
    return df, info


def miss_counts(df: pd.DataFrame) -> dict[str, int]:
    """How the player-periods that miss the exact share miss: ours 0 or
    missing while Fantrax's is above 0; else ours near half of Fantrax's,
    near equal, or elsewhere. Also the compared players with no row of ours."""
    ours, theirs = df["ours"], df["theirs"]
    miss = (ours - theirs).abs() > EXACT
    zero = miss & (ours == 0) & (theirs > 0)
    rest = miss & ~zero
    ratio = ours / theirs.where(theirs != 0)
    half = rest & ratio.between(*HALF)
    equal = rest & ratio.between(*EQUAL)
    return {"compared": int(len(df)), "misses": int(miss.sum()), "ours_zero_theirs_above": int(zero.sum()),
            "near_half": int(half.sum()), "near_equal": int(equal.sum()),
            "elsewhere": int((rest & ~half & ~equal).sum()),
            "no_row_of_ours": int((~df["joined"]).sum())}


def tackle_fit(ytd: pd.DataFrame, rows: pd.DataFrame, categories: pd.DataFrame,
               points: pd.Series) -> dict[str, dict]:
    """Per IDP position, the points per solo and per assisted tackle that best
    fit Fantrax's 2025 totals from our counts (least squares on the gap),
    beside the rules' points; the share inside the bar under the fitted
    points and the gap left; and the share and gap with the solo and
    assisted counts swapped at the rules' points. A free fit is the same
    with the columns swapped, so the swap is tested at the rules' points."""
    code_to_id = categories.drop_duplicates("category_code").set_index("category_code")["category_id"]
    solo_id, assist_id = (code_to_id.get(c) for c in TACKLE_CODES)
    if solo_id is None or assist_id is None:
        return {}
    counts = rows.pivot_table(index="gsis_id", columns="category_id", values="stat_count", aggfunc="sum")
    tackle_pts = rows[rows["category_id"].isin([solo_id, assist_id])].groupby("gsis_id")["points"].sum()
    out = {}
    for pos in IDP_POSITIONS:
        part = ytd[ytd["position"] == pos]
        if part.empty:
            continue
        col = lambda cid: (part["gsis_id"].map(counts[cid]) if cid in counts.columns
                           else pd.Series(0.0, index=part.index)).fillna(0).to_numpy()
        solo, assist = col(solo_id), col(assist_id)
        theirs = part["theirs"].to_numpy()
        other = part["ours"].to_numpy() - part["gsis_id"].map(tackle_pts).fillna(0).to_numpy()
        fit, *_ = np.linalg.lstsq(np.column_stack([solo, assist]), theirs - other, rcond=None)
        rule_solo, rule_assist = float(points[(solo_id, pos)]), float(points[(assist_id, pos)])
        fitted = other + fit[0] * solo + fit[1] * assist
        swapped = other + rule_solo * assist + rule_assist * solo
        th = pd.Series(theirs)
        out[pos] = {"players": int(len(part)), "fit_solo": float(fit[0]), "fit_assist": float(fit[1]),
                    "rule_solo": rule_solo, "rule_assist": rule_assist,
                    "share_rules": float(inside(part["ours"].reset_index(drop=True), th).mean()),
                    "share_fitted": float(inside(pd.Series(fitted), th).mean()),
                    "gap_fitted": float((fitted - theirs).sum()),
                    "share_swapped": float(inside(pd.Series(swapped), th).mean()),
                    "gap_swapped": float((swapped - theirs).sum())}
    return out


def unit_gaps(df: pd.DataFrame) -> dict[str, float]:
    return {u: float((df[f"ours_{u}"] - df[f"theirs_{u}"]).sum()) for u in UNIT_COLUMNS}


def print_figures(label: str, fig: dict) -> None:
    if not fig["compared"]:
        print(f"[drift] {label}: 0 players compared")
        return
    print(f"[drift] {label}: {fig['compared']} compared; exact (within {EXACT}) "
          f"{fig['exact_share']:.1%}; inside the bar {fig['pass_share']:.1%}; "
          f"inside the tighter bar (0.5 plus 2%) {fig['tight_share']:.1%}")
    for pos, (gap, theirs) in sorted(fig["by_position"].items()):
        rel = f"{gap / theirs:+.2%}" if theirs else "n/a"
        print(f"[drift]   position {pos}: summed gap {gap:+.1f} ({rel})")
    for grp, gap in sorted(fig["by_group"].items()):
        print(f"[drift]   dominant group {grp}: summed gap {gap:+.1f}")


# %%
def load_nflverse(seasons: list[int], week_seasons: list[int]) -> dict[str, pd.DataFrame]:
    """The nflverse frames, as pandas: `reg` stats and snaps for `seasons`,
    week stats and schedules for `week_seasons`. A season nflverse has not
    started is left out."""
    import nflreadpy as nfl

    last = int(nfl.get_current_season())
    seasons = [s for s in seasons if s <= last]
    week_seasons = [s for s in week_seasons if s <= last]
    snap_seasons = [s for s in seasons if s >= SNAPS_FROM]
    loads = {
        "stats": (seasons, lambda: nfl.load_player_stats(seasons=seasons, summary_level="reg")),
        "snaps": (snap_seasons, lambda: nfl.load_snap_counts(seasons=snap_seasons)),
        "weeks": (week_seasons, lambda: nfl.load_player_stats(seasons=week_seasons, summary_level="week")),
        "schedule": (week_seasons, lambda: nfl.load_schedules(seasons=week_seasons)),
    }
    frames = {}
    for name, (asked, load) in loads.items():
        if not asked:
            frames[name] = pd.DataFrame()
            continue
        try:
            frames[name] = load().to_pandas()
        except Exception as exc:
            raise RuntimeError(f"nflverse {name} for {asked} could not be loaded: {exc}") from exc
    return frames


def _stored(name: str, dtypes: dict) -> pd.DataFrame:
    if etl.table_exists(name):
        return read_table(name)
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in dtypes.items()})


def main() -> int:
    periods_all = read_table("dim_scoring_period")
    season = current_season(periods_all)
    seasons = list(range(season - SEASONS_BACK, season + 1))
    categories = read_table("dim_scoring_category")
    rules_season_id, points = rule_points(read_table("dim_fantrax_scoring_rule"), categories)
    colmap, unmapped = column_map(categories, points)
    names = categories.set_index("category_id")
    for cat in unmapped:
        print(f"[info] category {cat} {names.at[cat, 'category_code']} ({names.at[cat, 'category_name']}) "
              f"has no nflverse column: it scores 0 and writes no rows")

    players = read_table("dim_nfl_players")
    crosswalk = read_table("dim_fantrax_crosswalk")
    positions = read_table("dim_position")
    links = read_table(etl.GSIS_LINK_TABLE) if etl.table_exists(etl.GSIS_LINK_TABLE) else pd.DataFrame()
    lookup = positions.drop_duplicates("position_raw").set_index("position_raw")["position_group"]
    scoring = read_table("fact_period_scoring") if etl.table_exists("fact_period_scoring") else pd.DataFrame()
    week_ids = sorted(scoring["season_id"].unique().tolist()) if len(scoring) else []

    stored_stats = _stored(STAT_TABLE, STAT_DTYPES)
    stored_players = _stored(PLAYER_TABLE, PLAYER_DTYPES)
    changed = rules_changed(stored_stats, stored_players, points, rules_season_id, colmap)
    held = set(stored_players["season"].unique().tolist())
    pull = sorted({season} | {s for s in seasons if changed or s not in held})
    print(f"[info] rules {rules_season_id}; {'changed since the stored rows' if changed else 'unchanged'}; "
          f"pulling seasons {pull}")

    nfl = load_nflverse(pull, [nfl_season(s) for s in week_ids])
    if nfl["stats"].empty:
        raise RuntimeError("nflverse returned no season stats: nothing is scored or written")
    confirmed = check_columns(nfl["stats"], colmap, "season stats")
    if not nfl["weeks"].empty:
        check_columns(nfl["weeks"], colmap, "week stats")
    blocks = sorted(c for c in nfl["stats"].columns if c.endswith("_blocks"))
    print(f"[ok] {len(confirmed)} mapped nflverse column(s) confirmed in the frame: {confirmed}")
    print(f"[info] block columns the frame holds: {blocks or 'none'}")

    stats = nfl["stats"][nfl["stats"]["season"].isin(pull)]
    stat_new, player_new, info = build_history(stats, nfl["snaps"], players, crosswalk, positions,
                                               colmap, points, rules_season_id, links)
    print(f"[info] {info['dropped_ids']} player id(s) dim_nfl_players lacks were dropped; "
          f"{sum(info['no_league_position'].values())} player-season(s) with no league position left out, "
          f"by group: {info['no_league_position']}")
    if info["unknown_positions"]:
        print(f"[warn] nflverse position(s) dim_position lacks, by player-seasons: "
              f"{info['unknown_positions']} -- add a dim_position row")
    print(f"[info] {info['games_from_stats_rows']} player-season(s) from {SNAPS_FROM} took stats-row games "
          f"(no mapped snap game)")

    keep = ~stored_stats["season"].isin(pull)
    history = pd.concat([stored_stats[keep], stat_new], ignore_index=True)
    player_all = pd.concat([stored_players[~stored_players["season"].isin(pull)], player_new],
                           ignore_index=True)
    fantrax_pos = fantrax_positions(crosswalk, lookup, links)

    problems: list[str] = []
    ytd = ytd_comparison(read_table("fact_fantrax_adp"), history, categories, lookup, links)
    fig = figures(ytd)
    print_figures(f"{YTD_SEASON} season totals", fig)
    for pos, f in tackle_fit(ytd, history[history["season"] == YTD_SEASON], categories, points).items():
        print(f"[drift]   {YTD_SEASON} tackle fit {pos} ({f['players']} players): fitted solo "
              f"{f['fit_solo']:.3f}, assisted {f['fit_assist']:.3f} (rules {f['rule_solo']:g}, "
              f"{f['rule_assist']:g}); inside the bar: rules {f['share_rules']:.1%}, fitted "
              f"{f['share_fitted']:.1%} (gap left {f['gap_fitted']:+.1f}), solo and assisted swapped "
              f"{f['share_swapped']:.1%} (gap {f['gap_swapped']:+.1f})")
    problems += failures(f"{YTD_SEASON}", fig)
    known = set(players["gsis_id"].dropna())
    for season_id in week_ids:
        nfl_year = nfl_season(season_id)
        per = periods_all[periods_all["season_id"] == season_id]
        positions_of = player_all[player_all["season"] == nfl_year].set_index("gsis_id")["position"]
        df, pinfo = period_comparison(nfl["weeks"][nfl["weeks"]["season"] == nfl_year], nfl["schedule"], per,
                                      scoring[scoring["season_id"] == season_id], crosswalk, positions_of,
                                      fantrax_pos, colmap, points, categories, links, known)
        print(f"[drift] {season_id}: periods held {pinfo['held']}, compared (closed) {pinfo['compared']}, "
              f"held but not closed {pinfo['not_closed']}, not compared (no Fantrax figure) "
              f"{pinfo['after_last_frozen']}; {pinfo['no_gsis_id']} scorer row(s) with no gsis_id")
        print(f"[drift] {season_id}: one Fantrax figure per scorer and period; "
              f"{pinfo['rows_disagree']} scorer-period(s) whose rows disagree by more than {ROW_AGREE}, "
              f"{pinfo['too_many_rows']} with more than {MAX_ROWS} rows")
        if pinfo["rows_disagree"]:
            problems.append(f"{season_id}: {pinfo['rows_disagree']} scorer-period(s) of fact_period_scoring "
                            f"whose rows disagree by more than {ROW_AGREE}")
        if pinfo["too_many_rows"]:
            problems.append(f"{season_id}: {pinfo['too_many_rows']} scorer-period(s) of fact_period_scoring "
                            f"with more than {MAX_ROWS} rows")
        for period, part in df.groupby("period"):
            print_figures(f"{season_id} period {int(period)}", figures(part))
            print(f"[drift]   Unit gaps: {', '.join(f'{u} {g:+.1f}' for u, g in unit_gaps(part).items())}")
            print(f"[drift]   misses: {miss_counts(part)}")
            print(f"[drift]   stored fact_period_scoring rows per player: "
                  f"{pinfo['rows_per_player'].get(int(period))}; weeks: {pinfo['weeks'].get(int(period))}")
        fig = figures(df)
        print_figures(f"{season_id} all compared periods", fig)
        print(f"[drift]   misses: {miss_counts(df)}")
        gaps = unit_gaps(df)
        zero_units = categories[categories["category_id"].isin(unmapped)].groupby("unit")["category_code"]
        for unit, codes in zero_units:
            print(f"[drift]   cost of the 0-scored {sorted(codes)} (the {unit} residual): "
                  f"{-gaps.get(unit, 0.0):+.1f} points over {len(df)} player-periods")
        problems += failures(f"{season_id}", fig)
    if problems:
        raise DriftError("drift past the threshold, nothing written: " + "; ".join(problems))
    print("[ok] drift inside the threshold")

    cur_same = (not changed and pull == [season]
                and same_rows(stat_new, stored_stats[stored_stats["season"] == season].reset_index(drop=True),
                              STAT_KEY)
                and same_rows(player_new,
                              stored_players[stored_players["season"] == season].reset_index(drop=True),
                              PLAYER_KEY))
    if cur_same:
        print(f"[ok] nothing changed for {season} and the rules are the same: nothing written")
        return 0
    total_p = write_table(PLAYER_TABLE, player_new, mode="replace_partition", partition={"season": pull})
    total_s = write_table(STAT_TABLE, stat_new, mode="replace_partition", partition={"season": pull})
    print(f"[ok] {PLAYER_TABLE}: {len(player_new)} rows for seasons {pull} ({total_p} total)")
    print(f"[ok] {STAT_TABLE}: {len(stat_new)} rows for seasons {pull} ({total_s} total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

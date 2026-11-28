# %% [markdown]
# # 04m_fantrax_matchup_scores  (public fxea getMatchupScores -- no auth)
#
# **Purpose:** `fact_matchup`'s Team Scores from Fantrax's public, no-login
# API (#520), in place of the logged-in `fxpa` schedule that 04s reads. One
# call per period, `getMatchupScores?period=N` -> `{period, matchups[]}`; a
# matchup holds `away` and `home`, each `{teamId, teamName, score,
# gamesPlayed}`, and a `categories` breakdown this step does not load.
#
# **Shadow** (#520, the owner's word of 2026-11-28): by default the step builds
# the rows, compares them period by period with the `fact_matchup` rows on
# hand (the fxpa build), prints the differences as counts and writes nothing.
# A shadow run never fails the run: an error is printed and the step exits 0.
# `--live` writes `fact_matchup`, and only when no period on hand differs.
# Turning `--live` on in the scheduled run is its own change, never during
# the fantasy playoffs (periods 13 to 17).
#
# **Which periods:** the regular-season periods of the league's own season
# whose end has passed and that are not `closed` in `dim_scoring_period`.
# The call serves live scores for the period in play, so a period is read
# once it has ended; it is replaced whole on every run until it is `closed`.
# `--periods` reads any period asked for and compares it; a period outside
# that list is never written.
#
# **Fails, and writes nothing, when:** a reply echoes a period other than the
# one asked for; its teams are not exactly dim_fantasy_teams' teams, each
# once; a score is not a number.
#
# **Outputs:**
# - `data/raw/fantrax_fxea_matchupscores_{year}_p{NN}.json` -- each reply,
#   stamped with `captured_at` (UTC) and `season_id` (untracked).
# - `fact_matchup.parquet` (`--live` only) -- two mirrored rows per matchup,
#   replace-by-`(season_id, period)`; `capture_date` is the Eastern day the
#   reply was read.
#
# **Run:**  python notebooks/04m_fantrax_matchup_scores.py [--periods 1-9] [--live]
#           python notebooks/04m_fantrax_matchup_scores.py --raw FILE [FILE ...]
#           (`--raw` compares saved replies: no network call, never writes)

# %%
import argparse
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
from etl_helpers import DATA, fantrax_public_get, read_table, table_exists, write_table

# league_id/raw_dir are 04a's; the season id and Update-Set states 04p's;
# the league clock 04r's.
fx = importlib.import_module("04a_fantrax_weekly_scrape")
lg = importlib.import_module("04p_fantrax_league_info")
rs = importlib.import_module("04r_fantrax_roster_state")
FX_CFG = fx.CFG

MATCHUP_PATH = DATA / "fact_matchup.parquet"
RAW_NAME = "fantrax_fxea_matchupscores_{year}_p{period:02d}.json"
PULL_DELAY_S = (0.5, 1.5)
POINTS_TOLERANCE = 0.01

MATCHUP_COLUMNS = ["season_id", "period", "team_key", "opponent_team_key", "is_home",
                   "fpts_for", "fpts_against", "capture_date"]
KEYS = ["season_id", "period", "team_key"]
DIFF_COUNTS = ("only_fxea", "only_fxpa", "opponent", "is_home", "fpts_for", "fpts_against")


# %%
def periods_to_read(periods: pd.DataFrame, now) -> list[int]:
    """One season's regular-season periods that have ended by `now` and are
    not `closed`. `periods` is that season's dim_scoring_period rows."""
    ended = ~periods["is_playoff"] & (periods["end_at"] <= now)
    due = periods[ended & ~periods["update_set_state"].eq(lg.CLOSED)]
    return sorted(int(p) for p in due["period"])


def _score(side: dict, where: str) -> float:
    score = side.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError(f"{where}: score {score!r} is not a number")
    return float(score)


def matchups_to_frame(body: dict, teams: pd.DataFrame, season_id: str, period: int,
                      capture_date) -> pd.DataFrame:
    """One getMatchupScores reply -> fact_matchup rows for `period`.

    Two mirrored rows per matchup, one per team: its opponent, whether it is
    the home side, and each side's score. `teams` is dim_fantasy_teams
    (`fantrax_team_id` -> `team_key`). Raises on a reply for another period,
    teams that are not exactly the dim's each once, or a score that is not a
    number.
    """
    echoed = body.get("period")
    if echoed is None or int(echoed) != period:
        raise ValueError(f"getMatchupScores period={period} echoed period {echoed}")
    key_of = dict(zip(teams["fantrax_team_id"], teams["team_key"]))
    recs, listed = [], []
    for i, m in enumerate(body.get("matchups") or []):
        where = f"getMatchupScores period {period} matchup {i}"
        away, home = m.get("away") or {}, m.get("home") or {}
        away_id, home_id = away.get("teamId"), home.get("teamId")
        away_pts, home_pts = _score(away, where), _score(home, where)
        listed += [away_id, home_id]
        if away_id in key_of and home_id in key_of:
            recs.append((key_of[away_id], key_of[home_id], False, away_pts, home_pts))
            recs.append((key_of[home_id], key_of[away_id], True, home_pts, away_pts))
    got, want = set(listed), set(key_of)
    if got != want:
        raise ValueError(f"getMatchupScores period {period}: {len(got)} teams, expected "
                         f"{len(want)} (missing {sorted(want - got)}; not in "
                         f"dim_fantasy_teams {sorted(got - want, key=str)})")
    if len(listed) != len(key_of):
        raise ValueError(f"getMatchupScores period {period}: {len(listed) // 2} matchups do "
                         f"not hold each of {len(key_of)} teams once")

    rows = pd.DataFrame.from_records(
        recs, columns=["team_key", "opponent_team_key", "is_home", "fpts_for", "fpts_against"])
    rows = rows.sort_values("team_key", ignore_index=True)
    df = pd.DataFrame({
        "season_id": pd.Series(season_id, index=rows.index, dtype="str"),
        "period": pd.Series(period, index=rows.index, dtype="int64"),
        "team_key": rows["team_key"].astype("str"),
        "opponent_team_key": rows["opponent_team_key"].astype("str"),
        "is_home": rows["is_home"].astype("bool"),
        "fpts_for": rows["fpts_for"].astype("float64"),
        "fpts_against": rows["fpts_against"].astype("float64"),
        "capture_date": pd.Series(capture_date, index=rows.index, dtype="datetime64[us]"),
    })
    return df[MATCHUP_COLUMNS]


# %%
def shadow_diff(fxea: pd.DataFrame, fxpa: pd.DataFrame) -> dict[str, int]:
    """Counts of the differences between two builds of one period's rows:
    teams compared, teams in one build only, and teams whose opponent, home
    side, fpts_for or fpts_against differ (points beyond 0.01)."""
    m = fxea.merge(fxpa, on=KEYS, how="outer", suffixes=("_fxea", "_fxpa"), indicator=True)
    both = m[m["_merge"] == "both"]

    def off(col: str) -> int:
        return int((both[f"{col}_fxea"] != both[f"{col}_fxpa"]).sum())

    def pts_off(col: str) -> int:
        return int(((both[f"{col}_fxea"] - both[f"{col}_fxpa"]).abs() > POINTS_TOLERANCE).sum())

    return {"compared": len(both),
            "only_fxea": int((m["_merge"] == "left_only").sum()),
            "only_fxpa": int((m["_merge"] == "right_only").sum()),
            "opponent": off("opponent_team_key"), "is_home": off("is_home"),
            "fpts_for": pts_off("fpts_for"), "fpts_against": pts_off("fpts_against")}


def compare(fxea: pd.DataFrame, on_hand: pd.DataFrame) -> dict[int, dict[str, int] | None]:
    """Per period of `fxea`: its shadow_diff against the rows on hand for the
    same season and period, or None when none are on hand."""
    out = {}
    for (season_id, period), rows in fxea.groupby(["season_id", "period"], sort=True):
        hand = on_hand[(on_hand["season_id"] == season_id) & (on_hand["period"] == period)]
        out[int(period)] = shadow_diff(rows, hand) if len(hand) else None
    return out


def differs(diff: dict[str, int] | None) -> bool:
    return diff is not None and any(diff[k] for k in DIFF_COUNTS)


def report(results: dict[int, dict[str, int] | None]) -> list[str]:
    lines = []
    for period, d in results.items():
        if d is None:
            lines.append(f"[shadow] period {period}: no fxpa rows on hand, nothing compared")
        else:
            lines.append(f"[shadow] period {period}: {d['compared']} teams compared; "
                         + ", ".join(f"{k} {d[k]}" for k in DIFF_COUNTS)
                         + (" -- DIFFERS" if differs(d) else " -- matches"))
    return lines


# %%
def read_reply(path: Path, default_season: str) -> tuple[dict, pd.Timestamp, str]:
    """A saved reply, the UTC time it was read and its season. A reply saved
    by hand has no stamp: the file's time and `default_season` stand in."""
    body = json.loads(Path(path).read_text(encoding="utf-8"))
    stamp = body.get("captured_at")
    captured = (pd.Timestamp(stamp) if stamp
                else pd.Timestamp(Path(path).stat().st_mtime, unit="s", tz="UTC"))
    return body, captured.tz_convert("UTC"), body.get("season_id") or default_season


def on_hand_rows() -> pd.DataFrame:
    return read_table("fact_matchup") if table_exists("fact_matchup") else \
        pd.DataFrame(columns=MATCHUP_COLUMNS)


def compare_raw(paths: list[Path], teams: pd.DataFrame, default_season: str) -> int:
    frames = []
    for path in paths:
        body, captured, season_id = read_reply(path, default_season)
        frames.append(matchups_to_frame(body, teams, season_id, int(body.get("period", -1)),
                                        rs.league_day(captured)))
    for line in report(compare(pd.concat(frames, ignore_index=True), on_hand_rows())):
        print(line)
    return 0


def run(asked: list[int], due: list[int], teams: pd.DataFrame, season_id: str, year: int,
        now, live: bool) -> int:
    raw_dir = Path(FX_CFG.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, period in enumerate(asked):
        if i:
            time.sleep(random.uniform(*PULL_DELAY_S))
        reply = fantrax_public_get("getMatchupScores", FX_CFG.league_id,
                                   expect=("period", "matchups"), period=period)
        stamped = {"captured_at": now.isoformat(), "season_id": season_id, **reply}
        (raw_dir / RAW_NAME.format(year=year, period=period)).write_text(
            json.dumps(stamped, indent=2), encoding="utf-8")
        frames.append(matchups_to_frame(reply, teams, season_id, period, rs.league_day(now)))
    if not frames:
        print(f"[ok] getMatchupScores: no ended, open regular-season period of {season_id}")
        return 0
    fxea = pd.concat(frames, ignore_index=True)
    results = compare(fxea, on_hand_rows())
    for line in report(results):
        print(line)
    if not live:
        return 0
    bad = sorted(p for p, d in results.items() if differs(d))
    if bad:
        print(f"[fail] fact_matchup: period(s) {bad} differ from the rows on hand; nothing written")
        return 1
    load = fxea[fxea["period"].isin(due)]
    if load.empty:
        print("[ok] fact_matchup: no period asked for is due, nothing written")
        return 0
    total = write_table("fact_matchup", load, mode="replace_partition",
                        keys=("season_id", "period"))
    print(f"[ok] fact_matchup: {len(load)} rows for {season_id}, periods "
          f"{load.groupby('period').size().to_dict()} -> {total} total rows "
          f"-> {MATCHUP_PATH.name}")
    return 0


# %%
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="fact_matchup's Team Scores from public getMatchupScores, in shadow "
                    "beside the fxpa build unless --live.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--raw", nargs="+", type=Path,
                      help="compare saved replies with the rows on hand: no call, no write")
    mode.add_argument("--live", action="store_true",
                      help="write fact_matchup when no period on hand differs")
    ap.add_argument("--periods", help="e.g. 9 or 1-9; default: every regular-season period "
                                      "that has ended and is not closed")
    args = ap.parse_args(argv)

    teams = read_table("dim_fantasy_teams")
    periods = read_table("dim_scoring_period") if table_exists("dim_scoring_period") else None
    if args.raw:
        if periods is None:
            raise ValueError("dim_scoring_period is missing -- run 04p first")
        return compare_raw(args.raw, teams, str(periods["season_id"].max()))

    try:
        now = pd.Timestamp.now(tz="UTC")
        info = fantrax_public_get("getLeagueInfo", FX_CFG.league_id, expect=("seasonYear",))
        season_id, year = lg.season_id_of(info), int(info["seasonYear"])
        if periods is None or season_id not in set(periods["season_id"]):
            raise ValueError(f"season {season_id} is not in dim_scoring_period -- run 04p first")
        due = periods_to_read(periods[periods["season_id"] == season_id], now)
        lo, _, hi = (args.periods or "").partition("-")
        asked = list(range(int(lo), int(hi or lo) + 1)) if args.periods else due
        return run(asked, due, teams, season_id, year, now, args.live)
    except Exception as e:
        if args.live:
            raise
        print(f"[shadow] getMatchupScores failed, nothing compared ({type(e).__name__}: {e})")
        return 0


if __name__ == "__main__":
    sys.exit(main())

"""
etl_checks.py — the publish-gate check suite (ADR-0008 amendment, #115).

Two tiers (decision 2):
  Gate   — our pipeline produced something broken. The owning Chain does not
           publish; its parquet is restored from git HEAD (run_pipeline.py).
  Review — the data mirrors Fantrax but disagrees with an expectation. Filed
           to data/review/review_check.csv; the publish goes ahead.

Table Gates take their parameters from docs/data_model.yml (decision 16):
grain uniqueness, required keys, schema (columns + dtypes) and shrink limit.
Domain checks (coverage, known contracts, Unit sums, Starter slots, matchup
mirrors, the Dead Money schedule and the two drop Review checks today; drift,
dirty edges and replay with #116) are functions here, registered in
DOMAIN_CHECKS. A Gate check returns error strings; a Review check returns
(row_key, detail) findings, one filed row each.

The Close checks (`close_errors`, decision 7) are not in the suite: 04p runs
them on one Scoring Period before it moves that period's Update-Set from
closing to closed.

The gate functions are pure (DataFrame + registry entry in, verdict out) so
tests drive them without parquet. `run_suite` does the I/O; `file_review`
applies the filing lifecycle (decision 8) to the local CSV until the #77
seam swaps it for ops.review_check.

Run the whole suite against the current snapshot:
    .\\run.ps1 scripts\\run_pipeline.py --check-only
"""
from __future__ import annotations

import io
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import pyarrow.parquet as pq
import yaml

import etl_cap as cap
from etl_helpers import DATA, REVIEW, read_stored

REPO = Path(__file__).resolve().parent.parent
MODEL_YML = REPO / "docs" / "data_model.yml"
REVIEW_CSV = REVIEW / "review_check.csv"

DEFAULT_SHRINK_LIMIT = 0.20   # decision 6: >20% drop vs last published snapshot
TEAMS_TOTAL = 28
TEAMS_PER_CONFERENCE = 14
UNIT_COLUMNS = ["fpts_offense", "fpts_defense", "fpts_special_teams"]
POINTS_TOLERANCE = 0.01       # Fantrax serves points to the cent
STARTER_SLOT = "Starter"
CLOSED = "closed"             # dim_scoring_period.update_set_state (04p's CLOSED)
DROP = "drop"                 # fact_roster_transactions.event_type
NO_STINT = "no_stint"         # fact_roster_transactions.contract_source (02d)
DEFAULT_SOURCE = "default"

# ops.review_check columns (ADR-0018 decision 11, as amended by ADR-0008 d8/d9).
FILING_COLUMNS = ["check_name", "table_name", "row_key", "detail", "run_id",
                  "created_at", "last_seen_at", "pending", "resolved_at",
                  "resolution"]


# ---- Registry -------------------------------------------------------------------
def load_registry(path: Path = MODEL_YML) -> dict[str, dict]:
    """docs/data_model.yml tables, keyed by table name."""
    with Path(path).open(encoding="utf-8") as fh:
        tables = yaml.safe_load(fh).get("tables") or []
    return {t["name"]: t for t in tables}


def table_key(entry: dict) -> list[str]:
    """Key columns: ADR-0018's `pk` once #108 adds it, else the informational
    `grain` ("col" or "(a, b, c)")."""
    pk = entry.get("pk")
    if pk:
        return [pk] if isinstance(pk, str) else list(pk)
    return [c.strip() for c in str(entry["grain"]).strip("()").split(",") if c.strip()]


def chain_tables(registry: dict[str, dict]) -> dict[str, list[str]]:
    """Chain -> its tables. Tables with no `chain` are manual-only."""
    out: dict[str, list[str]] = {}
    for name, entry in registry.items():
        if entry.get("chain"):
            out.setdefault(entry["chain"], []).append(name)
    return {c: sorted(ts) for c, ts in out.items()}


# ---- Table Gates (pure) ------------------------------------------------------------
def check_grain(df: pd.DataFrame, key: list[str]) -> tuple[int, int]:
    """(duplicate rows among complete-key rows, rows with a null key column).

    Uniqueness is checked only where every key column is non-null, so a new
    duplicate still blocks while null-key rows are filed for review instead."""
    complete = df[key].notna().all(axis=1)
    dupes = int(df.loc[complete].duplicated(subset=key).sum())
    return dupes, int((~complete).sum())


def check_required_keys(df: pd.DataFrame, cols: Iterable[str]) -> list[str]:
    errs = []
    for c in cols:
        if c not in df.columns:
            errs.append(f"{c}: column missing")
        elif n := int(df[c].isna().sum()):
            errs.append(f"{c}: {n} null")
    return errs


def _same_dtype(declared: str, real: str) -> bool:
    text = ("str", "string", "object")
    return real == declared or (declared in text and real in text)


def schema_errors(entry: dict, real_cols: dict[str, str]) -> list[str]:
    """Declared columns vs a real {column: dtype} schema (name + dtype).
    str/string/object count as one text family."""
    name = entry.get("name")
    declared = {c["name"]: str(c["dtype"]) for c in (entry.get("columns") or [])}
    errs = []
    missing = set(real_cols) - set(declared)
    extra = set(declared) - set(real_cols)
    if missing:
        errs.append(f"[{name}] parquet has undeclared columns: {sorted(missing)}")
    if extra:
        errs.append(f"[{name}] yaml declares columns not in parquet: {sorted(extra)}")
    for col, dtype in declared.items():
        if col in real_cols and not _same_dtype(dtype, real_cols[col]):
            errs.append(f"[{name}].{col}: yaml dtype '{dtype}' != parquet dtype '{real_cols[col]}'")
    return errs


def check_shrink(rows_now: int, rows_head: int | None,
                 limit: float = DEFAULT_SHRINK_LIMIT,
                 accepted: bool = False) -> str | None:
    """Collapse verdict vs the last published row count, or None if fine.
    New tables (no HEAD copy) and --accept-shrink tables never block; growth
    never blocks."""
    if rows_head is None or accepted:
        return None
    if rows_now == 0 and rows_head > 0:
        return f"collapsed to 0 rows (HEAD {rows_head})"
    if rows_head and (rows_head - rows_now) / rows_head > limit:
        return (f"shrank {rows_head} -> {rows_now} rows "
                f"({(rows_head - rows_now) / rows_head:.0%} > {limit:.0%})")
    return None


def head_row_count(table: str, repo: Path = REPO) -> int | None:
    """Row count of data/<table>.parquet at git HEAD (the last published
    snapshot), read from parquet metadata. None if the table isn't in HEAD."""
    r = subprocess.run(["git", "show", f"HEAD:data/{table}.parquet"],
                       cwd=repo, capture_output=True)
    if r.returncode != 0:
        return None
    return pq.ParquetFile(io.BytesIO(r.stdout)).metadata.num_rows


# ---- Domain checks -----------------------------------------------------------------
def coverage_errors(roster: pd.DataFrame, teams: pd.DataFrame) -> list[str]:
    """Roster State covers 28 teams, 14 per Conference (decision 4).
    `roster` needs team_key; `teams` is dim_fantasy_teams."""
    present = set(roster["team_key"].dropna())
    conf = teams.set_index("team_key")["conference"]
    errs = []
    if len(present) != TEAMS_TOTAL:
        errs.append(f"{len(present)} teams, expected {TEAMS_TOTAL}")
    unknown = present - set(conf.index)
    if unknown:
        errs.append(f"team_key not in dim_fantasy_teams: {sorted(unknown)}")
    got = conf[conf.index.isin(present)].value_counts()
    for c in sorted(conf.dropna().unique()):
        if int(got.get(c, 0)) != TEAMS_PER_CONFERENCE:
            errs.append(f"conference {c}: {int(got.get(c, 0))} teams, "
                        f"expected {TEAMS_PER_CONFERENCE}")
    return errs


def newest_period(df: pd.DataFrame) -> pd.DataFrame:
    """The newest Scoring Period of the newest season in a
    replace-by-(season_id, period) fact."""
    season = df[df["season_id"] == df["season_id"].max()]
    return season[season["period"] == season["period"].max()]


def contract_errors(rows: pd.DataFrame, contracts: pd.DataFrame) -> list[str]:
    """Every contract_id is a dim_contract row. `rows` needs contract_id."""
    unknown = sorted(set(rows["contract_id"].dropna()) - set(contracts["contract_id"]))
    return [f"contract_id not in dim_contract: {unknown}"] if unknown else []


def unit_sum_errors(scoring: pd.DataFrame) -> list[str]:
    """Every Period Scoring row's three Units sum to its fpts (ADR-0016
    amendment decision 1)."""
    off = (scoring[UNIT_COLUMNS].sum(axis=1) - scoring["fpts"]).abs() > POINTS_TOLERANCE
    return [f"{int(off.sum())} rows whose Units do not sum to fpts"] if off.any() else []


def starter_slot_errors(scoring: pd.DataFrame, state: pd.DataFrame) -> list[str]:
    """Every Period Scoring row is on that period's Roster State, and its
    is_starter is true exactly when its Roster Slot is Starter (#118)."""
    key = ["season_id", "period", "team_key", "scorer_id"]
    m = scoring.merge(state[key + ["roster_slot"]], on=key, how="left")
    off_roster = m["roster_slot"].isna()
    wrong = ~off_roster & (m["is_starter"] != m["roster_slot"].eq(STARTER_SLOT))
    errs = []
    if off_roster.any():
        errs.append(f"{int(off_roster.sum())} rows not on that period's fact_roster_state "
                    f"(periods {sorted(set(m.loc[off_roster, 'period']))})")
    if wrong.any():
        errs.append(f"{int(wrong.sum())} rows whose is_starter disagrees with the Roster Slot "
                    f"(periods {sorted(set(m.loc[wrong, 'period']))})")
    return errs


def mirror_errors(matchup: pd.DataFrame) -> list[str]:
    """Every matchup row has its mirror: the opponent's row for the same
    period, naming this team, on the other side, with the two scores swapped.
    With the grain Gate that puts each team in one matchup per period."""
    key = ["season_id", "period"]
    m = matchup.merge(matchup, left_on=key + ["opponent_team_key"], right_on=key + ["team_key"],
                      how="left", suffixes=("", "_opp"))
    alone = m["team_key_opp"].isna()
    wrong = ~alone & ((m["opponent_team_key_opp"] != m["team_key"])
                      | (m["is_home_opp"] == m["is_home"])
                      | ((m["fpts_for"] - m["fpts_against_opp"]).abs() > POINTS_TOLERANCE)
                      | ((m["fpts_against"] - m["fpts_for_opp"]).abs() > POINTS_TOLERANCE))
    errs = []
    if alone.any():
        errs.append(f"{int(alone.sum())} rows whose opponent has no row that period "
                    f"(periods {sorted(set(m.loc[alone, 'period']))})")
    if wrong.any():
        errs.append(f"{int(wrong.sum())} rows that do not mirror their opponent's row "
                    f"(periods {sorted(set(m.loc[wrong, 'period']))})")
    return errs


def scoring_coverage_errors(scoring: pd.DataFrame, teams: pd.DataFrame,
                            periods: pd.DataFrame) -> list[str]:
    """Period Scoring covers 28 teams in every period it holds, and holds
    every Scoring Period from 1 to the last closed one of each season
    (decision 4). `periods` is dim_scoring_period."""
    errs = []
    for (season_id, period), rows in scoring.groupby(["season_id", "period"]):
        errs += [f"{season_id} period {period}: {e}" for e in coverage_errors(rows, teams)]
    closed = periods[periods["update_set_state"].eq(CLOSED)]
    for season_id, last in closed.groupby("season_id")["period"].max().items():
        held = set(scoring.loc[scoring["season_id"] == season_id, "period"])
        missing = sorted(set(range(1, int(last) + 1)) - held)
        if missing:
            errs.append(f"{season_id}: no rows for period(s) {missing}, "
                        f"closed through period {int(last)}")
    return errs


def _of_period(df: pd.DataFrame, season_id: str, period: int) -> pd.DataFrame:
    return df[(df["season_id"] == season_id) & (df["period"] == period)]


def close_errors(season_id: str, period: int,
                 load: Callable[[str], pd.DataFrame]) -> list[str]:
    """The Close checks of one Scoring Period, read off the stored tables
    (decision 7; ADR-0016 amendment decision 10). An empty list means the
    period may close.

      - its Roster State covers 28 teams;
      - its Matchups hold every team once, and each pair mirrors;
      - per team, the Matchup's score is the sum of that team's Starter rows
        in Period Scoring, to 0.01.

    Decision 10's other leg (the Starter sum equals Fantrax's `totalFpts`) is
    enforced by 04s when the period loads. `load` is a table loader."""
    teams = load("dim_fantasy_teams")
    state = _of_period(load("fact_roster_state"), season_id, period)
    matchup = _of_period(load("fact_matchup"), season_id, period)
    scoring = _of_period(load("fact_period_scoring"), season_id, period)

    errs = [f"Roster State: {e}" for e in coverage_errors(state, teams)]
    errs += [f"Matchups: {e}" for e in coverage_errors(matchup, teams)]
    twice = sorted(set(matchup.loc[matchup["team_key"].duplicated(), "team_key"]))
    if twice:
        errs.append(f"Matchups: team(s) listed more than once: {twice}")
    errs += [f"Matchups: {e}" for e in mirror_errors(matchup)]

    starters = scoring[scoring["is_starter"].astype(bool)].groupby("team_key")["fpts"].sum()
    score = matchup.drop_duplicates("team_key").set_index("team_key")["fpts_for"]
    off = (score - starters.reindex(score.index, fill_value=0.0)).abs() > POINTS_TOLERANCE
    if off.any():
        errs.append(f"{int(off.sum())} team(s) whose Matchup score is not their "
                    f"Starter sum: {sorted(off[off].index)}")
    return errs


def _drops(ledger: pd.DataFrame) -> pd.DataFrame:
    return ledger[ledger["event_type"] == DROP]


def dead_money_errors(dead: pd.DataFrame, ledger: pd.DataFrame,
                      contracts: pd.DataFrame) -> list[str]:
    """fact_dead_money follows the schedule (ADR-0016 decision 5; #96):

      - dead_money is cap_hit_pct x contract_value, to the cent;
      - the charging contract is a guaranteed dim_contract row at that pct;
      - every row is a drop on the ledger, and never one that ends no stint;
      - a drop's rows carry its ledger terms, number the guaranteed years left
        on its contract, and start in the drop's season;
      - every drop that ends a stint on a guaranteed contract, with a salary,
        has a row (so a ledger rebuilt without 02f does not publish).
    """
    move = ["transaction_id", "scorer_id", "team_key"]
    errs = []
    off = (dead["dead_money"] - dead["cap_hit_pct"] * dead["contract_value"]).abs() > 0.01
    if off.any():
        errs.append(f"{int(off.sum())} rows whose dead_money is not "
                    "cap_hit_pct x contract_value")

    rate = contracts[contracts["guaranteed"].astype(bool)].set_index("contract_id")["cap_hit_pct"]
    charged = dead["charge_contract_id"].map(rate)
    bad = charged.isna() | ((charged - dead["cap_hit_pct"]).abs() > 1e-9)
    if bad.any():
        errs.append(f"{int(bad.sum())} rows whose charge_contract_id is not a guaranteed "
                    f"dim_contract row at that cap_hit_pct: "
                    f"{sorted(set(dead.loc[bad, 'charge_contract_id'].dropna()))}")

    drops = _drops(ledger)
    m = dead[move].drop_duplicates().merge(drops[move + ["contract_source"]], on=move,
                                           how="left", indicator=True)
    unknown = m["_merge"].eq("left_only")
    if unknown.any():
        errs.append(f"{int(unknown.sum())} charged moves are not a drop on the ledger")
    stintless = m["contract_source"].eq(NO_STINT)
    if stintless.any():
        errs.append(f"{int(stintless.sum())} charged drops end no stint")

    # Each charged drop against its own ledger row: the terms at the drop, one
    # row per guaranteed year left, the first in the drop's season and the
    # rest in later ones (the grain Gate keeps the seasons distinct).
    led = drops[move + ["season_id", "contract_id", "contract_value"]].rename(
        columns={"season_id": "drop_season", "contract_id": "drop_contract",
                 "contract_value": "drop_value"})
    j = dead.merge(led, on=move, how="inner")
    terms = (j["contract_id"] != j["drop_contract"]) | (
        (j["contract_value"] - j["drop_value"]).abs() > 0.01)
    if terms.any():
        errs.append(f"{int(terms.sum())} rows whose contract_id or contract_value is not "
                    "the ledger drop's")
    first = j["charge_contract_id"] == j["contract_id"]
    season = (first & (j["season_id"] != j["drop_season"])) | (
        ~first & (j["season_id"] <= j["drop_season"]))
    if season.any():
        errs.append(f"{int(season.sum())} rows charged to the wrong season")
    by_type = contracts[contracts["guaranteed"].astype(bool)]
    years_left = {
        c.contract_id: int(((by_type["contract_type"] == c.contract_type)
                            & (by_type["contract_year"] >= c.contract_year)).sum())
        for c in contracts.itertuples() if pd.notna(c.contract_year)}
    got = j.groupby(move)["season_id"].size()
    want = j.drop_duplicates(move).set_index(move)["contract_id"].map(years_left)
    short = got != want.reindex(got.index)
    if short.any():
        errs.append(f"{int(short.sum())} drops whose row count is not the guaranteed "
                    "years left on the contract")

    owed = drops[(drops["contract_source"] != NO_STINT) & drops["contract_value"].notna()
                 & drops["contract_id"].isin(rate.index)]
    missing = owed[move].merge(dead[move].drop_duplicates(), on=move, how="left", indicator=True)
    missing = missing["_merge"].eq("left_only")
    if missing.any():
        errs.append(f"{int(missing.sum())} drops of a guaranteed contract have no row "
                    "(run 02f after 02d)")
    return errs


def _move_key(row) -> str:
    return f"{row.transaction_id}|{row.scorer_id}|{row.team_key}"


def stintless_drop_findings(ledger: pd.DataFrame, state: pd.DataFrame) -> list[tuple[str, str]]:
    """One finding per drop that ends no stint (#96 decision 2): no draft
    pick, claim or trade into that team is on the ledger before it, so it
    makes no Dead Money. The detail says whether Roster State ever showed the
    copy on the dropping team before the drop took effect: if it did, the
    ledger is missing the move in and the drop may be owed."""
    out = []
    for d in _drops(ledger)[lambda x: x["contract_source"] == NO_STINT].itertuples():
        seen = state[(state["season_id"] == d.season_id) & (state["team_key"] == d.team_key)
                     & (state["scorer_id"] == d.scorer_id)]
        if pd.notna(d.period):
            seen = seen[seen["period"] < d.period]
        periods = sorted(int(p) for p in set(seen["period"]))
        shown = (f"Roster State shows the copy on {d.team_key} in period(s) {periods}: "
                 "the ledger is missing the move in" if periods
                 else f"no Roster State row shows the copy on {d.team_key} before the drop")
        when = f"period {int(d.period)}" if pd.notna(d.period) else "no period (another season)"
        out.append((_move_key(d), f"drop of {d.scorer_id} by {d.team_key} on "
                                  f"{pd.Timestamp(d.event_date).date()} ({when}) ends no stint; "
                                  f"no Dead Money charged; {shown}"))
    return out


def default_contract_drop_findings(ledger: pd.DataFrame,
                                   periods: pd.DataFrame) -> list[tuple[str, str]]:
    """One finding per drop priced on a default contract whose Scoring Period
    is not closed (#96 decision 6): no Roster State row and no preseason
    capture showed the stint, so the contract is a rule's guess until the
    period's Roster State is final. A drop with no period (another season's
    move) has no Scoring Period to wait for and is not listed."""
    closed = periods[periods["update_set_state"].eq(CLOSED)]
    closed = set(zip(closed["season_id"], closed["period"].astype(int)))
    out = []
    for d in _drops(ledger)[lambda x: x["contract_source"] == DEFAULT_SOURCE].itertuples():
        if pd.isna(d.period) or (d.season_id, int(d.period)) in closed:
            continue
        out.append((_move_key(d), f"drop of {d.scorer_id} by {d.team_key} in period "
                                  f"{int(d.period)} is priced on the default contract "
                                  f"{d.contract_id}; the period is not closed"))
    return out


def roster_membership_findings(roster: pd.DataFrame,
                               ledger: pd.DataFrame) -> list[tuple[str, str]]:
    """The ledger replay against the current roster, membership only (#97;
    zero grace, ADR-0008 decision 9). One finding per copy on the roster with
    no open stint on the ledger, and per open stint with no roster row.

    Held back, with one finding in their place: a roster built from the
    ledger replay (no saved reply; nothing to compare), and a ledger whose
    transaction capture is older than the roster read ("ledger is stale")."""
    if roster.empty:
        return []
    read = pd.to_datetime(roster["roster_captured_at"], utc=True).max()
    if pd.isna(read):
        return [("replay", "fact_fantasy_teams was built from the ledger replay: no saved "
                           "roster reply, so membership is not compared")]
    led = pd.to_datetime(roster["ledger_captured_at"], utc=True).max()
    if pd.isna(led) or led < read:
        when = "no transaction capture" if pd.isna(led) else f"captured {led.isoformat()}"
        return [("ledger_stale", f"the ledger is stale ({when}; roster read "
                                 f"{read.isoformat()}): per-row membership findings held "
                                 "until 04t and 02d run again")]
    extra, missing = cap.membership_differences(roster, cap.open_stints(ledger))
    return ([(f"{t}|{s}", f"{s} is on {t}'s roster with no open stint on the ledger")
             for t, s in extra]
            + [(f"{t}|{s}", f"the ledger has {s} on {t}, the roster does not")
               for t, s in missing])


@dataclass(frozen=True)
class DomainCheck:
    name: str
    tier: str                      # "gate" | "review"
    table: str
    # gate: error strings. review: (row_key, detail) findings, one filed each.
    fn: Callable[[Callable[[str], pd.DataFrame]], list]
    grace_periods: int = 0         # decision 9; used from #116


# Each fn takes a table loader (name -> DataFrame).
DOMAIN_CHECKS = [
    DomainCheck("coverage", "gate", "fact_fantasy_teams",
                lambda load: coverage_errors(load("fact_fantasy_teams"),
                                             load("dim_fantasy_teams"))),
    DomainCheck("coverage", "gate", "fact_roster_state",
                lambda load: coverage_errors(newest_period(load("fact_roster_state")),
                                             load("dim_fantasy_teams"))),
    DomainCheck("contract", "gate", "fact_roster_state",
                lambda load: contract_errors(load("fact_roster_state"),
                                             load("dim_contract"))),
    DomainCheck("coverage", "gate", "fact_period_scoring",
                lambda load: scoring_coverage_errors(load("fact_period_scoring"),
                                                     load("dim_fantasy_teams"),
                                                     load("dim_scoring_period"))),
    DomainCheck("unit_sum", "gate", "fact_period_scoring",
                lambda load: unit_sum_errors(load("fact_period_scoring"))),
    DomainCheck("starter_slot", "gate", "fact_period_scoring",
                lambda load: starter_slot_errors(load("fact_period_scoring"),
                                                 load("fact_roster_state"))),
    DomainCheck("mirror", "gate", "fact_matchup",
                lambda load: mirror_errors(load("fact_matchup"))),
    DomainCheck("schedule", "gate", "fact_dead_money",
                lambda load: dead_money_errors(load("fact_dead_money"),
                                               load("fact_roster_transactions"),
                                               load("dim_contract"))),
    DomainCheck("stintless_drop", "review", "fact_roster_transactions",
                lambda load: stintless_drop_findings(load("fact_roster_transactions"),
                                                     load("fact_roster_state"))),
    DomainCheck("default_contract_drop", "review", "fact_roster_transactions",
                lambda load: default_contract_drop_findings(load("fact_roster_transactions"),
                                                            load("dim_scoring_period"))),
    DomainCheck("roster_membership", "review", "fact_fantasy_teams",
                lambda load: roster_membership_findings(load("fact_fantasy_teams"),
                                                        load("fact_roster_transactions"))),
]


# ---- Suite ----------------------------------------------------------------------
@dataclass
class Result:
    check: str
    table: str
    chain: str | None
    tier: str                      # "gate" | "review"
    ok: bool
    detail: str = ""
    findings: list[tuple[str, str]] = field(default_factory=list)  # review: (row_key, detail)
    ran: bool = True               # False: the check raised before it could look


def run_suite(tables: Iterable[str] | None = None,
              accepted_shrink: Iterable[str] = (),
              registry: dict[str, dict] | None = None,
              data_dir: Path = DATA,
              head_rows: Callable[[str], int | None] = head_row_count) -> list[Result]:
    """Run every Table Gate and domain check for `tables` (default: every
    registered table). Never raises on bad data — failures come back as
    Results."""
    registry = registry if registry is not None else load_registry()
    tables = sorted(registry) if tables is None else sorted(set(tables))
    accepted = set(accepted_shrink)
    cache: dict[str, pd.DataFrame] = {}

    def load(name: str) -> pd.DataFrame:
        if name not in cache:
            cache[name] = read_stored(name, data_dir)
        return cache[name]

    results: list[Result] = []
    for name in tables:
        entry = registry[name]
        chain = entry.get("chain")

        def add(check, tier, errs, findings=()):
            results.append(Result(check, name, chain, tier, not errs and not findings,
                                  "; ".join(errs), list(findings)))

        try:
            df = load(name)
        except Exception as e:   # missing or unreadable parquet blocks the Chain
            add("schema", "gate", [f"cannot read data/{name}.parquet: {e}"])
            continue

        add("schema", "gate", schema_errors(entry, {c: str(d) for c, d in df.dtypes.items()}))
        key = table_key(entry)
        if set(key) - set(df.columns):
            add("grain", "gate", [f"grain columns missing: {sorted(set(key) - set(df.columns))}"])
        else:
            dupes, null_key = check_grain(df, key)
            add("grain", "gate", [f"{dupes} duplicate rows on {key}"] if dupes else [])
            add("grain_null_key", "review", [],
                [("*", f"{null_key} of {len(df)} rows have a null grain column")]
                if null_key else [])
        add("required_keys", "gate", check_required_keys(df, entry.get("required_keys") or []))
        verdict = check_shrink(len(df), head_rows(name),
                               float(entry.get("shrink_limit", DEFAULT_SHRINK_LIMIT)),
                               name in accepted)
        add("shrink", "gate", [verdict] if verdict else [])

    for dc in DOMAIN_CHECKS:
        if dc.table not in tables:
            continue
        chain = registry[dc.table].get("chain")
        try:
            found = dc.fn(load)
        except Exception as e:
            # A Review check that cannot run is reported, files nothing and
            # clears nothing (`ran` False); a Gate that cannot run blocks.
            results.append(Result(dc.name, dc.table, chain, dc.tier, False,
                                  f"check raised: {e}", ran=False))
            continue
        if dc.tier == "review":
            results.append(Result(dc.name, dc.table, chain, dc.tier, not found,
                                  findings=list(found)))
        else:
            results.append(Result(dc.name, dc.table, chain, dc.tier, not found,
                                  "; ".join(found)))
    return results


# ---- Filing (decision 8) -----------------------------------------------------------
def _is_open(df: pd.DataFrame) -> pd.Series:
    return df["resolved_at"].fillna("").astype(str) == ""


def file_findings(existing: pd.DataFrame, findings: list[dict],
                  checks_run: set[tuple[str, str]], run_id: str,
                  now: str) -> tuple[pd.DataFrame, dict]:
    """Apply one run's Review findings to the filing table.

    One open row per (check_name, table_name, row_key). A repeat updates
    last_seen_at, run_id and the detail (so a count stays current). An open
    row this run no longer sees resolves as 'cleared' — but only if its check
    ran this run, so a partial run can't clear another Chain's rows. A
    recurrence after clearing opens a new row. `pending` (grace, decision 9)
    is always False until #116."""
    out = existing.reindex(columns=FILING_COLUMNS).copy()
    out = out.astype(object).where(out.notna(), "")
    seen = {(f["check_name"], f["table_name"], f["row_key"]): f for f in findings}
    stats = {"opened": 0, "repeated": 0, "cleared": 0}

    handled = set()
    for i in out.index[_is_open(out)]:
        k = (out.at[i, "check_name"], out.at[i, "table_name"], str(out.at[i, "row_key"]))
        if k in seen:
            out.loc[i, ["last_seen_at", "run_id", "detail"]] = [now, run_id, seen[k]["detail"]]
            handled.add(k)
            stats["repeated"] += 1
        elif k[:2] in checks_run:
            out.loc[i, ["resolved_at", "resolution"]] = [now, "cleared"]
            stats["cleared"] += 1

    new = [{"check_name": k[0], "table_name": k[1], "row_key": k[2],
            "detail": f["detail"], "run_id": run_id, "created_at": now,
            "last_seen_at": now, "pending": False, "resolved_at": "",
            "resolution": ""}
           for k, f in seen.items() if k not in handled]
    stats["opened"] = len(new)
    if new:
        out = pd.concat([out, pd.DataFrame(new, columns=FILING_COLUMNS)], ignore_index=True)
    stats["open"] = int(_is_open(out).sum())
    return out, stats


def review_findings(results: list[Result]) -> tuple[list[dict], set[tuple[str, str]]]:
    """Review-tier Results -> (findings, the (check, table) pairs that ran)."""
    findings, ran = [], set()
    for r in results:
        if r.tier != "review" or not r.ran:
            continue
        ran.add((r.check, r.table))
        findings += [{"check_name": r.check, "table_name": r.table,
                      "row_key": row_key, "detail": detail}
                     for row_key, detail in r.findings]
    return findings, ran


def file_review(results: list[Result], run_id: str,
                path: Path = REVIEW_CSV, now: str | None = None) -> dict:
    """Read the filing CSV, apply this run's Review findings, write it back.
    Returns {opened, repeated, cleared, open}."""
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = Path(path)
    existing = (pd.read_csv(path, dtype=str, keep_default_na=False)
                if path.exists() else pd.DataFrame(columns=FILING_COLUMNS))
    findings, ran = review_findings(results)
    out, stats = file_findings(existing, findings, ran, run_id, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return stats

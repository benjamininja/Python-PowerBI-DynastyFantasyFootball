"""
etl_checks.py — the publish-gate check suite (ADR-0008 amendment, #115).

Two tiers (decision 2):
  Gate   — our pipeline produced something broken. The owning Chain does not
           publish; its parquet is restored from git HEAD (run_pipeline.py).
  Review — the data mirrors Fantrax but disagrees with an expectation. Filed
           to data/review/review_check.csv; the publish goes ahead.

Table Gates take their parameters from docs/data_model.yml (decision 16):
grain uniqueness, required keys, schema (columns + dtypes) and shrink limit.
Domain checks (coverage today; Close checks, drift, dirty edges and replay
with #116) are functions here, registered in DOMAIN_CHECKS.

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

from etl_helpers import DATA, REVIEW

REPO = Path(__file__).resolve().parent.parent
MODEL_YML = REPO / "docs" / "data_model.yml"
REVIEW_CSV = REVIEW / "review_check.csv"

DEFAULT_SHRINK_LIMIT = 0.20   # decision 6: >20% drop vs last published snapshot
TEAMS_TOTAL = 28
TEAMS_PER_CONFERENCE = 14

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
    duplicate still blocks while known null-key rows (e.g. Composite dynasty
    rows with no source_player_id) are filed for review instead."""
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


def latest_partition(df: pd.DataFrame) -> pd.DataFrame:
    """The most recent weekly snapshot (max capture_date) of a
    replace-by-(season, week) fact."""
    return df[df["capture_date"] == df["capture_date"].max()]


@dataclass(frozen=True)
class DomainCheck:
    name: str
    tier: str                      # "gate" | "review"
    table: str
    fn: Callable[[Callable[[str], pd.DataFrame]], list[str]]
    grace_periods: int = 0         # decision 9; used from #116


# Each fn takes a table loader (name -> DataFrame) and returns error strings.
DOMAIN_CHECKS = [
    DomainCheck("coverage", "gate", "fact_fantasy_teams",
                lambda load: coverage_errors(load("fact_fantasy_teams"),
                                             load("dim_fantasy_teams"))),
    DomainCheck("coverage", "gate", "fact_roster_placement",
                lambda load: coverage_errors(latest_partition(load("fact_roster_placement")),
                                             load("dim_fantasy_teams"))),
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
            cache[name] = pd.read_parquet(Path(data_dir) / f"{name}.parquet")
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
        try:
            errs = dc.fn(load)
        except Exception as e:
            errs = [f"check raised: {e}"]
        results.append(Result(dc.name, dc.table, registry[dc.table].get("chain"),
                              dc.tier, not errs, "; ".join(errs)))
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
        if r.tier != "review":
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

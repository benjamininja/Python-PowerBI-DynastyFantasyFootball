"""Record one crosswalk override, from the Record a crosswalk override workflow (#431).

    record_crosswalk_override.py

Reads SCORER_ID, GSIS_ID, REPLACE and GITHUB_RUN_ID from the environment, checks
them against the stored tables, then writes one row to
`dim_fantrax_crosswalk_override` through the storage seam (origin `form`, note
`run <run id>`). It writes nothing unless every check passes. The checks run
twice: first as a preflight with no lock, then again inside
`etl.write_table_checked`, which under Postgres locks the override table and
reads the tables in the same transaction as the write (#451), so a second form
run checks against the first one's row. The next Daily
Run's 04z reads the row; this script does not rebuild the crosswalk.

The run log is public. The script takes no free text and prints the two ids
only after they pass their shape check, plus counts. A rejected input is never
echoed. An unexpected error prints its type only.
"""
import os
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
import etl_helpers as etl  # noqa: E402

OVERRIDE_TABLE = "dim_fantrax_crosswalk_override"
CROSSWALK_TABLE = "dim_fantrax_crosswalk"
PLAYERS_TABLE = "dim_nfl_players"
NEW_MARK = "new"
ORIGIN = "form"
COLUMNS = ["scorer_id", "gsis_id", "note", "recorded_at", "origin"]
SCORER_SHAPE = re.compile(r"[0-9a-z]{5}")
GSIS_SHAPE = re.compile(r"[0-9A-Za-z-]{1,24}")
RUN_SHAPE = re.compile(r"[0-9]{1,20}")


def _current(ids: pd.Series, links: pd.DataFrame | None) -> pd.Series:
    return ids.copy() if links is None else etl.current_gsis(ids, links)


def shape_problems(scorer_id: str, gsis_id: str, replace: str, run_id: str) -> list[str]:
    """What is wrong with the four inputs by their shape alone. No message
    holds an input."""
    problems = []
    if not SCORER_SHAPE.fullmatch(scorer_id):
        problems.append("scorer_id is not a Fantrax id (five lowercase letters or digits)")
    if gsis_id != NEW_MARK and not GSIS_SHAPE.fullmatch(gsis_id):
        problems.append("gsis_id is neither a registry id nor new")
    if replace not in ("true", "false", ""):
        problems.append("replace is neither true nor false")
    if not RUN_SHAPE.fullmatch(run_id):
        problems.append("GITHUB_RUN_ID is not a run id")
    return problems


def validate(scorer_id: str, gsis_id: str, replace: bool, crosswalk: pd.DataFrame,
             players: pd.DataFrame, overrides: pd.DataFrame,
             links: pd.DataFrame | None = None) -> list[str]:
    """The problems with recording `gsis_id` for `scorer_id`, given the stored
    tables; empty when the row may be written. Shapes are checked first
    (`shape_problems`), so the ids here are safe to name."""
    problems = []
    if scorer_id not in set(crosswalk["scorer_id"]):
        problems.append(f"scorer_id {scorer_id} is not in {CROSSWALK_TABLE}")
    if gsis_id != NEW_MARK:
        known = set(players["gsis_id"]) | (set(links["old_gsis_id"]) if links is not None else set())
        if gsis_id not in known:
            problems.append(f"gsis_id {gsis_id} is not in {PLAYERS_TABLE} and is not {NEW_MARK}")
        else:
            target = _current(pd.Series([gsis_id]), links).iat[0]
            for table, frame in ((CROSSWALK_TABLE, crosswalk), (OVERRIDE_TABLE, overrides)):
                other = frame[(frame["scorer_id"] != scorer_id) & frame["gsis_id"].notna()]
                mine = _current(other["gsis_id"], links) == target
                for sid in sorted(set(other.loc[mine, "scorer_id"])):
                    problems.append(f"gsis_id {gsis_id} is already claimed by scorer_id {sid} in {table}")
    if scorer_id in set(overrides["scorer_id"]) and not replace:
        problems.append(f"scorer_id {scorer_id} already has an override; tick replace to change it")
    return problems


def row(scorer_id: str, gsis_id: str, run_id: str, now=None) -> pd.DataFrame:
    stamp = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    return pd.DataFrame({
        "scorer_id": [scorer_id], "gsis_id": [gsis_id], "note": [f"run {run_id}"],
        "recorded_at": [stamp.tz_convert("UTC").floor("us")], "origin": [ORIGIN],
    }, columns=COLUMNS)


READS = {
    CROSSWALK_TABLE: ["scorer_id", "gsis_id"],
    PLAYERS_TABLE: ["gsis_id"],
    OVERRIDE_TABLE: ["scorer_id", "gsis_id"],
    etl.GSIS_LINK_TABLE: None,
}


def _inputs_from(stored: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """The four tables `validate` reads, from `{table: frame or None}`. A
    table that holds no rows is an error for the crosswalk and the players, an
    empty frame for the overrides and None for the links."""
    for table in (CROSSWALK_TABLE, PLAYERS_TABLE):
        if stored[table] is None:
            raise etl.TableNotFound(f"{table}: no data")
    overrides = stored[OVERRIDE_TABLE]
    if overrides is None:
        overrides = pd.DataFrame({"scorer_id": pd.Series(dtype=str), "gsis_id": pd.Series(dtype=str)})
    return stored[CROSSWALK_TABLE], stored[PLAYERS_TABLE], overrides, stored[etl.GSIS_LINK_TABLE]


def stored_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    crosswalk = etl.read_table(CROSSWALK_TABLE, columns=READS[CROSSWALK_TABLE])
    players = etl.read_table(PLAYERS_TABLE, columns=READS[PLAYERS_TABLE])
    overrides = (etl.read_table(OVERRIDE_TABLE, columns=READS[OVERRIDE_TABLE])
                 if etl.table_exists(OVERRIDE_TABLE)
                 else pd.DataFrame({"scorer_id": pd.Series(dtype=str), "gsis_id": pd.Series(dtype=str)}))
    links = etl.read_table(etl.GSIS_LINK_TABLE) if etl.table_exists(etl.GSIS_LINK_TABLE) else None
    return crosswalk, players, overrides, links


def _stop(problems: list[str], out) -> int:
    for line in problems:
        out(f"stopped: {line}")
    out("nothing was written")
    return 1


def run(env, out=print, now=None, inputs=None) -> int:
    """The checks, then the one write. Returns 0 on success, 1 on a stop."""
    scorer_id = (env.get("SCORER_ID") or "").strip()
    gsis_id = (env.get("GSIS_ID") or "").strip()
    replace = (env.get("REPLACE") or "").strip().lower()
    run_id = (env.get("GITHUB_RUN_ID") or "").strip()
    bad = shape_problems(scorer_id, gsis_id, replace, run_id)
    if bad:
        for line in bad:
            out(f"stopped: {line}")
        out("nothing was written")
        return 1
    guarded = inputs is None
    crosswalk, players, overrides, links = stored_inputs() if guarded else inputs
    problems = validate(scorer_id, gsis_id, replace == "true", crosswalk, players, overrides, links)
    out(f"storage: {os.environ.get('ETL_STORAGE') or 'parquet'}")
    out(f"read: {len(crosswalk)} crosswalk row(s), {len(players)} player(s), {len(overrides)} override(s)")
    if problems:
        return _stop(problems, out)
    new_row = row(scorer_id, gsis_id, run_id, now)
    if guarded:
        held = {}

        def check(stored):
            held["inputs"] = _inputs_from(stored)
            return validate(scorer_id, gsis_id, replace == "true", *held["inputs"])

        try:
            problems, total = etl.write_table_checked(OVERRIDE_TABLE, new_row, reads=READS, check=check)
        except etl.LockWaitTimeout as exc:
            return _stop([str(exc)], out)
        if problems:
            return _stop(problems, out)
        overrides = held["inputs"][2]
    else:
        total = etl.write_table(OVERRIDE_TABLE, new_row, mode="upsert")
    replaced = scorer_id in set(overrides["scorer_id"])
    out(f"recorded: scorer_id {scorer_id} -> {gsis_id} (origin {ORIGIN}, run {run_id})")
    out(f"replaced an earlier override: {'yes' if replaced else 'no'}")
    out(f"wrote {OVERRIDE_TABLE}: {total} row(s)")
    return 0


def main() -> int:
    try:
        return run(os.environ)
    except Exception as exc:
        print(f"stopped: {type(exc).__name__} (no detail printed: it may hold a value)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

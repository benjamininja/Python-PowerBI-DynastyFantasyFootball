"""One-time loader for the three private tables 02d and 04z read (#93, brief 6).

    load_draft_and_overrides.py [--check] [--raw-dir DIR]

The owner runs it once, on the PC, with ETL_STORAGE=postgres:

  - every `fantrax_draftresults_2026*.json` capture -> `fact_startup_draft_slot`
    (one row per slot, deduped on (division, round, pick) keeping the latest
    capture) and `dim_startup_draft_scorer` (the players the captures name)
  - `fantrax_crosswalk_overrides.csv` and the apply script's DECISIONS ->
    `dim_fantrax_crosswalk_override`

Checks first, writes after. It writes nothing unless every check passes, and
refuses if any of the three tables already holds a row. `--check` runs the
checks and stops. It prints table names, counts and Fantrax scorer ids, never
a name, a note or a cell. A mismatch on the overrides stops the run until the
planner rules.
"""
import argparse
import ast
import glob
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
import etl_helpers as etl  # noqa: E402

SLOT_TABLE = "fact_startup_draft_slot"
SCORER_TABLE = "dim_startup_draft_scorer"
OVERRIDE_TABLE = "dim_fantrax_crosswalk_override"
CROSSWALK_TABLE = "dim_fantrax_crosswalk"
TABLES = (SCORER_TABLE, SLOT_TABLE, OVERRIDE_TABLE)

DRAFT_PATTERN = "fantrax_draftresults_2026*.json"
OVERRIDES_FILE = "fantrax_crosswalk_overrides.csv"
APPLY_SCRIPT = REPO / "scripts" / "apply_fantrax_crosswalk_review.py"
SLOTS, MADE, UNMADE = 980, 975, 5
MANUAL, NEW = 26, 7
NEW_MARK = "new"
SLOT_KEY = ["division_id", "round", "pick_in_round"]
_TAGS = re.compile(r"<[^>]+>")


def draft_files(raw_dir: Path) -> list[Path]:
    return [Path(f) for f in glob.glob(str(raw_dir / DRAFT_PATTERN))]


def read_payloads(files) -> list[dict]:
    return [json.loads(Path(f).read_text(encoding="utf-8")) for f in files]


def slots_from_payloads(payloads: list[dict]) -> pd.DataFrame:
    """`getDraftResults` payloads, oldest capture first -> the slot table.

    Slots are deduped on (divisionId, round, pickNumber) keeping the latest
    capture, so an old and a new capture of one Division do not double-count.
    Only the slot's own fields are kept: no name, flag, account or division
    label of the capture reaches the table."""
    rows = []
    for payload in payloads:
        rows.extend(payload["responses"][0]["data"]["draftPicksOrdered"])
    picks = pd.DataFrame(rows).drop_duplicates(
        subset=["divisionId", "round", "pickNumber"], keep="last").reset_index(drop=True)
    absent = pd.Series([None] * len(picks), dtype=object)
    stamp = pd.to_numeric(picks["modifiedDate"] if "modifiedDate" in picks else absent,
                          errors="coerce")
    picked_at = pd.to_datetime(stamp, unit="ms", utc=True)
    scorer = picks["scorerId"] if "scorerId" in picks else absent
    return pd.DataFrame({
        "division_id": picks["divisionId"],
        "round": picks["round"].astype("int64"),
        "pick_in_round": picks["pickNumber"].astype("int64"),
        "team_id": picks["teamId"],
        "scorer_id": scorer.astype(object).where(scorer.notna(), None),
        "picked_at": picked_at,
    })


def scorers_from_payloads(payloads: list[dict]) -> pd.DataFrame:
    """The players the captures name, the first capture winning a duplicate,
    in the shape 04z's `_scorer_extras` builds."""
    seen = {}
    for payload in payloads:
        for s in payload["responses"][0]["data"].get("scorers", []):
            seen.setdefault(s["scorerId"], s)
    return pd.DataFrame({
        "scorer_id": list(seen),
        "player_name": [s["name"] for s in seen.values()],
        "position_raw": [_TAGS.sub("", s.get("posShortNames", "")) for s in seen.values()],
        "nfl_team": [s.get("teamShortName", "") for s in seen.values()],
        "is_rookie": [bool(s.get("rookie", False)) for s in seen.values()],
    }, columns=["scorer_id", "player_name", "position_raw", "nfl_team", "is_rookie"])


def draft_problems(slots: pd.DataFrame, scorers: pd.DataFrame) -> list[str]:
    problems = []
    made = int(slots["scorer_id"].notna().sum())
    for what, got, want in (("slots", len(slots), SLOTS), ("made slots", made, MADE),
                            ("unmade slots", len(slots) - made, UNMADE)):
        if got != want:
            problems.append(f"draft: {got} {what}, expected {want}")
    if not len(scorers):
        problems.append("draft: the captures name no player")
    return problems


def decisions_from_script(path: Path = APPLY_SCRIPT) -> dict:
    """The apply script's DECISIONS dict, read from its source. The script is
    not imported: it reads and writes tables as it loads."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "DECISIONS" for t in node.targets):
            return dict(ast.literal_eval(node.value))
    raise ValueError(f"{Path(path).name} holds no DECISIONS dict")


def read_overrides_csv(path: Path) -> pd.DataFrame:
    """The CSV's scorer_id, gsis_id and note, as text. Any other column is
    left out."""
    raw = pd.read_csv(path, dtype=str)
    keep = [c for c in ("scorer_id", "gsis_id", "note") if c in raw.columns]
    return raw[keep].reindex(columns=["scorer_id", "gsis_id", "note"])


def overrides_from(csv: pd.DataFrame | None, decisions: dict, recorded_at) -> tuple[pd.DataFrame, list[str]]:
    """The decisions table's rows and the problems found building them.

    The CSV is what 04z reads today, so its rows go in as origin `csv`; a
    DECISIONS entry with no CSV row goes in as `apply_script`. Two sources
    that disagree on one scorer_id, a blank id and a repeated scorer_id with
    two answers are problems, listed by scorer_id."""
    problems, rows = [], {}
    if csv is not None:
        blank = csv[csv["scorer_id"].isna() | csv["gsis_id"].isna()]
        if len(blank):
            problems.append(f"overrides: {len(blank)} CSV row(s) with no scorer_id or gsis_id")
        csv = csv.dropna(subset=["scorer_id", "gsis_id"])
        split = csv.groupby("scorer_id")["gsis_id"].nunique()
        for sid in sorted(split[split > 1].index):
            problems.append(f"overrides: scorer_id {sid} has two answers in the CSV")
        for r in csv.drop_duplicates("scorer_id", keep="last").itertuples(index=False):
            rows[r.scorer_id] = {"scorer_id": r.scorer_id, "gsis_id": r.gsis_id,
                                 "note": None if pd.isna(r.note) else r.note, "origin": "csv"}
    for sid, gsis in decisions.items():
        if sid in rows and rows[sid]["gsis_id"] != gsis:
            problems.append(f"overrides: scorer_id {sid} differs between the CSV and DECISIONS")
        elif sid not in rows:
            rows[sid] = {"scorer_id": sid, "gsis_id": gsis, "note": None, "origin": "apply_script"}
    frame = pd.DataFrame(list(rows.values()),
                         columns=["scorer_id", "gsis_id", "note", "origin"])
    frame["recorded_at"] = pd.Timestamp(recorded_at).tz_convert("UTC")
    return frame[["scorer_id", "gsis_id", "note", "recorded_at", "origin"]], problems


def crosswalk_problems(overrides: pd.DataFrame, crosswalk: pd.DataFrame) -> list[str]:
    """How the overrides differ from the crosswalk's `manual` and `new` rows,
    by count and scorer_id only."""
    problems = []
    xw = crosswalk.set_index("scorer_id")
    for method, want in (("manual", MANUAL), ("new", NEW)):
        got = int((crosswalk["match_method"] == method).sum())
        if got != want:
            problems.append(f"crosswalk: {got} {method} row(s), expected {want}")
        is_new = overrides["gsis_id"] == NEW_MARK
        mine = set(overrides.loc[is_new if method == "new" else ~is_new, "scorer_id"])
        theirs = set(crosswalk.loc[crosswalk["match_method"] == method, "scorer_id"])
        for sid in sorted(mine - theirs):
            problems.append(f"overrides: scorer_id {sid} is not a {method} row of the crosswalk")
        for sid in sorted(theirs - mine):
            problems.append(f"crosswalk: scorer_id {sid} is a {method} row with no override")
    manual = overrides[overrides["gsis_id"] != NEW_MARK]
    for r in manual.itertuples(index=False):
        if r.scorer_id in xw.index and xw.at[r.scorer_id, "match_method"] == "manual" \
                and xw.at[r.scorer_id, "gsis_id"] != r.gsis_id:
            problems.append(f"overrides: scorer_id {r.scorer_id} gsis_id differs from the crosswalk")
    return problems


def nonempty(tables=TABLES) -> list[str]:
    return [t for t in tables if etl.table_exists(t)]


def load(raw_dir: Path, *, check_only: bool = False, decisions: dict | None = None,
         crosswalk: pd.DataFrame | None = None, now=None, out=print) -> int:
    """Run the checks, then the writes. Returns 0 on success, 1 on a stop."""
    raw_dir = Path(raw_dir)
    files = draft_files(raw_dir)
    csv_path = raw_dir / OVERRIDES_FILE
    stops = []
    if not files:
        stops.append(f"no {DRAFT_PATTERN} capture in the raw folder")
    if not csv_path.exists():
        stops.append(f"no {OVERRIDES_FILE} in the raw folder")
    if stops:
        for line in stops:
            out(f"stopped: {line}")
        return 1

    slots = slots_from_payloads(read_payloads(sorted(files, key=lambda f: f.stat().st_mtime)))
    scorers = scorers_from_payloads(read_payloads(sorted(files)))
    decisions = decisions_from_script() if decisions is None else decisions
    overrides, problems = overrides_from(
        read_overrides_csv(csv_path), decisions,
        pd.Timestamp.now(tz="UTC").floor("us") if now is None else now)
    problems = draft_problems(slots, scorers) + problems
    xw = etl.read_table(CROSSWALK_TABLE) if crosswalk is None else crosswalk
    problems += crosswalk_problems(overrides, xw)
    for name, frame in ((SCORER_TABLE, scorers), (SLOT_TABLE, slots), (OVERRIDE_TABLE, overrides)):
        try:
            etl._check_batch(frame, etl._table_entry(name))
        except etl.StorageError as exc:
            problems.append(f"{name}: {str(exc).splitlines()[0]}")
    held = nonempty()
    problems += [f"{name} already holds rows; the loader fills an empty table once" for name in held]

    out(f"storage: {os.environ.get('ETL_STORAGE') or 'parquet'}")
    out(f"read: {len(slots)} slot(s), {len(scorers)} player(s), {len(overrides)} override(s)")
    if problems:
        for line in problems:
            out(f"stopped: {line}")
        out("nothing was written")
        return 1
    if check_only:
        out("checks passed; nothing was written (--check)")
        return 0
    for name, frame in ((SCORER_TABLE, scorers), (SLOT_TABLE, slots), (OVERRIDE_TABLE, overrides)):
        out(f"wrote {name}: {etl.write_table(name, frame)} row(s)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="run the checks, write nothing")
    ap.add_argument("--raw-dir", type=Path, default=etl.DATA / "raw",
                    help="folder holding the raw captures (default: data/raw)")
    args = ap.parse_args(argv)
    try:
        return load(args.raw_dir, check_only=args.check)
    except etl.StorageError as exc:
        print(f"stopped: {type(exc).__name__}: {(str(exc).splitlines() or [''])[0]}")
        return 1
    except Exception as exc:
        print(f"stopped: {type(exc).__name__} (no detail printed: it may hold a value)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Seed and apply the team-name crosswalk dim_fantasy_team_alias (#770).

Teams change their names often. A source that names a team only by its name
(the owner's hand download of the transaction history, a pick's owner hint)
resolves it through this crosswalk first, then the current names of
dim_fantasy_teams. This command is the only writer of the crosswalk.

- With no argument, the seed: every name the stored tables pair with a team
  id. These are the current names of dim_fantasy_teams, and the names the 04t
  capture in the raw folder gives beside a teamId, when a capture is there.
  A seed row is `decision seed`. A stored row is never changed: a name
  already stored for another team is counted as a conflict and left. A name
  the sources give to two teams is reused: it is not written, it is counted,
  and it stays on the owner's list as two_teams.
- `--apply`: the owner's list, data/review/review_team_names.csv, as the
  loader wrote it and the owner filled it. Each row with a team id is
  written: `guess` for a taken guess left as the loader filled it, else
  `owner`. An id not in dim_fantasy_teams, or a name the file gives two ids,
  is refused and counted. A blank row writes nothing.

Output is counts only: no team name or id. No network request.

Run from the repo root:
    .venv/Scripts/python.exe scripts/load_team_names.py
    .venv/Scripts/python.exe scripts/load_team_names.py --apply
"""
import argparse
import glob
import importlib
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
import etl_helpers as etl

rt = importlib.import_module("02d_fact_roster_transactions")

TABLE = etl.TEAM_ALIAS_TABLE
COLUMNS = ["name_clean", "fantrax_team_id", "decision", "score", "source", "recorded_at"]
TEAM_CELLS = ("team", "from", "to")
REVIEW_PATH = etl.TEAM_NAME_REVIEW_PATH
SEED_SOURCES = ("dim_fantasy_teams", "txn_capture")


def stored() -> pd.DataFrame:
    """The crosswalk as stored, or no rows."""
    if etl.table_exists(TABLE):
        return etl.read_table(TABLE)
    return pd.DataFrame(columns=COLUMNS)


def capture_pairs() -> tuple[list, int]:
    """(name, teamId) of every team cell of the 04t capture(s) that carries
    both, and the number of capture files read."""
    files = sorted(glob.glob(rt.TXN_GLOB))
    pairs = []
    for path in files:
        for row in rt.rows_from_pages(json.loads(Path(path).read_text(encoding="utf-8"))):
            for cell in row.get("cells") or []:
                if (cell.get("key") in TEAM_CELLS and cell.get("teamId")
                        and isinstance(cell.get("content"), str)):
                    pairs.append((cell["content"], cell["teamId"]))
    return pairs, len(files)


def _frame(rows: list) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["score"] = frame["score"].astype("Int64")
    frame["recorded_at"] = pd.to_datetime(frame["recorded_at"], utc=True)
    return frame


def seed_rows(teams: pd.DataFrame, held: pd.DataFrame, capture: list, now) -> tuple:
    """(the new seed rows, counts). The current names come first, so a name
    both sources give one team is recorded as from dim_fantasy_teams."""
    sources = [(etl.clean_team_name(n), t, SEED_SOURCES[0])
               for n, t in zip(teams["team_name"], teams["fantrax_team_id"])]
    sources += [(etl.clean_team_name(n), t, SEED_SOURCES[1]) for n, t in capture]
    valid = set(teams["fantrax_team_id"])
    counts = {"unknown_id": 0, "reused": 0, "conflict": 0, "stored": 0}
    ids, source = {}, {}
    for name, team_id, src in sources:
        if not name:
            continue
        if team_id not in valid:
            counts["unknown_id"] += 1
            continue
        ids.setdefault(name, set()).add(team_id)
        source.setdefault(name, src)
    have = dict(zip(held["name_clean"], held["fantrax_team_id"]))
    rows = []
    for name, found in sorted(ids.items()):
        if len(found) > 1:
            counts["reused"] += 1
        elif name in have:
            counts["stored" if have[name] in found else "conflict"] += 1
        else:
            rows.append((name, next(iter(found)), "seed", None, source[name], now))
    counts["new"] = len(rows)
    return _frame(rows), counts


def apply_rows(review: pd.DataFrame, teams: pd.DataFrame, held: pd.DataFrame, now) -> tuple:
    """(the rows the owner's list writes, counts)."""
    missing = [c for c in etl.TEAM_NAME_REVIEW_COLS if c not in review.columns]
    if missing:
        raise SystemExit(f"[error] {REVIEW_PATH.name} lacks the column(s) {missing} -- "
                         f"run the loader again to rebuild it")
    key_of = dict(zip(teams["team_key"], teams["fantrax_team_id"]))
    valid = set(teams["fantrax_team_id"])
    review = review.assign(fantrax_team_id=review["fantrax_team_id"].fillna("").astype(str).str.strip(),
                           name_clean=review["name"].map(etl.clean_team_name))
    filled = review[(review["fantrax_team_id"] != "") & (review["name_clean"] != "")]
    counts = {"blank": len(review) - len(filled), "unknown_id": 0, "two_ids": 0,
              "unchanged": 0, "replaced": 0, "guess": 0, "owner": 0}
    two_ids = set(filled.groupby("name_clean")["fantrax_team_id"].nunique().loc[lambda s: s > 1].index)
    have = {r.name_clean: (r.fantrax_team_id, r.decision) for r in held.itertuples()}
    rows, done = [], set()
    for r in filled.itertuples():
        if r.name_clean in two_ids:
            counts["two_ids"] += 1
            continue
        if r.fantrax_team_id not in valid:
            counts["unknown_id"] += 1
            continue
        if r.name_clean in done:
            continue
        done.add(r.name_clean)
        guess = r.reason == "guess_90" and key_of.get(r.best_guess_team_key) == r.fantrax_team_id
        decision = "guess" if guess else "owner"
        if have.get(r.name_clean) == (r.fantrax_team_id, decision):
            counts["unchanged"] += 1
            continue
        if r.name_clean in have:
            counts["replaced"] += 1
        counts[decision] += 1
        score = (int(float(r.best_guess_score))
                 if guess and pd.notna(pd.to_numeric(r.best_guess_score, errors="coerce")) else None)
        rows.append((r.name_clean, r.fantrax_team_id, decision, score, "review_file", now))
    return _frame(rows), counts


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Seed the team-name crosswalk, or apply the owner's list.")
    parser.add_argument("--apply", action="store_true",
                        help=f"write the owner's filled {REVIEW_PATH.name} into the crosswalk")
    return parser.parse_args(argv)


def main(argv=None) -> dict:
    args = parse_args(argv)
    teams = etl.read_table("dim_fantasy_teams")
    held = stored()
    now = pd.Timestamp.now(tz="UTC")
    if args.apply:
        if not REVIEW_PATH.exists():
            raise SystemExit(f"[error] no {REVIEW_PATH.name} to apply -- the loader writes it")
        rows, counts = apply_rows(pd.read_csv(REVIEW_PATH, dtype=str), teams, held, now)
        print(f"[info] {REVIEW_PATH.name}: {counts['owner']} owner row(s) and {counts['guess']} "
              f"guess row(s) to write ({counts['replaced']} replace a stored row), "
              f"{counts['unchanged']} already stored, {counts['blank']} blank")
        if counts["unknown_id"] or counts["two_ids"]:
            print(f"[warn] refused: {counts['unknown_id']} row(s) whose team id is not in "
                  f"dim_fantasy_teams, {counts['two_ids']} row(s) of a name given two team ids")
    else:
        capture, files = capture_pairs()
        if not files:
            print("[info] no 04t capture in the raw folder -- seeding from the current names only")
        rows, counts = seed_rows(teams, held, capture, now)
        print(f"[info] seed: {len(teams)} current name(s), {len(capture)} capture team cell(s) "
              f"from {files} file(s); {counts['new']} new row(s), {counts['stored']} already stored, "
              f"{counts['unknown_id']} cell(s) with a team id not in dim_fantasy_teams")
        if counts["conflict"]:
            print(f"[warn] {counts['conflict']} name(s) already stored for another team -- left as stored")
        if counts["reused"]:
            print(f"[warn] {counts['reused']} name(s) carried by two teams -- not written; post this "
                  f"count on #770 for the planner (the crosswalk's grain)")
    if len(rows):
        total = etl.write_table(TABLE, rows, mode="upsert")
        print(f"[ok] {TABLE}: {len(rows)} row(s) written, {total} in all")
    else:
        print(f"[ok] {TABLE}: nothing to write")
    return counts


if __name__ == "__main__":
    main()

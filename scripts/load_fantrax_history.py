"""Load the owner's weekly hand download of the league's transaction history (#761).

The owner downloads two CSV files from the league's Transactions history page
in his own browser (view CLAIM_DROP and view TRADE, team filter on all teams)
into the raw folder. This command reads the newest file of each view, turns
each row into a row of 04t's capture shape, and hands them to 02d's own
parser and ledger build, which write `fact_roster_transactions` (its trade,
claim and drop rows), `fact_trade_log` and `dim_roster_asset` through the
storage seam. It makes no network request.

- A move already on the stored ledger keeps Fantrax's id; a new move gets a
  minted `hand:` id, a hash of what groups it, so the same file loads the
  same way twice.
- A team name resolves through the crosswalk dim_fantasy_team_alias, then
  the current names of dim_fantasy_teams, then a fuzzy guess of 90 or more
  (#770). Every name not resolved by a stored name is listed, once, in
  data/review/review_team_names.csv for the owner: the names that need his
  team id first, the taken guesses last. `scripts/load_team_names.py --apply`
  writes that file into the crosswalk. `--write` refuses while a name
  resolves only by a guess not yet applied.
- A team or player still unresolved goes to
  data/review/review_txn_history.csv and is left out. A player is never
  guessed.
- Every load is first built in a shadow (the seam's capture mode, into
  data/review/txn_history_shadow/, its pick-review files beside it), and the
  run prints, as counts, how it agrees with the stored tables. `--write` then
  writes the store, and refuses, writing nothing, when the shadow lost a
  stored ledger move or trade-log row.
- Output is counts only: no name, scorer, team or pick (#761).

Run from the repo root:
    .venv/Scripts/python.exe scripts/load_fantrax_history.py [--write] [--raw-dir DIR]
"""
import argparse
import contextlib
import csv
import hashlib
import importlib
import io
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
import etl_helpers as etl
from etl_helpers import DATA, REVIEW

rt = importlib.import_module("02d_fact_roster_transactions")

FILE_LABEL = {"CLAIM_DROP": "Claims+Drops", "TRADE": "Trade"}
HEADER = {"CLAIM_DROP": ["Player", "Team", "Position", "Type", "Team", "Bid", "Date (CST)", "Week"],
          "TRADE": ["Player", "Team", "Position", "From", "To", "Date (CST)", "Week"]}
COLUMNS = {"CLAIM_DROP": ["player", "nfl_team", "position", "type", "team", "bid", "date", "week"],
           "TRADE": ["player", "nfl_team", "position", "from", "to", "date", "week"]}
TYPE_CODE = {"Claim": "CLAIM", "Drop": "DROP"}
SKIPPED_TYPES = frozenset({"Lineup Change"})
DATE_FORMAT = "%a %b %d, %Y, %I:%M%p"
MINTED = "hand:"
PICK = re.compile(r"^(\d{4}) Draft Pick, Round (\d+)(?: Pick (\d+))?(?: \((.*)\))?$")
STAMP = re.compile(r"-(\d{8})(?:_(\d{4}))?\.csv$")
SHADOW_DIR = REVIEW / "txn_history_shadow"
REVIEW_PATH = REVIEW / "review_txn_history.csv"
TEAM_REVIEW_PATH = etl.TEAM_NAME_REVIEW_PATH
REVIEW_COLS = ["view", "line", "player", "team", "reason"]
SHADOW_TABLES = ("fact_roster_transactions", "fact_trade_log", "dim_roster_asset")


# ---- Files ---------------------------------------------------------------------
def newest_file(raw_dir, view: str):
    """The newest download of `view` in `raw_dir`: by the date and `_hhmm` in
    its name, then by file time. None when there is none."""
    files = list(Path(raw_dir).glob(f"Fantrax-Transaction-History-{FILE_LABEL[view]}-*.csv"))

    def order(path):
        return stamp_of(path) or "", path.stat().st_mtime
    return max(files, key=order) if files else None


def stamp_of(path):
    """The `YYYYMMDD_hhmm` a download's name carries, None when it has none."""
    m = STAMP.search(Path(path).name)
    return f"{m.group(1)}_{m.group(2) or '0000'}" if m else None


def unstamped_newer(raw_dir, view: str, chosen) -> int:
    """Downloads of `view` with no stamp in their name, newer on disk than `chosen`."""
    return sum(1 for p in Path(raw_dir).glob(f"Fantrax-Transaction-History-{FILE_LABEL[view]}-*.csv")
               if stamp_of(p) is None and p.stat().st_mtime > Path(chosen).stat().st_mtime)


def read_view(path, view: str) -> pd.DataFrame:
    """One downloaded file as text, its columns named by position (the
    Claims+Drops file has `Team` twice), and `line` its line in the file."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if not rows or rows[0] != HEADER[view]:
        raise SystemExit(f"[error] {view}: the header is {rows[0] if rows else 'missing'}, "
                         f"expected {HEADER[view]} -- has the download changed shape?")
    frame = pd.DataFrame(rows[1:], columns=COLUMNS[view], dtype=str)
    frame["line"] = range(2, len(frame) + 2)
    return frame


def minute(text):
    """A `Date (CST)` cell as a timestamp, NaT when it does not read."""
    return pd.to_datetime(text, format=DATE_FORMAT, errors="coerce")


# ---- Names -> keys -------------------------------------------------------------
class Names:
    """Team and player lookups from the stored tables. A team name resolves
    through the crosswalk, then the current names, then a fuzzy guess of 90
    or more (#770); every name it cannot take goes on the owner's list."""

    def __init__(self, teams: pd.DataFrame, crosswalk: pd.DataFrame, roster: set,
                 aliases: pd.DataFrame | None = None):
        self.known = etl.team_names(teams, aliases)
        self.team_key = dict(zip(teams["fantrax_team_id"], teams["team_key"]))
        self.team_name = dict(zip(teams["team_key"], teams["team_name"]))
        self.resolved = {}      # name_clean -> crosswalk | current | guess
        self.listed = {}        # name_clean -> [name as first seen, rows, TeamMatch]
        self.players = {}
        for r in crosswalk.itertuples():
            self.players.setdefault(etl.clean_name_for_match(r.player_name), []).append(r)
        self.roster = roster

    def team(self, name):
        """(team_key, fantrax_team_id), or (None, reason)."""
        clean = etl.clean_team_name(name)
        if not clean:
            return None, "unknown_team"
        if clean in self.known.ambiguous:
            self._list(clean, name, etl.TeamMatch(None, "two_teams", None, None))
            return None, "ambiguous_team"
        team_id, origin = self.known.lookup.get(clean, (None, None))
        if team_id in self.team_key:
            self.resolved[clean] = origin
            return self.team_key[team_id], team_id
        match = (self.listed[clean][2] if clean in self.listed
                 else etl.match_team_name(clean, self.known.known))
        self._list(clean, name, match)
        if match.fantrax_team_id in self.team_key:
            self.resolved[clean] = "guess"
            return self.team_key[match.fantrax_team_id], match.fantrax_team_id
        return None, "unknown_team"

    def _list(self, clean, name, match):
        entry = self.listed.setdefault(clean, [str(name).strip(), 0, match])
        entry[1] += 1

    def guessed(self) -> int:
        """Names resolved only by a guess the crosswalk does not hold yet."""
        return sum(1 for how in self.resolved.values() if how == "guess")

    def name_counts(self) -> dict:
        """Distinct names: resolved by the crosswalk, by a current name, by a
        guess, and on the owner's list (two_teams, no_guess, guess_70_89)."""
        how = pd.Series(list(self.resolved.values()), dtype="object").value_counts()
        return {"crosswalk": int(how.get("crosswalk", 0)), "current": int(how.get("current", 0)),
                "guess": int(how.get("guess", 0)),
                "listed": sum(1 for _, _, m in self.listed.values() if m.fantrax_team_id is None)}

    def pick_hints(self) -> dict:
        """Each name this run resolved, in the form 02d's pick-hint lookup keys
        it (`hint.strip().lower()`), to its team_key."""
        out = {}
        for raw, _, match in self.listed.values():
            if match.fantrax_team_id in self.team_key:
                out[raw.strip().lower()] = self.team_key[match.fantrax_team_id]
        for clean, (team_id, _) in self.known.lookup.items():
            if team_id in self.team_key:
                out.setdefault(clean, self.team_key[team_id])
        return out

    def review_frame(self) -> pd.DataFrame:
        """The owner's list: one row per distinct name not resolved by a stored
        name. The rows that need him come first, the taken guesses last."""
        rows = []
        for clean, (raw, n, m) in self.listed.items():
            guess_key = self.team_key.get(m.best_guess)
            rows.append({"name": raw, "rows": n, "reason": m.reason,
                         "best_guess_team_key": guess_key,
                         "best_guess_team_name": self.team_name.get(guess_key),
                         "best_guess_score": m.score,
                         "fantrax_team_id": m.fantrax_team_id})
        frame = pd.DataFrame(rows, columns=etl.TEAM_NAME_REVIEW_COLS)
        order = {r: i for i, r in enumerate(etl.TEAM_NAME_REASONS)}
        frame["_order"] = frame["reason"].map(order)
        frame = frame.sort_values(["_order", "rows", "name"], ascending=[True, False, True], kind="stable")
        frame["best_guess_score"] = frame["best_guess_score"].astype("Int64")
        return frame.drop(columns="_order").reset_index(drop=True)

    def player(self, name, nfl_team, position, team_key):
        """(scorer_id, None) for exactly one crosswalk row of this name, else
        (None, reason). The position, the fantasy team's Roster State and
        then the NFL team (last: the crosswalk's copy of it can be stale)
        narrow several rows, each only where it leaves one."""
        cands = self.players.get(etl.clean_name_for_match(name), [])
        positions = set(re.split(r"[,/ ]+", str(position).strip())) - {""}
        narrowing = (lambda c: bool(positions & set(re.split(r"[,/ ]+", str(c.position_raw)))),
                     lambda c: (team_key, c.scorer_id) in self.roster,
                     lambda c: c.nfl_team == nfl_team)
        for keep in narrowing:
            if len(cands) <= 1:
                break
            narrowed = [c for c in cands if keep(c)]
            cands = narrowed or cands
        if len(cands) == 1:
            return cands[0].scorer_id, None
        return None, "unknown_player" if not cands else "ambiguous_player"


# ---- Ids -----------------------------------------------------------------------
def mint(*parts) -> str:
    """A minted transaction id: the same parts give the same id."""
    return MINTED + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def stored_ids(ledger, trade_log) -> tuple:
    """The ids the stored tables already give moves: (event type, scorer,
    team, minute) -> id from the ledger (a trade by its `trade` row), and
    (year, round, pick, from, to, minute) -> id for a pick leg."""
    moves = {}
    if ledger is not None:
        rows = ledger[ledger["event_type"].isin((rt.CLAIM_EVENT, rt.DROP_EVENT, rt.TRADE_IN))]
        for r in rows.itertuples():
            moves[(r.event_type, r.scorer_id, r.team_key, pd.Timestamp(r.event_date).floor("min"))] = r.transaction_id
    picks = {}
    if trade_log is not None:
        for r in trade_log[trade_log["asset_kind"] == "pick"].itertuples():
            pick = 0 if pd.isna(r.pick_in_round) else int(r.pick_in_round)
            picks[(int(r.draft_year), int(r.draft_round), pick, r.team_key_from, r.team_key_to,
                   pd.Timestamp(r.event_date).floor("min"))] = r.transaction_id
    return moves, picks


# ---- Rows of 04t's shape -------------------------------------------------------
def _cell(key, **kw):
    return {"key": key, **kw}


def claim_drop_rows(frame, names: Names, moves: dict, review: list, counts: dict) -> list:
    """Claims+Drops rows -> 04t rows. A claim and the drops of its team in the
    same minute share one minted id: the file does not pair them."""
    rows, minute_of = [], {}
    for r in frame.itertuples():
        if r.type in SKIPPED_TYPES:
            counts["skipped_type"] = counts.get("skipped_type", 0) + 1
            continue
        code = TYPE_CODE.get(r.type)
        (team_key, team_id), at = names.team(r.team), minute(r.date)
        reason = ("unknown_type" if code is None else team_id if team_key is None
                  else "bad_date" if pd.isna(at) else None)
        sid = None
        if reason is None:
            sid, reason = names.player(r.player, r.nfl_team, r.position, team_key)
        if reason is not None:
            review.append(("CLAIM_DROP", r.line, r.player, r.team, reason))
            continue
        event = rt.CLAIM_EVENT if code == "CLAIM" else rt.DROP_EVENT
        known = moves.get((event, sid, team_key, at))
        counts["reused" if known else "minted"] = counts.get("reused" if known else "minted", 0) + 1
        cells = [_cell("team", teamId=team_id), _cell("date", content=r.date),
                 _cell("week", content=r.week)]
        if code == "CLAIM":
            cells.append(_cell("bid", content=r.bid))
        rows.append({"txSetId": known or mint("claim_drop", at.isoformat(), team_key),
                     "transactionCode": code, "scorer": {"scorerId": sid}, "cells": cells})
        minute_of[(team_key, at)] = minute_of.get((team_key, at), []) + [code]
    # A drop whose team made another claim or drop in the same minute: the
    # file cannot say which claim it went with.
    counts["unsure_pairing"] = sum(codes.count("DROP") for codes in minute_of.values()
                                   if "CLAIM" in codes and len(codes) > 2)
    return rows


def _components(legs: list) -> list:
    """Legs of one minute -> a group number each: legs whose teams connect."""
    parent = {}

    def find(t):
        parent.setdefault(t, t)
        while parent[t] != t:
            t = parent[t]
        return t
    for leg in legs:
        parent[find(leg["from"])] = find(leg["to"])
    return [find(leg["from"]) for leg in legs]


def trade_rows(frame, names: Names, moves: dict, picks: dict, review: list, counts: dict,
               left_picks: list | None = None) -> list:
    """Trade rows -> 04t rows. The file has no trade id: legs of one minute
    whose teams connect are one trade. A trade the store already holds keeps
    its id; legs one minute groups but the store holds under several ids keep
    theirs, and a leg among them the store lacks is counted as ungroupable.
    A pick's owner hint is a team name too, so it is looked up (and listed)
    like the others. `left_picks` gets the (year, round) of each pick leg
    left out."""
    legs = []
    for r in frame.itertuples():
        (from_key, from_id), (to_key, to_id), at = names.team(r[4]), names.team(r.to), minute(r.date)
        reason = (from_id if from_key is None else to_id if to_key is None
                  else "bad_date" if pd.isna(at) else None)
        pick = PICK.match(r.player.strip())
        if pick and pick.group(4):
            names.team(pick.group(4))
        sid = None
        if reason is None and pick is None:
            sid, reason = names.player(r.player, r.nfl_team, r.position, from_key)
        if reason is not None:
            review.append(("TRADE", r.line, r.player if pick is None else "", r[4], reason))
            if pick and left_picks is not None:
                left_picks.append((int(pick.group(1)), int(pick.group(2))))
            continue
        leg = {"row": r, "from": from_key, "to": to_key, "from_id": from_id, "to_id": to_id,
               "at": at, "sid": sid, "pick": pick.groups() if pick else None}
        if pick:
            year, rnd, slot, _ = leg["pick"]
            leg["known"] = picks.get((int(year), int(rnd), int(slot or 0), from_key, to_key, at))
        else:
            leg["known"] = moves.get((rt.TRADE_IN, sid, to_key, at))
        legs.append(leg)

    by_minute = {}
    for leg in legs:
        by_minute.setdefault(leg["at"], []).append(leg)
    for at, group in by_minute.items():
        roots = _components(group)
        for comp in set(roots):
            trade = [leg for leg, root in zip(group, roots) if root == comp]
            known = sorted({leg["known"] for leg in trade if leg["known"]})
            teams = sorted({t for leg in trade for t in (leg["from"], leg["to"])})
            fallback = known[0] if len(known) == 1 else mint("trade", at.isoformat(), *teams)
            for leg in trade:
                if leg["known"] is None and len(known) > 1:
                    counts["ungroupable_legs"] = counts.get("ungroupable_legs", 0) + 1
                leg["id"] = leg["known"] or fallback
                counts["reused" if leg["known"] else "minted"] = (
                    counts.get("reused" if leg["known"] else "minted", 0) + 1)

    rows = []
    for leg in legs:
        r = leg["row"]
        row = {"txSetId": leg["id"], "transactionCode": None,
               "scorer": {"scorerId": leg["sid"]} if leg["sid"] else None,
               "cells": [_cell("from", teamId=leg["from_id"]), _cell("to", teamId=leg["to_id"]),
                         _cell("date", content=r.date), _cell("week", content=r.week)]}
        if leg["pick"]:
            year, rnd, slot, owner = leg["pick"]
            info = f"Round <b>{rnd}</b>" + (f" Pick <b>{slot}</b>" if slot else "")
            row["draftPickDisplayParts"] = {"year": f"<b>{year}</b>",
                                            "roundInfo": info + (f" ({owner})" if owner else "")}
        rows.append(row)
    return rows


# ---- Agreement with the store --------------------------------------------------
def move_keys(ledger) -> set:
    """The stored trade / claim / drop moves, as (event type, scorer, team, minute)."""
    if ledger is None:
        return set()
    rows = ledger[ledger["event_type"].isin((rt.CLAIM_EVENT, rt.DROP_EVENT, rt.TRADE_IN))]
    return {(r.event_type, r.scorer_id, r.team_key, pd.Timestamp(r.event_date).floor("min"))
            for r in rows.itertuples()}


def agreement(before, after, key: list, ignore=()) -> dict:
    """Rows of `after` against `before` on `key`: same, changed, new, gone."""
    if before is None:
        return {"same": 0, "changed": 0, "new": len(after), "gone": 0}
    cols = [c for c in after.columns if c not in key and c not in ignore and c in before.columns]
    merged = before.merge(after, on=key, how="outer", suffixes=("_b", "_a"), indicator=True)
    both = merged[merged["_merge"] == "both"]
    differs = pd.Series(False, index=both.index)
    for c in cols:
        b, a = both[f"{c}_b"], both[f"{c}_a"]
        differs |= ~((b == a).fillna(False) | (b.isna() & a.isna()))
    return {"same": int((~differs).sum()), "changed": int(differs.sum()),
            "new": int((merged["_merge"] == "right_only").sum()),
            "gone": int((merged["_merge"] == "left_only").sum())}


def _read(name):
    return etl.read_table(name) if etl.table_exists(name) else None


def team_names_review(names: Names) -> None:
    """Write the owner's list of team names (#770) and print its counts.
    The file is rebuilt on every run; a run with nothing to list removes it."""
    frame = names.review_frame()
    counts = names.name_counts()
    print(f"[info] team names: {counts['crosswalk']} resolved by the crosswalk, {counts['current']} "
          f"by a current name, {counts['guess']} taken by a guess of {etl.TEAM_NAME_TAKE} or more, "
          f"{counts['listed']} on the owner's list")
    if not len(frame):
        TEAM_REVIEW_PATH.unlink(missing_ok=True)
        return
    TEAM_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(TEAM_REVIEW_PATH, index=False)
    by_reason = frame["reason"].value_counts().to_dict()
    need = int((frame["reason"] != "guess_90").sum())
    print(f"[warn] {TEAM_REVIEW_PATH.name}: {need} name(s) need the owner's team id, "
          f"{len(frame) - need} taken guess(es) are only for him to look over {by_reason}")


def pick_gaps(shadow_dir, left_picks: list) -> dict:
    """The picks the shadow build left with an owner Fantrax does not report,
    split by whether a pick leg left out of the load has the same draft year
    and round (and so may explain the gap)."""
    path = Path(shadow_dir) / rt.PICK_OWNER_REVIEW_PATH.name
    if not path.exists():
        return {"explained": 0, "not_explained": 0}
    gaps = pd.read_csv(path, dtype=str)
    year_round = {}
    for name in ("fact_draft_pick", "fact_draft_pick_future"):
        frame = _read(name)
        if frame is not None:
            year_round.update({ref: (int(str(season)[:4]), int(rnd)) for ref, season, rnd in
                               zip(frame["pick_ref"], frame["draft_season"], frame["round"])})
    left = set(left_picks)
    explained = int(gaps["pick_ref"].map(lambda ref: year_round.get(ref) in left).sum())
    return {"explained": explained, "not_explained": len(gaps) - explained}


# ---- Run -----------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Load the hand-downloaded transaction history.")
    parser.add_argument("--raw-dir", type=Path, default=DATA / "raw",
                        help="folder holding the two downloads (default: data/raw)")
    parser.add_argument("--write", action="store_true",
                        help="write the store; without it the load is a shadow")
    parser.add_argument("--shadow-dir", type=Path, default=SHADOW_DIR,
                        help="where a shadow load writes its tables")
    return parser.parse_args(argv)


def main(argv=None) -> dict:
    args = parse_args(argv)
    paths = {view: newest_file(args.raw_dir, view) for view in FILE_LABEL}
    missing = [view for view, path in paths.items() if path is None]
    if missing:
        raise SystemExit(f"[error] no download of view(s) {missing} in the raw folder "
                         f"(Fantrax-Transaction-History-<view>-*.csv)")
    frames = {view: read_view(path, view) for view, path in paths.items()}
    print(f"[info] read {len(frames['CLAIM_DROP'])} Claims+Drops row(s) (download "
          f"{stamp_of(paths['CLAIM_DROP']) or 'with no stamp'}) and {len(frames['TRADE'])} Trade "
          f"row(s) (download {stamp_of(paths['TRADE']) or 'with no stamp'})")
    for view, path in paths.items():
        later = unstamped_newer(args.raw_dir, view, path)
        if later:
            print(f"[warn] {later} {view} download(s) with no `_hhmm` stamp in the name are newer "
                  f"on disk than the one read -- rename it with its stamp if it is this week's")

    lk = rt.load_lookups()
    state = _read("fact_roster_state")
    roster = set() if state is None else set(zip(state["team_key"], state["scorer_id"]))
    names = Names(etl.read_table("dim_fantasy_teams"), etl.read_table("dim_fantrax_crosswalk"), roster,
                  aliases=_read(etl.TEAM_ALIAS_TABLE))
    ledger, trade_log = _read("fact_roster_transactions"), _read("fact_trade_log")
    moves, picks = stored_ids(ledger, trade_log)

    review, counts, left_picks = [], {}, []
    rows = (trade_rows(frames["TRADE"], names, moves, picks, review, counts, left_picks)
            + claim_drop_rows(frames["CLAIM_DROP"], names, moves, review, counts))
    team_names_review(names)
    lk = lk._replace(name_lut={**names.pick_hints(), **lk.name_lut})
    if review:
        REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(review, columns=REVIEW_COLS).to_csv(REVIEW_PATH, index=False)
        by_reason = pd.Series([r[-1] for r in review]).value_counts().to_dict()
        print(f"[warn] {len(review)} row(s) name a team or player the stored tables cannot "
              f"name exactly ({by_reason}) -- left out, listed in {REVIEW_PATH.name}")
    elif REVIEW_PATH.exists():
        REVIEW_PATH.unlink()
    print(f"[info] ids: {counts.get('reused', 0)} move(s) keep the stored id, "
          f"{counts.get('minted', 0)} get a minted {MINTED} id; "
          f"{counts.get('skipped_type', 0)} lineup row(s) skipped")
    print("[info] not in the download, left blank or minted, never guessed: Fantrax's "
          "transaction id on a new move; the claim/drop pairing inside a minute "
          f"({counts.get('unsure_pairing', 0)} drop(s) share a minute with more than one move "
          f"of their team); a trade's grouping beyond its minute "
          f"({counts.get('ungroupable_legs', 0)} leg(s) the store holds apart)")

    trade_parsed, legs, stats = rt.parse_txn_rows(rows, lk.team_lut, lk.gsis_lut)
    rt.check_periods(legs, lk, quiet=True)
    loaded = {(l["kind"], l["scorer_id"], l["team_to"], pd.Timestamp(l["event_dt"]).floor("min"))
              for l in legs}
    store_only = move_keys(ledger) - loaded
    if store_only:
        by_type = pd.Series([k[0] for k in store_only]).value_counts().to_dict()
        by_season = (pd.Series([rt._season_id_for(k[3], lk.spans) for k in store_only], dtype="object")
                     .fillna("no season").value_counts().to_dict())
        print(f"[warn] {len(store_only)} stored move(s) are not in the download {by_type}; "
              f"by season {by_season}")
    startup = (ledger[ledger["event_type"] == rt.EVENT_TYPE] if ledger is not None
               else pd.DataFrame(columns=rt.LEDGER_COLS))

    def build(review_dir=None):
        slotted, future, ref2aid = rt.pick_assets()
        rt.post_moves(rows, trade_parsed, legs, stats, lk, slotted, future, ref2aid, startup,
                      quiet=True, review_dir=review_dir)
        return _read("fact_roster_transactions"), _read("fact_trade_log")

    # Every load is built in the shadow first, its pick-review files beside
    # it; `--write` then writes the store only when nothing stored is lost.
    args.shadow_dir.mkdir(parents=True, exist_ok=True)
    for name in SHADOW_TABLES:
        etl.captured_path(name, args.shadow_dir).unlink(missing_ok=True)
    with etl.capturing(args.shadow_dir):
        new_ledger, new_log = build(review_dir=args.shadow_dir)

    result = {"store_only": len(store_only), "review": len(review), **counts,
              "team_names": names.name_counts(),
              "pick_gaps": pick_gaps(args.shadow_dir, left_picks)}
    is_move = lambda f: None if f is None else f[f["event_type"].isin(rt.TXN_EVENT_TYPES)]
    if new_ledger is not None:
        result["ledger"] = agreement(is_move(ledger), is_move(new_ledger), rt.LEDGER_KEY, ("event_seq",))
    if new_log is not None:
        result["trade_log"] = agreement(trade_log, new_log, ["transaction_id", "asset_id"])
    if any(result["pick_gaps"].values()):
        print(f"[info] picks whose last owner Fantrax does not report: {result['pick_gaps']} "
              f"(explained = a left-out pick leg of the same draft year and round)")
    print(f"[ok] built in the shadow ({args.shadow_dir.name}); against the stored tables: "
          f"ledger moves {result.get('ledger')}, trade log {result.get('trade_log')}")
    if args.write:
        if names.guessed():
            raise SystemExit(f"[error] --write: {names.guessed()} team name(s) resolve only by a "
                             f"guess not yet applied -- run load_team_names.py --apply on "
                             f"{etl.TEAM_NAME_REVIEW_PATH.name} first; nothing written to the store")
        lost = {name: result[name]["gone"] for name in ("ledger", "trade_log")
                if result.get(name, {}).get("gone")}
        if lost or store_only:
            raise SystemExit(f"[error] --write would delete stored rows ({lost or 'ledger moves'}); "
                             f"nothing written to the store")
        with contextlib.redirect_stdout(io.StringIO()):
            build()
        print("[ok] written to the store")
    return result


if __name__ == "__main__":
    main()

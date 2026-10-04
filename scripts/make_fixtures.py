"""make_fixtures.py — cut committed parser-test fixtures out of data/raw.

ADR-0008 amendment decision 13: parser tests run on fixtures generated from
real Fantrax payloads, not hand-trimmed or synthetic ones. Each fixture is
  1. a row/team selection over one raw file (its trimmer), then
  2. pruned to an ALLOWLIST — a nested spec of the only keys kept — so owner,
     user, avatar and every other unlisted field is dropped by construction.
tests/test_fixture_allowlist.py asserts every committed fixture is already
pruned (prune(f) == f), so a hand edit can't sneak a field back in.

Regenerate when Fantrax changes shape (a deliberate PR — the fixture diff
shows the drift):
    .\\run.ps1 scripts\\make_fixtures.py            # all fixtures
    .\\run.ps1 scripts\\make_fixtures.py public_rosters.json
A git worktree has no data/raw (gitignored): pass --raw-dir <main checkout>\\data\\raw.

To cover a new parser (#118 live scoring + standings): add an ALLOWLIST spec,
a trimmer and a SOURCES row, regenerate, and test the parser against the new
file.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
OUT = REPO / "tests" / "fixtures" / "fantrax"

KEEP = True     # leaf: keep the scalar (or list of scalars) as-is
ANY = "*"       # dict spec key: any key (e.g. a {teamId: payload} map)


# ---- Allowlist ----------------------------------------------------------------------
def _cells(*keys: str) -> list:
    return [{k: KEEP for k in keys}]


# 04a player_stats_to_frame: list of getPlayerStats pages.
_PLAYERSTATS = [{"responses": [{"data": {
    "displayedPosOrGroup": KEEP,
    "tableHeader": {"cells": _cells("shortName")},
    "statsTable": [{
        "scorer": {k: KEEP for k in ("scorerId", "name", "posShortNames",
                                     "teamShortName", "rookie", "rank")},
        "cells": _cells("content"),
    }],
    "paginatedResultSet": {k: KEEP for k in ("totalNumPages", "pageNumber",
                                             "maxResultsPerPage", "totalNumResults")},
}}]}]

ALLOWLIST: dict[str, object] = {
    # BY_DATE pull (--rebuild-week): Fantrax serves no Rk, the parser derives it.
    "playerstats_page.json": _PLAYERSTATS,
    # YEAR_TO_DATE pull: scorer.rank served, Rk/%D/ADP header columns present.
    "playerstats_page_ranked.json": _PLAYERSTATS,
    # 04u build_future_picks: public getDraftPicks.
    "public_draftpicks.json": {"futureDraftPicks": [{k: KEEP for k in (
        "year", "round", "originalOwnerTeamId", "currentOwnerTeamId")}]},
    # 04p parse_scoring_periods / parse_divisions: public getLeagueInfo. A
    # team's `name` is its display name and is not listed.
    "league_info.json": {
        "seasonYear": KEEP,
        "scoringPeriods": [{k: KEEP for k in ("number", "startDate", "endDate")}],
        "playoffs": {k: KEEP for k in ("lastRegularSeasonPeriod", "firstPlayoffPeriod")},
        "teamInfo": {ANY: {"id": KEEP, "division": KEEP}},
    },
    # 04r check_reply / rosters_to_state: public getTeamRosters for one period.
    # A roster's `teamName` is the team's display name and is not listed.
    "public_rosters.json": {"period": KEEP, "rosters": {ANY: {"rosterItems": [{
        "id": KEEP, "status": KEEP, "salary": KEEP, "contract": {"name": KEEP}}]}}},
    # 04s schedule_periods / schedule_team_ids: getStandings view=SCHEDULE.
    "schedule.json": {"responses": [{"data": {"tableList": [{
        "caption": KEEP, "subCaption": KEEP,
        "rows": [{"cells": _cells("teamId")}],
    }]}}]},
    # 02d parse_draft_results / build_draft_picks: one Division's getDraftResults.
    "draft_results.json": {"responses": [{"data": {"draftPicksOrdered": [{k: KEEP for k in (
        "divisionId", "round", "pickNumber", "teamId", "scorerId", "modifiedDate")}]}}]},
    # 02d parse_txn_rows: 04t's transaction history, a list of pages. `content`
    # is listed for the date and week cells only -- trim_txn_history drops it
    # from the team cells, where it is the fantasy team's display name.
    "txn_history.json": [{"responses": [{"data": {"table": {"rows": [{
        "txSetId": KEEP,
        "transactionCode": KEEP,
        "scorer": {"scorerId": KEEP},
        "draftPickDisplayParts": {"roundInfo": KEEP, "year": KEEP},
        "cells": _cells("key", "teamId", "content"),
    }]}}}]}],
}


def _scalar(x) -> bool:
    return x is None or isinstance(x, (str, int, float, bool))


def prune(node, spec):
    """Keep only what `spec` lists. Raises on a shape the spec doesn't expect
    (Fantrax drift), and never lets a KEEP leaf carry a nested object."""
    if spec is KEEP:
        if _scalar(node) or (isinstance(node, list) and all(_scalar(x) for x in node)):
            return node
        raise ValueError(f"KEEP leaf holds a nested object: {type(node).__name__}")
    if isinstance(spec, list):
        if not isinstance(node, list):
            raise ValueError(f"expected a list, got {type(node).__name__}")
        return [prune(x, spec[0]) for x in node]
    if not isinstance(node, dict):
        if node is None:
            return None
        raise ValueError(f"expected an object, got {type(node).__name__}")
    if ANY in spec:
        return {k: prune(v, spec[ANY]) for k, v in node.items()}
    return {k: prune(node[k], sub) for k, sub in spec.items() if k in node}


# ---- Trimmers (row/team selection) --------------------------------------------------
def _data(resp: dict) -> dict:
    return resp["responses"][0]["data"]


def _active(row: dict) -> bool:
    return row["scorer"].get("teamShortName", "(N/A)") != "(N/A)"


def trim_playerstats(pages: list) -> list:
    """First OFFENSE + first DEFENSE page, ~10 rows: a few active rows each,
    one player present on both pages (first occurrence wins in the parser)
    and one '(N/A)' row (filtered out by the parser)."""
    off = next(p for p in pages if _data(p).get("displayedPosOrGroup") == "FOOTBALL_OFFENSE")
    de = next(p for p in pages if _data(p).get("displayedPosOrGroup") == "FOOTBALL_DEFENSE")
    off_rows, de_rows = _data(off)["statsTable"], _data(de)["statsTable"]
    de_ids = {r["scorer"]["scorerId"] for r in de_rows}
    shared = next(r for r in off_rows if _active(r) and r["scorer"]["scorerId"] in de_ids)
    sid = shared["scorer"]["scorerId"]
    na = next(r for r in off_rows if not _active(r))
    keep_off = [r for r in off_rows if _active(r) and r["scorer"]["scorerId"] != sid][:4]
    keep_de = [r for r in de_rows if _active(r) and r["scorer"]["scorerId"] != sid][:3]
    keep_de.append(next(r for r in de_rows if r["scorer"]["scorerId"] == sid))
    return [{"responses": [{"data": {**_data(off), "statsTable": keep_off + [shared, na]}}]},
            {"responses": [{"data": {**_data(de), "statsTable": keep_de}}]}]


def trim_draftpicks(raw: dict) -> dict:
    """Two teams' future picks, including at least one pick traded between
    them (currentOwnerTeamId != originalOwnerTeamId)."""
    picks = raw["futureDraftPicks"]
    traded = next(p for p in picks if p["originalOwnerTeamId"] != p["currentOwnerTeamId"])
    teams = {traded["originalOwnerTeamId"], traded["currentOwnerTeamId"]}
    return {"futureDraftPicks": [p for p in picks if p["originalOwnerTeamId"] in teams
                                 and p["currentOwnerTeamId"] in teams]}


def trim_league_info(raw: dict) -> dict:
    """Every Scoring Period (the parser needs them numbered 1..n) and two
    teams from each division."""
    by_division: dict[str, list] = {}
    for tid in sorted(raw["teamInfo"]):
        by_division.setdefault(raw["teamInfo"][tid]["division"].strip(), []).append(tid)
    if len(by_division) < 2:
        raise ValueError("fewer than two divisions in teamInfo")
    keep = [tid for ids in by_division.values() for tid in ids[:2]]
    return {**raw, "teamInfo": {tid: raw["teamInfo"][tid] for tid in keep}}


PUBLIC_ROSTER_STATUSES = {"ACTIVE", "RESERVE", "INJURED_RESERVE", "MINORS"}


def _trim_public_roster(items: list) -> list:
    """Up to two players per status, plus the first player on each contract."""
    keep, per_status, contracts = [], {}, set()
    for it in items:
        status, contract = it["status"], it["contract"]["name"]
        if per_status.get(status, 0) < 2 or contract not in contracts:
            per_status[status] = per_status.get(status, 0) + 1
            contracts.add(contract)
            keep.append(it)
    return keep


def trim_public_rosters(raw: dict) -> dict:
    """Two teams whose rosters hold all four statuses."""
    rosters = raw["rosters"]
    picked = [tid for tid in sorted(rosters) if PUBLIC_ROSTER_STATUSES
              <= {it["status"] for it in rosters[tid]["rosterItems"]}][:2]
    if len(picked) < 2:
        raise ValueError("fewer than two teams hold every roster status")
    return {**raw, "rosters": {tid: {**rosters[tid], "rosterItems": _trim_public_roster(
        rosters[tid]["rosterItems"])} for tid in picked}}


def trim_schedule(raw: dict) -> dict:
    """Two schedule weeks, two matchups each."""
    tables = [{**t, "rows": t.get("rows", [])[:2]} for t in _data(raw)["tableList"][:2]]
    return {"responses": [{"data": {"tableList": tables}}]}


DRAFT_FIXTURE_ROUNDS = 2


def trim_draft_results(raw: dict) -> dict:
    """Rounds 1-2 of one Division (round 1 whole: it defines the snake order),
    with at least one traded slot in round 2."""
    picks = _data(raw)["draftPicksOrdered"]
    keep = [p for p in picks if p["round"] <= DRAFT_FIXTURE_ROUNDS]
    per_round = max(p["pickNumber"] for p in picks)
    order = {p["pickNumber"]: p["teamId"] for p in keep if p["round"] == 1}
    if len(order) != per_round:
        raise ValueError("round 1 is not a full round")
    if not any(p["teamId"] != order[per_round + 1 - p["pickNumber"]]
               for p in keep if p["round"] == 2):
        raise ValueError("no traded slot in round 2 -- cut from the other Division")
    return {"responses": [{"data": {"draftPicksOrdered": keep}}]}


TXN_CELL_KEYS = {"from", "to", "team", "date", "week"}
TXN_CONTENT_KEYS = {"date", "week"}        # every other cell's content names a team
PICK_OWNER_PLACEHOLDER = "(Team (X))"
_PICK_OWNER_HINT = re.compile(r"\(.*\)\s*$")


def _scrub_txn_row(row: dict) -> dict:
    """Drop team display names: keep `content` on the date/week cells only,
    and swap the pick owner hint (a team name in trailing parentheses) for a
    placeholder of the same shape."""
    cells = [{k: v for k, v in c.items() if k != "content" or c["key"] in TXN_CONTENT_KEYS}
             for c in row["cells"] if c["key"] in TXN_CELL_KEYS]
    out = {**row, "cells": cells}
    parts = row.get("draftPickDisplayParts")
    if parts and "roundInfo" in parts:
        out["draftPickDisplayParts"] = {**parts, "roundInfo": _PICK_OWNER_HINT.sub(
            PICK_OWNER_PLACEHOLDER, parts["roundInfo"])}
    return out


def trim_txn_history(pages: list) -> list:
    """Two pages. Page 1: one trade with a player leg and a pick leg. Page 2:
    a claim-and-drop pair, a lone claim and a lone drop."""
    groups: dict[str, list] = {}
    for pg in pages:
        for r in _data(pg)["table"]["rows"]:
            groups.setdefault(r["txSetId"], []).append(r)

    def codes(rows):
        return sorted(str(r.get("transactionCode")) for r in rows)

    def has_scorer(r):
        return bool((r.get("scorer") or {}).get("scorerId"))

    trade = next(g for g in groups.values()
                 if all(r.get("transactionCode") is None for r in g)
                 and any(has_scorer(r) for r in g) and not all(has_scorer(r) for r in g))
    pair = next(g for g in groups.values() if codes(g) == ["CLAIM", "DROP"])
    claim = next(g for g in groups.values() if codes(g) == ["CLAIM"])
    drop = next(g for g in groups.values() if codes(g) == ["DROP"])

    def page(rows):
        return {"responses": [{"data": {"table": {"rows": [_scrub_txn_row(r) for r in rows]}}}]}

    return [page(trade), page(pair + claim + drop)]


# fixture -> (raw source file, trimmer). Bump the source when re-cutting from
# a newer capture.
SOURCES = {
    "playerstats_page.json": ("fantrax_playerstats_2026_01.json", trim_playerstats),
    "playerstats_page_ranked.json": ("fantrax_playerstats_2025_YTD.json", trim_playerstats),
    "public_draftpicks.json": ("fantrax_public_draftpicks.json", trim_draftpicks),
    "league_info.json": ("fantrax_public_leagueinfo.json", trim_league_info),
    "public_rosters.json": ("fantrax_public_rosters_2026_p01.json", trim_public_rosters),
    "schedule.json": ("fantrax_inseason_2026_schedule.json", trim_schedule),
    "draft_results.json": ("fantrax_draftresults_2026_svxeyvvgmmvk3jnh.json", trim_draft_results),
    "txn_history.json": ("fantrax_txn_history_2026.json", trim_txn_history),
}


def build(name: str, raw_dir: Path = RAW):
    src, trim = SOURCES[name]
    raw = json.loads((raw_dir / src).read_text(encoding="utf-8"))
    return prune(trim(raw), ALLOWLIST[name])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cut allowlisted parser fixtures from data/raw")
    ap.add_argument("names", nargs="*", help=f"fixtures to (re)build: {', '.join(SOURCES)}")
    ap.add_argument("--raw-dir", type=Path, default=RAW,
                    help="folder holding the raw captures (default: data/raw)")
    args = ap.parse_args(argv)
    unknown = set(args.names) - set(SOURCES)
    if unknown:
        ap.error(f"unknown fixture(s): {sorted(unknown)}")
    OUT.mkdir(parents=True, exist_ok=True)
    for name in args.names or SOURCES:
        fixture = build(name, args.raw_dir)
        out = OUT / name
        out.write_text(json.dumps(fixture, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8", newline="\n")
        print(f"[ok] {name}: {out.stat().st_size:,} bytes <- {SOURCES[name][0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

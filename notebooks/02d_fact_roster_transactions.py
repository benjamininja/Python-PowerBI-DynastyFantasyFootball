# %% [markdown]
# # 02d_fact_roster_transactions  (startup-draft ledger parse)
#
# **Purpose:** Transform-step for the event-sourced acquisition ledger
# (ADR-0003/0004). Reads the captured `getDraftResults` (04w) and emits three
# tables in one pass:
#
# - **`dim_roster_asset`** — polymorphic asset bridge. One row per real-world
#   asset; `asset_id` is a **monotonic int sequence assigned at first sight and
#   persisted** (never re-derived — ADR-0004). Minted on the Fantrax `scorer_id`
#   (the player's stable natural key), so the surrogate survives a prospect
#   signing (`player_key` → `gsis_id` fills underneath the same `asset_id`).
# - **`fact_draft_pick`** — the 2026 startup pick grid (every slot, made or not).
#   Keyed on the slot: `pick_ref = (draft_season, divisionId, overall_slot)`.
#   Records `current_owner` (getDraftResults `teamId`, post-trade) and
#   `original_owner`, inferred from round 1's own slot assignment expanded via
#   the snake rule (Fantrax's API carries no pre-trade allocation field at all —
#   see the fact_draft_pick cell below). `draft_type` ("Startup"/"Rookie") is
#   derived per-batch from the max round count. `overall_slot` = snake order
#   `(round-1)*N + pick_in_round`.
# - **`fact_roster_transactions`** — one `startup_draft` row per **made** pick.
#   Key `season_id + event_type + team_key + asset_id + event_seq`. Each pick's
#   contract is sourced, not assumed (ADR-0019 -- see "Contract sourcing"
#   below): `Minor` for a minors-eligible player, else `1st`. `contract_value` =
#   the salary Fantrax charges the pick -- read off the roster snapshot, else
#   the salary pool at draft time (see "Salary sourcing" below); `cap_hit` =
#   that contract's `dim_contract.cap_hit_pct` × value.
#   PLUS the free-agency/trade events parsed from 04t's captured transaction
#   history — `trade_away` (TERMINAL) + `trade` for a traded player, and
#   `claim` / `drop` (TERMINAL) for FA churn. All four share one chronological
#   `event_seq` and resolve contract terms by walking the stream forward — see
#   that section below.
# - **`fact_trade_log.parquet`** — one row per traded ASSET (players AND draft
#   picks), grouped by `transaction_id` (Fantrax's `txSetId`) so a multi-asset
#   trade's legs stay linked. Deliberately kept OUT of the polymorphic
#   `dim_roster_asset`/`fact_roster_transactions` system: pick assets have no
#   stable identity yet (current-season pick rows go up to round 35 with no
#   asset_id minted for them), and a
#   `dim_roster_asset` row with `asset_id=NA` would corrupt 02e's
#   `drop_duplicates(["team_key","asset_id"])` replay (collapses every such
#   row per team into one bogus roster line). This is the source for
#   `profiles.infer_trade_activity(team_key)` (count of distinct
#   `transaction_id` involving that team) — no asset-identity resolution
#   needed for that signal, since `team_key_from`/`team_key_to` come straight
#   off Fantrax's own `cells` (`from`/`to` teamId), not parsed text.
#
# **Why a script (like 04w/05a, not a notebook):** re-run during the live draft
# (after each 04w capture) to refresh the ledger → feeds the 05a availability
# join. Idempotent: replace-by-`(season_id, event_type)` for the fact and
# `draft_season` for the pick grid; the asset sequence only ever grows.
#
# **Identity joins:** team `teamId → team_key` via `dim_fantasy_teams.fantrax_team_id`
# (01c, the league Sheet's authoritative `Fantrax-TeamId` column — ADR-0005);
# player `scorerId → gsis_id/player_key` via `dim_fantrax_crosswalk` (04z);
# `salary` via `fact_roster_placement` (04v), else the draft-time
# `fact_fantrax_adp` capture (04a); contract via `fact_roster_placement` +
# `fact_minor_eligibility` (04v).
#
# **Run:**  python notebooks/02d_fact_roster_transactions.py
#
# **Layout:** everything at module level is a constant or a function; the run
# itself is `main()`, behind the `__main__` guard. The parsers take their
# lookups as arguments, so `tests/` can import this module and feed them
# fixtures without touching `data/`.

# %%
import sys
import json
import glob
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import NamedTuple

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
import etl_helpers as etl
from etl_helpers import CFG, DATA, TODAY, load_replace_partition

SEASON_ID   = f"{CFG.draft_year}-{CFG.draft_year + 1}"   # "2026-2027"
EVENT_TYPE  = "startup_draft"
STATUS      = "active"
SOURCE      = "getDraftResults"

FACT_PATH        = DATA / "fact_roster_transactions.parquet"
ASSET_PATH       = DATA / "dim_roster_asset.parquet"
PICK_PATH        = DATA / "fact_draft_pick.parquet"
PLACEMENT_PATH   = DATA / "fact_roster_placement.parquet"
ELIGIBILITY_PATH = DATA / "fact_minor_eligibility.parquet"
TRADE_LOG_PATH = DATA / "fact_trade_log.parquet"
DRAFT_GLOB     = str(DATA / "raw" / "fantrax_draftresults_2026*.json")
TXN_GLOB       = str(DATA / "raw" / "fantrax_txn_history_*.json")

ASSET_COLS  = ["asset_id", "asset_type", "scorer_id", "gsis_id", "player_key", "pick_ref"]
LEDGER_KEY  = ["season_id", "event_type", "team_key", "asset_id", "event_seq"]
LEDGER_COLS = ["season_id", "event_type", "team_key", "asset_id", "event_seq", "event_date",
               "contract_id", "contract_year", "contract_value", "cap_hit", "dead_money",
               "status", "scorer_id", "gsis_id", "draft_round", "pick_in_round",
               "pick_overall", "source"]

TRADE_SOURCE   = "getTransactionDetailsHistory"
TXN_SEQ_BASE   = 100_000
TRADE_AWAY     = "trade_away"
TRADE_IN       = "trade"
CLAIM_EVENT    = "claim"
DROP_EVENT     = "drop"
TXN_EVENT_TYPES = (TRADE_AWAY, TRADE_IN, CLAIM_EVENT, DROP_EVENT)

MINOR_CONTRACT_ID = "Minor"   # the stage before 1st, held while minors-eligible
DRAFT_CONTRACT_ID = "1st"     # a drafted player who is not minors-eligible
FA_CONTRACT_ID    = "FA"      # a claim with no contract history this season
PRESEASON_WEEK    = "PRE"     # fact_roster_placement.week of a preseason capture
STALE_ELIGIBILITY_DAYS = 8    # 04v runs weekly; a move further past its newest capture is warned on

# Which fact_minor_eligibility capture says a player was eligible (eligible_at).
ELIGIBLE_NEXT, ELIGIBLE_PREVIOUS, ELIGIBLE_NEWEST = "next", "previous", "newest"

# Where a draft pick's salary was read (build_startup_rows), firmest first.
SALARY_SNAPSHOT   = "roster snapshot"
SALARY_AT_PICK    = "ADP on or before the pick"
SALARY_AFTER_PICK = "ADP after the pick"
SALARY_LATEST     = "latest ADP of any season"
SALARY_MISSING    = "none"

# Same-timestamp tiebreak: a drop frees the roster spot the paired claim
# fills, and a trade_away precedes the claim of anyone it displaced.
_KIND_ORDER = {DROP_EVENT: 0, TRADE_IN: 1, CLAIM_EVENT: 2}
_TERM_COLS  = ["contract_id", "contract_year", "contract_value", "cap_hit", "status"]

_HTML_TAG   = re.compile(r"<[^>]+>")
_PICK_OWNER = re.compile(r"\((.*)\)\s*$")


# %%
# ---- Draft results: load + parse -------------------------------------------
def load_draft() -> list[dict]:
    """Every captured `getDraftResults` payload, oldest capture first.

    Globs every `fantrax_draftresults_2026*.json` — covers the legacy no-suffix
    file AND the per-division files 04w now writes."""
    files = sorted(glob.glob(DRAFT_GLOB), key=lambda f: Path(f).stat().st_mtime)
    if not files:
        raise FileNotFoundError("No draft-results capture found -- run 04w first.")
    print(f"[info] division files (oldest first): {[Path(f).name for f in files]}")
    return [json.loads(Path(f).read_text(encoding="utf-8")) for f in files]


def parse_draft_results(payloads: list[dict]) -> pd.DataFrame:
    """`getDraftResults` payloads (oldest first) -> one row per pick slot.

    Picks are deduped on `(divisionId, round, pickNumber)` keeping the latest
    capture, so the old and new Riddell files don't double-count."""
    pick_rows = []
    for payload in payloads:
        pick_rows.extend(payload["responses"][0]["data"]["draftPicksOrdered"])

    picks = pd.DataFrame(pick_rows)
    picks = picks.drop_duplicates(
        subset=["divisionId", "round", "pickNumber"], keep="last").reset_index(drop=True)
    # canonical snake order: pickNumber already encodes within-round snake order,
    # so overall_slot is linear in (round, pickNumber). N = teams per division.
    n_by_div = picks.groupby("divisionId")["pickNumber"].transform("max")
    picks["overall_slot"] = (picks["round"] - 1) * n_by_div + picks["pickNumber"]
    return picks


# %%
# ---- dim_roster_asset: persist + mint (monotonic, never re-derived) --------
def _atype(g, p):
    if pd.notna(g):  return "player"      # signed NFL player (gsis_id resolved)
    if pd.notna(p):  return "prospect"    # unsigned prospect (player_key only)
    return "player"                        # default; resolvers backfill later


def mint_assets(scorer_ids, existing, gsis_lut, pkey_lut):
    """Extend the asset bridge to cover `scorer_ids`. `existing` is the bridge
    as persisted (empty frame on the first run). Returns (bridge, sid2aid)."""
    rows = {r["asset_id"]: dict(r) for r in existing.to_dict("records")}
    sid2aid = {r["scorer_id"]: r["asset_id"] for r in rows.values() if pd.notna(r.get("scorer_id"))}
    next_id = (int(existing["asset_id"].max()) + 1) if len(existing) else 1

    for sid in scorer_ids:
        g, p = gsis_lut.get(sid), pkey_lut.get(sid)
        if sid in sid2aid:                              # known asset → refresh resolvers only
            r = rows[sid2aid[sid]]
            r["gsis_id"], r["player_key"], r["asset_type"] = g, p, _atype(g, p)
        else:                                           # first sight → mint a new asset_id
            rows[next_id] = dict(asset_id=next_id, asset_type=_atype(g, p),
                                 scorer_id=sid, gsis_id=g, player_key=p, pick_ref=pd.NA)
            sid2aid[sid] = next_id; next_id += 1

    df = pd.DataFrame(rows.values())[ASSET_COLS].sort_values("asset_id").reset_index(drop=True)
    return df, sid2aid


def _read_assets():
    return pd.read_parquet(ASSET_PATH) if ASSET_PATH.exists() else pd.DataFrame(columns=ASSET_COLS)


# %%
# ---- fact_draft_pick: 2026 startup grid (all slots) -------------------------
def build_draft_picks(picks: pd.DataFrame, team_lut: dict, season_id: str = SEASON_ID) -> pd.DataFrame:
    """Parsed pick slots -> the `fact_draft_pick` grid for one draft season.

    getDraftResults gives each slot's CURRENT owner (who picks there now).
    Startup picks WERE traded (some teams hold 2 picks in a round, others 0), so
    the current owner != original owner for traded slots. Fantrax's API carries
    no pre-trade allocation field at all (confirmed by direct inspection -- no
    `originalTeamId`/`tradedFrom` anywhere in getDraftResults/
    getFantasyLeagueInfo/getRefObject) -- so `original_owner` is INFERRED from
    the draft's own round 1: round-1 slot assignment defines the draft order by
    construction, and a snake expansion of that order reconstructs every later
    round's pre-trade owner. The unique slot identity is
    (draft_season, divisionId, overall_slot)."""
    dp = picks.copy()
    dp["draft_season"]  = season_id
    dp["current_owner"] = dp["teamId"].map(team_lut)
    dp["is_made"]       = dp["scorerId"].notna()
    dp["pick_ref"]      = (dp["draft_season"] + "|" + dp["divisionId"]
                           + "|S" + dp["overall_slot"].astype(int).map("{:03d}".format))
    dp = dp.rename(columns={"pickNumber": "pick_in_round"})
    dp["draft_type"] = etl.classify_draft_type(dp["round"])

    round1_order = dp.loc[dp["round"] == 1, ["divisionId", "pick_in_round", "current_owner"]] \
        .rename(columns={"current_owner": "team_key"})
    snake_order = etl.expand_snake_draft_order(round1_order, int(dp["round"].max()))
    dp = dp.merge(snake_order.rename(columns={"team_key": "original_owner"}),
                  on=["divisionId", "round", "pick_in_round"], how="left")
    dp.loc[dp["round"] == 1, "original_owner"] = dp.loc[dp["round"] == 1, "current_owner"]

    grid = dp[
        ["pick_ref", "draft_season", "divisionId", "round", "pick_in_round",
         "overall_slot", "current_owner", "original_owner", "is_made", "draft_type"]
    ].sort_values(["divisionId", "overall_slot"]).reset_index(drop=True)
    assert not grid.duplicated(["draft_season", "divisionId", "overall_slot"]).any()
    assert grid["pick_ref"].is_unique
    assert grid["original_owner"].notna().all(), "original_owner inference left gaps"
    return grid


# %%
# ---- Contract sourcing (ADR-0019 decision 6) --------------------------------
# A Roster Move's contract is OBSERVED, never derived. Every ledger row asks,
# in order:
#   1. Roster State -- the latest in-season snapshot that shows this copy on
#      the move's team (the "from" team for a trade), captured inside the
#      copy's current stint on that team and before the move day:
#          stint start  <=  capture day  <  move day
#      What Fantrax showed wins.
#   2. Only when no snapshot covers the move, a default: `Minor` for a
#      minors-eligible player; else the contract the copy already held; else
#      `1st` for a draft pick and `FA` for a claim or drop with no history.
#
# Why both bounds on the capture day:
# - Before the move day. 04v stamps a snapshot with the day it RAN and replaces
#   that week's rows on a re-run, so a capture dated the move day may have been
#   taken after the move. Reading it would make the label depend on run timing.
# - From the stint start on. A copy dropped and claimed back starts a new stint,
#   and a snapshot from the old one can show a contract the player has since
#   left (a `Minor` on a graduate).
# A draft pick and a claim START a stint, so no snapshot covers either and both
# take the default. A copy with no stint on record (the ledger never saw it
# join the team) reads any snapshot before the move day.
#
# The preseason (`PRE`) snapshot is NOT read for a contract. Fantrax moved the
# eligible players to `Minor` after it was taken, so it shows `1st` on players
# who were `Minor` by week 1; reading it would stamp `1st` on an eligible
# player moved between that capture and the season start. (Its salaries ARE
# read -- see "Salary sourcing".)
#
# Today the snapshot is 04v's fact_roster_placement, keyed by capture date;
# #117 re-points step 1 at fact_roster_state, keyed by Scoring Period, and
# settles how a claim reads its own period.
class ContractSource(NamedTuple):
    snaps: dict    # (team_key, scorer_id) -> [(capture day, contract)], oldest first
    elig: list     # [(capture day, {minors-eligible scorer_ids})], oldest first
    years: dict    # contract_id -> dim_contract.contract_year
    pcts: dict     # contract_id -> dim_contract.cap_hit_pct
    salaries: dict # (team_key, scorer_id) -> [(capture day, salary)], oldest first


class Sourced(NamedTuple):
    """One Roster Move's contract, and how it was reached. The last three
    flags only apply to a default; see eligible_at() for the middle two."""
    contract_id: object
    observed: bool = False        # read off a Roster State snapshot
    after_newest: bool = False    # eligible on the newest capture, taken before the move
    left_list: bool = False       # eligible before the move, off the next capture's list
    stale_capture: bool = False   # defaulted long after the newest eligibility capture


def _day(dt):
    """The calendar day of a datetime, or None when it is unknown."""
    return None if dt is None or pd.isna(dt) else pd.Timestamp(dt).normalize()


def index_snapshots(placement) -> dict:
    """In-season Roster State rows, indexed per copy. Left out: the preseason
    capture (see above), rows with no capture date, and rows with no contract
    -- 04v writes an empty cell as "", which is not an observation."""
    if placement is None or placement.empty:
        return {}
    contract = placement["contract"].fillna("").astype(str).str.strip()
    seen = placement[(placement["week"] != PRESEASON_WEEK) & (contract != "")
                     & placement["capture_date"].notna()]
    snaps = {}
    for r in seen.sort_values("capture_date").itertuples():
        snaps.setdefault((r.team_key, r.scorer_id), []).append(
            (_day(r.capture_date), r.contract))
    return snaps


def index_eligibility(eligibility) -> list:
    """fact_minor_eligibility -> one set of scorer_ids per capture day. A row
    in a capture means Fantrax held the player minors-eligible that day."""
    if eligibility is None or eligibility.empty:
        return []
    return [(_day(day), set(rows["scorer_id"]))
            for day, rows in eligibility.groupby("capture_date", sort=True)]


def contract_source(placement, eligibility, contracts) -> ContractSource:
    return ContractSource(
        snaps=index_snapshots(placement),
        elig=index_eligibility(eligibility),
        years=dict(zip(contracts["contract_id"], contracts["contract_year"])),
        pcts=dict(zip(contracts["contract_id"], contracts["cap_hit_pct"])),
        salaries=index_salaries(placement))


def snapshot_contract(snaps: dict, team_key, scorer_id, event_dt, since=None):
    """The contract on the latest in-season snapshot that shows this copy on
    this team, captured before the move day and no earlier than `since` -- the
    day the copy joined the team (None when the ledger never saw it join).
    None when no snapshot covers the move."""
    day, start = _day(event_dt), _day(since)
    if day is None:
        return None
    seen = [contract for captured, contract in snaps.get((team_key, scorer_id), ())
            if captured < day and (start is None or captured >= start)]
    return seen[-1] if seen else None


def eligible_at(elig: list, scorer_id, event_dt):
    """Was the player minors-eligible on the move day? Names the capture that
    says so, or None when neither neighbouring capture lists the player.

    - ELIGIBLE_NEXT: the first capture on or after the move day lists them.
      Games played only grow, so a player eligible on a later day was eligible
      on the move day too.
    - ELIGIBLE_PREVIOUS: that capture does not, but the last one before the
      move day does. They graduated somewhere in between, and no capture closer
      to the move says on which side of it, so the earlier list stands.
    - ELIGIBLE_NEWEST: the move postdates every capture and the newest one
      lists them. A move with no date reads the newest capture too."""
    if not elig:
        return None
    day = _day(event_dt)
    after = next((ids for captured, ids in elig if day is not None and captured >= day), None)
    if after is not None and scorer_id in after:
        return ELIGIBLE_NEXT
    before = next((ids for captured, ids in reversed(elig) if day is None or captured < day), ())
    if scorer_id not in before:
        return None
    return ELIGIBLE_NEWEST if after is None else ELIGIBLE_PREVIOUS


def stale_capture(elig: list, event_dt) -> bool:
    """Is the move more than STALE_ELIGIBILITY_DAYS past the newest eligibility
    capture? Its eligibility then rests on an old list."""
    day = _day(event_dt)
    return bool(elig) and day is not None and (day - elig[-1][0]).days > STALE_ELIGIBILITY_DAYS


def default_contract(eligible: bool, kind: str, inherited=None):
    """The contract when no Roster State row covers the move.

    - minors-eligible -> `Minor` (ADR-0019 decision 1);
    - else the contract the copy already held -- but an inherited `Minor` on a
      player who is no longer eligible is `1st`: they graduated (decision 3);
    - else `1st` for a draft pick, `FA` for a claim or drop with no history,
      and unknown (NA) for a trade with no source row."""
    if eligible:
        return MINOR_CONTRACT_ID
    if inherited is not None and pd.notna(inherited):
        return DRAFT_CONTRACT_ID if inherited == MINOR_CONTRACT_ID else inherited
    return {EVENT_TYPE: DRAFT_CONTRACT_ID, CLAIM_EVENT: FA_CONTRACT_ID,
            DROP_EVENT: FA_CONTRACT_ID}.get(kind, pd.NA)


def resolve_contract(src: ContractSource, kind, team_key, scorer_id, event_dt,
                     inherited=None, since=None) -> Sourced:
    """One Roster Move's contract: the snapshot when one covers the move, else
    the default. `since` is the day the copy joined `team_key`."""
    seen = snapshot_contract(src.snaps, team_key, scorer_id, event_dt, since)
    if seen is not None:
        return Sourced(seen, observed=True)
    basis = eligible_at(src.elig, scorer_id, event_dt)
    return Sourced(default_contract(basis is not None, kind, inherited),
                   after_newest=basis == ELIGIBLE_NEWEST,
                   left_list=basis == ELIGIBLE_PREVIOUS,
                   stale_capture=stale_capture(src.elig, event_dt))


def tally_sourcing(sourced: list) -> dict:
    """How many moves each `Sourced` flag is set on."""
    return {flag: sum(getattr(s, flag) for s in sourced) for flag in Sourced._fields[1:]}


def sourcing_report(elig: list, tallies: list) -> list:
    """The lines main() prints on how firm the `Minor` defaults are, summed
    over the draft and transaction tallies."""
    if not elig:
        return []
    n = {flag: sum(t[flag] for t in tallies) for flag in Sourced._fields[1:]}
    newest = elig[-1][0].date()
    lines = [f"[info] minors eligibility read off the capture before the move: "
             f"{n['after_newest']} move(s) made after the newest capture ({newest}); "
             f"{n['left_list']} by a player off the next capture's list (graduated in between)"]
    if n["stale_capture"]:
        lines.append(f"[warn] {n['stale_capture']} move(s) defaulted more than "
                     f"{STALE_ELIGIBILITY_DAYS} days after the newest eligibility capture "
                     f"({newest}) -- their contract rests on an old list (run 04v)")
    return lines


def contract_year_of(src: ContractSource, contract_id) -> float:
    """dim_contract's contract_year for a contract. NaN for `Minor` (it has no
    term) and for a contract dim_contract doesn't list."""
    year = src.years.get(contract_id) if pd.notna(contract_id) else None
    return float(year) if year is not None and pd.notna(year) else float("nan")


def unknown_contracts(frame: pd.DataFrame, contracts: pd.DataFrame) -> list:
    """Contracts written to the ledger that dim_contract doesn't list. Only a
    snapshot can produce one; it is written as observed and warned on."""
    return sorted(set(frame["contract_id"].dropna()) - set(contracts["contract_id"]))


# %%
# ---- Salary sourcing (#125) -------------------------------------------------
# A draft pick and a claim START a stint, so each sets the salary the copy
# carries. Both read it off Roster State: the FIRST snapshot that shows the
# copy on the move's team inside the stint the move starts:
#          move day  <  capture day  <  the day the copy next left the team
# - After the move day, for the reason a contract is read from before it: a
#   capture dated the move day may predate the move.
# - Before the copy next left (a trade away, a drop). A copy that comes back
#   starts a new stint, and that stint's salary belongs to the move that
#   started it.
# The first such snapshot, not the latest: it is the one closest to the move.
#
# Only when no snapshot qualifies, a default:
# - a draft pick: the fact_fantrax_adp salary of the draft's own season, on the
#   latest capture on or before the pick day, else the earliest one after it,
#   else the latest capture of any season. Fantrax re-prices the pool after the
#   draft and keeps charging a roster the draft-time salary, so the LATEST
#   capture is the wrong one to read first.
# - a claim: the salary it inherits this season in this Conference, else the
#   league minimum (see resolve_legs).
#
# The preseason snapshot IS read here. Its contracts predate Fantrax's `Minor`
# relabel, but its salaries match the in-season rosters row for row.
#
# A trade and a drop set no salary: they carry the copy's.
#
# #117 re-points this lookup at fact_roster_state with the contract lookup.
class DraftSalaries(NamedTuple):
    season: dict   # scorer_id -> [(capture day, salary)], the draft's season, oldest first
    latest: dict   # scorer_id -> salary on the latest capture of any season


def index_salaries(placement) -> dict:
    """Every Roster State row's salary, indexed per copy, the preseason capture
    included. Left out: rows with no capture date and rows with no salary."""
    if placement is None or placement.empty:
        return {}
    seen = placement[placement["capture_date"].notna() & placement["salary"].notna()]
    salaries = {}
    for r in seen.sort_values("capture_date").itertuples():
        salaries.setdefault((r.team_key, r.scorer_id), []).append(
            (_day(r.capture_date), float(r.salary)))
    return salaries


def snapshot_salary(salaries: dict, team_key, scorer_id, event_dt, until=None):
    """The salary on the first snapshot that shows this copy on this team
    inside the stint the move starts: captured after the move day and before
    `until`, the day the copy next left the team (None when it never did).
    None when no snapshot qualifies."""
    day, end = _day(event_dt), _day(until)
    if day is None:
        return None
    return next((salary for captured, salary in salaries.get((team_key, scorer_id), ())
                 if captured > day and (end is None or captured < end)), None)


def departures(legs: list) -> dict:
    """(team_key, scorer_id) -> when the copy left that team, oldest first: a
    trade away from it, or a drop by it. A leg with no date is left out."""
    left = {}
    for l in legs:
        team = {TRADE_IN: l["team_from"], DROP_EVENT: l["team_to"]}.get(l["kind"])
        if team is not None and pd.notna(team) and pd.notna(l["event_dt"]):
            left.setdefault((team, l["scorer_id"]), []).append(l["event_dt"])
    return {copy: sorted(times) for copy, times in left.items()}


def stint_end(departs: dict, team_key, scorer_id, joined=None):
    """When the copy next left the team after joining it at `joined`; None when
    it never did. A draft pick passes no `joined`: the ledger puts every
    transaction after the draft, so its stint ends at the copy's first
    departure. A departure stamped the same instant as the join belongs to the
    stint before (sort_legs puts it first)."""
    return next((left for left in departs.get((team_key, scorer_id), ())
                 if joined is None or left > joined), None)


def index_draft_salaries(adp: pd.DataFrame, season: int) -> DraftSalaries:
    """fact_fantrax_adp -> the salary lookups a draft pick falls back on. The
    season index holds only `season`'s captures, and no row without a salary
    or a capture date: another season's pool is priced differently."""
    by_day = adp.sort_values(["capture_date", "week"], kind="stable")
    priced = by_day[(by_day["season"] == season) & by_day["salary"].notna()
                    & by_day["capture_date"].notna()]
    in_season = {}
    for r in priced.itertuples():
        in_season.setdefault(r.scorer_id, []).append((_day(r.capture_date), float(r.salary)))
    latest = by_day.drop_duplicates("scorer_id", keep="last")
    return DraftSalaries(in_season, dict(zip(latest["scorer_id"], latest["salary"])))


def draft_time_salary(index: DraftSalaries, scorer_id, event_dt):
    """A draft pick's (salary, where it was read) when no snapshot prices it:
    the draft season's latest capture on or before the pick day, else its
    earliest capture after, else the latest capture of any season. A pick with
    no date reads the season's earliest capture."""
    day = _day(event_dt)
    seen = index.season.get(scorer_id, ())
    at_pick = [salary for captured, salary in seen if day is not None and captured <= day]
    if at_pick:
        return at_pick[-1], SALARY_AT_PICK
    if seen:
        return seen[0][1], SALARY_AFTER_PICK
    latest = index.latest.get(scorer_id)
    return (latest, SALARY_LATEST) if pd.notna(latest) else (pd.NA, SALARY_MISSING)


def repriced(terms: dict, salary: float) -> dict:
    """Contract terms at a new salary. `cap_hit` keeps the share of the salary
    it had: all of it on the league-minimum fallback, the draft row's share on
    inherited terms. Unknown when the old share is. (Nothing reads the ledger's
    `cap_hit`; #97 settles what it means.)"""
    old, hit = terms["contract_value"], terms["cap_hit"]
    if pd.notna(old) and old == salary:
        return terms
    share = hit / old if pd.notna(old) and pd.notna(hit) and old else pd.NA
    return {**terms, "contract_value": salary,
            "cap_hit": salary * share if pd.notna(share) else pd.NA}


# %%
# ---- fact_roster_transactions: one startup_draft row per made pick ---------
def _epoch_ms_to_date(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date() if pd.notna(ms) else pd.NaT


def build_startup_rows(made, team_lut, sid2aid, gsis_lut, draft_salaries, src, departs):
    """Made picks -> (the ledger's `startup_draft` rows, one per pick; the
    `tally_sourcing` of their contracts; how many salaries each source gave).

    `draft_salaries` is `index_draft_salaries()`; `departs` is `departures()`
    of the transaction legs, which end a drafted copy's stint."""
    fact_rows, sourced, priced = [], [], []
    for _, p in made.iterrows():
        sid = p["scorerId"]
        team_key   = team_lut[p["teamId"]]
        event_date = _epoch_ms_to_date(p["modifiedDate"])
        # Salary: the first snapshot inside the stint the pick starts, else the
        # pool at draft time (see "Salary sourcing").
        val, origin = snapshot_salary(src.salaries, team_key, sid, event_date,
                                      stint_end(departs, team_key, sid)), SALARY_SNAPSHOT
        if val is None:
            val, origin = draft_time_salary(draft_salaries, sid, event_date)
        val = float(val) if pd.notna(val) else pd.NA
        priced.append(origin)
        # The pick starts the copy's stint, so no snapshot covers it: the default.
        sourced.append(resolve_contract(src, EVENT_TYPE, team_key, sid, event_date,
                                        since=event_date))
        contract_id = sourced[-1].contract_id
        pct = src.pcts.get(contract_id)
        fact_rows.append({
            "season_id":      SEASON_ID,
            "event_type":     EVENT_TYPE,
            "team_key":       team_key,
            "asset_id":       sid2aid[sid],
            "event_seq":      int(p["overall_slot"]),
            "event_date":     event_date,
            "contract_id":    contract_id,
            "contract_year":  contract_year_of(src, contract_id),
            "contract_value": val,
            "cap_hit":        (val * pct) if pd.notna(val) and pct is not None else pd.NA,
            "dead_money":     0,
            "status":         STATUS,
            "scorer_id":      sid,
            "gsis_id":        gsis_lut.get(sid),
            "draft_round":    int(p["round"]),
            "pick_in_round":  int(p["pickNumber"]),
            "pick_overall":   int(p["overall_slot"]),
            "source":         SOURCE,
        })

    fact = pd.DataFrame(fact_rows)[LEDGER_COLS]
    fact["event_date"] = pd.to_datetime(fact["event_date"])
    # key integrity: the ADR grain must be unique.
    assert not fact.duplicated(LEDGER_KEY).any(), "duplicate ledger key — grain violated"
    return fact, tally_sourcing(sourced), {o: priced.count(o) for o in dict.fromkeys(priced)}


# %%
# ---- Transaction events from 04t capture (trade / claim / drop) ------------
# 04t captures BOTH views of Fantrax's transaction history into one file:
# `transactionCode` is null on a trade leg and "CLAIM"/"DROP" on free-agency
# churn. Player-asset legs of all three types feed fact_roster_transactions
# (dim_roster_asset's asset_id system + 02e's replay); pick assets (trade-only)
# have no stable identity yet and land in the separate fact_trade_log instead
# (see module docstring for why).
#
# "trade_away" and "drop" are TERMINAL in 02e (they remove the copy from the
# active roster); "trade" lands the asset on the new team and "claim" lands it
# on the claiming team.
#
# **One shared chronological event_seq** (TXN_SEQ_BASE + i, ordered by each
# row's real parsed datetime) across all three types: trades and FA churn
# interleave in real time, so per-type seq bases would let 02e's
# last-event-wins replay rank an older claim after a newer trade.
#
# **Contract terms are never invented.** A trade moves the copy's existing
# contract (it doesn't reset one to year 1). A CLAIM re-signs the player to
# whatever contract they last held THIS SEASON IN THIS CONFERENCE -- a released
# player "retains salary and contract for the season" -- and only a player with
# no such history gets dim_contract's league-minimum "FA" row. Conference
# scoping matters: this is a duplicate-player league (one copy per conference),
# so an unrelated copy on the other side must not donate its contract. A DROP
# carries the copy's last-known terms forward for auditing.
#
# Those inherited terms set the leg's salary -- except on a claim the roster
# snapshot shows at another one ("Salary sourcing" above). Its `contract_id`
# goes through "Contract sourcing": the snapshot wins, and the inherited
# contract is only the fallback for a player who is not minors-eligible.
def _strip_html(s: str) -> str:
    return _HTML_TAG.sub("", s or "").strip()


def rows_from_pages(pages: list[dict]) -> list[dict]:
    """One captured transaction-history file (a list of pages) -> its rows."""
    rows = []
    for pg in pages:
        rows.extend(pg["responses"][0]["data"]["table"]["rows"])
    return rows


def load_txn_rows() -> list[dict]:
    files = sorted(glob.glob(TXN_GLOB), key=lambda f: Path(f).stat().st_mtime)
    if not files:
        print("[info] no transaction-history capture found (run 04t) -- skipping txn events")
        return []
    rows = []
    for f in files:
        rows.extend(rows_from_pages(json.loads(Path(f).read_text(encoding="utf-8"))))
    return rows


def season_spans(season_dim: pd.DataFrame) -> list[tuple]:
    """dim_season -> [(fantasy start, fantasy end, season_id)]."""
    return [(pd.Timestamp(r.season_fantasy_start_date),
             pd.Timestamp(r.season_fantasy_end_date), r.season_id)
            for r in season_dim.itertuples()]


def _season_id_for(dt, spans):
    """Event datetime -> league season_id, read straight off dim_season's own
    fantasy-year span (2026-03-01..2027-02-28). Replaces an earlier month>=8
    heuristic that mis-filed the June/July startup-era trades under
    "2025-2026" -- a season that doesn't exist in dim_season at all."""
    if pd.isna(dt):
        return pd.NA
    d = pd.Timestamp(dt).normalize()
    for start, end, sid in spans:
        if start <= d <= end:
            return sid
    return pd.NA


def _parse_trades(trade_rows, team_lut, gsis_lut):
    """Trade rows -> (fact_trade_log rows, player-asset legs)."""
    last_date = {}   # date is only stamped on the first row of each txSetId
                     # group (HTML rowspan) -- carry it forward within the group.
    trade_log_rows, legs = [], []
    for r in trade_rows:
        txset = r["txSetId"]
        team_key_from = team_lut.get(next(c["teamId"] for c in r["cells"] if c["key"] == "from"))
        team_key_to   = team_lut.get(next(c["teamId"] for c in r["cells"] if c["key"] == "to"))
        date_cell = next((c["content"] for c in r["cells"] if c["key"] == "date"), None)
        if date_cell:
            last_date[txset] = date_cell
        event_dt = pd.to_datetime(last_date.get(txset), errors="coerce")
        week = next((c["content"] for c in r["cells"] if c["key"] == "week"), pd.NA)

        scorer = r.get("scorer") or {}
        sid = scorer.get("scorerId")
        if sid:
            asset_kind = "player"
            draft_round = pick_in_round = draft_year = pick_owner_hint = pd.NA
        else:
            asset_kind = "pick"
            sid = pd.NA
            dp = r.get("draftPickDisplayParts", {})
            round_m = re.search(r"Round\s*<b>(\d+)</b>", dp.get("roundInfo", ""))
            pick_m  = re.search(r"Pick\s*<b>(\d+)</b>", dp.get("roundInfo", ""))
            year_m  = re.search(r"<b>(\d{4})</b>", dp.get("year", ""))
            owner_m = _PICK_OWNER.search(_strip_html(dp.get("roundInfo", "")))
            draft_round   = int(round_m.group(1)) if round_m else pd.NA
            pick_in_round = int(pick_m.group(1)) if pick_m else pd.NA
            draft_year    = int(year_m.group(1)) if year_m else pd.NA
            pick_owner_hint = owner_m.group(1) if owner_m else pd.NA

        trade_log_rows.append({
            "transaction_id": txset,
            "asset_kind":     asset_kind,
            "team_key_from":  team_key_from,
            "team_key_to":    team_key_to,
            "event_date":     event_dt,
            "week":           week,
            "scorer_id":      sid,
            "gsis_id":        gsis_lut.get(sid) if asset_kind == "player" else pd.NA,
            "draft_round":    draft_round,
            "pick_in_round":  pick_in_round,
            "draft_year":     draft_year,
            "pick_owner_hint": pick_owner_hint,
            "source":         TRADE_SOURCE,
        })
        if asset_kind == "player" and pd.notna(team_key_from) and pd.notna(team_key_to):
            legs.append({"kind": TRADE_IN, "scorer_id": sid, "team_from": team_key_from,
                         "team_to": team_key_to, "event_dt": event_dt})
    return trade_log_rows, legs


def _parse_claim_drops(cd_rows, team_lut):
    """Claim/drop rows -> (legs, rows skipped for no scorer, for no team).

    Same HTML-rowspan shape as trades: only the FIRST row of a txSetId group
    carries the `team`/`date` cells, and a paired DROP inherits both from the
    CLAIM above it. Rows with no `scorer` block (or an unmapped team) can't be
    posted to an asset-keyed ledger, so they're counted and skipped."""
    last_cd_team, last_cd_date = {}, {}
    legs, n_no_player, n_no_team = [], 0, 0
    for r in cd_rows:
        txset = r["txSetId"]
        tcell = next((c for c in r["cells"] if c["key"] == "team"), None)
        if tcell and tcell.get("teamId"):
            last_cd_team[txset] = tcell["teamId"]
        dcell = next((c["content"] for c in r["cells"] if c["key"] == "date"), None)
        if dcell:
            last_cd_date[txset] = dcell

        sid = (r.get("scorer") or {}).get("scorerId")
        if not sid:
            n_no_player += 1
            continue
        team_key = team_lut.get(last_cd_team.get(txset))
        if not team_key:
            n_no_team += 1
            continue
        legs.append({
            "kind":      CLAIM_EVENT if r["transactionCode"] == "CLAIM" else DROP_EVENT,
            "scorer_id": sid,
            "team_from": pd.NA,
            "team_to":   team_key,
            "event_dt":  pd.to_datetime(last_cd_date.get(txset), errors="coerce"),
        })
    return legs, n_no_player, n_no_team


def parse_txn_rows(raw_rows, team_lut, gsis_lut):
    """Captured transaction-history rows -> (trade_log, legs, stats).

    - `trade_log`: one row per traded asset (players AND picks) for
      fact_trade_log, or None when the capture holds no trade.
    - `legs`: one dict per player-asset leg (`kind`, `scorer_id`, `team_from`,
      `team_to`, `event_dt`), trades first then claim/drops, in capture order.
    - `stats`: row counts (`trade_rows`, `claim_drop_rows`) and the claim/drop
      rows skipped (`no_player`, `no_team`)."""
    trade_rows = [r for r in raw_rows if r.get("transactionCode") is None]
    cd_rows    = [r for r in raw_rows if r.get("transactionCode") in ("CLAIM", "DROP")]

    trade_log, legs = None, []
    if trade_rows:
        trade_log_rows, legs = _parse_trades(trade_rows, team_lut, gsis_lut)
        trade_log = pd.DataFrame(trade_log_rows)
    cd_legs, n_no_player, n_no_team = _parse_claim_drops(cd_rows, team_lut)
    stats = {"trade_rows": len(trade_rows), "claim_drop_rows": len(cd_rows),
             "no_player": n_no_player, "no_team": n_no_team}
    return trade_log, legs + cd_legs, stats


# %%
# ---- Resolve every transaction leg chronologically -> ledger rows ----------
def fa_terms(contracts: pd.DataFrame) -> dict:
    """League-minimum FA fallback, straight off dim_contract's own "FA" row.
    cap_hit mirrors contract_value: dim_contract.cap_hit_pct prices a CUT
    (dead money), it is NOT a discount on a kept player's charge.

    A claim whose player was dropped BEFORE 04t's capture window (04t only
    starts 2026-07-19) has no ledger history, so it lands here even if the
    player carried a real contract. resolve_legs then re-prices it off the
    first roster snapshot that shows it on the claiming team ("Salary
    sourcing").

    Known gap: a claim that left the team again before any snapshot, or that
    postdates the newest one, keeps the league minimum. #117 builds
    fact_roster_state, a snapshot per Scoring Period, from Fantrax's
    `getTeamRosters?period=N` (#79, docs/research/inseason-schema-extraction.md),
    which closes most of it."""
    fa    = contracts.loc[contracts["contract_id"] == FA_CONTRACT_ID].iloc[0]
    value = float(fa["min_salary"])
    return dict(contract_id=FA_CONTRACT_ID, contract_year=1,
                contract_value=value, cap_hit=value, status="active")


def sort_legs(legs: list[dict]) -> list[dict]:
    """Chronological order, with the same-timestamp tiebreak in _KIND_ORDER."""
    return sorted(legs, key=lambda l: (pd.Timestamp.min if pd.isna(l["event_dt"]) else l["event_dt"],
                                       _KIND_ORDER[l["kind"]]))


def resolve_legs(legs, base, sid2aid, conf_lut, gsis_lut, spans, fa, src):
    """Transaction legs -> ledger rows, plus what main() reports on.

    `base` is the NON-transaction ledger (startup_draft rows); `fa` is
    `fa_terms()`; `src` is the ContractSource. Seed contract state from `base`,
    then walk the transaction stream forward, updating state as we go -- so a
    chained trade, or a drop-then-reclaim on the same day, resolves against
    what was actually true at that moment.

    Returns (rows, missing_source, fa_fallback, sourcing, snapshot_priced):
    traded players with no prior ledger row on their 'from' team, claims left
    at the league minimum (no in-season history, no snapshot), the
    `tally_sourcing` of the legs' contracts, and claims priced off a roster
    snapshot."""
    copy_terms, conf_terms = {}, {}      # (team_key, asset_id) / (conference, asset_id)
    stint_start = {}                     # (team_key, asset_id) -> when the copy joined
    departs = departures(legs)           # (team_key, scorer_id) -> when the copy left
    for r in base.sort_values("event_seq").itertuples():
        t = {c: getattr(r, c) for c in _TERM_COLS}
        copy_terms[(r.team_key, r.asset_id)] = t
        stint_start[(r.team_key, r.asset_id)] = r.event_date
        conf_terms[(conf_lut.get(r.team_key), r.asset_id)] = (t, r.season_id)

    rows, missing_source, fa_fallback, sourced, snapshot_priced = [], [], [], [], []
    for i, l in enumerate(sort_legs(legs)):
        aid, kind = sid2aid[l["scorer_id"]], l["kind"]
        team, season = l["team_to"], _season_id_for(l["event_dt"], spans)
        conf = conf_lut.get(team)
        prior = conf_terms.get((conf, aid))

        # 1. The terms the copy carries into this move (salary, status), and
        #    the start of its stint on the team a snapshot would show it on.
        #    A claim starts that stint itself.
        if kind == TRADE_IN:
            holder = l["team_from"]
            since = stint_start.get((holder, aid))
            inherited = copy_terms.get((holder, aid)) or (prior[0] if prior else None)
            if inherited is None:
                missing_source.append((holder, l["scorer_id"]))
                inherited = dict(contract_id=pd.NA, contract_year=pd.NA, contract_value=pd.NA,
                                 cap_hit=pd.NA, status="active")
        else:
            holder = team
            since = l["event_dt"] if kind == CLAIM_EVENT else stint_start.get((team, aid))
            # Only a contract held THIS season carries over ("retain salary and
            # contract for the season"); anything older resets to league minimum.
            inherited = prior[0] if (prior and prior[1] == season) else None
            if inherited is None and kind == DROP_EVENT:
                inherited = copy_terms.get((team, aid))
            no_history = inherited is None
            if no_history:
                inherited = fa
            # A claim starts a stint: the first snapshot inside it sets the
            # salary (see "Salary sourcing").
            if kind == CLAIM_EVENT:
                seen = snapshot_salary(src.salaries, team, l["scorer_id"], l["event_dt"],
                                       stint_end(departs, team, l["scorer_id"], l["event_dt"]))
                if seen is not None:
                    inherited = repriced(inherited, seen)
                    snapshot_priced.append(l["scorer_id"])
                elif no_history:
                    fa_fallback.append(l["scorer_id"])

        # 2. Its contract: the snapshot wins, else the default (see
        #    "Contract sourcing").
        sourced.append(resolve_contract(src, kind, holder, l["scorer_id"], l["event_dt"],
                                        inherited["contract_id"], since))
        contract_id = sourced[-1].contract_id
        terms = {**inherited, "contract_id": contract_id,
                 "contract_year": contract_year_of(src, contract_id)}

        seq = TXN_SEQ_BASE + i
        common = dict(season_id=season, **terms, dead_money=0, scorer_id=l["scorer_id"],
                      gsis_id=gsis_lut.get(l["scorer_id"]), draft_round=pd.NA,
                      pick_in_round=pd.NA, pick_overall=pd.NA, source=TRADE_SOURCE)
        if kind == TRADE_IN:
            rows.append({**common, "event_type": TRADE_AWAY, "team_key": l["team_from"],
                         "asset_id": aid, "event_seq": seq, "event_date": l["event_dt"]})
            rows.append({**common, "event_type": TRADE_IN, "team_key": team,
                         "asset_id": aid, "event_seq": seq, "event_date": l["event_dt"]})
            copy_terms.pop((l["team_from"], aid), None)
            stint_start.pop((l["team_from"], aid), None)
            copy_terms[(team, aid)] = terms
            stint_start[(team, aid)] = l["event_dt"]
        else:
            rows.append({**common, "event_type": kind, "team_key": team,
                         "asset_id": aid, "event_seq": seq, "event_date": l["event_dt"]})
            if kind == CLAIM_EVENT:
                copy_terms[(team, aid)] = terms
                stint_start[(team, aid)] = l["event_dt"]
            else:
                copy_terms.pop((team, aid), None)
                stint_start.pop((team, aid), None)
        conf_terms[(conf, aid)] = (terms, season)
    return rows, missing_source, fa_fallback, tally_sourcing(sourced), snapshot_priced


# %%
# ---- Run -------------------------------------------------------------------
def main():
    picks = parse_draft_results(load_draft())
    print(f"[info] {len(picks)} pick slots across {picks['divisionId'].nunique()} division(s); "
          f"{picks['scorerId'].notna().sum()} made")

    # ---- Identity + value lookups ------------------------------------------
    teams_dim = pd.read_parquet(DATA / "dim_fantasy_teams.parquet")
    team_lut = dict(zip(teams_dim["fantrax_team_id"], teams_dim["team_key"]))
    conf_lut = dict(zip(teams_dim["team_key"], teams_dim["conference"]))

    px = pd.read_parquet(DATA / "dim_fantrax_crosswalk.parquet")
    gsis_lut = dict(zip(px["scorer_id"], px["gsis_id"]))
    pkey_lut = dict(zip(px["scorer_id"], px["player_key"]))

    draft_salaries = index_draft_salaries(pd.read_parquet(DATA / "fact_fantrax_adp.parquet"),
                                          CFG.draft_year)

    contracts = pd.read_parquet(DATA / "dim_contract.parquet")
    spans = season_spans(pd.read_parquet(DATA / "dim_season.parquet"))

    # ---- Contract source: Roster State + minors eligibility (04v) ------------
    placement   = pd.read_parquet(PLACEMENT_PATH) if PLACEMENT_PATH.exists() else None
    eligibility = pd.read_parquet(ELIGIBILITY_PATH) if ELIGIBILITY_PATH.exists() else None
    src = contract_source(placement, eligibility, contracts)
    n_snapshots = len({day for seen in src.snaps.values() for day, _ in seen})
    n_salary_snapshots = len({day for seen in src.salaries.values() for day, _ in seen})
    print(f"[info] contract source: {n_snapshots} in-season roster snapshot(s), "
          f"{len(src.elig)} eligibility snapshot(s)")
    print(f"[info] salary source: {n_salary_snapshots} roster snapshot(s), preseason included")
    if not src.elig:
        print(f"[warn] no fact_minor_eligibility (run 04v) -- no move can default "
              f"to '{MINOR_CONTRACT_ID}'")

    # Every made pick must resolve to a team (captured divisions only) and a player.
    made = picks[picks["scorerId"].notna()].copy()
    unmapped_teams = sorted(set(made["teamId"]) - set(team_lut))
    if unmapped_teams:
        raise RuntimeError(
            f"teamIds absent from dim_fantasy_teams.fantrax_team_id (refresh 01c "
            f"from the Sheet's Fantrax-TeamId column): {unmapped_teams}")

    # ---- dim_roster_asset ---------------------------------------------------
    dim_roster_asset, sid2aid = mint_assets(sorted(made["scorerId"].unique()),
                                            _read_assets(), gsis_lut, pkey_lut)
    dim_roster_asset.to_parquet(ASSET_PATH, index=False)
    print(f"[ok] dim_roster_asset: {len(dim_roster_asset)} assets "
          f"({(dim_roster_asset['asset_type']=='player').sum()} player, "
          f"{(dim_roster_asset['asset_type']=='prospect').sum()} prospect) -> {ASSET_PATH.name}")

    # ---- fact_draft_pick ----------------------------------------------------
    dim_draft_pick = build_draft_picks(picks, team_lut)
    load_replace_partition(dim_draft_pick, PICK_PATH, part_cols=("draft_season",))
    print(f"[ok] fact_draft_pick: {len(dim_draft_pick)} slots ({SEASON_ID}, "
          f"{int(dim_draft_pick['is_made'].sum())} made) -> {PICK_PATH.name}")

    # ---- Transaction history: parsed here, posted further down ----------------
    # The parse is pure. The draft rows need it first: a trade away or a drop
    # ends a drafted copy's stint, which bounds the snapshot its salary is read
    # from.
    raw_txn_rows = load_txn_rows()
    trade_log, legs, stats = parse_txn_rows(raw_txn_rows, team_lut, gsis_lut)

    # ---- fact_roster_transactions: startup_draft rows ------------------------
    fact, draft_sourcing, draft_priced = build_startup_rows(
        made, team_lut, sid2aid, gsis_lut, draft_salaries, src, departures(legs))
    tallies = [draft_sourcing]
    total = load_replace_partition(fact, FACT_PATH, part_cols=("season_id", "event_type"))
    print(f"[ok] fact_roster_transactions: +{len(fact)} {EVENT_TYPE} rows "
          f"({total} total) -> {FACT_PATH.name}")
    print(f"[info] {EVENT_TYPE} contracts (all defaulted): "
          f"{fact['contract_id'].value_counts().to_dict()}")
    print(f"[info] {EVENT_TYPE} salaries read off: {draft_priced}")
    if draft_priced.get(SALARY_LATEST):
        print(f"[warn] {draft_priced[SALARY_LATEST]} pick(s) have no {CFG.draft_year} salary "
              f"capture -- priced off another season's pool")

    # ---- Asset bridge extension from roster placement ------------------------
    # Placement (04v) can carry roster copies the startup draft never saw — a
    # player added off free agency after the draft still shows up in a weekly
    # snapshot. Mint asset_ids for them so the bridge covers every scorer the
    # ledger might later reference (a trade/claim leg for an unminted scorer would
    # KeyError downstream).
    #
    # This block used to ALSO derive `minor_assignment`/`minor_graduation` events
    # from per-copy contract transitions. That was removed under ADR-0011. ADR-0019
    # has since made `Minor` a contract stage, but a stage change is still not a
    # ledger event: each Roster Move reads its contract off Roster State (see
    # "Contract sourcing"), and the Minors Roster Slot reaches the cap through
    # 02e's `roster_status` stamp.
    if placement is not None:
        dim_roster_asset, sid2aid = mint_assets(sorted(placement["scorer_id"].unique()),
                                                _read_assets(), gsis_lut, pkey_lut)
        dim_roster_asset.to_parquet(ASSET_PATH, index=False)
        print(f"[ok] asset bridge extended from placement: {len(dim_roster_asset)} assets "
              f"-> {ASSET_PATH.name}")
    else:
        print("[info] fact_roster_placement not built yet (run 04v) — asset bridge "
              "covers drafted copies only")

    # ---- Transaction events (trade / claim / drop) ---------------------------
    if raw_txn_rows:
        print(f"[info] captured txn rows: {stats['trade_rows']} trade leg(s), "
              f"{stats['claim_drop_rows']} claim/drop row(s)")

    if trade_log is not None:
        n_unmapped = int((trade_log["team_key_from"].isna() | trade_log["team_key_to"].isna()).sum())
        if n_unmapped:
            print(f"[warn] {n_unmapped} trade_log row(s) have an unmapped team "
                  f"(fantrax_team_id missing from dim_fantasy_teams) -- left NA")
        trade_log.to_parquet(TRADE_LOG_PATH, index=False)
        print(f"[ok] fact_trade_log: {len(trade_log)} asset row(s) across "
              f"{trade_log['transaction_id'].nunique()} trade(s) -> {TRADE_LOG_PATH.name}")

    if stats["no_player"] or stats["no_team"]:
        print(f"[warn] skipped {stats['no_player']} claim/drop row(s) with no scorer and "
              f"{stats['no_team']} with an unmapped team")

    if legs:
        dim_roster_asset, sid2aid = mint_assets(sorted({l["scorer_id"] for l in legs}),
                                                _read_assets(), gsis_lut, pkey_lut)
        dim_roster_asset.to_parquet(ASSET_PATH, index=False)

        fa   = fa_terms(contracts)
        base = pd.read_parquet(FACT_PATH)
        base = base[~base["event_type"].isin(TXN_EVENT_TYPES)]
        txn_fact_rows, missing_source, fa_fallback, txn_sourcing, snapshot_priced = resolve_legs(
            legs, base, sid2aid, conf_lut, gsis_lut, spans, fa, src)
        tallies.append(txn_sourcing)

        if missing_source:
            print(f"[warn] {len(missing_source)} traded player(s) had no prior ledger row on "
                  f"their 'from' team -- contract fields left NA for those legs: "
                  f"{missing_source[:5]}{'...' if len(missing_source) > 5 else ''}")
        if snapshot_priced:
            print(f"[info] {len(snapshot_priced)} claim(s) priced off the roster snapshot")
        if fa_fallback:
            print(f"[info] {len(fa_fallback)} claim(s) had no in-season contract history and "
                  f"no snapshot -- priced at the league minimum (${fa['contract_value']:,.0f})")

        txn_fact = pd.DataFrame(txn_fact_rows)[LEDGER_COLS]
        txn_fact["event_date"] = pd.to_datetime(txn_fact["event_date"])
        assert txn_fact["season_id"].notna().all(), "event_date outside every dim_season span"
        assert not txn_fact.duplicated(LEDGER_KEY).any(), "duplicate transaction-event ledger key"

        # Replace by EVENT_TYPE, not (season_id, event_type): these types are rebuilt
        # in full from the 04t capture on every run, so a corrected season_id would
        # otherwise strand the previous run's partition behind as orphan rows.
        _led    = pd.read_parquet(FACT_PATH)
        _stale  = int(_led["event_type"].isin(TXN_EVENT_TYPES).sum())
        out     = pd.concat([_led[~_led["event_type"].isin(TXN_EVENT_TYPES)], txn_fact],
                            ignore_index=True)
        out.to_parquet(FACT_PATH, index=False)
        by_type = txn_fact["event_type"].value_counts().to_dict()
        print(f"[ok] transaction events: +{len(txn_fact)} {by_type} "
              f"(replaced {_stale} prior txn row(s); {len(out)} total ledger rows)")
        print(f"[info] transaction contracts: "
              f"{txn_fact['contract_id'].value_counts(dropna=False).to_dict()} "
              f"({txn_sourcing['observed']} leg(s) read off a snapshot)")
        unknown = unknown_contracts(pd.concat([fact, txn_fact]), contracts)
        if unknown:
            print(f"[warn] contract(s) observed on a snapshot but absent from dim_contract "
                  f"(written as observed; add a row in 01b): {unknown}")
    elif raw_txn_rows:
        print("[info] no player-asset transaction legs to add (pick-only trades, or all unmapped)")
    else:
        print("[info] no captured transaction history -- skipping transaction events entirely")

    # ---- Minors eligibility: how firm the defaults are -----------------------
    for line in sourcing_report(src.elig, tallies):
        print(line)

    # ---- Summary -------------------------------------------------------------
    print("\n=== ledger summary ===")
    print(f"made picks: {len(fact)}  |  missing salary: {int(fact['contract_value'].isna().sum())}")
    by_team = (fact.groupby("team_key")
               .agg(picks=("asset_id", "size"), cap_committed=("cap_hit", "sum"))
               .sort_values("team_key"))
    print(by_team.to_string())
    print("\nsample rows:")
    show = ["team_key", "draft_round", "pick_in_round", "pick_overall", "scorer_id",
            "asset_id", "contract_value", "cap_hit", "event_date"]
    print(fact.sort_values("pick_overall").head(8)[show].to_string(index=False))


if __name__ == "__main__":
    main()

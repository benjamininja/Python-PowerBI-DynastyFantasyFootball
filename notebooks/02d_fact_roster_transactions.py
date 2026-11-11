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
#   Keyed on the slot: `pick_ref = (draft_season, division_id, overall_slot)`.
#   Records `current_owner` (getDraftResults `teamId`, post-trade) and
#   `original_owner`, inferred from round 1's own slot assignment expanded via
#   the snake rule (Fantrax's API carries no pre-trade allocation field at all —
#   see the fact_draft_pick cell below). `draft_type` ("Startup"/"Rookie") is
#   derived per-batch from the max round count. `overall_slot` = snake order
#   `(round-1)*N + pick_in_round`.
# - **`fact_roster_transactions`** — one `startup_draft` row per **made** pick.
#   Key `transaction_id + scorer_id + team_key + event_type` (ADR-0016
#   decision 6). `transaction_id` is the pick's `pick_ref` on a draft row and
#   Fantrax's `txSetId` on a move, so a rebuild never renumbers a row.
#   `event_seq` is sort order only. Each pick's
#   contract is sourced, not assumed (ADR-0019 -- see "Contract sourcing"
#   below): the contract Roster State shows, else `Minor` for a minors-eligible
#   player, else the contract the preseason capture shows, else `1st`.
#   `contract_source` says which. `contract_value` = the salary Fantrax charges the pick
#   -- read off the preseason capture or Roster State, else the salary pool at
#   draft time (see "Salary sourcing" below).
#   PLUS the free-agency/trade events parsed from 04t's captured transaction
#   history — `trade_away` (TERMINAL) + `trade` for a traded player, and
#   `claim` / `drop` (TERMINAL) for FA churn. All four share one chronological
#   `event_seq` and resolve contract terms by walking the stream forward — see
#   that section below. Every row carries `period`, the Scoring Period the
#   move takes effect in (null on a move of another season). A claim also
#   carries `claim_method` (`waiver` / `free_agent`) and `claim_bid`, read off
#   its `bid` cell; a drop made with a claim takes that claim's method ("Claim
#   method" below).
# - **`fact_trade_log.parquet`** — one row per traded ASSET (players AND draft
#   picks), keyed `(transaction_id, asset_id)` (ADR-0018 decision 5, #109).
#   `transaction_id` is Fantrax's `txSetId`, so a multi-asset trade's legs stay
#   linked. Every leg carries the `asset_id` of a `dim_roster_asset` row: a
#   player leg its scorer's, a pick leg the asset of the pick it resolves to
#   ("Pick legs" below). A pick leg that resolves to no pick is written to
#   `data/review/review_trade_log_picks.csv` and left out of the table. Pick
#   legs stay out of `fact_roster_transactions`, so 02e's replay never sees a
#   pick. `profiles.infer_trade_activity(team_key)` counts the distinct
#   `transaction_id` a team is party to.
# - **`dim_roster_asset.parquet`** also holds one `pick` asset for every row of
#   `fact_draft_pick` and `fact_draft_pick_future` (ADR-0006 decision 2), with
#   `pick_ref` set and no `scorer_id`.
#
# **Why a script (like 04w/05a, not a notebook):** re-run during the live draft
# (after each 04w capture) to refresh the ledger → feeds the 05a availability
# join. Idempotent: replace-by-`(season_id, event_type)` for the fact and
# `draft_season` for the pick grid; the asset sequence only ever grows.
#
# **Identity joins:** team `teamId → team_key` via `dim_fantasy_teams.fantrax_team_id`
# (01c, the league Sheet's authoritative `Fantrax-TeamId` column — ADR-0005);
# player `scorerId → gsis_id/player_key` via `dim_fantrax_crosswalk` (04z);
# `salary` via `fact_preseason_salary` and `fact_roster_state` (04r), else the
# draft-time `fact_fantrax_adp` capture (04a); contract via `fact_roster_state`,
# `fact_preseason_salary` and `fact_minor_eligibility` (04v).
#
# **Run:**  python notebooks/02d_fact_roster_transactions.py
#
# **Layout:** everything at module level is a constant or a function; the run
# itself is `main()`, behind the `__main__` guard. The parsers take their
# lookups as arguments, so `tests/` can import this module and feed them
# fixtures without touching `data/`.

# %%
import sys
import argparse
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
from etl_helpers import CFG, DATA, REVIEW, TODAY, write_table

SEASON_ID   = f"{CFG.draft_year}-{CFG.draft_year + 1}"   # "2026-2027"
EVENT_TYPE  = "startup_draft"
STATUS      = "active"
SOURCE      = "getDraftResults"

FACT_PATH        = DATA / "fact_roster_transactions.parquet"
ASSET_PATH       = DATA / "dim_roster_asset.parquet"
PICK_PATH        = DATA / "fact_draft_pick.parquet"
TRADE_LOG_PATH = DATA / "fact_trade_log.parquet"
PICK_REVIEW_PATH = REVIEW / "review_trade_log_picks.csv"
PICK_OWNER_REVIEW_PATH = REVIEW / "review_pick_ownership.csv"
DRAFT_GLOB     = str(DATA / "raw" / "fantrax_draftresults_2026*.json")
TXN_GLOB       = str(DATA / "raw" / "fantrax_txn_history_*.json")


def use_raw_dir(raw_dir) -> None:
    """Point both raw globs at `raw_dir`, read in place (a worktree has no data/raw)."""
    global DRAFT_GLOB, TXN_GLOB
    folder = Path(raw_dir)
    DRAFT_GLOB = str(folder / Path(DRAFT_GLOB).name)
    TXN_GLOB   = str(folder / Path(TXN_GLOB).name)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Build the roster-transaction ledger.")
    parser.add_argument("--raw-dir", type=Path, default=None,
                        help="folder holding the raw captures (default: data/raw)")
    return parser.parse_args(argv)

ASSET_COLS  = ["asset_id", "asset_type", "scorer_id", "gsis_id", "player_key", "pick_ref"]
# The ledger's grain (ADR-0016 decision 6). `transaction_id` is the pick's
# `pick_ref` on a draft row and Fantrax's `txSetId` on a move: neither changes
# when the ledger is rebuilt. `event_seq` is sort order only -- it renumbers
# whenever a capture adds or drops a move.
LEDGER_KEY  = ["transaction_id", "scorer_id", "team_key", "event_type"]
LEDGER_COLS = ["transaction_id", "season_id", "event_type", "team_key", "asset_id",
               "event_seq", "event_date", "period",
               "contract_id", "contract_year", "contract_value", "contract_source",
               "status", "scorer_id", "gsis_id", "draft_round", "pick_in_round",
               "pick_overall", "source", "claim_method", "claim_bid"]

# fact_trade_log, keyed (transaction_id, asset_id). The parsed
# `pick_owner_hint` (a team name off Fantrax's text) is read while the pick
# legs are resolved and is not written: `pick_ref` names the pick.
TRADE_LOG_COLS = ["transaction_id", "asset_id", "asset_kind", "team_key_from", "team_key_to",
                  "event_date", "week", "scorer_id", "gsis_id", "pick_ref",
                  "draft_year", "draft_round", "pick_in_round", "source"]
PICK_REVIEW_COLS = ["transaction_id", "event_date", "team_key_from", "team_key_to",
                    "draft_year", "draft_round", "pick_in_round", "reason"]
PICK_OWNER_REVIEW_COLS = ["pick_ref", "replayed_owner", "reported_owner"]

TRADE_SOURCE   = "getTransactionDetailsHistory"
TXN_SEQ_BASE   = 100_000
TRADE_AWAY     = "trade_away"
TRADE_IN       = "trade"
CLAIM_EVENT    = "claim"
DROP_EVENT     = "drop"
TXN_EVENT_TYPES = (TRADE_AWAY, TRADE_IN, CLAIM_EVENT, DROP_EVENT)

# How a claim was made (the ledger's `claim_method`), read off its `bid` cell.
CLAIM_WAIVER     = "waiver"       # the claim carried a bid, 0.00 included
CLAIM_FREE_AGENT = "free_agent"   # the bid cell was empty

MINOR_CONTRACT_ID = "Minor"   # the stage before 1st, held while minors-eligible
DRAFT_CONTRACT_ID = "1st"     # a drafted player who is not minors-eligible
FA_CONTRACT_ID    = "FA"      # a claim with no contract history this season
DRAFT_PERIOD      = 1         # the Scoring Period a startup pick takes effect in
STALE_ELIGIBILITY_DAYS = 8    # 04v runs weekly; a move further past its newest capture is warned on

# Which fact_minor_eligibility capture says a player was eligible (eligible_at).
ELIGIBLE_NEXT, ELIGIBLE_PREVIOUS, ELIGIBLE_NEWEST = "next", "previous", "newest"

# Where a row's contract was read (the ledger's `contract_source`).
FROM_STATE     = "roster_state"   # a Roster State row
FROM_PRESEASON = "preseason"      # the preseason capture, inside the stint
FROM_DEFAULT   = "default"        # neither: the default rule
NO_STINT       = "no_stint"       # a drop by a team the ledger never saw the copy join

# Where a draft pick's salary was read (build_startup_rows), firmest first.
SALARY_PRESEASON  = "preseason capture"
SALARY_STATE      = "Roster State"
SALARY_AT_PICK    = "ADP on or before the pick"
SALARY_AFTER_PICK = "ADP after the pick"
SALARY_MINIMUM    = "league minimum (no salary capture)"

# Same-timestamp tiebreak: a drop frees the roster spot the paired claim
# fills, and a trade_away precedes the claim of anyone it displaced.
_KIND_ORDER = {DROP_EVENT: 0, TRADE_IN: 1, CLAIM_EVENT: 2}
_TERM_COLS  = ["contract_id", "contract_year", "contract_value", "status",
               "contract_source"]

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
    return etl.read_table("dim_roster_asset") if etl.table_exists("dim_roster_asset") else pd.DataFrame(columns=ASSET_COLS)


# %%
# ---- fact_draft_pick: 2026 startup grid (all slots) -------------------------
def pick_refs(season_id: str, picks: pd.DataFrame) -> pd.Series:
    """Each slot's `pick_ref`: (draft_season, division_id, overall_slot) as one
    string. It keys the pick grid, and a made pick's ledger row carries it as
    its `transaction_id`. `picks` is the parsed payload, so the division is
    still under Fantrax's own key, `divisionId`."""
    return (season_id + "|" + picks["divisionId"]
            + "|S" + picks["overall_slot"].astype(int).map("{:03d}".format))


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
    (draft_season, division_id, overall_slot). The payload's `divisionId` is
    renamed `division_id` here, where the table's columns are made (ADR-0018
    decision 8)."""
    dp = picks.copy()
    dp["draft_season"]  = season_id
    dp["current_owner"] = dp["teamId"].map(team_lut)
    dp["is_made"]       = dp["scorerId"].notna()
    dp["pick_ref"]      = pick_refs(season_id, dp)
    dp = dp.rename(columns={"pickNumber": "pick_in_round", "divisionId": "division_id"})
    dp["draft_type"] = etl.classify_draft_type(dp["round"])

    round1_order = dp.loc[dp["round"] == 1, ["division_id", "pick_in_round", "current_owner"]] \
        .rename(columns={"current_owner": "team_key"})
    snake_order = etl.expand_snake_draft_order(round1_order, int(dp["round"].max()))
    dp = dp.merge(snake_order.rename(columns={"team_key": "original_owner"}),
                  on=["division_id", "round", "pick_in_round"], how="left")
    dp.loc[dp["round"] == 1, "original_owner"] = dp.loc[dp["round"] == 1, "current_owner"]

    grid = dp[
        ["pick_ref", "draft_season", "division_id", "round", "pick_in_round",
         "overall_slot", "current_owner", "original_owner", "is_made", "draft_type"]
    ].sort_values(["division_id", "overall_slot"]).reset_index(drop=True)
    assert not grid.duplicated(["draft_season", "division_id", "overall_slot"]).any()
    assert grid["pick_ref"].is_unique
    assert grid["original_owner"].notna().all(), "original_owner inference left gaps"
    return grid


# %%
# ---- Pick assets + trade-log pick legs (#109, ADR-0018 decision 5) ----------
# **Pick assets.** Every pick is an asset (ADR-0006 decision 2): one
# `dim_roster_asset` row of type `pick` per row of `fact_draft_pick` (slotted)
# and `fact_draft_pick_future` (unslotted), carrying that row's `pick_ref`.
# Like a player's, the id is minted at first sight and never re-derived. A
# pick is one asset for life: its identity is (draft year, round, Original
# Owner) (ADR-0006 decision 1), which is what a future pick's `pick_ref`
# spells (`2027|B10|1`). When the draft order is set and the pick turns up
# in `fact_draft_pick` under a slot `pick_ref`, its asset keeps its id and
# takes the new `pick_ref` (ADR-0004: the resolver moves under a stable id).
#
# **Pick legs.** Fantrax's trade row names a pick by year and round, plus the
# pick number once the draft order is set. It carries no id, so each leg is
# resolved to the pick it moved:
# - a leg WITH a pick number is a slot of `fact_draft_pick`: (draft year, the
#   sending team's division, round, pick number). The slot's `original_owner`
#   is its Original Owner.
# - a leg WITHOUT one is a future pick. Each team starts with its own pick of
#   every (year, round) in `fact_draft_pick_future`; the legs are replayed in
#   time order and a leg moves the one pick of that (year, round) its sender
#   holds. A sender holding several needs the row's owner hint (a team name)
#   to name one of them. A hint that names a pick the sender does not hold
#   leaves the leg unresolved: the replay has lost track of that pick. A pick
#   that has since been slotted is still replayed, under its slot `pick_ref`.
# An unresolved leg goes to review and stays out of the table. So does every
# leg of an asset that moves twice inside one trade: the table's key
# (transaction_id, asset_id) cannot hold both. The replay's end state is then
# held against the owner Fantrax reports (ADR-0006 decision 4):
# `ownership_gaps` lists the picks where the two disagree, which means a
# missed trade or a pick table older than the trade log (rerun 04u). They are
# written to `data/review/review_pick_ownership.csv`.
def mint_pick_assets(existing: pd.DataFrame, refs, was=None) -> tuple:
    """Extend the asset bridge with a `pick` asset for each of `refs` it does
    not hold yet, in the order given. `was` maps a slot `pick_ref` to the
    `pick_ref` the same pick had before it was slotted: an asset held under
    that older ref keeps its id and takes the new ref. Returns (bridge,
    pick_ref -> asset_id)."""
    was = was or {}
    known = existing[existing["pick_ref"].notna()]
    ref2aid = dict(zip(known["pick_ref"], known["asset_id"]))
    next_id = (int(existing["asset_id"].max()) + 1) if len(existing) else 1
    new, moved = [], {}
    for ref in refs:
        if ref in ref2aid:
            continue
        if was.get(ref) in ref2aid:
            moved[ref2aid[was[ref]]] = ref
            ref2aid[ref] = ref2aid.pop(was[ref])
            continue
        new.append(dict(asset_id=next_id, asset_type="pick", scorer_id=pd.NA,
                        gsis_id=pd.NA, player_key=pd.NA, pick_ref=ref))
        ref2aid[ref] = next_id; next_id += 1
    if not new and not moved:
        return existing, ref2aid
    bridge = existing.copy()
    if moved:
        bridge["pick_ref"] = bridge["asset_id"].map(moved).fillna(bridge["pick_ref"])
    frames = [f for f in (bridge, pd.DataFrame(new, columns=ASSET_COLS)) if len(f)]
    bridge = pd.concat(frames, ignore_index=True)[ASSET_COLS]
    return bridge.sort_values("asset_id").reset_index(drop=True), ref2aid


def _draft_year(draft_season) -> int:
    """`"2026-2027"` (or `"2026"`) -> 2026, the year Fantrax's trade row shows."""
    return int(str(draft_season)[:4])


def unslotted_ref(draft_season, original_owner, rnd) -> str:
    """A pick's `pick_ref` before it has a slot, as 04u writes it:
    (draft year, Original Owner, round)."""
    return f"{_draft_year(draft_season)}|{original_owner}|{int(rnd)}"


def slot_history(slotted: pd.DataFrame) -> dict:
    """Each slot `pick_ref` -> the `pick_ref` that pick had before its slot."""
    return {r.pick_ref: unslotted_ref(r.draft_season, r.original_owner, r.round)
            for r in slotted.itertuples()}


def all_pick_refs(slotted: pd.DataFrame, future: pd.DataFrame) -> list:
    """Every pick's `pick_ref`, slotted grid first, in a fixed order. A pick
    in both tables is listed once, under its slot."""
    s = slotted.sort_values(["draft_season", "division_id", "overall_slot"])["pick_ref"]
    f = future.sort_values(["draft_season", "round", "original_owner"])["pick_ref"]
    has_slot = set(slot_history(slotted).values())
    return [*s, *(ref for ref in f if ref not in has_slot)]


def resolve_pick_legs(trade_log: pd.DataFrame, slotted: pd.DataFrame,
                      future: pd.DataFrame, name_lut: dict) -> tuple:
    """Each pick leg of the parsed trade log -> the `pick_ref` of the pick it
    moved (see "Pick legs"). Returns (pick_ref by trade-log index, reason by
    index for the legs left unresolved, holder by future pick_ref after the
    replay). `name_lut` maps a lower-cased team name to its team_key."""
    refs, reasons = {}, {}
    legs = trade_log[trade_log["asset_kind"] == "pick"]

    division = dict(zip(slotted["original_owner"], slotted["division_id"]))
    slot_ref = {(_draft_year(r.draft_season), r.division_id, int(r.round), int(r.pick_in_round)): r.pick_ref
                for r in slotted.itertuples()}
    # (year, round) -> holder -> the Original Owners whose pick it holds.
    # Slotted picks are replayed too, so a leg made before the pick had a
    # slot still resolves once the pick has left the future table.
    held, future_ref = {}, {}
    for r in (*slotted.itertuples(), *future.itertuples()):
        year_round = (_draft_year(r.draft_season), int(r.round))
        if (*year_round, r.original_owner) in future_ref:
            continue                                    # in both tables: the slot wins
        held.setdefault(year_round, {}).setdefault(r.original_owner, []).append(r.original_owner)
        future_ref[(*year_round, r.original_owner)] = r.pick_ref

    def move(i, leg) -> bool:
        """Resolve one future leg if its sender's holdings name one pick."""
        year_round = (int(leg.draft_year), int(leg.draft_round))
        have = held.get(year_round, {}).get(leg.team_key_from, [])
        hint = leg.pick_owner_hint
        hinted = name_lut.get(hint.strip().lower()) if isinstance(hint, str) else None
        if hinted is not None and hinted not in have:
            return False
        if hinted is None and len(have) != 1:
            return False
        owner = hinted if hinted is not None else have[0]
        have.remove(owner)
        held[year_round].setdefault(leg.team_key_to, []).append(owner)
        refs[i] = future_ref[(*year_round, owner)]
        return True

    ordered = legs.sort_values(["event_date", "transaction_id"], kind="stable")
    for _, txn in ordered.groupby("transaction_id", sort=False):
        pending = []
        for i, leg in txn.iterrows():
            if pd.isna(leg.draft_year) or pd.isna(leg.draft_round):
                reasons[i] = "no_year_or_round"
            elif pd.isna(leg.team_key_from) or pd.isna(leg.team_key_to):
                reasons[i] = "unmapped_team"
            elif pd.notna(leg.pick_in_round):
                ref = slot_ref.get((int(leg.draft_year), division.get(leg.team_key_from),
                                    int(leg.draft_round), int(leg.pick_in_round)))
                if ref is None:
                    reasons[i] = "no_such_slot"
                else:
                    refs[i] = ref
            else:
                pending.append((i, leg))
        # A pick can pass through two teams inside one trade, so keep going
        # round the pending legs while any of them resolves.
        moved = True
        while pending and moved:
            left = [(i, leg) for i, leg in pending if not move(i, leg)]
            moved, pending = len(left) < len(pending), left
        for i, _ in pending:
            reasons[i] = "sender_holds_no_single_pick"

    holders = {future_ref[(*year_round, owner)]: team
               for year_round, by_team in held.items()
               for team, owners in by_team.items() for owner in owners}
    return (pd.Series(refs, dtype="object").reindex(trade_log.index),
            pd.Series(reasons, dtype="object").reindex(trade_log.index), holders)


def ownership_gaps(slotted: pd.DataFrame, future: pd.DataFrame, holders: dict,
                   log: pd.DataFrame) -> list:
    """Picks whose owner after the trades is not the `current_owner` Fantrax
    reports: [(pick_ref, replayed owner, reported owner)]. A future pick's
    replayed owner is its holder after the replay; a slot's is the last
    receiver among its legs in `log` (the finished trade log), or its
    Original Owner when no leg moved it."""
    reported = dict(zip(future["pick_ref"], future["current_owner"]))
    gaps = [(ref, team, reported[ref]) for ref, team in holders.items()
            if ref in reported and reported[ref] != team]
    slot_owner = dict(zip(slotted["pick_ref"], slotted["current_owner"]))
    legs = log[log["pick_in_round"].notna()].sort_values("event_date", kind="stable")
    last_to = dict(zip(legs["pick_ref"], legs["team_key_to"]))
    gaps += [(ref, team, slot_owner[ref]) for ref, team in last_to.items()
             if slot_owner.get(ref) != team]
    gaps += [(r.pick_ref, r.original_owner, r.current_owner) for r in slotted.itertuples()
             if r.pick_ref not in last_to and r.current_owner != r.original_owner]
    return sorted(gaps)


def finish_trade_log(parsed: pd.DataFrame, pick_ref: pd.Series, reasons: pd.Series,
                     sid2aid: dict, ref2aid: dict) -> tuple:
    """The parsed trade rows -> (fact_trade_log, the legs for review). Every
    row of the table has an `asset_id`, and no (transaction_id, asset_id)
    repeats: every leg of an asset that moves twice inside one trade goes to
    review, since the key can hold neither."""
    log = parsed.assign(pick_ref=pick_ref)
    is_pick = log["asset_kind"] == "pick"
    log["asset_id"] = log["scorer_id"].map(sid2aid).where(~is_pick, log["pick_ref"].map(ref2aid))
    reasons = reasons.where(log["asset_id"].notna(), reasons.fillna("no_asset"))
    twice = log["asset_id"].notna() & log.duplicated(["transaction_id", "asset_id"], keep=False)
    reasons = reasons.mask(twice, "asset_moves_twice_in_trade")
    unresolved = log["asset_id"].isna() | twice
    review = log[unresolved].assign(reason=reasons[unresolved])[PICK_REVIEW_COLS]
    log = log[~unresolved].astype({"asset_id": "int64"})
    # an Arrow string column whether or not the capture holds a pick leg
    log["pick_ref"] = log["pick_ref"].astype("string")
    return log[TRADE_LOG_COLS].reset_index(drop=True), review.reset_index(drop=True)


# %%
# ---- Contract sourcing (ADR-0019 decision 6) --------------------------------
# A Roster Move's contract is OBSERVED, never derived. Every ledger row asks,
# in order:
#   1. Roster State (fact_roster_state, one roster per Scoring Period) -- the
#      row that shows this copy on the move's team (the "from" team for a
#      trade) inside the copy's stint there. What Fantrax showed wins.
#   2. For a draft pick or a claim no Roster State row covers: the preseason
#      capture (fact_preseason_salary), when it was taken inside the stint the
#      move starts. `Minor` for a minors-eligible player, else the contract
#      the capture shows (see "The preseason capture" below).
#   3. Only when neither covers the move, a default: `Minor` for a
#      minors-eligible player; else the contract the copy already held; else
#      `1st` for a draft pick and `FA` for a claim or drop with no history.
# `contract_source` records which: `roster_state`, `preseason` or `default`.
# A trade or a drop with no Roster State row of its own keeps the contract of
# the stint it ends, and that stint's source with it.
#
# Which Roster State a move reads goes by Scoring Period, not by day. Fantrax
# stamps every move with the period it takes effect in (the `week` cell), and
# a period's roster is the roster at that period's lineup lock: it shows every
# move effective in that period or earlier, and nothing later. (Measured
# 2026-10-04: replaying the draft and every move by that stamp reproduces
# periods 1-4 row for row. A claim made on a Tuesday, after the week's games,
# is stamped for the next period and is not on the period it was made in.)
#
# - A draft pick and a claim START a stint. Each reads the FIRST Roster State
#   inside the stint it starts:
#          move period  <=  p  <  the period the copy next leaves the team in
#   A draft pick takes effect in period 1.
# - A trade and a drop END a stint. Each reads the LATEST Roster State inside
#   the stint, from before the move takes effect:
#          stint-start period  <=  p  <  move period
#   A copy with no stint on record (the ledger never saw it join the team)
#   reads any Roster State before the move's period.
# A copy dropped and claimed back starts a new stint, so neither rule reads a
# row from the old one (a `Minor` on a graduate).
#
# The roster of the period in play keeps changing until its lineup lock, so a
# Roster State is only read for a stint-starting move when it was captured
# after the move day: a capture dated the move day may predate the move.
#
# A move outside the season the index holds reads no Roster State and takes
# the default. A move of that season with no readable period stops the run
# (legs_without_period): it cannot be placed in a stint, and its neighbours
# would read another stint's row.
#
# A trade or a drop of a copy the ledger never saw join has no terms to
# inherit. It takes its salary, as well as its contract, off the Roster State
# row it reads.
#
# The preseason capture (fact_preseason_salary, one frozen roster taken
# 2026-07-18) is read for a contract only by a stint no Roster State row
# shows: a pick or a claim that left its team before Scoring Period 1 (#96
# decision 1, which amends ADR-0019 decision 6). The window is the one its
# salary is read by ("Salary sourcing"): after the move day, before the day
# the copy next left the team. Eligibility wins over the capture: it predates
# the `Minor` label, so it shows an eligible player on `1st`. That `Minor` is
# the default rule's, so its `contract_source` is `default`. (Measured
# 2026-10-04: Fantrax charged Dead Money on four claims the capture shows on
# `1st` and dropped before period 1, and none on the eligible players it
# shows the same way.)
#
# A drop by a team with no stint for the copy -- the ledger never saw it
# drafted, claimed or traded there -- is marked `no_stint` in
# `contract_source`, whatever its contract was read from. It ends no stint, so
# it makes no Dead Money (#96 decision 2).
class Seen(NamedTuple):
    """One Roster State row, as a move reads it."""
    period: int
    captured: object   # the day that period's roster was last read
    contract_id: object
    salary: float


class Preseason(NamedTuple):
    """One preseason capture row, as a move reads it."""
    captured: object     # the day the capture was taken
    salary: float
    contract_id: object  # None when the row shows no contract


class ContractSource(NamedTuple):
    snaps: dict     # (team_key, scorer_id) -> [Seen], by Scoring Period
    elig: list      # [(capture day, {minors-eligible scorer_ids})], oldest first
    years: dict     # contract_id -> dim_contract.contract_year
    preseason: dict # (team_key, scorer_id) -> Preseason
    season: object  # the season_id whose Roster State `snaps` and `preseason` hold


class Sourced(NamedTuple):
    """One Roster Move's contract, and how it was reached. Every flag after
    `observed` applies only when no Roster State row was read; see
    eligible_at() for `after_newest` and `left_list`."""
    contract_id: object
    observed: bool = False        # read off a Roster State row
    preseason: bool = False       # read off the preseason capture
    after_newest: bool = False    # eligible on the newest capture, taken before the move
    left_list: bool = False       # eligible before the move, off the next capture's list
    stale_capture: bool = False   # defaulted long after the newest eligibility capture

    @property
    def source(self) -> str:
        """The `contract_source` of a move that read its own contract."""
        return FROM_STATE if self.observed else FROM_PRESEASON if self.preseason else FROM_DEFAULT


def _day(dt):
    """The calendar day of a datetime, or None when it is unknown."""
    return None if dt is None or pd.isna(dt) else pd.Timestamp(dt).normalize()


def _period(value):
    """A Scoring Period as an int, or None when it is unknown or unreadable."""
    try:
        return None if value is None or pd.isna(value) else int(value)
    except (TypeError, ValueError):
        return None


def index_state(state, season_id) -> dict:
    """One season's Roster State rows, indexed per copy, by Scoring Period.
    Left out: rows with no contract, no salary or no capture date."""
    if state is None or state.empty:
        return {}
    seen = state[state["season_id"] == season_id].dropna(
        subset=["period", "contract_id", "salary", "capture_date"])
    snaps = {}
    for r in seen.sort_values("period").itertuples():
        snaps.setdefault((r.team_key, r.scorer_id), []).append(
            Seen(int(r.period), _day(r.capture_date), r.contract_id, float(r.salary)))
    return snaps


def index_eligibility(eligibility, season=None) -> list:
    """fact_minor_eligibility -> one set of scorer_ids per capture day. A row
    in a capture means Fantrax held the player minors-eligible that day.
    `season` keeps one season's captures, so that an old list cannot stamp
    `Minor` over a player who has since moved on."""
    if eligibility is None or eligibility.empty:
        return []
    if season is not None:
        eligibility = eligibility[eligibility["season"] == season]
    return [(_day(day), set(rows["scorer_id"]))
            for day, rows in eligibility.groupby("capture_date", sort=True)]


def contract_source(state, preseason, eligibility, contracts,
                    season_id=SEASON_ID, season=CFG.draft_year) -> ContractSource:
    """Everything a move's contract and salary are read from. `season_id` picks
    the Roster State and preseason rows; `season` the eligibility captures."""
    return ContractSource(
        snaps=index_state(state, season_id),
        elig=index_eligibility(eligibility, season),
        years=dict(zip(contracts["contract_id"], contracts["contract_year"])),
        preseason=index_preseason(preseason, season_id),
        season=season_id)


def first_in_stint(snaps: dict, team_key, scorer_id, period, event_dt, until=None):
    """The first Roster State row that shows this copy on this team inside the
    stint a draft pick or a claim starts: from the move's own period up to, and
    not including, `until` -- the period the copy next leaves the team in (None
    when it never does). A row captured on or before the move day is skipped.
    None when no row qualifies."""
    start, end, day = _period(period), _period(until), _day(event_dt)
    if start is None:
        return None
    return next((s for s in snaps.get((team_key, scorer_id), ())
                 if s.period >= start and (end is None or s.period < end)
                 and (day is None or s.captured > day)), None)


def latest_before(snaps: dict, team_key, scorer_id, period, since=None):
    """The latest Roster State row that shows this copy on this team before a
    trade or a drop takes effect, and no earlier than `since` -- the period the
    copy joined the team in (None when the ledger never saw it join). None when
    no row qualifies."""
    end, start = _period(period), _period(since)
    if end is None:
        return None
    seen = [s for s in snaps.get((team_key, scorer_id), ())
            if s.period < end and (start is None or s.period >= start)]
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


def resolve_contract(src: ContractSource, kind, scorer_id, event_dt,
                     inherited=None, seen=None, preseason=None) -> Sourced:
    """One Roster Move's contract: the Roster State row that covers the move
    (`seen`, from first_in_stint() or latest_before()); else, for a player who
    is not minors-eligible, the preseason capture's (`preseason`, the contract
    preseason_in_stint() found for a pick or a claim); else the default, which
    is `Minor` for an eligible player."""
    if seen is not None:
        return Sourced(seen.contract_id, observed=True)
    basis = eligible_at(src.elig, scorer_id, event_dt)
    # Eligibility wins over the capture: an eligible player's `Minor` is the
    # default rule's, whether or not the capture shows the stint.
    captured = basis is None and preseason is not None and pd.notna(preseason)
    contract_id = preseason if captured else default_contract(basis is not None, kind, inherited)
    return Sourced(contract_id, preseason=captured,
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
    Roster State row can produce one; it is written as observed and warned on."""
    return sorted(set(frame["contract_id"].dropna()) - set(contracts["contract_id"]))


# %%
# ---- Salary sourcing (#125) -------------------------------------------------
# A draft pick and a claim START a stint, so each sets the salary the copy
# carries. Both read it, in order, off:
#   1. The preseason capture (fact_preseason_salary, one frozen roster taken
#      before the season), when it was taken inside the stint the move starts:
#          move day  <  capture day  <  the day the copy next left the team
#      By day, because the capture belongs to no Scoring Period. After the move
#      day: a capture dated the move day may predate the move.
#   2. The FIRST Roster State inside that stint -- the row first_in_stint()
#      finds, which is also the row the move's contract is read from.
# The first observation, not the latest: it is the one closest to the move.
#
# Only when neither shows the copy, a default:
# - a draft pick: the fact_fantrax_adp salary of the draft's own season, on the
#   latest capture on or before the pick day, else the earliest one after it,
#   and never below the league minimum. A pick with no capture in the draft's
#   season takes the league minimum, and main() warns. Fantrax re-prices the
#   pool after the draft and keeps charging a roster the draft-time salary, so
#   the LATEST capture is the wrong one to read first, and another season's
#   pool is not read at all.
# - a claim: the salary it inherits this season in this Conference, else the
#   league minimum (see resolve_legs).
#
# A trade and a drop set no salary: they carry the copy's.
#
# Known limits:
# - An ADP capture taken after the pick can already carry Fantrax's post-draft
#   re-price.
# - A claim that leaves the team before a Roster State shows it keeps its
#   default: the trade carries the salary on, and the new team's row is not
#   read.
class Left(NamedTuple):
    """One departure of a copy from a team."""
    at: object       # when it left
    period: object   # the Scoring Period the departure takes effect in


def index_preseason(preseason, season_id) -> dict:
    """One season's preseason capture, indexed per copy: its salary and its
    contract. Left out: rows with no capture date and rows with no salary."""
    if preseason is None or preseason.empty:
        return {}
    seen = preseason[preseason["season_id"] == season_id].dropna(
        subset=["salary", "capture_date"])
    return {(r.team_key, r.scorer_id): Preseason(
                _day(r.capture_date), float(r.salary),
                r.contract_id if pd.notna(r.contract_id) else None)
            for r in seen.itertuples()}


def preseason_in_stint(preseason: dict, team_key, scorer_id, event_dt, until=None):
    """The preseason capture's row for this copy on this team, when the
    capture falls inside the stint the move starts: after the move day and
    before `until`, the day the copy next left the team (None when it never
    did). None when it does not."""
    day, end = _day(event_dt), _day(until)
    row = preseason.get((team_key, scorer_id))
    if day is None or row is None:
        return None
    return row if row.captured > day and (end is None or row.captured < end) else None


def departures(legs: list, spans=None, season=None) -> dict:
    """(team_key, scorer_id) -> each time the copy left that team, oldest
    first: a trade away from it, or a drop by it. A leg with no date is left
    out. Given `spans` and `season`, a departure of another season carries no
    period: its number counts that season's periods, and the stint it ends
    runs past every roster `season` holds."""
    left = {}
    for l in legs:
        team = {TRADE_IN: l["team_from"], DROP_EVENT: l["team_to"]}.get(l["kind"])
        if team is not None and pd.notna(team) and pd.notna(l["event_dt"]):
            period = _period(l.get("period"))
            if spans is not None and not _in_season(l["event_dt"], spans, season):
                period = None
            left.setdefault((team, l["scorer_id"]), []).append(Left(l["event_dt"], period))
    return {copy: sorted(times, key=lambda d: d.at) for copy, times in left.items()}


def stint_end(departs: dict, team_key, scorer_id, joined=None):
    """The copy's next departure from the team after joining it at `joined`;
    None when it never left. A draft pick passes no `joined`: the ledger and
    02e's replay put every transaction after the draft, so its stint ends at
    the copy's first departure, whatever its date. A departure stamped the same
    instant as the join belongs to the stint before (sort_legs puts it first)."""
    return next((left for left in departs.get((team_key, scorer_id), ())
                 if joined is None or left.at > joined), None)


def index_draft_salaries(adp: pd.DataFrame, season: int) -> dict:
    """fact_fantrax_adp -> scorer_id -> [(capture day, salary)], oldest first:
    the salaries a draft pick falls back on. Only `season`'s captures, and no
    row without a salary or a capture date: another season's pool is priced
    differently."""
    by_day = adp.sort_values(["capture_date", "week"], kind="stable")
    priced = by_day[(by_day["season"] == season) & by_day["salary"].notna()
                    & by_day["capture_date"].notna()]
    in_season = {}
    for r in priced.itertuples():
        in_season.setdefault(r.scorer_id, []).append((_day(r.capture_date), float(r.salary)))
    return in_season


def draft_time_salary(index: dict, scorer_id, event_dt, minimum: float):
    """A draft pick's (salary, where it was read) when no roster prices it: the
    draft season's latest capture on or before the pick day, else its earliest
    capture after -- neither below `minimum`, the league minimum -- else the
    minimum itself. A pick with no date reads the season's earliest capture."""
    day = _day(event_dt)
    seen = index.get(scorer_id, ())
    at_pick = [salary for captured, salary in seen if day is not None and captured <= day]
    if at_pick:
        return max(at_pick[-1], minimum), SALARY_AT_PICK
    if seen:
        return max(seen[0][1], minimum), SALARY_AFTER_PICK
    return minimum, SALARY_MINIMUM


def repriced(terms: dict, salary: float) -> dict:
    """Contract terms at a new salary."""
    old = terms["contract_value"]
    if pd.notna(old) and old == salary:
        return terms
    return {**terms, "contract_value": salary}


# %%
# ---- fact_roster_transactions: one startup_draft row per made pick ---------
def _epoch_ms_to_date(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date() if pd.notna(ms) else pd.NaT


def build_startup_rows(made, team_lut, sid2aid, gsis_lut, draft_salaries, src, departs,
                       minimum):
    """Made picks -> (the ledger's `startup_draft` rows, one per pick; the
    `tally_sourcing` of their contracts; how many salaries each source gave).

    `draft_salaries` is `index_draft_salaries()`; `departs` is `departures()`
    of the transaction legs, which end a drafted copy's stint; `minimum` is the
    league-minimum salary."""
    fact_rows, sourced, priced = [], [], []
    made = made.assign(pick_ref=pick_refs(SEASON_ID, made))
    for _, p in made.iterrows():
        sid = p["scorerId"]
        team_key   = team_lut[p["teamId"]]
        event_date = _epoch_ms_to_date(p["modifiedDate"])
        # The pick starts the copy's stint, which ends at its first departure.
        left = stint_end(departs, team_key, sid)
        seen = first_in_stint(src.snaps, team_key, sid, DRAFT_PERIOD, event_date,
                              left.period if left else None)
        pre = preseason_in_stint(src.preseason, team_key, sid, event_date,
                                 left.at if left else None)
        # Salary: the preseason capture, else the first Roster State inside the
        # stint, else the pool at draft time (see "Salary sourcing").
        if pre is not None:
            val, origin = pre.salary, SALARY_PRESEASON
        elif seen is not None:
            val, origin = seen.salary, SALARY_STATE
        else:
            val, origin = draft_time_salary(draft_salaries, sid, event_date, minimum)
        val = float(val)
        priced.append(origin)
        # Contract: that first Roster State, else the preseason capture, else
        # the default ("Contract sourcing").
        sourced.append(resolve_contract(
            src, EVENT_TYPE, sid, event_date, seen=seen,
            preseason=pre.contract_id if pre is not None else None))
        contract_id = sourced[-1].contract_id
        fact_rows.append({
            "transaction_id": p["pick_ref"],
            "season_id":      SEASON_ID,
            "event_type":     EVENT_TYPE,
            "team_key":       team_key,
            "asset_id":       sid2aid[sid],
            "event_seq":      int(p["overall_slot"]),
            "event_date":     event_date,
            "period":         DRAFT_PERIOD,
            "contract_id":    contract_id,
            "contract_year":  contract_year_of(src, contract_id),
            "contract_value": val,
            "contract_source": sourced[-1].source,
            "status":         STATUS,
            "scorer_id":      sid,
            "gsis_id":        gsis_lut.get(sid),
            "draft_round":    int(p["round"]),
            "pick_in_round":  int(p["pickNumber"]),
            "pick_overall":   int(p["overall_slot"]),
            "source":         SOURCE,
            "claim_method":   pd.NA,
            "claim_bid":      pd.NA,
        })

    fact = claim_dtypes(pd.DataFrame(fact_rows)[LEDGER_COLS])
    fact["event_date"] = pd.to_datetime(fact["event_date"])
    fact["period"] = fact["period"].astype("Int64")
    # key integrity: the ADR grain must be unique.
    assert not fact.duplicated(LEDGER_KEY).any(), "duplicate ledger key — grain violated"
    return fact, tally_sourcing(sourced), {o: priced.count(o) for o in dict.fromkeys(priced)}


# %%
# ---- Transaction events from 04t capture (trade / claim / drop) ------------
# 04t captures BOTH views of Fantrax's transaction history into one file:
# `transactionCode` is null on a trade leg and "CLAIM"/"DROP" on free-agency
# churn. Player-asset legs of all three types feed fact_roster_transactions
# (dim_roster_asset's asset_id system + 02e's replay); pick legs (trade-only)
# land in fact_trade_log alone, each resolved to its pick asset ("Pick legs").
#
# "trade_away" and "drop" are TERMINAL in 02e (they remove the copy from the
# active roster); "trade" lands the asset on the new team and "claim" lands it
# on the claiming team.
#
# **One shared chronological event_seq** (TXN_SEQ_BASE + i, ordered by each
# row's real parsed datetime) across all three types: trades and FA churn
# interleave in real time, so per-type seq bases would let 02e's
# last-event-wins replay rank an older claim after a newer trade. It is sort
# order, not identity: a capture that adds or drops a move renumbers every
# later row. A row is identified by `transaction_id` (Fantrax's `txSetId`)
# with its scorer, team and event type.
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
# Those inherited terms set the leg's salary -- except on a claim a roster
# shows at another one ("Salary sourcing" above). Its `contract_id` goes
# through "Contract sourcing": Roster State wins, then the preseason capture
# for a claim, and the inherited contract is only the fallback for a player
# who is not minors-eligible.
#
# **Claim method** (#68). Fantrax's history does not say whether a claim went
# through the waiver run or was a free-agent add: `claimType` reads the same
# on every claim. The row's `bid` cell is the only field that separates them,
# so the method is INFERRED from it: a claim with a bid, 0.00 included, is
# `waiver`; a claim whose bid cell is empty is `free_agent`. (In the capture
# of 2026-10-11 every claim stamped 08:00, the waiver run, carried a bid and
# no claim without one was stamped 08:00.) `claim_bid` keeps the amount. A
# drop takes the method of the claim it was made with -- same `txSetId`, same
# team -- and no bid; a drop made on its own has no method. A capture with no
# `bid` cell on a claim leaves the method null: it cannot be told. Neither
# column changes a contract or a salary.
# The league's Fantrax rules page (read 2026-10-11) fits the rule: "Free Agent
# Claim System: Bidding", bids "processed on: Wed, Thu at 8:00 am", minimum bid
# $0.00, and Fantrax's own Waiver Wire process "Not used". So what the league
# calls waivers is Fantrax's bid run, and a 0.00 bid is a real bid.
#
# Every leg carries `period`: the Scoring Period Fantrax says the move takes
# effect in (the row's `week` cell). It decides which Roster State the leg
# reads, and it is written to the ledger (null on a move of another season,
# whose number counts that season's periods).
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


def _in_season(dt, spans, season) -> bool:
    """Does the event fall inside `season`'s span?"""
    sid = _season_id_for(dt, spans)
    return bool(pd.notna(sid) and sid == season)


def unkeyed_moves(ledger: pd.DataFrame) -> int:
    """Transaction rows on a ledger with no `transaction_id`: written before
    the stable key. Only a rebuild from the 04t capture gives them one."""
    moves = ledger[ledger["event_type"].isin(TXN_EVENT_TYPES)]
    if "transaction_id" not in moves.columns:
        return len(moves)
    return int(moves["transaction_id"].isna().sum())


def legs_without_period(legs: list, spans, season) -> list:
    """`season`'s legs with no readable Scoring Period. Fantrax stamps every
    move with one, so main() stops on any (see "Contract sourcing")."""
    return [l for l in legs if _in_season(l["event_dt"], spans, season)
            and _period(l.get("period")) is None]


def _parse_trades(trade_rows, team_lut, gsis_lut):
    """Trade rows -> (fact_trade_log rows, player-asset legs)."""
    last_date = {}   # date is only stamped on the first row of each txSetId
                     # group (HTML rowspan) -- carry it forward within the group.
    last_week = {}   # same for the week cell the leg's period is read from
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
        if _period(week) is not None:
            last_week[txset] = week

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
            legs.append({"kind": TRADE_IN, "transaction_id": txset, "scorer_id": sid,
                         "team_from": team_key_from, "team_to": team_key_to,
                         "event_dt": event_dt, "period": _period(last_week.get(txset))})
    return trade_log_rows, legs


def _claim_bid(row) -> tuple:
    """A CLAIM row -> (claim_method, claim_bid), read off its `bid` cell
    ("Claim method" above). No such cell: neither is known."""
    cell = next((c for c in row["cells"] if c["key"] == "bid"), None)
    if cell is None:
        return pd.NA, pd.NA
    content = cell.get("content")
    text = "" if content is None else str(content).strip()
    if not text:
        return CLAIM_FREE_AGENT, pd.NA
    amount = pd.to_numeric(text.replace("$", "").replace(",", ""), errors="coerce")
    return CLAIM_WAIVER, (float(amount) if pd.notna(amount) else pd.NA)


def claim_dtypes(ledger: pd.DataFrame) -> pd.DataFrame:
    """The claim columns typed the same whether or not any row fills them.
    The nullable string type keeps a missing method missing on pandas 2 and 3
    alike (a plain `str` cast writes the text "<NA>" on pandas 2)."""
    ledger["claim_method"] = ledger["claim_method"].astype("string")
    ledger["claim_bid"] = pd.to_numeric(ledger["claim_bid"], errors="coerce").astype("float64")
    return ledger


def _parse_claim_drops(cd_rows, team_lut):
    """Claim/drop rows -> (legs, rows skipped for no scorer, for no team).

    Same HTML-rowspan shape as trades: only the FIRST row of a txSetId group
    carries the `team`/`date`/`week` cells, and a paired DROP inherits all
    three from the CLAIM above it. Rows with no `scorer` block (or an unmapped team) can't be
    posted to an asset-keyed ledger, so they're counted and skipped.

    A claim leg carries `claim_method` and `claim_bid`; a drop takes the
    method of the claim of its own txSetId and team, wherever in the group
    that claim sits."""
    last_cd_team, last_cd_date, last_cd_week = {}, {}, {}
    methods = {}                         # (txSetId, team_key) -> its claim's method
    legs, n_no_player, n_no_team = [], 0, 0
    for r in cd_rows:
        txset = r["txSetId"]
        tcell = next((c for c in r["cells"] if c["key"] == "team"), None)
        if tcell and tcell.get("teamId"):
            last_cd_team[txset] = tcell["teamId"]
        dcell = next((c["content"] for c in r["cells"] if c["key"] == "date"), None)
        if dcell:
            last_cd_date[txset] = dcell
        wcell = next((c.get("content") for c in r["cells"] if c["key"] == "week"), None)
        if _period(wcell) is not None:
            last_cd_week[txset] = wcell

        sid = (r.get("scorer") or {}).get("scorerId")
        if not sid:
            n_no_player += 1
            continue
        team_key = team_lut.get(last_cd_team.get(txset))
        if not team_key:
            n_no_team += 1
            continue
        is_claim = r["transactionCode"] == "CLAIM"
        method, bid = _claim_bid(r) if is_claim else (pd.NA, pd.NA)
        if is_claim and pd.notna(method):
            # One method per transaction and team: its first claim that has one.
            methods.setdefault((txset, team_key), method)
        legs.append({
            "kind":      CLAIM_EVENT if is_claim else DROP_EVENT,
            "transaction_id": txset,
            "scorer_id": sid,
            "team_from": pd.NA,
            "team_to":   team_key,
            "event_dt":  pd.to_datetime(last_cd_date.get(txset), errors="coerce"),
            "period":    _period(last_cd_week.get(txset)),
            "claim_method": method,
            "claim_bid":    bid,
        })
    for l in legs:
        if l["kind"] == DROP_EVENT:
            l["claim_method"] = methods.get((l["transaction_id"], l["team_to"]), pd.NA)
    return legs, n_no_player, n_no_team


KNOWN_SKIPPED_CODES = frozenset({"LINEUP_CHANGE"})


def count_skipped_codes(raw_rows):
    """Rows no parser reads -> (counts, unknown): a count per `transactionCode`
    that is not a trade leg (null), CLAIM or DROP, and the codes among them
    outside KNOWN_SKIPPED_CODES, sorted."""
    counts = {}
    for r in raw_rows:
        code = r.get("transactionCode")
        if code is None or code in ("CLAIM", "DROP"):
            continue
        counts[code] = counts.get(code, 0) + 1
    unknown = sorted(c for c in counts if c not in KNOWN_SKIPPED_CODES)
    return counts, unknown


def skipped_code_lines(raw_rows):
    """The `[info]` / `[warn]` lines main() prints for the skipped codes."""
    counts, unknown = count_skipped_codes(raw_rows)
    lines = []
    known = {c: n for c, n in sorted(counts.items()) if c not in unknown}
    if known:
        lines.append("[info] skipped transaction code(s): "
                     + ", ".join(f"{c} x{n}" for c, n in known.items()))
    if unknown:
        lines.append("[warn] transaction code(s) in no known list, skipped: "
                     + ", ".join(f"{c} x{counts[c]}" for c in unknown))
    return lines


def parse_txn_rows(raw_rows, team_lut, gsis_lut):
    """Captured transaction-history rows -> (trade_log, legs, stats).

    - `trade_log`: one row per traded asset (players AND picks) for
      fact_trade_log, or None when the capture holds no trade.
    - `legs`: one dict per player-asset leg (`kind`, `transaction_id`,
      `scorer_id`, `team_from`, `team_to`, `event_dt`, `period`), trades first
      then claim/drops, in capture order. A claim or drop leg also carries
      `claim_method` and `claim_bid`.
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

    A claim of a player with no contract history this season lands here.
    resolve_legs then re-prices it off the first roster that shows it on the
    claiming team ("Salary sourcing").

    Known gap: a claim that left the team again before any roster showed it,
    or that takes effect after the newest Roster State, keeps the league
    minimum."""
    fa    = contracts.loc[contracts["contract_id"] == FA_CONTRACT_ID].iloc[0]
    value = float(fa["min_salary"])
    return dict(contract_id=FA_CONTRACT_ID, contract_year=1,
                contract_value=value, status="active")


def sort_legs(legs: list[dict]) -> list[dict]:
    """Chronological order, with the same-timestamp tiebreak in _KIND_ORDER."""
    return sorted(legs, key=lambda l: (pd.Timestamp.min if pd.isna(l["event_dt"]) else l["event_dt"],
                                       _KIND_ORDER[l["kind"]]))


def _same_contract(a, b) -> bool:
    """Do two contract ids match? Unknown matches unknown."""
    if pd.isna(a) or pd.isna(b):
        return bool(pd.isna(a) and pd.isna(b))
    return a == b


def resolve_legs(legs, base, sid2aid, conf_lut, gsis_lut, spans, fa, src):
    """Transaction legs -> ledger rows, plus what main() reports on.

    `base` is the NON-transaction ledger (startup_draft rows); `fa` is
    `fa_terms()`; `src` is the ContractSource. Seed contract state from `base`,
    then walk the transaction stream forward, updating state as we go -- so a
    chained trade, or a drop-then-reclaim on the same day, resolves against
    what was actually true at that moment.

    `copy_terms` holds the open stints: a copy is in it from the pick, claim
    or trade that put it on a team until the trade or drop that takes it off.
    A drop of a copy that is not in it ends no stint (`no_stint`).

    Returns (rows, missing_source, fa_fallback, sourcing, roster_priced):
    traded players with no prior ledger row on their 'from' team, claims left
    at the league minimum (no in-season history, on no roster), the
    `tally_sourcing` of the legs' contracts, and claims priced off a roster."""
    copy_terms, conf_terms = {}, {}      # (team_key, asset_id) / (conference, asset_id)
    stint_start = {}                     # (team_key, asset_id) -> the period the copy joined in
    departs = departures(legs, spans, src.season)   # (team_key, scorer_id) -> when it left
    for r in base.sort_values("event_seq").itertuples():
        t = {c: getattr(r, c) for c in _TERM_COLS}
        copy_terms[(r.team_key, r.asset_id)] = t
        stint_start[(r.team_key, r.asset_id)] = DRAFT_PERIOD
        conf_terms[(conf_lut.get(r.team_key), r.asset_id)] = (t, r.season_id)

    rows, missing_source, fa_fallback, sourced, roster_priced = [], [], [], [], []
    for i, l in enumerate(sort_legs(legs)):
        sid, kind = l["scorer_id"], l["kind"]
        aid = sid2aid[sid]
        team, season = l["team_to"], _season_id_for(l["event_dt"], spans)
        conf = conf_lut.get(team)
        prior = conf_terms.get((conf, aid))
        # The rosters are one season's: a move of another season reads none.
        # (A leg outside every season span has no season; main() rejects it.)
        in_season = pd.notna(season) and season == src.season
        period = _period(l.get("period")) if in_season else None
        # The stint a trade or a drop ends: the copy's on the team it leaves.
        holder = l["team_from"] if kind == TRADE_IN else team
        joined = None if kind == CLAIM_EVENT else copy_terms.get((holder, aid))
        pre = None       # the preseason capture's row; only a claim reads one

        # 1. The terms the copy carries into this move (salary, status), and
        #    the Roster State row that covers it (see "Contract sourcing").
        if kind == TRADE_IN:
            seen = latest_before(src.snaps, holder, sid, period, stint_start.get((holder, aid)))
            inherited = joined or (prior[0] if prior else None)
            if inherited is None:
                # No terms on the ledger: the Roster State row prices the
                # copy, when there is one.
                missing_source.append((holder, sid))
                inherited = (repriced(fa, seen.salary) if seen is not None else
                             dict(contract_id=pd.NA, contract_year=pd.NA, contract_value=pd.NA,
                                  status="active"))
        else:
            # Only a contract held THIS season carries over ("retain salary and
            # contract for the season"); anything older resets to league minimum.
            inherited = prior[0] if (prior and prior[1] == season) else None
            if inherited is None and kind == DROP_EVENT:
                inherited = joined
            no_history = inherited is None
            if no_history:
                inherited = fa
            if kind == DROP_EVENT:
                seen = latest_before(src.snaps, team, sid, period, stint_start.get((team, aid)))
                if no_history and seen is not None:
                    inherited = repriced(inherited, seen.salary)
            else:
                # A claim starts a stint: the first roster inside it sets the
                # salary (see "Salary sourcing").
                left = stint_end(departs, team, sid, l["event_dt"])
                seen = first_in_stint(src.snaps, team, sid, period, l["event_dt"],
                                      left.period if left else None)
                if in_season:
                    pre = preseason_in_stint(src.preseason, team, sid, l["event_dt"],
                                             left.at if left else None)
                salary = (pre.salary if pre is not None
                          else seen.salary if seen is not None else None)
                if salary is not None:
                    inherited = repriced(inherited, salary)
                    roster_priced.append(sid)
                elif no_history:
                    fa_fallback.append(sid)

        # 2. Its contract: Roster State wins, then the preseason capture (a
        #    claim only), else the default.
        got = resolve_contract(src, kind, sid, l["event_dt"], inherited["contract_id"], seen,
                               pre.contract_id if pre is not None else None)
        sourced.append(got)
        contract_id = got.contract_id
        #    Where it was read: a claim starts a stint, so it read its own. A
        #    trade or a drop with no Roster State row keeps the contract of
        #    the stint it ends, and that stint's source with it. A contract
        #    the default rule changed on the way (a graduate's `Minor`) is a
        #    default.
        if kind == DROP_EVENT and joined is None:
            source = NO_STINT
        elif got.observed or kind == CLAIM_EVENT:
            source = got.source
        elif joined is not None and _same_contract(contract_id, joined["contract_id"]):
            source = joined["contract_source"]
        else:
            source = FROM_DEFAULT
        terms = {**inherited, "contract_id": contract_id,
                 "contract_year": contract_year_of(src, contract_id),
                 "contract_source": source}

        seq = TXN_SEQ_BASE + i
        common = dict(transaction_id=l["transaction_id"], season_id=season, period=period,
                      **terms, scorer_id=sid,
                      gsis_id=gsis_lut.get(sid), draft_round=pd.NA,
                      pick_in_round=pd.NA, pick_overall=pd.NA, source=TRADE_SOURCE,
                      claim_method=l.get("claim_method", pd.NA),
                      claim_bid=l.get("claim_bid", pd.NA))
        if kind == TRADE_IN:
            rows.append({**common, "event_type": TRADE_AWAY, "team_key": l["team_from"],
                         "asset_id": aid, "event_seq": seq, "event_date": l["event_dt"]})
            rows.append({**common, "event_type": TRADE_IN, "team_key": team,
                         "asset_id": aid, "event_seq": seq, "event_date": l["event_dt"]})
            copy_terms.pop((l["team_from"], aid), None)
            stint_start.pop((l["team_from"], aid), None)
            copy_terms[(team, aid)] = terms
            stint_start[(team, aid)] = period
        else:
            rows.append({**common, "event_type": kind, "team_key": team,
                         "asset_id": aid, "event_seq": seq, "event_date": l["event_dt"]})
            if kind == CLAIM_EVENT:
                copy_terms[(team, aid)] = terms
                stint_start[(team, aid)] = period
            else:
                copy_terms.pop((team, aid), None)
                stint_start.pop((team, aid), None)
        conf_terms[(conf, aid)] = (terms, season)
    return rows, missing_source, fa_fallback, tally_sourcing(sourced), roster_priced


# %%
# ---- Run -------------------------------------------------------------------
def main():
    picks = parse_draft_results(load_draft())
    print(f"[info] {len(picks)} pick slots across {picks['divisionId'].nunique()} division(s); "
          f"{picks['scorerId'].notna().sum()} made")

    # ---- Identity + value lookups ------------------------------------------
    teams_dim = etl.read_table("dim_fantasy_teams")
    team_lut = dict(zip(teams_dim["fantrax_team_id"], teams_dim["team_key"]))
    conf_lut = dict(zip(teams_dim["team_key"], teams_dim["conference"]))
    name_lut = ({n.strip().lower(): k for n, k in zip(teams_dim["team_name"], teams_dim["team_key"])
                 if isinstance(n, str)} if "team_name" in teams_dim.columns else {})

    px = etl.read_table("dim_fantrax_crosswalk")
    gsis_lut = dict(zip(px["scorer_id"], px["gsis_id"]))
    pkey_lut = dict(zip(px["scorer_id"], px["player_key"]))

    draft_salaries = index_draft_salaries(etl.read_table("fact_fantrax_adp"),
                                          CFG.draft_year)

    contracts = etl.read_table("dim_contract")
    spans = season_spans(etl.read_table("dim_season"))
    fa = fa_terms(contracts)

    # ---- Contract source: Roster State (04r), the preseason capture, and
    #      minors eligibility (04v) ------------------------------------------
    state, preseason, eligibility = (
        etl.read_table(name) if etl.table_exists(name) else None
        for name in ("fact_roster_state", "fact_preseason_salary", "fact_minor_eligibility"))
    src = contract_source(state, preseason, eligibility, contracts)
    read_periods = sorted({s.period for seen in src.snaps.values() for s in seen})
    print(f"[info] contract source: Roster State of {len(read_periods)} Scoring Period(s) "
          f"{read_periods} ({SEASON_ID}), {len(src.elig)} eligibility snapshot(s)")
    print(f"[info] salary source: the same Roster State, and {len(src.preseason)} "
          f"preseason salar(ies)")
    if not src.snaps:
        print("[warn] no fact_roster_state for this season (run 04r) -- every move "
              "takes its default contract and salary")
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
    write_table("dim_roster_asset", dim_roster_asset)
    print(f"[ok] dim_roster_asset: {len(dim_roster_asset)} assets "
          f"({(dim_roster_asset['asset_type']=='player').sum()} player, "
          f"{(dim_roster_asset['asset_type']=='prospect').sum()} prospect) -> {ASSET_PATH.name}")

    # ---- fact_draft_pick ----------------------------------------------------
    dim_draft_pick = build_draft_picks(picks, team_lut)
    write_table("fact_draft_pick", dim_draft_pick, mode="replace_partition", keys=("draft_season",))
    print(f"[ok] fact_draft_pick: {len(dim_draft_pick)} slots ({SEASON_ID}, "
          f"{int(dim_draft_pick['is_made'].sum())} made) -> {PICK_PATH.name}")

    # ---- Pick assets: one per pick, slotted and future ------------------------
    slotted = etl.read_table("fact_draft_pick")
    future = (etl.read_table("fact_draft_pick_future") if etl.table_exists("fact_draft_pick_future")
              else pd.DataFrame(columns=["pick_ref", "draft_season", "round",
                                         "original_owner", "current_owner"]))
    if not len(future):
        print("[warn] no fact_draft_pick_future (run 04u) -- a traded future pick "
              "cannot be resolved and goes to review")
    dim_roster_asset, ref2aid = mint_pick_assets(_read_assets(), all_pick_refs(slotted, future),
                                                 slot_history(slotted))
    write_table("dim_roster_asset", dim_roster_asset)
    print(f"[ok] dim_roster_asset: {len(ref2aid)} pick asset(s) "
          f"({len(slotted)} slotted, {len(future)} future)")

    # ---- Transaction history: parsed here, posted further down ----------------
    # The parse is pure. The draft rows need it first: a trade away or a drop
    # ends a drafted copy's stint, which bounds the snapshot its salary is read
    # from.
    raw_txn_rows = load_txn_rows()
    trade_log, legs, stats = parse_txn_rows(raw_txn_rows, team_lut, gsis_lut)
    unplaced = legs_without_period(legs, spans, src.season)
    if unplaced:
        l = unplaced[0]
        raise RuntimeError(
            f"{len(unplaced)} transaction leg(s) of {src.season} carry no readable Scoring "
            f"Period (the `week` cell) -- has the transaction history changed shape? "
            f"First: {l['kind']} of {l['scorer_id']} at {l['event_dt']}. The ledger is "
            f"not rebuilt.")
    # With no legs the ledger's transaction rows are kept as they are, so they
    # must already carry the key.
    stranded = unkeyed_moves(etl.read_table("fact_roster_transactions")) if not legs and etl.table_exists("fact_roster_transactions") else 0
    if stranded:
        raise RuntimeError(
            f"{stranded} transaction row(s) on the ledger carry no transaction_id (written "
            f"before the stable key) and this run has no transaction history to rebuild "
            f"them from -- run 04t. The ledger is not rebuilt.")

    # ---- fact_roster_transactions: startup_draft rows ------------------------
    fact, draft_sourcing, draft_priced = build_startup_rows(
        made, team_lut, sid2aid, gsis_lut, draft_salaries, src,
        departures(legs, spans, src.season),
        fa["contract_value"])
    tallies = [draft_sourcing]
    total = write_table("fact_roster_transactions", fact, mode="replace_partition",
                        keys=("season_id", "event_type"))
    # A ledger written under an older schema keeps its other rows, but not a
    # column that has since been dropped.
    kept = etl.read_table("fact_roster_transactions")
    # With legs the whole ledger is written once more below, in today's
    # columns, so the file is left alone here: transaction rows from before
    # the stable key have no transaction_id, the seam refuses a null key, and
    # they stay on disk until the rebuilt rows replace them in one write.
    if list(kept.columns) != LEDGER_COLS and not legs:
        write_table("fact_roster_transactions", claim_dtypes(kept.reindex(columns=LEDGER_COLS)))
    print(f"[ok] fact_roster_transactions: +{len(fact)} {EVENT_TYPE} rows "
          f"({total} total) -> {FACT_PATH.name}")
    print(f"[info] {EVENT_TYPE} contracts: {fact['contract_id'].value_counts().to_dict()} "
          f"({draft_sourcing['observed']} read off Roster State, "
          f"{draft_sourcing['preseason']} off the preseason capture)")
    print(f"[info] {EVENT_TYPE} salaries read off: {draft_priced}")
    if draft_priced.get(SALARY_MINIMUM):
        print(f"[warn] {draft_priced[SALARY_MINIMUM]} pick(s) are on no roster and have no "
              f"{CFG.draft_year} salary capture -- priced at the league minimum "
              f"(${fa['contract_value']:,.0f})")

    # ---- Asset bridge extension from the rosters -----------------------------
    # A roster can carry copies the startup draft never saw -- a player added
    # off free agency after the draft still shows up on a Roster State or the
    # preseason capture. Mint asset_ids for them so the bridge covers every
    # scorer the ledger might later reference (a trade/claim leg for an unminted
    # scorer would KeyError downstream).
    #
    # This block used to ALSO derive `minor_assignment`/`minor_graduation` events
    # from per-copy contract transitions. That was removed under ADR-0011. ADR-0019
    # has since made `Minor` a contract stage, but a stage change is still not a
    # ledger event: each Roster Move reads its contract off Roster State (see
    # "Contract sourcing"), and the Minors Roster Slot reaches the cap through
    # 02e's `roster_slot` stamp.
    rostered = sorted({sid for frame in (state, preseason) if frame is not None
                       for sid in frame["scorer_id"].dropna().unique()})
    if rostered:
        dim_roster_asset, sid2aid = mint_assets(rostered, _read_assets(), gsis_lut, pkey_lut)
        write_table("dim_roster_asset", dim_roster_asset)
        print(f"[ok] asset bridge extended from the rosters: {len(dim_roster_asset)} assets "
              f"-> {ASSET_PATH.name}")
    else:
        print("[info] no fact_roster_state or fact_preseason_salary yet (run 04r) -- "
              "asset bridge covers drafted copies only")

    # ---- Transaction events (trade / claim / drop) ---------------------------
    if raw_txn_rows:
        print(f"[info] captured txn rows: {stats['trade_rows']} trade leg(s), "
              f"{stats['claim_drop_rows']} claim/drop row(s)")

    if trade_log is not None:
        n_unmapped = int((trade_log["team_key_from"].isna() | trade_log["team_key_to"].isna()).sum())
        if n_unmapped:
            print(f"[warn] {n_unmapped} trade_log row(s) have an unmapped team "
                  f"(fantrax_team_id missing from dim_fantasy_teams) -- left NA")
        # Every traded player needs an asset, a leg with an unmapped team included.
        traded = sorted(trade_log.loc[trade_log["asset_kind"] == "player", "scorer_id"].unique())
        dim_roster_asset, sid2aid = mint_assets(traded, _read_assets(), gsis_lut, pkey_lut)
        write_table("dim_roster_asset", dim_roster_asset)

        pick_ref, reasons, holders = resolve_pick_legs(trade_log, slotted, future, name_lut)
        trade_log, pick_review = finish_trade_log(trade_log, pick_ref, reasons, sid2aid, ref2aid)
        write_table("fact_trade_log", trade_log)
        n_picks = int((trade_log["asset_kind"] == "pick").sum())
        print(f"[ok] fact_trade_log: {len(trade_log)} asset row(s) across "
              f"{trade_log['transaction_id'].nunique()} trade(s), {n_picks} pick leg(s) "
              f"resolved to a pick -> {TRADE_LOG_PATH.name}")
        # The review file is rebuilt on every run, like the crosswalk's.
        if len(pick_review):
            PICK_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
            pick_review.to_csv(PICK_REVIEW_PATH, index=False)
            print(f"[warn] {len(pick_review)} trade leg(s) cannot be keyed "
                  f"({pick_review['reason'].value_counts().to_dict()}) -- left out of "
                  f"fact_trade_log, listed in {PICK_REVIEW_PATH.name}")
        elif PICK_REVIEW_PATH.exists():
            PICK_REVIEW_PATH.unlink()
        gaps = ownership_gaps(slotted, future, holders, trade_log)
        if gaps:
            PICK_OWNER_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(gaps, columns=PICK_OWNER_REVIEW_COLS).to_csv(PICK_OWNER_REVIEW_PATH, index=False)
            print(f"[warn] {len(gaps)} pick(s) end the trade replay with an owner Fantrax "
                  f"does not report (rerun 04u, or a trade is missing) -- listed in "
                  f"{PICK_OWNER_REVIEW_PATH.name}: {gaps[:5]}{'...' if len(gaps) > 5 else ''}")
        elif PICK_OWNER_REVIEW_PATH.exists():
            PICK_OWNER_REVIEW_PATH.unlink()

    for line in skipped_code_lines(raw_txn_rows):
        print(line)

    if stats["no_player"] or stats["no_team"]:
        print(f"[warn] skipped {stats['no_player']} claim/drop row(s) with no scorer and "
              f"{stats['no_team']} with an unmapped team")

    if legs:
        dim_roster_asset, sid2aid = mint_assets(sorted({l["scorer_id"] for l in legs}),
                                                _read_assets(), gsis_lut, pkey_lut)
        write_table("dim_roster_asset", dim_roster_asset)

        base = claim_dtypes(etl.read_table("fact_roster_transactions").reindex(columns=LEDGER_COLS))
        base = base[~base["event_type"].isin(TXN_EVENT_TYPES)]
        txn_fact_rows, missing_source, fa_fallback, txn_sourcing, roster_priced = resolve_legs(
            legs, base, sid2aid, conf_lut, gsis_lut, spans, fa, src)
        tallies.append(txn_sourcing)

        if missing_source:
            print(f"[warn] {len(missing_source)} traded player(s) had no prior ledger row on "
                  f"their 'from' team -- priced off Roster State where it shows them, "
                  f"else contract fields left NA: "
                  f"{missing_source[:5]}{'...' if len(missing_source) > 5 else ''}")
        if roster_priced:
            print(f"[info] {len(roster_priced)} claim(s) priced off a roster "
                  f"(the preseason capture or Roster State)")
        if fa_fallback:
            print(f"[info] {len(fa_fallback)} claim(s) had no in-season contract history and "
                  f"are on no roster -- priced at the league minimum "
                  f"(${fa['contract_value']:,.0f})")

        txn_fact = claim_dtypes(pd.DataFrame(txn_fact_rows)[LEDGER_COLS])
        txn_fact["event_date"] = pd.to_datetime(txn_fact["event_date"])
        txn_fact["period"] = txn_fact["period"].astype("Int64")
        assert txn_fact["season_id"].notna().all(), "event_date outside every dim_season span"
        assert not txn_fact.duplicated(LEDGER_KEY).any(), "duplicate transaction-event ledger key"

        # Replace by EVENT_TYPE, not (season_id, event_type): these types are rebuilt
        # in full from the 04t capture on every run, so a corrected season_id would
        # otherwise strand the previous run's partition behind as orphan rows.
        # LEDGER_COLS only: a column a later schema dropped does not ride along
        # on the rows that were kept.
        _led    = etl.read_table("fact_roster_transactions")
        _stale  = int(_led["event_type"].isin(TXN_EVENT_TYPES).sum())
        out     = claim_dtypes(
            pd.concat([_led[~_led["event_type"].isin(TXN_EVENT_TYPES)], txn_fact],
                      ignore_index=True)[LEDGER_COLS])
        assert out[LEDGER_KEY].notna().all().all(), "ledger row with part of its key missing"
        assert not out.duplicated(LEDGER_KEY).any(), "duplicate ledger key — grain violated"
        write_table("fact_roster_transactions", out)
        by_type = txn_fact["event_type"].value_counts().to_dict()
        print(f"[ok] transaction events: +{len(txn_fact)} {by_type} "
              f"(replaced {_stale} prior txn row(s); {len(out)} total ledger rows)")
        print(f"[info] transaction contracts: "
              f"{txn_fact['contract_id'].value_counts(dropna=False).to_dict()} "
              f"({txn_sourcing['observed']} leg(s) read off Roster State, "
              f"{txn_sourcing['preseason']} off the preseason capture)")
        claims = txn_fact[txn_fact["event_type"] == CLAIM_EVENT]
        print(f"[info] claim_method: "
              f"{claims['claim_method'].value_counts(dropna=False).to_dict()} on claims, "
              f"{txn_fact.loc[txn_fact['event_type'] == DROP_EVENT, 'claim_method'].value_counts(dropna=False).to_dict()} "
              f"on drops")
        print(f"[info] contract_source, all rows: "
              f"{out['contract_source'].value_counts(dropna=False).to_dict()}")
        stintless = txn_fact[txn_fact["contract_source"] == NO_STINT]
        if len(stintless):
            print(f"[warn] {len(stintless)} drop(s) end no stint on the ledger "
                  f"(contract_source = {NO_STINT}; no Dead Money): "
                  f"{list(zip(stintless['team_key'], stintless['scorer_id']))[:5]}"
                  f"{'...' if len(stintless) > 5 else ''}")
        unknown = unknown_contracts(pd.concat([fact, txn_fact]), contracts)
        if unknown:
            print(f"[warn] contract(s) observed on Roster State but absent from dim_contract "
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
               .agg(picks=("asset_id", "size"), contract_committed=("contract_value", "sum"))
               .sort_values("team_key"))
    print(by_team.to_string())
    print("\nsample rows:")
    show = ["team_key", "draft_round", "pick_in_round", "pick_overall", "scorer_id",
            "asset_id", "contract_value", "event_date"]
    print(fact.sort_values("pick_overall").head(8)[show].to_string(index=False))


if __name__ == "__main__":
    _args = parse_args()
    if _args.raw_dir is not None:
        use_raw_dir(_args.raw_dir)
    main()

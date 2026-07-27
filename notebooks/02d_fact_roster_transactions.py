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
#   Key `season_id + event_type + team_key + asset_id + event_seq`. Each pick →
#   an **Initial** contract (yr 1): `contract_value` = the Fantrax `salary`
#   as-of the capture; `cap_hit` = `dim_contract.cap_hit_pct` × value (0.50).
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
# `salary` via the latest `fact_fantrax_adp` snapshot (04a).
#
# **Run:**  python notebooks/02d_fact_roster_transactions.py

# %%
import sys
import json
import glob
import re
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
import etl_helpers as etl
from etl_helpers import CFG, DATA, TODAY, load_replace_partition

SEASON_ID   = f"{CFG.draft_year}-{CFG.draft_year + 1}"   # "2026-2027"
EVENT_TYPE  = "startup_draft"
CONTRACT_ID = "1st"
STATUS      = "active"
SOURCE      = "getDraftResults"

FACT_PATH  = DATA / "fact_roster_transactions.parquet"
ASSET_PATH = DATA / "dim_roster_asset.parquet"
PICK_PATH  = DATA / "fact_draft_pick.parquet"
ASSET_COLS = ["asset_id", "asset_type", "scorer_id", "gsis_id", "player_key", "pick_ref"]


# %%
# ---- Load + merge all captured divisions -----------------------------------
def load_draft():
    """Return (picks_df, teams: {teamId->(name,div)}, scorers: {sid->detail}).

    Globs every `fantrax_draftresults_2026*.json` — covers the legacy no-suffix
    file AND the per-division files 04w now writes. Picks are deduped on
    `(divisionId, round, pickNumber)` keeping the latest capture, so the old and
    new Riddell files don't double-count."""
    files = sorted(glob.glob(str(DATA / "raw" / "fantrax_draftresults_2026*.json")),
                   key=lambda f: Path(f).stat().st_mtime)
    if not files:
        raise FileNotFoundError("No draft-results capture found -- run 04w first.")
    print(f"[info] division files (oldest first): {[Path(f).name for f in files]}")

    pick_rows, teams, scorers = [], {}, {}
    for f in files:
        d0 = json.loads(Path(f).read_text(encoding="utf-8"))["responses"][0]["data"]
        divmap = {x["id"]: x["name"].strip() for x in d0["divisions"]}
        for t in d0["fantasyTeamsOrdered"]:
            teams[t["id"]] = (t["name"], divmap.get(d0["selectedDivisionId"]))
        for s in d0["scorers"]:
            scorers[s["scorerId"]] = s
        pick_rows.extend(d0["draftPicksOrdered"])

    picks = pd.DataFrame(pick_rows)
    picks = picks.drop_duplicates(
        subset=["divisionId", "round", "pickNumber"], keep="last").reset_index(drop=True)
    # canonical snake order: pickNumber already encodes within-round snake order,
    # so overall_slot is linear in (round, pickNumber). N = teams per division.
    n_by_div = picks.groupby("divisionId")["pickNumber"].transform("max")
    picks["overall_slot"] = (picks["round"] - 1) * n_by_div + picks["pickNumber"]
    print(f"[info] {len(picks)} pick slots across {picks['divisionId'].nunique()} division(s); "
          f"{picks['scorerId'].notna().sum()} made")
    return picks, teams, scorers


picks, teams, scorers = load_draft()


# %%
# ---- Identity + value lookups ----------------------------------------------
teams_dim = pd.read_parquet(DATA / "dim_fantasy_teams.parquet")
team_lut = dict(zip(teams_dim["fantrax_team_id"], teams_dim["team_key"]))

px = pd.read_parquet(DATA / "dim_fantrax_crosswalk.parquet")
gsis_lut = dict(zip(px["scorer_id"], px["gsis_id"]))
pkey_lut = dict(zip(px["scorer_id"], px["player_key"]))

adp = pd.read_parquet(DATA / "fact_fantrax_adp.parquet")
adp_latest = adp.sort_values("capture_date").drop_duplicates("scorer_id", keep="last")
salary_lut = dict(zip(adp_latest["scorer_id"], adp_latest["salary"]))

contracts = pd.read_parquet(DATA / "dim_contract.parquet")
cap_hit_pct = float(contracts.loc[contracts["contract_id"] == CONTRACT_ID, "cap_hit_pct"].iloc[0])
print(f"[info] contract '{CONTRACT_ID}' cap_hit_pct = {cap_hit_pct}")

# Every made pick must resolve to a team (captured divisions only) and a player.
made = picks[picks["scorerId"].notna()].copy()
unmapped_teams = sorted(set(made["teamId"]) - set(team_lut))
if unmapped_teams:
    raise RuntimeError(
        f"teamIds absent from dim_fantasy_teams.fantrax_team_id (refresh 01c "
        f"from the Sheet's Fantrax-TeamId column): {unmapped_teams}")


# %%
# ---- dim_roster_asset: persist + mint (monotonic, never re-derived) --------
def _atype(g, p):
    if pd.notna(g):  return "player"      # signed NFL player (gsis_id resolved)
    if pd.notna(p):  return "prospect"    # unsigned prospect (player_key only)
    return "player"                        # default; resolvers backfill later


def mint_assets(scorer_ids):
    existing = pd.read_parquet(ASSET_PATH) if ASSET_PATH.exists() else pd.DataFrame(columns=ASSET_COLS)
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


dim_roster_asset, sid2aid = mint_assets(sorted(made["scorerId"].unique()))
dim_roster_asset.to_parquet(ASSET_PATH, index=False)
print(f"[ok] dim_roster_asset: {len(dim_roster_asset)} assets "
      f"({(dim_roster_asset['asset_type']=='player').sum()} player, "
      f"{(dim_roster_asset['asset_type']=='prospect').sum()} prospect) -> {ASSET_PATH.name}")


# %%
# ---- fact_draft_pick: 2026 startup grid (all slots) -------------------------
# getDraftResults gives each slot's CURRENT owner (who picks there now). Startup
# picks WERE traded (some teams hold 2 picks in a round, others 0), so the
# current owner != original owner for traded slots. Fantrax's API carries no
# pre-trade allocation field at all (confirmed by direct inspection -- no
# `originalTeamId`/`tradedFrom` anywhere in getDraftResults/getFantasyLeagueInfo/
# getRefObject) -- so `original_owner` is INFERRED from the draft's own round 1:
# round-1 slot assignment defines the draft order by construction, and a snake
# expansion of that order reconstructs every later round's pre-trade owner. The
# unique slot identity is (draft_season, divisionId, overall_slot).
dp = picks.copy()
dp["draft_season"]  = SEASON_ID
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

dim_draft_pick = dp[
    ["pick_ref", "draft_season", "divisionId", "round", "pick_in_round",
     "overall_slot", "current_owner", "original_owner", "is_made", "draft_type"]
].sort_values(["divisionId", "overall_slot"]).reset_index(drop=True)
assert not dim_draft_pick.duplicated(["draft_season", "divisionId", "overall_slot"]).any()
assert dim_draft_pick["pick_ref"].is_unique
assert dim_draft_pick["original_owner"].notna().all(), "original_owner inference left gaps"
load_replace_partition(dim_draft_pick, PICK_PATH, part_cols=("draft_season",))
print(f"[ok] fact_draft_pick: {len(dim_draft_pick)} slots ({SEASON_ID}, "
      f"{int(dim_draft_pick['is_made'].sum())} made) -> {PICK_PATH.name}")


# %%
# ---- fact_roster_transactions: one startup_draft row per made pick ---------
def _epoch_ms_to_date(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date() if pd.notna(ms) else pd.NaT


fact_rows = []
for _, p in made.iterrows():
    sid = p["scorerId"]
    val = salary_lut.get(sid)
    val = float(val) if pd.notna(val) else pd.NA
    fact_rows.append({
        "season_id":      SEASON_ID,
        "event_type":     EVENT_TYPE,
        "team_key":       team_lut[p["teamId"]],
        "asset_id":       sid2aid[sid],
        "event_seq":      int(p["overall_slot"]),
        "event_date":     _epoch_ms_to_date(p["modifiedDate"]),
        "contract_id":    CONTRACT_ID,
        "contract_year":  1,
        "contract_value": val,
        "cap_hit":        (val * cap_hit_pct) if pd.notna(val) else pd.NA,
        "dead_money":     0,
        "status":         STATUS,
        "scorer_id":      sid,
        "gsis_id":        gsis_lut.get(sid),
        "draft_round":    int(p["round"]),
        "pick_in_round":  int(p["pickNumber"]),
        "pick_overall":   int(p["overall_slot"]),
        "source":         SOURCE,
    })

fact = pd.DataFrame(fact_rows)
fact["event_date"] = pd.to_datetime(fact["event_date"])
# key integrity: the ADR grain must be unique.
key = ["season_id", "event_type", "team_key", "asset_id", "event_seq"]
assert not fact.duplicated(key).any(), "duplicate ledger key — grain violated"
total = load_replace_partition(fact, FACT_PATH, part_cols=("season_id", "event_type"))
print(f"[ok] fact_roster_transactions: +{len(fact)} {EVENT_TYPE} rows "
      f"({total} total) -> {FACT_PATH.name}")


# %%
# ---- Asset bridge extension from roster placement --------------------------
# Placement (04v) can carry roster copies the startup draft never saw — a
# player added off free agency after the draft still shows up in a weekly
# snapshot. Mint asset_ids for them so the bridge covers every scorer the
# ledger might later reference (a trade/claim leg for an unminted scorer would
# KeyError downstream).
#
# This block used to ALSO derive `minor_assignment`/`minor_graduation` events
# from per-copy contract transitions. That was removed (ADR-0011): there is no
# Minor contract type, so the transition it watched for could never occur — the
# function emitted zero rows for its entire life. Minors is placement +
# eligibility; placement reaches the cap via 02e's `roster_status` stamp, not
# via ledger events. Do not reintroduce this without a contract type to hang it
# on.
PLACEMENT_PATH = DATA / "fact_roster_placement.parquet"

if PLACEMENT_PATH.exists():
    placement = pd.read_parquet(PLACEMENT_PATH)
    dim_roster_asset, sid2aid = mint_assets(sorted(placement["scorer_id"].unique()))
    dim_roster_asset.to_parquet(ASSET_PATH, index=False)
    print(f"[ok] asset bridge extended from placement: {len(dim_roster_asset)} assets "
          f"-> {ASSET_PATH.name}")
else:
    print("[info] fact_roster_placement not built yet (run 04v) — asset bridge "
          "covers drafted copies only")


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
TXN_GLOB       = str(DATA / "raw" / "fantrax_txn_history_*.json")
TRADE_LOG_PATH = DATA / "fact_trade_log.parquet"
TRADE_SOURCE   = "getTransactionDetailsHistory"
TXN_SEQ_BASE   = 100_000
TRADE_AWAY     = "trade_away"
TRADE_IN       = "trade"
CLAIM_EVENT    = "claim"
DROP_EVENT     = "drop"
TXN_EVENT_TYPES = (TRADE_AWAY, TRADE_IN, CLAIM_EVENT, DROP_EVENT)
FA_CONTRACT_ID = "FA"

_HTML_TAG   = re.compile(r"<[^>]+>")
_PICK_OWNER = re.compile(r"\((.*)\)\s*$")

conf_lut = dict(zip(teams_dim["team_key"], teams_dim["conference"]))

season_dim    = pd.read_parquet(DATA / "dim_season.parquet")
_SEASON_SPANS = [(pd.Timestamp(r.season_fantasy_start_date),
                  pd.Timestamp(r.season_fantasy_end_date), r.season_id)
                 for r in season_dim.itertuples()]


def _strip_html(s: str) -> str:
    return _HTML_TAG.sub("", s or "").strip()


def load_txn_rows() -> list[dict]:
    files = sorted(glob.glob(TXN_GLOB), key=lambda f: Path(f).stat().st_mtime)
    if not files:
        print("[info] no transaction-history capture found (run 04t) -- skipping txn events")
        return []
    rows = []
    for f in files:
        for pg in json.loads(Path(f).read_text(encoding="utf-8")):
            rows.extend(pg["responses"][0]["data"]["table"]["rows"])
    return rows


def _season_id_for(dt):
    """Event datetime -> league season_id, read straight off dim_season's own
    fantasy-year span (2026-03-01..2027-02-28). Replaces an earlier month>=8
    heuristic that mis-filed the June/July startup-era trades under
    "2025-2026" -- a season that doesn't exist in dim_season at all."""
    if pd.isna(dt):
        return pd.NA
    d = pd.Timestamp(dt).normalize()
    for start, end, sid in _SEASON_SPANS:
        if start <= d <= end:
            return sid
    return pd.NA


raw_txn_rows = load_txn_rows()
trade_rows   = [r for r in raw_txn_rows if r.get("transactionCode") is None]
cd_rows      = [r for r in raw_txn_rows if r.get("transactionCode") in ("CLAIM", "DROP")]
if raw_txn_rows:
    print(f"[info] captured txn rows: {len(trade_rows)} trade leg(s), "
          f"{len(cd_rows)} claim/drop row(s)")

legs = []   # one entry per player-asset transaction leg, resolved chronologically below

if trade_rows:
    last_date = {}   # date is only stamped on the first row of each txSetId
                     # group (HTML rowspan) -- carry it forward within the group.
    trade_log_rows = []
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

    trade_log = pd.DataFrame(trade_log_rows)
    n_unmapped = int((trade_log["team_key_from"].isna() | trade_log["team_key_to"].isna()).sum())
    if n_unmapped:
        print(f"[warn] {n_unmapped} trade_log row(s) have an unmapped team "
              f"(fantrax_team_id missing from dim_fantasy_teams) -- left NA")
    trade_log.to_parquet(TRADE_LOG_PATH, index=False)
    print(f"[ok] fact_trade_log: {len(trade_log)} asset row(s) across "
          f"{trade_log['transaction_id'].nunique()} trade(s) -> {TRADE_LOG_PATH.name}")


# %%
# ---- Claim / Drop legs -----------------------------------------------------
# Same HTML-rowspan shape as trades: only the FIRST row of a txSetId group
# carries the `team`/`date` cells, and a paired DROP inherits both from the
# CLAIM above it. Rows with no `scorer` block (or an unmapped team) can't be
# posted to an asset-keyed ledger, so they're counted and skipped.
if cd_rows:
    last_cd_team, last_cd_date = {}, {}
    n_no_player = n_no_team = 0
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
    if n_no_player or n_no_team:
        print(f"[warn] skipped {n_no_player} claim/drop row(s) with no scorer and "
              f"{n_no_team} with an unmapped team")


# %%
# ---- Resolve every transaction leg chronologically -> ledger rows ----------
if legs:
    # Same-timestamp tiebreak: a drop frees the roster spot the paired claim
    # fills, and a trade_away precedes the claim of anyone it displaced.
    _KIND_ORDER = {DROP_EVENT: 0, TRADE_IN: 1, CLAIM_EVENT: 2}
    legs.sort(key=lambda l: (pd.Timestamp.min if pd.isna(l["event_dt"]) else l["event_dt"],
                             _KIND_ORDER[l["kind"]]))

    dim_roster_asset, sid2aid = mint_assets(sorted({l["scorer_id"] for l in legs}))
    dim_roster_asset.to_parquet(ASSET_PATH, index=False)

    # League-minimum FA fallback, straight off dim_contract's own "FA" row.
    # cap_hit mirrors contract_value: dim_contract.cap_hit_pct prices a CUT
    # (dead money), it is NOT a discount on a kept player's charge.
    #
    # Known gap, deliberately NOT patched: a claim whose player was dropped
    # BEFORE 04t's capture window (04t only starts 2026-07-19) has no ledger
    # history, so it lands here and gets the league minimum even if the player
    # actually carried a real contract. The proposed backstop was Fantrax's
    # public `getTeamRosters?leagueId=...&period=N`, which the developer docs
    # describe as serving historical per-period roster state.
    #
    # PROBED LIVE 2026-07-26 -- it does not. Across period=1/2/5/17/99 the only
    # field that changes is the echoed `period` itself: identical roster
    # membership, contract, salary and status every time (1031 items, zero
    # diffs), and period 17 == 99, so it clamps rather than erroring. It serves
    # CURRENT state regardless of the parameter.
    #
    # Wiring it would be strictly worse than this fallback, not just useless:
    # for the exact case it is meant to serve -- a claim with no ledger history
    # -- the player's current contract IS the one that claim produced, so the
    # lookup would circularly hand back its own answer and write a confidently
    # wrong contract instead of an honestly conservative minimum.
    #
    # Re-probe once real in-season periods exist (the league is still entirely
    # inside preseason period 1, so there is no historical state for Fantrax to
    # serve yet). If period ever returns genuinely distinct rosters, this
    # becomes viable; until then the league minimum is the correct answer.
    _fa       = contracts.loc[contracts["contract_id"] == FA_CONTRACT_ID].iloc[0]
    _fa_value = float(_fa["min_salary"])
    FA_TERMS  = dict(contract_id=FA_CONTRACT_ID, contract_year=1,
                     contract_value=_fa_value, cap_hit=_fa_value, status="active")

    # Seed contract state from the NON-transaction ledger (startup_draft rows),
    # then walk the transaction stream forward, updating state as
    # we go -- so a chained trade, or a drop-then-reclaim on the same day,
    # resolves against what was actually true at that moment.
    _TERM_COLS = ["contract_id", "contract_year", "contract_value", "cap_hit", "status"]
    base = pd.read_parquet(FACT_PATH)
    base = base[~base["event_type"].isin(TXN_EVENT_TYPES)].sort_values("event_seq")
    copy_terms, conf_terms = {}, {}      # (team_key, asset_id) / (conference, asset_id)
    for r in base.itertuples():
        t = {c: getattr(r, c) for c in _TERM_COLS}
        copy_terms[(r.team_key, r.asset_id)] = t
        conf_terms[(conf_lut.get(r.team_key), r.asset_id)] = (t, r.season_id)

    txn_fact_rows, missing_source, fa_fallback = [], [], []
    for i, l in enumerate(legs):
        aid, kind = sid2aid[l["scorer_id"]], l["kind"]
        team, season = l["team_to"], _season_id_for(l["event_dt"])
        conf = conf_lut.get(team)
        prior = conf_terms.get((conf, aid))

        if kind == TRADE_IN:
            terms = copy_terms.get((l["team_from"], aid)) or (prior[0] if prior else None)
            if terms is None:
                missing_source.append((l["team_from"], l["scorer_id"]))
                terms = dict(contract_id=pd.NA, contract_year=pd.NA, contract_value=pd.NA,
                             cap_hit=pd.NA, status="active")
        else:
            # Only a contract held THIS season carries over ("retain salary and
            # contract for the season"); anything older resets to league minimum.
            terms = prior[0] if (prior and prior[1] == season) else None
            if terms is None and kind == DROP_EVENT:
                terms = copy_terms.get((team, aid))
            if terms is None:
                terms = FA_TERMS
                if kind == CLAIM_EVENT:
                    fa_fallback.append(l["scorer_id"])

        seq = TXN_SEQ_BASE + i
        common = dict(season_id=season, **terms, dead_money=0, scorer_id=l["scorer_id"],
                      gsis_id=gsis_lut.get(l["scorer_id"]), draft_round=pd.NA,
                      pick_in_round=pd.NA, pick_overall=pd.NA, source=TRADE_SOURCE)
        if kind == TRADE_IN:
            txn_fact_rows.append({**common, "event_type": TRADE_AWAY, "team_key": l["team_from"],
                                  "asset_id": aid, "event_seq": seq, "event_date": l["event_dt"]})
            txn_fact_rows.append({**common, "event_type": TRADE_IN, "team_key": team,
                                  "asset_id": aid, "event_seq": seq, "event_date": l["event_dt"]})
            copy_terms.pop((l["team_from"], aid), None)
            copy_terms[(team, aid)] = terms
        else:
            txn_fact_rows.append({**common, "event_type": kind, "team_key": team,
                                  "asset_id": aid, "event_seq": seq, "event_date": l["event_dt"]})
            if kind == CLAIM_EVENT:
                copy_terms[(team, aid)] = terms
            else:
                copy_terms.pop((team, aid), None)
        conf_terms[(conf, aid)] = (terms, season)

    if missing_source:
        print(f"[warn] {len(missing_source)} traded player(s) had no prior ledger row on "
              f"their 'from' team -- contract fields left NA for those legs: "
              f"{missing_source[:5]}{'...' if len(missing_source) > 5 else ''}")
    if fa_fallback:
        print(f"[info] {len(fa_fallback)} claim(s) had no in-season contract history -- "
              f"assigned the league-minimum '{FA_CONTRACT_ID}' contract "
              f"(${_fa_value:,.0f})")

    txn_fact = pd.DataFrame(txn_fact_rows)[fact.columns]
    txn_fact["event_date"] = pd.to_datetime(txn_fact["event_date"])
    assert txn_fact["season_id"].notna().all(), "event_date outside every dim_season span"
    assert not txn_fact.duplicated(key).any(), "duplicate transaction-event ledger key"

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
elif raw_txn_rows:
    print("[info] no player-asset transaction legs to add (pick-only trades, or all unmapped)")
else:
    print("[info] no captured transaction history -- skipping transaction events entirely")


# %%
# ---- Summary ---------------------------------------------------------------
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

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
# - **`dim_draft_pick`** — the 2026 startup pick grid (every slot, made or not).
#   Keyed on the slot: `pick_ref = (draft_season, divisionId, overall_slot)`.
#   Records `current_owner` (getDraftResults `teamId`, post-trade); `original_owner`
#   is NULL until `draftPicks.go` is captured (startup picks were traded — see the
#   dim_draft_pick cell below). `overall_slot` = snake order `(round-1)*N + pick_in_round`.
# - **`fact_roster_transactions`** — one `startup_draft` row per **made** pick.
#   Key `season_id + event_type + team_key + asset_id + event_seq`. Each pick →
#   an **Initial** contract (yr 1): `contract_value` = the Fantrax `salary`
#   as-of the capture; `cap_hit` = `dim_contract.cap_hit_pct` × value (0.50).
#   PLUS the Yo-Yo Rule contract-state events `minor_assignment` /
#   `minor_graduation`, derived from observed per-copy contract transitions in
#   the weekly `fact_roster_placement` snapshots (04v) — see that section below.
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
PICK_PATH  = DATA / "dim_draft_pick.parquet"
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
# ---- dim_draft_pick: 2026 startup grid (all slots) -------------------------
# getDraftResults gives each slot's CURRENT owner (who picks there now). Startup
# picks WERE traded (some teams hold 2 picks in a round, others 0), so the
# current owner != original owner for traded slots. ADR-0004's
# pick_ref=(draft_season, round, original_owner) needs the pre-trade allocation
# from `draftPicks.go`, which isn't captured yet -> `original_owner` is left null
# (backfilled when draftPicks.go lands; that also feeds `pick_allocation`/`trade`
# events, dormant in v1). The unique slot identity we DO have is
# (draft_season, divisionId, overall_slot).
dp = picks.copy()
dp["draft_season"]   = SEASON_ID
dp["current_owner"]  = dp["teamId"].map(team_lut)
dp["original_owner"] = pd.NA                      # deferred: needs draftPicks.go
dp["is_made"]        = dp["scorerId"].notna()
dp["pick_ref"]       = (dp["draft_season"] + "|" + dp["divisionId"]
                        + "|S" + dp["overall_slot"].astype(int).map("{:03d}".format))
dim_draft_pick = dp.rename(columns={"pickNumber": "pick_in_round"})[
    ["pick_ref", "draft_season", "divisionId", "round", "pick_in_round",
     "overall_slot", "current_owner", "original_owner", "is_made"]
].sort_values(["divisionId", "overall_slot"]).reset_index(drop=True)
assert not dim_draft_pick.duplicated(["draft_season", "divisionId", "overall_slot"]).any()
assert dim_draft_pick["pick_ref"].is_unique
load_replace_partition(dim_draft_pick, PICK_PATH, part_cols=("draft_season",))
print(f"[ok] dim_draft_pick: {len(dim_draft_pick)} slots ({SEASON_ID}, "
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
# ---- Yo-Yo Rule: minor_assignment / minor_graduation events -----------------
# Derived from OBSERVED per-copy contract transitions across the weekly
# fact_roster_placement snapshots (04v): the ledger records what the site
# actually shows, dated at the capture where the new state first appears —
# not the worklist's intent. Contract is per roster copy (team x scorer), so
# events are per copy too. Rebuilt from the full snapshot history every run
# and loaded replace-by-(season_id, event_type) -> idempotent.
#
# event_seq = MINOR_SEQ_BASE + snapshot ordinal. MINOR_SEQ_BASE (1000) clears
# every startup overall_slot (max 490), so 02e's last-event-wins replay always
# ranks a Minor flip after the copy's startup_draft acquisition.
PLACEMENT_PATH = DATA / "fact_roster_placement.parquet"
MINOR_ID       = "Minor"
MINOR_SEQ_BASE = 1000
MINOR_SOURCE   = "fact_roster_placement"


def _week_ord(week) -> int:
    """'PRE' -> 0, '01'..'18' -> 1..18 (snapshot order within a season)."""
    return 0 if str(week) == "PRE" else int(week)


def derive_minor_events(placement: pd.DataFrame, sid2aid: dict,
                        cap_pct_by_contract: dict) -> pd.DataFrame:
    """Walk each roster copy's snapshot history in capture order and emit:
      - minor_assignment: contract becomes Minor (from anything else, or the
        copy's first appearance already holding Minor)
      - minor_graduation: contract leaves Minor (crossed 20 GP; typically 1st)
    A copy vanishing from snapshots while Minor is a DROP — out of scope until
    the drop event type exists (tracked in PLAN.md dead-money work)."""
    p = placement.copy()
    p["week_ord"] = p["week"].map(_week_ord)
    p["snap_seq"] = (p["season"] - CFG.draft_year) * 100 + p["week_ord"]
    events = []
    for (team, sid), g in p.sort_values("snap_seq").groupby(["team_key", "scorer_id"]):
        prev = None   # contract in the prior snapshot; None = copy absent
        for r in g.itertuples():
            evt = None
            if r.contract == MINOR_ID and prev != MINOR_ID:
                evt = ("minor_assignment", MINOR_ID)
            elif prev == MINOR_ID and r.contract and r.contract != MINOR_ID:
                evt = ("minor_graduation", r.contract)
            if evt:
                etype, cid = evt
                val = float(r.salary) if pd.notna(r.salary) else pd.NA
                pct = float(cap_pct_by_contract.get(cid, 0))
                events.append({
                    "season_id":      f"{r.season}-{r.season + 1}",
                    "event_type":     etype,
                    "team_key":       team,
                    "asset_id":       sid2aid[sid],
                    "event_seq":      MINOR_SEQ_BASE + int(r.snap_seq),
                    "event_date":     pd.to_datetime(r.capture_date),
                    "contract_id":    cid,
                    "contract_year":  1,   # graduation starts the 3-yr clock; Minor is a 1-yr rolling term
                    "contract_value": val,
                    "cap_hit":        (val * pct) if pd.notna(val) else pd.NA,
                    "dead_money":     0,
                    "status":         STATUS,
                    "scorer_id":      sid,
                    "gsis_id":        r.gsis_id,
                    "draft_round":    pd.NA,
                    "pick_in_round":  pd.NA,
                    "pick_overall":   pd.NA,
                    "source":         MINOR_SOURCE,
                })
            prev = r.contract
    return pd.DataFrame(events, columns=fact.columns)


if PLACEMENT_PATH.exists():
    placement = pd.read_parquet(PLACEMENT_PATH)
    # Placement can carry copies the draft never saw (post-draft FA minors) —
    # extend the asset bridge before deriving events.
    dim_roster_asset, sid2aid = mint_assets(sorted(placement["scorer_id"].unique()))
    dim_roster_asset.to_parquet(ASSET_PATH, index=False)
    cap_pct = dict(zip(contracts["contract_id"], contracts["cap_hit_pct"]))
    minor_events = derive_minor_events(placement, sid2aid, cap_pct)
    if len(minor_events):
        assert not minor_events.duplicated(key).any(), "duplicate minor-event key"
        total = load_replace_partition(minor_events, FACT_PATH,
                                       part_cols=("season_id", "event_type"))
        by_type = minor_events["event_type"].value_counts().to_dict()
        print(f"[ok] minor events: +{len(minor_events)} {by_type} ({total} total ledger rows)")
    else:
        print("[info] no minor contract transitions observed in placement history yet")
else:
    print("[info] fact_roster_placement not built yet (run 04v) — skipping minor events")


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

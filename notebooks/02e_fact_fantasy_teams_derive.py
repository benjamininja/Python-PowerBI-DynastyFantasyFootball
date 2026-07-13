# %% [markdown]
# # 02e_fact_fantasy_teams_derive  (ledger replay -> current roster)
#
# **Purpose:** Derive the current-roster fact `fact_fantasy_teams` from the
# event-sourced `fact_roster_transactions` ledger (ADR-0003: the ledger is the
# SSOT; this fact is a *replay projection*, never scraped independently).
# `fact_fantasy_teams` is the only location for contract/salary/cap-hit data --
# it no longer rolls cap totals up into `dim_fantasy_teams`. Consumers compute
# active-roster-salary/remaining-cap live from this fact instead of reading a
# cached snapshot: Power BI via the DAX measures in `_Measures.tmdl`
# ('Active Roster Salary', 'Remaining Salary Cap'), the Discord bot via
# `discord_bot/capmath.py`. Same formula, computed where it's consumed.
#
# **Replay rule:** order events by `event_seq`; the **last** event per
# `(team_key, asset_id)` defines that player's current contract. Terminal `drop`
# events remove the player from the active roster. v1 has only `startup_draft`
# events (all active), so this is one active row per drafted player — but the
# logic is written general so `resign`/`fa_*`/`drop` slot in without change.
#
# **Output schema:** team_key, gsis_id, player_key, contract_id, contract_value,
# contract_year, status, acquired_method, roster_status, season.
# `dead_money` is NOT stored (dropped 2026-07-13): it's computed from
# status/Dim_Contract (Cut + Guaranteed -> contract_value x cap_hit_pct)
# wherever it's consumed, like cap_hit before it.
# `roster_status` (added 2026-07-13) is OBSERVED state stamped from the latest
# `fact_roster_placement` snapshot — Minors placement is cap-exempt downstream.
# `conference` and
# `cap_hit` are NOT stored (removed 2026-07-11) -- both are 100% derivable
# (`TeamKey`->`Dim_FantasyTeams`; a kept player's charge is the full
# ContractValue), so caching them here just duplicated that math a second time.
# Power BI derives them live (`_Measures.tmdl` 'Active Roster Salary' =
# SUM(ContractValue), current season, RosterStatus <> "Minors"); the bot's
# `discord_bot/capmath.py` applies the same rule in pandas. CapHitPct on
# Dim_Contract is dead-money-only (prices a CUT, never a kept player).
#
# **Run:**  python notebooks/02e_fact_fantasy_teams_derive.py
#   (after 02d; re-run during the live draft to refresh roster state.)

# %%
import sys
from pathlib import Path

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
import etl_helpers as etl
from etl_helpers import CFG, DATA

LEDGER_PATH    = DATA / "fact_roster_transactions.parquet"
FFT_PATH       = DATA / "fact_fantasy_teams.parquet"
TEAMS_PATH     = DATA / "dim_fantasy_teams.parquet"
PLACEMENT_PATH = DATA / "fact_roster_placement.parquet"

TERMINAL = {"drop"}   # event_types that REMOVE a player from the active roster

# %%
# ---- Replay the ledger -> latest contract per (team_key, asset_id) ---------
ledger = pd.read_parquet(LEDGER_PATH)
assets = pd.read_parquet(DATA / "dim_roster_asset.parquet")
teams  = pd.read_parquet(TEAMS_PATH)
print(f"[info] ledger: {len(ledger)} events, {ledger['event_type'].nunique()} type(s)")

# last event wins per player+team (event_seq = canonical order: startup slots
# 1..490, then minor_assignment/minor_graduation at 1000+snapshot ordinal).
latest = (ledger.sort_values("event_seq")
          .drop_duplicates(["team_key", "asset_id"], keep="last"))
active = latest[~latest["event_type"].isin(TERMINAL)].copy()

# acquired_method = the copy's FIRST event (how the player arrived), not the
# last — contract-state events (minor_*) update the contract columns via
# last-event-wins above but must not masquerade as an acquisition method.
first = (ledger.sort_values("event_seq")
         .drop_duplicates(["team_key", "asset_id"], keep="first")
         .rename(columns={"event_type": "acquired_method"})
         [["team_key", "asset_id", "acquired_method"]])
active = active.merge(first, on=["team_key", "asset_id"], how="left")

# roster_status: OBSERVED squad placement (Active/Reserve/Minors) stamped from
# the latest fact_roster_placement snapshot (04v), keyed exactly on
# (team_key, scorer_id) — the ledger rows carry scorer_id, no gsis fallback
# needed. Not a derived rollup (allowed to live on the fact): cap exemption
# follows Minors PLACEMENT, not Minor contract type, so consumers (capmath,
# PBI measures) exclude roster_status == "Minors" salaries from the charge.
# Null = not in the latest snapshot (e.g. before 04v's first run) -> charged,
# the safe default.
if PLACEMENT_PATH.exists():
    _pl = pd.read_parquet(PLACEMENT_PATH)
    _pl = _pl[_pl["capture_date"] == _pl["capture_date"].max()]
    _pl = (_pl[["team_key", "scorer_id", "roster_section"]]
           .rename(columns={"roster_section": "roster_status"})
           .drop_duplicates(subset=["team_key", "scorer_id"]))
    active = active.merge(_pl, on=["team_key", "scorer_id"], how="left")
    n_minor = (active["roster_status"] == "Minors").sum()
    print(f"[info] roster_status stamped from placement snapshot "
          f"({_pl.shape[0]} placement rows; {n_minor} Minors-placed, cap-exempt)")
    # Reverse check: placement rows with no matching active ledger row are
    # observed ownership the ledger doesn't know about (e.g. an on-site trade —
    # no trade event type exists yet). Surface them; the ledger side of such a
    # pair keeps roster_status null and is charged (safe default).
    _led_keys = set(zip(active["team_key"], active["scorer_id"]))
    _orphans = _pl[[k not in _led_keys
                    for k in zip(_pl["team_key"], _pl["scorer_id"])]]
    if len(_orphans):
        print(f"[warn] {len(_orphans)} placement row(s) have no active ledger "
              f"row for that (team, scorer) — ledger gap (trade/FA move not in "
              f"ledger?). Examples:")
        print(_orphans.head(8).to_string(index=False))
else:
    active["roster_status"] = pd.NA
    print("[warn] no fact_roster_placement.parquet — roster_status all null "
          "(every salary charged)")

# resolve asset_id -> gsis_id / player_key via the polymorphic bridge.
res = assets.set_index("asset_id")[["gsis_id", "player_key"]]
active = active.merge(res, on="asset_id", how="left", suffixes=("", "_asset"))
# prefer the ledger snapshot's gsis_id; fall back to the asset's current resolver.
active["gsis_id"] = active["gsis_id"].fillna(active["gsis_id_asset"])

fact_fantasy_teams = pd.DataFrame({
    "team_key":       active["team_key"],
    "gsis_id":        active["gsis_id"],
    "player_key":     active["player_key"],
    "contract_id":    active["contract_id"],
    "contract_value": active["contract_value"],
    "contract_year":  active["contract_year"],
    "status":         active["status"],
    "acquired_method": active["acquired_method"],
    "roster_status":  active["roster_status"],
    "season":         active["season_id"],
}).reset_index(drop=True)

fact_fantasy_teams.to_parquet(FFT_PATH, index=False)
print(f"[ok] fact_fantasy_teams: {len(fact_fantasy_teams)} active roster rows -> {FFT_PATH.name}")

# %%
# ---- Summary -----------------------------------------------------------------
# Live-computed for display only -- not persisted. A KEPT player's cap charge
# is the FULL contract_value: cap_hit_pct on dim_contract is DEAD-MONEY-ONLY
# (what's owed if you CUT the player) — same rule as the DAX 'Active Roster
# Salary' comment and capmath.roster_with_cap_hit (2026-07-13 audit fix: this
# summary used to multiply by cap_hit_pct, a 2x understatement that also
# silently zero-charged Minor-CONTRACT players kept active).
fact_fantasy_teams["cap_hit"] = fact_fantasy_teams["contract_value"]
# Minors-squad PLACEMENT is the only cap exemption (roster_status == "Minors");
# null roster_status charges — same rule as capmath / DAX.
fact_fantasy_teams.loc[
    fact_fantasy_teams["roster_status"] == "Minors", "cap_hit"] = 0.0
# dead_money is COMPUTED, not stored (column dropped 2026-07-13, same
# stale-under-filter defect that killed the stored cap_hit): only players
# actually Cut on a Guaranteed contract price in, at contract_value x
# cap_hit_pct — mirrors DAX 'Dead Money - Active - Current Year' and
# capmath.teams_with_cap.
contracts = pd.read_parquet(DATA / "dim_contract.parquet")
_pct = dict(zip(contracts["contract_id"], contracts["cap_hit_pct"]))
_gtd = dict(zip(contracts["contract_id"], contracts["guaranteed"]))
_is_dead = (fact_fantasy_teams["status"].eq("Cut")
            & fact_fantasy_teams["contract_id"].map(_gtd).fillna(False).astype(bool))
fact_fantasy_teams["dead_money"] = 0.0
fact_fantasy_teams.loc[_is_dead, "dead_money"] = (
    fact_fantasy_teams.loc[_is_dead, "contract_value"]
    * fact_fantasy_teams.loc[_is_dead, "contract_id"].map(_pct))
roll = (fact_fantasy_teams.groupby("team_key")
        .agg(active_roster_salary=("cap_hit", "sum"),
             dead_money=("dead_money", "sum"))
        .reset_index())
chk = teams.merge(roll, on="team_key", how="left")
for c in ("active_roster_salary", "dead_money"):
    chk[c] = chk[c].fillna(0)
chk["remaining_cap_current_yr"] = chk["original_cap"] - (
    chk["active_roster_salary"] + chk["dead_money"] + chk["reinvestment_cap"])

print("\n=== roster + cap (teams with picks) ===")
print(chk[chk["active_roster_salary"] > 0][
    ["team_key", "team_name", "active_roster_salary", "remaining_cap_current_yr"]
].to_string(index=False))
# The invariant that matters is remaining cap >= 0 (the old
# `remaining <= original` check was vacuously true). Warn, don't assert:
# an over-cap team is a league-side compliance problem to surface, not a
# reason to kill the scheduled pipeline run.
_over = chk[chk["remaining_cap_current_yr"] < 0]
if len(_over):
    print(f"[warn] {len(_over)} team(s) OVER the cap:")
    print(_over[["team_key", "team_name", "remaining_cap_current_yr"]]
          .to_string(index=False))
assert fact_fantasy_teams["team_key"].notna().all()
print(f"\nrostered players: {len(fact_fantasy_teams)} | "
      f"avg cap_hit: {fact_fantasy_teams['cap_hit'].mean():,.0f} | "
      f"total committed: {fact_fantasy_teams['cap_hit'].sum():,.0f}")

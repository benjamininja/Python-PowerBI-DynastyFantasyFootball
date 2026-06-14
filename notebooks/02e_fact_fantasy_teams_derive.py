# %% [markdown]
# # 02e_fact_fantasy_teams_derive  (ledger replay -> current roster + cap)
#
# **Purpose:** Derive the current-roster fact `fact_fantasy_teams` from the
# event-sourced `fact_roster_transactions` ledger (ADR-0003: the ledger is the
# SSOT; this fact is a *replay projection*, never scraped independently). Then
# roll the resulting cap charges up into `dim_fantasy_teams` (01c seeds those
# columns to 0 and documents that the ETL rollup overwrites them).
#
# **Replay rule:** order events by `event_seq`; the **last** event per
# `(team_key, asset_id)` defines that player's current contract. Terminal `drop`
# events remove the player from the active roster. v1 has only `startup_draft`
# events (all active), so this is one active row per drafted player — but the
# logic is written general so `resign`/`fa_*`/`drop` slot in without change.
#
# **Output schema (12 cols, matches 02b seed):** team_key, gsis_id, player_key,
# conference, contract_id, contract_value, contract_year, cap_hit, dead_money,
# status, acquired_method, season.
#
# **Run:**  python notebooks/02e_fact_fantasy_teams_derive.py
#   (after 02d; re-run during the live draft to refresh roster + cap state.)

# %%
import sys
from pathlib import Path

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
import etl_helpers as etl
from etl_helpers import CFG, DATA

LEDGER_PATH = DATA / "fact_roster_transactions.parquet"
FFT_PATH    = DATA / "fact_fantasy_teams.parquet"
TEAMS_PATH  = DATA / "dim_fantasy_teams.parquet"

TERMINAL = {"drop"}   # event_types that REMOVE a player from the active roster

# %%
# ---- Replay the ledger -> latest contract per (team_key, asset_id) ---------
ledger = pd.read_parquet(LEDGER_PATH)
assets = pd.read_parquet(DATA / "dim_roster_asset.parquet")
teams  = pd.read_parquet(TEAMS_PATH)
conf   = dict(zip(teams["team_key"], teams["conference"]))
print(f"[info] ledger: {len(ledger)} events, {ledger['event_type'].nunique()} type(s)")

# last event wins per player+team (event_seq = canonical acquisition order).
latest = (ledger.sort_values("event_seq")
          .drop_duplicates(["team_key", "asset_id"], keep="last"))
active = latest[~latest["event_type"].isin(TERMINAL)].copy()

# resolve asset_id -> gsis_id / player_key via the polymorphic bridge.
res = assets.set_index("asset_id")[["gsis_id", "player_key"]]
active = active.merge(res, on="asset_id", how="left", suffixes=("", "_asset"))
# prefer the ledger snapshot's gsis_id; fall back to the asset's current resolver.
active["gsis_id"] = active["gsis_id"].fillna(active["gsis_id_asset"])

fact_fantasy_teams = pd.DataFrame({
    "team_key":       active["team_key"],
    "gsis_id":        active["gsis_id"],
    "player_key":     active["player_key"],
    "conference":     active["team_key"].map(conf),
    "contract_id":    active["contract_id"],
    "contract_value": active["contract_value"],
    "contract_year":  active["contract_year"],
    "cap_hit":        active["cap_hit"],
    "dead_money":     active["dead_money"],
    "status":         active["status"],
    "acquired_method": active["event_type"],
    "season":         active["season_id"],
}).reset_index(drop=True)

fact_fantasy_teams.to_parquet(FFT_PATH, index=False)
print(f"[ok] fact_fantasy_teams: {len(fact_fantasy_teams)} active roster rows -> {FFT_PATH.name}")

# %%
# ---- Roll cap charges up into dim_fantasy_teams ----------------------------
# active_roster_salary = sum of active cap_hit; cap_hits_current_yr = realized
# dead money (0 in v1, no drops); remaining = original - (active + cap_hits + reinvest).
roll = (fact_fantasy_teams.groupby("team_key")
        .agg(active_roster_salary=("cap_hit", "sum"),
             cap_hits_current_yr=("dead_money", "sum"))
        .reset_index())

t = teams.drop(columns=["active_roster_salary", "cap_hits_current_yr"]).merge(roll, on="team_key", how="left")
for c in ("active_roster_salary", "cap_hits_current_yr"):
    t[c] = t[c].fillna(0)
t["remaining_cap_current_yr"] = t["original_cap"] - (
    t["active_roster_salary"] + t["cap_hits_current_yr"] + t["reinvestment_cap"])
t["remaining_cap_next_yr"] = t["original_cap"] - (t["active_roster_salary"] + t["cap_hits_next_yr"])
t = t[teams.columns]                                   # preserve column order
t.to_parquet(TEAMS_PATH, index=False)
print(f"[ok] dim_fantasy_teams cap rollup refreshed -> {TEAMS_PATH.name}")

# %%
# ---- Summary ---------------------------------------------------------------
print("\n=== roster + cap (teams with picks) ===")
chk = t[t["active_roster_salary"] > 0][
    ["team_key", "team_name", "active_roster_salary", "remaining_cap_current_yr"]]
print(chk.to_string(index=False))
assert (t["remaining_cap_current_yr"] <= t["original_cap"]).all()
assert fact_fantasy_teams["team_key"].notna().all()
print(f"\nrostered players: {len(fact_fantasy_teams)} | "
      f"avg cap_hit: {fact_fantasy_teams['cap_hit'].mean():,.0f} | "
      f"total committed: {fact_fantasy_teams['cap_hit'].sum():,.0f}")

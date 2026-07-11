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
# contract_year, dead_money, status, acquired_method, season. `conference` and
# `cap_hit` are NOT stored (removed 2026-07-11) -- both are 100% derivable via
# relationships that already exist (`TeamKey`->`Dim_FantasyTeams`, `ContractID`->
# `Dim_Contract`), so caching them here just duplicated that math a second time.
# Power BI derives them live (`_Measures.tmdl` 'Active Roster Salary' =
# ContractValue x RELATED(Dim_Contract[CapHitPct])); the bot's
# `discord_bot/capmath.py` does the same join in pandas.
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

LEDGER_PATH = DATA / "fact_roster_transactions.parquet"
FFT_PATH    = DATA / "fact_fantasy_teams.parquet"
TEAMS_PATH  = DATA / "dim_fantasy_teams.parquet"

TERMINAL = {"drop"}   # event_types that REMOVE a player from the active roster

# %%
# ---- Replay the ledger -> latest contract per (team_key, asset_id) ---------
ledger = pd.read_parquet(LEDGER_PATH)
assets = pd.read_parquet(DATA / "dim_roster_asset.parquet")
teams  = pd.read_parquet(TEAMS_PATH)
contracts = pd.read_parquet(DATA / "dim_contract.parquet")
cap_hit_pct = dict(zip(contracts["contract_id"], contracts["cap_hit_pct"]))
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
    "contract_id":    active["contract_id"],
    "contract_value": active["contract_value"],
    "contract_year":  active["contract_year"],
    "dead_money":     active["dead_money"],
    "status":         active["status"],
    "acquired_method": active["event_type"],
    "season":         active["season_id"],
}).reset_index(drop=True)

fact_fantasy_teams.to_parquet(FFT_PATH, index=False)
print(f"[ok] fact_fantasy_teams: {len(fact_fantasy_teams)} active roster rows -> {FFT_PATH.name}")

# %%
# ---- Summary -----------------------------------------------------------------
# Live-computed for display only -- not persisted. cap_hit is derived here the
# same way Power BI/the bot derive it (contract_value x dim_contract.cap_hit_pct),
# not read from a stored column. Mirrors _Measures.tmdl / discord_bot/capmath.py:
# original - (active_roster_salary + dead_money + reinvest).
fact_fantasy_teams["cap_hit"] = (
    fact_fantasy_teams["contract_value"]
    * fact_fantasy_teams["contract_id"].map(cap_hit_pct)
)
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
assert (chk["remaining_cap_current_yr"] <= chk["original_cap"]).all()
assert fact_fantasy_teams["team_key"].notna().all()
print(f"\nrostered players: {len(fact_fantasy_teams)} | "
      f"avg cap_hit: {fact_fantasy_teams['cap_hit'].mean():,.0f} | "
      f"total committed: {fact_fantasy_teams['cap_hit'].sum():,.0f}")

# %% [markdown]
# # 04u_fantrax_public_api  (public fxea/general REST API -- no auth)
#
# **Purpose:** Fantrax exposes a public, unauthenticated REST API
# (`https://www.fantrax.com/fxea/general/...`) alongside the internal
# `fxpa/req` RPC that 04a/04v/04w reverse-engineer. Discovered 2026-07-18
# while chasing 04a's post-startup-draft breakage (`getDraftRanks` is
# permanently retired for this league once the draft completes). This script
# reads one endpoint:
#
# - `getDraftPicks?leagueId=...` -> `futureDraftPicks`: real per-pick
#   ownership for **every** future draft (this league: 2027-2028, rounds
#   1-5, 28 teams -- 280 rows), including already-executed pick-for-pick
#   trades (`currentOwnerTeamId != originalOwnerTeamId`). This replaces the
#   synthesized future-pick baseline in
#   `mouserat_trade-bud/backend/data_access.py`'s `draft_pick_inventory()`
#   -- no HAR/RPC reverse-engineering needed for this part.
#
# The same API's `getTeamRosters` (per-team roster: salary, contract, status)
# is read by `04r`, which lands it as `fact_roster_state`.
#
# `currentDraftPicks` (the other key in getDraftPicks' response) is a small
# (~5 row) leftover of rounds 28+ from the completed startup draft -- not
# future-pick inventory, out of scope here.
#
# **No trade event-log endpoint exists** in this API (confirmed: 6
# method-name guesses all failed) -- the real transaction-history ETL
# (plan Phase A #5) still needs the HAR/internal-RPC approach.
#
# **Outputs:**
# - `data/raw/fantrax_public_draftpicks.json` -- verbatim getDraftPicks response
# - `fact_draft_pick_future.parquet` -- real future-pick ownership, grain
#   `pick_ref = year|original_owner_team_key|round` (unslotted -- no
#   `pick_in_round`/`overall_slot` exists pre-draft). `is_slotted=False`
#   throughout (retires `is_synthetic` from the backend's synthesized rows).
#   `draft_type` is always "Rookie" here (future picks are annual rookie-draft
#   slots, never startup).
#
# **Run:**  python notebooks/04u_fantrax_public_api.py

# %%
import importlib
import json
import sys
from pathlib import Path

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
from etl_helpers import DATA, load_replace_partition, classify_draft_type, fantrax_public_get

# league_id/raw_dir live on 04a's own LeagueConfig (separate from
# etl_helpers.CFG) -- reuse it rather than re-declaring the league id here,
# same import-by-file pattern 04w uses.
fx = importlib.import_module("04a_fantrax_weekly_scrape")
FX_CFG = fx.CFG

FUTURE_PATH = DATA / "fact_draft_pick_future.parquet"

# This league's two divisions (Riddell/Wilson) -- same divisionId strings
# already hardcoded in 04w's draft-results capture; dim_fantasy_teams only
# stores the human-readable `division` name, not Fantrax's internal id.
DIVISION_ID_BY_NAME = {
    "Riddell": "rhf63kfummvk3jnh",
    "Wilson": "svxeyvvgmmvk3jnh",
}


# %%
def build_future_picks(draft_picks: dict, teams: pd.DataFrame) -> pd.DataFrame:
    """futureDraftPicks -> real dim_draft_pick_future rows. teamId -> team_key
    via dim_fantasy_teams.fantrax_team_id (same FK 04w/02d already use)."""
    team_key_by_fantrax_id = dict(zip(teams["fantrax_team_id"], teams["team_key"]))
    division_by_team_key = dict(zip(teams["team_key"], teams["division"]))

    rows = []
    for p in draft_picks["futureDraftPicks"]:
        original_owner = team_key_by_fantrax_id[p["originalOwnerTeamId"]]
        current_owner = team_key_by_fantrax_id[p["currentOwnerTeamId"]]
        year = p["year"]
        round_ = p["round"]
        rows.append({
            "pick_ref": f"{year}|{original_owner}|{round_}",
            "draft_season": f"{year}-{year + 1}",
            "round": round_,
            "pick_in_round": pd.NA,
            "overall_slot": pd.NA,
            "original_owner": original_owner,
            "divisionId": DIVISION_ID_BY_NAME[division_by_team_key[original_owner]],
            "current_owner": current_owner,
            "is_made": False,
            "is_slotted": False,
        })
    df = pd.DataFrame(rows)
    df["draft_type"] = classify_draft_type(df["round"])
    assert df["pick_ref"].is_unique, "duplicate future pick_ref -- unexpected multiple picks per (year, owner, round)"
    return df


# %%
if __name__ == "__main__":
    teams = pd.read_parquet(DATA / "dim_fantasy_teams.parquet")

    draft_picks = fantrax_public_get("getDraftPicks", FX_CFG.league_id,
                                     expect=("futureDraftPicks",))
    (Path(FX_CFG.raw_dir) / "fantrax_public_draftpicks.json").write_text(
        json.dumps(draft_picks, indent=2), encoding="utf-8"
    )

    future = build_future_picks(draft_picks, teams)
    n = load_replace_partition(future, FUTURE_PATH, part_cols=("draft_season",))
    traded = int((future["original_owner"] != future["current_owner"]).sum())
    print(f"[ok] dim_draft_pick_future: {len(future)} picks written this run "
          f"({traded} already traded) -> {n} total rows -> {FUTURE_PATH.name}")

# %% [markdown]
# # 02k_fact_contract_move  (the commissioners' contract lists)
#
# **Purpose:** `fact_contract_move` (#545), the three lists the commissioners
# work from by hand in Fantrax: Minor to 1st (both directions), Expiring, and the
# re-sign Decision table. The rules and the status windows are
# `etl_contract_moves`'s; the Review check `minor_contract`, the xlsx, the
# daily post and the bot's `/contract-moves` read the same rows.
#
# **Grain:** `(list_name, team_key, scorer_id)`, rewritten whole each run. An
# empty list is a valid answer (every move made, or none due yet): the table
# may hold zero rows. It holds `team_key` only; team names are joined when a
# list is shown.
#
# **Dates:** `LeagueConfig.resign_deadline` and `final_period_end`; the day is
# the league's Eastern day.
#
# **Run:**  python notebooks/02k_fact_contract_move.py
#   (after 02e and 02j; no network.)

# %%
import sys
from datetime import date
from pathlib import Path

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "etl_helpers.py").exists():
        sys.path.insert(0, str(_p)); break
import etl_contract_moves as cm
import etl_helpers as etl

TABLE = "fact_contract_move"


# %%
def read_roster() -> pd.DataFrame:
    """The current Roster State, or a raise. An empty list may only come from
    a healthy roster (ADR-0008 decision 6, amended): no roster means no write."""
    try:
        roster = etl.read_table("fact_fantasy_teams")
    except FileNotFoundError as exc:
        raise RuntimeError("fact_fantasy_teams is missing: no contract list written") from exc
    if roster.empty:
        raise RuntimeError("fact_fantasy_teams holds no rows: no contract list written")
    return roster


def build(day: date):
    roster = read_roster()
    computed = (etl.read_table("fact_nfl_minor_eligibility")
                if etl.table_exists("fact_nfl_minor_eligibility") else None)
    return cm.build_lists(
        roster, etl.read_table("dim_fantasy_teams"), etl.read_table("dim_nfl_players"),
        etl.read_table("fact_minor_eligibility"),
        computed if computed is not None else pd.DataFrame(columns=["gsis_id", "capture_date", "career_games"]),
        etl.read_table("fact_roster_transactions"), day,
        date.fromisoformat(etl.CFG.resign_deadline), date.fromisoformat(etl.CFG.final_period_end))


def main() -> int:
    day = etl.league_date()
    lists = build(day)
    total = etl.write_table(TABLE, lists)
    counts = lists.groupby(["list_name", "status"]).size().to_dict() if len(lists) else {}
    print(f"[ok] {TABLE}: {total} rows for {day.isoformat()} -> {TABLE}.parquet")
    print(f"[info] by list and status: {counts if counts else 'none due'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

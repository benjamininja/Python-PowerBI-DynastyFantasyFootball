"""Team stance + risk-threshold inference (decisions #5-#8). Ephemeral --
computed fresh per request, no persistence (decision #12).

Decision #6 originally called for stance inference from "age-curve +
standings" -- no fact_standings/wins table exists in this repo yet
(confirmed 2026-07-17), so stance here is age-curve only until that data
exists; a future ETL source, not a Slice 2 blocker. Cap tightness (decision
#7) is a separate signal feeding risk_threshold, not stance.
"""

from __future__ import annotations

import pandas as pd

import data_access as da

_STANCE_YOUNG_AGE = 25.0  # avg roster age below this -> Future-Focused
_STANCE_OLD_AGE = 27.5  # avg roster age above this -> Contending

# Fields the reference app's "Unknown Owner" mode covered that we genuinely
# cannot infer from data -- surfaced only for a Counterparty profile's
# helper panel, per decision #8 (this replaces that third top-level mode).
LOW_CONFIDENCE_FIELDS = ["risk_tolerance", "injury_tolerance", "trade_activity_preference"]


def _roster_avg_age(team_key: str) -> float | None:
    roster = da.read_parquet("fact_fantasy_teams")
    roster = roster[roster["team_key"] == team_key]
    players = da.read_parquet("dim_nfl_players")[["gsis_id", "birth_date"]]
    r = roster.merge(players, on="gsis_id", how="inner").dropna(subset=["birth_date"])
    if r.empty:
        return None
    today = pd.Timestamp.today()
    ages = (today - pd.to_datetime(r["birth_date"])).dt.days / 365.25
    return float(ages.mean())


def infer_stance(team_key: str) -> dict:
    avg_age = _roster_avg_age(team_key)
    if avg_age is None:
        stance, confidence = "Balanced", "low"
    elif avg_age < _STANCE_YOUNG_AGE:
        stance, confidence = "Future-Focused", "medium"
    elif avg_age > _STANCE_OLD_AGE:
        stance, confidence = "Contending", "medium"
    else:
        stance, confidence = "Balanced", "medium"
    return {"stance": stance, "stance_confidence": confidence, "avg_roster_age": avg_age}


def infer_risk_threshold(team_key: str) -> dict:
    """Tighter cap (less remaining_cap_current_yr as a share of
    original_cap) -> lower risk threshold (less room to absorb a
    lopsided trade)."""
    teams = da.teams_with_cap()
    row = teams[teams["team_key"] == team_key]
    if row.empty:
        return {"risk_threshold": "medium", "risk_confidence": "low", "cap_room_pct": None}
    r = row.iloc[0]
    cap_room_pct = (
        float(r["remaining_cap_current_yr"] / r["original_cap"]) if r["original_cap"] else None
    )
    if cap_room_pct is None:
        threshold = "medium"
    elif cap_room_pct < 0.10:
        threshold = "low"
    elif cap_room_pct > 0.30:
        threshold = "high"
    else:
        threshold = "medium"
    return {"risk_threshold": threshold, "risk_confidence": "medium", "cap_room_pct": cap_room_pct}


def build_profile(team_key: str, mode: str) -> dict:
    """mode: 'my' or 'counterparty' (decision #8 -- both auto-infer the
    same signals; counterparty additionally reports which fields have no
    data-driven signal, for the frontend's helper panel)."""
    profile = {
        "team_key": team_key,
        "mode": mode,
        **infer_stance(team_key),
        **infer_risk_threshold(team_key),
    }
    if mode == "counterparty":
        profile["low_confidence_fields"] = LOW_CONFIDENCE_FIELDS
    return profile

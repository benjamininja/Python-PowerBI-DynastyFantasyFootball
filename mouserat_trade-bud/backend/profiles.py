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
_STANCE_YOUNG_AGE_HIGH = 23.0  # below this, the age-curve signal is unambiguous -> high confidence
_STANCE_OLD_AGE_HIGH = 30.0  # above this, same -> high confidence

_RISK_LOW_HIGH = 0.05  # cap_room_pct below this -> "low" threshold, high confidence
_RISK_HIGH_HIGH = 0.40  # cap_room_pct above this -> "high" threshold, high confidence

# Fields that genuinely have no data source yet (no fact_nfl_season_injuries,
# and risk-tolerance inference is an explicit future grill -- see plan
# Round 2 punch list). These are always low-confidence, for every team.
_STATIC_LOW_CONFIDENCE_FIELDS = ["risk_tolerance", "injury_tolerance"]

_TRADE_ACTIVITY_ACTIVE = 4  # nunique transaction_id at/above this -> "active"
_TRADE_ACTIVITY_OCCASIONAL = 1  # at/above this (below ACTIVE) -> "occasional"


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
    elif avg_age < _STANCE_YOUNG_AGE_HIGH:
        stance, confidence = "Future-Focused", "high"
    elif avg_age < _STANCE_YOUNG_AGE:
        stance, confidence = "Future-Focused", "medium"
    elif avg_age > _STANCE_OLD_AGE_HIGH:
        stance, confidence = "Contending", "high"
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
        threshold, confidence = "medium", "low"
    elif cap_room_pct < _RISK_LOW_HIGH:
        threshold, confidence = "low", "high"
    elif cap_room_pct < 0.10:
        threshold, confidence = "low", "medium"
    elif cap_room_pct > _RISK_HIGH_HIGH:
        threshold, confidence = "high", "high"
    elif cap_room_pct > 0.30:
        threshold, confidence = "high", "medium"
    else:
        threshold, confidence = "medium", "medium"
    return {"risk_threshold": threshold, "risk_confidence": confidence, "cap_room_pct": cap_room_pct}


def infer_trade_activity(team_key: str) -> dict:
    """Real trade-activity signal (Phase A #5) -- count of distinct trades
    (fact_trade_log's `transaction_id`, Fantrax's `txSetId`) this team has
    been a party to, either side (`team_key_from` or `team_key_to`). No
    asset-identity resolution needed for this count: those columns come
    straight off Fantrax's own `cells` teamId, not parsed text (see
    .claude/memory/mouserat-trade-bud.md Checkpoint 7).

    Single-season history so far -- tiers are a count over whatever history
    exists, not yet normalized per-season. Revisit the thresholds once
    multiple seasons of fact_trade_log accumulate."""
    log = da.read_parquet("fact_trade_log")
    involved = log[(log["team_key_from"] == team_key) | (log["team_key_to"] == team_key)]
    trade_count = int(involved["transaction_id"].nunique())
    if trade_count >= _TRADE_ACTIVITY_ACTIVE:
        tier = "active"
    elif trade_count >= _TRADE_ACTIVITY_OCCASIONAL:
        tier = "occasional"
    else:
        tier = "inactive"
    # A count of 0 doesn't distinguish "genuinely inactive owner" from "no
    # attractive offers came their way yet" -- only a nonzero count is a
    # real behavioral signal.
    confidence = "medium" if trade_count > 0 else "low"
    return {
        "trade_activity": tier,
        "trade_activity_confidence": confidence,
        "trade_count": trade_count,
    }


def low_confidence_fields(profile: dict) -> list[str]:
    """Per-team low-confidence field list (Phase A #6): starts from the
    fields with no data source at all (_STATIC_LOW_CONFIDENCE_FIELDS), then
    adds any inferred field whose own confidence came back "low" for this
    particular team (e.g. no roster/cap row found), so the frontend's
    helper panel reflects this team's actual data gaps, not a fixed list."""
    fields = list(_STATIC_LOW_CONFIDENCE_FIELDS)
    if profile.get("stance_confidence") == "low":
        fields.append("stance")
    if profile.get("risk_confidence") == "low":
        fields.append("risk_threshold")
    if profile.get("trade_activity_confidence") == "low":
        fields.append("trade_activity")
    return fields


def build_profile(team_key: str, mode: str) -> dict:
    """mode: 'my' or 'counterparty' (decision #8 -- both auto-infer the
    same signals; counterparty additionally reports which fields have no
    data-driven signal, for the frontend's helper panel)."""
    profile = {
        "team_key": team_key,
        "mode": mode,
        **infer_stance(team_key),
        **infer_risk_threshold(team_key),
        **infer_trade_activity(team_key),
    }
    if mode == "counterparty":
        profile["low_confidence_fields"] = low_confidence_fields(profile)
    return profile

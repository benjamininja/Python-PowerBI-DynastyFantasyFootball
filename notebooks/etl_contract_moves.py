"""The commissioners' contract lists (#545): Minor to 1st, Expiring and the
re-sign Decision table. One builder per list over the current Roster State
(`fact_fantasy_teams`), shared by the Review check `minor_contract`, the
`02k` step that publishes `fact_contract_move`, the xlsx, the daily post and
the bot's `/contract-moves`. Pure functions: tables in, a frame out."""
from __future__ import annotations

from datetime import date

import pandas as pd

LIST_MINOR, LIST_EXPIRING, LIST_DECISION = "minor-to-1st", "expiring", "decision"
LISTS = (LIST_MINOR, LIST_EXPIRING, LIST_DECISION)

DUE_NOW, DUE_SOON = "Due now", "Due within 7 days"
SOON_DAYS = 7
SOON_GAMES = (19, 20)

MINOR, FIRST, FA = "Minor", "1st", "FA"
EXPIRING_CONTRACTS = ("X", "6th", "Tag")
TAGGABLE = ("X", "6th")
DECISION_CONTRACTS = ("2nd", FA)

DRAFT_METHODS = frozenset({"startup_draft"})
CLAIM_METHOD, DROP_EVENT, TRADE_EVENT = "claim", "drop", "trade"

COLUMNS = ["list_name", "conference", "division", "team_key", "scorer_id", "gsis_id",
           "player_name", "position", "nfl_team", "contract_now", "move_to", "reason",
           "nfl_games", "roster_slot", "salary", "status"]
DTYPES = {"nfl_games": "Int64", "salary": "float64"}
KEY = ["list_name", "team_key", "scorer_id"]
CHANGE_KEY = ["list_name", "conference", "team_key", "scorer_id", "status"]


def empty() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=DTYPES.get(c, "object")) for c in COLUMNS})


def status_for(day: date, deadline: date, soon_days: int = SOON_DAYS) -> str | None:
    """`Due now` after the deadline, `Due within 7 days` up to 7 days before it
    (the deadline day included), nothing earlier."""
    if day > deadline:
        return DUE_NOW
    if (deadline - day).days <= soon_days:
        return DUE_SOON
    return None


def fantrax_listed(fantrax: pd.DataFrame) -> set:
    """Scorer ids on Fantrax's newest eligibility capture (04v). Empty frame:
    an empty set, so the caller must treat that as 'not comparable'."""
    if fantrax.empty:
        return set()
    return set(fantrax.loc[fantrax["capture_date"] == fantrax["capture_date"].max(), "scorer_id"])


def nflverse_games(computed: pd.DataFrame) -> pd.Series:
    """gsis_id -> career regular-season games on nflverse's newest capture (02j)."""
    if computed.empty:
        return pd.Series(dtype="int64")
    newest = computed[computed["capture_date"] == computed["capture_date"].max()]
    return newest.drop_duplicates("gsis_id", keep="last").set_index("gsis_id")["career_games"]


def roster_copies(roster: pd.DataFrame, teams: pd.DataFrame, players: pd.DataFrame,
                  fantrax: pd.DataFrame, games: pd.Series | None = None,
                  links: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per rostered copy with team conference/division and the player's
    name, position and NFL team: dim_nfl_players first, Fantrax's own listing
    (its newest capture) for a scorer with no gsis_id, the scorer id last.
    `nfl_games` is nflverse's count for reference, looked up under the player's
    newest gsis_id when `links` (dim_gsis_link) is given."""
    out = roster.merge(teams[["team_key", "conference", "division"]], on="team_key", how="left")
    by_gsis = players.drop_duplicates("gsis_id").set_index("gsis_id")
    by_scorer = (fantrax.sort_values("capture_date", kind="stable")
                 .drop_duplicates("scorer_id", keep="last").set_index("scorer_id")
                 if not fantrax.empty else pd.DataFrame())
    if games is None or games.empty:
        out["nfl_games"] = float("nan")
    else:
        ids = out["gsis_id"]
        if links is not None and not links.empty:
            import etl_helpers
            ids = etl_helpers.current_gsis(ids, links)
        out["nfl_games"] = pd.to_numeric(ids.map(games))
    for col, nfl_col, fx_col in (("player_name", "display_name", "player_name"),
                                 ("position", "position", "position_raw"),
                                 ("nfl_team", "team_abbr", "nfl_team")):
        got = out["gsis_id"].map(by_gsis[nfl_col])
        if fx_col in by_scorer.columns:
            got = got.fillna(out["scorer_id"].map(by_scorer[fx_col]))
        out[col] = got
    out["player_name"] = out["player_name"].fillna(out["scorer_id"])
    return out


def _shape(rows: pd.DataFrame, list_name: str, move_to, reason, status) -> pd.DataFrame:
    if rows.empty:
        return empty()
    out = pd.DataFrame({
        "list_name": list_name,
        "conference": rows["conference"], "division": rows["division"],
        "team_key": rows["team_key"], "scorer_id": rows["scorer_id"], "gsis_id": rows["gsis_id"],
        "player_name": rows["player_name"], "position": rows["position"],
        "nfl_team": rows["nfl_team"], "contract_now": rows["contract_id"],
        "move_to": move_to, "reason": reason,
        "nfl_games": rows["nfl_games"],
        "roster_slot": rows["roster_slot"], "salary": rows["contract_value"],
        "status": status,
    }, index=rows.index)
    return out[COLUMNS].astype(DTYPES)


def _came_in_as_minor(copy_moves: pd.DataFrame, opener) -> bool:
    """One copy's moves (its Conference, player and season, oldest first) and
    the inbound move that opened its current stint. A trade passes the copy on
    with its contract, so a traded copy is followed back to the latest
    non-trade move that brought it onto a roster; a draft pick came in as a
    Minor; a claim only when the latest drop before it was on a Minor."""
    origin = opener
    if opener["event_type"] == TRADE_EVENT:
        earlier = copy_moves[(copy_moves["event_seq"] < opener["event_seq"])
                             & copy_moves["event_type"].isin(sorted(DRAFT_METHODS | {CLAIM_METHOD}))]
        if earlier.empty:
            return False
        origin = earlier.iloc[-1]
    if origin["event_type"] in DRAFT_METHODS:
        return True
    if origin["event_type"] != CLAIM_METHOD:
        return False
    drops = copy_moves[(copy_moves["event_type"] == DROP_EVENT)
                       & (copy_moves["event_seq"] < origin["event_seq"])]
    return not drops.empty and drops.iloc[-1]["contract_id"] == MINOR


def came_in_as_minor(rows: pd.DataFrame, teams: pd.DataFrame, ledger: pd.DataFrame) -> pd.Series:
    """True per roster row whose copy came onto a roster the way that earns a
    `Minor` (ADR-0019 amendment 2026-11-14, rules 2 and 5): a startup draft
    pick, or a dropped Minor claimed, even when the copy has since been traded.
    A copy is one player in one Conference and season; moves are ordered by
    `event_seq`, as `02d` and `etl_cap.open_stints` order them. A row with no
    open stint on the ledger is False (nothing is guessed)."""
    out = pd.Series(False, index=rows.index)
    if ledger.empty or rows.empty:
        return out
    import etl_cap as cap
    conference = dict(zip(teams["team_key"], teams["conference"]))
    moves = ledger[ledger["scorer_id"].notna()].assign(
        conference=ledger["team_key"].map(conference)).sort_values("event_seq", kind="stable")
    stints = cap.open_stints(moves).set_index(["team_key", "scorer_id"])
    for i, r in rows.iterrows():
        key = (r["team_key"], r["scorer_id"])
        if key not in stints.index:
            continue
        opener = stints.loc[key]
        mine = moves[(moves["conference"] == conference.get(r["team_key"]))
                     & (moves["scorer_id"] == r["scorer_id"])
                     & (moves["season_id"] == opener["season_id"])]
        out[i] = _came_in_as_minor(mine, opener)
    return out


def minor_rows(copies: pd.DataFrame, listed: set, teams: pd.DataFrame,
               ledger: pd.DataFrame) -> pd.DataFrame:
    """Minor to 1st, both directions (ADR-0019 decision 4 and Ben's ruling of
    2026-11-14).
      - to 1st: on `Minor` and not on Fantrax's list (past 20 games) is due now;
        on the list at 19 or 20 nflverse games is due within 7 days;
      - to Minor: on the list, on FA or 1st, and the copy came in by a draft or
        as a dropped Minor claimed while eligible. A pure free-agent claim on
        FA is correct and never listed."""
    on_minor = copies[copies["contract_id"] == MINOR]
    on_list = on_minor["scorer_id"].isin(listed)
    past = on_minor[~on_list]
    near = on_minor[on_list & on_minor["nfl_games"].isin(SOON_GAMES)]
    wrong = copies[copies["contract_id"].isin([FA, FIRST]) & copies["scorer_id"].isin(listed)]
    wrong = wrong[came_in_as_minor(wrong, teams, ledger)]
    parts = [
        _shape(past, LIST_MINOR, FIRST,
               "Past 20 games: Fantrax no longer lists the player as Minors-eligible", DUE_NOW),
        _shape(near, LIST_MINOR, FIRST,
               "At 19 or 20 games: still on Minor, moves to 1st once past game 20", DUE_SOON),
        _shape(wrong, LIST_MINOR, MINOR,
               "Eligible and came in as a draft pick or a dropped Minor: belongs on Minor",
               DUE_NOW),
    ]
    return pd.concat(parts, ignore_index=True) if any(len(p) for p in parts) else empty()


def expiring_rows(copies: pd.DataFrame, day: date, final_period_end: date) -> pd.DataFrame:
    """Every rostered copy on X, 6th or Tag (bylaws 11.4.1). Rows exist only
    inside the status window of the season's final period."""
    status = status_for(day, final_period_end)
    rows = copies[copies["contract_id"].isin(EXPIRING_CONTRACTS)]
    if status is None or rows.empty:
        return empty()
    move_to = rows["contract_id"].map(lambda c: "Tag or expire" if c in TAGGABLE else "Expire")
    reason = rows["contract_id"].map(
        lambda c: f"Final year on {c}: tag-eligible at season's end" if c in TAGGABLE
        else "Final year on a Tag: expires at season's end")
    return _shape(rows, LIST_EXPIRING, move_to, reason, status)


def decision_rows(copies: pd.DataFrame, day: date, resign_deadline: date) -> pd.DataFrame:
    """Every rostered copy on 2nd or FA: the Year-2 re-sign decision (bylaws
    12.2-12.3) and the FA extension decision (5.2)."""
    status = status_for(day, resign_deadline)
    rows = copies[copies["contract_id"].isin(DECISION_CONTRACTS)]
    if status is None or rows.empty:
        return empty()
    is_fa = rows["contract_id"] == FA
    move_to = is_fa.map({True: "Keep (X next season), or let go at season's end",
                         False: "Re-sign, or keep to year 3"})
    reason = is_fa.map({True: "FA pickup: keep it by the re-sign deadline, or it returns to the pool at season's end",
                        False: "Year-2 contract: re-sign at the re-sign deadline"})
    return _shape(rows, LIST_DECISION, move_to, reason, status)


def build_lists(roster: pd.DataFrame, teams: pd.DataFrame, players: pd.DataFrame,
                fantrax: pd.DataFrame, computed: pd.DataFrame, ledger: pd.DataFrame,
                day: date, resign_deadline: date, final_period_end: date,
                links: pd.DataFrame | None = None) -> pd.DataFrame:
    """The three lists as one frame, sorted. An empty frame is a valid answer."""
    copies = roster_copies(roster, teams, players, fantrax, nflverse_games(computed), links)
    parts = [minor_rows(copies, fantrax_listed(fantrax), teams, ledger),
             expiring_rows(copies, day, final_period_end),
             decision_rows(copies, day, resign_deadline)]
    parts = [p for p in parts if len(p)]
    if not parts:
        return empty()
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["list_name", "conference", "team_key", "player_name"],
                           ignore_index=True)[COLUMNS]


def change_keys(lists: pd.DataFrame) -> set[tuple]:
    """The rows a post is about: (list, conference, team, player, status)."""
    if lists.empty:
        return set()
    return set(map(tuple, lists[CHANGE_KEY].astype(str).to_numpy()))


def new_keys(current: pd.DataFrame, previous: pd.DataFrame) -> set[tuple]:
    """Keys in `current` and not in `previous`. A commissioner's fix only removes
    a key; a copy moving from due within 7 days to due now changes its status,
    so it is a new key."""
    return change_keys(current) - change_keys(previous)

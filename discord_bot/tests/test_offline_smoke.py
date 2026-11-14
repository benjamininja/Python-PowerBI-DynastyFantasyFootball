r"""Offline smoke test for every command's embed builder.

No Discord round-trip and no network: monkeypatch each command module's
`fetch_parquet` to read the repo's local parquet, build the embeds, and assert
they honour Discord's hard limits (<=25 fields, each value <=1024, total <=6000).
This is the fast iteration loop the skill calls for — run it from the bot venv:

    discord_bot\.botvenv\Scripts\python.exe -m pytest discord_bot\tests\test_offline_smoke.py

It exercises the real data, so it also catches schema drift (a renamed column
surfaces here, not in production). The cap readers' own tests are
tests/test_cap_readers.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_BOT_DIR = Path(__file__).resolve().parent.parent
_DATA = _BOT_DIR.parent / "data"
sys.path.insert(0, str(_BOT_DIR))

import cap  # noqa: E402
import capmath  # noqa: E402
import player  # noqa: E402
import rankings  # noqa: E402
import roster  # noqa: E402
from config import Config  # noqa: E402
from delivery import CommandError  # noqa: E402

# Dummy config — fetch is patched, so only the dataclass shape matters.
CFG = Config(
    discord_bot_token="x", discord_guild_id=1, github_pat="x",
    github_owner="o", github_repo="r", github_ref="main", command_prefix="!",
)


def _local_fetch(path: str, _cfg: Config) -> pd.DataFrame:
    return pd.read_parquet(_DATA / Path(path).name)


# Each module did `from github_fetch import fetch_parquet`, so patch the name in
# each module's own namespace. capmath (cap.py/roster.py's shared cap-table
# reader) imports fetch_parquet itself — omitting it here means teams_with_cap/
# roster_with_cap_hit silently hit real GitHub instead of local parquet.
for mod in (rankings, player, cap, roster, capmath):
    mod.fetch_parquet = _local_fetch


def _check(embeds, label: str) -> None:
    assert embeds, f"{label}: produced no embeds"
    for e in embeds:
        assert len(e) <= 6000, f"{label}: embed total {len(e)} > 6000"
        assert len(e.fields) <= 25, f"{label}: {len(e.fields)} fields > 25"
        for f in e.fields:
            assert len(f.value) <= 1024, f"{label}: field '{f.name}' value > 1024"


def _expect_error(fn, label: str) -> None:
    try:
        fn()
    except CommandError:
        return
    raise AssertionError(f"{label}: expected CommandError, got a result")


def test_rankings():
    _check(rankings.build_rankings_embeds(CFG, fmt="SF"), "rankings SF all")
    _check(rankings.build_rankings_embeds(CFG, fmt="SF", position="QB"), "rankings SF QB")
    _expect_error(lambda: rankings.build_rankings_embeds(CFG, fmt="ZZZ"), "rankings bad format")


def test_player():
    _check(player.build_player_embeds(CFG, "Bijan Robinson"), "player exact")
    _check(player.build_player_embeds(CFG, "bijan"), "player substring")
    _expect_error(lambda: player.build_player_embeds(CFG, "zzzznotaplayer"), "player not found")


def _people(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame({
        "gsis_id": [g for g, _ in rows], "display_name": ["Sam Person"] * len(rows),
        "status": [s for _, s in rows], "position_group": ["WR"] * len(rows),
        "team_abbr": ["AAA"] * len(rows),
    })


def test_name_search_prefers_the_live_row_whichever_comes_first():
    for rows in ([("old", "DROPPED"), ("new", "ACT")], [("new", "ACT"), ("old", "DROPPED")]):
        assert player._resolve_player(_people(rows), "Sam Person")["gsis_id"] == "new"
        assert player._resolve_player(_people(rows), "sam")["gsis_id"] == "new"


def test_name_search_still_resolves_a_person_with_only_a_dropped_row():
    assert player._resolve_player(_people([("old", "DROPPED")]), "Sam Person")["gsis_id"] == "old"


def _tied_board(order: list[int]) -> list[str]:
    eav = pd.DataFrame({
        "snapshot_date": pd.to_datetime(["2026-01-01"] * 3), "source_name": ["DynastySharks"] * 3,
        "format": ["SF"] * 3, "metric_key": ["ds_positional_rank"] * 3,
        "gsis_id": ["g1", "g2", "g3"], "metric_num": [1.0, 1.0, 1.0],
    }).iloc[order]
    players = pd.DataFrame({
        "gsis_id": ["g1", "g2", "g3"], "display_name": ["Zed Zee", "Amy Ant", "Amy Ant"],
        "position_group": ["QB"] * 3, "team_abbr": ["AAA", "BBB", "CCC"],
    })
    fetch = lambda path, _cfg: eav if "metrics" in path else players  # noqa: E731
    return [
        (f.name, f.value)
        for e in _rank_embeds(fetch)
        for f in e.fields
    ]


def _rank_embeds(fetch):
    saved = rankings.fetch_parquet
    rankings.fetch_parquet = fetch
    try:
        return rankings.build_rankings_embeds(CFG, fmt="SF", position="QB")
    finally:
        rankings.fetch_parquet = saved


def test_rankings_ties_break_by_name_then_gsis_whichever_row_comes_first():
    first = _tied_board([0, 1, 2])
    assert _tied_board([2, 1, 0]) == _tied_board([1, 0, 2]) == first
    body = first[0][1]
    assert body.index("BBB") < body.index("CCC") < body.index("Zed")


def _rank_fetch(eav: pd.DataFrame):
    players = pd.DataFrame({
        "gsis_id": ["g1", "g2"], "display_name": ["Amy Ant", "Bob Bee"],
        "position_group": ["QB", "QB"], "team_abbr": ["AAA", "BBB"],
    })
    return lambda path, _cfg: eav if "metrics" in path else players


def _eav(rows: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame({
        "snapshot_date": pd.to_datetime(["2026-01-01"] * len(rows)),
        "source_name": [r[0] for r in rows], "format": [r[1] for r in rows],
        "metric_key": [r[2] for r in rows], "gsis_id": [r[3] for r in rows],
        "metric_num": [float(i + 1) for i in range(len(rows))],
    })


def test_rankings_idp_replies_with_the_fixed_text_when_no_source_ranks_it(monkeypatch):
    eav = _eav([("DynastySharks", "SF", "ds_positional_rank", "g1")])
    monkeypatch.setattr(rankings, "fetch_parquet", _rank_fetch(eav))
    with pytest.raises(CommandError) as err:
        rankings.build_rankings_embeds(CFG, fmt="IDP")
    assert str(err.value) == "No IDP ranking source yet."


def test_rankings_sf_defaults_to_dynastysharks(monkeypatch):
    eav = _eav([
        ("DynastySharks", "SF", "ds_positional_rank", "g1"),
        ("DynastySharks", "SF", "ds_positional_rank", "g2"),
    ])
    monkeypatch.setattr(rankings, "fetch_parquet", _rank_fetch(eav))
    embeds = rankings.build_rankings_embeds(CFG, fmt="SF")
    assert "(DynastySharks)" in embeds[0].title
    assert "Source: DynastySharks" in embeds[0].footer.text


def _league_fetch(owned: pd.DataFrame, teams: pd.DataFrame):
    def fetch(path: str, _cfg: Config) -> pd.DataFrame:
        return owned if "fantasy_teams" in path and "dim_" not in path else teams
    return fetch


_TEAMS = pd.DataFrame({"team_key": ["A01", "B01"], "team_name": ["Alpha", "Bravo"]})


def test_player_card_names_every_team_holding_the_player(monkeypatch):
    owned = pd.DataFrame({
        "team_key": ["A01", "B01", "A01"], "gsis_id": ["g1", "g1", "g2"],
        "contract_value": [5_000_000.0, 2_000_000.0, 1.0], "cap_hit": [5_000_000.0, 0.0, 1.0],
    })
    monkeypatch.setattr(player, "fetch_parquet", _league_fetch(owned, _TEAMS))
    lines = player._league_lines(CFG, "g1")
    assert [ln for ln in lines if ln.startswith("Owner")] == ["Owner    Alpha", "Owner    Bravo"]
    assert len(lines) == 4
    assert lines[1] == "Contract $5.0M · cap $5.0M"
    assert lines[3] == "Contract $2.0M · cap $0"


def test_player_card_contract_line_prints_the_stored_cap_hit(monkeypatch):
    owned = pd.DataFrame({
        "team_key": ["A01"], "gsis_id": ["g1"],
        "contract_value": [5_000_000.0], "cap_hit": [1_000_000.0],
    })
    monkeypatch.setattr(player, "fetch_parquet", _league_fetch(owned, _TEAMS))
    assert player._league_lines(CFG, "g1")[1] == "Contract $5.0M · cap $1.0M"


def test_fmt_money_abbreviates_a_negative_like_a_positive():
    from render import fmt_money
    assert fmt_money(-5_000_000) == "-$5.0M"
    assert fmt_money(-5_000) == "-$5K"
    assert fmt_money(-12) == "-$12"
    assert fmt_money(5_000_000) == "$5.0M"
    assert fmt_money(float("nan")) == "—"
    assert fmt_money(None) == "—"
    assert fmt_money(-0.4) == "$0"
    assert fmt_money(float("-inf")) == "—"
    assert fmt_money(pd.NA) == "—"


def test_cap():
    embeds = cap.build_cap_embeds(CFG)
    _check(embeds, "cap standings")
    for e in embeds:
        for f in e.fields:
            assert f.value.split("\n")[1].rstrip().endswith("IR"), "cap board lacks the IR column"
            # mono_block cuts an over-long block to exactly 1024 characters
            assert len(f.value) < 1024, f"cap board '{f.name}' was cut by mono_block"
        assert "IR and Minors exempt" in e.footer.text


def test_roster():
    teams = pd.read_parquet(_DATA / "dim_fantasy_teams.parquet")
    owned = pd.read_parquet(_DATA / "fact_fantasy_teams.parquet")
    drafted_key = owned["team_key"].iloc[0]
    drafted_abbr = teams.loc[teams["team_key"] == drafted_key, "team_abbr"].iloc[0]
    embeds = roster.build_roster_embeds(CFG, drafted_abbr)
    _check(embeds, f"roster {drafted_abbr} (drafted)")
    assert all("IR-exempt salary" in e.footer.text for e in embeds)
    # A team with no roster rows should hit the friendly empty-state.
    undrafted = teams[~teams["team_key"].isin(owned["team_key"].unique())]
    if not undrafted.empty:
        _expect_error(
            lambda: roster.build_roster_embeds(CFG, undrafted.iloc[0]["team_abbr"]),
            "roster undrafted (empty-state)",
        )
    _expect_error(lambda: roster.build_roster_embeds(CFG, "zzzznoteam"), "roster not found")

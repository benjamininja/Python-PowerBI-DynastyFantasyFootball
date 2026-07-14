r"""Offline smoke test for every command's embed builder.

No Discord round-trip and no network: monkeypatch each command module's
`fetch_parquet` to read the repo's local parquet, build the embeds, and assert
they honour Discord's hard limits (<=25 fields, each value <=1024, total <=6000).
This is the fast iteration loop the skill calls for — run it from the bot venv:

    discord_bot\.botvenv\Scripts\python.exe -m pytest discord_bot\tests\test_offline_smoke.py

It exercises the real data, so it also catches schema drift (a renamed column
surfaces here, not in production).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_BOT_DIR = Path(__file__).resolve().parent.parent
_DATA = _BOT_DIR.parent / "data"
sys.path.insert(0, str(_BOT_DIR))

import adp  # noqa: E402
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
# each module's own namespace. capmath (cap.py/roster.py's shared cap-math helper)
# imports fetch_parquet itself — omitting it here means teams_with_cap/
# roster_with_cap_hit silently hit real GitHub instead of local parquet.
for mod in (rankings, adp, player, cap, roster, capmath):
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
    _check(rankings.build_rankings_embeds(CFG, fmt="IDP"), "rankings IDP all")
    _check(rankings.build_rankings_embeds(CFG, fmt="SF", position="QB"), "rankings SF QB")
    _expect_error(lambda: rankings.build_rankings_embeds(CFG, fmt="ZZZ"), "rankings bad format")


def test_adp():
    _check(adp.build_adp_embeds(CFG), "adp overall")
    _check(adp.build_adp_embeds(CFG, position="QB"), "adp QB")
    _check(adp.build_adp_embeds(CFG, limit=50), "adp limit 50")
    _expect_error(lambda: adp.build_adp_embeds(CFG, position="ZZZ"), "adp bad position")


def test_player():
    _check(player.build_player_embeds(CFG, "Bijan Robinson"), "player exact")
    _check(player.build_player_embeds(CFG, "bijan"), "player substring")
    _expect_error(lambda: player.build_player_embeds(CFG, "zzzznotaplayer"), "player not found")


def test_cap():
    _check(cap.build_cap_embeds(CFG), "cap standings")


def test_roster():
    teams = pd.read_parquet(_DATA / "dim_fantasy_teams.parquet")
    owned = pd.read_parquet(_DATA / "fact_fantasy_teams.parquet")
    drafted_key = owned["team_key"].iloc[0]
    drafted_abbr = teams.loc[teams["team_key"] == drafted_key, "team_abbr"].iloc[0]
    _check(roster.build_roster_embeds(CFG, drafted_abbr), f"roster {drafted_abbr} (drafted)")
    # A team with no roster rows should hit the friendly empty-state.
    undrafted = teams[~teams["team_key"].isin(owned["team_key"].unique())]
    if not undrafted.empty:
        _expect_error(
            lambda: roster.build_roster_embeds(CFG, undrafted.iloc[0]["team_abbr"]),
            "roster undrafted (empty-state)",
        )
    _expect_error(lambda: roster.build_roster_embeds(CFG, "zzzznoteam"), "roster not found")


def test_capmath_minors_exempt():
    """Cap rules (2026-07-13 audit): a kept player charges the FULL
    contract_value (CapHitPct is dead-money-only, never applied); Minors
    PLACEMENT (roster_status) is the only exemption — a Minor-CONTRACT player
    kept Active is charged in full; null roster_status charges (safe default)."""
    frames = {
        "fact_fantasy_teams.parquet": pd.DataFrame({
            "team_key":       ["A01", "A01", "A01", "A01"],
            "contract_id":    ["1st", "1st", "Minor", "Minor"],
            "contract_value": [10_000_000.0, 6_000_000.0, 2_000_000.0, 2_000_000.0],
            "roster_status":  ["Active", None, "Minors", "Active"],
        }),
    }
    orig = capmath.fetch_parquet
    capmath.fetch_parquet = lambda path, _cfg: frames[Path(path).name]
    try:
        r = capmath.roster_with_cap_hit(CFG)
    finally:
        capmath.fetch_parquet = orig
    hits = r["cap_hit"].tolist()
    assert hits[0] == 10_000_000.0   # kept player: FULL contract value, no pct
    assert hits[1] == 6_000_000.0    # null roster_status charges (safe default)
    assert hits[2] == 0.0            # Minors PLACEMENT: exempt
    assert hits[3] == 2_000_000.0    # Minor CONTRACT kept Active: charged in full
    assert r["cap_exempt"].tolist() == [False, False, True, False]
    # contract_value untouched by the exemption
    assert r["contract_value"].tolist()[2] == 2_000_000.0


def test_capmath_dead_money_computed():
    """teams_with_cap computes dead money (stored column dropped 2026-07-13):
    only Cut + Guaranteed prices in, at contract_value x cap_hit_pct. The trap
    case is 'X' (cap_hit_pct 0.5 but guaranteed False) — must price 0."""
    frames = {
        "dim_fantasy_teams.parquet": pd.DataFrame({
            "team_key":         ["A01"],
            "original_cap":     [300_000_000.0],
            "reinvestment_cap": [0.0],
        }),
        "fact_fantasy_teams.parquet": pd.DataFrame({
            "team_key":       ["A01", "A01", "A01", "A01"],
            "contract_id":    ["1st", "1st", "X", "3rd"],
            "contract_value": [10_000_000.0, 8_000_000.0, 4_000_000.0, 6_000_000.0],
            "status":         ["active", "Cut", "Cut", "Cut"],
            "roster_status":  ["Active", None, None, None],
        }),
        "dim_contract.parquet": pd.DataFrame({
            "contract_id": ["1st", "X", "3rd"],
            "cap_hit_pct": [0.5, 0.5, 0.0],
            "guaranteed":  [True, False, False],
        }),
    }
    orig = capmath.fetch_parquet
    capmath.fetch_parquet = lambda path, _cfg: frames[Path(path).name]
    try:
        t = capmath.teams_with_cap(CFG)
    finally:
        capmath.fetch_parquet = orig
    row = t.iloc[0]
    # Cut+Guaranteed 1st: 8M x 0.5 = 4M. Cut X (not guaranteed) and Cut 3rd
    # (guaranteed False, pct 0) price 0.
    assert row["dead_money"] == 4_000_000.0
    # active salary is full contract_value of every row (Cut exclusion is a
    # known open item pending drop events — parity with the DAX measure).
    assert row["active_roster_salary"] == 28_000_000.0
    assert row["remaining_cap_current_yr"] == 300_000_000.0 - 28_000_000.0 - 4_000_000.0

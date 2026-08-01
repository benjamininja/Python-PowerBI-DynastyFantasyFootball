"""Render mouserat_trade-bud to a fully static site for GitHub Pages.

Every GET endpoint in backend/ is a pure function of this repo's committed
parquet -- the same answer on every request until the ETL reruns -- so the
whole app ships as static JSON with no server and no database. See the
Round 10 section of the plan for why this beats hosting FastAPI or mirroring
the reference app's Supabase design.

This script **calls the existing router functions directly** rather than
reimplementing anything: positional_strength.py, profiles.py, pick_value.py,
pareto.py and routers/*.py stay the single source of truth for every number
that lands in the JSON (same don't-copy-paste rule as etl_helpers.py).

Usage (from the repo root, or anywhere -- paths are anchored to this file):

    .venv\\Scripts\\python.exe mouserat_trade-bud/export_static.py --out mouserat_trade-bud/_site

Serve the result locally with:

    python -m http.server --directory mouserat_trade-bud/_site 8500
"""

from __future__ import annotations

import argparse
import functools
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR / "backend"
REPO_ROOT = APP_DIR.parent

# routers/*.py import their siblings as top-level modules ("import data_access
# as da"), exactly as they do under `uvicorn main:app` with CWD=backend/ --
# so backend/ has to be on sys.path before importing them.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import data_access as da  # noqa: E402 -- needs sys.path set up first
from routers import assets as assets_router  # noqa: E402
from routers import positional as positional_router  # noqa: E402
from routers import teams as teams_router  # noqa: E402

DEFAULT_OUT = APP_DIR / "_site"


def _memoize_readers() -> None:
    """Cache the hot parquet readers **for this process only**.

    data_access.read_parquet has no caching, and pareto.asset_value re-reads
    dim_nfl_players (25k rows) and re-aggregates the 26k-row dynasty EAV for
    *every* player -- fine for a single API request (~45 assets), wasteful
    across a 1027-asset full export. Measured: 1.04s -> 0.23s per team
    (~29s -> ~6s overall), with byte-identical payloads.

    Deliberately NOT applied inside data_access.py: the long-lived dev server
    would then serve stale data after a pipeline run until restarted. A
    one-shot export process has no such staleness window.
    """
    da.read_parquet = functools.lru_cache(maxsize=None)(da.read_parquet)
    da.player_values = functools.lru_cache(maxsize=None)(da.player_values)
    da.draft_pick_inventory = functools.lru_cache(maxsize=None)(da.draft_pick_inventory)


def _commit_sha() -> str | None:
    """Short SHA of the checkout the data came from, for meta.json. Best
    effort -- a tarball export or missing git just yields None."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _nulls_for_nan(obj):
    """Recursively replace non-finite floats (NaN/inf) with None.

    Not cosmetic -- required for correctness twice over. These payloads carry
    real NaNs (a player with no contract value, an unnamed roster copy), and:

    1. json.dumps writes them as a bare ``NaN`` literal, which is **not valid
       JSON**. Browsers' JSON.parse rejects the whole file, so one missing
       contract value would blank an entire team.
    2. The live API renders them as ``null``, so anything else breaks parity
       with the endpoints this export is meant to stand in for.
    """
    if isinstance(obj, float):
        return None if obj != obj or obj in (float("inf"), float("-inf")) else obj
    if isinstance(obj, dict):
        return {k: _nulls_for_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nulls_for_nan(v) for v in obj]
    return obj


def _write_json(path: Path, payload) -> int:
    """Write compact JSON (this is wire payload, not a reviewed artifact).

    default=str coerces the stray numpy/pandas scalars these payloads carry;
    allow_nan=False then makes any missed non-finite float a hard error rather
    than silently emitting invalid JSON (see _nulls_for_nan).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_nulls_for_nan(payload), default=str,
                      separators=(",", ":"), allow_nan=False)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def export(out_dir: Path) -> None:
    _memoize_readers()

    data_dir = out_dir / "data"
    if out_dir.exists():
        # ignore_errors because OneDrive keeps a handle on synced directories:
        # the files delete fine, then rmdir fails with WinError 5. Stale *files*
        # are what would corrupt a build, and those always go; a surviving empty
        # directory is harmless and gets repopulated below.
        shutil.rmtree(out_dir, ignore_errors=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    total = 0

    teams = teams_router.list_teams()
    total += _write_json(data_dir / "teams.json", teams)
    team_keys = [t["team_key"] for t in teams]
    print(f"[ok] teams.json                 {len(teams)} teams")

    # Positional ranks are stance-dependent (a contender's DL surplus is not a
    # rebuilder's), so all three are precomputed and the chips switch between
    # them client-side with no refetch.
    league = {s: positional_router.league_positional_strength(s) for s in da.STANCES}
    total += _write_json(data_dir / "positional-league.json", league)
    n_rows = sum(len(v) for v in league.values())
    print(f"[ok] positional-league.json     {n_rows} rows across {len(league)} stances")

    # 28 teams x 2 modes, nested one level -- small enough that one file
    # beats 56 round trips.
    profiles = {
        k: {mode: teams_router.team_profile(k, mode) for mode in ("my", "counterparty")}
        for k in team_keys
    }
    total += _write_json(data_dir / "profiles.json", profiles)
    print(f"[ok] profiles.json              {len(profiles)} teams x 2 modes")

    # One file per team: the UI only ever loads two at a time, so keep these
    # lazy rather than shipping every roster on first paint.
    asset_bytes = 0
    for k in team_keys:
        payload = assets_router.team_assets(k)
        asset_bytes += _write_json(data_dir / "assets" / f"{k}.json", payload)
    total += asset_bytes
    print(f"[ok] assets/*.json              {len(team_keys)} files, {asset_bytes / 1024:.0f} KB")

    total += _write_json(data_dir / "meta.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit_sha(),
        "teams": len(teams),
        "positional_rows": n_rows,
        "stances": list(da.STANCES),
    })

    shutil.copy2(APP_DIR / "frontend" / "index.html", out_dir / "index.html")
    # Pages' default Jekyll processing would drop files/dirs starting with
    # "_"; harmless here, but this makes the upload verbatim regardless.
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    print(f"[ok] index.html + .nojekyll")
    print(f"[done] {out_dir}  ({total / 1024:.0f} KB of JSON)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"build directory (default: {DEFAULT_OUT})")
    export(ap.parse_args().out.resolve())


if __name__ == "__main__":
    main()

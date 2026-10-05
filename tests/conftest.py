"""Shared fixtures for tests/ (pytest picks this file up automatically)."""
import subprocess
from pathlib import Path

import pandas as pd
import pytest


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


@pytest.fixture
def git_repo(tmp_path):
    """An empty throwaway git repo on branch `main` with a data/ dir, for
    tests that exercise git HEAD reads and the pipeline's commit path."""
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "test")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "core.autocrlf", "false")
    return repo


def league_teams(conferences=("A",) * 14 + ("B",) * 14):
    """dim_fantasy_teams as the checks read it: 28 teams, 14 per Conference."""
    return pd.DataFrame({"team_key": [f"T{i:02d}" for i in range(len(conferences))],
                         "conference": list(conferences)})


def closeable(periods=(1,), season_id="2026-2027"):
    """A table loader over 28 teams whose `periods` all pass the Close checks:
    teams paired inside their Conference, one Starter and one Bench player
    each, and a Matchup score equal to the Starter's points."""
    keys = league_teams()["team_key"].tolist()
    pts = {k: 100.0 + i for i, k in enumerate(keys)}
    opp = {a: b for i in range(0, len(keys), 2)
           for a, b in ((keys[i], keys[i + 1]), (keys[i + 1], keys[i]))}
    state, matchup, scoring = [], [], []
    for p in periods:
        for i, k in enumerate(keys):
            state.append((season_id, p, k, f"s{i}", "Starter"))
            matchup.append((season_id, p, k, opp[k], i % 2 == 1, pts[k], pts[opp[k]]))
            scoring.append((season_id, p, k, f"s{i}", True, pts[k]))
            scoring.append((season_id, p, k, f"b{i}", False, 7.0))
    tables = {
        "dim_fantasy_teams": league_teams(),
        "fact_roster_state": pd.DataFrame(state, columns=[
            "season_id", "period", "team_key", "scorer_id", "roster_slot"]),
        "fact_matchup": pd.DataFrame(matchup, columns=[
            "season_id", "period", "team_key", "opponent_team_key", "is_home",
            "fpts_for", "fpts_against"]),
        "fact_period_scoring": pd.DataFrame(scoring, columns=[
            "season_id", "period", "team_key", "scorer_id", "is_starter", "fpts"]),
    }
    return tables

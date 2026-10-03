"""Shared fixtures for tests/ (pytest picks this file up automatically)."""
import subprocess
from pathlib import Path

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

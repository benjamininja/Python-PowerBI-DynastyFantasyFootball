"""Fetch parquet from the GitHub repo and return DataFrames.

All GitHub access lives here so auth and caching stay in one place. The repo is
public, but we authenticate with a fine-grained PAT (Contents: Read-only, this
repo) for the higher rate limit. The bot performs no writes.

Uses the contents API with `Accept: application/vnd.github.raw` to get the file
bytes directly (avoids the base64 JSON envelope and its ~1 MB ceiling). Results
are cached in-memory with a short TTL: the data refreshes on a manual ETL
cadence, so minutes of staleness is fine and the cache spares the rate limit.
"""

from __future__ import annotations

import time
from io import BytesIO

import httpx
import pandas as pd

from config import Config

_API = "https://api.github.com/repos/{owner}/{repo}/contents/{path}"
_TTL_SECONDS = 600
_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def fetch_parquet(path: str, cfg: Config) -> pd.DataFrame:
    """Fetch a repo parquet file as a DataFrame, with TTL caching.

    path is repo-relative, e.g. "data/fact_dynasty_rankings.parquet".
    """
    key = f"{cfg.github_ref}:{path}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _TTL_SECONDS:
        return hit[1]

    url = _API.format(owner=cfg.github_owner, repo=cfg.github_repo, path=path)
    resp = httpx.get(
        url,
        params={"ref": cfg.github_ref},
        headers={
            "Authorization": f"Bearer {cfg.github_pat}",
            "Accept": "application/vnd.github.raw",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    df = pd.read_parquet(BytesIO(resp.content))
    _cache[key] = (time.time(), df)
    return df


def clear_cache() -> None:
    """Drop all cached frames (used by tests or a future refresh command)."""
    _cache.clear()

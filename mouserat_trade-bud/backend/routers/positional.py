from __future__ import annotations

from fastapi import APIRouter

import positional_strength as ps

router = APIRouter(prefix="/teams", tags=["positional-strength"])
league_router = APIRouter(prefix="/positional-strength", tags=["positional-strength"])


@router.get("/{team_key}/positional-strength")
def team_positional_strength(team_key: str) -> list[dict]:
    return ps.positional_strength(team_key)


@league_router.get("/league")
def league_positional_strength() -> list[dict]:
    return ps.league_positional_strength().to_dict(orient="records")

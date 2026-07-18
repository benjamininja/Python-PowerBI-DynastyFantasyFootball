from __future__ import annotations

from fastapi import APIRouter

import positional_strength as ps

router = APIRouter(prefix="/teams", tags=["positional-strength"])


@router.get("/{team_key}/positional-strength")
def team_positional_strength(team_key: str) -> list[dict]:
    return ps.positional_strength(team_key)

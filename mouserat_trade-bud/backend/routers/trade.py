from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

import pareto

router = APIRouter(prefix="/trade", tags=["trade"])


class TradeAsset(BaseModel):
    asset_type: str  # "player" | "pick"
    asset_id: str


class TradeRequest(BaseModel):
    give: list[TradeAsset]
    receive: list[TradeAsset]


@router.post("/evaluate")
def evaluate_trade(req: TradeRequest) -> dict:
    return pareto.evaluate_trade(
        give=[a.model_dump() for a in req.give],
        receive=[a.model_dump() for a in req.receive],
    )

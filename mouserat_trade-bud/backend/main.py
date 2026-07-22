"""mouserat_trade-bud backend -- local FastAPI dev server (decision #2).

Run from this directory (backend/), CWD matters for the sys.path bootstrap
in the routers/*.py modules importing sibling modules directly:

    ..\..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8420

CORS is wide open -- this is a local-only tool (decision #3: single static
HTML file, no build step) served from file:// or a trivial local server,
never deployed.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import assets, positional, teams, trade

app = FastAPI(title="mouserat_trade-bud")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(teams.router)
app.include_router(positional.router)
app.include_router(positional.league_router)
app.include_router(assets.router)
app.include_router(trade.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

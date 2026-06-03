"""BVE Platform — FastAPI application.

Start with:
    uvicorn apps.api.main:app --reload --port 8000

Configuration:
    DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/bve uvicorn apps.api.main:app
    DATABASE_URL=sqlite:///./bve_platform.db uvicorn apps.api.main:app  (dev default)
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import acquirers, alerts, assets, calibration, deals, theses
from bve.persistence.db import create_all_tables

app = FastAPI(
    title="BVE Platform API",
    description="Biotech M&A + public-markets intelligence platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — permissive in dev; tighten in prod
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(assets.router)
app.include_router(acquirers.router)
app.include_router(deals.router)
app.include_router(alerts.router)
app.include_router(calibration.router)
app.include_router(theses.router)


@app.on_event("startup")
async def startup_event() -> None:
    """Create tables on startup if they don't exist (dev convenience)."""
    create_all_tables()


@app.get("/health/live")
def liveness() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> dict:
    try:
        from bve.persistence.db import engine
        with engine.connect():
            pass
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}

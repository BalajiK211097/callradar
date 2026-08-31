"""
CallRadar backend — FastAPI application entry point.

Start the server:
    uvicorn backend.main:app --reload

Interactive API docs available at:
    http://localhost:8000/docs   (Swagger UI)
    http://localhost:8000/redoc  (ReDoc)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Bootstrap AWS Parameter Store secrets before any module reads os.environ
from pipeline.secrets import load_secrets
load_secrets()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import init_db
from backend.routers import agents, calls, customers, flagged

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create database tables on startup, clean up on shutdown."""
    logger.info("Initialising database …")
    await init_db()
    logger.info("Database ready — CallRadar API is live")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="CallRadar API",
    description="AI-powered call centre analysis platform.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow all origins during development / hackathon demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(calls.router, prefix="/calls", tags=["calls"])
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(customers.router, prefix="/customers", tags=["customers"])
app.include_router(flagged.router, prefix="/flagged", tags=["flagged"])


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe — returns ok when the server is up.

    Returns:
        Dict with status key.
    """
    return {"status": "ok"}


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    """Root endpoint — useful for confirming the API is reachable.

    Returns:
        Dict with name and docs link.
    """
    return {"name": "CallRadar API", "docs": "/docs"}

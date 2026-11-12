"""FastAPI Application factory and configuration."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api.middleware import SecurityAndLimitsMiddleware
from api.routes import VERSION, router
from core.db import db as database
from core.logging_config import configure_logging

# Structured logs: one JSON object per line by default (REFACTOR_AI_LOG_FORMAT=text
# switches to a human-readable line for local development).
configure_logging()
logger = logging.getLogger("refactor_ai.app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Recover runs that a previous process left in flight (FR07, UC03)."""
    recovered = database.recover_interrupted_runs()
    if recovered:
        logger.warning(
            "Recovered %d interrupted run(s) as failed",
            len(recovered),
            extra={"recovered_runs": len(recovered)},
        )
    yield


app = FastAPI(
    title="Multi-Agent Refactoring for Python",
    version=VERSION,
    description="End-to-end multi-agent Python refactoring system with deterministic verification.",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "Analysis",
            "description": "Static AST analysis and provider availability (FR02).",
        },
        {
            "name": "Runs",
            "description": "Start, poll, list and export refactoring runs (FR03, FR05, FR07).",
        },
        {"name": "Feedback", "description": "Record the user's accept/reject decision (FR06)."},
        {
            "name": "Operations",
            "description": "Health, measured aggregates and Prometheus metrics (NFR07).",
        },
    ],
)

# Attach Security and Limiting Middleware
app.add_middleware(SecurityAndLimitsMiddleware)

# Enable CORS for local web interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)

# --- Static frontend serving (Phase 6) -------------------------------------
# The single React/TypeScript interface built to frontend/dist is served at
# "/". The branch degrades gracefully when the build is absent, so the API
# always boots on a fresh checkout.
repo_root = Path(__file__).resolve().parents[2]
frontend_dir = repo_root / "frontend"
frontend_dist = frontend_dir / "dist"

if frontend_dist.exists():
    # The whole built bundle is served at "/": index.html, the hashed assets,
    # the favicon and the pre-paint theme bootstrap script. API routes are
    # registered above, so they always win over the static mount.
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="ui")
else:

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def serve_placeholder() -> HTMLResponse:
        """Fallback shown when the frontend bundle has not been built yet."""
        return HTMLResponse(
            "<h1>Multi-Agent Refactoring UI</h1>"
            "<p>The frontend bundle is missing. Build it with: "
            "<code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code></p>"
        )

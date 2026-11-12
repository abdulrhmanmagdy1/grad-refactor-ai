"""FastAPI dependency injection utilities."""

from agents.orchestrator import WorkflowOrchestrator, orchestrator
from core.db import DatabaseManager, db


def get_db() -> DatabaseManager:
    """Dependency providing access to the SQLite database manager."""
    return db


def get_orchestrator() -> WorkflowOrchestrator:
    """Dependency providing access to the workflow orchestrator."""
    return orchestrator

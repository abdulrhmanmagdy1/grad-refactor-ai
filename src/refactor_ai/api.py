"""Backward-compatible entry point for the FastAPI application."""

from api.app import app
from core.schemas import CodeInput as AnalysisRequest

__all__ = ["app", "AnalysisRequest"]

"""Wiring of the project review mode into the service.

With the local provider and a project model configuration file, the function mode's model
and the project mode's GGUF model share one ModelPool, so only one of them is loaded on the
GPU at a time. In fake mode, or without the project model configuration, project reviews use
the static checks only.
"""

from __future__ import annotations

import logging
from pathlib import Path

from refactor_ai.config import Settings
from refactor_ai.providers.gguf import (
    GgufProvider,
    ModelPool,
    PooledProvider,
    ReleasableLocalProvider,
)
from refactor_ai.providers.local import LocalProvider

logger = logging.getLogger(__name__)


def pair_providers(settings: Settings, provider):
    """(the function mode's provider, the project mode's provider or None)."""
    if settings.provider != "local" or not isinstance(provider, LocalProvider):
        return provider, None
    config = Path(settings.project_model_config)
    if not config.is_file():
        logger.info("No project model configuration at %s; project reviews are static only", config)
        return provider, None
    try:
        project = GgufProvider.from_config(config)
    except Exception:
        logger.exception("The project model provider could not start; reviews are static only")
        return provider, None
    if isinstance(provider, ReleasableLocalProvider):
        releasable = provider
    else:  # the same settings, with release(); the original has not started a worker
        releasable = ReleasableLocalProvider(provider.settings)
        provider.close()
    pool = ModelPool()
    return PooledProvider(releasable, pool), PooledProvider(project, pool)


def project_model_info(provider) -> dict:
    if provider is None:
        return {
            "uses_model": False,
            "detail": "No project model is configured: reviews use the static checks only.",
        }
    info = provider.info()
    return {
        "uses_model": True,
        "model_id": info.model_id,
        "model_revision": info.model_revision,
        "ready": info.ready,
        "detail": info.detail,
    }

"""Shared Chroma runtime configuration for quiet production startup."""

from __future__ import annotations

import logging
import os
from typing import Any

_CHROMA_LOGGERS = (
    "chromadb.telemetry.product.posthog",
    "chromadb.telemetry",
)


def configure_chroma_runtime() -> None:
    """Disable noisy Chroma telemetry logging for production services."""
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "FALSE")
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
    os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
    os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")
    for logger_name in _CHROMA_LOGGERS:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)
        logger.propagate = False
        logger.disabled = True


def build_chroma_settings(*, chromadb_module: Any):
    """Create Chroma settings with telemetry disabled."""
    configure_chroma_runtime()
    return chromadb_module.config.Settings(anonymized_telemetry=False)

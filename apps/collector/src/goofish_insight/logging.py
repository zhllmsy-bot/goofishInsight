from __future__ import annotations

import logging
import os
from functools import lru_cache

from .settings import get_settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _resolve_log_level(raw_level: str | None) -> int:
    normalized = str(raw_level or "").strip().upper()
    if not normalized:
        return logging.INFO
    return getattr(logging, normalized, logging.INFO)


@lru_cache(maxsize=1)
def configure_logging() -> None:
    settings = get_settings()
    raw_level = os.getenv("LOG_LEVEL") or getattr(settings, "log_level", None) or "INFO"
    raw_format = os.getenv("LOG_FORMAT") or getattr(settings, "log_format", None) or "text"

    level = _resolve_log_level(raw_level)
    if str(raw_format).strip().lower() == "json":
        fmt = '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'
    else:
        fmt = LOG_FORMAT

    logging.basicConfig(level=level, format=fmt)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)

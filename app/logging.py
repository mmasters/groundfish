"""Structured JSON logging: a rotating file handler plus optional stdout.

Every request emits one JSON line via the ``stockfish_server.request`` logger so the
log file is trivially grep-able and ingestible for metrics/analytics later.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from pythonjsonlogger.json import JsonFormatter

from app.config import Settings

REQUEST_LOGGER = "stockfish_server.request"
APP_LOGGER = "stockfish_server"

_FMT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _build_formatter() -> JsonFormatter:
    return JsonFormatter(_FMT, rename_fields={"asctime": "ts", "levelname": "level"})


def configure_logging(settings: Settings) -> None:
    """Install JSON handlers on the application loggers. Idempotent."""
    formatter = _build_formatter()
    handlers: list[logging.Handler] = []

    if settings.log_file:
        os.makedirs(os.path.dirname(os.path.abspath(settings.log_file)), exist_ok=True)
        file_handler = RotatingFileHandler(
            settings.log_file,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    if settings.log_to_stdout:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    for name in (APP_LOGGER, REQUEST_LOGGER):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers.clear()
        for handler in handlers:
            logger.addHandler(handler)
        logger.propagate = False


def get_request_logger() -> logging.Logger:
    return logging.getLogger(REQUEST_LOGGER)


def get_app_logger() -> logging.Logger:
    return logging.getLogger(APP_LOGGER)

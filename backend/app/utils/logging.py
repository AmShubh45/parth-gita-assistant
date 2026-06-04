"""
Structured logging configuration.

Provides consistent, level-aware logging across the application.
Uses JSON formatting in production and human-readable format in development.
"""

import logging
import sys

from app.config import settings


def setup_logging() -> None:
    """Configure the root logger for the application."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Determine format based on environment
    if settings.node_env == "production":
        fmt = (
            '{"time": "%(asctime)s", "level": "%(levelname)s", '
            '"module": "%(name)s", "message": "%(message)s"}'
        )
    else:
        fmt = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"

    logging.basicConfig(
        level=log_level,
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )

    # Reduce noise from third-party libraries
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger instance.

    Usage::

        from app.utils.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Server started")
    """
    return logging.getLogger(name)

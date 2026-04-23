"""Logging configuration."""

import sys
from typing import Optional

from loguru import logger


def get_logger(name: Optional[str] = None, level: str = "INFO"):
    """Get a configured logger instance."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=level,
    )
    return logger.bind(name=name or __name__)

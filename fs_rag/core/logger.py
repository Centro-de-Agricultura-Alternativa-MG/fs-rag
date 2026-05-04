"""Logging configuration."""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def get_logger(name: Optional[str] = None, level: str = "INFO", log_file: Optional[Path] = None):
    """Get a configured logger instance with optional file output.
    
    Args:
        name: Logger name
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to write logs to file
    
    Returns:
        Configured logger instance
    """
    logger.remove()
    
    # Console output
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=level,
    )
    
    # File output if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
            level=level,
            rotation="100 MB",
            retention="7 days",
        )
    
    return logger.bind(name=name or __name__)

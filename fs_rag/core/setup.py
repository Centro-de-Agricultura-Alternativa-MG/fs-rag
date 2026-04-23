"""Setup and utility functions."""

import subprocess
import sys
from pathlib import Path

from fs_rag.core import get_logger

logger = get_logger(__name__)


def install_dependencies() -> bool:
    """Install required dependencies."""
    logger.info("Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        logger.info("Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install dependencies: {e}")
        return False


def setup_environment() -> bool:
    """Setup environment and create necessary directories."""
    logger.info("Setting up environment...")
    try:
        from fs_rag.core import get_config
        config = get_config()
        config.ensure_dirs()
        logger.info("Environment setup complete")
        return True
    except Exception as e:
        logger.error(f"Failed to setup environment: {e}")
        return False


def verify_setup() -> bool:
    """Verify all dependencies are available."""
    logger.info("Verifying setup...")

    try:
        # Try importing all major dependencies
        import chromadb
        import qdrant_client
        import PyPDF2
        import docx
        import pandas
        import click
        from fastapi import FastAPI
        from openai import OpenAI

        logger.info("All dependencies verified")
        return True
    except ImportError as e:
        logger.warning(f"Missing optional dependency: {e}")
        return False

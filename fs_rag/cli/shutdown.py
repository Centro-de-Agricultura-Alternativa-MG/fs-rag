"""Graceful shutdown utilities for async feedback processing."""

import time
import threading
from typing import Optional

from fs_rag.core import get_config, get_logger

logger = get_logger(__name__)


def wait_for_feedback_processing(timeout: float = 5.0) -> bool:
    """
    Wait for any pending feedback processing threads to complete.

    This should be called before exiting the CLI to ensure async feedback
    indexing has a chance to complete.

    Args:
        timeout: Maximum time to wait in seconds

    Returns:
        True if all threads completed, False if timeout
    """
    config = get_config()

    # If feedback is disabled or sync processing is off, no need to wait
    if not config.knowledge_feedback_enabled:
        return True

    if not config.knowledge_feedback_async_processing:
        return True

    logger.debug(f"Waiting for feedback processing (timeout: {timeout}s)...")

    start_time = time.time()
    check_interval = 0.1

    while time.time() - start_time < timeout:
        # Get all daemon threads
        daemon_threads = [t for t in threading.enumerate() if t.daemon]

        # Filter to feedback processor threads (they have a specific naming pattern)
        feedback_threads = [
            t for t in daemon_threads
            if "Thread" in t.name or "feedback" in t.name.lower()
        ]

        if not feedback_threads:
            logger.debug("All feedback threads completed")
            return True

        logger.debug(
            f"Waiting for {len(feedback_threads)} feedback thread(s)... "
            f"({time.time() - start_time:.1f}s elapsed)"
        )

        time.sleep(check_interval)

    logger.warning(
        f"Feedback processing timeout after {timeout}s. "
        "Some feedback may not be indexed."
    )
    return False


def graceful_exit(exit_code: int = 0, wait_feedback: bool = True) -> None:
    """
    Exit gracefully, optionally waiting for feedback processing.

    Use this instead of exit() in CLI commands to ensure async feedback
    has time to complete.

    Args:
        exit_code: Exit code to return
        wait_feedback: Whether to wait for feedback processing (default: True)
    """
    if wait_feedback:
        wait_for_feedback_processing()

    exit(exit_code)


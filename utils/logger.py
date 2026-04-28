"""
Logger Utility
==============
Configures a consistent, coloured logger used across all modules.
"""

import logging
import sys
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# ANSI colour codes
_COLOURS = {
    "DEBUG": "\033[36m",     # Cyan
    "INFO": "\033[32m",      # Green
    "WARNING": "\033[33m",   # Yellow
    "ERROR": "\033[31m",     # Red
    "CRITICAL": "\033[35m",  # Magenta
    "RESET": "\033[0m",
}


class _ColourFormatter(logging.Formatter):
    """Formatter that injects ANSI colour codes for console output."""

    FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    DATEFMT = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        colour = _COLOURS.get(record.levelname, _COLOURS["RESET"])
        reset = _COLOURS["RESET"]
        formatter = logging.Formatter(
            fmt=f"{colour}{self.FMT}{reset}",
            datefmt=self.DATEFMT,
        )
        return formatter.format(record)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger with both console and file handlers.

    Args:
        name: Usually __name__ of the calling module.

    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger(name)

    # Only configure once
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Console handler (coloured)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_ColourFormatter())

    # File handler (plain text, DEBUG level)
    fh = logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger

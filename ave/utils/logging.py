from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.logging import RichHandler


class AveFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone()
        return timestamp.isoformat(timespec="seconds")

    def format(self, record: logging.LogRecord) -> str:
        original_name = record.name
        if record.name.startswith("ave."):
            record.name = record.name.split(".", 1)[1]
        try:
            return super().format(record)
        finally:
            record.name = original_name


def setup_logging(
    verbose: bool = False,
    debug: bool = False,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    logger = logging.getLogger("ave")
    logger.handlers.clear()
    logger.propagate = False

    level = logging.WARNING
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO

    logger.setLevel(level)

    formatter = AveFormatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
    )

    console_handler = RichHandler(markup=False, show_time=False, show_level=False, show_path=False)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file is not None:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ave.{name}")

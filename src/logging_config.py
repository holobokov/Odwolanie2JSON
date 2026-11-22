from __future__ import annotations

import logging
import os
import sys
import json
from typing import Any
from logging.handlers import RotatingFileHandler
from pathlib import Path


def log_intermediate(logger: logging.Logger, label: str, value: Any) -> None:
    """Log intermediate command/text data locally, unless text logging is disabled."""
    if os.getenv("LOG_INTERMEDIATE", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, indent=2)
    else:
        rendered = str(value)
    if not rendered:
        rendered = "(puste)"
    logger.info("%s:\n%s", label, rendered)


def configure_logging(log_level: str | int = "INFO") -> Path:
    """Configure console and rotating file logging for CLI and Streamlit."""
    level = (
        getattr(logging, str(log_level).upper())
        if isinstance(log_level, str)
        else log_level
    )
    log_directory = Path(os.getenv("LOG_DIR", "./logs"))
    log_directory.mkdir(parents=True, exist_ok=True)
    log_file = log_directory / "odwolania2json.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)

    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logging.captureWarnings(True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    return log_file

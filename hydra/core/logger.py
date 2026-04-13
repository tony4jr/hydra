"""Structured JSON logger using rich."""

import logging
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from hydra.core.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log["error"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(f"hydra.{name}")

    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    # Console — human readable
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)-7s %(name)s | %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(console)

    # File — JSON lines
    log_dir: Path = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_dir / f"{name}.log", encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    logger.addHandler(fh)

    return logger

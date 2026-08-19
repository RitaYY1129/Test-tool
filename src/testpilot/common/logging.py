from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(directory: str | Path) -> Path:
    target = Path(directory) 
    target.mkdir(parents=True, exist_ok=True)
    log_path = target / "testpilot.log"
    root = logging.getLogger()
    if not root.handlers:
        root.setLevel(logging.INFO)
        handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    return log_path

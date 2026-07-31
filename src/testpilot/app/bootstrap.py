from __future__ import annotations

import os
from pathlib import Path

from testpilot.storage.database import Database
from testpilot.common.logging import configure_logging


def default_data_dir() -> Path:
    root = os.getenv("LOCALAPPDATA")
    return (Path(root) if root else Path.home() / ".testpilot-ai") / "TestPilotAI"


def build_main_window():
    from testpilot.ui.main_window import MainWindow

    data_dir = default_data_dir()
    configure_logging(data_dir / "logs")
    database = Database(data_dir / "testpilot.db")
    return MainWindow(database)

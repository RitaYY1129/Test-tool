from __future__ import annotations

import sys
import logging


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print('缺少 PySide6，请先运行: pip install -e ".[dev]"', file=sys.stderr)
        return 1

    from testpilot.app.bootstrap import build_main_window
    from testpilot.ui.theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName("TestPilot AI")
    apply_theme(app)
    window = build_main_window()
    def handle_exception(exc_type, exc_value, traceback):
        logging.getLogger("testpilot").exception("未处理异常", exc_info=(exc_type, exc_value, traceback))
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(window, "TestPilot AI", f"发生未处理异常：{exc_value}")
    sys.excepthook = handle_exception
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

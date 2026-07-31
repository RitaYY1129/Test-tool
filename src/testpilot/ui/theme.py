from __future__ import annotations

BLUE_WHITE_THEME = """
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
    color: #1e293b;
}
QMainWindow, QWidget#AppRoot {
    background: #f3f7fc;
}
QWidget#Sidebar {
    background: #0b3b78;
    border: none;
}
QLabel#Brand {
    color: white;
    font-size: 21px;
    font-weight: 700;
    padding: 24px 20px 4px 20px;
}
QLabel#BrandSub {
    color: #b9d6ff;
    font-size: 11px;
    padding: 0 20px 18px 20px;
}
QToolButton#SidebarToggle {
    color: white;
    background: #174f91;
    border: 1px solid #2c64a2;
    border-radius: 7px;
    width: 32px;
    height: 30px;
    font-size: 17px;
}
QToolButton#SidebarToggle:hover {
    background: #2462a7;
}
QWidget#MenuContainer, QWidget#MenuGroup, QWidget#Submenu {
    background: transparent;
}
QToolButton#MenuHeader {
    color: #84add9;
    background: transparent;
    border: none;
    min-height: 36px;
    padding: 0 10px;
    text-align: left;
    font-size: 11px;
    font-weight: 700;
}
QToolButton#MenuHeader:hover {
    color: #dcecff;
    background: #174f91;
    border-radius: 9px;
}
QPushButton#NavItem {
    color: #d8eaff;
    background: transparent;
    border: none;
    border-radius: 10px;
    min-height: 42px;
    padding: 0 14px;
    text-align: left;
    font-weight: 500;
}
QPushButton#NavItem:hover {
    color: white;
    background: #1c5598;
    border: none;
}
QPushButton#NavItem[active="true"] {
    color: white;
    background: #082f63;
    border: 1px solid #275d9c;
    font-weight: 700;
}
QTreeWidget#Navigation {
    background: transparent;
    border: none;
    outline: none;
    padding: 8px 10px;
}
QTreeWidget#Navigation::item {
    color: #dbeafe;
    border-radius: 8px;
    padding: 13px 14px;
    margin: 3px 0;
}
QTreeWidget#Navigation::item:hover {
    background: #174f91;
    color: white;
}
QTreeWidget#Navigation::item:selected {
    background: #ffffff;
    color: #0b4ea2;
    font-weight: 600;
}
QTreeWidget#Navigation::branch {
    background: #0b3b78;
}
QWidget#ContentPage {
    background: transparent;
}
QLabel#PageTitle {
    color: #0f2f57;
    font-size: 24px;
    font-weight: 700;
}
QLabel#PageSubtitle {
    color: #64748b;
    font-size: 12px;
}
QLabel#ContextBanner {
    background: #e8f2ff;
    color: #245b94;
    border: 1px solid #c7def8;
    border-radius: 8px;
    padding: 10px 12px;
    font-weight: 600;
}
QFrame#Card, QGroupBox {
    background: white;
    border: 1px solid #dce7f5;
    border-radius: 12px;
}
QGroupBox {
    margin-top: 10px;
    padding: 16px 12px 12px 12px;
    font-weight: 600;
    color: #23466e;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
}
QPushButton {
    min-height: 34px;
    padding: 0 15px;
    border-radius: 7px;
    border: 1px solid #b9cce5;
    background: #ffffff;
    color: #1c4f86;
    font-weight: 600;
}
QPushButton:hover {
    background: #edf5ff;
    border-color: #77a9e6;
}
QPushButton:pressed {
    background: #dcecff;
}
QPushButton[primary="true"] {
    color: white;
    background: #1677e8;
    border-color: #1677e8;
}
QPushButton[primary="true"]:hover {
    background: #0867cf;
}
QPushButton[danger="true"] {
    color: #c53030;
    border-color: #f1b5b5;
    background: #fffafa;
}
QLineEdit, QTextEdit, QComboBox, QSpinBox {
    background: white;
    border: 1px solid #cbd9eb;
    border-radius: 7px;
    padding: 7px 9px;
    selection-background-color: #2b82e8;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #2b82e8;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QTableWidget {
    background: white;
    alternate-background-color: #f6f9fd;
    border: 1px solid #dce7f5;
    border-radius: 9px;
    gridline-color: #e8eef7;
    selection-background-color: #d9ebff;
    selection-color: #143b67;
}
QTreeWidget {
    background: white;
    alternate-background-color: #f6f9fd;
    border: 1px solid #dce7f5;
    border-radius: 9px;
    selection-background-color: #d9ebff;
    selection-color: #143b67;
    padding: 5px;
}
QTreeWidget::item {
    min-height: 28px;
}
QTableWidget::item {
    padding: 8px;
    border: none;
}
QTabWidget::pane {
    background: #ffffff;
    border: 1px solid #d7e3f4;
    border-radius: 10px;
    top: -1px;
}
QTabBar::tab {
    background: #eaf2ff;
    color: #48617f;
    border: 1px solid #d7e3f4;
    padding: 10px 18px;
    margin-right: 4px;
    min-width: 130px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QTabBar::tab:hover {
    background: #dceaff;
    color: #165db5;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #0b5fc6;
    font-weight: 700;
    border-bottom-color: #ffffff;
}
QHeaderView::section {
    background: #eaf2fc;
    color: #244d78;
    border: none;
    border-bottom: 1px solid #cedcee;
    padding: 10px 8px;
    font-weight: 700;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #bfd0e5;
    border-radius: 5px;
    min-height: 32px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QProgressBar {
    height: 10px;
    border: none;
    border-radius: 5px;
    background: #dce7f5;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    border-radius: 5px;
    background: #2383ed;
}
QCheckBox {
    spacing: 8px;
    color: #385675;
}
QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border: 1px solid #a9bfd9;
    border-radius: 4px;
    background: white;
}
QCheckBox::indicator:checked {
    background: #1677e8;
    border-color: #1677e8;
}
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #dce7f5;
    color: #5b718b;
}
QSplitter::handle {
    background: #e4ecf6;
    width: 2px;
}
"""


def apply_theme(app) -> None:
    from pathlib import Path
    from PySide6.QtGui import QFont, QFontDatabase

    windows_font = Path("C:/Windows/Fonts/msyh.ttc")
    if windows_font.exists():
        QFontDatabase.addApplicationFont(str(windows_font))
        app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyle("Fusion")
    app.setStyleSheet(BLUE_WHITE_THEME)

from __future__ import annotations

BLUE_WHITE_THEME = """
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
    color: #1e293b;
}
QMainWindow, QWidget#AppRoot {
    background: #f6f8fb;
}
QWidget#Sidebar {
    background: #0f3154;
    border: none;
}
QLabel#BrandMark {
    color: white;
    background: #1677e8;
    border-radius: 5px;
    min-width: 28px;
    min-height: 28px;
    max-width: 28px;
    max-height: 28px;
    qproperty-alignment: AlignCenter;
    font-size: 14px;
    font-weight: 700;
}
QLabel#Brand {
    color: white;
    font-size: 15px;
    font-weight: 600;
    padding-left: 7px;
}
QLabel#BrandSub {
    color: #8fa2b8;
    font-size: 11px;
    padding: 3px 18px 15px 53px;
}
QToolButton#SidebarToggle {
    background: transparent;
    border: none;
    border-radius: 6px;
    width: 28px;
    height: 28px;
}
QWidget#ContentShell {
    background: #f5f7fa;
}
QFrame#TopBar {
    background: #ffffff;
    border: none;
    border-bottom: 1px solid #e4e9f0;
    min-height: 52px;
    max-height: 52px;
}
QToolButton#TopMenuToggle {
    color: #526375;
    background: transparent;
    border: none;
    border-radius: 4px;
    min-width: 30px;
    min-height: 30px;
    font-size: 17px;
}
QToolButton#TopMenuToggle:hover {
    color: #1677e8;
    background: #edf6ff;
}
QLabel#Breadcrumb {
    color: #697b8e;
    font-size: 13px;
}
QLabel#HeaderStatus {
    color: #6c7d8f;
    font-size: 12px;
}
QLabel#HeaderAvatar {
    color: #ffffff;
    background: #1677e8;
    border-radius: 15px;
    min-width: 30px;
    min-height: 30px;
    max-width: 30px;
    max-height: 30px;
    qproperty-alignment: AlignCenter;
    font-size: 10px;
    font-weight: 700;
}
QPushButton#QuickAIButton {
    min-height: 30px;
    padding: 0 12px;
    color: #1677e8;
    background: #edf6ff;
    border: 1px solid #c9e1fb;
}
QWidget#WorkspaceBody {
    background: #f6f8fb;
}
QFrame#QuickAIPanel {
    background: #ffffff;
    border-left: 1px solid #dfe6ee;
}
QLabel#QuickAITitle {
    color: #1f3449;
    font-size: 16px;
    font-weight: 700;
}
QLabel#ShortcutBadge {
    color: #52708f;
    background: #eef3f8;
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 11px;
}
QLabel#QuickAIContext {
    color: #718399;
    padding-bottom: 8px;
}
QLabel#QuickAISectionLabel {
    color: #52677c;
    font-size: 12px;
    font-weight: 600;
}
QToolButton#QuickAIClose {
    border: none;
    background: transparent;
    color: #6c7d90;
    font-size: 22px;
    min-width: 28px;
    min-height: 28px;
}
QTextEdit#QuickAIHistory {
    background: #f8fafc;
    border: 1px solid #e3e9f0;
    border-radius: 8px;
    padding: 12px;
}
QTextEdit#QuickAIInput {
    background: white;
    border: 1px solid #b8d4f2;
    border-radius: 8px;
    padding: 10px;
}
QSplitter#AIWorkspace::handle {
    background: #e5eaf0;
    width: 1px;
}
QFrame#AIConversationRail {
    background: #f7f9fc;
    border: 1px solid #e1e7ee;
    border-radius: 8px;
}
QPushButton#NewAIConversation {
    min-height: 42px;
    color: #1677e8;
    background: #ffffff;
    border: 1px solid #cddff2;
    border-radius: 8px;
}
QLabel#AIRailTitle {
    color: #53687e;
    font-weight: 600;
    padding-top: 8px;
}
QTextEdit#AISessionSummary {
    background: transparent;
    border: none;
    color: #64778b;
    padding: 4px;
}
QLabel#AIShortcutHelp {
    color: #8493a5;
    background: #eef3f8;
    border-radius: 6px;
    padding: 10px;
    font-size: 11px;
}
QFrame#AIChatMain {
    background: #ffffff;
    border: 1px solid #e1e7ee;
    border-radius: 8px;
}
QLabel#AIWelcome {
    color: #1b3045;
    font-size: 22px;
    font-weight: 700;
    padding-top: 4px;
}
QLabel#AIWelcomeHint {
    color: #7a899a;
    font-size: 13px;
}
QPushButton#AITemplateButton {
    color: #316da9;
    background: #f4f8fd;
    border: 1px solid #d8e5f3;
    border-radius: 16px;
    min-height: 32px;
    padding: 0 14px;
}
QFrame#AIComposer {
    background: #ffffff;
    border: 1px solid #b9d3ef;
    border-radius: 10px;
}
QTextEdit#AIComposerInput {
    background: transparent;
    border: none;
    padding: 8px;
}
QTextEdit#AIChatHistory, QTextEdit#AIArtifactView {
    border: none;
    background: #ffffff;
    padding: 14px;
}
QTextEdit:read-only {
    background: #f7f9fc;
    color: #52677c;
}
QStackedWidget#ContentStack {
    background: #f5f7fa;
}
QToolButton#SidebarToggle:hover {
    background: #173252;
}
QScrollArea#MenuScroll, QWidget#MenuContainer, QWidget#MenuGroup {
    background: transparent;
    border: none;
}
QWidget#Submenu {
    background: #0c2948;
    border: none;
}
QWidget#RouteSubmenu {
    background: #08233e;
    border-left: none;
    margin-left: 0;
}
QToolButton#MenuHeader {
    color: #d0d9e3;
    background: transparent;
    border: none;
    min-height: 48px;
    padding: 0 18px;
    text-align: left;
    font-size: 14px;
    font-weight: 500;
}
QToolButton#MenuHeader[expanded="true"] {
    color: #d0d9e3;
    background: transparent;
}
QToolButton#MenuHeader[active="true"] {
    color: #3395ff;
    background: transparent;
    font-weight: 600;
}
QToolButton#MenuHeader:checked {
    color: #3395ff;
    background: transparent;
    font-weight: 600;
}
QToolButton#RouteHeader {
    color: #c5d0dc;
    background: transparent;
    border: none;
    min-height: 46px;
    padding: 0 30px;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
}
QToolButton#RouteHeader[expanded="true"] {
    color: #d7e1ec;
    background: transparent;
    border-radius: 0;
}
QPushButton#NavItem {
    color: #b7c5d4;
    background: transparent;
    border: none;
    border-radius: 0;
    min-height: 46px;
    padding: 0 18px;
    text-align: left;
    font-size: 14px;
    font-weight: 400;
}
QPushButton#NavItem[depth="root"] {
    min-height: 48px;
    padding-left: 18px;
    color: #d0d9e3;
    font-size: 14px;
    font-weight: 500;
}
QPushButton#NavItem[depth="root"][active="true"] {
    color: #3395ff;
    background: transparent;
    font-weight: 600;
}
QPushButton#NavItem[depth="root"]:checked,
QPushButton#NavItem:checked {
    color: #3395ff;
    background: transparent;
    font-weight: 600;
}
QPushButton#NavItem[depth="third"] {
    min-height: 44px;
    padding-left: 44px;
    color: #b9c6d3;
    font-size: 14px;
    font-weight: 400;
}
QPushButton#NavItem[depth="second"] {
    min-height: 46px;
    padding-left: 30px;
    color: #c5d0dc;
    font-size: 14px;
}
QPushButton#NavItem[active="true"] {
    color: #3395ff;
    background: transparent;
    border: none;
    margin: 0;
    font-weight: 600;
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
    background: #f6f8fb;
}
QLabel#PageTitle {
    color: #26384a;
    font-size: 20px;
    font-weight: 600;
}
QLabel#PageSubtitle {
    color: #64748b;
    font-size: 12px;
}
QLabel#ContextBanner {
    background: #ffffff;
    color: #52677c;
    border: 1px solid #e2e8f0;
    border-left: 3px solid #1677e8;
    border-radius: 3px;
    padding: 9px 12px;
    font-weight: 500;
}
QFrame#Card, QGroupBox {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
}
QGroupBox {
    margin-top: 10px;
    padding: 16px 12px 12px 12px;
    font-weight: 600;
    color: #334a60;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
}
QPushButton {
    min-height: 34px;
    padding: 0 15px;
    border-radius: 4px;
    border: 1px solid #d5dde7;
    background: #ffffff;
    color: #40566d;
    font-weight: 500;
}
QPushButton:hover {
    background: #f2f7fd;
    border-color: #91b9e8;
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
    border: 1px solid #d9e0e8;
    border-radius: 4px;
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
    alternate-background-color: #fafbfd;
    border: 1px solid #e1e6ec;
    border-radius: 3px;
    gridline-color: #edf0f4;
    selection-background-color: #e9f3ff;
    selection-color: #143b67;
}
QTreeWidget {
    background: white;
    alternate-background-color: #f6f9fd;
    border: 1px solid #e1e6ec;
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
    background: #f5f7fa;
    color: #40566d;
    border: none;
    border-bottom: 1px solid #e1e6ec;
    padding: 10px 8px;
    font-weight: 600;
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

from __future__ import annotations

import html
import json
import shutil
import subprocess
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from urllib.parse import urlparse

from PySide6.QtCore import QByteArray, Qt, QProcess, QSize, QObject, QRunnable, QThreadPool, Signal, Slot, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QIcon, QPainter, QPixmap, QKeySequence, QShortcut
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QScrollArea, QSpinBox, QStackedWidget, QStyle, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from testpilot.engines.http_engine import execute_request
from testpilot.cases.generator import generate_cases, generate_plan
from testpilot.engines.batch_runner import run_cases
from testpilot.engines.workflow_runner import SqliteTestDatabase, run_workflow
from testpilot.engines.ai_dialogue import ControlledDialogue
from testpilot.engines.database_observer import inspect_sqlite_database
from testpilot.engines.database_adapters import create_database_adapter
from testpilot.engines.runtime_trace import TraceCollector
from testpilot.reports.difference import build_combined_difference, generate_difference_report
from testpilot.engines.replay_package import export_replay_package
from testpilot.domain.flow import build_flow_model, validate_flow_model
from testpilot.domain.process_script import build_process_script, evaluate_process_script, validate_process_script
from testpilot.parsers.completeness_checker import check_completeness
from testpilot.parsers.openapi_parser import OpenApiParser, OpenApiParseError
from testpilot.parsers.postman_parser import PostmanParser
from testpilot.parsers.curl_parser import parse_curl
from testpilot.parsers.backend_source_parser import BackendSourceParser
from testpilot.parsers.har_parser import HarParser
from testpilot.parsers.document_parser import DocumentParser
from testpilot.parsers.apifox_parser import ApifoxParser
from testpilot.parsers.postman_parser import parse_postman_environment
from testpilot.reports.generator import generate_report
from testpilot.engines.workflow_report import generate_workflow_report
from testpilot.common.security import SecretStore, split_sensitive
from testpilot.cases.schema import TEST_GENERATION_SCHEMA, validate_generation
from testpilot.model_providers.openai_compatible import OpenAICompatibleProvider
from testpilot.model_providers.codex_cli import CodexCliProvider, find_codex
from testpilot.model_providers.ollama import OllamaProvider
from testpilot.model_providers.resilience import AIRequestCancelled
from testpilot.parsers.difference_checker import compare_documents
from testpilot.domain.api import ApiDocument, ApiEndpoint, ApiParameter


WORKFLOW_GENERATION_SCHEMA = {
    "type": "object",
    "required": ["name", "data_flows", "database_changes", "test_focus", "steps"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "data_flows": {"type": "array"},
        "database_changes": {"type": "array"},
        "test_focus": {"type": "array"},
        "steps": {"type": "array", "minItems": 1},
        "invariants": {"type": "array"},
        "failure_scenarios": {"type": "array"},
    },
}


class _AIWorkerSignals(QObject):
    completed = Signal(object, object, object)
    failed = Signal(object, object)


class _ChatTranscript(QScrollArea):
    """Native Qt chat bubbles; avoids QTextEdit's limited HTML/CSS support."""

    def __init__(self):
        super().__init__()
        self.setObjectName("AIChatTranscript")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(18, 18, 18, 18)
        self._layout.setSpacing(10)
        self.setWidget(self._content)

    def clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def render(self, messages: list[dict], pending_message: str = "", assistant_notice: str = ""):
        self.clear()
        for item in messages:
            self._add_bubble(str(item.get("content", "")), item.get("role") == "user", item.get("role", "assistant"))
        if pending_message:
            self._add_bubble(pending_message, True, "user")
            self._add_bubble("正在思考…", False, "assistant", pending=True)
        if assistant_notice:
            self._add_bubble(assistant_notice, False, "assistant", notice=True)
        self._layout.addStretch(1)
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))

    def _add_bubble(self, text: str, is_user: bool, role: str, pending: bool = False, notice: bool = False):
        row = QWidget(); row_layout = QHBoxLayout(row); row_layout.setContentsMargins(0, 0, 0, 0); row_layout.setSpacing(8)
        bubble = QLabel(text); bubble.setWordWrap(True); bubble.setMaximumWidth(650); bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if is_user:
            bubble.setStyleSheet("background:#1677ff;color:#fff;border-radius:14px;padding:10px 13px;font-size:14px;")
            row_layout.addStretch(1); row_layout.addWidget(bubble)
        else:
            prefix = "AI\n" if role == "assistant" else "系统\n"
            bubble.setText(prefix + text)
            color = "#fff7e6" if notice else "#f3f6fa"
            text_color = "#8a5b00" if notice else "#20334d"
            opacity = "color:#8a98aa;" if pending else f"color:{text_color};"
            bubble.setStyleSheet(f"background:{color};{opacity}border-radius:14px;padding:10px 13px;font-size:14px;")
            row_layout.addWidget(bubble); row_layout.addStretch(1)
        self._layout.addWidget(row)


class _AIWorker(QRunnable):
    def __init__(self, dialogue, message: str, context: dict, request_id: int):
        super().__init__()
        self.dialogue = dialogue
        self.message = message
        self.context = context
        self.request_id = request_id
        self.signals = _AIWorkerSignals()
        self.setAutoDelete(False)

    @Slot()
    def run(self):
        try:
            result = self.dialogue.send(self.message, self.context)
            self.signals.completed.emit(self.request_id, self.dialogue, result)
        except Exception as exc:
            self.signals.failed.emit(self.request_id, exc)


class _CaseRunSignals(QObject):
    progressed = Signal(object)
    completed = Signal(object, object)
    failed = Signal(object)


class _CaseRunWorker(QRunnable):
    """Runs HTTP cases outside the Qt UI thread while keeping cancellation cooperative."""

    def __init__(self, cases: list[dict], base_url: str, headers: dict, variables: dict,
                 stop_event: Event, max_workers: int):
        super().__init__()
        self.cases = cases
        self.base_url = base_url
        self.headers = headers
        self.variables = variables
        self.stop_event = stop_event
        self.max_workers = max_workers
        self.signals = _CaseRunSignals()
        self.setAutoDelete(False)

    @Slot()
    def run(self):
        try:
            results, summary = run_cases(
                self.cases, self.base_url, self.headers,
                on_result=self.signals.progressed.emit, variables=self.variables,
                stop_event=self.stop_event, max_workers=self.max_workers,
            )
            self.signals.completed.emit(results, summary)
        except Exception as exc:
            self.signals.failed.emit(exc)


class MainWindow(QMainWindow):
    def __init__(self, database):
        super().__init__()
        self.db = database
        self.secret_store = SecretStore(self.db.path.parent / "config" / "master.key")
        self.current_project_id: int | None = None
        self._ai_thread_pool = QThreadPool.globalInstance()
        self._ai_busy = False
        self._active_ai_worker = None
        self._ai_workers = {}
        self._ai_cancel_event = None
        self._ai_request_id = 0
        self._case_run_worker = None
        self._case_run_id = None
        self._case_run_cases = []
        self._case_run_completed = 0
        self._last_failed_case_ids = []
        self.setWindowTitle("TestPilot AI · 第一阶段")
        self.resize(1280, 780)
        self._build()
        self.refresh_projects()

    def _build(self):
        root = QWidget()
        root.setObjectName("AppRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QWidget()
        self.sidebar = sidebar
        sidebar.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 18)
        sidebar_layout.setSpacing(0)
        self.sidebar_toggle = QToolButton()
        self.sidebar_toggle.setObjectName("SidebarToggle")
        self.sidebar_toggle.setIcon(self.style().standardIcon(QStyle.SP_ArrowLeft))
        self.sidebar_toggle.setToolTip("收缩/展开侧边栏")
        self.sidebar_toggle.clicked.connect(self.toggle_sidebar)
        self.sidebar_toggle.setVisible(False)
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(18, 16, 14, 0)
        self.brand_mark = QLabel("T")
        self.brand_mark.setObjectName("BrandMark")
        self.brand = QLabel("TestPilot AI")
        self.brand.setObjectName("Brand")
        brand_row.addWidget(self.brand_mark)
        brand_row.addWidget(self.brand)
        brand_row.addStretch()
        self.brand_sub = QLabel("测试管理系统")
        self.brand_sub.setObjectName("BrandSub")
        self.menu_container = QWidget()
        self.menu_container.setObjectName("MenuContainer")
        self.menu_layout = QVBoxLayout(self.menu_container)
        self.menu_layout.setContentsMargins(0, 6, 0, 8)
        self.menu_layout.setSpacing(0)
        self.menu_scroll = QScrollArea()
        self.menu_scroll.setObjectName("MenuScroll")
        self.menu_scroll.setWidgetResizable(True)
        self.menu_scroll.setFrameShape(QFrame.NoFrame)
        self.menu_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.menu_scroll.setWidget(self.menu_container)
        self._nav_buttons = {}
        self._menu_groups = []
        self._primary_headers = []
        self._route_headers = []
        self._active_route = "路线 A · 源码驱动"
        self._sidebar_icon_cache = {}
        self._add_sidebar_entry("首页", 0, QStyle.SP_DirHomeIcon)
        self._add_nested_sidebar_group("接口测试", QStyle.SP_ComputerIcon, [
            ("路线 A · 源码驱动", QStyle.SP_FileDialogContentsView, [
                ("接口查看", 1, QStyle.SP_FileDialogDetailedView),
                ("业务流程与数据流", 7, QStyle.SP_FileDialogInfoView),
                ("环境与请求", 2, QStyle.SP_DriveNetIcon),
                ("测试用例与执行", 3, QStyle.SP_MediaPlay),
            ]),
            ("路线 B · 资料驱动", QStyle.SP_FileDialogContentsView, [
                ("接口资料与资产", 1, QStyle.SP_FileDialogDetailedView),
                ("环境与请求", 2, QStyle.SP_DriveNetIcon),
                ("测试用例与执行", 3, QStyle.SP_MediaPlay),
            ]),
        ], direct_entries=[
            ("历史报告", 4, QStyle.SP_FileDialogInfoView),
        ])
        self._add_sidebar_group("系统配置", QStyle.SP_FileDialogInfoView, [
            ("AI 写作中心", 8, QStyle.SP_MessageBoxInformation, lambda: self._activate_ai_hub_tab(0)),
        ])
        self._add_sidebar_entry("能力中心", 5, QStyle.SP_FileDialogListView)
        self.menu_layout.addStretch()
        sidebar.setFixedWidth(208)
        sidebar_layout.addLayout(brand_row)
        sidebar_layout.addWidget(self.brand_sub)
        sidebar_layout.addWidget(self.menu_scroll, 1)
        content_shell = QWidget()
        content_shell.setObjectName("ContentShell")
        content_layout = QVBoxLayout(content_shell)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        topbar = QFrame(); topbar.setObjectName("TopBar")
        topbar_layout = QHBoxLayout(topbar); topbar_layout.setContentsMargins(18, 0, 18, 0)
        topbar_layout.setSpacing(10)
        self.top_menu_toggle = QToolButton(); self.top_menu_toggle.setObjectName("TopMenuToggle")
        self.top_menu_toggle.setIcon(self._sidebar_icon("menu")); self.top_menu_toggle.setIconSize(QSize(18, 18)); self.top_menu_toggle.setToolTip("收缩/展开侧边栏")
        self.top_menu_toggle.clicked.connect(self.toggle_sidebar)
        self.breadcrumb = QLabel("首页  /  项目中心"); self.breadcrumb.setObjectName("Breadcrumb")
        self.header_status = QLabel("●  本地工作台"); self.header_status.setObjectName("HeaderStatus")
        self.header_avatar = QLabel("TP"); self.header_avatar.setObjectName("HeaderAvatar")
        self.quick_ai_button = QPushButton("AI 助手"); self.quick_ai_button.setObjectName("QuickAIButton")
        self.quick_ai_button.setToolTip("打开 AI 辅助侧栏（Ctrl+K）"); self.quick_ai_button.clicked.connect(self.toggle_ai_assistant)
        topbar_layout.addWidget(self.top_menu_toggle); topbar_layout.addWidget(self.breadcrumb)
        topbar_layout.addStretch(); topbar_layout.addWidget(self.quick_ai_button); topbar_layout.addWidget(self.header_status); topbar_layout.addWidget(self.header_avatar)
        self.pages = QStackedWidget()
        self.pages.setObjectName("ContentStack")
        self.pages.addWidget(self._project_page())
        self.pages.addWidget(self._endpoint_page())
        self.pages.addWidget(self._request_page())
        self.pages.addWidget(self._cases_page())
        self.pages.addWidget(self._reports_page())
        self.pages.addWidget(self._capability_page())
        self.pages.addWidget(QWidget())  # Page 6 is retained for saved navigation compatibility.
        self.pages.addWidget(self._workflow_page())
        self.pages.addWidget(self._ai_hub_page())
        self._activate_page(0)
        self.quick_ai_panel = self._quick_ai_sidebar()
        body = QWidget(); body.setObjectName("WorkspaceBody")
        body_layout = QHBoxLayout(body); body_layout.setContentsMargins(0, 0, 0, 0); body_layout.setSpacing(0)
        body_layout.addWidget(self.pages, 1); body_layout.addWidget(self.quick_ai_panel)
        content_layout.addWidget(topbar)
        content_layout.addWidget(body, 1)
        layout.addWidget(sidebar)
        layout.addWidget(content_shell, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("就绪")
        self._sidebar_collapsed = False
        self.ai_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.ai_shortcut.activated.connect(self.toggle_ai_assistant)

    def _add_sidebar_entry(self, text, page_index, item_icon):
        button = QPushButton(f"  {text}")
        button.setObjectName("NavItem")
        button.setCheckable(True)
        button.setProperty("depth", "root")
        button.setProperty("menuText", text)
        button.setProperty("iconLabel", text)
        button.setIcon(self._sidebar_icon(text))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(text)
        button.clicked.connect(lambda checked=False, index=page_index: self._activate_primary_page(index))
        self.menu_layout.addWidget(button)
        self._nav_buttons.setdefault(page_index, []).append(button)

    def _add_sidebar_group(self, title, icon, entries):
        group = QWidget()
        group.setObjectName("MenuGroup")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(2)
        header = QToolButton()
        header.setObjectName("MenuHeader")
        header.setCheckable(True)
        header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        header.setIcon(self._sidebar_icon(title))
        header.setIconSize(QSize(18, 18))
        header.setText(f"  {title}")
        header.setProperty("menuText", title)
        header.setProperty("expanded", True)
        header.setProperty("active", False)
        submenu = QWidget()
        submenu.setObjectName("Submenu")
        submenu_layout = QVBoxLayout(submenu)
        submenu_layout.setContentsMargins(0, 2, 0, 0)
        submenu_layout.setSpacing(2)
        for entry in entries:
            text, page_index, item_icon, *custom_action = entry
            button = QPushButton(f"  {text}")
            button.setObjectName("NavItem")
            button.setCheckable(True)
            button.setProperty("depth", "second")
            button.setIcon(self._sidebar_icon(text))
            button.setIconSize(QSize(18, 18))
            button.setProperty("menuText", text)
            button.setProperty("iconLabel", text)
            button.setToolTip(text)
            if custom_action:
                button.clicked.connect(lambda checked=False, action=custom_action[0], control=header: self._activate_primary_action(control, action))
            else:
                button.clicked.connect(lambda checked=False, index=page_index, control=header: self._activate_primary_child(index, control))
            submenu_layout.addWidget(button)
            self._nav_buttons.setdefault(page_index, []).append(button)
        header.clicked.connect(lambda checked=False, panel=submenu, control=header: self._toggle_primary_group(panel, control))
        group_layout.addWidget(header)
        group_layout.addWidget(submenu)
        self.menu_layout.addWidget(group)
        self._menu_groups.append((header, submenu))
        self._primary_headers.append(header)

    def _add_nested_sidebar_group(self, title, icon, routes, direct_entries=None):
        group = QWidget()
        group.setObjectName("MenuGroup")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(2)
        header = QToolButton()
        header.setObjectName("MenuHeader")
        header.setCheckable(True)
        header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        header.setIcon(self._sidebar_icon(title))
        header.setIconSize(QSize(18, 18))
        header.setText(f"  {title}")
        header.setProperty("menuText", title)
        header.setProperty("expanded", True)
        header.setProperty("active", False)
        submenu = QWidget(); submenu.setObjectName("Submenu")
        submenu_layout = QVBoxLayout(submenu)
        submenu_layout.setContentsMargins(0, 2, 0, 0)
        submenu_layout.setSpacing(2)
        for route_title, route_icon, entries in routes:
            route_header = QToolButton()
            route_header.setObjectName("RouteHeader")
            route_header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            route_header.setText(f"  {route_title}")
            route_header.setProperty("menuText", route_title)
            route_header.setProperty("expanded", True)
            route_header.setIcon(self._sidebar_icon(route_title))
            route_header.setIconSize(QSize(18, 18))
            route_panel = QWidget(); route_panel.setObjectName("RouteSubmenu")
            route_layout = QVBoxLayout(route_panel)
            route_layout.setContentsMargins(8, 0, 0, 4)
            route_layout.setSpacing(2)
            for text, page_index, item_icon in entries:
                icon_label = f"{route_title}/{text}"
                button = QPushButton(f"  {text}")
                button.setObjectName("NavItem")
                button.setCheckable(True)
                button.setProperty("depth", "third")
                button.setProperty("route", route_title)
                button.setIcon(self._sidebar_icon(icon_label))
                button.setIconSize(QSize(17, 17))
                button.setProperty("menuText", text)
                button.setProperty("iconLabel", icon_label)
                button.setToolTip(text)
                button.clicked.connect(
                    lambda checked=False, index=page_index, route=route_title, control=header: self._activate_primary_route(index, route, control)
                )
                route_layout.addWidget(button)
                self._nav_buttons.setdefault(page_index, []).append(button)
            route_header.clicked.connect(
                lambda checked=False, panel=route_panel, control=route_header: self._toggle_menu_group(panel, control)
            )
            submenu_layout.addWidget(route_header); submenu_layout.addWidget(route_panel)
            self._route_headers.append(route_header)
        for text, page_index, item_icon in direct_entries or []:
            button = QPushButton(f"  {text}")
            button.setObjectName("NavItem")
            button.setCheckable(True)
            button.setProperty("depth", "second")
            button.setIcon(self._sidebar_icon(text))
            button.setIconSize(QSize(18, 18))
            button.setProperty("menuText", text)
            button.setProperty("iconLabel", text)
            button.setToolTip(text)
            button.clicked.connect(lambda checked=False, index=page_index, control=header: self._activate_primary_child(index, control))
            submenu_layout.addWidget(button)
            self._nav_buttons.setdefault(page_index, []).append(button)
        header.clicked.connect(lambda checked=False, panel=submenu, control=header: self._toggle_primary_group(panel, control))
        group_layout.addWidget(header); group_layout.addWidget(submenu)
        self.menu_layout.addWidget(group)
        self._menu_groups.append((header, submenu))
        self._primary_headers.append(header)

    def _sidebar_icon(self, label: str, active: bool = False) -> QIcon:
        """Return a consistent monochrome line icon for the sidebar."""
        key = "section"
        if label == "首页":
            key = "home"
        elif label == "接口测试":
            key = "test"
        elif "路线 A" in label and "/接口查看" in label:
            key = "endpoint"
        elif "路线 A" in label and "/业务流程" in label:
            key = "workflow"
        elif "路线 A" in label and "/环境" in label:
            key = "env_a"
        elif "路线 A" in label and "/测试用例" in label:
            key = "cases_a"
        elif "路线 B" in label and "/接口资料" in label:
            key = "assets"
        elif "路线 B" in label and "/环境" in label:
            key = "env_b"
        elif "路线 B" in label and "/测试用例" in label:
            key = "cases_b"
        elif label in {"AI 对话", "AI 协作中心"}:
            key = "dialogue"
        elif label in {"AI 模型配置", "AI 模型与连接"}:
            key = "model"
        elif label == "系统配置":
            key = "section"
        elif "项目" in label:
            key = "project"
        elif "源码" in label or "接口查看" in label:
            key = "source"
        elif "资料" in label or "资产" in label:
            key = "document"
        elif "流程" in label or "数据流" in label:
            key = "flow"
        elif "环境" in label:
            key = "environment"
        elif "用例" in label or "执行" in label:
            key = "run"
        elif "报告" in label:
            key = "report"
        elif "AI" in label or "模型" in label:
            key = "ai"
        elif "能力" in label:
            key = "capability"
        cache_key = f"{key}:{'active' if active else 'normal'}"
        if cache_key in self._sidebar_icon_cache:
            return self._sidebar_icon_cache[cache_key]
        paths = {
            "home": "<path d='M4 11l8-7 8 7v9h-6v-6h-4v6H4z'/>",
            "test": "<circle cx='12' cy='12' r='3'/><path d='M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4'/>",
            "endpoint": "<circle cx='6' cy='12' r='2'/><circle cx='18' cy='7' r='2'/><circle cx='18' cy='17' r='2'/><path d='M8 12h4c3 0 3-5 4-5M12 12c3 0 3 5 4 5'/>",
            "workflow": "<circle cx='6' cy='6' r='2'/><circle cx='18' cy='6' r='2'/><circle cx='12' cy='18' r='2'/><path d='M8 6h8M7 8l4 8M17 8l-4 8'/>",
            "env_a": "<circle cx='12' cy='12' r='8'/><path d='M4 12h16M12 4c3 3 3 13 0 16'/>",
            "cases_a": "<path d='M9 3h6M10 3v5l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3'/><path d='M8 15h8'/>",
            "assets": "<path d='M4 6h6l2 2h8v11H4z'/><path d='M8 12h8M8 16h5'/>",
            "env_b": "<path d='M4 18h16M6 18V9h5v9M13 18V5h5v13'/>",
            "cases_b": "<path d='M5 4h14v16H5z'/><path d='M8 9l2 2 4-4M8 15h8'/>",
            "dialogue": "<path d='M4 5h16v11H9l-5 4z'/><path d='M8 10h.01M12 10h.01M16 10h.01'/>",
            "model": "<rect x='5' y='5' width='14' height='14' rx='2'/><path d='M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M19 9h4M1 15h4M19 15h4M9 9h6v6H9z'/>",
            "project": "<path d='M3 7h7l2 2h9v10H3z'/><path d='M3 7V5h7l2 2'/>",
            "source": "<path d='M9 6l-6 6 6 6M15 6l6 6-6 6M14 3l-4 18'/>",
            "document": "<path d='M7 3h12v15H7z'/><path d='M4 6v15h12M10 8h6M10 12h6'/>",
            "flow": "<circle cx='6' cy='6' r='2'/><circle cx='18' cy='6' r='2'/><circle cx='12' cy='18' r='2'/><path d='M8 6h8M6 8l5 8M18 8l-5 8'/>",
            "environment": "<circle cx='12' cy='12' r='8'/><path d='M4 12h16M12 4c3 3 3 13 0 16M12 4c-3 3-3 13 0 16'/>",
            "run": "<path d='M7 4l12 8-12 8z'/>",
            "report": "<path d='M5 3h10l4 4v14H5z'/><path d='M15 3v5h4M8 12h8M8 16h6'/>",
            "ai": "<path d='M7 8h10a4 4 0 0 1 4 4v1a4 4 0 0 1-4 4H9l-4 3 1-4a4 4 0 0 1-3-4v-1a4 4 0 0 1 4-4z'/><path d='M9 12h.01M13 12h.01M17 12h.01'/>",
            "capability": "<rect x='4' y='4' width='6' height='6'/><rect x='14' y='4' width='6' height='6'/><rect x='4' y='14' width='6' height='6'/><rect x='14' y='14' width='6' height='6'/>",
            "section": "<path d='M4 7h16M4 12h16M4 17h16'/>",
        }
        color = "#3395ff" if active else "#aebdce"
        svg = ("<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'>"
               f"<g fill='none' stroke='{color}' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
               + paths[key] + "</g></svg>")
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pixmap = QPixmap(24, 24); pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap); renderer.render(painter); painter.end()
        icon = QIcon(pixmap)
        self._sidebar_icon_cache[cache_key] = icon
        return icon

    @staticmethod
    def _toggle_menu_group(submenu, header):
        submenu.setVisible(not submenu.isVisible())
        header.setProperty("expanded", submenu.isVisible())
        header.style().unpolish(header)
        header.style().polish(header)

    def _set_primary_header_active(self, selected=None):
        for header in self._primary_headers:
            active = header is selected
            header.setProperty("active", active)
            header.setChecked(active)
            header.setIcon(self._sidebar_icon(str(header.property("menuText") or ""), active=active))
            header.style().unpolish(header)
            header.style().polish(header)

    def _clear_nav_button_active(self):
        """Clear stale leaf selection when a collapsible top-level group is selected."""
        for buttons in self._nav_buttons.values():
            for button in buttons:
                button.setProperty("active", False)
                button.setChecked(False)
                button.setIcon(self._sidebar_icon(
                    str(button.property("iconLabel") or button.property("menuText") or ""), active=False
                ))
                button.style().unpolish(button)
                button.style().polish(button)

    def _toggle_primary_group(self, submenu, header):
        self._set_primary_header_active(header)
        self._clear_nav_button_active()
        self._toggle_menu_group(submenu, header)

    def _activate_primary_page(self, page_index: int):
        self._set_primary_header_active()
        self._activate_page(page_index)

    def _activate_primary_child(self, page_index: int, header):
        # A child is the active destination, not its container.  Keeping both
        # checked caused the parent and child to appear selected together.
        self._set_primary_header_active()
        self._activate_page(page_index)

    def _activate_primary_route(self, page_index: int, route: str, header):
        self._set_primary_header_active()
        self._activate_route_page(page_index, route)

    def _activate_primary_action(self, header, action):
        self._set_primary_header_active()
        action()

    def _activate_page(self, page_index):
        # Programmatic jumps (for example “查看接口资产”) must obey the same
        # single-selection rule as a mouse click.
        self._set_primary_header_active()
        self.pages.setCurrentIndex(page_index)
        page_names = {
            0: "项目中心", 1: "接口资产", 2: "环境与请求", 3: "测试用例与执行",
            4: "历史报告", 5: "能力中心", 6: "模型与连接", 7: "业务流程与数据流", 8: "AI 协作中心",
        }
        if hasattr(self, "breadcrumb"):
            section = "系统配置" if page_index == 8 else "接口测试"
            self.breadcrumb.setText(f"首页  /  {section}  /  {page_names.get(page_index, '工作台')}")
        for index, buttons in self._nav_buttons.items():
            for button in buttons:
                route = button.property("route")
                active = index == page_index and (not route or route == self._active_route)
                button.setProperty("active", active)
                button.setChecked(active)
                button.setIcon(self._sidebar_icon(str(button.property("iconLabel") or button.property("menuText") or ""), active=active))
                button.style().unpolish(button)
                button.style().polish(button)

    def _activate_route_page(self, page_index, route):
        self._active_route = route
        self._activate_page(page_index)

    def toggle_sidebar(self):
        self._sidebar_collapsed = not self._sidebar_collapsed
        collapsed = self._sidebar_collapsed
        self.sidebar.setFixedWidth(58 if collapsed else 208)
        self.sidebar_toggle.setIcon(
            self.style().standardIcon(QStyle.SP_ArrowRight if collapsed else QStyle.SP_ArrowLeft)
        )
        self.brand.setVisible(not collapsed)
        self.brand_sub.setVisible(not collapsed)
        self.brand_mark.setVisible(True)
        for header, submenu in self._menu_groups:
            title = str(header.property("menuText") or "")
            header.setText(title[:1] if collapsed else f"  {title}")
            header.setToolButtonStyle(Qt.ToolButtonIconOnly if collapsed else Qt.ToolButtonTextBesideIcon)
            submenu.layout().setContentsMargins(0, 2, 0, 0)
        for buttons in self._nav_buttons.values():
            for button in buttons:
                button.setText("" if collapsed else f"  {button.property('menuText')}")
        for header in self._route_headers:
            title = str(header.property("menuText") or "")
            short = "A" if "路线 A" in title else "B" if "路线 B" in title else title[:1]
            header.setText(short if collapsed else f"  {title}")
            header.setToolButtonStyle(Qt.ToolButtonIconOnly if collapsed else Qt.ToolButtonTextBesideIcon)

    def go_to_page(self, page_index):
        self._activate_page(page_index)

    def _project_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("项目中心"); title.setObjectName("PageTitle")
        mode = QLabel("统一管理多个测试项目，并按资料源、模块和接口查看项目资产")
        mode.setObjectName("PageSubtitle")
        row = QHBoxLayout()
        self.projects = QComboBox(); self.projects.currentIndexChanged.connect(self._project_changed)
        new_btn = QPushButton("新建项目"); new_btn.clicked.connect(self.new_project)
        delete_btn = QPushButton("删除项目"); delete_btn.clicked.connect(self.delete_project)
        self.import_type = QComboBox()
        self.import_type.addItems([
            "OpenAPI / Swagger 文件", "在线 OpenAPI URL", "Postman Collection",
            "Postman Environment", "Apifox 数据", "cURL 命令", "HAR 请求记录",
            "接口文档 / Excel", "后端源码（自动识别）",
        ])
        import_btn = QPushButton("导入资料")
        import_btn.setProperty("primary", True)
        import_btn.clicked.connect(self.import_selected_source)
        compare_btn = QPushButton("对比最近两份资料"); compare_btn.clicked.connect(self.compare_sources)
        new_btn.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        delete_btn.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        import_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        compare_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        row.addWidget(QLabel("当前项目")); row.addWidget(self.projects, 1); row.addWidget(new_btn); row.addWidget(delete_btn)
        import_row = QHBoxLayout()
        import_row.addWidget(QLabel("资料类型"))
        import_row.addWidget(self.import_type, 1)
        import_row.addWidget(import_btn)
        import_row.addWidget(compare_btn)
        import_row.addStretch()
        self.summary = QTextEdit(); self.summary.setReadOnly(True)
        self.summary.setPlaceholderText("导入资料后，这里会显示完整度、缺失信息和差异分析。")
        self.project_table = QTableWidget(0, 6)
        self.project_table.setHorizontalHeaderLabels(["项目", "资料源", "模块", "接口", "用例", "最近更新"])
        self.project_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.project_table.setAlternatingRowColors(True)
        self.project_table.setShowGrid(False)
        self.project_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.project_table.verticalHeader().setVisible(False)
        self.project_table.verticalHeader().setDefaultSectionSize(48)
        self.project_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.project_table.itemSelectionChanged.connect(self.select_project_from_table)
        self.project_table.cellDoubleClicked.connect(lambda *_: self.go_to_page(1))
        self.asset_tree = QTreeWidget()
        self.asset_tree.setHeaderLabels(["项目资产结构", "类型 / 方法", "数量 / 路径"])
        self.asset_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.asset_tree.itemDoubleClicked.connect(self.open_asset_item)
        asset_split = QSplitter(Qt.Horizontal)
        asset_split.addWidget(self.project_table)
        detail_panel = QSplitter(Qt.Vertical)
        detail_panel.addWidget(self.asset_tree)
        detail_panel.addWidget(self.summary)
        detail_panel.setSizes([420, 180])
        asset_split.addWidget(detail_panel)
        asset_split.setSizes([650, 520])
        new_btn.setProperty("primary", True)
        delete_btn.setProperty("danger", True)
        layout.addWidget(title); layout.addWidget(mode); layout.addLayout(row); layout.addLayout(import_row)
        layout.addWidget(asset_split, 1)
        self._finish_page(page, layout)
        return page

    def import_selected_source(self):
        handlers = [
            self.import_openapi, self.import_openapi_url, self.import_postman,
            self.import_postman_environment, self.import_apifox, self.import_curl,
            self.import_har, self.import_document, self.import_backend_source,
        ]
        handlers[self.import_type.currentIndex()]()

    def _cases_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("用例生成与执行"); title.setObjectName("PageTitle")
        subtitle = QLabel("路线 A、路线 B 共用的用例审核、批量执行和结果分析中心"); subtitle.setObjectName("PageSubtitle")
        self.case_project_label = QLabel("当前项目：未选择"); self.case_project_label.setObjectName("ContextBanner")
        scope_row = QHBoxLayout()
        self.case_project_selector = QComboBox()
        self.case_project_selector.currentIndexChanged.connect(self.select_case_project)
        self.case_module_filter = QComboBox()
        self.case_module_filter.currentIndexChanged.connect(self.refresh_cases)
        scope_row.addWidget(QLabel("测试项目"))
        scope_row.addWidget(self.case_project_selector, 1)
        scope_row.addWidget(QLabel("接口模块"))
        scope_row.addWidget(self.case_module_filter, 1)
        self.instruction = QTextEdit()
        self.instruction.setPlaceholderText("输入测试要求，例如：重点检查必填参数、边界值、Token 失效和越权访问")
        self.instruction.setMaximumHeight(90)
        model_row = QHBoxLayout()
        self.ai_status_label = QLabel("AI：请先检测当前连接")
        self.ai_status_label.setObjectName("PageSubtitle")
        self.max_workers = QSpinBox(); self.max_workers.setRange(1, 8); self.max_workers.setValue(1)
        self.max_workers.setPrefix("并发 ")
        model_row.addWidget(self.ai_status_label, 1); model_row.addWidget(self.max_workers)
        buttons = QHBoxLayout()
        plan_btn = QPushButton("预览测试计划"); plan_btn.clicked.connect(self.preview_plan)
        generate_btn = QPushButton("生成用例"); generate_btn.clicked.connect(self.generate_test_cases)
        confirm_btn = QPushButton("确认选中用例"); confirm_btn.clicked.connect(self.confirm_cases)
        edit_btn = QPushButton("编辑用例"); edit_btn.clicked.connect(self.edit_case)
        copy_btn = QPushButton("复制用例"); copy_btn.clicked.connect(self.copy_case)
        delete_case_btn = QPushButton("删除用例"); delete_case_btn.clicked.connect(self.delete_case)
        run_btn = QPushButton("执行已确认用例"); run_btn.clicked.connect(self.run_confirmed_cases)
        run_selected_btn = QPushButton("执行选中用例"); run_selected_btn.clicked.connect(self.run_selected_cases)
        rerun_failed_btn = QPushButton("重跑上次失败"); rerun_failed_btn.clicked.connect(self.rerun_failed_cases)
        stop_btn = QPushButton("停止任务"); stop_btn.clicked.connect(self.stop_run)
        for button in (plan_btn, generate_btn, confirm_btn, edit_btn, copy_btn, delete_case_btn, run_btn, run_selected_btn, rerun_failed_btn, stop_btn):
            buttons.addWidget(button)
        self.case_table = QTableWidget(0, 5)
        self.case_table.setHorizontalHeaderLabels(["ID", "名称", "优先级", "状态", "风险"])
        self.case_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.run_output = QTextEdit(); self.run_output.setReadOnly(True)
        self.run_progress = QProgressBar(); self.run_progress.setRange(0, 100)
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(self.case_project_label)
        layout.addLayout(scope_row)
        layout.addWidget(self.instruction)
        layout.addLayout(model_row); layout.addLayout(buttons); layout.addWidget(self.case_table, 1)
        layout.addWidget(self.run_progress); layout.addWidget(QLabel("计划 / 执行结果")); layout.addWidget(self.run_output, 1)
        generate_btn.setProperty("primary", True)
        run_btn.setProperty("primary", True)
        delete_case_btn.setProperty("danger", True)
        self.case_table.setAlternatingRowColors(True)
        self.case_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._finish_page(page, layout)
        return page

    def _workflow_page(self):
        # Workflow definitions can be large. Keep every control reachable instead of
        # allowing a long JSON document to squeeze adjacent rows into each other.
        page = QScrollArea()
        page.setObjectName("WorkflowScroll")
        page.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        page.setWidget(content)
        title = QLabel("源码驱动测试 · 路线 A"); title.setObjectName("PageTitle")
        subtitle = QLabel("查看接口 → AI/人工业务流程 → 数据流与数据库变更确认 → 测试范围 → 用例 → 执行 → 报告")
        subtitle.setObjectName("PageSubtitle")
        self.workflow_project_label = QLabel("当前项目：未选择"); self.workflow_project_label.setObjectName("ContextBanner")
        route_row = QHBoxLayout()
        view_endpoints = QPushButton("查看接口资产"); view_endpoints.clicked.connect(lambda: self.go_to_page(1))
        ai_generate = QPushButton("AI 生成业务流程"); ai_generate.clicked.connect(self.generate_workflow_draft)
        manual_generate = QPushButton("人工新建业务流程"); manual_generate.clicked.connect(self.create_manual_workflow)
        route_row.addWidget(view_endpoints); route_row.addWidget(ai_generate); route_row.addWidget(manual_generate); route_row.addStretch()
        selector_row = QHBoxLayout()
        self.workflow_selector = QComboBox()
        self.workflow_selector.currentIndexChanged.connect(self.load_workflow)
        save_btn = QPushButton("保存流程"); save_btn.clicked.connect(self.save_workflow)
        confirm_btn = QPushButton("确认流程"); confirm_btn.clicked.connect(self.confirm_workflow)
        coverage_btn = QPushButton("检查工艺完整性"); coverage_btn.clicked.connect(self.check_process_coverage)
        selector_row.addWidget(QLabel("流程")); selector_row.addWidget(self.workflow_selector, 1)
        selector_row.addWidget(save_btn); selector_row.addWidget(coverage_btn); selector_row.addWidget(confirm_btn)
        self.workflow_scope = QTextEdit(); self.workflow_scope.setMaximumHeight(65)
        self.workflow_scope.setPlaceholderText("确认测试方向，例如：订单创建、库存扣减、权限、重复提交、事务一致性、异常回滚")
        scope_row = QHBoxLayout()
        confirm_scope = QPushButton("确认测试范围"); confirm_scope.clicked.connect(self.confirm_workflow_scope)
        generate_cases_btn = QPushButton("生成接口测试用例"); generate_cases_btn.clicked.connect(self.generate_workflow_cases)
        scope_row.addWidget(QLabel("测试范围")); scope_row.addWidget(self.workflow_scope, 1)
        scope_row.addWidget(confirm_scope); scope_row.addWidget(generate_cases_btn)
        self.workflow_json = QTextEdit()
        self.workflow_json.setPlaceholderText(
            '{"name":"订单创建流程","review_status":"draft","data_flows":[],"database_changes":[],"steps":[]}'
        )
        self.workflow_json.setMinimumHeight(260)
        self.workflow_json.setMaximumHeight(320)
        database_row = QHBoxLayout()
        self.workflow_db_path = QLineEdit(); self.workflow_db_path.setPlaceholderText("SQLite 测试库或副本路径")
        choose_db = QPushButton("选择测试库"); choose_db.clicked.connect(self.choose_workflow_database)
        self.workflow_db_read_only = QCheckBox("只读数据库（断言安全，不能写入夹具）")
        self.workflow_db_read_only.setChecked(True)
        save_db = QPushButton("保存数据库配置"); save_db.clicked.connect(self.save_workflow_database)
        inspect_db = QPushButton("检查测试库"); inspect_db.clicked.connect(self.inspect_workflow_database)
        database_row.addWidget(QLabel("测试库")); database_row.addWidget(self.workflow_db_path, 1)
        database_row.addWidget(choose_db); database_row.addWidget(self.workflow_db_read_only); database_row.addWidget(save_db); database_row.addWidget(inspect_db)
        fixture_row = QHBoxLayout()
        self.workflow_fixture_name = QLineEdit(); self.workflow_fixture_name.setPlaceholderText("夹具名称")
        self.workflow_fixture_json = QLineEdit(); self.workflow_fixture_json.setPlaceholderText('{"table":"users","rows":[{"name":"Ada"}]}')
        save_fixture = QPushButton("保存夹具"); save_fixture.clicked.connect(self.save_workflow_fixture)
        fixture_row.addWidget(QLabel("测试数据")); fixture_row.addWidget(self.workflow_fixture_name)
        fixture_row.addWidget(self.workflow_fixture_json, 2); fixture_row.addWidget(save_fixture)
        execute_btn = QPushButton("执行已确认流程"); execute_btn.setProperty("primary", True); execute_btn.clicked.connect(self.execute_workflow)
        diff_btn = QPushButton("生成 A/B 差异报告"); diff_btn.clicked.connect(self.generate_ab_difference_report)
        replay_btn = QPushButton("导出重放包"); replay_btn.clicked.connect(self.export_workflow_replay)
        self.workflow_output = QTextEdit(); self.workflow_output.setReadOnly(True)
        self.workflow_output.setMinimumHeight(150)
        self.workflow_output.setMaximumHeight(260)
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(self.workflow_project_label)
        layout.addLayout(route_row); layout.addLayout(selector_row); layout.addWidget(QLabel("业务流程、数据流、数据库变更和步骤定义（需人工审核）"))
        layout.addWidget(self.workflow_json); layout.addLayout(scope_row)
        layout.addLayout(database_row); layout.addLayout(fixture_row); layout.addWidget(execute_btn)
        action_row = QHBoxLayout(); action_row.addWidget(diff_btn); action_row.addWidget(replay_btn); action_row.addStretch(); layout.addLayout(action_row)
        layout.addWidget(QLabel("流程执行与审计结果")); layout.addWidget(self.workflow_output)
        self._finish_page(content, layout)
        return page

    def _reports_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("历史测试报告"); title.setObjectName("PageTitle")
        subtitle = QLabel("统一查看路线 A 业务流程报告与路线 B 接口用例报告，按类型、名称和时间区分"); subtitle.setObjectName("PageSubtitle")
        self.report_project_label = QLabel("当前项目：未选择"); self.report_project_label.setObjectName("ContextBanner")
        refresh = QPushButton("刷新历史"); refresh.clicked.connect(self.refresh_reports)
        self.report_table = QTableWidget(0, 8)
        self.report_table.setHorizontalHeaderLabels(["类型", "流程/项目", "运行", "状态", "开始", "结束", "HTML", "JSON"])
        self.report_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.report_detail = QTextEdit(); self.report_detail.setReadOnly(True)
        self.report_table.itemSelectionChanged.connect(self.show_report)
        self.report_table.cellDoubleClicked.connect(lambda *_: self.open_selected_report("html"))
        open_html = QPushButton("打开 HTML 报告"); open_html.setProperty("primary", True); open_html.clicked.connect(lambda: self.open_selected_report("html"))
        open_json = QPushButton("打开 JSON 明细"); open_json.clicked.connect(lambda: self.open_selected_report("json"))
        report_actions = QHBoxLayout(); report_actions.addWidget(refresh); report_actions.addWidget(open_html); report_actions.addWidget(open_json); report_actions.addStretch()
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(self.report_project_label); layout.addLayout(report_actions)
        layout.addWidget(self.report_table, 1); layout.addWidget(self.report_detail, 1)
        self.report_table.setAlternatingRowColors(True)
        self.report_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._finish_page(page, layout)
        return page

    def _capability_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("测试能力中心"); title.setObjectName("PageTitle")
        subtitle = QLabel("统一项目、环境、用例、任务和报告基础上的分层测试能力")
        subtitle.setObjectName("PageSubtitle")
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["能力层", "建设阶段", "状态", "主要能力"])
        capabilities = [
            ("接口测试", "第一阶段", "可用", "路线 B 完整闭环；路线 A 为源码导入、静态证据和测试草稿基础支持"),
            ("数据流与状态", "V4 R1", "可用", "可见/隐藏工艺、SQLite schema、前后状态、运行时 Trace 和副作用观察"),
            ("AI 受控对话", "V4 R3", "可用", "问题清单、证据引用、artifact、人工审批和白名单工具边界"),
            ("组合差异与重放", "V4 R4", "基础支持", "A/B 差异报告、脱敏重放包；仍需完善跨系统运行时差异"),
            ("UI 自动化", "第二阶段", "规划中", "Playwright 页面流程、截图与 Trace"),
            ("性能测试", "第三阶段", "规划中", "Locust 场景、负载控制与性能指标"),
            ("鲁棒性测试", "第三阶段", "规划中", "超时、中断、异常响应与恢复验证"),
            ("安全性测试", "第四阶段", "规划中", "授权范围内的非破坏性安全检查"),
            ("回归测试", "平台能力", "规划中", "变更影响、用例复用、基线与趋势"),
            ("集成测试", "平台能力", "规划中", "跨接口依赖、业务链路和系统集成"),
        ]
        table.setRowCount(len(capabilities))
        for row, values in enumerate(capabilities):
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 2 and value == "可用":
                    item.setForeground(Qt.darkGreen)
                table.setItem(row, column, item)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.verticalHeader().setDefaultSectionSize(46)
        note = QLabel(
            "分层原则：工作空间管理多个项目；每个项目共享环境与资产；"
            "不同测试能力复用统一用例、执行任务和报告体系。"
        )
        note.setObjectName("ContextBanner")
        note.setWordWrap(True)
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(note); layout.addWidget(table, 1)
        self._finish_page(page, layout)
        return page

    def _ai_hub_page(self):
        """One home for AI collaboration and optional model connectivity."""
        page = QWidget()
        layout = QVBoxLayout(page)
        self.ai_hub_tabs = QTabWidget()
        self.ai_hub_tabs.setObjectName("AIHubTabs")
        # Settings are created first because the collaboration page reads the
        # configured provider list when building its model selector.
        settings = self._ai_settings_page()
        dialogue = self._ai_dialogue_page()
        self.ai_hub_tabs.addTab(dialogue, "AI 协作")
        self.ai_hub_tabs.addTab(settings, "模型与连接")
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ai_hub_tabs)
        return page

    def _activate_ai_hub_tab(self, index: int):
        self._activate_page(8)
        if hasattr(self, "ai_hub_tabs"):
            self.ai_hub_tabs.setCurrentIndex(index)

    def _ai_settings_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("模型与连接"); title.setObjectName("PageTitle")
        subtitle = QLabel("VS Code Codex 可复用 ChatGPT 登录；兼容 API 或本地 Ollama 可在 TestPilot 内直接对话")
        subtitle.setObjectName("PageSubtitle")
        explanation = QLabel(
            "安全流程：只读分析源码与接口资产 → 生成结构化草稿 → Schema 校验 → "
            "人工确认 → 在已授权环境执行。AI 不会直接发送接口请求。"
        )
        explanation.setObjectName("ContextBanner"); explanation.setWordWrap(True)

        self.ai_tabs = QTabWidget()
        self.ai_tabs.currentChanged.connect(self._ai_mode_changed)

        codex_tab = QWidget(); codex_form = QFormLayout(codex_tab)
        self.codex_path = QLineEdit()
        self.codex_path.setPlaceholderText("选择需要分析的源码项目目录")
        choose_source = QPushButton("选择目录"); choose_source.clicked.connect(self.choose_codex_source)
        source_row = QHBoxLayout(); source_row.addWidget(self.codex_path, 1); source_row.addWidget(choose_source)
        self.codex_model = QLineEdit()
        self.codex_model.setPlaceholderText("留空则使用 Codex 当前默认模型")
        codex_buttons = QHBoxLayout()
        install = QPushButton("安装 Codex"); install.clicked.connect(self.install_codex)
        detect = QPushButton("检测登录状态"); detect.clicked.connect(self.check_codex_connection)
        login = QPushButton("登录 ChatGPT"); login.setProperty("primary", True); login.clicked.connect(self.login_codex)
        codex_buttons.addWidget(install); codex_buttons.addWidget(detect)
        codex_buttons.addWidget(login); codex_buttons.addStretch()
        codex_form.addRow("源码目录", source_row)
        codex_form.addRow("Codex 模型", self.codex_model)
        codex_form.addRow("账号连接", codex_buttons)
        self.codex_account_label = QLabel("当前登录账号：未检测")
        self.codex_account_label.setObjectName("CodexAccountLabel")
        codex_form.addRow("已登录账号", self.codex_account_label)
        codex_note = QLabel(
            "此处只验证 Codex / ChatGPT 的登录状态，不代表 TestPilot 内置聊天已经连通。"
            "使用已登录的 ChatGPT 请到“AI 协作”点击“在 VS Code 中问 Codex”；"
            "TestPilot 内直接回复请配置兼容 API 或本地 Ollama。"
        )
        codex_note.setWordWrap(True); codex_form.addRow("", codex_note)
        self.ai_tabs.addTab(codex_tab, "Codex 登录（VS Code 协作）")

        api_tab = QWidget(); api_form = QFormLayout(api_tab)
        self.model_url = QLineEdit()
        self.model_url.setPlaceholderText("例如：https://api.openai.com/v1")
        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("支持结构化 JSON 输出的模型名称")
        self.model_key = QLineEdit(); self.model_key.setEchoMode(QLineEdit.Password)
        self.model_key.setPlaceholderText("API Token / Key")
        api_form.addRow("API Base URL", self.model_url)
        api_form.addRow("模型", self.model_name)
        api_form.addRow("Token", self.model_key)
        self.ai_tabs.addTab(api_tab, "兼容 API")

        ollama_tab = QWidget(); ollama_form = QFormLayout(ollama_tab)
        self.ollama_url = QLineEdit("http://localhost:11434")
        self.ollama_model = QLineEdit()
        self.ollama_model.setPlaceholderText("例如：qwen3:8b")
        ollama_form.addRow("Ollama 地址", self.ollama_url)
        ollama_form.addRow("本地模型", self.ollama_model)
        ollama_note = QLabel("需要先启动 Ollama 并下载模型；源码与提示词保留在本机。")
        ollama_note.setWordWrap(True); ollama_form.addRow("", ollama_note)
        self.ai_tabs.addTab(ollama_tab, "本地 Ollama")

        resilience_form = QFormLayout()
        self.ai_timeout = QSpinBox(); self.ai_timeout.setRange(10, 300); self.ai_timeout.setSuffix(" 秒")
        self.ai_timeout.setToolTip("单次请求超过该时间会终止，并按重试次数重新请求")
        self.ai_retries = QSpinBox(); self.ai_retries.setRange(0, 3); self.ai_retries.setSuffix(" 次")
        self.ai_retries.setToolTip("只重试超时和临时连接错误；认证及模型配置错误不会重试")
        resilience_form.addRow("单次请求超时", self.ai_timeout)
        resilience_form.addRow("失败自动重试", self.ai_retries)

        actions = QHBoxLayout()
        save = QPushButton("保存当前配置"); save.setProperty("primary", True); save.clicked.connect(self.save_ai_settings)
        test = QPushButton("检测登录状态"); test.clicked.connect(self.test_ai_connection)
        self.ai_test_connection_button = test
        clear = QPushButton("清除 API Token"); clear.setProperty("danger", True); clear.clicked.connect(self.clear_ai_token)
        actions.addWidget(save); actions.addWidget(test); actions.addWidget(clear); actions.addStretch()
        self.ai_connection_result = QTextEdit(); self.ai_connection_result.setReadOnly(True)
        self.ai_connection_result.setPlaceholderText("安装、登录和模型连接状态会显示在这里。")
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(explanation)
        layout.addWidget(self.ai_tabs); layout.addLayout(resilience_form); layout.addLayout(actions); layout.addWidget(self.ai_connection_result, 1)
        self._finish_page(page, layout)
        self._load_ai_settings()
        return page

    def _ai_dialogue_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("AI 协作中心"); title.setObjectName("PageTitle")
        subtitle = QLabel("优先通过 VS Code Codex 生成测试方案；也可在“模型与连接”配置本地或 API 模型")
        subtitle.setObjectName("PageSubtitle")
        self.ai_dialogue_project_label = QLabel("当前项目：未选择"); self.ai_dialogue_project_label.setObjectName("ContextBanner")

        workspace = QSplitter(Qt.Horizontal); workspace.setObjectName("AIWorkspace")
        rail = QFrame(); rail.setObjectName("AIConversationRail"); rail.setMinimumWidth(220); rail.setMaximumWidth(280)
        rail_layout = QVBoxLayout(rail); rail_layout.setContentsMargins(12, 14, 12, 14); rail_layout.setSpacing(10)
        new_session = QPushButton("＋  新建测试对话"); new_session.setObjectName("NewAIConversation"); new_session.clicked.connect(self.new_ai_dialogue_session)
        rail_title = QLabel("当前会话"); rail_title.setObjectName("AIRailTitle")
        self.ai_session_summary = QTextEdit(); self.ai_session_summary.setReadOnly(True); self.ai_session_summary.setObjectName("AISessionSummary")
        self.ai_session_summary.setPlaceholderText("尚未开始对话\n\n可以先选择右侧的快捷任务。")
        rail_help = QLabel("快捷键\nCtrl+K  在任意页面打开 AI 助手"); rail_help.setObjectName("AIShortcutHelp"); rail_help.setWordWrap(True)
        rail_layout.addWidget(new_session); rail_layout.addWidget(rail_title); rail_layout.addWidget(self.ai_session_summary, 1); rail_layout.addWidget(rail_help)

        main = QFrame(); main.setObjectName("AIChatMain")
        main_layout = QVBoxLayout(main); main_layout.setContentsMargins(24, 18, 24, 18); main_layout.setSpacing(12)
        welcome = QLabel("有什么想聊的？"); welcome.setObjectName("AIWelcome"); welcome.setAlignment(Qt.AlignCenter)
        hint = QLabel("可以直接聊天、了解项目，或让 AI 编排接口与数据库测试"); hint.setObjectName("AIWelcomeHint"); hint.setAlignment(Qt.AlignCenter)
        templates = QHBoxLayout(); templates.addStretch()
        for label, prompt in [
            ("测试一个接口", "帮我测试当前项目的一个核心接口，并验证响应和数据库状态。"),
            ("验证数据库状态", "执行接口后检查关联表的数据、状态迁移和事务回滚是否符合业务逻辑。"),
            ("生成路线 A 流程", "根据当前后端源码生成一套 API + 数据库联合测试流程，并告诉我每一步为什么要测。"),
        ]:
            button = QPushButton(label); button.setObjectName("AITemplateButton")
            button.clicked.connect(lambda checked=False, value=prompt: self.use_ai_template(value)); templates.addWidget(button)
        templates.addStretch()
        controls = QHBoxLayout()
        self.ai_dialogue_route = QComboBox(); self.ai_dialogue_route.addItem("智能对话 · 可测试编排", "chat"); self.ai_dialogue_route.addItem("路线 A · 源码 + 数据库", "route_a"); self.ai_dialogue_route.addItem("路线 B · 接口资料", "route_b"); self.ai_dialogue_route.addItem("组合检查 · A+B", "combined")
        approve = QPushButton("批准测试草稿"); approve.clicked.connect(self.approve_latest_ai_artifact); approve.setProperty("primary", True)
        reject = QPushButton("退回修改"); reject.clicked.connect(self.reject_latest_ai_artifact)
        controls.addWidget(QLabel("对话模式")); controls.addWidget(self.ai_dialogue_route, 1); controls.addWidget(approve); controls.addWidget(reject)
        self.ai_dialogue_history = _ChatTranscript()
        self.ai_dialogue_artifact = QTextEdit(); self.ai_dialogue_artifact.setReadOnly(True); self.ai_dialogue_artifact.setObjectName("AIArtifactView")
        self.ai_dialogue_artifact.setPlaceholderText("生成草稿后，这里显示 API 步骤、关联表、数据库断言和证据缺口。")
        result_tabs = QTabWidget(); result_tabs.setObjectName("AIResultTabs"); result_tabs.addTab(self.ai_dialogue_history, "对话"); result_tabs.addTab(self.ai_dialogue_artifact, "测试草稿与证据")
        composer = QFrame(); composer.setObjectName("AIComposer"); composer_layout = QVBoxLayout(composer); composer_layout.setContentsMargins(14, 12, 14, 12); composer_layout.setSpacing(8)
        self.ai_dialogue_input = QTextEdit(); self.ai_dialogue_input.setObjectName("AIComposerInput"); self.ai_dialogue_input.setMaximumHeight(86)
        self.ai_dialogue_input.setPlaceholderText("随便问我任何问题；也可以说：帮我编排并执行当前项目的登录接口测试")
        self.ai_chat_model = QComboBox(); self.ai_chat_model.setObjectName("AIChatModelSelector"); self.ai_chat_model.setMinimumWidth(160)
        self.ai_dialogue_send = QPushButton("发送"); self.ai_dialogue_send.clicked.connect(self.send_ai_dialogue); self.ai_dialogue_send.setProperty("primary", True); self.ai_dialogue_send.setMinimumWidth(86)
        self.ai_dialogue_cancel = QPushButton("取消生成"); self.ai_dialogue_cancel.clicked.connect(self.cancel_ai_request); self.ai_dialogue_cancel.setVisible(False)
        composer_footer = QHBoxLayout(); composer_footer.addWidget(self.ai_chat_model); composer_footer.addStretch(); composer_footer.addWidget(self.ai_dialogue_cancel); composer_footer.addWidget(self.ai_dialogue_send)
        composer_layout.addWidget(self.ai_dialogue_input); composer_layout.addLayout(composer_footer)
        vscode_actions = QHBoxLayout()
        open_vscode = QPushButton("在 VS Code 中问 Codex")
        open_vscode.setObjectName("OpenVSCodeCodex")
        open_vscode.clicked.connect(lambda: self.open_vscode_codex())
        import_vscode = QPushButton("导入 Codex 测试方案")
        import_vscode.setObjectName("ImportVSCodeCodexPlan")
        import_vscode.clicked.connect(self.import_vscode_codex_plan)
        vscode_note = QLabel("使用已登录的 VS Code Codex，不需要 API Key")
        vscode_note.setObjectName("AIWelcomeHint")
        vscode_actions.addWidget(open_vscode); vscode_actions.addWidget(import_vscode)
        vscode_actions.addWidget(vscode_note); vscode_actions.addStretch()
        # The conversation is the primary surface.  Test orchestration is inferred
        # from what the user asks for, instead of forcing a form before chatting.
        main_layout.addWidget(welcome); main_layout.addWidget(hint); main_layout.addLayout(vscode_actions)
        main_layout.addWidget(result_tabs, 1); main_layout.addWidget(composer)
        workspace.addWidget(rail); workspace.addWidget(main); workspace.setSizes([240, 900])
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(self.ai_dialogue_project_label); layout.addWidget(workspace, 1)
        self._ai_dialogue_session_id = None
        self._finish_page(page, layout)
        self._refresh_chat_model_selector()
        return page

    def _quick_ai_sidebar(self):
        panel = QFrame(); panel.setObjectName("QuickAIPanel"); panel.setFixedWidth(380); panel.setVisible(False)
        layout = QVBoxLayout(panel); layout.setContentsMargins(14, 14, 14, 14); layout.setSpacing(10)
        header = QHBoxLayout(); title = QLabel("AI 测试助手"); title.setObjectName("QuickAITitle")
        shortcut = QLabel("Ctrl+K"); shortcut.setObjectName("ShortcutBadge")
        close = QToolButton(); close.setText("×"); close.setObjectName("QuickAIClose"); close.clicked.connect(self.toggle_ai_assistant)
        header.addWidget(title); header.addWidget(shortcut); header.addStretch(); header.addWidget(close)
        context = QLabel("基于当前项目和当前页面提供帮助"); context.setObjectName("QuickAIContext")
        history_label = QLabel("对话记录（只读）"); history_label.setObjectName("QuickAISectionLabel")
        self.quick_ai_history = QTextEdit(); self.quick_ai_history.setReadOnly(True); self.quick_ai_history.setObjectName("QuickAIHistory")
        self.quick_ai_history.setPlaceholderText("可以问我：\n\n• 这个页面怎么使用？\n• 帮我生成路线 A 测试\n• 执行接口后该检查哪些表？")
        self.quick_ai_input = QTextEdit(); self.quick_ai_input.setObjectName("QuickAIInput"); self.quick_ai_input.setMaximumHeight(100)
        self.quick_ai_input.setPlaceholderText("输入测试问题……")
        self.quick_ai_send = QPushButton("发送"); self.quick_ai_send.setProperty("primary", True); self.quick_ai_send.clicked.connect(self.send_quick_ai)
        input_label = QLabel("输入问题"); input_label.setObjectName("QuickAISectionLabel")
        self.quick_ai_cancel = QPushButton("取消生成"); self.quick_ai_cancel.clicked.connect(self.cancel_ai_request); self.quick_ai_cancel.setVisible(False)
        quick_actions = QHBoxLayout(); quick_actions.addWidget(self.quick_ai_cancel); quick_actions.addWidget(self.quick_ai_send, 1)
        layout.addLayout(header); layout.addWidget(context); layout.addWidget(history_label); layout.addWidget(self.quick_ai_history, 1); layout.addWidget(input_label); layout.addWidget(self.quick_ai_input); layout.addLayout(quick_actions)
        return panel

    def _endpoint_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("接口资产"); title.setObjectName("PageTitle")
        subtitle = QLabel("浏览、搜索与维护统一接口定义"); subtitle.setObjectName("PageSubtitle")
        self.endpoint_project_label = QLabel("当前项目：未选择")
        self.endpoint_project_label.setObjectName("ContextBanner")
        filter_row = QHBoxLayout()
        self.source_filter = QComboBox(); self.source_filter.addItem("全部资料源", None)
        self.module_filter = QComboBox(); self.module_filter.addItem("全部模块", None)
        self.source_filter.currentIndexChanged.connect(self.refresh_endpoints)
        self.module_filter.currentIndexChanged.connect(self.refresh_endpoints)
        filter_row.addWidget(QLabel("资料源"))
        filter_row.addWidget(self.source_filter)
        filter_row.addWidget(QLabel("模块"))
        filter_row.addWidget(self.module_filter)
        filter_row.addStretch()
        self.search = QLineEdit(); self.search.setPlaceholderText("搜索方法、路径、模块或摘要")
        # Do not redraw a potentially large endpoint table for every keystroke.
        self._endpoint_search_timer = QTimer(self)
        self._endpoint_search_timer.setSingleShot(True)
        self._endpoint_search_timer.setInterval(180)
        self._endpoint_search_timer.timeout.connect(self.refresh_endpoints)
        self.search.textChanged.connect(self._schedule_endpoint_refresh)
        split = QSplitter(Qt.Horizontal)
        self.endpoint_table = QTableWidget(0, 4)
        self.endpoint_table.setHorizontalHeaderLabels(["方法", "路径", "模块", "摘要"])
        self.endpoint_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.endpoint_table.itemSelectionChanged.connect(self.show_endpoint)
        self.endpoint_detail = QTextEdit(); self.endpoint_detail.setReadOnly(True)
        split.addWidget(self.endpoint_table); split.addWidget(self.endpoint_detail)
        split.setSizes([700, 500])
        actions = QHBoxLayout()
        add_btn = QPushButton("手工添加"); add_btn.clicked.connect(self.add_endpoint)
        edit_btn = QPushButton("编辑 JSON"); edit_btn.clicked.connect(self.edit_endpoint)
        delete_btn = QPushButton("删除接口"); delete_btn.clicked.connect(self.delete_endpoint)
        actions.addWidget(add_btn); actions.addWidget(edit_btn); actions.addWidget(delete_btn); actions.addStretch()
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(self.endpoint_project_label)
        layout.addLayout(filter_row); layout.addWidget(self.search)
        layout.addLayout(actions); layout.addWidget(split, 1)
        add_btn.setProperty("primary", True)
        delete_btn.setProperty("danger", True)
        self.endpoint_table.setAlternatingRowColors(True)
        self.endpoint_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._finish_page(page, layout)
        return page

    def _request_page(self):
        page = QWidget(); layout = QVBoxLayout(page); form = QFormLayout()
        title = QLabel("环境与请求调试"); title.setObjectName("PageTitle")
        subtitle = QLabel("管理测试环境、认证变量并发送单接口请求"); subtitle.setObjectName("PageSubtitle")
        self.request_project_label = QLabel("当前项目：未选择"); self.request_project_label.setObjectName("ContextBanner")
        self.env_selector = QComboBox(); self.env_selector.currentIndexChanged.connect(self.select_environment)
        self.env_name = QLineEdit("测试环境")
        self.base_url = QLineEdit()
        self.method = QComboBox(); self.method.addItems(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
        self.path = QLineEdit("/")
        self.headers = QTextEdit("{}"); self.headers.setMaximumHeight(90)
        self.variables = QTextEdit("{}"); self.variables.setMaximumHeight(90)
        self.body = QTextEdit("{}"); self.body.setMaximumHeight(130)
        self.environment_confirmed = QCheckBox("我确认该地址是已授权的测试/预发布环境")
        form.addRow("已有环境", self.env_selector); form.addRow("环境名称", self.env_name); form.addRow("Base URL", self.base_url)
        form.addRow("Method", self.method); form.addRow("Path", self.path)
        form.addRow("Headers JSON", self.headers); form.addRow("Body JSON", self.body)
        form.addRow("环境变量 JSON", self.variables)
        form.addRow("执行授权", self.environment_confirmed)
        buttons = QHBoxLayout()
        save = QPushButton("保存环境"); save.clicked.connect(self.save_environment)
        send = QPushButton("发送请求"); send.clicked.connect(self.send_request)
        save_as_case = QPushButton("保存为测试用例"); save_as_case.clicked.connect(self.save_request_as_case)
        buttons.addWidget(save); buttons.addWidget(send); buttons.addWidget(save_as_case); buttons.addStretch()
        self.response = QTextEdit(); self.response.setReadOnly(True)
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(self.request_project_label)
        layout.addLayout(form); layout.addLayout(buttons)
        layout.addWidget(QLabel("响应（敏感字段已脱敏）")); layout.addWidget(self.response, 1)
        save.setProperty("primary", True)
        send.setProperty("primary", True)
        self._finish_page(page, layout)
        return page

    @staticmethod
    def _finish_page(page, layout):
        page.setObjectName("ContentPage")
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

    def _load_ai_settings(self):
        mode = self.db.get_setting("ai_provider", "codex")
        self.ai_tabs.setCurrentIndex({"codex": 0, "api": 1, "ollama": 2}.get(mode, 0))
        self.codex_path.setText(self.db.get_setting("codex_project_path"))
        self.codex_model.setText(self.db.get_setting("codex_model"))
        self.model_url.setText(self.db.get_setting("ai_base_url"))
        self.model_name.setText(self.db.get_setting("ai_model"))
        self.ollama_url.setText(self.db.get_setting("ollama_url", "http://localhost:11434"))
        self.ollama_model.setText(self.db.get_setting("ollama_model"))
        self.ai_timeout.setValue(int(self.db.get_setting("ai_request_timeout", "45") or 45))
        self.ai_retries.setValue(int(self.db.get_setting("ai_request_retries", "1") or 1))
        encrypted = self.db.get_setting("ai_token_encrypted")
        if encrypted:
            try:
                self.model_key.setText(self.secret_store.decrypt_dict(encrypted).get("api_key", ""))
            except Exception:
                self.model_key.clear()
        self._update_ai_status()
        self._update_codex_account_label()
        self._refresh_chat_model_selector()

    def _update_ai_status(self):
        if not hasattr(self, "ai_status_label"):
            return
        mode = self.ai_tabs.currentIndex() if hasattr(self, "ai_tabs") else 1
        if mode == 0:
            verified = self.db.get_setting("codex_login_verified", "false") == "true"
            self.ai_status_label.setText("AI：Codex · ChatGPT 已验证" if verified else "AI：Codex · 尚未验证登录")
        elif mode == 2:
            model = self.ollama_model.text().strip() or "未选择模型"
            self.ai_status_label.setText(f"AI：本地 Ollama · {model}")
        elif self.model_url.text().strip() and self.model_name.text().strip() and self.model_key.text():
            self.ai_status_label.setText(f"AI：兼容 API · {self.model_name.text().strip()}")
        else:
            self.ai_status_label.setText("AI：兼容 API 尚未完成配置")

    def _ai_mode_changed(self, _index=None):
        self._update_ai_status()
        self._refresh_chat_model_selector()
        if hasattr(self, "ai_test_connection_button"):
            labels = ("检测登录状态", "测试 API 连接", "测试 Ollama")
            self.ai_test_connection_button.setText(labels[self.ai_tabs.currentIndex()])

    def _update_codex_account_label(self, identity: dict | None = None):
        if not hasattr(self, "codex_account_label"):
            return
        identity = identity or CodexCliProvider.account_identity()
        name = identity.get("name") or self.db.get_setting("codex_account_name")
        email = identity.get("email") or self.db.get_setting("codex_account_email")
        if name and email:
            self.codex_account_label.setText(f"{name}（{email}）")
        elif email:
            self.codex_account_label.setText(email)
        elif name:
            self.codex_account_label.setText(name)
        else:
            self.codex_account_label.setText("未检测到已登录账号，请点击“检测登录状态”")

    def _refresh_chat_model_selector(self):
        if not hasattr(self, "ai_chat_model"):
            return
        current = self.ai_chat_model.currentData()
        self.ai_chat_model.blockSignals(True)
        self.ai_chat_model.clear()
        self.ai_chat_model.addItem("Codex · 在 VS Code 中使用", "codex")
        if self.model_url.text().strip() and self.model_name.text().strip() and self.model_key.text():
            self.ai_chat_model.addItem(f"兼容 API · {self.model_name.text().strip()}", "api")
        if self.ollama_model.text().strip():
            self.ai_chat_model.addItem(f"本地 Ollama · {self.ollama_model.text().strip()}", "ollama")
        index = self.ai_chat_model.findData(current)
        self.ai_chat_model.setCurrentIndex(index if index >= 0 else 0)
        self.ai_chat_model.blockSignals(False)

    def choose_codex_source(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择 Codex 分析的源码目录", self.codex_path.text().strip()
        )
        if path:
            self.codex_path.setText(path)

    def save_ai_settings(self):
        mode = ("codex", "api", "ollama")[self.ai_tabs.currentIndex()]
        self.db.set_setting("ai_provider", mode)
        self.db.set_setting("codex_project_path", self.codex_path.text().strip())
        self.db.set_setting("codex_model", self.codex_model.text().strip())
        self.db.set_setting("ai_base_url", self.model_url.text().strip())
        self.db.set_setting("ai_model", self.model_name.text().strip())
        self.db.set_setting("ollama_url", self.ollama_url.text().strip())
        self.db.set_setting("ollama_model", self.ollama_model.text().strip())
        self.db.set_setting("ai_request_timeout", str(self.ai_timeout.value()))
        self.db.set_setting("ai_request_retries", str(self.ai_retries.value()))
        encrypted = self.secret_store.encrypt_dict({"api_key": self.model_key.text()}) if self.model_key.text() else ""
        self.db.set_setting("ai_token_encrypted", encrypted)
        self._update_ai_status()
        self._refresh_chat_model_selector()
        self.ai_connection_result.setPlainText(
            f"已保存 {self.ai_tabs.tabText(self.ai_tabs.currentIndex())} 配置。"
            + (" API Token 已使用本机密钥加密。" if self.model_key.text() else "")
        )

    def clear_ai_token(self):
        self.model_key.clear()
        self.db.set_setting("ai_token_encrypted", "")
        self._update_ai_status()
        self._refresh_chat_model_selector()
        self.ai_connection_result.setPlainText("Token 已从本地配置中清除。")

    def test_ai_connection(self):
        mode = self.ai_tabs.currentIndex()
        if mode == 0:
            self.check_codex_connection()
            return
        if mode == 2:
            try:
                models = OllamaProvider(self.ollama_url.text().strip()).list_models()
                self.ai_connection_result.setPlainText(
                    "Ollama 连接成功。\n本地模型：\n"
                    + ("\n".join(models) if models else "尚未下载模型。")
                )
            except Exception as exc:
                self.ai_connection_result.setPlainText(f"Ollama 连接失败：{exc}")
            return
        if not self.model_url.text().strip() or not self.model_key.text():
            QMessageBox.warning(self, "AI 配置", "请先填写 API Base URL 和 Token。")
            return
        try:
            import httpx
            response = httpx.get(
                self.model_url.text().strip().rstrip("/") + "/models",
                headers={"Authorization": f"Bearer {self.model_key.text()}"},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            models = [item.get("id") for item in payload.get("data", [])[:20] if isinstance(item, dict)]
            self.ai_connection_result.setPlainText(
                "连接成功。\n可用模型：\n" + ("\n".join(models) if models else json.dumps(payload, ensure_ascii=False, indent=2)[:4000])
            )
        except Exception as exc:
            self.ai_connection_result.setPlainText(f"连接失败：{exc}")

    def check_codex_connection(self):
        executable = find_codex()
        if not executable:
            self.ai_connection_result.setPlainText(
                "未检测到 Codex CLI。\n请先安装 Node.js，然后执行：npm install -g @openai/codex"
            )
            return
        try:
            ok, status = CodexCliProvider(
                self.codex_path.text().strip() or str(Path.cwd()),
                executable=executable,
            ).status()
            identity = CodexCliProvider.account_identity() if ok else {}
            if identity.get("name"):
                self.db.set_setting("codex_account_name", identity["name"])
            if identity.get("email"):
                self.db.set_setting("codex_account_email", identity["email"])
            self.db.set_setting("codex_login_verified", "true" if ok else "false")
            self._update_ai_status()
            self._update_codex_account_label(identity)
            account_text = ""
            if identity.get("name") or identity.get("email"):
                account_text = "\n已登录账号：" + (identity.get("name") or identity.get("email", ""))
                if identity.get("name") and identity.get("email"):
                    account_text += f"（{identity['email']}）"
            self.ai_connection_result.setPlainText(
                f"已检测到 Codex：{executable}\n"
                + (
                    f"账号状态：{status}{account_text}\n\n"
                    "登录已验证：这只说明你的 ChatGPT / Codex 账户可用，"
                    "不代表 TestPilot 内置聊天能够直接调用模型。\n"
                    "请在“AI 协作”页点击“在 VS Code 中问 Codex”，使用已登录的 VS Code Codex。"
                    if ok else f"尚未登录：{status}\n请点击“登录 ChatGPT”。"
                )
            )
        except Exception as exc:
            self.db.set_setting("codex_login_verified", "false")
            self._update_ai_status()
            self.ai_connection_result.setPlainText(f"Codex 检测失败：{exc}")

    def install_codex(self):
        import shutil

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            self.ai_connection_result.setPlainText(
                "未检测到 npm。请先安装 Node.js，再点击“安装 Codex”。"
            )
            return
        if QMessageBox.question(
            self, "安装 Codex",
            "将通过 npm 安装官方 @openai/codex。是否继续？",
        ) != QMessageBox.Yes:
            return
        started = QProcess.startDetached(npm, ["install", "-g", "@openai/codex"])
        success = started[0] if isinstance(started, tuple) else started
        if success:
            self.ai_connection_result.setPlainText(
                "Codex 安装进程已经启动。安装完成后点击“检测登录状态”。"
            )
        else:
            self.ai_connection_result.setPlainText("无法启动 Codex 安装进程。")

    def login_codex(self):
        executable = find_codex()
        if not executable:
            self.check_codex_connection()
            return
        started = QProcess.startDetached(executable, ["login"])
        success = started[0] if isinstance(started, tuple) else started
        if success:
            self.ai_connection_result.setPlainText(
                "已启动 Codex 登录。请在打开的浏览器或终端中完成 ChatGPT 授权，"
                "完成后点击“检测登录状态”。"
            )
        else:
            self.ai_connection_result.setPlainText("无法启动 Codex 登录进程。")

    def refresh_projects(self):
        selected = self.current_project_id
        self.projects.blockSignals(True); self.projects.clear()
        overviews = self.db.list_project_overviews()
        for project in overviews:
            self.projects.addItem(project["name"], project["id"])
        self.projects.blockSignals(False)
        self.case_project_selector.blockSignals(True)
        self.case_project_selector.clear()
        for project in overviews:
            self.case_project_selector.addItem(project["name"], project["id"])
        case_index = self.case_project_selector.findData(selected)
        self.case_project_selector.setCurrentIndex(max(0, case_index))
        self.case_project_selector.blockSignals(False)
        self.project_table.setUpdatesEnabled(False)
        self.project_table.blockSignals(True)
        try:
            self.project_table.setRowCount(len(overviews))
            for row, project in enumerate(overviews):
                values = (
                    project["name"], project["source_count"], project["module_count"],
                    project["endpoint_count"], project["case_count"], project["updated_at"],
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column == 0:
                        item.setData(Qt.UserRole, project["id"])
                    self.project_table.setItem(row, column, item)
                if project["id"] == selected:
                    self.project_table.selectRow(row)
        finally:
            self.project_table.blockSignals(False)
            self.project_table.setUpdatesEnabled(True)
        if self.projects.count():
            index = self.projects.findData(selected)
            self.projects.setCurrentIndex(max(0, index))
            self._project_changed()
            if self.project_table.currentRow() < 0:
                self.project_table.selectRow(max(0, self.projects.currentIndex()))
        else:
            self.current_project_id = None; self.refresh_endpoints(); self.asset_tree.clear()

    def select_project_from_table(self):
        row = self.project_table.currentRow()
        if row < 0:
            return
        project_id = self.project_table.item(row, 0).data(Qt.UserRole)
        index = self.projects.findData(project_id)
        if index >= 0 and self.projects.currentIndex() != index:
            self.projects.setCurrentIndex(index)

    def _project_changed(self):
        self.current_project_id = self.projects.currentData()
        if hasattr(self, "case_project_selector"):
            index = self.case_project_selector.findData(self.current_project_id)
            self.case_project_selector.blockSignals(True)
            self.case_project_selector.setCurrentIndex(max(0, index))
            self.case_project_selector.blockSignals(False)
        self.refresh_context_labels()
        self.refresh_asset_tree()
        self.refresh_endpoint_filters()
        self.refresh_case_module_filter()
        self.refresh_endpoints()
        if self.current_project_id:
            envs = self.db.list_environments(self.current_project_id)
            self.env_selector.blockSignals(True)
            self.env_selector.clear()
            for item in envs:
                self.env_selector.addItem(item["name"], item["id"])
            self.env_selector.blockSignals(False)
            if envs:
                self._load_environment(envs[0])
        if hasattr(self, "case_table"):
            self.refresh_cases()
        if hasattr(self, "report_table"):
            self.refresh_reports()
        if hasattr(self, "workflow_selector"):
            self.refresh_workflows()

    def refresh_asset_tree(self):
        if not hasattr(self, "asset_tree"):
            return
        self.asset_tree.setUpdatesEnabled(False)
        self.asset_tree.clear()
        if not self.current_project_id:
            self.asset_tree.setUpdatesEnabled(True)
            return
        project_name = self.projects.currentText()
        project_root = QTreeWidgetItem([project_name, "测试项目", ""])
        self.asset_tree.addTopLevelItem(project_root)
        source_nodes = {}
        source_counts = {}
        module_nodes = {}
        rows = self.db.project_asset_tree(self.current_project_id)
        for row in rows:
            source_id = row["source_id"]
            if source_id not in source_nodes:
                source_nodes[source_id] = QTreeWidgetItem(
                    project_root, [row["source_name"], row["kind"], ""]
                )
                source_counts[source_id] = 0
            if row["endpoint_id"] is None:
                continue
            source_counts[source_id] += 1
            module_key = (source_id, row["module"])
            if module_key not in module_nodes:
                module_nodes[module_key] = QTreeWidgetItem(
                    source_nodes[source_id], [row["module"], "模块", ""]
                )
            endpoint_node = QTreeWidgetItem(
                module_nodes[module_key],
                [row["summary"] or row["path"], row["method"], row["path"]],
            )
            endpoint_node.setData(0, Qt.UserRole, row["endpoint_id"])
        for source_id, source_node in source_nodes.items():
            source_node.setText(2, f"{source_counts[source_id]} 个接口")
        project_root.setText(2, f"{len(source_nodes)} 个资料源")
        project_root.setExpanded(True)
        for node in source_nodes.values():
            node.setExpanded(True)
        self.asset_tree.setUpdatesEnabled(True)

    def open_asset_item(self, item, column):
        endpoint_id = item.data(0, Qt.UserRole)
        if not endpoint_id:
            return
        self.source_filter.setCurrentIndex(0)
        self.module_filter.setCurrentIndex(0)
        self.search.clear()
        self.refresh_endpoints()
        for row, stored in enumerate(self._endpoint_rows):
            if stored["id"] == endpoint_id:
                self.endpoint_table.selectRow(row)
                break
        self.go_to_page(1)

    def refresh_context_labels(self):
        name = self.projects.currentText() if self.current_project_id else "未选择"
        endpoint_count = len(self.db.list_endpoints(self.current_project_id)) if self.current_project_id else 0
        context = f"当前项目：{name}  ·  {endpoint_count} 个接口"
        for attribute in ("request_project_label", "case_project_label", "report_project_label", "workflow_project_label", "ai_dialogue_project_label"):
            label = getattr(self, attribute, None)
            if label:
                label.setText(context)

    def _dialogue_context(self) -> dict:
        """Build a minimal, local evidence context for the AI conversation."""
        context: dict = {"environment_confirmed": bool(getattr(self, "environment_confirmed", None) and self.environment_confirmed.isChecked())}
        if not self.current_project_id:
            return context
        analyses = self.db.list_analysis_runs(self.current_project_id)
        if analyses:
            latest = analyses[0]
            run_id = int(latest["id"])
            context["analysis"] = {
                "symbols": [dict(row) for row in self.db.list_analysis_symbols(run_id)],
                "edges": [dict(row) for row in self.db.list_analysis_edges(run_id)],
                "evidence": [dict(row) for row in self.db.list_analysis_evidence(run_id)],
            }
            context["analysis"]["root_path"] = latest.get("root_path", "")
        workflow_id = self.workflow_selector.currentData() if hasattr(self, "workflow_selector") else None
        if workflow_id:
            row = self.db.get_workflow(int(workflow_id))
            if row:
                try:
                    context["workflow"] = json.loads(row["definition_json"] or "{}")
                except (TypeError, ValueError):
                    context["workflow"] = {}
        endpoints = self.db.list_endpoints(self.current_project_id)
        context["endpoints"] = endpoints
        context["project_summary"] = {
            "name": self.projects.currentText(), "endpoint_count": len(endpoints),
            "module_count": len({item.get("module") for item in endpoints}),
            "has_database": bool(context.get("database_connection")),
        }
        if self.ai_dialogue_route.currentData() == "route_a" and not context.get("workflow"):
            context["workflow"] = {
                "name": "AI 对话生成的 API + 数据库联合测试",
                "review_status": "draft", "requires_confirmation": True,
                "steps": [{
                    "name": f'{item["method"]} {item["path"]}', "kind": "http",
                    "request": {"method": item["method"], "path": item["path"], "headers": {}, "query": {}, "body": None},
                    "assertions": [{"type": "status_code", "operator": "equals", "expected": 200}],
                    "extract": [], "compensation": [], "review_status": "draft",
                } for item in endpoints[:30]],
            }
        connections = self.db.list_db_connections(self.current_project_id)
        if connections:
            connection = connections[-1]
            context["database_connection"] = {"backend": connection.get("backend", "sqlite"), "read_only": bool(connection.get("read_only", True)), "configured": True}
        context["base_url_configured"] = bool(self.base_url.text().strip())
        return context

    def new_ai_dialogue_session(self):
        if not self._require_project():
            return
        if self._ai_busy:
            self.cancel_ai_request()
        route = self.ai_dialogue_route.currentData() or "route_a"
        provider_name = self.ai_chat_model.currentData() if hasattr(self, "ai_chat_model") else ("codex" if self.ai_tabs.currentIndex() == 0 else "api" if self.ai_tabs.currentIndex() == 1 else "ollama")
        self._ai_dialogue_session_id = self.db.create_ai_session(self.current_project_id, route, model_provider=provider_name)
        self.ai_dialogue_history.clear(); self.ai_dialogue_artifact.clear()
        if hasattr(self, "ai_session_summary"):
            self.ai_session_summary.setPlainText(f"新会话 #{self._ai_dialogue_session_id}\n\n0 条消息\n测试模式：{self.ai_dialogue_route.currentText()}")
        if hasattr(self, "quick_ai_history"):
            self.quick_ai_history.clear()
        self.statusBar().showMessage(f"已创建 AI 测试会话 #{self._ai_dialogue_session_id}", 3000)

    def toggle_ai_assistant(self):
        if not hasattr(self, "quick_ai_panel"):
            return
        visible = not self.quick_ai_panel.isVisible()
        self.quick_ai_panel.setVisible(visible)
        self.quick_ai_button.setText("关闭助手" if visible else "AI 助手")
        if visible:
            self.quick_ai_input.setFocus()

    def use_ai_template(self, prompt: str):
        self.ai_dialogue_input.setPlainText(prompt)
        self.ai_dialogue_input.setFocus()

    def _vscode_project_root(self) -> Path | None:
        """Return the analyzed source root without relying on any VS Code token."""
        if self.current_project_id:
            analyses = self.db.list_analysis_runs(self.current_project_id)
            if analyses:
                root = Path(str(analyses[0].get("root_path") or ""))
                if root.is_dir():
                    return root
        configured_text = self.codex_path.text().strip() if hasattr(self, "codex_path") else ""
        configured = Path(configured_text) if configured_text else None
        return configured if configured and configured.is_dir() else None

    def _build_vscode_codex_prompt(self, user_request: str = "") -> str:
        if not self.current_project_id:
            raise ValueError("请先选择项目。")
        endpoints = self.db.list_endpoints(self.current_project_id)
        modules = sorted({str(item.get("module") or "未分组") for item in endpoints})
        endpoint_lines = "\n".join(
            f"- {item.get('method', 'GET')} {item.get('path', '/')}（{item.get('module') or '未分组'}）"
            for item in endpoints[:60]
        ) or "- 当前尚未导入接口，请先阅读项目源码识别接口。"
        connections = self.db.list_db_connections(self.current_project_id)
        db_note = "已配置只读测试数据库连接。" if connections else "尚未配置测试数据库；请列出需要确认的表和字段，不要猜测数据。"
        request_note = f"\n用户这次的具体请求：{user_request}\n" if user_request else ""
        return (
            "你是本项目的测试协作助手。请阅读当前工作区源码并为 TestPilot 生成可审核的接口测试方案。\n\n"
            f"项目：{self.projects.currentText()}\n"
            f"已导入接口：{len(endpoints)} 个；模块：{'、'.join(modules) or '未识别'}\n"
            f"数据库：{db_note}\n\n"
            "已知接口：\n" + endpoint_lines + "\n\n"
            "请输出 Markdown，按以下结构：\n"
            "1. 业务目标与关键流程\n2. 建议优先测试的接口及原因\n"
            "3. 每个用例：前置条件、请求、断言、关联数据库表/字段、清理或回滚\n"
            "4. 异常、权限、重复提交、事务一致性风险\n5. 还需要人工确认的信息\n\n"
            "只分析和建议，不要修改源码、启动服务、发送请求、写入数据库或执行破坏性命令。"
            + request_note
        )

    def open_vscode_codex(self, user_request: str = "") -> bool:
        if not self._require_project():
            return False
        root = self._vscode_project_root()
        if not root:
            QMessageBox.warning(self, "VS Code Codex", "未找到当前项目的源码目录。请先导入源码，或在 AI 模型配置中选择源码目录。")
            return False
        prompt = self._build_vscode_codex_prompt(user_request)
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(prompt)
        command = shutil.which("code") or shutil.which("code.cmd")
        if command:
            try:
                subprocess.Popen([command, str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.statusBar().showMessage("已打开 VS Code；任务已复制，粘贴到 Codex 对话即可获得真实回复。", 8000)
                return True
            except OSError:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))
        QMessageBox.information(
            self, "VS Code Codex", "测试任务已复制到剪贴板。未检测到 code 命令，请在 VS Code 中手动打开该目录并粘贴给 Codex。"
        )
        return True

    def import_vscode_codex_plan(self):
        if not self._require_project():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 Codex 测试方案", "", "测试方案 (*.md *.markdown *.txt *.json);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8-sig")
        except OSError as exc:
            QMessageBox.warning(self, "导入失败", f"无法读取方案文件：{exc}")
            return
        if not content.strip():
            QMessageBox.warning(self, "导入失败", "方案文件为空。")
            return
        parsed: dict | None = None
        if Path(path).suffix.lower() == ".json":
            try:
                candidate = json.loads(content)
                parsed = candidate if isinstance(candidate, dict) else {"items": candidate}
            except json.JSONDecodeError:
                QMessageBox.warning(self, "导入失败", "JSON 文件格式无效。请导入 Codex 输出的有效 JSON，或改用 Markdown。")
                return
        if not self._ai_dialogue_session_id:
            self._ai_dialogue_session_id = self.db.create_ai_session(
                self.current_project_id, "route_a", model_provider="vscode_codex"
            )
        definition = {
            "version": "1.0", "kind": "vscode_codex_test_plan", "source": "vscode_codex",
            "file_name": Path(path).name, "markdown": content if parsed is None else "",
            "plan": parsed or {}, "requires_human_approval": True,
        }
        artifact_id = self.db.save_ai_artifact(
            self._ai_dialogue_session_id, "vscode_codex_test_plan", Path(path).stem, definition,
            review_status="draft",
        )
        self.db.add_ai_message(
            self._ai_dialogue_session_id, "tool",
            f"已导入 VS Code Codex 测试方案：{Path(path).name}。请在“测试草稿与证据”中审核后再执行。",
            metadata={"artifact_id": artifact_id, "source": "vscode_codex"},
        )
        self._refresh_ai_dialogue_view(self._ai_dialogue_session_id, artifact_id)
        self.statusBar().showMessage("Codex 测试方案已导入为待审核草稿。", 6000)

    def send_quick_ai(self):
        message = self.quick_ai_input.toPlainText().strip()
        if not message:
            return
        if not self._require_project():
            return
        if self.ai_chat_model.currentData() == "codex":
            if self.open_vscode_codex(message):
                self.quick_ai_input.clear()
            return
        self._start_ai_request(message, "quick")

    def _present_ai_error(self, title: str, error: Exception):
        detail = str(error).strip() or error.__class__.__name__
        if hasattr(self, "ai_dialogue_artifact"):
            self.ai_dialogue_artifact.setPlainText("AI 调用诊断（未生成测试草稿）\n\n" + detail[:12000])
        if hasattr(self, "quick_ai_history"):
            self.quick_ai_history.setPlainText("发送失败。详细诊断已写入完整 AI 页的“测试草稿与证据”。")
        summary = detail.splitlines()[0][:220]
        if "Not logged in" in detail or "尚未登录" in detail:
            summary = "Codex 尚未登录。请到“AI 模型配置”完成 ChatGPT 登录并重新检测。"
        elif "WinError 206" in detail:
            summary = "Codex 输入过长。请重启应用以加载已修复的标准输入调用方式。"
        QMessageBox.warning(self, title, summary + "\n\n详细信息已放到“测试草稿与证据”页签。")

    def _dialogue(self, cancel_event: Event | None = None) -> ControlledDialogue:
        if not self._require_project():
            raise ValueError("请先选择项目")
        selected_mode = self.ai_chat_model.currentData() if hasattr(self, "ai_chat_model") else None
        provider_name = selected_mode or ("codex" if self.ai_tabs.currentIndex() == 0 else "api" if self.ai_tabs.currentIndex() == 1 else "ollama")
        try:
            provider = self._workflow_model_provider(check_status=False, cancel_event=cancel_event, mode_override=provider_name)
        except Exception as exc:
            raise RuntimeError(f"当前 AI 配置不可用：{exc}。请到“AI 模型配置”检测连接后重试。") from exc
        if not self._ai_dialogue_session_id:
            self._ai_dialogue_session_id = self.db.create_ai_session(
                self.current_project_id, self.ai_dialogue_route.currentData() or "route_a",
                model_provider=provider_name,
            )
        return ControlledDialogue(self.db, self.current_project_id, self.ai_dialogue_route.currentData() or "route_a", provider=provider, session_id=self._ai_dialogue_session_id)

    def send_ai_dialogue(self):
        if not self._require_project():
            return
        message = self.ai_dialogue_input.toPlainText().strip()
        if not message:
            QMessageBox.information(self, "提示", "请先输入业务流程或测试目标")
            return
        if self.ai_chat_model.currentData() == "codex":
            if self.open_vscode_codex(message):
                self.ai_dialogue_input.clear()
            return
        self._start_ai_request(message, "page")

    def _start_ai_request(self, message: str, origin: str):
        if self._ai_busy:
            self.statusBar().showMessage("AI 正在生成，请等待当前请求完成。", 3000)
            return
        try:
            self._ai_cancel_event = Event()
            dialogue = self._dialogue(self._ai_cancel_event)
            context = self._dialogue_context()
        except Exception as exc:
            self._present_ai_error("AI 对话失败", exc)
            return
        if origin == "quick":
            self.quick_ai_input.clear()
        else:
            self.ai_dialogue_input.clear()
        self._ai_request_id += 1
        worker = _AIWorker(dialogue, message, context, self._ai_request_id)
        worker.signals.completed.connect(self._ai_request_completed)
        worker.signals.failed.connect(self._ai_request_failed)
        self._active_ai_worker = worker
        self._ai_workers[self._ai_request_id] = worker
        self._show_ai_pending(message)
        self._set_ai_busy(True)
        self._ai_thread_pool.start(worker)

    def _show_ai_pending(self, message: str):
        self._render_ai_chat(self._ai_dialogue_session_id, pending_message=message)

    def _set_ai_busy(self, busy: bool):
        self._ai_busy = busy
        for button in (getattr(self, "ai_dialogue_send", None), getattr(self, "quick_ai_send", None)):
            if button:
                button.setEnabled(not busy)
                button.setText("生成中…" if busy else "发送")
        for button in (getattr(self, "ai_dialogue_cancel", None), getattr(self, "quick_ai_cancel", None)):
            if button:
                button.setVisible(busy)
                button.setEnabled(busy)
                button.setText("取消生成")
        if busy:
            timeout = self.ai_timeout.value() if hasattr(self, "ai_timeout") else 45
            if getattr(self, "ai_dialogue_route", None) and self.ai_dialogue_route.currentData() == "chat":
                timeout = min(timeout, 8)
            retries = self.ai_retries.value() if hasattr(self, "ai_retries") else 1
            self.statusBar().showMessage(f"AI 正在回复；最长等待 {timeout} 秒，可随时取消。")
        else:
            self.statusBar().showMessage("AI 请求已完成", 3000)

    def cancel_ai_request(self):
        if not self._ai_busy or not self._ai_cancel_event:
            return
        self._ai_cancel_event.set()
        for button in (getattr(self, "ai_dialogue_cancel", None), getattr(self, "quick_ai_cancel", None)):
            if button:
                button.setEnabled(False)
                button.setText("正在取消…")
        self.statusBar().showMessage("正在终止 AI 请求…")

    @Slot(object, object, object)
    def _ai_request_completed(self, request_id, dialogue, result):
        self._ai_workers.pop(request_id, None)
        if request_id != self._ai_request_id:
            return
        self._set_ai_busy(False)
        self._active_ai_worker = None
        self._ai_cancel_event = None
        self._refresh_ai_dialogue_view(dialogue.session_id, result.artifact_id)

    @Slot(object, object)
    def _ai_request_failed(self, request_id, error):
        self._ai_workers.pop(request_id, None)
        if request_id != self._ai_request_id:
            return
        self._set_ai_busy(False)
        self._active_ai_worker = None
        self._ai_cancel_event = None
        if isinstance(error, AIRequestCancelled):
            self._render_ai_chat(self._ai_dialogue_session_id, assistant_notice="本次生成已取消。")
            self.statusBar().showMessage("AI 请求已取消。", 3000)
            return
        self._render_ai_chat(self._ai_dialogue_session_id, assistant_notice=f"生成失败：{str(error).splitlines()[0][:300]}")
        self._present_ai_error("AI 对话失败", error)

    def closeEvent(self, event):
        if self._ai_cancel_event:
            self._ai_cancel_event.set()
            self._ai_thread_pool.waitForDone(3000)
        super().closeEvent(event)

    def _refresh_ai_dialogue_view(self, session_id: int, artifact_id: int | None = None):
        messages = self.db.list_ai_messages(session_id)
        self._render_ai_chat(session_id)
        if hasattr(self, "ai_session_summary"):
            self.ai_session_summary.setPlainText(f"当前会话\n\n{len(messages)} 条消息\n测试模式：{self.ai_dialogue_route.currentText()}")
        artifacts = self.db.list_ai_artifacts(session_id)
        if artifacts:
            artifact = next((item for item in artifacts if item["id"] == artifact_id), artifacts[0])
            approvals = self.db.list_ai_approvals(session_id)
            self.ai_dialogue_artifact.setPlainText(json.dumps({"artifact": artifact, "approvals": approvals}, ensure_ascii=False, indent=2))

    def _render_ai_chat(self, session_id: int | None, pending_message: str = "", assistant_notice: str = ""):
        messages = self.db.list_ai_messages(session_id) if session_id else []
        self.ai_dialogue_history.render(messages, pending_message, assistant_notice)
        if hasattr(self, "quick_ai_history"):
            role_names = {"user": "我", "assistant": "AI", "tool": "系统", "system": "系统"}
            transcript = "\n\n".join(f"{role_names.get(item['role'], item['role'])}：\n{item['content']}" for item in messages)
            if pending_message:
                transcript += f"\n\n我：\n{pending_message}\n\nAI：\n正在思考…"
            if assistant_notice:
                transcript += f"\n\nAI：\n{assistant_notice}"
            self.quick_ai_history.setPlainText(transcript)

    def approve_latest_ai_artifact(self):
        self._decide_latest_ai_artifact("approved")

    def reject_latest_ai_artifact(self):
        self._decide_latest_ai_artifact("rejected")

    def _decide_latest_ai_artifact(self, status: str):
        if not self._ai_dialogue_session_id:
            QMessageBox.information(self, "提示", "当前没有 AI 对话会话")
            return
        approvals = self.db.list_ai_approvals(self._ai_dialogue_session_id)
        pending = next((item for item in approvals if item["status"] == "pending"), None)
        if not pending:
            QMessageBox.information(self, "提示", "当前没有待审批草稿")
            return
        try:
            dialogue = self._dialogue()
            if status == "approved":
                dialogue.approve(int(pending["id"]), "人工在 AI 对话页确认")
                artifact = next((item for item in self.db.list_ai_artifacts(self._ai_dialogue_session_id) if item["id"] == pending.get("artifact_id")), None)
                script = (artifact or {}).get("definition", {}).get("process_script") or {}
                if script.get("steps"):
                    script["review_status"] = "draft"
                    script["requires_confirmation"] = True
                    analyses = self.db.list_analysis_runs(self.current_project_id)
                    workflow_id = self.db.save_workflow(
                        self.current_project_id, script.get("name", "AI API + 数据库联合测试"), script,
                        source_analysis_run_id=int(analyses[0]["id"]) if analyses else None,
                    )
                    self.db.audit(self.current_project_id, "promote_ai_process_script", {"artifact_id": pending.get("artifact_id"), "workflow_id": workflow_id})
                    self.refresh_workflows()
                    self.workflow_selector.setCurrentIndex(self.workflow_selector.findData(workflow_id))
                    self.workflow_output.setPlainText("AI 联合测试计划已进入路线 A。请审核 API 参数、关联表查询和状态预期，确认后即可执行。")
            else:
                dialogue.reject(int(pending["id"]), "人工要求补充或修改")
            self._refresh_ai_dialogue_view(self._ai_dialogue_session_id, pending.get("artifact_id"))
        except Exception as exc:
            QMessageBox.warning(self, "审批失败", str(exc))

    def refresh_workflows(self):
        if not hasattr(self, "workflow_selector"):
            return
        current = self.workflow_selector.currentData()
        rows = self.db.list_workflows(self.current_project_id) if self.current_project_id else []
        self.workflow_selector.blockSignals(True)
        self.workflow_selector.clear()
        for row in rows:
            self.workflow_selector.addItem(f'{row["name"]} · {row["review_status"]}', row["id"])
        index = self.workflow_selector.findData(current)
        self.workflow_selector.setCurrentIndex(index if index >= 0 else (0 if rows else -1))
        self.workflow_selector.blockSignals(False)
        if rows:
            self.load_workflow()
        else:
            self.workflow_json.clear()

    def load_workflow(self):
        workflow_id = self.workflow_selector.currentData() if hasattr(self, "workflow_selector") else None
        if not workflow_id:
            return
        row = self.db.get_workflow(int(workflow_id))
        if row:
            try:
                definition = json.loads(row["definition_json"] or "{}")
                self.workflow_json.setPlainText(json.dumps(definition, ensure_ascii=False, indent=2))
                self.workflow_scope.setPlainText("，".join(definition.get("test_focus", [])))
            except (TypeError, ValueError):
                self.workflow_json.setPlainText(row["definition_json"])
                self.workflow_scope.clear()

    def _workflow_model_provider(self, check_status: bool = True, cancel_event: Event | None = None, mode_override: str | None = None):
        mode = {"codex": 0, "api": 1, "ollama": 2}.get(mode_override, self.ai_tabs.currentIndex())
        timeout = self.ai_timeout.value() if hasattr(self, "ai_timeout") else 45
        retries = self.ai_retries.value() if hasattr(self, "ai_retries") else 1
        if mode == 0:
            provider = CodexCliProvider(
                self.codex_path.text().strip(), self.codex_model.text().strip(),
                timeout=timeout, retries=retries, cancel_event=cancel_event,
            )
            if check_status:
                ok, status = provider.status()
                if not ok:
                    raise RuntimeError(f"Codex 尚未登录：{status}")
            return provider
        if mode == 1:
            if not all((self.model_url.text().strip(), self.model_name.text().strip(), self.model_key.text())):
                raise ValueError("请先在“AI 与 Codex”中完成兼容 API 配置")
            return OpenAICompatibleProvider(
                self.model_url.text().strip(), self.model_key.text(), self.model_name.text().strip(),
                timeout=timeout, retries=retries, cancel_event=cancel_event,
            )
        return OllamaProvider(
            self.ollama_url.text().strip(), self.ollama_model.text().strip(),
            timeout=timeout, retries=retries, cancel_event=cancel_event,
        )

    @staticmethod
    def _normalize_workflow_steps(definition: dict) -> dict:
        for step in definition.get("steps", []):
            step.setdefault("kind", "http")
            step.setdefault("request", {"method": "GET", "path": "/", "headers": {}, "query": {}, "body": None})
            step.setdefault("assertions", [])
            step.setdefault("extract", [])
            step.setdefault("compensation", [])
            step.setdefault("review_status", "draft")
            step.setdefault("internal_checkpoints", [])
            step.setdefault("failure_branches", [])
            step.setdefault("invariants", [])
        definition.setdefault("data_flows", [])
        definition.setdefault("database_changes", [])
        definition.setdefault("test_focus", [])
        definition["review_status"] = "draft"
        definition["requires_confirmation"] = True
        return definition

    def generate_workflow_draft(self):
        if not self._require_project():
            return
        analyses = self.db.list_analysis_runs(self.current_project_id)
        if not analyses:
            QMessageBox.information(self, "提示", "请先导入后端源码并完成源码分析。")
            return
        try:
            latest = analyses[0]
            analysis, candidate = BackendSourceParser().suggest_workflow(latest["root_path"])
            candidate["generation_mode"] = "rule_based"
            try:
                provider = self._workflow_model_provider()
                prompt = json.dumps({
                    "instruction": "分析源码并设计可人工审核的业务流程，不执行源码、不发送请求。必须识别数据流、可能修改的数据库实体、异常分支和补偿动作。",
                    "source_root": latest["root_path"],
                    "analysis": {key: value for key, value in analysis.items() if key != "document"},
                    "endpoints": [endpoint.to_dict() for endpoint in analysis["document"].endpoints],
                    "draft": candidate,
                }, ensure_ascii=False)
                generated = provider.generate_structured(
                    "你是源码驱动接口测试设计器，只输出结构化业务流程草稿。所有数据库变更和副作用必须标注为候选并要求人工确认。",
                    prompt, WORKFLOW_GENERATION_SCHEMA,
                )
                from jsonschema import validate
                validate(generated, WORKFLOW_GENERATION_SCHEMA)
                candidate = self._normalize_workflow_steps(generated)
                candidate = build_process_script(candidate, analysis)
                candidate["generation_mode"] = "ai"
            except Exception as ai_error:
                candidate["ai_note"] = f"AI 未生成，保留确定性源码候选：{ai_error}"
            candidate["flow_model"] = build_flow_model(analysis, candidate)
            workflow_id = self.db.save_workflow(
                self.current_project_id, candidate["name"], candidate, source_analysis_run_id=latest["id"]
            )
            self.db.save_data_flow_model(
                self.current_project_id, f"{candidate['name']} · 数据流", candidate["flow_model"],
                source_analysis_run_id=latest["id"], workflow_id=workflow_id,
            )
            self.db.audit(self.current_project_id, "create_workflow_draft", {
                "workflow_id": workflow_id, "analysis_run_id": latest["id"],
                "summary": analysis.get("summary", {}),
            })
            self.refresh_workflows()
            self.workflow_selector.setCurrentIndex(self.workflow_selector.findData(workflow_id))
            self.workflow_output.setPlainText(
                f"已生成流程草稿（{candidate.get('generation_mode')}）。请补充参数、数据绑定、数据流、数据库变更、断言和补偿动作，确认后才能执行。"
            )
        except Exception as exc:
            QMessageBox.critical(self, "流程生成失败", str(exc))

    def save_workflow(self):
        if not self._require_project():
            return
        try:
            definition = json.loads(self.workflow_json.toPlainText() or "{}")
            if not isinstance(definition, dict) or not isinstance(definition.get("steps", []), list):
                raise ValueError("流程必须是包含 steps 数组的 JSON 对象")
            if definition.get("flow_model"):
                errors = validate_flow_model(definition["flow_model"])
                if errors:
                    raise ValueError("数据流模型无效：" + "；".join(errors))
            workflow_id = self.workflow_selector.currentData()
            if workflow_id:
                self.db.update_workflow(int(workflow_id), definition)
            else:
                workflow_id = self.db.save_workflow(self.current_project_id, definition.get("name", "未命名流程"), definition)
            if definition.get("flow_model"):
                self.db.save_data_flow_model(self.current_project_id, f"{definition.get('name','未命名流程')} · 数据流", definition["flow_model"], workflow_id=int(workflow_id))
            self.db.audit(self.current_project_id, "save_workflow", {"workflow_id": workflow_id})
            self.refresh_workflows()
            self.workflow_selector.setCurrentIndex(self.workflow_selector.findData(workflow_id))
        except Exception as exc:
            QMessageBox.warning(self, "流程无效", str(exc))

    def confirm_workflow(self):
        workflow_id = self.workflow_selector.currentData() if hasattr(self, "workflow_selector") else None
        if not workflow_id:
            QMessageBox.information(self, "提示", "请先生成或保存流程草稿")
            return
        try:
            definition = json.loads(self.workflow_json.toPlainText() or "{}")
            if not definition.get("steps"):
                raise ValueError("流程至少需要一个步骤")
            if definition.get("flow_model"):
                errors = validate_flow_model(definition["flow_model"])
                if errors:
                    raise ValueError("请先修正数据流模型：" + "；".join(errors))
                definition["flow_model"]["review_status"] = "confirmed"
            definition["review_status"] = "confirmed"
            self.db.update_workflow(int(workflow_id), definition)
            self.db.update_workflow_status(int(workflow_id), "confirmed")
            self.db.audit(self.current_project_id, "confirm_workflow", {"workflow_id": workflow_id})
            self.refresh_workflows()
            self.workflow_selector.setCurrentIndex(self.workflow_selector.findData(workflow_id))
        except Exception as exc:
            QMessageBox.warning(self, "确认失败", str(exc))

    def check_process_coverage(self):
        try:
            definition = json.loads(self.workflow_json.toPlainText() or "{}")
            coverage = evaluate_process_script(definition)
            definition["coverage"] = coverage
            self.workflow_json.setPlainText(json.dumps(definition, ensure_ascii=False, indent=2))
            self.workflow_output.setPlainText(json.dumps({
                "结论": "存在证据缺口，执行结果不得判定通过" if any(item.get("critical") for item in coverage["issues"]) else "关键内部工艺已有证据",
                "工艺覆盖率": f'{coverage["score"]}%',
                "内部节点": coverage["internal_total"],
                "已观测节点": coverage["internal_observed"],
                "问题": coverage["issues"],
            }, ensure_ascii=False, indent=2))
        except Exception as exc:
            QMessageBox.warning(self, "工艺脚本无效", str(exc))

    def create_manual_workflow(self):
        if not self._require_project():
            return
        endpoints = self.db.list_endpoints(self.current_project_id)
        definition = {
            "name": "人工业务流程草稿",
            "review_status": "draft",
            "requires_confirmation": True,
            "generation_mode": "manual",
            "data_flows": [],
            "database_changes": [],
            "test_focus": [],
            "steps": [
                {
                    "name": f'{row["method"]} {row["path"]}', "kind": "http",
                    "request": {"method": row["method"], "path": row["path"], "headers": {}, "query": {}, "body": None},
                    "assertions": [], "extract": [], "compensation": [], "review_status": "draft",
                } for row in endpoints[:20]
            ],
        }
        self.workflow_json.setPlainText(json.dumps(definition, ensure_ascii=False, indent=2))
        self.workflow_output.setPlainText("已创建人工流程草稿，请补全数据流、数据库变更、异常分支和补偿动作后保存。")

    def confirm_workflow_scope(self):
        workflow_id = self.workflow_selector.currentData() if hasattr(self, "workflow_selector") else None
        if not workflow_id:
            QMessageBox.information(self, "提示", "请先选择或保存流程")
            return
        try:
            definition = json.loads(self.workflow_json.toPlainText() or "{}")
            raw = self.workflow_scope.toPlainText().strip()
            if not raw:
                raise ValueError("请先填写测试方向")
            focuses = [item.strip() for item in raw.replace("，", ",").replace("\n", ",").split(",") if item.strip()]
            definition["test_focus"] = focuses
            definition["scope_confirmed"] = True
            definition["review_status"] = "draft"
            self.db.update_workflow(int(workflow_id), definition)
            self.db.audit(self.current_project_id, "confirm_workflow_scope", {"workflow_id": workflow_id, "test_focus": focuses})
            self.workflow_json.setPlainText(json.dumps(definition, ensure_ascii=False, indent=2))
            self.workflow_output.setPlainText("测试范围已记录。现在可以生成接口测试用例；流程本身仍需最终确认。")
        except Exception as exc:
            QMessageBox.warning(self, "测试范围无效", str(exc))

    def generate_workflow_cases(self):
        if not self._require_project():
            return
        workflow_id = self.workflow_selector.currentData()
        if not workflow_id:
            QMessageBox.information(self, "提示", "请先选择业务流程")
            return
        try:
            definition = json.loads(self.workflow_json.toPlainText() or "{}")
            if not definition.get("scope_confirmed"):
                raise ValueError("请先确认测试范围")
            endpoints = self._case_scope_endpoints()
            cases = generate_cases(endpoints, "；".join(definition.get("test_focus", [])))
            for case in cases:
                case["workflow_id"] = int(workflow_id)
                case["source"] = "route_a_workflow"
                case["workflow_focus"] = definition.get("test_focus", [])
            self.db.save_test_cases(self.current_project_id, cases)
            self.refresh_cases()
            self.go_to_page(3)
            self.run_output.setPlainText(f"已根据路线 A 流程和确认范围生成 {len(cases)} 条接口测试用例，请继续人工审核。")
        except Exception as exc:
            QMessageBox.warning(self, "用例生成失败", str(exc))

    def choose_workflow_database(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 SQLite 测试库", "", "SQLite (*.db *.sqlite *.sqlite3);;所有文件 (*)")
        if path:
            self.workflow_db_path.setText(path)

    def save_workflow_database(self):
        if not self._require_project():
            return
        path = self.workflow_db_path.text().strip()
        if not path or not Path(path).is_file():
            QMessageBox.warning(self, "数据库配置", "请选择存在的 SQLite 测试数据库文件")
            return
        connection_id = self.db.save_db_connection(
            self.current_project_id, "业务流程测试库", path, self.workflow_db_read_only.isChecked(),
        )
        self.db.audit(self.current_project_id, "save_workflow_database", {
            "connection_id": connection_id, "read_only": self.workflow_db_read_only.isChecked(),
        })
        self.statusBar().showMessage("测试数据库配置已保存", 3000)

    def inspect_workflow_database(self):
        if not self._require_project():
            return
        path = self.workflow_db_path.text().strip()
        if not path or not Path(path).is_file():
            QMessageBox.warning(self, "数据库检查", "请选择存在的 SQLite 测试数据库文件")
            return
        try:
            snapshot = inspect_sqlite_database(path, read_only=True)
            connections = self.db.list_db_connections(self.current_project_id)
            connection_id = connections[-1]["id"] if connections else None
            snapshot_id = self.db.save_db_schema_snapshot(self.current_project_id, connection_id, snapshot)
            self.workflow_output.setPlainText(json.dumps({"snapshot_id": snapshot_id, **snapshot}, ensure_ascii=False, indent=2))
        except Exception as exc:
            QMessageBox.warning(self, "数据库检查失败", str(exc))

    def generate_ab_difference_report(self):
        if not self._require_project():
            return
        workflow_id = self.workflow_selector.currentData() if hasattr(self, "workflow_selector") else None
        workflow = {}
        if workflow_id:
            row = self.db.get_workflow(int(workflow_id))
            if row:
                workflow = json.loads(row.get("definition_json") or "{}")
        analyses = self.db.list_analysis_runs(self.current_project_id)
        analysis = {}
        if analyses:
            run_id = int(analyses[0]["id"])
            analysis = {"evidence": self.db.list_analysis_evidence(run_id)}
        endpoints = [SimpleNamespace(method=item["method"], path=item["path"]) for item in self.db.list_endpoints(self.current_project_id)]
        difference = build_combined_difference(SimpleNamespace(endpoints=endpoints), analysis, workflow)
        html_path, json_path = generate_difference_report(self.db.path.parent / "reports", self.projects.currentText(), difference)
        self.db.save_evidence_report(self.current_project_id, "A/B 差异报告", str(html_path), str(json_path), difference, "combined", self.env_name.text().strip())
        self.workflow_output.setPlainText(json.dumps(difference, ensure_ascii=False, indent=2) + f"\n\nHTML：{html_path}\nJSON：{json_path}")

    def export_workflow_replay(self):
        if not self._require_project():
            return
        workflow_id = self.workflow_selector.currentData() if hasattr(self, "workflow_selector") else None
        if not workflow_id:
            QMessageBox.information(self, "提示", "请先选择业务流程")
            return
        row = self.db.get_workflow(int(workflow_id))
        if not row:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出可重放测试包", "testpilot-replay.tpa", "TestPilot 重放包 (*.tpa)")
        if not path:
            return
        workflow = json.loads(row.get("definition_json") or "{}")
        package = export_replay_package(path, {"id": self.current_project_id, "name": self.projects.currentText()}, workflow=workflow, cases=self.db.list_test_cases(self.current_project_id), environment={"name": self.env_name.text(), "base_url": self.base_url.text()})
        self.workflow_output.setPlainText(f"已导出脱敏重放包：{package}")

    def save_workflow_fixture(self):
        if not self._require_project():
            return
        try:
            definition = json.loads(self.workflow_fixture_json.text() or "{}")
            if not definition.get("table") or not definition.get("rows"):
                raise ValueError("夹具必须包含 table 和 rows")
            workflow_id = self.workflow_selector.currentData()
            fixture_id = self.db.save_fixture(
                self.current_project_id, self.workflow_fixture_name.text().strip() or "未命名夹具",
                definition, int(workflow_id) if workflow_id else None,
            )
            self.db.audit(self.current_project_id, "save_workflow_fixture", {"fixture_id": fixture_id})
            self.workflow_output.setPlainText(f"已保存测试夹具 #{fixture_id}。执行流程前请取消数据库只读。")
        except Exception as exc:
            QMessageBox.warning(self, "夹具无效", str(exc))

    def execute_workflow(self):
        if not self._require_project():
            return
        if not self.environment_confirmed.isChecked():
            QMessageBox.warning(self, "执行被阻止", "请先确认目标是已授权的测试环境。")
            return
        workflow_id = self.workflow_selector.currentData()
        if not workflow_id:
            QMessageBox.information(self, "提示", "请先选择业务流程")
            return
        row = self.db.get_workflow(int(workflow_id))
        if not row:
            return
        definition = json.loads(row["definition_json"])
        if row["review_status"] != "confirmed":
            QMessageBox.warning(self, "执行被阻止", "流程必须先人工确认")
            return
        if any(step.get("kind", "http") in {"http", "side_effect_check"} for step in definition.get("steps", [])) and not self.base_url.text().strip():
            QMessageBox.warning(self, "执行被阻止", "联合测试包含 API 步骤，请先配置已启动后端的 Base URL。")
            return
        connections = self.db.list_db_connections(self.current_project_id)
        database = None; connection_id = None
        if connections:
            connection = connections[-1]
            connection_id = connection["id"]
            try:
                db_config = json.loads(connection.get("config_json") or "{}")
                if connection.get("secrets_encrypted"):
                    db_config.update(self.secret_store.decrypt_dict(connection["secrets_encrypted"]))
                database = create_database_adapter(
                    connection.get("backend", "sqlite"), connection["target_path"],
                    bool(connection["read_only"]), db_config,
                )
            except Exception as adapter_error:
                self.workflow_output.setPlainText(f"数据库适配器不可用：{adapter_error}")
                return
        if definition.get("state_observations") and database is None:
            QMessageBox.warning(self, "执行被阻止", "联合测试包含数据库状态验证，请先配置测试数据库连接。")
            return
        try:
            variables = json.loads(self.variables.toPlainText() or "{}")
            fixtures = [
                json.loads(item["definition_json"]) for item in self.db.list_fixtures(self.current_project_id, int(workflow_id))
            ]
            run_id = self.db.create_workflow_run(self.current_project_id, int(workflow_id), connection_id)
            trace = TraceCollector()
            results, summary = run_workflow(
                definition, self.base_url.text(), json.loads(self.headers.toPlainText() or "{}"),
                variables=variables, database=database, fixtures=fixtures, stop_event=getattr(self, "_stop_event", None), trace=trace,
            )
            for index, result in enumerate(results, 1):
                self.db.save_workflow_step_result(run_id, None, int(result.get("step_order", index)), result.get("status", "error"), result)
            self.db.finish_workflow_run(run_id, summary["status"], summary)
            trace_row_id = self.db.save_workflow_trace(run_id, trace.to_dict(), summary["status"])
            self.db.audit_workflow(run_id, "workflow_completed", summary)
            html_path, json_path = generate_workflow_report(
                self.db.path.parent / "reports", self.projects.currentText(), row["name"], results, summary,
                report_type="业务流程报告", route="route_a", environment=self.env_name.text().strip(),
            )
            self.db.save_workflow_report(run_id, str(html_path), str(json_path), "业务流程报告", "route_a", self.env_name.text().strip())
            self.workflow_output.setPlainText(
                json.dumps({"run_id": run_id, **summary, "results": results}, ensure_ascii=False, indent=2)
                + f"\n\nTrace：{trace.trace_id}（记录 #{trace_row_id}）\nHTML：{html_path}\nJSON：{json_path}"
            )
        except Exception as exc:
            self.workflow_output.setPlainText(f"流程执行失败：{exc}")

    def select_case_project(self):
        project_id = self.case_project_selector.currentData()
        index = self.projects.findData(project_id)
        if index >= 0 and self.projects.currentIndex() != index:
            self.projects.setCurrentIndex(index)

    def refresh_case_module_filter(self):
        if not hasattr(self, "case_module_filter"):
            return
        current = self.case_module_filter.currentData()
        modules = sorted({row["module"] for row in self.db.list_endpoints(self.current_project_id)}) if self.current_project_id else []
        self.case_module_filter.blockSignals(True)
        self.case_module_filter.clear()
        self.case_module_filter.addItem("全部模块", None)
        for module in modules:
            self.case_module_filter.addItem(module, module)
        index = self.case_module_filter.findData(current)
        self.case_module_filter.setCurrentIndex(max(0, index))
        self.case_module_filter.blockSignals(False)

    def refresh_endpoint_filters(self):
        if not hasattr(self, "source_filter"):
            return
        rows = self.db.list_endpoints(self.current_project_id) if self.current_project_id else []
        current_source = self.source_filter.currentData()
        current_module = self.module_filter.currentData()
        self.source_filter.blockSignals(True)
        self.module_filter.blockSignals(True)
        self.source_filter.clear(); self.source_filter.addItem("全部资料源", None)
        for source_id, source_name in sorted({(row["source_id"], row["source_name"]) for row in rows}):
            self.source_filter.addItem(source_name, source_id)
        self.module_filter.clear(); self.module_filter.addItem("全部模块", None)
        for module in sorted({row["module"] for row in rows}):
            self.module_filter.addItem(module, module)
        source_index = self.source_filter.findData(current_source)
        module_index = self.module_filter.findData(current_module)
        self.source_filter.setCurrentIndex(max(0, source_index))
        self.module_filter.setCurrentIndex(max(0, module_index))
        self.source_filter.blockSignals(False)
        self.module_filter.blockSignals(False)
        self.endpoint_project_label.setText(
            f"当前项目：{self.projects.currentText()}  ·  {len(rows)} 个接口"
            if self.current_project_id else "当前项目：未选择"
        )

    def new_project(self):
        name, ok = QInputDialog.getText(self, "新建项目", "项目名称")
        if ok and name.strip():
            self.current_project_id = self.db.create_project(name)
            self.refresh_projects()

    def delete_project(self):
        if not self.current_project_id:
            return
        if QMessageBox.question(self, "删除项目", "确定删除当前项目及其接口数据？") == QMessageBox.Yes:
            self.db.delete_project(self.current_project_id); self.current_project_id = None; self.refresh_projects()

    def import_openapi(self):
        if not self.current_project_id:
            QMessageBox.information(self, "提示", "请先新建项目"); return
        path, _ = QFileDialog.getOpenFileName(self, "导入接口文档", "", "OpenAPI (*.json *.yaml *.yml);;所有文件 (*)")
        if not path:
            return
        try:
            document = OpenApiParser().parse_file(path)
            report = self._save_document(Path(path).name, document)
        except (OpenApiParseError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "导入失败", str(exc)); return
        suggestions = "\n".join(f"• {x}" for x in report.suggestions) or "• 暂无"
        self.summary.setPlainText(
            f"文档：{document.title} {document.version}\n规范：{document.specification}\n"
            f"接口：{report.endpoint_count} 个\n模块：{report.module_count} 个\n"
            f"完整度：{report.score}%（{report.level}）\n缺少 Base URL：{report.missing_base_url}\n"
            f"缺少请求示例：{report.missing_request_example}\n缺少响应 Schema：{report.missing_response_schema}\n"
            f"缺少鉴权说明：{report.missing_auth}\n\n建议：\n{suggestions}"
        )
        if document.base_urls and not self.base_url.text():
            self.base_url.setText(document.base_urls[0])
        self.refresh_endpoint_filters(); self.refresh_endpoints()

    def import_openapi_url(self):
        if not self._require_project():
            return
        url, ok = QInputDialog.getText(self, "在线 OpenAPI", "文档 URL")
        if not ok or not url.strip():
            return
        try:
            document = OpenApiParser().parse_url(url.strip())
            self._save_document(url.strip(), document)
            if document.base_urls and not self.base_url.text():
                self.base_url.setText(document.base_urls[0])
        except Exception as exc:
            QMessageBox.critical(self, "在线导入失败", str(exc)); return
        self.refresh_endpoint_filters(); self.refresh_endpoints()

    def import_postman(self):
        if not self._require_project():
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入 Postman Collection", "", "Postman Collection (*.json)")
        if not path:
            return
        try:
            parser = PostmanParser()
            document = parser.parse_file(path)
            self._save_document(Path(path).name, document)
            self.summary.append(
                "\nPostman 脚本："
                f"可转换 {parser.script_report['converted']}，"
                f"需人工确认 {parser.script_report['manual_review']}，"
                f"禁止执行 {parser.script_report['blocked']}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc)); return
        self.refresh_endpoint_filters(); self.refresh_endpoints()

    def import_postman_environment(self):
        if not self._require_project():
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入 Postman Environment", "", "Postman Environment (*.json)")
        if not path:
            return
        try:
            name, values, sensitive_names = parse_postman_environment(path)
            secrets = {key: value for key, value in values.items() if key in sensitive_names}
            public = {key: value for key, value in values.items() if key not in sensitive_names}
            base_url = public.pop("baseUrl", public.pop("base_url", self.base_url.text()))
            self.db.save_environment(
                self.current_project_id, name, base_url, {}, public, self.secret_store.encrypt_dict(secrets)
            )
            self.db.audit(self.current_project_id, "import_postman_environment",
                          {"name": name, "variables": len(values), "sensitive": len(secrets)})
            self.env_name.setText(name); self.base_url.setText(base_url)
            self.variables.setPlainText(json.dumps(values, ensure_ascii=False, indent=2))
        except Exception as exc:
            QMessageBox.critical(self, "环境导入失败", str(exc))

    def import_apifox(self):
        if not self._require_project():
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入 Apifox 数据", "", "Apifox JSON (*.json)")
        if not path:
            return
        try:
            document = ApifoxParser().parse_file(path); self._save_document(Path(path).name, document)
        except Exception as exc:
            QMessageBox.critical(self, "Apifox 导入失败", str(exc)); return
        self.refresh_endpoint_filters(); self.refresh_endpoints()

    def import_document(self):
        if not self._require_project():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "导入接口文档", "",
            "接口文档 (*.md *.txt *.html *.htm *.xlsx *.xlsm *.docx *.pdf)"
        )
        if not path:
            return
        try:
            document = DocumentParser().parse_file(path); self._save_document(Path(path).name, document)
        except Exception as exc:
            QMessageBox.critical(self, "文档提取失败", str(exc)); return
        QMessageBox.information(self, "需要确认", "文档提取结果属于接口草稿，请在接口详情中人工核对后再生成用例。")
        self.refresh_endpoint_filters(); self.refresh_endpoints()

    def import_curl(self):
        if not self._require_project():
            return
        command, ok = QInputDialog.getMultiLineText(self, "导入 cURL", "粘贴 cURL 命令")
        if not ok or not command.strip():
            return
        try:
            document = parse_curl(command)
            self._save_document("粘贴的 cURL", document)
            if document.base_urls:
                self.base_url.setText(document.base_urls[0])
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc)); return
        self.refresh_endpoint_filters(); self.refresh_endpoints()

    def import_backend_source(self):
        if not self._require_project():
            return
        path = QFileDialog.getExistingDirectory(self, "选择后端源码项目目录")
        if not path:
            return
        try:
            analysis = BackendSourceParser().analyze_directory(path)
            document = analysis["document"]
            if not document.endpoints:
                raise ValueError(
                    f"已识别为 {document.specification}，但没有找到接口。"
                    "请确认选择的是包含 Controller 的后端项目目录。"
                )
            removed = self.db.delete_empty_sources(self.current_project_id)
            self._save_document(Path(path).name, document, source_analysis=analysis, source_root=path)
            self.codex_path.setText(path)
            self.db.set_setting("codex_project_path", path)
            if removed:
                self.db.audit(
                    self.current_project_id, "remove_empty_source",
                    {"count": removed, "reason": "backend_source_reimport"},
                )
        except Exception as exc:
            QMessageBox.critical(self, "源码解析失败", str(exc)); return
        self.refresh_endpoint_filters(); self.refresh_endpoints()

    def import_spring(self):
        """Backward-compatible entry point for older UI/tests."""
        self.import_backend_source()

    def import_har(self):
        if not self._require_project():
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入 HAR", "", "HAR 文件 (*.har *.json)")
        if not path:
            return
        try:
            document = HarParser().parse_file(path)
            self._save_document(Path(path).name, document)
            if document.base_urls and not self.base_url.text():
                self.base_url.setText(document.base_urls[0])
        except Exception as exc:
            QMessageBox.critical(self, "HAR 导入失败", str(exc)); return
        self.refresh_endpoint_filters(); self.refresh_endpoints()

    def _save_document(self, name, document, source_analysis=None, source_root=None):
        report = check_completeness(document)
        source_id = self.db.save_document(self.current_project_id, name, document, report)
        if source_analysis is not None:
            self.db.save_source_analysis(self.current_project_id, source_analysis, source_id=source_id)
            self.db.audit(self.current_project_id, "analyze_source_project", {
                "root_path": str(source_root or source_analysis.get("root_path", "")),
                "framework": source_analysis.get("framework", "unknown"),
                "summary": source_analysis.get("summary", {}),
            })
        self.db.audit(self.current_project_id, "import_api_source",
                      {"name": name, "type": document.specification, "endpoints": len(document.endpoints)})
        self.summary.setPlainText(
            f"文档：{document.title}\n规范：{document.specification}\n接口：{report.endpoint_count} 个\n"
            f"模块：{report.module_count} 个\n完整度：{report.score}%（{report.level}）\n"
            + "\n".join(f"• {x}" for x in report.suggestions)
        )
        self.refresh_projects()
        return report

    def compare_sources(self):
        if not self._require_project():
            return
        sources = self.db.list_sources(self.current_project_id)
        if len(sources) < 2:
            QMessageBox.information(self, "资料对比", "至少需要导入两份接口资料或源码。")
            return
        documents = []
        for source in sources[-2:]:
            endpoints = []
            for row in self.db.list_source_endpoints(source["id"]):
                value = json.loads(row["definition_json"])
                endpoints.append(ApiEndpoint(
                    method=value["method"], path=value["path"], summary=value.get("summary", ""),
                    module=value.get("module", "未分组"),
                    parameters=[ApiParameter(
                        p["name"], p["location"], p.get("required", False), p.get("schema") or {},
                        p.get("description", ""), p.get("example"),
                    ) for p in value.get("parameters", [])],
                    request_body=value.get("request_body") or {}, responses=value.get("responses") or {},
                    security=value.get("security") or [], source=value.get("source", source["kind"]),
                    source_location=value.get("source_location", source["name"]),
                ))
            documents.append(ApiDocument(source["name"], "", source["kind"], [], endpoints))
        difference = compare_documents(documents[0], documents[1])
        self.summary.setPlainText(json.dumps(difference, ensure_ascii=False, indent=2))
        self.db.audit(self.current_project_id, "compare_sources", {
            "left": sources[-2]["name"], "right": sources[-1]["name"],
            "differences": len(difference["differences"]),
        })

    def _require_project(self):
        if self.current_project_id:
            return True
        QMessageBox.information(self, "提示", "请先新建项目")
        return False

    def refresh_endpoints(self):
        if hasattr(self, "_endpoint_search_timer") and self._endpoint_search_timer.isActive():
            self._endpoint_search_timer.stop()
        rows = self.db.list_endpoints(self.current_project_id) if self.current_project_id else []
        query = self.search.text().lower() if hasattr(self, "search") else ""
        source_id = self.source_filter.currentData() if hasattr(self, "source_filter") else None
        module = self.module_filter.currentData() if hasattr(self, "module_filter") else None
        if source_id is not None:
            rows = [row for row in rows if row["source_id"] == source_id]
        if module is not None:
            rows = [row for row in rows if row["module"] == module]
        rows = [r for r in rows if query in " ".join(str(r[k]) for k in ("method", "path", "module", "summary")).lower()]
        table = self.endpoint_table
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        try:
            table.setRowCount(len(rows)); self._endpoint_rows = rows
            for i, row in enumerate(rows):
                for col, key in enumerate(("method", "path", "module", "summary")):
                    table.setItem(i, col, QTableWidgetItem(str(row[key])))
        finally:
            table.blockSignals(False)
            table.setUpdatesEnabled(True)

    def _schedule_endpoint_refresh(self):
        if hasattr(self, "_endpoint_search_timer"):
            self._endpoint_search_timer.start()

    def add_endpoint(self):
        if not self._require_project():
            return
        template = {
            "method": "GET", "path": "/api/example", "summary": "手工接口", "module": "手工",
            "parameters": [], "request_body": {}, "responses": {}, "security": [],
            "source": "manual", "source_location": "manual",
        }
        text, ok = QInputDialog.getMultiLineText(
            self, "手工添加接口", "编辑统一接口 JSON", json.dumps(template, ensure_ascii=False, indent=2)
        )
        if ok:
            try:
                definition = json.loads(text)
                if definition.get("method") not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                    raise ValueError("不支持的 HTTP Method")
                if not str(definition.get("path", "")).startswith("/"):
                    raise ValueError("Path 必须以 / 开头")
                self.db.add_manual_endpoint(self.current_project_id, definition)
                self.refresh_projects(); self.refresh_endpoints()
            except Exception as exc:
                QMessageBox.warning(self, "接口无效", str(exc))

    def edit_endpoint(self):
        row = self.endpoint_table.currentRow()
        if row < 0:
            return
        stored = self._endpoint_rows[row]
        original = json.loads(stored["definition_json"])
        text, ok = QInputDialog.getMultiLineText(
            self, "编辑接口", "统一接口 JSON", json.dumps(original, ensure_ascii=False, indent=2)
        )
        if ok:
            try:
                self.db.update_endpoint(stored["id"], json.loads(text))
                self.refresh_endpoints()
            except Exception as exc:
                QMessageBox.warning(self, "接口无效", str(exc))

    def delete_endpoint(self):
        row = self.endpoint_table.currentRow()
        if row >= 0 and QMessageBox.question(self, "删除接口", "确定删除选中接口？") == QMessageBox.Yes:
            self.db.delete_endpoint(self._endpoint_rows[row]["id"])
            self.refresh_projects(); self.refresh_endpoints()

    def show_endpoint(self):
        row = self.endpoint_table.currentRow()
        if row < 0 or row >= len(getattr(self, "_endpoint_rows", [])):
            return
        data = json.loads(self._endpoint_rows[row]["definition_json"])
        self.endpoint_detail.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
        self.method.setCurrentText(data["method"]); self.path.setText(data["path"])

    def select_environment(self):
        if not self.current_project_id or self.env_selector.currentIndex() < 0:
            return
        env_id = self.env_selector.currentData()
        env = next((x for x in self.db.list_environments(self.current_project_id) if x["id"] == env_id), None)
        if env:
            self._load_environment(env)

    def _load_environment(self, env):
        self.env_name.setText(env["name"])
        self.base_url.setText(env["base_url"])
        self.headers.setPlainText(env["headers_json"])
        values = json.loads(env.get("variables_json") or "{}")
        try:
            values.update(self.secret_store.decrypt_dict(env.get("secrets_encrypted") or ""))
        except Exception:
            QMessageBox.warning(self, "敏感配置", "无法解密该环境的敏感变量，请重新输入。")
        self.variables.setPlainText(json.dumps(values, ensure_ascii=False, indent=2))

    def save_environment(self):
        if not self.current_project_id:
            QMessageBox.information(self, "提示", "请先选择项目"); return
        try:
            headers = json.loads(self.headers.toPlainText() or "{}")
            values = json.loads(self.variables.toPlainText() or "{}")
            if not isinstance(headers, dict): raise ValueError("Headers 必须是 JSON 对象")
            if not isinstance(values, dict): raise ValueError("环境变量必须是 JSON 对象")
            public, secrets = split_sensitive(values)
            self.db.save_environment(
                self.current_project_id, self.env_name.text(), self.base_url.text(), headers,
                public, self.secret_store.encrypt_dict(secrets),
            )
            self.db.audit(self.current_project_id, "save_environment",
                          {"name": self.env_name.text(), "secret_count": len(secrets)})
            self.statusBar().showMessage("环境已保存", 3000)
            self._project_changed()
        except ValueError as exc:
            QMessageBox.warning(self, "配置错误", str(exc))

    def send_request(self):
        if not self.environment_confirmed.isChecked():
            QMessageBox.warning(self, "执行被阻止", "请先确认目标是已授权的测试环境。")
            return
        try:
            headers = json.loads(self.headers.toPlainText() or "{}")
            body = None if self.method.currentText() in {"GET", "HEAD"} else json.loads(self.body.toPlainText() or "null")
            result = execute_request(self.method.currentText(), self.base_url.text(), self.path.text(), headers, body)
            self._last_request_result = result
            self.response.setPlainText(json.dumps({
                "status_code": result.status_code, "elapsed_ms": result.elapsed_ms,
                "headers": result.headers, "body": result.body,
            }, ensure_ascii=False, indent=2))
        except Exception as exc:
            QMessageBox.critical(self, "请求失败", str(exc))

    def save_request_as_case(self):
        """Turn an authorised debugging request into an editable draft case."""
        if not self._require_project():
            return
        try:
            headers = json.loads(self.headers.toPlainText() or "{}")
            body = None if self.method.currentText() in {"GET", "HEAD"} else json.loads(self.body.toPlainText() or "null")
            if not isinstance(headers, dict):
                raise ValueError("Headers 必须是 JSON 对象")
            status = getattr(getattr(self, "_last_request_result", None), "status_code", 200)
            definition = {
                "name": f"{self.method.currentText()} {self.path.text()} 调试用例",
                "priority": "P1", "module": "手工调试", "source": "request_debug",
                "review_status": "draft", "risk": "high" if self.method.currentText() in {"POST", "PUT", "PATCH", "DELETE"} else "low",
                "request": {"method": self.method.currentText(), "path": self.path.text(), "headers": headers, "body": body},
                "assertions": [{"type": "status_code", "expected": status}],
            }
            self.db.save_test_cases(self.current_project_id, [definition])
            self.refresh_projects(); self.refresh_cases()
            self.statusBar().showMessage("已保存为草稿用例；请在“用例生成与执行”审核后执行。", 5000)
        except (ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "无法保存用例", str(exc))

    def preview_plan(self):
        if not self._require_project():
            return
        plan = generate_plan(self._case_scope_endpoints(), self.instruction.toPlainText())
        self.run_output.setPlainText(json.dumps(plan, ensure_ascii=False, indent=2))

    def generate_test_cases(self):
        if not self._require_project():
            return
        endpoints = self._case_scope_endpoints()
        if not endpoints:
            QMessageBox.information(self, "提示", "请先导入接口")
            return
        mode = self.ai_tabs.currentIndex()
        if mode in {0, 1, 2}:
            try:
                if mode == 0:
                    provider = CodexCliProvider(
                        self.codex_path.text().strip(),
                        self.codex_model.text().strip(),
                    )
                    ok, status = provider.status()
                    if not ok:
                        raise RuntimeError(f"Codex 尚未登录：{status}")
                elif mode == 1:
                    if not all((
                        self.model_url.text().strip(),
                        self.model_name.text().strip(),
                        self.model_key.text(),
                    )):
                        raise ValueError("请先在“AI 与 Codex”中完成兼容 API 配置。")
                    provider = OpenAICompatibleProvider(
                        self.model_url.text().strip(), self.model_key.text(),
                        self.model_name.text().strip(),
                    )
                else:
                    provider = OllamaProvider(
                        self.ollama_url.text().strip(),
                        self.ollama_model.text().strip(),
                    )
                prompt = json.dumps(
                    {"instruction": self.instruction.toPlainText(),
                     "endpoints": [json.loads(x["definition_json"]) for x in endpoints]},
                    ensure_ascii=False,
                )
                generated = provider.generate_structured(
                    "你是接口测试设计器。只基于给定接口生成结构化测试计划和草稿用例，不执行请求。",
                    prompt, TEST_GENERATION_SCHEMA,
                )
                validate_generation(generated, {f'{x["method"]} {x["path"]}' for x in endpoints})
                cases = generated["cases"]
            except Exception as exc:
                QMessageBox.critical(self, "模型生成失败", str(exc)); return
        self.db.save_test_cases(self.current_project_id, cases)
        self.refresh_projects(); self.refresh_cases(); self.go_to_page(3)
        self.run_output.setPlainText(f"已生成 {len(cases)} 条草稿用例，请检查后确认。")

    def refresh_cases(self):
        rows = self.db.list_test_cases(self.current_project_id) if self.current_project_id else []
        selected_module = self.case_module_filter.currentData() if hasattr(self, "case_module_filter") else None
        if selected_module is not None:
            rows = [
                row for row in rows
                if json.loads(row["definition_json"]).get("module", "未分组") == selected_module
            ]
        table = self.case_table
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        try:
            self._case_rows = rows; table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                definition = json.loads(row["definition_json"])
                values = (row["id"], row["name"], row["priority"], row["review_status"], definition.get("risk", "low"))
                for column, value in enumerate(values):
                    table.setItem(index, column, QTableWidgetItem(str(value)))
        finally:
            table.blockSignals(False)
            table.setUpdatesEnabled(True)

    def _case_scope_endpoints(self):
        rows = self.db.list_endpoints(self.current_project_id) if self.current_project_id else []
        selected_module = self.case_module_filter.currentData() if hasattr(self, "case_module_filter") else None
        if selected_module is not None:
            rows = [row for row in rows if row["module"] == selected_module]
        return rows

    def confirm_cases(self):
        selected = sorted({x.row() for x in self.case_table.selectedItems()})
        if not selected:
            QMessageBox.information(self, "提示", "请先选择用例")
            return
        high_risk = any(json.loads(self._case_rows[i]["definition_json"]).get("risk") == "high" for i in selected)
        if high_risk and QMessageBox.question(
            self, "高风险确认", "选中用例包含新增、修改或删除类请求。确认目标是授权测试环境并允许执行？"
        ) != QMessageBox.Yes:
            return
        for index in selected:
            self.db.update_case_status(self._case_rows[index]["id"], "confirmed")
        self.refresh_cases()

    def edit_case(self):
        row = self.case_table.currentRow()
        if row < 0:
            return
        stored = self._case_rows[row]
        original = json.loads(stored["definition_json"])
        text, ok = QInputDialog.getMultiLineText(
            self, "编辑测试用例", "结构化用例 JSON", json.dumps(original, ensure_ascii=False, indent=2)
        )
        if ok:
            try:
                changed = json.loads(text)
                if changed != original:
                    changed["review_status"] = "draft"
                self.db.update_test_case(stored["id"], changed)
                self.refresh_cases()
            except Exception as exc:
                QMessageBox.warning(self, "用例无效", str(exc))

    def copy_case(self):
        row = self.case_table.currentRow()
        if row < 0:
            return
        definition = json.loads(self._case_rows[row]["definition_json"])
        definition["name"] += "（副本）"
        definition["review_status"] = "draft"
        self.db.save_test_cases(self.current_project_id, [definition])
        self.refresh_cases()

    def delete_case(self):
        selected = sorted({item.row() for item in self.case_table.selectedItems()}, reverse=True)
        if selected and QMessageBox.question(self, "删除用例", f"确定删除 {len(selected)} 条用例？") == QMessageBox.Yes:
            for row in selected:
                self.db.delete_test_case(self._case_rows[row]["id"])
            self.refresh_cases()

    def run_confirmed_cases(self):
        if not self._require_project():
            return
        cases = [x for x in self.db.list_test_cases(self.current_project_id) if x["review_status"] == "confirmed"]
        selected_module = self.case_module_filter.currentData()
        if selected_module is not None:
            cases = [
                case for case in cases
                if json.loads(case["definition_json"]).get("module", "未分组") == selected_module
            ]
        self._start_case_run(cases, "已确认用例")

    def run_selected_cases(self):
        selected = sorted({item.row() for item in self.case_table.selectedItems()})
        if not selected:
            QMessageBox.information(self, "提示", "请先在用例列表中选择需要执行的用例")
            return
        cases = [self._case_rows[index] for index in selected if self._case_rows[index]["review_status"] == "confirmed"]
        if len(cases) != len(selected):
            QMessageBox.warning(self, "执行被阻止", "选中项中包含未确认的草稿用例，请先审核确认。")
            return
        self._start_case_run(cases, "选中用例")

    def rerun_failed_cases(self):
        failed_ids = getattr(self, "_last_failed_case_ids", [])
        if not failed_ids:
            QMessageBox.information(self, "提示", "当前会话还没有可重跑的失败用例。")
            return
        cases = [item for item in self.db.list_test_cases(self.current_project_id) if item["id"] in failed_ids and item["review_status"] == "confirmed"]
        self._start_case_run(cases, "上次失败用例")

    def _validate_case_run(self, cases: list[dict], label: str) -> tuple[dict, dict] | None:
        if not cases:
            QMessageBox.information(self, "提示", f"没有可执行的{label}。")
            return None
        if self._case_run_worker:
            QMessageBox.information(self, "提示", "已有测试任务正在执行。")
            return None
        if not self.environment_confirmed.isChecked():
            QMessageBox.warning(self, "执行被阻止", "请先确认目标是已授权的测试环境。")
            return None
        parsed = urlparse(self.base_url.text().strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            QMessageBox.warning(self, "执行前检查", "Base URL 必须是有效的 http:// 或 https:// 测试环境地址。")
            return None
        try:
            headers = json.loads(self.headers.toPlainText() or "{}")
            variables = json.loads(self.variables.toPlainText() or "{}")
            if not isinstance(headers, dict) or not isinstance(variables, dict):
                raise ValueError("Headers 和环境变量必须是 JSON 对象")
        except (ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "执行前检查", str(exc))
            return None
        message = (f"准备执行 {len(cases)} 条{label}\n\n环境：{self.env_name.text() or '未命名'}\n"
                   f"地址：{self.base_url.text()}\n并发：{self.max_workers.value()}\n\n"
                   "将向该测试环境发送请求，并记录报告。是否开始？")
        if QMessageBox.question(self, "执行前确认", message) != QMessageBox.Yes:
            return None
        return headers, variables

    def _start_case_run(self, cases: list[dict], label: str):
        checked = self._validate_case_run(cases, label)
        if not checked:
            return
        headers, variables = checked
        self._case_run_id = self.db.create_run(self.current_project_id)
        self._case_run_cases = cases
        self._stop_event = Event()
        self._case_run_completed = 0
        self.run_progress.setValue(0)
        self.run_output.setPlainText(f"正在后台执行 {len(cases)} 条{label}，界面仍可继续操作；可随时点击“停止任务”。")
        worker = _CaseRunWorker(cases, self.base_url.text().strip(), headers, variables, self._stop_event, self.max_workers.value())
        worker.signals.progressed.connect(self._case_run_progressed)
        worker.signals.completed.connect(self._case_run_completed_handler)
        worker.signals.failed.connect(self._case_run_failed)
        self._case_run_worker = worker
        self._ai_thread_pool.start(worker)

    def _case_run_progressed(self, result: dict):
        self._case_run_completed += 1
        total = len(self._case_run_cases)
        self.run_progress.setValue(round(self._case_run_completed * 100 / total))
        self.statusBar().showMessage(f"正在执行：{result.get('name', '用例')} → {result.get('status', 'unknown')}")

    def _case_run_completed_handler(self, results: list[dict], summary: dict):
        try:
            for result in results:
                self.db.save_result(self._case_run_id, result.get("case_id"), result)
            self.db.finish_run(self._case_run_id, summary)
            project_name = self.projects.currentText()
            html_path, json_path = generate_report(self.db.path.parent / "reports", project_name, results, summary,
                                                   report_type="接口契约报告", route="route_b", environment=self.env_name.text().strip())
            self.db.save_report(self._case_run_id, str(html_path), str(json_path), "接口契约报告", "route_b", self.env_name.text().strip())
            self._last_failed_case_ids = [item["case_id"] for item in results if item.get("status") in {"failed", "error"} and item.get("case_id")]
            self.run_output.setPlainText(json.dumps(summary, ensure_ascii=False, indent=2) + f"\n\nHTML：{html_path}\nJSON：{json_path}")
            self.refresh_reports()
        finally:
            self._case_run_worker = None
            self.statusBar().showMessage("测试执行完成。", 5000)

    def _case_run_failed(self, error: Exception):
        self.run_output.setPlainText(f"执行失败：{error}")
        self._case_run_worker = None
        QMessageBox.critical(self, "执行失败", str(error))

    def stop_run(self):
        if hasattr(self, "_stop_event"):
            self._stop_event.set()
            self.statusBar().showMessage("正在停止任务；当前正在发送的请求结束后会停止后续用例。")

    def refresh_reports(self):
        rows = []
        if self.current_project_id:
            rows.extend({**row, "report_type": row.get("report_type") or "接口契约报告", "report_name": self.projects.currentText()} for row in self.db.list_reports(self.current_project_id))
            rows.extend({**row, "report_type": row.get("report_type") or "业务流程报告", "report_name": row.get("workflow_name", "业务流程")} for row in self.db.list_workflow_reports(self.current_project_id))
            rows.extend({**row, "report_name": self.projects.currentText(), "run_id": row.get("id", "")} for row in self.db.list_evidence_reports(self.current_project_id))
            rows.sort(key=lambda item: item.get("started_at") or item.get("created_at") or "", reverse=True)
        table = self.report_table
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        try:
            self._report_rows = rows
            table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                values = (row.get("report_type", ""), row.get("report_name", ""), row.get("run_id", row.get("workflow_run_id", "")), row["status"], row["started_at"], row["finished_at"] or "",
                          row["html_path"], row["json_path"])
                for column, value in enumerate(values):
                    table.setItem(index, column, QTableWidgetItem(str(value)))
        finally:
            table.blockSignals(False)
            table.setUpdatesEnabled(True)

    def show_report(self):
        row = self.report_table.currentRow()
        if row < 0:
            return
        stored = self._report_rows[row]
        summary = stored.get("summary_json") or "{}"
        detail = (
            f"类型：{stored.get('report_type', '')}\n名称：{stored.get('report_name', '')}\n"
            f"开始：{stored.get('started_at', '')}\n结束：{stored.get('finished_at', '')}\n\n"
            + json.dumps(json.loads(summary), ensure_ascii=False, indent=2)
            + f"\n\nHTML：{stored['html_path']}\nJSON：{stored['json_path']}"
        )
        json_path = Path(stored.get("json_path") or "")
        if json_path.is_file():
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                detail += "\n\n完整执行明细：\n" + json.dumps(payload.get("results", payload), ensure_ascii=False, indent=2)
            except (OSError, ValueError) as exc:
                detail += f"\n\n读取 JSON 明细失败：{exc}"
        self.report_detail.setPlainText(detail)

    def open_selected_report(self, kind: str = "html"):
        row = self.report_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择一条历史报告")
            return
        key = "html_path" if kind == "html" else "json_path"
        path = Path(self._report_rows[row].get(key) or "")
        if not path.is_file():
            QMessageBox.warning(self, "报告不存在", f"报告文件不存在：{path}")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            QMessageBox.warning(self, "打开失败", f"无法使用系统默认程序打开：{path}")

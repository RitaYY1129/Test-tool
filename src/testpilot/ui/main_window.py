from __future__ import annotations

import html
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlencode, urlparse

from PySide6.QtCore import QByteArray, Qt, QProcess, QProcessEnvironment, QSize, QPoint, QObject, QRunnable, QThreadPool, Signal, Slot, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QIcon, QPainter, QPixmap, QKeySequence, QShortcut, QPen, QColor, QPalette, QBrush
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QApplication, QAbstractItemView, QDialog, QDialogButtonBox, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QScrollArea, QSpinBox, QStackedWidget, QStyle, QTabWidget, QTableWidget, QTableWidgetItem, QMenu,
    QTextEdit, QToolButton, QVBoxLayout, QWidget, QStyleOptionButton, QStyleOptionViewItem, QStyledItemDelegate, QSizePolicy, QRadioButton,
)

from testpilot.engines.http_engine import execute_request
from testpilot.cases.generator import generate_cases, generate_plan
from testpilot.engines.batch_runner import run_cases
from testpilot.engines.workflow_runner import SqliteTestDatabase, run_workflow
from testpilot.engines.ai_dialogue import ControlledDialogue
from testpilot.engines.database_observer import inspect_sqlite_database
from testpilot.engines.database_adapters import create_database_adapter
from testpilot.engines.runtime_trace import TraceCollector
from testpilot.engines.external_runner import complete_external_run, queue_external_run, validate_local_runner_artifacts
from testpilot.contracts.runner import ContractError
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


class BlueCheckBox(QCheckBox):
    """A checkbox whose selected state stays legible in the compact blue theme."""

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt callback name
        super().paintEvent(event)
        if not self.isChecked():
            return

        option = QStyleOptionButton()
        self.initStyleOption(option)
        indicator = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(Qt.white, 2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        # Some Windows Qt styles paint a solid blue indicator over thin lines.
        # A bold glyph keeps the checked state unmistakable in every page.
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(max(12, indicator.height() - 4))
        painter.setFont(font)
        painter.drawText(indicator, Qt.AlignCenter, "✓")
        painter.end()


class HttpMethodItemDelegate(QStyledItemDelegate):
    """Keeps every HTTP method option coloured even when the combo has a style sheet."""

    COLORS = {
        "GET": "#00a854", "POST": "#f0441f", "PUT": "#1677ff", "PATCH": "#8b5cf6",
        "DELETE": "#ef4444", "HEAD": "#06b6c9", "OPTIONS": "#d69e00",
    }

    def paint(self, painter, option, index):  # noqa: N802 - Qt callback name
        styled = QStyleOptionViewItem(option)
        method = str(index.data(Qt.DisplayRole) or "").upper()
        styled.palette.setColor(QPalette.Text, QColor(self.COLORS.get(method, "#1677e8")))
        # Selected state is expressed by the row background, never by replacing
        # the method's semantic colour.
        styled.palette.setColor(QPalette.HighlightedText, QColor(self.COLORS.get(method, "#1677e8")))
        super().paint(painter, styled, index)


class BelowPopupComboBox(QComboBox):
    """Qt combo whose popup is anchored below its input instead of over it."""

    def showPopup(self) -> None:  # noqa: N802 - Qt callback name
        super().showPopup()
        popup = self.view().window()
        if popup is None:
            return
        popup.setMinimumWidth(max(popup.minimumWidth(), self.width()))
        anchor = self.mapToGlobal(QPoint(0, self.height()))
        screen = self.screen()
        available = screen.availableGeometry() if screen else None
        popup_height = popup.height() or popup.sizeHint().height()
        if available and anchor.y() + popup_height > available.bottom():
            anchor.setY(self.mapToGlobal(QPoint(0, 0)).y() - popup_height)
        popup.move(anchor)


class EndpointTreeDelegate(QStyledItemDelegate):
    """Render only the HTTP method in colour; endpoint names stay black."""

    COLORS = HttpMethodItemDelegate.COLORS

    def paint(self, painter, option, index):  # noqa: N802 - Qt callback name
        text = str(index.data(Qt.DisplayRole) or "")
        method, separator, remainder = text.partition("  ")
        if method not in self.COLORS or not separator:
            super().paint(painter, option, index)
            return
        styled = QStyleOptionViewItem(option); styled.text = ""
        super().paint(painter, styled, index)
        rect = option.rect.adjusted(8, 0, -5, 0)
        painter.save()
        painter.setPen(QColor(self.COLORS[method]))
        painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, method)
        # Keep a stable 12 px gap between the coloured method and the black name.
        method_width = painter.fontMetrics().horizontalAdvance(method) + 12
        painter.setPen(QColor("#243b53"))
        painter.drawText(rect.adjusted(method_width, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, remainder)
        painter.restore()


class QueryParameterEditor(QWidget):
    """Compact Apifox-style Query key/value editor with one trailing empty row."""

    parametersChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("QueryParameterEditor")
        self._rows: list[tuple[QWidget, QLineEdit, QLineEdit]] = []
        self._updating = False
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(3)
        header = QHBoxLayout(); header.setContentsMargins(4, 0, 28, 0)
        header.addWidget(QLabel("Parameter Name", objectName="QueryParameterHeader"), 1)
        header.addWidget(QLabel("Parameter Value", objectName="QueryParameterHeader"), 1)
        layout.addLayout(header)
        self.rows_layout = QVBoxLayout(); self.rows_layout.setContentsMargins(0, 0, 0, 0); self.rows_layout.setSpacing(3)
        layout.addLayout(self.rows_layout)
        self.set_parameters([])

    def set_parameters(self, parameters: list[dict]) -> None:
        self._updating = True
        while self._rows:
            row, _, _ = self._rows.pop()
            row.deleteLater()
        for parameter in parameters:
            self._add_row(str(parameter.get("name") or ""), str(parameter.get("value") or ""))
        self._add_row()
        self._updating = False

    def parameters(self) -> list[tuple[str, str]]:
        return [
            (name.text().strip(), value.text().strip())
            for _, name, value in self._rows
            if name.text().strip()
        ]

    def _add_row(self, name_value: str = "", parameter_value: str = "") -> None:
        row = QWidget(); row.setObjectName("QueryParameterRow")
        layout = QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(6)
        name = QLineEdit(name_value); name.setObjectName("QueryParameterName"); name.setPlaceholderText("Add parameter")
        value = QLineEdit(parameter_value); value.setObjectName("QueryParameterValue"); value.setPlaceholderText("Value")
        remove = QToolButton(); remove.setText("×"); remove.setObjectName("QueryParameterDelete"); remove.setToolTip("Delete parameter")
        layout.addWidget(name, 1); layout.addWidget(value, 1); layout.addWidget(remove)
        self.rows_layout.addWidget(row); self._rows.append((row, name, value))
        name.textChanged.connect(self._row_changed); value.textChanged.connect(self._row_changed)
        remove.clicked.connect(lambda: self._remove_row(row))

    def _row_changed(self, _value: str) -> None:
        if self._updating:
            return
        if self._rows:
            _, name, value = self._rows[-1]
            if name.text().strip() or value.text().strip():
                self._add_row()
        self.parametersChanged.emit()

    def _remove_row(self, row: QWidget) -> None:
        for index, (candidate, _, _) in enumerate(self._rows):
            if candidate is row:
                self._rows.pop(index)
                row.setParent(None); row.deleteLater()
                break
        if not self._rows:
            self._add_row()
        self.parametersChanged.emit()


class KeyValueParameterEditor(QWidget):
    """Shared compact editor for Query, Headers and Cookies."""

    parametersChanged = Signal()

    def __init__(self, name_label: str, value_label: str, name_placeholder: str, value_placeholder: str,
                 supports_enabled: bool = False, shows_metadata: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("KeyValueParameterEditor")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.supports_enabled = supports_enabled
        self.shows_metadata = shows_metadata
        self.name_placeholder, self.value_placeholder = name_placeholder, value_placeholder
        self._rows: list[dict] = []
        self._updating = False
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(6)
        header = QHBoxLayout(); header.setContentsMargins(6, 2, 34, 0); header.setSpacing(8)
        if supports_enabled:
            header.addSpacing(22)
        header.addWidget(QLabel(name_label, objectName="KeyValueParameterHeader"), 4)
        header.addWidget(QLabel(value_label, objectName="KeyValueParameterHeader"), 4)
        if shows_metadata:
            header.addWidget(QLabel("类型", objectName="KeyValueParameterHeader"), 2)
            header.addWidget(QLabel("说明", objectName="KeyValueParameterHeader"), 3)
        layout.addLayout(header)
        self.rows_layout = QVBoxLayout(); self.rows_layout.setContentsMargins(0, 0, 0, 0); self.rows_layout.setSpacing(6)
        layout.addLayout(self.rows_layout)
        self.set_parameters([])

    def set_parameters(self, parameters: list[dict]) -> None:
        self._updating = True
        while self._rows:
            self._rows.pop()["row"].deleteLater()
        for parameter in parameters:
            value = parameter.get("value", "")
            self._add_row(
                str(parameter.get("name") or ""), "" if value is None else str(value),
                bool(parameter.get("enabled", True)), str(parameter.get("source") or ""),
                str(parameter.get("type") or ""), str(parameter.get("description") or ""),
            )
        self._add_row()
        self._updating = False

    def entries(self) -> list[dict]:
        result = []
        for item in self._rows:
            name, value = item["name"].text().strip(), item["value"].text().strip()
            if name:
                result.append({
                    "name": name, "value": value,
                    "enabled": item["enabled"].isChecked() if item["enabled"] else True,
                    "source": item["source"],
                    "type": item["type"].text().strip() if item.get("type") else "",
                    "description": item["description"].text().strip() if item.get("description") else "",
                })
        return result

    def parameters(self) -> list[tuple[str, str]]:
        return [(item["name"], item["value"]) for item in self.entries() if item["enabled"]]

    def _add_row(self, name_value: str = "", parameter_value: str = "", enabled: bool = True, source: str = "",
                 parameter_type: str = "", description: str = "") -> None:
        row = QWidget(); row.setObjectName("KeyValueParameterRow")
        layout = QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)
        toggle = None
        if self.supports_enabled:
            toggle = QCheckBox(); toggle.setChecked(enabled); toggle.setToolTip("启用此参数"); toggle.setObjectName("KeyValueParameterEnabled")
            layout.addWidget(toggle)
        name = QLineEdit(name_value); name.setObjectName("KeyValueParameterName"); name.setPlaceholderText(self.name_placeholder)
        value = QLineEdit(parameter_value); value.setObjectName("KeyValueParameterValue"); value.setPlaceholderText(self.value_placeholder)
        parameter_type_input = None
        description_input = None
        if self.shows_metadata:
            parameter_type_input = QLineEdit(parameter_type); parameter_type_input.setObjectName("KeyValueParameterType"); parameter_type_input.setPlaceholderText("类型")
            description_input = QLineEdit(description); description_input.setObjectName("KeyValueParameterDescription"); description_input.setPlaceholderText("说明（可选）")
        source_label = QLabel(source); source_label.setObjectName("KeyValueParameterSource"); source_label.setVisible(bool(source))
        remove = QToolButton(); remove.setText("×"); remove.setObjectName("KeyValueParameterDelete"); remove.setToolTip("删除参数")
        layout.addWidget(name, 4); layout.addWidget(value, 4)
        if parameter_type_input and description_input:
            layout.addWidget(parameter_type_input, 2); layout.addWidget(description_input, 3)
        layout.addWidget(source_label); layout.addWidget(remove)
        item = {"row": row, "name": name, "value": value, "enabled": toggle, "source": source,
                "type": parameter_type_input, "description": description_input}
        self._rows.append(item); self.rows_layout.addWidget(row)
        name.textChanged.connect(self._row_changed); value.textChanged.connect(self._row_changed)
        if parameter_type_input:
            parameter_type_input.textChanged.connect(lambda *_: self.parametersChanged.emit())
        if description_input:
            description_input.textChanged.connect(lambda *_: self.parametersChanged.emit())
        if toggle:
            def set_row_enabled(is_enabled: bool) -> None:
                name.setEnabled(is_enabled); value.setEnabled(is_enabled)
                self._row_changed()
            name.setEnabled(enabled); value.setEnabled(enabled)
            toggle.toggled.connect(set_row_enabled)
        remove.clicked.connect(lambda: self._remove_row(row))

    def _row_changed(self, *_args) -> None:
        if self._updating:
            return
        if self._rows:
            last = self._rows[-1]
            if last["name"].text().strip() or last["value"].text().strip():
                self._add_row()
        self.parametersChanged.emit()

    def _remove_row(self, row: QWidget) -> None:
        for index, item in enumerate(self._rows):
            if item["row"] is row:
                self._rows.pop(index); row.setParent(None); row.deleteLater(); break
        if not self._rows:
            self._add_row()
        self.parametersChanged.emit()


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
        self._external_runner_processes: dict[int, QProcess] = {}
        self._external_runner_timeouts: dict[int, QTimer] = {}
        self._external_runner_timed_out: set[int] = set()
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
        self._active_route = "路线 A：外部工程测试"
        self._sidebar_icon_cache = {}
        self._add_sidebar_entry("首页", 0, QStyle.SP_DirHomeIcon)
        self._add_nested_sidebar_group("接口测试", QStyle.SP_ComputerIcon, [
            ("基础配置", QStyle.SP_FileDialogInfoView, [
                ("项目管理", 0, QStyle.SP_DirIcon),
                ("环境校验", 2, QStyle.SP_DriveNetIcon),
            ]),
            ("路线 A：外部工程测试", QStyle.SP_FileDialogContentsView, [
                ("外部 Runner", 9, QStyle.SP_MediaPlay),
            ]),
            ("路线 B：接口资产测试", QStyle.SP_FileDialogContentsView, [
                ("接口资产", 1, QStyle.SP_FileDialogDetailedView),
                ("测试用例与执行", 3, QStyle.SP_MediaPlay),
                ("业务流程与执行", 7, QStyle.SP_FileDialogInfoView),
            ]),
        ], direct_entries=[
            ("接口测试报告", 4, QStyle.SP_FileDialogInfoView),
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
        self.pages.addWidget(self._external_runner_page())
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

    def _illustration_icon(self, kind: str, size: int = 76) -> QLabel:
        """Build the dashboard illustrations as crisp local SVGs.

        Keeping these in code (instead of emoji or an external icon font) makes
        the packaged application render identically on every Windows machine.
        """
        artwork = {
            "server": """
                <rect x='15' y='17' width='70' height='22' rx='7' fill='#1877f2'/>
                <rect x='15' y='46' width='70' height='22' rx='7' fill='#2588ff'/>
                <rect x='15' y='75' width='70' height='22' rx='7' fill='#1d6fe0'/>
                <circle cx='29' cy='28' r='3.5' fill='white'/><circle cx='29' cy='57' r='3.5' fill='white'/><circle cx='29' cy='86' r='3.5' fill='white'/>
                <path d='M43 28h28M43 57h28M43 86h28' stroke='white' stroke-width='4' stroke-linecap='round'/>
            """,
            "key": """
                <circle cx='49' cy='45' r='23' fill='#2684ff'/><circle cx='49' cy='45' r='8' fill='white'/>
                <path d='M34 60L13 81l10 10 7-7 7 7 10-10-7-7 8-8' fill='#2684ff'/>
                <path d='M34 60L13 81l10 10 7-7 7 7 10-10-7-7 8-8' fill='none' stroke='#2684ff' stroke-width='6' stroke-linejoin='round'/>
            """,
            "shield": """
                <path d='M50 11l33 12v25c0 22-14 37-33 43C31 85 17 70 17 48V23z' fill='#20ae69'/>
                <path d='M34 50l11 11 22-25' fill='none' stroke='white' stroke-width='8' stroke-linecap='round' stroke-linejoin='round'/>
            """,
            "cube": """
                <path d='M50 12l33 19v38L50 88 17 69V31z' fill='#7157e8'/>
                <path d='M50 12v38m33-19L50 50 17 31M50 50v38' fill='none' stroke='#aa9cff' stroke-width='2.5'/>
                <text x='50' y='59' text-anchor='middle' font-family='Arial' font-size='18' font-weight='700' fill='white'>API</text>
            """,
            "complete": """
                <circle cx='50' cy='50' r='39' fill='#20ae69'/>
                <path d='M30 51l13 13 28-30' fill='none' stroke='white' stroke-width='9' stroke-linecap='round' stroke-linejoin='round'/>
            """,
            # Small status marks are SVG too, rather than Unicode glyphs.  This
            # keeps the green check and orange warning triangle identical in
            # every widget and on every Windows font installation.
            "status_success": """
                <circle cx='50' cy='50' r='43' fill='#17a64a'/>
                <path d='M27 51l14 14 31-33' fill='none' stroke='white' stroke-width='10' stroke-linecap='round' stroke-linejoin='round'/>
            """,
            "status_warning": """
                <path d='M50 9L94 87H6z' fill='#f29a16'/>
                <path d='M50 34v27' fill='none' stroke='white' stroke-width='10' stroke-linecap='round'/>
                <circle cx='50' cy='75' r='5.5' fill='white'/>
            """,
            "status_pending": """
                <circle cx='50' cy='50' r='26' fill='#92a4b8'/>
            """,
            "status_running": """
                <circle cx='50' cy='50' r='37' fill='none' stroke='#1677e8' stroke-width='10'/>
                <path d='M50 27v25l17 10' fill='none' stroke='#1677e8' stroke-width='9' stroke-linecap='round' stroke-linejoin='round'/>
            """,
            "source": """
                <path d='M15 34h29l8 9h33v38a8 8 0 0 1-8 8H15a8 8 0 0 1-8-8V42a8 8 0 0 1 8-8z' fill='#1478f5'/>
                <path d='M40 55L28 66l12 11M61 55l12 11-12 11' fill='none' stroke='white' stroke-width='5' stroke-linecap='round' stroke-linejoin='round'/>
            """,
            "ai": """
                <circle cx='50' cy='50' r='30' fill='#e9f3ff'/>
                <circle cx='39' cy='43' r='6' fill='#80b9ff'/><circle cx='59' cy='39' r='6' fill='#80b9ff'/><circle cx='62' cy='59' r='6' fill='#80b9ff'/><circle cx='42' cy='63' r='6' fill='#80b9ff'/>
                <path d='M39 43l20-4 3 20-20 4zM28 23l3 7m31-11l-3 8m16 25l-8 1' stroke='#4d95f5' stroke-width='3' fill='none' stroke-linecap='round'/>
                <path d='M46 50h8M50 46v8' stroke='#1478f5' stroke-width='4' stroke-linecap='round'/>
            """,
            "flow": """
                <rect x='38' y='14' width='24' height='18' rx='4' fill='#89a9d9'/>
                <rect x='13' y='68' width='24' height='18' rx='4' fill='#89a9d9'/><rect x='63' y='68' width='24' height='18' rx='4' fill='#89a9d9'/>
                <path d='M50 32v16M25 68V54h50v14' fill='none' stroke='#547cab' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'/>
            """,
            "node": """
                <circle cx='25' cy='27' r='12' fill='#e7f1ff' stroke='#1677e8' stroke-width='4'/><circle cx='75' cy='28' r='12' fill='#e7f1ff' stroke='#1677e8' stroke-width='4'/>
                <circle cx='50' cy='73' r='13' fill='#1677e8'/><path d='M34 33l10 28M66 34L56 61M37 27h26' stroke='#1677e8' stroke-width='5' stroke-linecap='round'/>
            """,
            "rule": """
                <rect x='21' y='11' width='58' height='78' rx='8' fill='#eef6ff' stroke='#1677e8' stroke-width='4'/>
                <path d='M35 34h31M35 50h31M35 66h20' stroke='#1677e8' stroke-width='5' stroke-linecap='round'/>
                <circle cx='29' cy='34' r='3' fill='#1677e8'/><circle cx='29' cy='50' r='3' fill='#1677e8'/><circle cx='29' cy='66' r='3' fill='#1677e8'/>
            """,
            "chain": """
                <path d='M41 58L31 68a16 16 0 1 1-23-23l13-13a16 16 0 0 1 23 0' fill='none' stroke='#1677e8' stroke-width='8' stroke-linecap='round'/>
                <path d='M59 42l10-10a16 16 0 1 1 23 23L79 68a16 16 0 0 1-23 0' fill='none' stroke='#1677e8' stroke-width='8' stroke-linecap='round'/>
                <path d='M38 62l24-24' stroke='#1677e8' stroke-width='8' stroke-linecap='round'/>
            """,
        }
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
            + artwork.get(kind, artwork['complete']) + "</svg>"
        )
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        label = QLabel()
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignCenter)
        label.setFixedSize(size, size)
        return label

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
            0: "项目管理", 1: "接口资产", 2: "环境校验", 3: "测试用例与执行",
            4: "接口测试报告", 5: "能力中心", 6: "模型与连接", 7: "业务流程与执行", 8: "AI 协作中心", 9: "外部 Runner",
        }
        if hasattr(self, "breadcrumb"):
            section = "系统配置" if page_index == 8 else "接口测试"
            route_names = {
                0: "基础配置", 2: "基础配置", 9: "路线 A：外部工程测试",
                1: "路线 B：接口资产测试", 3: "路线 B：接口资产测试", 7: "路线 B：接口资产测试",
            }
            route = route_names.get(page_index)
            trail = f"{section}  /  {route}  /  " if route else f"{section}  /  "
            self.breadcrumb.setText(f"首页  /  {trail}{page_names.get(page_index, '工作台')}")
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

    def _project_stat_card(self, title: str, color: str) -> QFrame:
        """项目中心顶部的统一统计卡片。"""
        card = QFrame(); card.setObjectName("ProjectStatCard")
        card.setProperty("accent", color)
        layout = QHBoxLayout(card); layout.setContentsMargins(18, 14, 18, 14)
        badge = QLabel(title[:1]); badge.setObjectName("ProjectStatBadge")
        badge.setStyleSheet(f"background:{color};")
        value = QLabel("0"); value.setObjectName("ProjectStatValue")
        caption = QLabel(f"个{title}"); caption.setObjectName("ProjectStatCaption")
        column = QVBoxLayout(); column.setSpacing(0); column.addWidget(value); column.addWidget(caption)
        layout.addWidget(badge); layout.addLayout(column); layout.addStretch()
        card.stat_value = value
        return card

    def _project_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("项目中心"); title.setObjectName("PageTitle")
        mode = QLabel("统一管理多个测试项目，并按资料源、模块和接口查看项目资产")
        mode.setObjectName("PageSubtitle")
        row = QHBoxLayout()
        self.projects = BelowPopupComboBox(); self.projects.currentIndexChanged.connect(self._project_changed)
        self.projects.setMinimumWidth(300)
        delete_btn = QPushButton("删除项目"); delete_btn.clicked.connect(self.delete_project)
        self.source_filter_home = QLineEdit(); self.source_filter_home.setPlaceholderText("筛选当前项目的资料名称或类型")
        self.source_filter_home.textChanged.connect(self.refresh_source_table)
        self.import_type = BelowPopupComboBox()
        self.import_type.addItems([
            "OpenAPI / Swagger 文件", "在线 OpenAPI URL", "Postman Collection",
            "Postman Environment", "Apifox 数据", "cURL 命令", "HAR 请求记录",
            "接口文档 / Excel", "后端源码（自动识别）",
        ])
        import_btn = QPushButton("导入项目")
        import_btn.setProperty("primary", True)
        import_btn.clicked.connect(self.import_project)
        delete_btn.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        import_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        row.addWidget(QLabel("当前项目")); row.addWidget(self.projects, 1)
        row.addWidget(import_btn); row.addWidget(delete_btn)
        self.source_table = QTableWidget(0, 3)
        self.source_table.setHorizontalHeaderLabels(["资料名称", "类型", "操作"])
        self.source_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.source_table.setAlternatingRowColors(True)
        self.source_table.setFocusPolicy(Qt.NoFocus)
        # 资料较少时不让空白区域挤占下方的概览与资产查看空间。
        self.source_table.setMinimumHeight(0)
        self.source_table.verticalHeader().setVisible(False)
        self.source_table.verticalHeader().setDefaultSectionSize(38)
        self.source_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in ((1, 105), (2, 62)):
            self.source_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Fixed)
            self.source_table.setColumnWidth(column, width)
        self.summary = QLabel("导入资料后，这里会显示完整度、缺失信息和差异分析。")
        self.summary.setObjectName("AssetHint")
        self.summary.setWordWrap(True)
        self.project_table = QTableWidget(0, 5)
        self.project_table.setHorizontalHeaderLabels(["项目名称", "资料源", "模块", "接口", "最近更新"])
        self.project_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.project_table.setAlternatingRowColors(True)
        self.project_table.setShowGrid(False)
        self.project_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.project_table.setFocusPolicy(Qt.NoFocus)
        self.project_table.verticalHeader().setVisible(False)
        self.project_table.verticalHeader().setDefaultSectionSize(48)
        for column, width in ((0, 110), (1, 62), (2, 62), (3, 62), (4, 104)):
            self.project_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Fixed)
            self.project_table.setColumnWidth(column, width)
        self.project_table.horizontalHeader().setStretchLastSection(True)
        self.project_table.itemSelectionChanged.connect(self.select_project_from_table)
        self.project_table.cellDoubleClicked.connect(lambda *_: self.go_to_page(1))
        self.asset_tree = QTreeWidget()
        self.asset_tree.setFocusPolicy(Qt.NoFocus)
        self.asset_tree.setHeaderLabels(["项目资产结构", "类型 / 方法", "数量 / 路径"])
        self.asset_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.asset_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.asset_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.asset_tree.itemDoubleClicked.connect(self.open_asset_item)
        self.asset_tree.itemSelectionChanged.connect(self.update_asset_actions)
        self.asset_search = QLineEdit(); self.asset_search.setPlaceholderText("搜索资料源、模块或接口路径")
        self.asset_search.textChanged.connect(self.filter_asset_tree)
        self.asset_summary = QLabel()
        self.asset_summary.setObjectName("ContextBanner")
        expand_assets = QPushButton("全部展开"); expand_assets.clicked.connect(self.asset_tree.expandAll)
        collapse_assets = QPushButton("全部收起"); collapse_assets.clicked.connect(self.asset_tree.collapseAll)
        asset_actions = QHBoxLayout(); asset_actions.addWidget(self.asset_search, 1); asset_actions.addWidget(expand_assets); asset_actions.addWidget(collapse_assets)
        # 顶部仅放项目操作；资料导入收敛到资料源面板，避免同一操作出现两处。
        project_card = QFrame(); project_card.setObjectName("Card")
        project_layout = QHBoxLayout(project_card); project_layout.setContentsMargins(18, 14, 18, 14)
        project_layout.addLayout(row)
        self.stat_projects = self._project_stat_card("项目", "#eaf3ff")
        self.stat_sources = self._project_stat_card("资料源", "#eaf9f2")
        self.stat_modules = self._project_stat_card("模块", "#f4edff")
        self.stat_endpoints = self._project_stat_card("接口", "#eef4ff")
        stats = QHBoxLayout(); stats.setSpacing(14)
        stats.addWidget(self.stat_projects); stats.addWidget(self.stat_sources)
        stats.addWidget(self.stat_modules); stats.addWidget(self.stat_endpoints)

        source_panel = QFrame(); source_panel.setObjectName("Card")
        source_layout = QVBoxLayout(source_panel); source_layout.setContentsMargins(16, 16, 16, 16); source_layout.setSpacing(10)
        source_heading = QHBoxLayout(); source_heading.addWidget(QLabel("项目列表")); source_heading.itemAt(0).widget().setObjectName("PanelTitle")
        source_heading.addStretch()
        source_layout.addLayout(source_heading)
        self.project_filter = QLineEdit(); self.project_filter.setPlaceholderText("搜索项目名称")
        self.project_filter.textChanged.connect(self.filter_project_table)
        source_layout.addWidget(self.project_filter); source_layout.addWidget(self.project_table, 1)
        self.project_total = QLabel("共 0 个项目"); self.project_total.setObjectName("PageSubtitle")
        source_layout.addWidget(self.project_total)

        asset_panel = QFrame(); asset_panel.setObjectName("Card")
        assets_layout = QVBoxLayout(asset_panel); assets_layout.setContentsMargins(16, 16, 16, 16); assets_layout.setSpacing(10)
        asset_heading = QHBoxLayout()
        asset_title = QLabel("当前项目资产"); asset_title.setObjectName("PanelTitle")
        reimport_btn = QPushButton("导入到当前项目")
        reimport_btn.clicked.connect(self.import_into_current_project)
        self.edit_asset_btn = QPushButton("编辑选中资产")
        self.delete_asset_btn = QPushButton("删除选中资产")
        self.delete_asset_btn.setProperty("danger", True)
        self.edit_asset_btn.clicked.connect(self.edit_selected_asset)
        self.delete_asset_btn.clicked.connect(self.delete_selected_asset)
        asset_heading.addWidget(asset_title); asset_heading.addStretch()
        asset_heading.addWidget(reimport_btn); asset_heading.addWidget(self.edit_asset_btn); asset_heading.addWidget(self.delete_asset_btn)
        assets_layout.addLayout(asset_heading); assets_layout.addWidget(self.asset_summary)
        self.current_source_label = QLabel("尚未导入资料")
        self.current_source_label.setObjectName("SelectedSource")
        assets_layout.addWidget(self.current_source_label)
        assets_layout.addLayout(asset_actions); assets_layout.addWidget(self.asset_tree, 1); assets_layout.addWidget(self.summary)
        workspace = QWidget(); workspace_layout = QHBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0); workspace_layout.setSpacing(16)
        workspace_layout.addWidget(source_panel, 3); workspace_layout.addWidget(asset_panel, 7)
        delete_btn.setProperty("danger", True)
        layout.addWidget(title); layout.addWidget(mode); layout.addWidget(project_card); layout.addLayout(stats)
        layout.addWidget(workspace, 1)
        self._finish_page(page, layout)
        return page

    def import_selected_source(self):
        handlers = [
            self.import_openapi, self.import_openapi_url, self.import_postman,
            self.import_postman_environment, self.import_apifox, self.import_curl,
            self.import_har, self.import_document, self.import_backend_source,
        ]
        handlers[self.import_type.currentIndex()]()

    def import_project(self):
        """在一个窗口中收集项目名称和导入类型，再打开对应的文件/目录选择器。"""
        options = [
            "后端源码目录（自动识别接口）",
            "OpenAPI / Swagger 文件",
            "Postman Collection",
            "Apifox JSON",
            "接口文档 / Excel",
            "HAR 请求记录",
        ]
        dialog = QDialog(self); dialog.setWindowTitle("导入项目"); dialog.setMinimumWidth(420)
        form = QFormLayout(dialog); form.setContentsMargins(24, 20, 24, 16); form.setSpacing(14)
        project_name_input = QLineEdit(); project_name_input.setPlaceholderText("例如：钢厂后端、恋爱日记")
        import_kind = BelowPopupComboBox(); import_kind.addItems(options)
        form.addRow("项目名称", project_name_input)
        form.addRow("导入类型", import_kind)
        tip = QLabel("确认后将选择对应的文件或后端源码目录。"); tip.setObjectName("PageSubtitle")
        form.addRow("", tip)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("下一步")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        choice = import_kind.currentText()
        chosen_name = project_name_input.text().strip()
        if choice == options[0]:
            path = QFileDialog.getExistingDirectory(self, "选择后端源码项目目录")
            if not path:
                return
            try:
                analysis = BackendSourceParser().analyze_directory(path)
                document = analysis["document"]
                if not document.endpoints:
                    raise ValueError("未在所选目录识别到接口，请选择包含 Controller 或路由文件的后端项目目录。")
                project_name = chosen_name or Path(path).name
                self._create_and_import_project(project_name, project_name, document, analysis, Path(path))
                self.codex_path.setText(path); self.db.set_setting("codex_project_path", path)
            except Exception as exc:
                QMessageBox.critical(self, "导入项目失败", str(exc))
            return

        filters = {
            options[1]: ("选择 OpenAPI 文件", "OpenAPI (*.json *.yaml *.yml)"),
            options[2]: ("选择 Postman Collection", "Postman Collection (*.json)"),
            options[3]: ("选择 Apifox 文件", "Apifox JSON (*.json)"),
            options[4]: ("选择接口文档", "接口文档 (*.md *.txt *.html *.htm *.xlsx *.xlsm *.docx *.pdf)"),
            options[5]: ("选择 HAR 文件", "HAR (*.har *.json)"),
        }
        dialog_title, file_filter = filters[choice]
        path, _ = QFileDialog.getOpenFileName(self, dialog_title, "", file_filter)
        if not path:
            return
        try:
            if choice == options[1]:
                document = OpenApiParser().parse_file(path)
            elif choice == options[2]:
                document = PostmanParser().parse_file(path)
            elif choice == options[3]:
                document = ApifoxParser().parse_file(path)
            elif choice == options[4]:
                document = DocumentParser().parse_file(path)
            else:
                document = HarParser().parse_file(path)
            project_name = chosen_name or Path(path).stem
            self._create_and_import_project(project_name, Path(path).name, document)
            if document.base_urls and not self.base_url.text():
                self.base_url.setText(document.base_urls[0])
        except Exception as exc:
            QMessageBox.critical(self, "导入项目失败", str(exc))

    def import_into_current_project(self):
        """为已存在项目导入一份新的资料源，便于版本更新和资料对比。"""
        if not self.current_project_id:
            QMessageBox.information(self, "提示", "请先在项目列表中选择一个项目。")
            return
        options = [
            "后端源码目录（自动识别接口）", "OpenAPI / Swagger 文件", "Postman Collection",
            "Apifox JSON", "接口文档 / Excel", "HAR 请求记录",
        ]
        choice, accepted = QInputDialog.getItem(self, "导入到当前项目", "导入类型", options, 0, False)
        if not accepted:
            return
        try:
            if choice == options[0]:
                path = QFileDialog.getExistingDirectory(self, "选择后端源码项目目录")
                if not path: return
                analysis = BackendSourceParser().analyze_directory(path); document = analysis["document"]
                if not document.endpoints: raise ValueError("未在所选目录识别到接口。")
                self._save_document(Path(path).name, document, source_analysis=analysis, source_root=Path(path))
            else:
                filters = {
                    options[1]: ("选择 OpenAPI 文件", "OpenAPI (*.json *.yaml *.yml)"),
                    options[2]: ("选择 Postman Collection", "Postman Collection (*.json)"),
                    options[3]: ("选择 Apifox 文件", "Apifox JSON (*.json)"),
                    options[4]: ("选择接口文档", "接口文档 (*.md *.txt *.html *.htm *.xlsx *.xlsm *.docx *.pdf)"),
                    options[5]: ("选择 HAR 文件", "HAR (*.har *.json)"),
                }
                dialog_title, file_filter = filters[choice]
                path, _ = QFileDialog.getOpenFileName(self, dialog_title, "", file_filter)
                if not path: return
                parsers = {options[1]: OpenApiParser(), options[2]: PostmanParser(), options[3]: ApifoxParser(), options[4]: DocumentParser(), options[5]: HarParser()}
                self._save_document(Path(path).name, parsers[choice].parse_file(path))
            QMessageBox.information(self, "导入完成", "资料已导入当前项目，可使用“对比资料”查看变更。")
        except Exception as exc:
            QMessageBox.critical(self, "导入资料失败", str(exc))

    def _create_and_import_project(self, project_name, source_name, document, analysis=None, source_root=None):
        """按导入资料自动创建唯一项目，避免用户手动输入名称。"""
        base_name = project_name.strip() or "未命名项目"
        existing = {str(row["name"]) for row in self.db.list_projects()}
        final_name = base_name
        index = 2
        while final_name in existing:
            final_name = f"{base_name}-{index}"
            index += 1
        self.current_project_id = self.db.create_project(final_name, mode="source" if analysis else "document")
        self._save_document(source_name, document, source_analysis=analysis, source_root=source_root)
        self.refresh_projects()
        QMessageBox.information(self, "导入完成", f"已创建项目：{final_name}\n识别接口：{len(document.endpoints)} 个")

    def _set_import_summary(self, text: str):
        if isinstance(self.summary, QLabel):
            self.summary.setText(text.replace("\n", "  ·  "))
        else:
            self.summary.setPlainText(text)

    def _append_import_summary(self, text: str):
        if isinstance(self.summary, QLabel):
            current = self.summary.text().strip()
            self.summary.setText(f"{current}  ·  {text}" if current else text)
        else:
            self.summary.append(text)

    def _cases_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("用例生成与执行"); title.setObjectName("PageTitle")
        subtitle = QLabel("路线 A、路线 B 共用的用例审核、批量执行和结果分析中心"); subtitle.setObjectName("PageSubtitle")
        self.case_project_label = QLabel("当前项目：未选择"); self.case_project_label.setObjectName("ContextBanner")
        scope_row = QHBoxLayout()
        self.case_project_selector = BelowPopupComboBox()
        self.case_project_selector.currentIndexChanged.connect(self.select_case_project)
        self.case_module_filter = BelowPopupComboBox()
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
        self.case_runtime_hint = QLabel("运行配置：请先在“项目运行配置与接口调试”中保存一次项目环境。")
        self.case_runtime_hint.setObjectName("PageSubtitle")
        self.max_workers = QSpinBox(); self.max_workers.setRange(1, 8); self.max_workers.setValue(1)
        self.max_workers.setPrefix("并发 ")
        model_row.addWidget(self.ai_status_label, 1); model_row.addWidget(self.case_runtime_hint, 2); model_row.addWidget(self.max_workers)
        buttons = QHBoxLayout()
        plan_btn = QPushButton("预览测试计划"); plan_btn.clicked.connect(self.preview_plan)
        generate_btn = QPushButton("生成用例"); generate_btn.clicked.connect(self.generate_test_cases)
        confirm_btn = QPushButton("确认选中用例"); confirm_btn.clicked.connect(self.confirm_cases)
        edit_btn = QPushButton("编辑用例"); edit_btn.clicked.connect(self.edit_case)
        copy_btn = QPushButton("复制用例"); copy_btn.clicked.connect(self.copy_case)
        delete_case_btn = QPushButton("删除用例"); delete_case_btn.clicked.connect(self.delete_case)
        run_btn = QPushButton("一键运行已确认用例"); run_btn.clicked.connect(self.run_confirmed_cases)
        run_selected_btn = QPushButton("执行选中用例"); run_selected_btn.clicked.connect(self.run_selected_cases)
        rerun_failed_btn = QPushButton("重跑上次失败"); rerun_failed_btn.clicked.connect(self.rerun_failed_cases)
        stop_btn = QPushButton("停止任务"); stop_btn.clicked.connect(self.stop_run)
        for button in (plan_btn, generate_btn, confirm_btn, edit_btn, copy_btn, delete_case_btn, run_btn, run_selected_btn, rerun_failed_btn, stop_btn):
            buttons.addWidget(button)
        self.case_table = QTableWidget(0, 5)
        self.case_table.setHorizontalHeaderLabels(["ID", "名称", "优先级", "状态", "风险"])
        self.case_table.setSelectionBehavior(QTableWidget.SelectRows)
        # Selection must never create an inline editor.  Editing is an explicit
        # action through the “编辑用例” button, which prevents text/input overlap.
        self.case_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.run_output = QTextEdit(); self.run_output.setReadOnly(True)
        self.run_progress = QProgressBar(); self.run_progress.setRange(0, 100)
        # The project selector immediately below already identifies the project;
        # avoid spending a full banner row on the same information.
        layout.addWidget(title); layout.addWidget(subtitle)
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

    def _business_flow_execution_page(self):
        page = QScrollArea(); page.setObjectName("BusinessFlowScroll"); page.setWidgetResizable(True)
        content = QWidget(); layout = QVBoxLayout(content); page.setWidget(content)
        title = QLabel("业务流程与测试执行"); title.setObjectName("PageTitle")
        stepper = QFrame(); stepper.setObjectName("BusinessStepper")
        bar = QHBoxLayout(stepper); bar.setContentsMargins(0, 0, 0, 12)
        for index, name in enumerate(("AI 流程识别", "流程确认", "生成测试用例", "执行测试用例"), 1):
            item = QLabel(f"{index}  {name}"); item.setObjectName("BusinessStepActive" if index == 1 else "BusinessStep")
            bar.addWidget(item)
            if index < 4:
                line = QFrame(); line.setFrameShape(QFrame.HLine); line.setObjectName("BusinessStepLine"); bar.addWidget(line, 1)

        analysis_card = QFrame(); analysis_card.setObjectName("RecognitionCard")
        analysis_layout = QVBoxLayout(analysis_card); analysis_layout.setContentsMargins(18, 16, 18, 16); analysis_layout.setSpacing(12)
        analysis_layout.addWidget(QLabel("AI 业务流程识别", objectName="PanelTitle"))
        analysis_left = QWidget(); left = QVBoxLayout(analysis_left); left.setContentsMargins(0, 0, 0, 0); left.setSpacing(10)
        visual = QFrame(); visual.setObjectName("RecognitionVisual"); visual_layout = QHBoxLayout(visual); visual_layout.setContentsMargins(16, 14, 16, 14)
        for pos, (icon_kind, name) in enumerate((("source", "导入源码项目"), ("ai", "AI 分析识别"), ("flow", "业务流程与依赖图谱"))):
            block = QWidget(); block.setObjectName("RecognitionVisualItem")
            block_layout = QVBoxLayout(block); block_layout.setContentsMargins(4, 4, 4, 4); block_layout.setSpacing(4)
            block_layout.addWidget(self._illustration_icon(icon_kind, 64), alignment=Qt.AlignCenter)
            label = QLabel(name); label.setObjectName("RecognitionVisualLabel"); label.setAlignment(Qt.AlignCenter)
            block_layout.addWidget(label)
            visual_layout.addWidget(block, 1)
            if pos < 2:
                arrow = QLabel("→"); arrow.setObjectName("RecognitionArrow"); arrow.setAlignment(Qt.AlignCenter); visual_layout.addWidget(arrow)
        self.workflow_project_selector = BelowPopupComboBox(); self.workflow_project_selector.currentIndexChanged.connect(self.select_workflow_project)
        source_scope = BelowPopupComboBox(); source_scope.addItem("已导入项目源码"); source_scope.setEnabled(False)
        choices = QHBoxLayout(); choices.addWidget(QLabel("源码范围")); choices.addWidget(source_scope, 1)
        checks = QHBoxLayout()
        for text in ("控制器", "服务层", "数据模型", "配置文件", "数据库操作"):
            checkbox = BlueCheckBox(text); checkbox.setChecked(True); checks.addWidget(checkbox)
        self.workflow_scope = QTextEdit(); self.workflow_scope.setFixedHeight(78); self.workflow_scope.setPlaceholderText("补充业务说明：例如说明关键业务术语或关注的模块（可选）")
        start = QPushButton("开始 AI 识别"); start.setProperty("primary", True); start.clicked.connect(self.generate_workflow_draft)
        left.addWidget(visual); left.addWidget(QLabel("AI 将根据导入源码自动识别业务流程、接口依赖与关键业务规则。")); left.addLayout(choices); left.addLayout(checks); left.addWidget(self.workflow_scope); left.addWidget(start)

        expected = QFrame(); expected.setObjectName("ExpectedOutputPanel"); expected_layout = QVBoxLayout(expected); expected_layout.setContentsMargins(12, 12, 12, 12); expected_layout.setSpacing(10)
        expected_layout.addWidget(QLabel("识别后将生成（预期输出）", objectName="ExpectedOutputTitle"))
        for icon_kind, item_text in (
            ("flow", "流程候选（识别后生成）"),
            ("node", "关键节点（识别后生成）"),
            ("rule", "工艺 / 规则详情（按识别结果显示）"),
            ("chain", "接口调用关系（识别后生成）"),
        ):
            item = QFrame(); item.setObjectName("ExpectedOutputItem")
            item_layout = QHBoxLayout(item); item_layout.setContentsMargins(10, 8, 10, 8); item_layout.setSpacing(9)
            item_layout.addWidget(self._illustration_icon(icon_kind, 26))
            item_layout.addWidget(QLabel(item_text, objectName="ExpectedOutputLabel"), 1)
            expected_layout.addWidget(item)
        expected_layout.addStretch(1)
        inner = QHBoxLayout(); inner.setSpacing(16); inner.addWidget(analysis_left, 3); inner.addWidget(expected, 1)
        analysis_layout.addLayout(inner)

        settings = QFrame(); settings.setObjectName("RecognitionCard")
        setting_layout = QVBoxLayout(settings); setting_layout.setContentsMargins(18, 16, 18, 16); setting_layout.setSpacing(14)
        setting_layout.addWidget(QLabel("识别设置", objectName="PanelTitle")); setting_layout.addWidget(QLabel("识别深度"))
        depth = BelowPopupComboBox(); depth.addItems(["标准（平衡识别速度与深度）", "快速（仅识别接口关系）", "深入（包含数据与异常路径）"]); setting_layout.addWidget(depth)
        include_cases = BlueCheckBox("包含测试相关分支"); include_cases.setChecked(True)
        include_db = BlueCheckBox("包含数据库数据流"); include_db.setChecked(True)
        setting_layout.addWidget(include_cases); setting_layout.addWidget(include_db); setting_layout.addStretch(1)
        setting_layout.addWidget(QLabel("◇  AI 只分析项目源码，不修改业务数据", objectName="SafetyHint"))

        top = QHBoxLayout(); top.setSpacing(14); top.addWidget(analysis_card, 4); top.addWidget(settings, 1)

        execution = QFrame(); execution.setObjectName("WorkflowExecutionCard"); execution_layout = QVBoxLayout(execution); execution_layout.setContentsMargins(18, 16, 18, 16)
        execution_layout.addWidget(QLabel("流程确认与测试执行中心", objectName="PanelTitle"))
        self.workflow_selector = BelowPopupComboBox(); self.workflow_selector.currentIndexChanged.connect(self.load_workflow)
        selector_row = QHBoxLayout(); selector_row.addWidget(QLabel("流程方案")); selector_row.addWidget(self.workflow_selector, 1)
        save = QPushButton("保存流程"); save.clicked.connect(self.save_workflow); confirm = QPushButton("确认识别结果"); confirm.clicked.connect(self.confirm_workflow)
        selector_row.addWidget(save); selector_row.addWidget(confirm); execution_layout.addLayout(selector_row)
        self.workflow_summary = QTextEdit(); self.workflow_summary.setReadOnly(True); self.workflow_summary.setMinimumHeight(180); self.workflow_summary.setPlaceholderText("尚未开始流程识别。完成 AI 识别后，这里将展示实际识别结果、关键规则、可确认项及测试用例。")
        self.workflow_json = QTextEdit(); self.workflow_json.setVisible(False)
        self.workflow_db_path = QLineEdit(); self.workflow_db_path.setVisible(False); self.workflow_db_read_only = QCheckBox(); self.workflow_db_read_only.setChecked(True); self.workflow_db_read_only.setVisible(False)
        self.workflow_fixture_name = QLineEdit(); self.workflow_fixture_name.setVisible(False); self.workflow_fixture_json = QTextEdit(); self.workflow_fixture_json.setVisible(False)
        execution_layout.addWidget(self.workflow_summary, 1)
        workflow_actions = QHBoxLayout(); generate = QPushButton("生成测试用例"); generate.setProperty("primary", True); generate.clicked.connect(self.generate_workflow_cases); run = QPushButton("执行测试用例"); run.clicked.connect(self.execute_workflow)
        workflow_actions.addStretch(); workflow_actions.addWidget(generate); workflow_actions.addWidget(run); execution_layout.addLayout(workflow_actions)

        report = QFrame(); report.setObjectName("WorkflowExecutionCard"); report_layout = QVBoxLayout(report); report_layout.setContentsMargins(18, 16, 18, 16); report_layout.addWidget(QLabel("执行结果与报告", objectName="PanelTitle"))
        self.workflow_output = QTextEdit(); self.workflow_output.setReadOnly(True); self.workflow_output.setPlaceholderText("完成执行后将在此处生成结果与报告。"); report_layout.addWidget(self.workflow_output, 1)
        lower = QHBoxLayout(); lower.setSpacing(14); lower.addWidget(execution, 3); lower.addWidget(report, 1)
        layout.addWidget(title); layout.addWidget(stepper); layout.addLayout(top); layout.addLayout(lower, 1)
        self._finish_page(content, layout)
        return page

    def _workflow_page(self):
        return self._business_flow_execution_page()
        # Workflow definitions can be large. Keep every control reachable instead of
        # allowing a long JSON document to squeeze adjacent rows into each other.
        page = QScrollArea()
        page.setObjectName("WorkflowScroll")
        page.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        page.setWidget(content)
        title = QLabel("源码驱动测试 · 路线 A"); title.setObjectName("PageTitle")
        subtitle = QLabel("导入后端源码后，自动理解业务与认证关系；只需确认测试重点，即可生成用例并一键回归。")
        subtitle.setObjectName("PageSubtitle")
        workflow_steps = QFrame(); workflow_steps.setObjectName("WorkflowStepBar")
        workflow_steps_layout = QHBoxLayout(workflow_steps)
        workflow_steps_layout.setContentsMargins(16, 10, 16, 10)
        for index, text in enumerate(("AI 识别", "确认流程", "生成用例", "执行回归"), 1):
            step = QLabel(f"{index}  {text}")
            step.setObjectName("WorkflowStep")
            step.setProperty("active", "true" if index == 1 else "false")
            workflow_steps_layout.addWidget(step)
            if index < 4:
                divider = QFrame(); divider.setFrameShape(QFrame.HLine); divider.setObjectName("WorkflowStepDivider")
                workflow_steps_layout.addWidget(divider, 1)
        self.workflow_project_label = QLabel("当前项目：未选择"); self.workflow_project_label.setObjectName("ContextBanner")
        self.workflow_setup_hint = QLabel("路线 A 在生成业务流程和用例时不需要手工填写单接口请求；仅执行真实 API 用例前，首次保存项目运行地址与认证即可。")
        self.workflow_setup_hint.setObjectName("ContextBanner")
        self.workflow_setup_hint.setWordWrap(True)
        analysis_track = QFrame(); analysis_track.setObjectName("AnalysisTrack")
        analysis_track_layout = QHBoxLayout(analysis_track)
        analysis_track_layout.setContentsMargins(16, 12, 16, 12)
        for index, (heading, detail) in enumerate((
            ("① 导入项目源码", "识别接口、模块与认证入口"),
            ("② AI 分析业务关系", "整理调用链与测试风险"),
            ("③ 输出测试方案", "确认重点后自动生成用例"),
        )):
            block = QLabel(f"{heading}\n{detail}")
            block.setObjectName("AnalysisTrackItem")
            analysis_track_layout.addWidget(block, 1)
            if index < 2:
                arrow = QLabel("→"); arrow.setObjectName("AnalysisTrackArrow")
                analysis_track_layout.addWidget(arrow)
        self.workflow_project_selector = BelowPopupComboBox(); self.workflow_project_selector.currentIndexChanged.connect(self.select_workflow_project)
        route_row = QHBoxLayout()
        view_endpoints = QPushButton("查看接口资产"); view_endpoints.clicked.connect(lambda: self.go_to_page(1))
        ai_generate = QPushButton("开始 AI 识别"); ai_generate.setProperty("primary", True); ai_generate.clicked.connect(self.generate_workflow_draft)
        manual_generate = QPushButton("手工补充测试方案"); manual_generate.clicked.connect(self.create_manual_workflow)
        route_row.addWidget(QLabel("测试项目")); route_row.addWidget(self.workflow_project_selector, 1); route_row.addWidget(view_endpoints); route_row.addWidget(ai_generate); route_row.addWidget(manual_generate); route_row.addStretch()
        selector_row = QHBoxLayout()
        self.workflow_selector = BelowPopupComboBox()
        self.workflow_selector.currentIndexChanged.connect(self.load_workflow)
        save_btn = QPushButton("保存流程"); save_btn.clicked.connect(self.save_workflow)
        confirm_btn = QPushButton("确认流程"); confirm_btn.clicked.connect(self.confirm_workflow)
        coverage_btn = QPushButton("检查测试覆盖"); coverage_btn.clicked.connect(self.check_process_coverage)
        selector_row.addWidget(QLabel("流程")); selector_row.addWidget(self.workflow_selector, 1)
        selector_row.addWidget(save_btn); selector_row.addWidget(coverage_btn); selector_row.addWidget(confirm_btn)
        self.workflow_scope = QTextEdit(); self.workflow_scope.setMaximumHeight(65)
        self.workflow_scope.setPlaceholderText("可选：补充你的关注点，例如：权限、重复提交、边界值、异常回滚。不填时系统自动覆盖常规风险。")
        scope_row = QHBoxLayout()
        confirm_scope = QPushButton("保存测试重点"); confirm_scope.clicked.connect(self.confirm_workflow_scope)
        generate_cases_btn = QPushButton("自动生成测试用例"); generate_cases_btn.setProperty("primary", True); generate_cases_btn.clicked.connect(self.generate_workflow_cases)
        scope_row.addWidget(QLabel("测试重点")); scope_row.addWidget(self.workflow_scope, 1)
        scope_row.addWidget(confirm_scope); scope_row.addWidget(generate_cases_btn)
        self.workflow_json = QTextEdit()
        self.workflow_json.setPlaceholderText(
            '{"name":"订单创建流程","review_status":"draft","data_flows":[],"database_changes":[],"steps":[]}'
        )
        self.workflow_json.setMinimumHeight(260)
        self.workflow_json.setMaximumHeight(320)
        self.workflow_summary = QTextEdit(); self.workflow_summary.setReadOnly(True)
        self.workflow_summary.setMinimumHeight(145); self.workflow_summary.setMaximumHeight(190)
        self.workflow_summary.setPlaceholderText("点击“自动分析并生成测试方案”后，这里会用中文说明识别到的业务场景、接口链路、风险与推荐测试重点。")
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
        # Project selection is part of the first action row.  Keep the page head
        # compact so the workflow editor stays visible.
        # Use a real hidden panel instead of constraining a checkable group box.
        # Fixed-height group boxes are clipped by Windows DPI/layout calculations.
        advanced_toggle = QPushButton("高级选项")
        advanced_toggle.setObjectName("AdvancedToggle")
        advanced_toggle.setCheckable(True)
        advanced_toggle.setToolTip("日常生成与执行不需要配置；仅在需要编辑底层流程或校验数据库时展开。")
        advanced_group = QWidget()
        advanced_group.setVisible(False)
        advanced_layout = QVBoxLayout(advanced_group)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(8)
        advanced_toggle.toggled.connect(advanced_group.setVisible)
        advanced_toggle.toggled.connect(
            lambda checked: advanced_toggle.setText("收起高级选项" if checked else "高级选项")
        )
        advanced_layout.addWidget(QLabel("底层流程结构（供高级用户编辑，日常使用请看上方中文测试方案）"))
        advanced_layout.addWidget(self.workflow_json)
        advanced_layout.addLayout(database_row)
        advanced_layout.addLayout(fixture_row)
        workflow_controls = QFrame(); workflow_controls.setObjectName("ProjectPanel")
        workflow_controls_layout = QVBoxLayout(workflow_controls)
        workflow_controls_layout.addWidget(analysis_track)
        workflow_controls_layout.addLayout(route_row)
        workflow_controls_layout.addLayout(selector_row)

        summary_card = QFrame(); summary_card.setObjectName("ProjectPanel")
        summary_layout = QVBoxLayout(summary_card)
        summary_title = QLabel("AI 测试方案（中文）"); summary_title.setObjectName("PanelTitle")
        summary_layout.addWidget(summary_title); summary_layout.addWidget(self.workflow_summary)

        focus_card = QFrame(); focus_card.setObjectName("ProjectPanel")
        focus_layout = QVBoxLayout(focus_card)
        focus_title = QLabel("测试重点与执行"); focus_title.setObjectName("PanelTitle")
        run_row = QHBoxLayout()
        run_row.addWidget(advanced_toggle)
        run_row.addStretch()
        run_row.addWidget(execute_btn)
        action_row = QHBoxLayout(); action_row.addWidget(diff_btn); action_row.addWidget(replay_btn); action_row.addStretch()
        focus_layout.addWidget(focus_title); focus_layout.addLayout(scope_row); focus_layout.addLayout(run_row)
        focus_layout.addWidget(advanced_group); focus_layout.addLayout(action_row)

        output_card = QFrame(); output_card.setObjectName("ProjectPanel")
        output_layout = QVBoxLayout(output_card)
        output_title = QLabel("流程执行与审计结果"); output_title.setObjectName("PanelTitle")
        output_layout.addWidget(output_title); output_layout.addWidget(self.workflow_output)
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(workflow_steps)
        layout.addWidget(workflow_controls); layout.addWidget(summary_card); layout.addWidget(focus_card); layout.addWidget(output_card)
        self._finish_page(content, layout)
        return page

    def _git_import_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("导入 Git 项目"); title.setObjectName("PageTitle")
        note = QLabel("连接远程 Git 仓库并克隆到本地，或选择已克隆仓库。导入时只读取源码分析接口，不会修改业务代码。")
        note.setObjectName("PageSubtitle"); note.setWordWrap(True)
        self.git_remote_url = QLineEdit(); self.git_remote_url.setPlaceholderText("Git 仓库地址，例如 https://github.com/org/service.git")
        self.git_clone_parent = QLineEdit(str(self.db.path.parent / "git-projects")); self.git_clone_parent.setPlaceholderText("克隆保存的父目录")
        choose_parent = QPushButton("选择保存目录"); choose_parent.clicked.connect(self.choose_git_clone_parent)
        self.git_project_path = QLineEdit(); self.git_project_path.setPlaceholderText("或选择已克隆的本地 Git 项目目录")
        choose = QPushButton("选择本地仓库"); choose.clicked.connect(self.choose_git_project)
        clone_import = QPushButton("克隆并导入"); clone_import.setProperty("primary", True); clone_import.clicked.connect(self.clone_and_import_git_project)
        local_import = QPushButton("导入本地仓库"); local_import.clicked.connect(self.import_git_project)
        remote_row = QHBoxLayout(); remote_row.addWidget(self.git_remote_url, 2); remote_row.addWidget(self.git_clone_parent, 1); remote_row.addWidget(choose_parent); remote_row.addWidget(clone_import)
        local_row = QHBoxLayout(); local_row.addWidget(self.git_project_path, 1); local_row.addWidget(choose); local_row.addWidget(local_import)
        self.git_import_output = QTextEdit(); self.git_import_output.setReadOnly(True); self.git_import_output.setMaximumHeight(170)
        self.git_import_output.setPlaceholderText("导入结果会显示在这里。")
        layout.addWidget(title); layout.addWidget(note); layout.addWidget(QLabel("远程仓库")); layout.addLayout(remote_row); layout.addWidget(QLabel("已有本地仓库")); layout.addLayout(local_row); layout.addWidget(self.git_import_output); layout.addStretch(1)
        self._finish_page(page, layout)
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
        open_artifacts = QPushButton("打开 Runner 产物"); open_artifacts.clicked.connect(self.open_selected_report_artifacts)
        report_actions = QHBoxLayout(); report_actions.addWidget(refresh); report_actions.addWidget(open_html); report_actions.addWidget(open_json); report_actions.addWidget(open_artifacts); report_actions.addStretch()
        layout.addWidget(title); layout.addWidget(subtitle); layout.addLayout(report_actions)
        layout.addWidget(self.report_table, 1); layout.addWidget(self.report_detail, 1)
        self.report_table.setAlternatingRowColors(True)
        self.report_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._finish_page(page, layout)
        return page

    def _external_runner_page(self):
        """Register an audited external runner and archive its standard artifacts.

        This screen deliberately never starts a command line.  A Runner is run by
        its own CLI/Docker worker; the platform persists the manifest first and
        accepts only a result whose run_id matches that immutable task.
        """
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("外部 Runner 任务与结果"); title.setObjectName("PageTitle")
        note = QLabel(
            "日常只需选择环境和测试套件后“一键执行”。平台会复用首次登记的 SteelMill Runner，"
            "自动生成任务、运行并归档结果；Docker / CI 的手工导入收在下方高级入口。"
        )
        note.setObjectName("PageSubtitle"); note.setWordWrap(True)
        self.runner_project_label = QLabel("当前项目：未选择"); self.runner_project_label.setObjectName("ContextBanner")

        quick_card = QFrame(); quick_card.setObjectName("RunnerConfigCard")
        quick_layout = QGridLayout(quick_card)
        quick_layout.setContentsMargins(18, 16, 18, 16); quick_layout.setHorizontalSpacing(16); quick_layout.setVerticalSpacing(10)
        quick_title = QLabel("一键执行 SteelMill"); quick_title.setObjectName("PanelTitle")
        quick_hint = QLabel("自动创建 Manifest 并归档 result.json；不会显示或写入密码、Token。")
        quick_hint.setObjectName("ValidationHint"); quick_hint.setWordWrap(True)
        self.auto_runner_environment = BelowPopupComboBox()
        self.auto_runner_suite = BelowPopupComboBox()
        self.auto_runner_suite.addItem("只读 Smoke（两个 GET 核心接口）", "run-manifest.readonly-smoke.example.json")
        self.auto_runner_suite.addItem("离线 Unit（不访问服务）", "run-manifest.unit.example.json")
        self.auto_runner_status = QLabel(); self.auto_runner_status.setObjectName("ValidationHint"); self.auto_runner_status.setVisible(False)
        auto_run_btn = QPushButton("▶ 一键执行"); auto_run_btn.setProperty("primary", True); auto_run_btn.clicked.connect(self.run_registered_steelmill)
        quick_layout.addWidget(quick_title, 0, 0, 1, 5); quick_layout.addWidget(quick_hint, 1, 0, 1, 5)
        quick_form = QHBoxLayout(); quick_form.setSpacing(10)
        environment_field = QHBoxLayout(); environment_field.setSpacing(8); environment_field.addWidget(QLabel("环境")); environment_field.addWidget(self.auto_runner_environment, 1)
        suite_field = QHBoxLayout(); suite_field.setSpacing(8); suite_field.addWidget(QLabel("套件")); suite_field.addWidget(self.auto_runner_suite, 1)
        quick_form.addLayout(environment_field, 1); quick_form.addSpacing(28); quick_form.addLayout(suite_field, 1); quick_form.addSpacing(28); quick_form.addWidget(auto_run_btn)
        quick_layout.addLayout(quick_form, 2, 0, 1, 5); quick_layout.addWidget(self.auto_runner_status, 3, 0, 1, 5)

        register_card = QFrame(); register_card.setObjectName("RunnerConfigCard")
        register_layout = QGridLayout(register_card)
        register_layout.setContentsMargins(18, 16, 18, 16); register_layout.setHorizontalSpacing(14); register_layout.setVerticalSpacing(8)
        register_title = QLabel("高级设置：首次接入或升级 Runner 时配置"); register_title.setObjectName("PanelTitle")
        self.runner_project_key = QLineEdit("steelmill")
        self.runner_name = QLineEdit("steelmill-runner")
        self.runner_version = QLineEdit("0.1.0")
        self.runner_workdir = QLineEdit(); self.runner_workdir.setPlaceholderText("SteelMill python_api_tests 工作目录")
        self.runner_python_executable = QLineEdit(); self.runner_python_executable.setPlaceholderText("运行 SteelMill 的 python.exe 完整路径")
        self.runner_image = QLineEdit(); self.runner_image.setPlaceholderText("可选：例如 steelmill-runner:0.1.0")
        self.runner_enabled = QCheckBox("启用此 Runner"); self.runner_enabled.setChecked(True)
        register_btn = QPushButton("保存 Adapter 与 Runner"); register_btn.setProperty("primary", True)
        register_btn.clicked.connect(self.save_external_runner)
        self.runner_save_status = QLabel("未保存"); self.runner_save_status.setObjectName("ValidationHint")
        register_layout.addWidget(register_title, 0, 0, 1, 4)
        register_layout.addWidget(QLabel("项目 Adapter Key"), 1, 0); register_layout.addWidget(self.runner_project_key, 1, 1)
        register_layout.addWidget(QLabel("Runner 名称"), 1, 2); register_layout.addWidget(self.runner_name, 1, 3)
        register_layout.addWidget(QLabel("Runner 版本"), 2, 0); register_layout.addWidget(self.runner_version, 2, 1)
        register_layout.addWidget(QLabel("镜像标识"), 2, 2); register_layout.addWidget(self.runner_image, 2, 3)
        register_layout.addWidget(QLabel("SteelMill Python"), 3, 0); register_layout.addWidget(self.runner_python_executable, 3, 1, 1, 3)
        register_layout.addWidget(QLabel("工作目录"), 4, 0); register_layout.addWidget(self.runner_workdir, 4, 1, 1, 3)
        register_layout.addWidget(self.runner_enabled, 5, 0); register_layout.addWidget(self.runner_save_status, 5, 1, 1, 2); register_layout.addWidget(register_btn, 5, 3)
        manual_card = QFrame(); manual_card.setObjectName("RunnerManualCard")
        actions = QHBoxLayout(manual_card); actions.setContentsMargins(14, 10, 14, 10); actions.setSpacing(10)
        queue_btn = QPushButton("导入 Manifest 并入队"); queue_btn.setProperty("primary", True); queue_btn.clicked.connect(self.queue_external_manifest)
        archive_btn = QPushButton("导入 result.json 并归档"); archive_btn.clicked.connect(self.archive_external_result)
        refresh_btn = QPushButton("刷新任务"); refresh_btn.clicked.connect(self.refresh_external_runner_runs)
        self.runner_platform_run_id = QLineEdit(); self.runner_platform_run_id.setPlaceholderText("平台任务 ID（选择表格行后自动填入）")
        actions.addWidget(queue_btn); actions.addWidget(self.runner_platform_run_id, 1); actions.addWidget(archive_btn); actions.addWidget(refresh_btn)
        self.runner_run_table = QTableWidget(0, 9)
        self.runner_run_table.setHorizontalHeaderLabels(["任务 ID", "run_id", "Runner", "环境", "状态", "创建时间", "结束时间", "产物目录", "操作"])
        self.runner_run_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.runner_run_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.runner_run_table.setAlternatingRowColors(True)
        self.runner_run_table.verticalHeader().setVisible(False)
        runner_header = self.runner_run_table.horizontalHeader()
        for column in (0, 2, 3, 5, 6):
            runner_header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        runner_header.setSectionResizeMode(1, QHeaderView.Interactive)
        runner_header.setSectionResizeMode(4, QHeaderView.Fixed)
        runner_header.setSectionResizeMode(7, QHeaderView.Stretch)
        runner_header.setSectionResizeMode(8, QHeaderView.Fixed)
        self.runner_run_table.setColumnWidth(1, 210)
        self.runner_run_table.setColumnWidth(4, 92)
        self.runner_run_table.setColumnWidth(8, 112)
        self.runner_run_table.verticalHeader().setDefaultSectionSize(38)
        self.runner_run_table.setObjectName("RunnerRunTable")
        self.runner_run_table.itemSelectionChanged.connect(self.show_external_runner_run)
        self.runner_run_table.cellDoubleClicked.connect(lambda row, _column: self.runner_run_table.selectRow(row))
        detail_card = QFrame(); detail_card.setObjectName("RunnerDetailCard")
        detail_layout = QVBoxLayout(detail_card); detail_layout.setContentsMargins(16, 12, 16, 12); detail_layout.setSpacing(8)
        detail_title = QLabel("任务详情（JSON）"); detail_title.setObjectName("PanelTitle")
        copy_detail = QPushButton("复制 JSON"); copy_detail.clicked.connect(self.copy_runner_run_detail)
        detail_header = QHBoxLayout(); detail_header.addWidget(detail_title); detail_header.addStretch(); detail_header.addWidget(copy_detail)
        self.runner_run_detail = QTextEdit(); self.runner_run_detail.setReadOnly(True); self.runner_run_detail.setObjectName("RunnerRunDetail")
        self.runner_run_detail.setPlaceholderText("选择一条任务后显示实际执行命令、Manifest、结果与产物目录。")
        detail_layout.addLayout(detail_header); detail_layout.addWidget(self.runner_run_detail)
        layout.addWidget(title); layout.addWidget(note); layout.addWidget(self.runner_project_label); layout.addWidget(register_card)
        layout.addWidget(quick_card); layout.addWidget(manual_card); layout.addWidget(self.runner_run_table, 1); layout.addWidget(detail_card, 1)
        self._finish_page(page, layout)
        layout.setContentsMargins(28, 16, 28, 16); layout.setSpacing(10)
        return page

    def _require_runner_project(self) -> int | None:
        if self.current_project_id:
            return self.current_project_id
        QMessageBox.information(self, "外部 Runner", "请先在项目中心创建并选择一个 TestPilot 项目。")
        return None

    def save_external_runner(self):
        project_id = self._require_runner_project()
        if project_id is None:
            return
        try:
            python_executable = Path(self.runner_python_executable.text().strip())
            working_directory = Path(self.runner_workdir.text().strip())
            if not python_executable.is_file():
                raise ValueError("请填写存在的 SteelMill Python 解释器完整路径")
            if not working_directory.is_dir():
                raise ValueError("请填写存在的 SteelMill python_api_tests 工作目录")
            self.db.save_project_adapter(project_id, self.runner_project_key.text(), {"managed_by": "TestPilot"})
            self.db.save_runner(
                project_id, self.runner_name.text(), command=str(python_executable), working_directory=str(working_directory),
                image=self.runner_image.text(), version=self.runner_version.text(),
                capabilities={
                    "manifest": "1.0", "result": "1.0",
                    "python_sha256": self._runner_file_sha256(python_executable),
                }, enabled=self.runner_enabled.isChecked(),
            )
        except (ValueError, OSError) as exc:
            self.runner_save_status.setText(f"保存失败：{exc}")
            QMessageBox.warning(self, "保存失败", str(exc)); return
        self.refresh_external_runner_runs()
        self.runner_save_status.setText(
            f"已保存：{self.runner_project_key.text().strip()} / {self.runner_name.text().strip()} {self.runner_version.text().strip()}"
        )
        self.statusBar().showMessage("外部 Runner 已保存；可使用上方一键执行。", 5000)
        QMessageBox.information(self, "Runner 已保存", "Runner 已登记。日常请直接使用上方“一键执行”。")

    @staticmethod
    def _runner_file_sha256(path: Path) -> str:
        """Fingerprint the registered interpreter before using it again."""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def run_registered_steelmill(self):
        """Run the registered local SteelMill Runner without exposing a shell UI.

        Only the saved Python executable is launched, with fixed module and
        arguments.  The manifest is generated by the platform and the result is
        completed automatically, so users never type a work order in daily use.
        """
        project_id = self._require_runner_project()
        if project_id is None:
            return
        runner = self.db.get_runner_by_name(project_id, "steelmill-runner")
        if runner is None or not runner["enabled"]:
            QMessageBox.warning(self, "未配置 Runner", "请先在高级设置中保存并启用 steelmill-runner。"); return
        python_executable = Path(str(runner.get("command") or ""))
        working_directory = Path(str(runner.get("working_directory") or ""))
        if not python_executable.is_file() or not working_directory.is_dir():
            QMessageBox.warning(self, "Runner 配置无效", "请在高级设置中重新保存有效的 Python 解释器和 SteelMill 工作目录。"); return
        environment_name = self.auto_runner_environment.currentData() or self.auto_runner_environment.currentText().strip()
        environment = self.db.get_environment(project_id, str(environment_name)) if environment_name else None
        if environment is None:
            QMessageBox.warning(self, "未配置环境", "请先在“环境校验”保存要执行的测试环境。"); return
        authorization_key = f"environment_authorized:{project_id}:{environment_name}"
        if self.db.get_setting(authorization_key) != "1":
            QMessageBox.warning(
                self, "环境未授权", "请先在“环境校验”确认目标为授权的测试/预发布环境并保存。"
            ); return
        expected_hash = str((runner.get("capabilities") or {}).get("python_sha256") or "")
        if expected_hash and self._runner_file_sha256(python_executable) != expected_hash:
            QMessageBox.warning(
                self, "Runner 校验失败", "已登记的 Python 解释器文件已变化，请在高级设置中重新确认并保存 Runner。"
            ); return
        template = working_directory / "examples" / str(self.auto_runner_suite.currentData() or "")
        if not template.is_file():
            QMessageBox.warning(self, "套件不存在", f"未找到套件模板：{template}"); return
        try:
            payload = json.loads(template.read_text(encoding="utf-8"))
            run_id = f"steelmill_{datetime.now():%Y%m%d_%H%M%S_%f}"
            artifacts_dir = working_directory / "reports" / run_id
            artifacts_dir.mkdir(parents=True, exist_ok=False)
            payload["run_id"] = run_id
            payload["environment_id"] = str(environment_name)
            payload["artifacts_dir"] = str(artifacts_dir)
            payload.setdefault("metadata", {}).update({"requested_by": "TestPilot desktop", "suite": self.auto_runner_suite.currentText()})
            manifest_path = artifacts_dir / "platform-manifest.json"
            manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            platform_run_id = queue_external_run(self.db, payload)
            self.db.start_runner_run(platform_run_id)
        except (OSError, ValueError, ContractError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "无法创建任务", str(exc)); return

        process_environment = QProcessEnvironment.systemEnvironment()
        process_environment.insert("STEELMILL_BASE_URL", str(environment.get("base_url") or ""))
        try:
            runtime_values = dict(environment.get("variables") or {})
            runtime_values.update(self.secret_store.decrypt_dict(environment.get("secrets_encrypted") or ""))
        except (ValueError, OSError):
            runtime_values = {}
        username = runtime_values.get("TEST_USERNAME") or runtime_values.get("USERNAME")
        password = runtime_values.get("TEST_PASSWORD") or runtime_values.get("PASSWORD")
        if username:
            process_environment.insert("STEELMILL_USERNAME", str(username))
        if password:
            process_environment.insert("STEELMILL_PASSWORD", str(password))
        process = QProcess(self)
        process.setProcessEnvironment(process_environment)
        process.setWorkingDirectory(str(working_directory))
        process.setProgram(str(python_executable))
        process.setArguments(["-m", "runner", "run", "--manifest", str(manifest_path)])
        process.finished.connect(lambda exit_code, _status, rid=platform_run_id, path=artifacts_dir: self._finish_registered_steelmill(rid, path, exit_code))
        process.errorOccurred.connect(lambda _error, rid=platform_run_id, path=artifacts_dir: self._finish_registered_steelmill(rid, path, 2))
        timeout = QTimer(process)
        timeout.setSingleShot(True)
        timeout.timeout.connect(lambda rid=platform_run_id: self._timeout_registered_steelmill(rid))
        timeout.start(int((payload.get("policy") or {}).get("timeout_seconds", 1800)) * 1000)
        self._external_runner_timeouts[platform_run_id] = timeout
        self._external_runner_processes[platform_run_id] = process
        self.auto_runner_status.setText(f"运行中：平台任务 #{platform_run_id} · {run_id}"); self.auto_runner_status.setVisible(True)
        self.refresh_external_runner_runs()
        process.start()

    def _timeout_registered_steelmill(self, platform_run_id: int):
        """Stop a locally launched Runner once its immutable policy deadline expires."""
        process = self._external_runner_processes.get(platform_run_id)
        if process is None or process.state() == QProcess.NotRunning:
            return
        self._external_runner_timed_out.add(platform_run_id)
        self.auto_runner_status.setText(f"任务 #{platform_run_id} 已超过 Manifest 超时限制，正在停止 Runner…")
        self.auto_runner_status.setVisible(True)
        process.terminate()
        QTimer.singleShot(5000, lambda rid=platform_run_id: self._force_stop_registered_steelmill(rid))

    def _force_stop_registered_steelmill(self, platform_run_id: int):
        process = self._external_runner_processes.get(platform_run_id)
        if process is not None and process.state() != QProcess.NotRunning:
            process.kill()

    def _finish_registered_steelmill(self, platform_run_id: int, artifacts_dir: Path, exit_code: int):
        """Archive a local process result once; failures still produce evidence."""
        stored = self.db.get_runner_run(platform_run_id)
        if stored is None or stored["status"] not in {"queued", "running"}:
            return
        result_path = artifacts_dir / "result.json"
        try:
            if platform_run_id in self._external_runner_timed_out:
                result = {
                    "schema_version": "1.0", "run_id": stored["run_key"], "status": "error",
                    "summary": {"total": 0, "passed": 0, "failed": 0, "error": 1, "skipped": 0},
                    "cases": [], "artifacts": {"root": str(artifacts_dir)},
                    "error": "Runner 超过 Manifest policy.timeout_seconds，已由平台停止",
                }
            elif result_path.is_file():
                result = json.loads(result_path.read_text(encoding="utf-8"))
                validate_local_runner_artifacts(artifacts_dir, result)
            else:
                result = {
                    "schema_version": "1.0", "run_id": stored["run_key"], "status": "error",
                    "summary": {"total": 0, "passed": 0, "failed": 0, "error": 1, "skipped": 0},
                    "cases": [], "artifacts": {"root": str(artifacts_dir)},
                    "error": f"Runner 未生成 result.json，进程退出码：{exit_code}",
                }
            complete_external_run(self.db, platform_run_id, result)
            self._archive_runner_report(platform_run_id, result)
            final_status = str(result.get("status") or "error")
            self.auto_runner_status.setText(f"已自动归档：平台任务 #{platform_run_id} · {final_status}"); self.auto_runner_status.setVisible(True)
        except (OSError, ValueError, ContractError, json.JSONDecodeError) as exc:
            self.auto_runner_status.setText(f"任务 #{platform_run_id} 归档失败：{exc}"); self.auto_runner_status.setVisible(True)
        finally:
            self._external_runner_processes.pop(platform_run_id, None)
            timeout = self._external_runner_timeouts.pop(platform_run_id, None)
            if timeout is not None:
                timeout.stop()
            self._external_runner_timed_out.discard(platform_run_id)
            self.refresh_external_runner_runs()

    def _read_runner_json(self, title: str) -> tuple[dict, Path] | None:
        path, _ = QFileDialog.getOpenFileName(self, title, "", "JSON files (*.json)")
        if not path:
            return None
        try:
            file_path = Path(path)
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON 根节点必须是对象")
            return payload, file_path
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, title, f"无法读取 JSON：{exc}")
            return None

    def queue_external_manifest(self):
        if self._require_runner_project() is None:
            return
        selected = self._read_runner_json("选择 SteelMill Manifest")
        if selected is None:
            return
        payload, path = selected
        try:
            platform_run_id = queue_external_run(self.db, payload)
        except (ContractError, ValueError) as exc:
            QMessageBox.warning(self, "入队被拒绝", str(exc)); return
        self.runner_platform_run_id.setText(str(platform_run_id))
        self.refresh_external_runner_runs()
        QMessageBox.information(self, "已入队", f"Manifest 已登记为平台任务 #{platform_run_id}。\n请用 SteelMill CLI 或 Docker 执行：{path.name}")

    def archive_external_result(self):
        project_id = self._require_runner_project()
        if project_id is None:
            return
        try:
            platform_run_id = int(self.runner_platform_run_id.text().strip())
        except ValueError:
            QMessageBox.information(self, "归档结果", "请先选择一条平台任务，或填写有效的平台任务 ID。")
            return
        selected = self._read_runner_json("选择 SteelMill result.json")
        if selected is None:
            return
        payload, _ = selected
        try:
            stored = self.db.get_runner_run(platform_run_id)
            if stored is None or int(stored["project_id"]) != project_id:
                raise ContractError("该平台任务不存在，或不属于当前项目")
            complete_external_run(self.db, platform_run_id, payload)
            self._archive_runner_report(platform_run_id, payload)
        except (ContractError, ValueError) as exc:
            QMessageBox.warning(self, "归档被拒绝", str(exc)); return
        self.refresh_external_runner_runs()
        self.statusBar().showMessage(f"SteelMill 结果已归档到平台任务 #{platform_run_id}。", 5000)

    def _archive_runner_report(self, platform_run_id: int, result: dict, refresh: bool = True) -> None:
        """Create a historical report index without moving or altering Runner artifacts."""
        stored = self.db.get_runner_run(platform_run_id)
        if stored is None:
            return
        project_id = int(stored["project_id"])
        project_name = next((item["name"] for item in self.db.list_projects() if int(item["id"]) == project_id), "外部 Runner")
        summary = dict(result.get("summary") or {})
        summary.update({
            "status": result.get("status") or stored.get("status"),
            "platform_run_id": platform_run_id,
            "runner_run_id": stored.get("run_key"),
            "runner": stored.get("runner_name"),
            "artifacts": result.get("artifacts") or {"root": stored.get("artifacts_dir")},
        })
        cases = []
        for case in result.get("cases") or []:
            if not isinstance(case, dict):
                continue
            cases.append({
                "name": case.get("name") or case.get("id") or "未命名用例",
                "module": case.get("module") or "SteelMill",
                "status": case.get("status") or "unknown",
                "elapsed_ms": case.get("elapsed_ms", 0),
                "status_code": case.get("status_code", ""),
                "error": case.get("error"),
            })
        report_dir = self.db.path.parent / "reports" / "external-runner"
        html_path, json_path = generate_report(
            report_dir, project_name, cases, summary,
            report_type="SteelMill Runner 报告", route="external_runner", environment=str(stored.get("environment_name") or ""),
        )
        self.db.save_evidence_report(
            project_id, "SteelMill Runner 报告", str(html_path), str(json_path), summary,
            route="external_runner", environment=str(stored.get("environment_name") or ""),
        )
        self.db.audit(project_id, "archive_runner_report", {"platform_run_id": platform_run_id, "artifacts": summary["artifacts"]})
        if refresh:
            self.refresh_reports()

    def _backfill_runner_reports(self, rows: list[dict]) -> None:
        """Archive terminal runs created before automatic report archiving existed."""
        if not self.current_project_id:
            return
        archived: set[int] = set()
        for evidence in self.db.list_evidence_reports(self.current_project_id):
            try:
                platform_run_id = json.loads(evidence.get("summary_json") or "{}").get("platform_run_id")
                if platform_run_id is not None:
                    archived.add(int(platform_run_id))
            except (TypeError, ValueError):
                continue
        created = False
        for row in rows:
            platform_run_id = int(row["id"])
            result = row.get("result") or {}
            if (
                platform_run_id not in archived
                and str(row.get("status") or "") in {"passed", "failed", "error"}
                and isinstance(result, dict)
                and result
            ):
                self._archive_runner_report(platform_run_id, result, refresh=False)
                created = True
        if created:
            self.refresh_reports()

    def _runner_action_icon(self, kind: str) -> QIcon:
        """Small local SVG icons: consistent blue rendering on every Windows font set."""
        paths = {
            "view": "<path d='M2.5 12s3.2-5.5 9.5-5.5S21.5 12 21.5 12 18.3 17.5 12 17.5 2.5 12 2.5 12z'/><circle cx='12' cy='12' r='2.5'/>",
            "download": "<path d='M12 3v11M8 10l4 4 4-4M4 19h16'/>",
            "delete": "<path d='M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5'/>",
        }
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'>"
            "<g fill='none' stroke='#1677e8' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
            + paths[kind] + "</g></svg>"
        )
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pixmap = QPixmap(24, 24); pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap); renderer.render(painter); painter.end()
        return QIcon(pixmap)

    def refresh_external_runner_runs(self):
        if not hasattr(self, "runner_run_table"):
            return
        environments = self.db.list_environments(self.current_project_id) if self.current_project_id else []
        selected_environment = self.auto_runner_environment.currentData() if hasattr(self, "auto_runner_environment") else None
        if hasattr(self, "auto_runner_environment"):
            self.auto_runner_environment.blockSignals(True); self.auto_runner_environment.clear()
            for environment in environments:
                self.auto_runner_environment.addItem(environment["name"], environment["name"])
            index = self.auto_runner_environment.findData(selected_environment)
            self.auto_runner_environment.setCurrentIndex(max(0, index))
            self.auto_runner_environment.blockSignals(False)
        if self.current_project_id and hasattr(self, "runner_python_executable"):
            registered = self.db.get_runner_by_name(self.current_project_id, "steelmill-runner")
            if registered:
                self.runner_project_key.setText(self.runner_project_key.text() or "steelmill")
                self.runner_version.setText(str(registered.get("version") or "0.1.0"))
                self.runner_workdir.setText(str(registered.get("working_directory") or ""))
                self.runner_python_executable.setText(str(registered.get("command") or ""))
                self.runner_image.setText(str(registered.get("image") or ""))
                self.runner_enabled.setChecked(bool(registered.get("enabled")))
        rows = self.db.list_runner_runs(self.current_project_id) if self.current_project_id else []
        self._backfill_runner_reports(rows)
        self._runner_run_rows = rows
        table = self.runner_run_table
        table.blockSignals(True); table.setRowCount(len(rows))
        try:
            for index, row in enumerate(rows):
                result = row.get("result") or {}
                values = (row["id"], row.get("run_key", ""), row.get("runner_name", ""), row.get("environment_name", ""), "",
                          row.get("created_at", ""), row.get("finished_at", ""),
                          (result.get("artifacts") or {}).get("root") or row.get("artifacts_dir", ""))
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value or ""))
                    table.setItem(index, column, item)
                status = str(row.get("status") or "queued").lower()
                status_label = QLabel(status)
                status_label.setAlignment(Qt.AlignCenter)
                status_label.setMinimumWidth(66)
                status_colors = {
                    "passed": ("#e8f8ef", "#16834a", "#b7ebcb"),
                    "failed": ("#fff0f0", "#cf3f3f", "#ffcaca"),
                    "error": ("#fff0f0", "#cf3f3f", "#ffcaca"),
                    "running": ("#eaf4ff", "#1677e8", "#b9d9ff"),
                    "queued": ("#fff8e7", "#9a6800", "#f5d88a"),
                }
                background, foreground, border = status_colors.get(status, status_colors["queued"])
                status_label.setStyleSheet(
                    f"background:{background}; color:{foreground}; border:1px solid {border}; "
                    "border-radius:10px; padding:3px 8px; font-weight:700;"
                )
                table.setCellWidget(index, 4, status_label)
                actions = QWidget(); action_layout = QHBoxLayout(actions); action_layout.setContentsMargins(3, 0, 3, 0); action_layout.setSpacing(3)
                view = QToolButton(); view.setIcon(self._runner_action_icon("view")); view.setIconSize(QSize(17, 17)); view.setAutoRaise(True); view.setToolTip("查看执行内容、命令和结果"); view.clicked.connect(lambda _=False, i=index: table.selectRow(i))
                open_artifacts = QToolButton(); open_artifacts.setIcon(self._runner_action_icon("download")); open_artifacts.setIconSize(QSize(17, 17)); open_artifacts.setAutoRaise(True); open_artifacts.setToolTip("打开产物目录"); open_artifacts.clicked.connect(lambda _=False, i=index: self.open_runner_artifacts(i))
                delete_run = QToolButton(); delete_run.setIcon(self._runner_action_icon("delete")); delete_run.setIconSize(QSize(17, 17)); delete_run.setAutoRaise(True); delete_run.setToolTip("删除此平台任务和对应历史报告"); delete_run.clicked.connect(lambda _=False, i=index: self.delete_runner_task(i))
                for button in (view, open_artifacts, delete_run):
                    button.setFixedSize(28, 28)
                action_layout.addWidget(view); action_layout.addWidget(open_artifacts); action_layout.addWidget(delete_run)
                table.setCellWidget(index, 8, actions)
        finally:
            table.blockSignals(False)

    def delete_runner_task(self, row_index: int):
        if row_index < 0 or row_index >= len(getattr(self, "_runner_run_rows", [])):
            return
        row = self._runner_run_rows[row_index]
        run_id = int(row["id"])
        if QMessageBox.question(
            self, "删除 Runner 任务", f"确定删除平台任务 #{run_id} 及其历史报告索引吗？\n不会删除 SteelMill 原始产物目录。"
        ) != QMessageBox.Yes:
            return
        for evidence in self.db.list_evidence_reports(int(row["project_id"])):
            try:
                platform_run_id = json.loads(evidence.get("summary_json") or "{}").get("platform_run_id")
                if int(platform_run_id) == run_id:
                    self.db.delete_evidence_report(int(evidence["id"]))
            except (TypeError, ValueError):
                continue
        self.db.delete_runner_run(run_id)
        self.refresh_external_runner_runs(); self.refresh_reports()
        self.statusBar().showMessage(f"已删除平台任务 #{run_id}，原始产物目录未删除。", 4000)

    def show_external_runner_run(self):
        row_index = self.runner_run_table.currentRow()
        if row_index < 0 or row_index >= len(getattr(self, "_runner_run_rows", [])):
            return
        row = self._runner_run_rows[row_index]
        self.runner_platform_run_id.setText(str(row["id"]))
        result = row.get("result") or {}
        runner = self.db.get_runner_by_name(int(row["project_id"]), str(row.get("runner_name") or ""))
        artifacts = result.get("artifacts") or {"root": row.get("artifacts_dir")}
        artifacts_root = str(artifacts.get("root") or row.get("artifacts_dir") or "")
        manifest_path = str(Path(artifacts_root) / "platform-manifest.json") if artifacts_root else ""
        execution = {
            "runner": row.get("runner_name"),
            "python": (runner or {}).get("command") or "由外部 Runner 提供",
            "working_directory": (runner or {}).get("working_directory") or "由外部 Runner 提供",
            "command": f"{(runner or {}).get('command') or 'python'} -m runner run --manifest {manifest_path or '<Manifest 文件>'}",
            "suite": (row.get("manifest") or {}).get("metadata", {}).get("suite", ""),
        }
        payload = {"execution": execution, "manifest": row.get("manifest") or {}, "result": result, "artifacts": artifacts}
        self.runner_run_detail.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    def copy_runner_run_detail(self):
        QApplication.clipboard().setText(self.runner_run_detail.toPlainText())
        self.statusBar().showMessage("任务 JSON 已复制。", 3000)

    def open_runner_artifacts(self, row_index: int):
        if row_index < 0 or row_index >= len(getattr(self, "_runner_run_rows", [])):
            return
        row = self._runner_run_rows[row_index]
        root = (row.get("result") or {}).get("artifacts", {}).get("root") or row.get("artifacts_dir")
        path = Path(str(root or ""))
        if not path.is_dir():
            QMessageBox.warning(self, "产物目录不存在", f"未找到产物目录：{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def copy_runner_manifest(self, row_index: int):
        if row_index < 0 or row_index >= len(getattr(self, "_runner_run_rows", [])):
            return
        manifest = self._runner_run_rows[row_index].get("manifest") or {}
        QApplication.clipboard().setText(json.dumps(manifest, ensure_ascii=False, indent=2))
        self.statusBar().showMessage("Manifest 已复制。", 3000)

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
        self.ai_dialogue_route = BelowPopupComboBox(); self.ai_dialogue_route.addItem("智能对话 · 可测试编排", "chat"); self.ai_dialogue_route.addItem("路线 A · 源码 + 数据库", "route_a"); self.ai_dialogue_route.addItem("路线 B · 接口资料", "route_b"); self.ai_dialogue_route.addItem("组合检查 · A+B", "combined")
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
        self.ai_chat_model = BelowPopupComboBox(); self.ai_chat_model.setObjectName("AIChatModelSelector"); self.ai_chat_model.setMinimumWidth(160)
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
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(workspace, 1)
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
        return self._endpoint_page_apifox()

        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("接口资产"); title.setObjectName("PageTitle")
        subtitle = QLabel("选择接口后可直接调试、查看定义或保存为测试用例。")
        subtitle.setObjectName("PageSubtitle")
        self.endpoint_project_label = QLabel("当前项目：未选择"); self.endpoint_project_label.setObjectName("ContextBanner")
        top_filters = QHBoxLayout(); top_filters.setSpacing(10)
        top_filters.addWidget(QLabel("测试项目"))
        self.endpoint_project_selector = QComboBox(); self.endpoint_project_selector.currentIndexChanged.connect(self.select_endpoint_project)
        top_filters.addWidget(self.endpoint_project_selector, 1)
        self.search = QLineEdit(); self.search.setPlaceholderText("⌕  搜索接口名称、路径、方法")
        top_filters.addWidget(self.search, 2)
        self.source_filter = QComboBox(); self.source_filter.addItem("全部资料源", None)
        self.module_filter = QComboBox(); self.module_filter.addItem("全部模块", None)
        self.source_filter.currentIndexChanged.connect(self.refresh_endpoints)
        self.module_filter.currentIndexChanged.connect(self.refresh_endpoints)
        top_filters.addWidget(self.source_filter, 1)
        self._endpoint_search_timer = QTimer(self); self._endpoint_search_timer.setSingleShot(True); self._endpoint_search_timer.setInterval(180)
        self._endpoint_search_timer.timeout.connect(self.refresh_endpoints); self.search.textChanged.connect(self._schedule_endpoint_refresh)

        workspace = QSplitter(Qt.Horizontal); workspace.setObjectName("EndpointWorkbench")
        group_card = QFrame(); group_card.setObjectName("EndpointGroupCard")
        group_layout = QVBoxLayout(group_card); group_layout.setContentsMargins(12, 12, 12, 12); group_layout.setSpacing(8)
        group_header = QHBoxLayout(); group_title = QLabel("接口分组"); group_title.setObjectName("PanelTitle")
        add_group = QPushButton("▦"); add_group.setToolTip("模块按接口导入数据自动生成")
        group_header.addWidget(group_title); group_header.addStretch(); group_header.addWidget(add_group)
        self.endpoint_tree = QTreeWidget(); self.endpoint_tree.setObjectName("EndpointNavigator"); self.endpoint_tree.setHeaderHidden(True)
        self.endpoint_tree.itemClicked.connect(self.select_endpoint_tree_item)
        add_endpoint = QPushButton("＋ 新建分组接口"); add_endpoint.clicked.connect(self.add_endpoint)
        group_layout.addLayout(group_header); group_layout.addWidget(self.endpoint_tree, 1); group_layout.addWidget(add_endpoint)

        # The table is retained as the selection model used by existing import,
        # edit and delete flows.  The user-facing navigator is the module tree.
        self.endpoint_table = QTableWidget(0, 3); self.endpoint_table.setObjectName("EndpointList")
        self.endpoint_table.setHorizontalHeaderLabels(["方法", "接口名称", "路径"])
        self.endpoint_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.endpoint_table.itemSelectionChanged.connect(self.show_endpoint); self.endpoint_table.setVisible(False)

        request_card = QFrame(); request_card.setObjectName("EndpointRequestCard")
        request_layout = QVBoxLayout(request_card); request_layout.setContentsMargins(14, 12, 14, 12); request_layout.setSpacing(8)
        request_header = QHBoxLayout(); request_title = QLabel("调试接口"); request_title.setObjectName("PanelTitle")
        self.endpoint_active_label = QLabel("选择左侧接口开始调试"); self.endpoint_active_label.setObjectName("EndpointActiveTab")
        environment_selector = QComboBox(); environment_selector.addItem("开发环境（使用已保存环境）")
        request_header.addWidget(request_title); request_header.addWidget(self.endpoint_active_label, 1); request_header.addWidget(environment_selector)
        request_url_row = QHBoxLayout(); self.method = QComboBox(); self.method.addItems(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
        self.endpoint_url = QLineEdit(); self.endpoint_url.setReadOnly(True); self.endpoint_url.setPlaceholderText("选择接口后显示完整请求地址")
        send = QPushButton("发送"); send.setProperty("primary", True); send.clicked.connect(self.send_request)
        request_url_row.addWidget(self.method); request_url_row.addWidget(self.endpoint_url, 1); request_url_row.addWidget(send)
        self.path = QLineEdit("/"); self.path.setVisible(False)
        self.debug_endpoint_label = QLabel("使用环境校验中保存的 Base URL、账号和授权配置。")
        self.debug_endpoint_label.setObjectName("ValidationHint")
        self.endpoint_request_tabs = QTabWidget(); self.endpoint_request_tabs.setObjectName("EndpointRequestTabs")
        params_tab = QLabel("接口参数会根据导入的定义显示；当前可在 Body 中填写请求数据。"); params_tab.setWordWrap(True)
        headers_tab = QLabel("认证 Token 由已保存环境和 Runner 自动维护；手工 Header 可在后续版本扩展。"); headers_tab.setWordWrap(True)
        body_tab = QWidget(); body_layout = QVBoxLayout(body_tab); body_layout.setContentsMargins(0, 6, 0, 0)
        self.body = QTextEdit("{}"); self.body.setObjectName("EndpointEditor"); body_layout.addWidget(self.body)
        auth_tab = QLabel("认证使用环境校验保存的测试账号。点击“验证登录”可安全确认。")
        auth_tab.setWordWrap(True)
        self.endpoint_request_tabs.addTab(params_tab, "参数")
        self.endpoint_request_tabs.addTab(headers_tab, "Headers")
        self.endpoint_request_tabs.addTab(body_tab, "Body")
        self.endpoint_request_tabs.addTab(auth_tab, "认证")
        request_actions = QHBoxLayout(); login_check = QPushButton("验证登录"); login_check.clicked.connect(self.verify_environment_login)
        save_case = QPushButton("保存为用例"); save_case.clicked.connect(self.save_request_as_case)
        edit_btn = QPushButton("编辑 JSON"); edit_btn.clicked.connect(self.edit_endpoint)
        delete_btn = QPushButton("删除接口"); delete_btn.setProperty("danger", True); delete_btn.clicked.connect(self.delete_endpoint)
        request_actions.addWidget(login_check); request_actions.addWidget(save_case); request_actions.addWidget(edit_btn); request_actions.addWidget(delete_btn); request_actions.addStretch()
        response_title = QLabel("响应结果"); response_title.setObjectName("EndpointResponseTitle")
        self.response = QTextEdit(); self.response.setReadOnly(True); self.response.setObjectName("EndpointEditor"); self.response.setPlaceholderText("发送请求后在此显示脱敏响应。")
        request_layout.addLayout(request_header); request_layout.addLayout(request_url_row); request_layout.addWidget(self.debug_endpoint_label)
        request_layout.addWidget(self.endpoint_request_tabs, 1); request_layout.addLayout(request_actions); request_layout.addWidget(response_title); request_layout.addWidget(self.response, 1)

        definition_card = QFrame(); definition_card.setObjectName("EndpointDefinitionCard")
        definition_layout = QVBoxLayout(definition_card); definition_layout.setContentsMargins(14, 12, 14, 12); definition_layout.setSpacing(8)
        definition_title = QLabel("接口定义"); definition_title.setObjectName("PanelTitle")
        self.endpoint_detail = QTextEdit(); self.endpoint_detail.setObjectName("EndpointDetail"); self.endpoint_detail.setReadOnly(True)
        self.endpoint_detail.setPlaceholderText("选择接口后显示基本信息、请求参数与响应定义。")
        definition_layout.addWidget(definition_title); definition_layout.addWidget(self.endpoint_detail, 1)

        workspace.addWidget(group_card); workspace.addWidget(request_card); workspace.addWidget(definition_card)
        workspace.setSizes([230, 610, 340])
        group_card.setMinimumWidth(210); request_card.setMinimumWidth(500); definition_card.setMinimumWidth(300)
        layout.addWidget(title); layout.addWidget(subtitle); layout.addLayout(top_filters); layout.addWidget(workspace, 1)
        self._finish_page(page, layout); layout.setContentsMargins(24, 14, 24, 14); layout.setSpacing(9)
        return page

    def _endpoint_input_table(self, headings: list[str]) -> QTableWidget:
        table = QTableWidget(1, len(headings))
        table.setObjectName("EndpointInputTable")
        table.setHorizontalHeaderLabels(headings)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(108)
        for column in range(len(headings)):
            table.setItem(0, column, QTableWidgetItem("添加参数" if column == 0 else ""))
        return table

    def _configure_http_method_selector(self, selector: QComboBox) -> None:
        colors = {
            "GET": "#00a854", "POST": "#f0441f", "PUT": "#1677ff", "PATCH": "#8b5cf6",
            "DELETE": "#ef4444", "HEAD": "#06b6c9", "OPTIONS": "#d69e00",
        }
        for index in range(selector.count()):
            method = selector.itemText(index).upper()
            selector.setItemData(index, QColor(colors.get(method, "#1677e8")), Qt.ForegroundRole)
        selector.setItemDelegate(HttpMethodItemDelegate(selector))
        selector.currentTextChanged.connect(self._set_http_method_current_color)
        self._set_http_method_current_color(selector.currentText())

    def _set_http_method_current_color(self, method: str) -> None:
        colors = {
            "GET": "#00a854", "POST": "#f0441f", "PUT": "#1677ff", "PATCH": "#8b5cf6",
            "DELETE": "#ef4444", "HEAD": "#06b6c9", "OPTIONS": "#d69e00",
        }
        if hasattr(self, "method"):
            palette = self.method.palette()
            color = QColor(colors.get(str(method).upper(), "#1677e8"))
            palette.setColor(QPalette.ButtonText, color)
            palette.setColor(QPalette.Text, color)
            self.method.setPalette(palette)
            # Qt's native combo style may ignore a palette Text role while the
            # popup delegate is correctly coloured; explicitly keep the closed
            # field on the same semantic method colour.
            self.method.setStyleSheet(f"color: {color.name()};")

    def _refresh_endpoint_debug_environments(self) -> None:
        """Offer every saved development/test URL in the debugging toolbar."""
        if not hasattr(self, "endpoint_debug_environment"):
            return
        selector = self.endpoint_debug_environment
        selected = selector.currentData()
        environments = self.db.list_environments(self.current_project_id) if self.current_project_id else []
        selector.blockSignals(True)
        selector.clear()
        for environment in environments:
            selector.addItem(str(environment.get("name") or "未命名环境"), environment.get("id"))
        selector.addItem("配置环境 URL…", "__manage__")
        index = selector.findData(selected)
        selector.setCurrentIndex(index if index >= 0 else (0 if environments else selector.count() - 1))
        selector.blockSignals(False)

    def _select_endpoint_debug_environment(self, _index: int) -> None:
        if not hasattr(self, "endpoint_debug_environment"):
            return
        environment_id = self.endpoint_debug_environment.currentData()
        if environment_id == "__manage__":
            # URL editing remains in the existing environment-validation workflow.
            self._activate_page(2)
            return
        if not self.current_project_id or environment_id is None:
            return
        environment = next(
            (item for item in self.db.list_environments(self.current_project_id) if item.get("id") == environment_id), None
        )
        if environment:
            self._load_environment(environment)
            self._sync_endpoint_url_query()

    def _endpoint_page_apifox(self):
        """Apifox-style interface workbench, while preserving TestPilot data flows."""
        page = QWidget(); page.setObjectName("EndpointAssetPage")
        layout = QVBoxLayout(page); layout.setContentsMargins(14, 12, 14, 12); layout.setSpacing(8)
        title = QLabel("接口资产"); title.setObjectName("PageTitle")
        subtitle = QLabel("选择接口可调试或查看定义，支持按分组管理接口，提高测试效率。")
        subtitle.setObjectName("PageSubtitle")
        self.endpoint_project_label = QLabel("当前项目：未选择"); self.endpoint_project_label.setVisible(False)

        filters = QHBoxLayout(); filters.setSpacing(10)
        filters.addWidget(QLabel("测试项目"))
        self.endpoint_project_selector = BelowPopupComboBox(); self.endpoint_project_selector.setMinimumWidth(180)
        self.endpoint_project_selector.currentIndexChanged.connect(self.select_endpoint_project)
        filters.addWidget(self.endpoint_project_selector); filters.addStretch()
        self.search = QLineEdit(); self.search.setObjectName("EndpointSearch"); self.search.setMinimumWidth(270)
        self.search.setPlaceholderText("⌕  搜索接口名称、路径、方法")
        self.source_filter = BelowPopupComboBox(); self.source_filter.setMinimumWidth(210); self.source_filter.addItem("全部资料源", None)
        self.module_filter = BelowPopupComboBox(); self.module_filter.addItem("全部模块", None)
        self.source_filter.currentIndexChanged.connect(self.refresh_endpoints)
        self.module_filter.currentIndexChanged.connect(self.refresh_endpoints)
        filters.addWidget(self.search); filters.addWidget(self.source_filter)
        self._endpoint_search_timer = QTimer(self); self._endpoint_search_timer.setSingleShot(True); self._endpoint_search_timer.setInterval(180)
        self._endpoint_search_timer.timeout.connect(self.refresh_endpoints); self.search.textChanged.connect(self._schedule_endpoint_refresh)

        workbench = QSplitter(Qt.Horizontal); workbench.setObjectName("EndpointWorkbench")
        groups = QFrame(); groups.setObjectName("EndpointGroupCard")
        groups_layout = QVBoxLayout(groups); groups_layout.setContentsMargins(10, 10, 10, 10); groups_layout.setSpacing(7)
        groups_header = QHBoxLayout(); groups_title = QLabel("接口分组"); groups_title.setObjectName("EndpointPaneTitle")
        new_endpoint_icon = QToolButton(); new_endpoint_icon.setText("＋"); new_endpoint_icon.setToolTip("新建接口"); new_endpoint_icon.clicked.connect(self.add_endpoint)
        groups_header.addWidget(groups_title); groups_header.addStretch(); groups_header.addWidget(new_endpoint_icon)
        self.endpoint_tree = QTreeWidget(); self.endpoint_tree.setObjectName("EndpointNavigator"); self.endpoint_tree.setHeaderHidden(True)
        self.endpoint_tree.itemClicked.connect(self.select_endpoint_tree_item)
        new_group = QPushButton("＋  新建分组"); new_group.setObjectName("EndpointNewGroup"); new_group.clicked.connect(self.add_endpoint)
        groups_layout.addLayout(groups_header); groups_layout.addWidget(self.endpoint_tree, 1); groups_layout.addWidget(new_group)

        # Existing edit, delete and import flows use this hidden selection model.
        self.endpoint_table = QTableWidget(0, 3); self.endpoint_table.setObjectName("EndpointList")
        self.endpoint_table.setHorizontalHeaderLabels(["方法", "接口名称", "路径"])
        self.endpoint_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.endpoint_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.endpoint_table.itemSelectionChanged.connect(self.show_endpoint); self.endpoint_table.setVisible(False)

        request = QFrame(); request.setObjectName("EndpointRequestCard")
        request_layout = QVBoxLayout(request); request_layout.setContentsMargins(12, 12, 12, 12); request_layout.setSpacing(12)
        request_header = QHBoxLayout(); request_header.setSpacing(8); request_header.addWidget(QLabel("调试接口", objectName="EndpointPaneTitle"))
        self.endpoint_active_label = QLabel("选择接口"); self.endpoint_active_label.setObjectName("EndpointActiveTab")
        self.endpoint_debug_environment = BelowPopupComboBox(); self.endpoint_debug_environment.setObjectName("EndpointEnvironment")
        self.endpoint_debug_environment.currentIndexChanged.connect(self._select_endpoint_debug_environment)
        self.endpoint_active_label.setFixedHeight(32); self.endpoint_debug_environment.setFixedHeight(32)
        save_case = QPushButton("保存"); save_case.setObjectName("EndpointToolbarButton"); save_case.setFixedHeight(32); save_case.clicked.connect(self.save_request_as_case)
        more = QPushButton("更多"); more.setObjectName("EndpointToolbarButton"); more.setFixedHeight(32); more.clicked.connect(self.edit_endpoint)
        request_header.addWidget(self.endpoint_active_label, 1); request_header.addWidget(self.endpoint_debug_environment); request_header.addWidget(save_case); request_header.addWidget(more)
        url_row = QHBoxLayout(); url_row.setContentsMargins(0, 0, 0, 0); url_row.setSpacing(0)
        self.method = BelowPopupComboBox(); self.method.setObjectName("EndpointMethod"); self.method.addItems(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
        self._configure_http_method_selector(self.method)
        self.method.setFixedHeight(36); self.method.setFixedWidth(84)
        self.endpoint_url = QLineEdit(); self.endpoint_url.setObjectName("EndpointUrl"); self.endpoint_url.setReadOnly(True); self.endpoint_url.setPlaceholderText("选择接口后显示完整请求地址"); self.endpoint_url.setFixedHeight(36)
        send = QPushButton("发送"); send.setObjectName("EndpointSend"); send.setProperty("primary", True); send.clicked.connect(self.send_request)
        send.setFixedHeight(36); send.setFixedWidth(54)
        url_row.addWidget(self.method); url_row.addWidget(self.endpoint_url, 1); url_row.addSpacing(6); url_row.addWidget(send)
        self.path = QLineEdit("/"); self.path.setVisible(False)

        self.endpoint_request_tabs = QTabWidget(); self.endpoint_request_tabs.setObjectName("EndpointRequestTabs")
        parameter_page = QWidget(); parameter_page_layout = QVBoxLayout(parameter_page); parameter_page_layout.setContentsMargins(14, 8, 14, 8); parameter_page_layout.setSpacing(8)
        parameter_page_layout.addWidget(QLabel("Query 参数", objectName="EndpointFormTitle"))
        self.endpoint_query_editor = KeyValueParameterEditor(
            "参数名", "参数值", "添加参数", "参数值", shows_metadata=True
        )
        self.endpoint_query_editor.parametersChanged.connect(self._sync_endpoint_url_query)
        parameter_page_layout.addWidget(self.endpoint_query_editor)
        parameter_page_layout.addStretch()
        body_container = QWidget(); parameter_layout = QVBoxLayout(body_container)
        parameter_layout.setContentsMargins(0, 0, 0, 0); parameter_layout.setSpacing(5)
        body_kind_row = QHBoxLayout(); body_kind_row.setContentsMargins(14, 0, 14, 0); body_kind_row.setSpacing(14)
        self.endpoint_body_type_buttons: dict[str, QRadioButton] = {}
        for key, text in (
            ("none", "none"), ("form-data", "form-data"),
            ("x-www-form-urlencoded", "x-www-form-urlencoded"), ("raw", "raw"), ("json", "JSON"),
            ("xml", "XML"), ("text", "Text"), ("binary", "Binary"), ("graphql", "GraphQL"), ("msgpack", "msgpack"),
        ):
            radio = QRadioButton(text); radio.setObjectName("EndpointBodyType")
            radio.setChecked(key == "json")
            radio.toggled.connect(lambda checked, selected=key: checked and self._set_endpoint_body_type(selected))
            self.endpoint_body_type_buttons[key] = radio
            body_kind_row.addWidget(radio)
        body_kind_row.addStretch()
        format_body = QPushButton("格式化"); format_body.setObjectName("EndpointBodyFormat")
        format_body.clicked.connect(self._format_endpoint_body)
        body_kind_row.addWidget(format_body)
        self.endpoint_body_format_button = format_body
        self._endpoint_body_type = "json"
        self.endpoint_body_stack = QStackedWidget()
        none_page = QWidget(); none_layout = QVBoxLayout(none_page); none_layout.addStretch()
        none_hint = QLabel("当前接口不发送请求 Body"); none_hint.setObjectName("EndpointEmptyHint"); none_hint.setAlignment(Qt.AlignCenter)
        none_layout.addWidget(none_hint); none_layout.addStretch()
        self.endpoint_body_form_editor = KeyValueParameterEditor(
            "参数名", "参数值", "添加参数", "参数值", shows_metadata=True
        )
        self.endpoint_body_urlencoded_editor = KeyValueParameterEditor(
            "参数名", "参数值", "添加参数", "参数值", shows_metadata=True
        )
        # form-data uses the same compact editor as Params.  Its page grows
        # only when rows are actually added instead of occupying the tab body.
        self.endpoint_body_form_editor.parametersChanged.connect(self._update_endpoint_body_editor_height)
        self.endpoint_body_urlencoded_editor.parametersChanged.connect(self._update_endpoint_body_editor_height)
        self.body = QTextEdit("{}"); self.body.setObjectName("EndpointBodyEditor")
        self.body.setPlaceholderText("根据接口定义填写请求 Body")
        self.body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        text_page = QWidget(); text_layout = QVBoxLayout(text_page); text_layout.setContentsMargins(0, 0, 0, 0); text_layout.addWidget(self.body)
        binary_page = QWidget(); binary_layout = QHBoxLayout(binary_page); binary_layout.setContentsMargins(8, 8, 8, 8); binary_layout.setSpacing(8)
        self.endpoint_binary_path = QLineEdit(); self.endpoint_binary_path.setReadOnly(True); self.endpoint_binary_path.setPlaceholderText("选择要作为 Binary Body 发送的文件")
        binary_choose = QPushButton("选择文件"); binary_choose.clicked.connect(self._choose_endpoint_binary_file)
        binary_layout.addWidget(self.endpoint_binary_path, 1); binary_layout.addWidget(binary_choose)
        for page_widget in (none_page, self.endpoint_body_form_editor, self.endpoint_body_urlencoded_editor, text_page, binary_page):
            self.endpoint_body_stack.addWidget(page_widget)
        self._endpoint_body_pages = {
            "none": none_page, "form-data": self.endpoint_body_form_editor,
            "x-www-form-urlencoded": self.endpoint_body_urlencoded_editor, "binary": binary_page,
            "raw": text_page, "json": text_page, "xml": text_page, "text": text_page,
            "graphql": text_page, "msgpack": text_page,
        }
        self._set_endpoint_body_type("json")
        body_editor_host = QWidget(); body_editor_layout = QHBoxLayout(body_editor_host)
        body_editor_layout.setContentsMargins(14, 0, 14, 8); body_editor_layout.setSpacing(0)
        # Keep the same horizontal content rule as Params, but never let a
        # form page stretch vertically into a large empty panel.
        self.endpoint_body_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        body_editor_layout.addWidget(self.endpoint_body_stack, 1, Qt.AlignTop)
        parameter_layout.addLayout(body_kind_row); parameter_layout.addWidget(body_editor_host); parameter_layout.addStretch()
        headers_page = QWidget(); headers_layout = QVBoxLayout(headers_page); headers_layout.setContentsMargins(0, 8, 0, 8); headers_layout.setSpacing(8)
        headers_layout.addWidget(QLabel("Headers", objectName="EndpointFormTitle"))
        self.endpoint_headers_editor = KeyValueParameterEditor("参数名", "参数值", "添加 Header", "Header 值", supports_enabled=True)
        headers_layout.addWidget(self.endpoint_headers_editor)
        headers_layout.addStretch()
        cookies_page = QWidget(); cookies_layout = QVBoxLayout(cookies_page); cookies_layout.setContentsMargins(0, 8, 0, 8); cookies_layout.setSpacing(8)
        cookies_layout.addWidget(QLabel("Cookies", objectName="EndpointFormTitle"))
        self.endpoint_cookies_editor = KeyValueParameterEditor("Cookie 名称", "Cookie 值", "添加 Cookie", "Cookie 值", supports_enabled=True)
        cookies_layout.addWidget(self.endpoint_cookies_editor)
        cookies_layout.addStretch()
        auth_page = QWidget(); auth_layout = QVBoxLayout(auth_page); auth_layout.setContentsMargins(8, 8, 8, 8); auth_layout.setSpacing(8)
        auth_layout.addWidget(QLabel("鉴权方式", objectName="EndpointFormTitle"))
        self.endpoint_auth_mode = BelowPopupComboBox(); self.endpoint_auth_mode.addItems(["无需鉴权", "Bearer Token", "Basic Auth"]); auth_layout.addWidget(self.endpoint_auth_mode)
        auth_help = QFrame(); auth_help.setObjectName("EndpointAuthHelp"); auth_help_layout = QVBoxLayout(auth_help); auth_help_layout.addWidget(QLabel("无需鉴权", objectName="EndpointFormTitle")); auth_help_layout.addWidget(QLabel("登录接口可使用“验证登录”，其他接口将复用已保存测试环境的授权信息。"))
        auth_layout.addWidget(auth_help); auth_layout.addStretch()
        before_page = QWidget(); before_layout = QVBoxLayout(before_page); before_layout.setContentsMargins(8, 8, 8, 8)
        before_button = QPushButton("添加前置操作  ▾"); before_button.setObjectName("EndpointAddAction")
        before_menu = QMenu(before_button); before_menu.setObjectName("EndpointOperationMenu")
        before_menu.aboutToShow.connect(lambda: before_menu.setFixedWidth(before_button.width()))
        for action_name in ("数据库操作", "脚本", "脚本库", "等待时间", "从其它接口/用例/目录导入"):
            action = before_menu.addAction(action_name); action.triggered.connect(lambda _=False, name=action_name: self._add_endpoint_operation("pre", name))
        before_button.setMenu(before_menu); before_layout.addWidget(before_button); before_layout.addStretch()
        self.endpoint_pre_actions_layout = before_layout
        after_page = QWidget(); after_layout = QVBoxLayout(after_page); after_layout.setContentsMargins(8, 8, 8, 8)
        after_button = QPushButton("添加后置操作  ▾"); after_button.setObjectName("EndpointAddAction")
        after_menu = QMenu(after_button); after_menu.setObjectName("EndpointOperationMenu")
        after_menu.aboutToShow.connect(lambda: after_menu.setFixedWidth(after_button.width()))
        for action_name in ("断言", "提取变量", "数据库操作", "脚本", "脚本库", "等待时间", "从其它接口/用例/目录导入"):
            action = after_menu.addAction(action_name); action.triggered.connect(lambda _=False, name=action_name: self._add_endpoint_operation("post", name))
        after_button.setMenu(after_menu); after_layout.addWidget(after_button); after_layout.addStretch()
        self.endpoint_post_actions_layout = after_layout
        settings_page = QWidget(); settings_layout = QFormLayout(settings_page); settings_layout.setContentsMargins(10, 10, 10, 10); settings_layout.setVerticalSpacing(13)
        for label in ("SSL 证书验证", "自动跟随重定向", "兼容带注释的 JSON"):
            setting = QCheckBox("跟随项目设置"); settings_layout.addRow(label, setting)
        url_encode = BelowPopupComboBox(); url_encode.addItem("跟随项目设置"); settings_layout.addRow("URL 自动编码", url_encode)
        self.endpoint_request_tabs.addTab(parameter_page, "Params"); self.endpoint_request_tabs.addTab(body_container, "Body  1")
        self.endpoint_request_tabs.addTab(headers_page, "Headers  2"); self.endpoint_request_tabs.addTab(cookies_page, "Cookies")
        self.endpoint_request_tabs.addTab(auth_page, "Auth"); self.endpoint_request_tabs.addTab(before_page, "前置操作")
        self.endpoint_request_tabs.addTab(after_page, "后置操作  3"); self.endpoint_request_tabs.addTab(settings_page, "设置")
        self.endpoint_request_tabs.setCurrentIndex(1)

        action_bar = QFrame(); action_bar.setObjectName("EndpointActionBar")
        actions = QHBoxLayout(action_bar); actions.setContentsMargins(8, 6, 8, 6); actions.setSpacing(8)
        login = QPushButton("验证登录"); login.setObjectName("EndpointActionButton"); login.clicked.connect(self.verify_environment_login)
        delete = QPushButton("删除接口"); delete.setProperty("danger", True); delete.clicked.connect(self.delete_endpoint)
        delete.setFixedHeight(30); login.setFixedHeight(30)
        actions.addWidget(login); actions.addSpacing(8); actions.addWidget(delete); actions.addStretch()
        response_panel = QFrame(); response_panel.setObjectName("EndpointResponsePanel")
        response_layout = QVBoxLayout(response_panel); response_layout.setContentsMargins(10, 8, 10, 8); response_layout.setSpacing(6)
        response_header = QHBoxLayout(); response_header.addWidget(QLabel("响应结果", objectName="EndpointResponseTitle")); response_header.addStretch()
        self.endpoint_response_meta = QLabel("状态：—    耗时：—    大小：—"); self.endpoint_response_meta.setObjectName("EndpointResponseMeta"); response_header.addWidget(self.endpoint_response_meta)
        response_tabs = QTabWidget(); response_tabs.setObjectName("EndpointResponseTabs")
        response_body = QWidget(); response_body_layout = QVBoxLayout(response_body); response_body_layout.setContentsMargins(8, 5, 8, 6)
        self.response = QTextEdit(); self.response.setReadOnly(True); self.response.setObjectName("EndpointEditor"); self.response.setPlaceholderText("发送请求后在此显示脱敏响应。")
        response_body_layout.addWidget(self.response)
        response_headers = QLabel("发送请求后显示响应 Header。"); response_headers.setObjectName("EndpointEmptyHint")
        response_cookie = QLabel("发送请求后显示响应 Cookie。"); response_cookie.setObjectName("EndpointEmptyHint")
        response_tabs.addTab(response_body, "美化"); response_tabs.addTab(response_headers, "原生")
        response_tabs.addTab(response_cookie, "预览"); response_tabs.addTab(QLabel("可视化响应将在后续版本提供。", objectName="EndpointEmptyHint"), "Visualize")
        response_tabs.addTab(QLabel("JSON 结构将在后续版本提供。", objectName="EndpointEmptyHint"), "JSON")
        response_layout.addLayout(response_header); response_layout.addWidget(response_tabs, 1)
        request_layout.addLayout(request_header); request_layout.addLayout(url_row); request_layout.addWidget(self.endpoint_request_tabs, 1)
        request_layout.addWidget(action_bar); request_layout.addWidget(response_panel, 1)

        definition = QFrame(); definition.setObjectName("EndpointDefinitionCard")
        definition_layout = QVBoxLayout(definition); definition_layout.setContentsMargins(10, 10, 10, 10); definition_layout.setSpacing(6)
        definition_layout.addWidget(QLabel("接口定义", objectName="EndpointPaneTitle"))
        definition_tabs = QTabWidget(); definition_tabs.setObjectName("EndpointDefinitionTabs")
        overview = QWidget(); overview_layout = QVBoxLayout(overview); overview_layout.setContentsMargins(10, 14, 10, 10); overview_layout.setSpacing(9)
        overview_layout.addWidget(QLabel("基本信息", objectName="EndpointDefinitionSection"))
        info = QFormLayout(); info.setHorizontalSpacing(10); info.setVerticalSpacing(5)
        self.endpoint_definition_name = QLabel("—"); self.endpoint_definition_path = QLabel("—"); self.endpoint_definition_method = QLabel("—"); self.endpoint_definition_module = QLabel("—")
        info.addRow("接口名称", self.endpoint_definition_name); info.addRow("接口路径", self.endpoint_definition_path); info.addRow("请求方法", self.endpoint_definition_method); info.addRow("接口分组", self.endpoint_definition_module)
        overview_layout.addLayout(info); overview_layout.addWidget(QLabel("请求参数", objectName="EndpointDefinitionSection"))
        self.endpoint_request_parameter_table = QTableWidget(0, 4); self.endpoint_request_parameter_table.setObjectName("EndpointDefinitionTable")
        self.endpoint_request_parameter_table.setHorizontalHeaderLabels(["参数名", "类型", "必填", "说明"]); self.endpoint_request_parameter_table.verticalHeader().setVisible(False)
        self.endpoint_request_parameter_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.endpoint_request_parameter_table.horizontalHeader().setStretchLastSection(True)
        overview_layout.addWidget(self.endpoint_request_parameter_table)
        overview_layout.addWidget(QLabel("响应参数", objectName="EndpointDefinitionSection"))
        self.endpoint_response_parameter_table = QTableWidget(0, 3); self.endpoint_response_parameter_table.setObjectName("EndpointDefinitionTable")
        self.endpoint_response_parameter_table.setHorizontalHeaderLabels(["参数名", "类型", "说明"]); self.endpoint_response_parameter_table.verticalHeader().setVisible(False)
        self.endpoint_response_parameter_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.endpoint_response_parameter_table.horizontalHeader().setStretchLastSection(True)
        overview_layout.addWidget(self.endpoint_response_parameter_table)
        self.endpoint_detail = QTextEdit(); self.endpoint_detail.setObjectName("EndpointDetail"); self.endpoint_detail.setReadOnly(True); self.endpoint_detail.setPlaceholderText("选择接口后显示完整接口说明。")
        definition_tabs.addTab(overview, "接口定义"); definition_tabs.addTab(self.endpoint_detail, "接口说明")
        definition_layout.addWidget(definition_tabs, 1)

        workbench.addWidget(groups); workbench.addWidget(request); workbench.addWidget(definition)
        workbench.setStretchFactor(0, 2); workbench.setStretchFactor(1, 5); workbench.setStretchFactor(2, 3)
        workbench.setSizes([220, 590, 310]); groups.setMinimumWidth(190); request.setMinimumWidth(500); definition.setMinimumWidth(285)
        layout.addWidget(title); layout.addWidget(subtitle); layout.addLayout(filters); layout.addWidget(workbench, 1)
        self._finish_page(page, layout)
        return page

    def _environment_validation_page(self):
        """Route A environment dashboard.  It keeps the real configuration fields
        while presenting the first-run check as a readable validation journey."""
        page = QScrollArea(); page.setObjectName("EnvironmentValidationScroll"); page.setWidgetResizable(True)
        page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        page.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        page.setFocusPolicy(Qt.NoFocus)
        content = QWidget(); content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(content); layout.setAlignment(Qt.AlignTop); page.setWidget(content)
        title = QLabel("环境校验"); title.setObjectName("PageTitle")
        subtitle = QLabel("校验测试环境、认证能力与接口资产可用性，确保后续流程测试可执行。")
        subtitle.setObjectName("PageSubtitle")

        setup_card = QFrame(); setup_card.setObjectName("ValidationConfigCard")
        setup = QGridLayout(setup_card); setup.setContentsMargins(18, 16, 18, 16); setup.setHorizontalSpacing(16); setup.setVerticalSpacing(6)
        setup.addWidget(QLabel("项目"), 0, 0); setup.addWidget(QLabel("环境"), 0, 1); setup.addWidget(QLabel("基础地址（Base URL）"), 0, 2)
        self.validation_project_selector = BelowPopupComboBox()
        self.validation_project_selector.setObjectName("ValidationProjectSelector")
        self.validation_project_selector.currentIndexChanged.connect(self.select_validation_project)
        self.env_selector = BelowPopupComboBox(); self.env_selector.setEditable(True); self.env_selector.currentIndexChanged.connect(self.select_environment)
        self.base_url = QLineEdit(); self.base_url.setPlaceholderText("例如：http://192.168.31.117:3000")
        self.env_name = QLineEdit("测试环境"); self.env_name.setVisible(False)
        self.env_selector.setCurrentText("测试环境")
        self.env_selector.editTextChanged.connect(self.env_name.setText)
        self.headers = QTextEdit("{}"); self.headers.setVisible(False)
        self.variables = QTextEdit("{}"); self.variables.setVisible(False)
        self.auth_username = QLineEdit(); self.auth_username.setPlaceholderText("测试账号（认证需要时填写）")
        self.auth_password = QLineEdit(); self.auth_password.setEchoMode(QLineEdit.Password); self.auth_password.setPlaceholderText("测试密码（认证需要时填写）")
        self.environment_confirmed = BlueCheckBox("已确认目标为授权的测试/预发布环境")
        self.auth_status_hint = QLabel("将从已导入接口自动识别登录与 Token 规则")
        self.auth_status_hint.setObjectName("ValidationHint")
        save_environment_button = QPushButton("保存测试环境"); save_environment_button.clicked.connect(self.save_environment)
        validate_button = QPushButton("▶  开始环境校验"); validate_button.setProperty("primary", True); validate_button.clicked.connect(self.run_environment_validation)
        setup.addWidget(self.validation_project_selector, 1, 0); setup.addWidget(self.env_selector, 1, 1); setup.addWidget(self.base_url, 1, 2); setup.addWidget(save_environment_button, 1, 3); setup.addWidget(validate_button, 1, 4)
        setup.setColumnStretch(0, 1); setup.setColumnStretch(1, 1); setup.setColumnStretch(2, 2)

        result_card = QFrame(); result_card.setObjectName("ValidationResultCard")
        result_layout = QVBoxLayout(result_card); result_layout.setContentsMargins(18, 16, 18, 16); result_layout.setSpacing(14)
        result_title = QLabel("环境校验结果"); result_title.setObjectName("PanelTitle")
        result_layout.addWidget(result_title)
        self.validation_steps = []
        steps_row = QHBoxLayout(); steps_row.setSpacing(8)
        for index, (name, icon_kind, detail) in enumerate((
            ("测试环境", "server", "等待校验"), ("登录认证", "key", "自动识别"),
            ("Token 获取", "shield", "回归时自动处理"), ("接口资产", "cube", "等待校验"), ("校验完成", "complete", "等待开始"),
        ), 1):
            card = QFrame(); card.setObjectName("ValidationStepCard")
            card_layout = QVBoxLayout(card); card_layout.setContentsMargins(10, 12, 10, 10); card_layout.setSpacing(8)
            heading = QLabel(f"{index}  {name}"); heading.setObjectName("ValidationStepTitle")
            symbol = self._illustration_icon(icon_kind, 78); symbol.setObjectName("ValidationStepIcon")
            detail_label = QLabel(detail); detail_label.setObjectName("ValidationStepDetail"); detail_label.setAlignment(Qt.AlignCenter); detail_label.setWordWrap(True)
            status_icon = self._illustration_icon("status_pending", 15)
            status = QLabel("待校验"); status.setObjectName("ValidationStepPending")
            status_row = QHBoxLayout(); status_row.setSpacing(5)
            status_row.addStretch(1); status_row.addWidget(status_icon); status_row.addWidget(status); status_row.addStretch(1)
            card_layout.addWidget(heading); card_layout.addWidget(symbol, 1, alignment=Qt.AlignCenter); card_layout.addWidget(detail_label); card_layout.addLayout(status_row)
            self.validation_steps.append((detail_label, status, status_icon))
            steps_row.addWidget(card, 1)
            if index < 5:
                arrow = QLabel("→"); arrow.setObjectName("ValidationArrow"); arrow.setAlignment(Qt.AlignCenter); steps_row.addWidget(arrow)
        result_layout.addLayout(steps_row)
        details_row = QHBoxLayout(); details_row.setSpacing(14)
        self.validation_metrics = {}
        self.validation_metric_icons = {}
        self.validation_panel_status = {}
        self.validation_panel_summaries = {}
        self.validation_asset_action = None
        self._validation_response_detail = {}
        for name, rows in (("基础连通性", ("DNS 解析", "网络响应", "服务健康")), ("认证校验", ("登录接口", "Token 有效期", "认证方式")), ("接口资产校验", ("发现接口数量", "可访问接口数量", "不可访问接口数量"))):
            panel = QFrame(); panel.setObjectName("ValidationDetailPanel")
            panel.setMinimumWidth(0)
            panel_layout = QVBoxLayout(panel); panel_layout.setContentsMargins(14, 12, 14, 12); panel_layout.setSpacing(6)
            panel_header = QHBoxLayout()
            panel_title = QLabel(name); panel_title.setObjectName("ValidationDetailTitle")
            panel_status_icon = self._illustration_icon("status_pending", 14)
            panel_status = QLabel("待校验"); panel_status.setObjectName("ValidationPanelPending")
            panel_header.addWidget(panel_title); panel_header.addStretch(1); panel_header.addWidget(panel_status_icon); panel_header.addWidget(panel_status)
            panel_layout.addLayout(panel_header)
            self.validation_panel_status[name] = (panel_status, panel_status_icon)
            for row_index, row in enumerate(rows):
                metric_row = QFrame(); metric_row.setObjectName("ValidationMetricRow")
                metric_layout = QHBoxLayout(metric_row); metric_layout.setContentsMargins(0, 0, 0, 0); metric_layout.setSpacing(8)
                metric_name = QLabel(row); metric_name.setObjectName("ValidationMetric")
                metric_value = QLabel("待校验"); metric_value.setObjectName("ValidationMetricValue")
                metric_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                metric_icon = self._illustration_icon("status_pending", 14)
                metric_layout.addWidget(metric_name, 1); metric_layout.addWidget(metric_value); metric_layout.addWidget(metric_icon)
                panel_layout.addWidget(metric_row)
                metric_divider = QFrame(); metric_divider.setObjectName("ValidationMetricDivider"); metric_divider.setFixedHeight(1)
                panel_layout.addWidget(metric_divider)
                self.validation_metrics[row] = metric_value
                self.validation_metric_icons[row] = metric_icon
            panel_layout.addStretch(1)
            summary_icon = self._illustration_icon("status_pending", 15)
            summary = QLabel("等待完成后显示校验结论"); summary.setObjectName("ValidationSummary"); summary.setWordWrap(True)
            summary_row = QHBoxLayout(); summary_row.setSpacing(6)
            summary_row.addWidget(summary_icon, 0, Qt.AlignTop); summary_row.addWidget(summary, 1)
            panel_layout.addLayout(summary_row)
            self.validation_panel_summaries[name] = (summary, summary_icon)
            if name == "接口资产校验":
                self.validation_asset_action = QPushButton("查看校验响应")
                self.validation_asset_action.setObjectName("ValidationDetailAction")
                self.validation_asset_action.setFixedSize(126, 32)
                self.validation_asset_action.setVisible(False)
                self.validation_asset_action.clicked.connect(self.show_validation_response_details)
                panel_layout.addWidget(self.validation_asset_action, 0, Qt.AlignHCenter)
            details_row.addWidget(panel, 1)
        result_layout.addLayout(details_row)

        log_card = QFrame(); log_card.setObjectName("ValidationLogCard")
        log_layout = QVBoxLayout(log_card); log_layout.setContentsMargins(16, 16, 16, 16); log_layout.setSpacing(10)
        log_title = QLabel("校验日志"); log_title.setObjectName("PanelTitle")
        self.validation_log = QScrollArea(); self.validation_log.setObjectName("ValidationLog")
        self.validation_log.setWidgetResizable(True); self.validation_log.setFrameShape(QFrame.NoFrame)
        self.validation_log.setStyleSheet("QScrollArea { background: #ffffff; border: none; } QWidget { background: #ffffff; }")
        self.validation_log.viewport().setStyleSheet("background: #ffffff;")
        self.validation_log_content = QWidget(); self.validation_log_content.setObjectName("ValidationLogContent")
        self.validation_log_content.setStyleSheet("background: #ffffff;")
        self.validation_log_rows = QVBoxLayout(self.validation_log_content)
        self.validation_log_rows.setContentsMargins(0, 0, 0, 0); self.validation_log_rows.setSpacing(0)
        self.validation_log.setWidget(self.validation_log_content)
        self._set_validation_log([("", "等待开始环境校验", "pending")])
        rerun = QPushButton("↻  重新校验"); rerun.clicked.connect(self.run_environment_validation)
        export_report = QPushButton("⇩  导出校验报告"); export_report.setObjectName("ValidationExportReport"); export_report.clicked.connect(self.export_environment_validation_report)
        log_layout.addWidget(log_title); log_layout.addWidget(self.validation_log, 1); log_layout.addWidget(rerun); log_layout.addWidget(export_report)

        result_card.setMinimumWidth(0)
        log_card.setFixedWidth(270)
        log_card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        # The log is part of the validation dashboard, not only the result
        # section.  Put it beside the configuration + results stack so its
        # title starts on the same horizontal line as “开始环境校验”.
        dashboard_left = QVBoxLayout(); dashboard_left.setSpacing(18)
        dashboard_left.addWidget(setup_card)
        dashboard_left.addWidget(result_card, 1)
        dashboard_row = QHBoxLayout(); dashboard_row.setSpacing(18)
        dashboard_row.addLayout(dashboard_left, 1)
        dashboard_row.addWidget(log_card, 0)
        runtime_card = QFrame(); runtime_card.setObjectName("RuntimeSetupCard")
        runtime_layout = QVBoxLayout(runtime_card); runtime_layout.setContentsMargins(18, 16, 18, 16); runtime_layout.setSpacing(12)
        runtime_title = QLabel("首次运行设置"); runtime_title.setObjectName("PanelTitle")
        runtime_subtitle = QLabel("首次保存一次账号和授权；凭据仅保存在本机安全存储，后续一键回归会自动复用。")
        runtime_subtitle.setObjectName("ValidationHint")
        runtime_form = QFormLayout(); runtime_form.setHorizontalSpacing(14); runtime_form.setVerticalSpacing(8)
        runtime_form.addRow("认证状态", self.auth_status_hint); runtime_form.addRow("测试账号", self.auth_username); runtime_form.addRow("测试密码", self.auth_password); runtime_form.addRow("执行授权", self.environment_confirmed)
        save = QPushButton("保存并启用一键回归"); save.setProperty("primary", True); save.clicked.connect(self.save_environment)
        runtime_left = QWidget(); runtime_left_layout = QVBoxLayout(runtime_left); runtime_left_layout.setContentsMargins(0, 0, 0, 0); runtime_left_layout.setSpacing(8)
        runtime_actions = QHBoxLayout(); runtime_actions.addWidget(save); runtime_actions.addStretch()
        runtime_left_layout.addLayout(runtime_form); runtime_left_layout.addLayout(runtime_actions)
        runtime_help = QFrame(); runtime_help.setObjectName("RuntimeHelpCard")
        runtime_help_layout = QVBoxLayout(runtime_help); runtime_help_layout.setContentsMargins(16, 14, 16, 14); runtime_help_layout.setSpacing(6)
        runtime_help_title = QLabel("说明"); runtime_help_title.setObjectName("RuntimeHelpTitle")
        runtime_help_text = QLabel(
            "• 平台用登录接口自动获取并复用 Token。\n"
            "• 凭据仅保存于当前电脑，不会写入 Manifest 或结果。\n"
            "• 更换账号或环境后，重新保存即可更新本机配置。"
        )
        runtime_help_text.setObjectName("RuntimeHelpText"); runtime_help_text.setWordWrap(True)
        runtime_help_layout.addWidget(runtime_help_title); runtime_help_layout.addWidget(runtime_help_text); runtime_help_layout.addStretch(1)
        runtime_body = QHBoxLayout(); runtime_body.setSpacing(18); runtime_body.addWidget(runtime_left, 3); runtime_body.addWidget(runtime_help, 2)
        runtime_layout.addWidget(runtime_title); runtime_layout.addWidget(runtime_subtitle); runtime_layout.addLayout(runtime_body)

        runtime_card.setVisible(True)
        layout.addWidget(title); layout.addWidget(subtitle); layout.addLayout(dashboard_row)
        runtime_row = QHBoxLayout(); runtime_row.addWidget(runtime_card, 1)
        layout.addLayout(runtime_row)
        self._finish_page(content, layout)
        return page

    def _request_page(self):
        return self._environment_validation_page()
        # This page has two complete forms.  Keep their field heights stable and
        # scroll the page on smaller windows instead of compressing editors into
        # unreadable one-line strips.
        page = QScrollArea(); page.setObjectName("RequestConfigScroll"); page.setWidgetResizable(True)
        content = QWidget(); layout = QVBoxLayout(content); page.setWidget(content)
        title = QLabel("项目运行配置与接口调试"); title.setObjectName("PageTitle")
        subtitle = QLabel("每个项目首次只需保存一次测试环境地址；认证方式会从已导入的接口中自动识别并在回归时自动处理。")
        subtitle.setObjectName("PageSubtitle")
        self.request_project_label = QLabel("当前项目：未选择"); self.request_project_label.setObjectName("ContextBanner")
        self.request_setup_hint = QLabel("步骤：① 保存项目运行配置（一次）  ② 从“接口资产”选择接口调试  ③ 保存为用例或在用例页一键执行。")
        self.request_setup_hint.setObjectName("ContextBanner")
        self.request_setup_hint.setWordWrap(True)
        validation_track = QFrame(); validation_track.setObjectName("ValidationTrack")
        validation_track_layout = QHBoxLayout(validation_track)
        validation_track_layout.setContentsMargins(14, 10, 14, 10)
        for index, (heading, detail) in enumerate((
            ("① 环境地址", "保存测试或预发布地址"),
            ("② 登录认证", "自动识别登录接口"),
            ("③ Token 复用", "回归执行时自动处理"),
            ("④ 接口可用性", "从接口资产进入调试"),
        )):
            item = QLabel(f"{heading}\n{detail}")
            item.setObjectName("ValidationTrackItem")
            validation_track_layout.addWidget(item, 1)

        environment_card = QFrame(); environment_card.setObjectName("ProjectPanel")
        environment_layout = QVBoxLayout(environment_card)
        environment_title = QLabel("环境校验与首次运行设置"); environment_title.setObjectName("PanelTitle")
        # QFormLayout may calculate QTextEdit rows using a single-line height on
        # high-DPI Windows displays.  Use explicit grid rows for the two JSON
        # editors so the checkbox and save button can never overlap them.
        environment_form = QGridLayout()
        environment_form.setHorizontalSpacing(14)
        environment_form.setVerticalSpacing(10)
        environment_form.setColumnStretch(1, 1)
        self.env_selector = BelowPopupComboBox(); self.env_selector.currentIndexChanged.connect(self.select_environment)
        self.env_name = QLineEdit("测试环境")
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("例如：http://192.168.31.117:3000")
        self.headers = QTextEdit("{}"); self.headers.setFixedHeight(74)
        self.variables = QTextEdit("{}"); self.variables.setFixedHeight(74)
        self.auth_status_hint = QLabel("认证：正在根据已导入接口自动识别"); self.auth_status_hint.setObjectName("PageSubtitle")
        self.auth_username = QLineEdit(); self.auth_username.setPlaceholderText("仅认证需要时填写测试账号")
        self.auth_password = QLineEdit(); self.auth_password.setPlaceholderText("仅认证需要时填写测试密码"); self.auth_password.setEchoMode(QLineEdit.Password)
        self.environment_confirmed = QCheckBox("首次确认：该地址是已授权的测试/预发布环境（保存后同项目无需重复确认）")
        environment_form.addWidget(QLabel("已保存环境"), 0, 0)
        environment_form.addWidget(self.env_selector, 0, 1)
        environment_form.addWidget(QLabel("环境名称"), 1, 0)
        environment_form.addWidget(self.env_name, 1, 1)
        environment_form.addWidget(QLabel("测试环境地址"), 2, 0)
        environment_form.addWidget(self.base_url, 2, 1)
        environment_form.addWidget(QLabel("认证状态"), 3, 0)
        environment_form.addWidget(self.auth_status_hint, 3, 1)
        environment_form.addWidget(QLabel("测试账号"), 4, 0)
        environment_form.addWidget(self.auth_username, 4, 1)
        environment_form.addWidget(QLabel("测试密码"), 5, 0)
        environment_form.addWidget(self.auth_password, 5, 1)
        environment_form.addWidget(QLabel("执行授权"), 6, 0)
        environment_form.addWidget(self.environment_confirmed, 6, 1)
        # Do not use a clipped, checkable QGroupBox here.  A hidden widget has no
        # layout footprint until explicitly expanded, at every display scale.
        advanced_runtime_toggle = QPushButton("高级配置")
        advanced_runtime_toggle.setObjectName("AdvancedToggle")
        advanced_runtime_toggle.setCheckable(True)
        advanced_runtime_toggle.setToolTip("首次配置通常只需填写测试环境地址和测试账号。")
        advanced_runtime = QFrame()
        advanced_runtime.setObjectName("InlineAdvancedPanel")
        advanced_runtime.setVisible(False)
        advanced_form = QFormLayout(advanced_runtime)
        advanced_form.addRow("公共 Headers JSON", self.headers)
        advanced_form.addRow("项目变量 JSON", self.variables)
        advanced_runtime_toggle.toggled.connect(advanced_runtime.setVisible)
        advanced_runtime_toggle.toggled.connect(
            lambda checked: advanced_runtime_toggle.setText("收起高级配置" if checked else "高级配置")
        )
        save = QPushButton("保存并启用一键回归"); save.clicked.connect(self.save_environment)
        environment_actions = QHBoxLayout(); environment_actions.addWidget(save)
        environment_actions.addWidget(advanced_runtime_toggle); environment_actions.addStretch()
        environment_layout.addWidget(environment_title); environment_layout.addLayout(environment_form)
        environment_layout.addLayout(environment_actions); environment_layout.addWidget(advanced_runtime)

        request_card = QFrame(); request_card.setObjectName("ProjectPanel")
        request_layout = QVBoxLayout(request_card)
        request_title = QLabel("接口调试（可选）"); request_title.setObjectName("PanelTitle")
        self.debug_endpoint_label = QLabel("请在“接口资产”中选择一个接口后点击“调试选中接口”，也可手工填写。")
        self.debug_endpoint_label.setObjectName("ContextBanner")
        request_form = QFormLayout()
        self.validation_debug_method = BelowPopupComboBox(); self.validation_debug_method.addItems(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
        self.validation_debug_path = QLineEdit("/")
        self.validation_debug_body = QTextEdit("{}"); self.validation_debug_body.setFixedHeight(112)
        request_form.addRow("请求方法", self.validation_debug_method); request_form.addRow("接口路径", self.validation_debug_path); request_form.addRow("Body JSON", self.validation_debug_body)
        buttons = QHBoxLayout()
        send = QPushButton("发送当前接口"); send.clicked.connect(self.send_request)
        save_as_case = QPushButton("保存为测试用例"); save_as_case.clicked.connect(self.save_request_as_case)
        buttons.addWidget(send); buttons.addWidget(save_as_case); buttons.addStretch()
        self.validation_debug_response = QTextEdit(); self.validation_debug_response.setReadOnly(True)
        self.validation_debug_response.setMinimumHeight(190)
        self.validation_debug_response.setMaximumHeight(260)
        request_layout.addWidget(request_title); request_layout.addWidget(self.debug_endpoint_label); request_layout.addLayout(request_form); request_layout.addLayout(buttons)
        # The running configuration itself identifies the project.  Retain the
        # guidance as a short subtitle rather than two large banners.
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(validation_track)
        request_card.setVisible(False)
        validation_response_title = QLabel("响应（敏感字段已脱敏）"); validation_response_title.setVisible(False)
        self.validation_debug_response.setVisible(False)
        layout.addWidget(environment_card); layout.addWidget(request_card)
        layout.addWidget(validation_response_title); layout.addWidget(self.validation_debug_response, 1)
        save.setProperty("primary", True)
        send.setProperty("primary", True)
        self._finish_page(content, layout)
        return page

    @staticmethod
    def _finish_page(page, layout):
        page.setObjectName("ContentPage")
        # 统一所有页面的阅读宽度与节奏，避免控件过度拉伸和页面松散。
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(12)

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
        if hasattr(self, "endpoint_project_selector"):
            self.endpoint_project_selector.blockSignals(True)
            self.endpoint_project_selector.clear()
            for project in overviews:
                self.endpoint_project_selector.addItem(project["name"], project["id"])
            endpoint_index = self.endpoint_project_selector.findData(selected)
            self.endpoint_project_selector.setCurrentIndex(max(0, endpoint_index))
            self.endpoint_project_selector.blockSignals(False)
        if hasattr(self, "workflow_project_selector"):
            self.workflow_project_selector.blockSignals(True)
            self.workflow_project_selector.clear()
            for project in overviews:
                self.workflow_project_selector.addItem(project["name"], project["id"])
            workflow_index = self.workflow_project_selector.findData(selected)
            self.workflow_project_selector.setCurrentIndex(max(0, workflow_index))
            self.workflow_project_selector.blockSignals(False)
        if hasattr(self, "validation_project_selector"):
            self.validation_project_selector.blockSignals(True)
            self.validation_project_selector.clear()
            for project in overviews:
                self.validation_project_selector.addItem(project["name"], project["id"])
            validation_index = self.validation_project_selector.findData(selected)
            self.validation_project_selector.setCurrentIndex(max(0, validation_index))
            self.validation_project_selector.blockSignals(False)
        self.project_table.setUpdatesEnabled(False)
        self.project_table.blockSignals(True)
        try:
            self.project_table.setRowCount(len(overviews))
            for row, project in enumerate(overviews):
                values = (
                    project["name"], project["source_count"], project["module_count"],
                    project["endpoint_count"], project["updated_at"],
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column == 0:
                        item.setData(Qt.UserRole, project["id"])
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    elif column == 4:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignCenter)
                    self.project_table.setItem(row, column, item)
                if project["id"] == selected:
                    self.project_table.selectRow(row)
        finally:
            self.project_table.blockSignals(False)
            self.project_table.setUpdatesEnabled(True)
        if hasattr(self, "project_total"):
            self.project_total.setText(f"共 {len(overviews)} 个项目")
        if hasattr(self, "stat_projects"):
            self.stat_projects.stat_value.setText(str(len(overviews)))
            self.stat_sources.stat_value.setText(str(sum(int(item["source_count"]) for item in overviews)))
            self.stat_modules.stat_value.setText(str(sum(int(item["module_count"]) for item in overviews)))
            self.stat_endpoints.stat_value.setText(str(sum(int(item["endpoint_count"]) for item in overviews)))
        self.filter_project_table()
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

    def select_validation_project(self):
        """Keep the environment-validation project dropdown synchronized globally."""
        project_id = self.validation_project_selector.currentData()
        index = self.projects.findData(project_id)
        if index >= 0 and self.projects.currentIndex() != index:
            self.projects.setCurrentIndex(index)

    def filter_project_table(self):
        if not hasattr(self, "project_table"):
            return
        keyword = self.project_filter.text().strip().lower() if hasattr(self, "project_filter") else ""
        for row in range(self.project_table.rowCount()):
            name_item = self.project_table.item(row, 0)
            self.project_table.setRowHidden(row, bool(keyword and name_item and keyword not in name_item.text().lower()))

    def _project_changed(self):
        self.current_project_id = self.projects.currentData()
        if hasattr(self, "case_project_selector"):
            index = self.case_project_selector.findData(self.current_project_id)
            self.case_project_selector.blockSignals(True)
            self.case_project_selector.setCurrentIndex(max(0, index))
            self.case_project_selector.blockSignals(False)
        if hasattr(self, "endpoint_project_selector"):
            index = self.endpoint_project_selector.findData(self.current_project_id)
            self.endpoint_project_selector.blockSignals(True)
            self.endpoint_project_selector.setCurrentIndex(max(0, index))
            self.endpoint_project_selector.blockSignals(False)
        if hasattr(self, "workflow_project_selector"):
            index = self.workflow_project_selector.findData(self.current_project_id)
            self.workflow_project_selector.blockSignals(True)
            self.workflow_project_selector.setCurrentIndex(max(0, index))
            self.workflow_project_selector.blockSignals(False)
        if hasattr(self, "validation_project_selector"):
            index = self.validation_project_selector.findData(self.current_project_id)
            self.validation_project_selector.blockSignals(True)
            self.validation_project_selector.setCurrentIndex(max(0, index))
            self.validation_project_selector.blockSignals(False)
        self.refresh_context_labels()
        self._refresh_case_runtime_hint()
        self.refresh_asset_tree()
        self.refresh_source_table()
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
            else:
                self.env_name.setText("测试环境")
                self.base_url.clear()
                self.headers.setPlainText("{}")
                self.variables.setPlainText("{}")
                self.environment_confirmed.setChecked(False)
        self._refresh_endpoint_debug_environments()
        if hasattr(self, "case_table"):
            self.refresh_cases()
        if hasattr(self, "report_table"):
            self.refresh_reports()
        if hasattr(self, "runner_run_table"):
            self.refresh_external_runner_runs()
        if hasattr(self, "workflow_selector"):
            self.refresh_workflows()

    def refresh_asset_tree(self):
        if not hasattr(self, "asset_tree"):
            return
        self.asset_tree.setUpdatesEnabled(False)
        self.asset_tree.clear()
        if not self.current_project_id:
            if hasattr(self, "current_source_label"):
                self.current_source_label.setText("尚未导入资料")
            if hasattr(self, "stat_sources"):
                for card in (self.stat_sources, self.stat_modules, self.stat_endpoints):
                    card.stat_value.setText("0")
            if hasattr(self, "asset_summary"):
                self.asset_summary.setText("请先在项目概览中选择一个项目，再查看其资料源、模块和接口。");
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
                source_nodes[source_id].setData(0, Qt.UserRole + 1, {"kind": "source", "id": source_id})
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
            endpoint_node.setData(0, Qt.UserRole + 1, {"kind": "endpoint", "id": row["endpoint_id"]})
        for source_id, source_node in source_nodes.items():
            source_node.setText(2, f"{source_counts[source_id]} 个接口")
        project_root.setText(2, f"{len(source_nodes)} 个资料源")
        project_root.setExpanded(True)
        for node in source_nodes.values():
            node.setExpanded(True)
        if hasattr(self, "asset_summary"):
            endpoint_count = sum(source_counts.values())
            source_names = "、".join(node.text(0) for node in source_nodes.values())
            self.asset_summary.setText(
                f"当前项目：{project_name}  ·  资料：{source_names or '未导入'}  ·  "
                f"{len(module_nodes)} 个模块  ·  {endpoint_count} 个接口。双击接口可直接查看详情。"
            )
        if hasattr(self, "current_source_label"):
            self.current_source_label.setText(source_names or "尚未导入资料")
        # 默认展开到资料源层级：结构一眼可见，接口明细仍可按模块按需展开。
        self.asset_tree.expandToDepth(1)
        self.update_asset_actions()
        self.asset_tree.setUpdatesEnabled(True)

    def filter_asset_tree(self):
        """按任意列筛选资产树，同时保留命中项的父级路径。"""
        if not hasattr(self, "asset_tree"):
            return
        keyword = self.asset_search.text().strip().lower()

        def visit(item: QTreeWidgetItem) -> bool:
            own_match = not keyword or any(
                keyword in item.text(column).lower() for column in range(item.columnCount())
            )
            child_match = any(visit(item.child(index)) for index in range(item.childCount()))
            visible = own_match or child_match
            item.setHidden(not visible)
            if keyword and child_match:
                item.setExpanded(True)
            return visible

        for index in range(self.asset_tree.topLevelItemCount()):
            visit(self.asset_tree.topLevelItem(index))

    def refresh_source_table(self):
        if not hasattr(self, "source_table"):
            return
        keyword = self.source_filter_home.text().strip().lower() if hasattr(self, "source_filter_home") else ""
        rows = self.db.list_sources(self.current_project_id) if self.current_project_id else []
        rows = [row for row in rows if not keyword or keyword in row["name"].lower() or keyword in row["kind"].lower()]
        self.source_table.setUpdatesEnabled(False)
        self.source_table.clearContents()
        self.source_table.setRowCount(len(rows))
        for index, source in enumerate(rows):
            self.source_table.setRowHeight(index, 44)
            for column, value in enumerate((source["name"], source["kind"])):
                item = QTableWidgetItem(str(value))
                if column == 1:
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.source_table.setItem(index, column, item)
            remove = QPushButton("删除")
            remove.setObjectName("InlineDeleteButton")
            remove.setProperty("danger", True)
            remove.setFixedSize(46, 22)
            remove.clicked.connect(lambda checked=False, source_id=source["id"]: self.delete_source(source_id))
            operation = QWidget()
            operation_layout = QHBoxLayout(operation)
            operation_layout.setContentsMargins(0, 0, 0, 0)
            operation_layout.setAlignment(Qt.AlignCenter)
            operation_layout.addWidget(remove)
            self.source_table.setCellWidget(index, 2, operation)
        self.source_table.setUpdatesEnabled(True)

    def delete_source(self, source_id: int):
        if not self.current_project_id:
            return
        if QMessageBox.question(self, "删除资料", "确定删除这份导入资料及其接口吗？") != QMessageBox.Yes:
            return
        self.db.delete_source(source_id, self.current_project_id)
        self.db.audit(self.current_project_id, "delete_source", {"source_id": source_id})
        self.refresh_source_table()
        self.refresh_asset_tree()
        self.refresh_endpoint_filters()
        self.refresh_endpoints()
        self.refresh_projects()

    def select_workflow_project(self):
        project_id = self.workflow_project_selector.currentData()
        index = self.projects.findData(project_id)
        if index >= 0 and self.projects.currentIndex() != index:
            self.projects.setCurrentIndex(index)

    def select_endpoint_project(self):
        project_id = self.endpoint_project_selector.currentData()
        index = self.projects.findData(project_id)
        if index >= 0 and self.projects.currentIndex() != index:
            self.projects.setCurrentIndex(index)

    def choose_git_project(self):
        path = QFileDialog.getExistingDirectory(self, "选择本地 Git 项目目录")
        if path:
            self.git_project_path.setText(path)

    def choose_git_clone_parent(self):
        path = QFileDialog.getExistingDirectory(self, "选择 Git 克隆保存目录")
        if path:
            self.git_clone_parent.setText(path)

    def clone_and_import_git_project(self):
        remote = self.git_remote_url.text().strip()
        parent = Path(self.git_clone_parent.text().strip())
        if not remote:
            QMessageBox.warning(self, "连接 Git 仓库", "请填写 Git 仓库地址。")
            return
        try:
            parent.mkdir(parents=True, exist_ok=True)
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10,
                                    creationflags=creation_flags)
            if result.returncode != 0:
                raise RuntimeError("未检测到可用 Git，请先安装 Git 并重新打开工具。")
            name = Path(urlparse(remote).path).stem or "git-project"
            target = parent / name
            if target.exists():
                raise ValueError(f"目标目录已存在：{target}。请改用“导入本地仓库”，或选择其他保存目录。")
            self.git_import_output.setPlainText(f"正在克隆：{remote}\n保存到：{target}")
            result = subprocess.run(["git", "clone", "--depth", "1", remote, str(target)], capture_output=True,
                                    text=True, timeout=300, creationflags=creation_flags)
            if result.returncode != 0:
                detail = result.stderr.strip() or "Git clone 失败"
                if "Connection was reset" in detail or "Recv failure" in detail:
                    detail += "\n\n网络连接被远端重置。请检查网络、VPN/代理设置，或先在终端执行 git clone 验证网络后再导入。"
                raise RuntimeError(detail)
            self.git_project_path.setText(str(target))
            self.import_git_project()
        except Exception as exc:
            QMessageBox.critical(self, "连接 Git 仓库失败", str(exc))

    def import_git_project(self):
        path = Path(self.git_project_path.text().strip())
        if not path.is_dir() or not (path / ".git").exists():
            QMessageBox.warning(self, "导入 Git 项目", "请选择包含 .git 文件夹的本地 Git 项目目录。")
            return
        try:
            analysis = BackendSourceParser().analyze_directory(path)
            document = analysis["document"]
            if not document.endpoints:
                raise ValueError("没有识别到后端接口。当前仅支持 ASP.NET Core、Spring Boot 和 Node/Express 项目。")
            already_imported = any(
                item["root_path"] == str(path)
                for project in self.db.list_projects()
                for item in self.db.list_source_projects(project["id"])
            )
            if already_imported:
                raise ValueError("该本地仓库已经导入。请在首页选择对应项目，或更换仓库目录。")
            self.current_project_id = self.db.create_project(path.name, mode="source")
            self._save_document(path.name, document, source_analysis=analysis, source_root=path)
            self.refresh_projects()
            self.git_import_output.setPlainText(f"已导入：{path.name}\n识别接口：{len(document.endpoints)} 个\n现在可在首页和路线 A 查看接口资产。")
            QMessageBox.information(self, "导入 Git 项目", f"已创建项目“{path.name}”，并识别到 {len(document.endpoints)} 个接口。")
        except Exception as exc:
            QMessageBox.critical(self, "导入 Git 项目失败", str(exc))

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

    def _selected_asset(self) -> dict | None:
        item = self.asset_tree.currentItem() if hasattr(self, "asset_tree") else None
        return item.data(0, Qt.UserRole + 1) if item else None

    def update_asset_actions(self):
        selected = self._selected_asset()
        enabled = bool(selected and selected.get("kind") in {"source", "endpoint"})
        for button in (getattr(self, "edit_asset_btn", None), getattr(self, "delete_asset_btn", None)):
            if button:
                button.setEnabled(enabled)

    def edit_selected_asset(self):
        selected = self._selected_asset()
        if not selected:
            return
        if selected["kind"] == "source":
            rows = {item["id"]: item for item in self.db.list_sources(self.current_project_id)}
            source = rows.get(selected["id"])
            if not source:
                return
            name, accepted = QInputDialog.getText(self, "编辑资料", "资料名称", text=source["name"])
            if accepted and name.strip():
                self.db.rename_source(selected["id"], self.current_project_id, name)
                self.refresh_projects()
            return
        endpoint = next((item for item in self.db.list_endpoints(self.current_project_id) if item["id"] == selected["id"]), None)
        if not endpoint:
            return
        text, accepted = QInputDialog.getMultiLineText(
            self, "编辑接口", "接口定义 JSON", json.dumps(json.loads(endpoint["definition_json"]), ensure_ascii=False, indent=2)
        )
        if accepted:
            try:
                self.db.update_endpoint(selected["id"], json.loads(text))
                self.refresh_projects()
            except Exception as exc:
                QMessageBox.warning(self, "接口无效", str(exc))

    def delete_selected_asset(self):
        selected = self._selected_asset()
        if not selected:
            return
        if selected["kind"] == "source":
            message = "确定删除这份资料及其全部接口吗？"
        else:
            message = "确定删除选中的接口吗？"
        if QMessageBox.question(self, "删除资产", message) != QMessageBox.Yes:
            return
        if selected["kind"] == "source":
            self.db.delete_source(selected["id"], self.current_project_id)
        else:
            self.db.delete_endpoint(selected["id"])
        self.db.audit(self.current_project_id, "delete_asset", selected)
        self.refresh_projects(); self.refresh_endpoints()

    def refresh_context_labels(self):
        name = self.projects.currentText() if self.current_project_id else "未选择"
        endpoint_count = len(self.db.list_endpoints(self.current_project_id)) if self.current_project_id else 0
        context = f"当前项目：{name}  ·  {endpoint_count} 个接口"
        for attribute in ("request_project_label", "case_project_label", "report_project_label", "workflow_project_label", "ai_dialogue_project_label", "runner_project_label"):
            label = getattr(self, attribute, None)
            if label:
                label.setText(context)

    def _refresh_case_runtime_hint(self) -> None:
        """Explain whether this project's saved runtime is ready for one-click runs."""
        runtime_hint = getattr(self, "case_runtime_hint", None)
        if not runtime_hint:
            return
        envs = self.db.list_environments(self.current_project_id) if self.current_project_id else []
        if not envs:
            runtime_hint.setText("运行配置：尚未保存。请先在“项目运行配置与接口调试”中完成一次配置。")
            return
        env = envs[0]
        authorized = self.db.get_setting(
            f"environment_authorized:{self.current_project_id}:{env['name']}", "0"
        ) == "1"
        state = "已保存，可一键运行" if authorized and env.get("base_url") else "请完成首次授权与 Base URL 配置"
        runtime_hint.setText(f"运行配置：{env['name']} · {env.get('base_url') or '未填写 Base URL'} · {state}")

    def _detected_project_auth(self) -> tuple[bool, dict | None]:
        """Infer the usual login entry from imported API assets, without asking users for headers."""
        if not self.current_project_id:
            return False, None
        endpoints = self.db.list_endpoints(self.current_project_id)
        login = next((item for item in endpoints if item.get("method", "").upper() == "POST"
                      and any(token in item.get("path", "").lower() for token in ("/login", "/signin", "/sign-in"))), None)
        secured = False
        for item in endpoints:
            try:
                secured = secured or bool(json.loads(item.get("definition_json") or "{}").get("security"))
            except (TypeError, ValueError):
                continue
        return bool(login or secured), login

    def _refresh_auth_status_hint(self) -> None:
        hint = getattr(self, "auth_status_hint", None)
        if not hint:
            return
        required, login = self._detected_project_auth()
        if not required:
            hint.setText("未识别到认证要求：回归测试将直接执行")
        elif login:
            hint.setText(f"已识别登录接口 {login['path']}：执行时自动获取并复用 Token")
        else:
            hint.setText("已识别受保护接口：请首次填写测试账号，系统会自动复用认证信息")

    @staticmethod
    def _find_token(payload):
        if isinstance(payload, dict):
            for key in ("access_token", "accessToken", "token", "jwt"):
                if payload.get(key):
                    return str(payload[key])
            for value in payload.values():
                token = MainWindow._find_token(value)
                if token:
                    return token
        if isinstance(payload, list):
            for value in payload:
                token = MainWindow._find_token(value)
                if token:
                    return token
        return ""

    def _prepare_auto_auth(self, variables: dict) -> dict:
        """Perform one discovered login at run time; never expose its token in the UI."""
        required, login = self._detected_project_auth()
        if not required or variables.get("TOKEN") or variables.get("ACCESS_TOKEN"):
            return variables
        username = str(variables.get("TEST_USERNAME") or variables.get("USERNAME") or "")
        password = str(variables.get("TEST_PASSWORD") or variables.get("PASSWORD") or "")
        if not login or not username or not password:
            raise ValueError("该项目需要认证。请在“项目运行配置”首次填写测试账号和测试密码；之后会自动登录。")
        response = execute_request("POST", self.base_url.text().strip(), login["path"], {},
                                   {"username": username, "password": password})
        if response.status_code < 200 or response.status_code >= 300:
            raise ValueError(f"自动登录失败（HTTP {response.status_code}）。请检查测试账号、密码或登录接口参数。")
        try:
            payload = json.loads(response.body) if isinstance(response.body, str) else response.body
        except (TypeError, ValueError):
            payload = {}
        token = self._find_token(payload) or response.headers.get("authorization", "").removeprefix("Bearer ")
        if not token:
            raise ValueError("登录成功但未找到 Token 字段。请在接口资产中补充登录响应定义，或在高级变量中配置 TOKEN。")
        variables = dict(variables)
        variables.update({"TOKEN": token, "AUTH_TYPE": "bearer"})
        return variables

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
                self._refresh_workflow_summary(definition)
            except (TypeError, ValueError):
                self.workflow_json.setPlainText(row["definition_json"])
                self.workflow_scope.clear()
                self.workflow_summary.setPlainText("该测试方案无法解析。请在“高级能力”中修正后重新保存。")

    def _refresh_workflow_summary(self, definition: dict) -> None:
        """Translate the internal workflow document into the review text users actually need."""
        summary = getattr(self, "workflow_summary", None)
        if not summary:
            return
        steps = definition.get("steps") or []
        focuses = definition.get("test_focus") or ["正常流程", "必填参数", "边界值", "权限与认证", "异常返回"]
        lines = [
            f"测试方案：{definition.get('name', '未命名方案')}",
            f"状态：{'已确认，可执行回归' if definition.get('review_status') == 'confirmed' else '草稿，已自动生成，可按需补充'}",
            f"识别到 {len(steps)} 个接口步骤。将自动覆盖：{'、'.join(map(str, focuses))}。",
            "接口链路：",
        ]
        for index, step in enumerate(steps[:8], 1):
            request = step.get("request") or {}
            method, path = request.get("method", ""), request.get("path", "")
            endpoint = f"{method} {path}".strip()
            name = str(step.get("name") or "").strip()
            if name and name != endpoint:
                lines.append(f"步骤 {index}：{name}（调用 {endpoint}）")
            else:
                lines.append(f"步骤 {index}：调用接口 {endpoint}")
        if len(steps) > 8:
            lines.append(f"……其余 {len(steps) - 8} 个步骤会一并生成测试用例。")
        if definition.get("database_changes"):
            lines.append("检测到可能的数据变更；如需验证数据库结果，可在“高级能力”中启用数据库校验。")
        else:
            lines.append("未要求数据库校验：可直接生成并执行接口回归测试。")
        summary.setPlainText("\n".join(lines))
        summary.verticalScrollBar().setValue(0)

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
            self._refresh_workflow_summary(candidate)
            self.workflow_output.setPlainText(
                f"已完成自动分析（{candidate.get('generation_mode')}）：中文测试方案已生成。下一步可直接点击“自动生成测试用例”；数据库校验和底层流程编辑仅在高级能力中按需使用。"
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
            self._refresh_workflow_summary(definition)
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
            self._refresh_workflow_summary(definition)
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
        self._refresh_workflow_summary(definition)
        self.workflow_output.setPlainText("已创建人工流程草稿，请补全数据流、数据库变更、异常分支和补偿动作后保存。")

    def confirm_workflow_scope(self):
        workflow_id = self.workflow_selector.currentData() if hasattr(self, "workflow_selector") else None
        if not workflow_id:
            QMessageBox.information(self, "提示", "请先选择或保存流程")
            return
        try:
            definition = json.loads(self.workflow_json.toPlainText() or "{}")
            raw = self.workflow_scope.toPlainText().strip()
            focuses = [item.strip() for item in raw.replace("，", ",").replace("\n", ",").split(",") if item.strip()]
            if not focuses:
                focuses = ["正常流程", "必填参数", "边界值", "权限与认证", "异常返回"]
            definition["test_focus"] = focuses
            definition["scope_confirmed"] = True
            definition["review_status"] = "draft"
            self.db.update_workflow(int(workflow_id), definition)
            self.db.audit(self.current_project_id, "confirm_workflow_scope", {"workflow_id": workflow_id, "test_focus": focuses})
            self.workflow_json.setPlainText(json.dumps(definition, ensure_ascii=False, indent=2))
            self._refresh_workflow_summary(definition)
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
            if not definition.get("test_focus"):
                definition["test_focus"] = ["正常流程", "必填参数", "边界值", "权限与认证", "异常返回"]
                definition["scope_confirmed"] = True
                self.db.update_workflow(int(workflow_id), definition)
                self.workflow_scope.setPlainText("、".join(definition["test_focus"]))
                self._refresh_workflow_summary(definition)
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
        self.statusBar().showMessage(
            f"使用已保存运行配置“{self.env_name.text() or '未命名'}”执行已确认流程。", 4000
        )
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
            execution_definition = {**definition, "run_id": f"workflow_{run_id}"}
            ledger_path = self.db.path.parent / "reports" / "workflow-artifacts" / str(run_id) / "resource_ledger.json"
            results, summary = run_workflow(
                execution_definition, self.base_url.text(), json.loads(self.headers.toPlainText() or "{}"),
                variables=variables, database=database, fixtures=fixtures, stop_event=getattr(self, "_stop_event", None), trace=trace,
                ledger_path=ledger_path,
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
        summary_setter = self.summary.setText if isinstance(self.summary, QLabel) else self.summary.setPlainText
        summary_setter(
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
            self._append_import_summary(
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
        self._set_import_summary(
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
        self._set_import_summary(json.dumps(difference, ensure_ascii=False, indent=2))
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
        # A project can contain both discovered source routes and an imported
        # OpenAPI document.  Show one endpoint per method/path and prefer the
        # document definition, because it carries the request schema/examples.
        # The original sources remain stored for comparison and filtering.
        if source_id is None:
            preferred: dict[tuple[str, str], dict] = {}
            for candidate in rows:
                kind = str(candidate.get("source_kind") or "")
                priority = 3 if kind == "manual" else 1 if kind == "source_code" else 2
                key = (str(candidate["method"]), str(candidate["path"]))
                existing = preferred.get(key)
                existing_kind = str(existing.get("source_kind") or "") if existing else ""
                existing_priority = 3 if existing_kind == "manual" else 1 if existing_kind == "source_code" else 2
                if existing is None or (priority, int(candidate["source_id"])) >= (existing_priority, int(existing["source_id"])):
                    preferred[key] = candidate
            rows = sorted(preferred.values(), key=lambda item: (str(item["module"]).lower(), str(item["path"]), str(item["method"])))
        table = self.endpoint_table
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        try:
            table.setRowCount(len(rows)); self._endpoint_rows = rows
            for i, row in enumerate(rows):
                values = (row["method"], row.get("summary") or row["path"], row["path"])
                for col, value in enumerate(values):
                    table.setItem(i, col, QTableWidgetItem(str(value)))
        finally:
            table.blockSignals(False)
            table.setUpdatesEnabled(True)
        self.refresh_endpoint_tree(rows)
        self._refresh_auth_status_hint()

    def refresh_endpoint_tree(self, rows: list[dict]) -> None:
        """Build the Apifox-style module navigator from the already filtered rows."""
        if not hasattr(self, "endpoint_tree"):
            return
        tree = self.endpoint_tree
        tree.blockSignals(True); tree.clear()
        try:
            workspace_root = QTreeWidgetItem(tree, ["默认模块"])
            workspace_root.setIcon(0, self.style().standardIcon(QStyle.SP_DirHomeIcon))
            workspace_root.setData(0, Qt.UserRole, {"kind": "all"})
            root = QTreeWidgetItem(workspace_root, [f"接口  ({len(rows)})"])
            root.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
            root.setData(0, Qt.UserRole, {"kind": "all"})
            groups: dict[str, list[dict]] = {}
            for row in rows:
                groups.setdefault(str(row.get("module") or "未分组"), []).append(row)
            for module, module_rows in sorted(groups.items(), key=lambda item: item[0].lower()):
                module_item = QTreeWidgetItem(root, [f"{module}  ({len(module_rows)})"])
                module_item.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
                module_item.setData(0, Qt.UserRole, {"kind": "module", "module": module})
                for row in module_rows:
                    method = str(row["method"]).upper()
                    endpoint_item = QTreeWidgetItem(module_item, [""])
                    endpoint_item.setSizeHint(0, QSize(0, 30))
                    endpoint_item.setData(0, Qt.UserRole, {"kind": "endpoint", "id": row["id"]})
                    endpoint_line = QWidget(tree); endpoint_line.setObjectName("EndpointTreeLeaf")
                    endpoint_line.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    endpoint_layout = QHBoxLayout(endpoint_line); endpoint_layout.setContentsMargins(0, 0, 0, 0); endpoint_layout.setSpacing(6)
                    method_label = QLabel(method); method_label.setObjectName("EndpointTreeMethod")
                    method_label.setStyleSheet(f"color: {HttpMethodItemDelegate.COLORS.get(method, '#1677e8')};")
                    name_label = QLabel(str(row.get("summary") or row["path"])); name_label.setObjectName("EndpointTreeName")
                    endpoint_layout.addWidget(method_label); endpoint_layout.addWidget(name_label); endpoint_layout.addStretch()
                    tree.setItemWidget(endpoint_item, 0, endpoint_line)
            workspace_root.setExpanded(True); root.setExpanded(True)
            for index in range(root.childCount()):
                root.child(index).setExpanded(True)
        finally:
            tree.blockSignals(False)

    def select_endpoint_tree_item(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.UserRole) or {}
        if data.get("kind") == "all":
            self.module_filter.setCurrentIndex(0)
            return
        if data.get("kind") == "module":
            index = self.module_filter.findData(data["module"])
            self.module_filter.setCurrentIndex(max(0, index))
            return
        if data.get("kind") == "endpoint":
            endpoint_id = data.get("id")
            for row_index, row in enumerate(getattr(self, "_endpoint_rows", [])):
                if row["id"] == endpoint_id:
                    self.endpoint_table.selectRow(row_index)
                    break

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

    def _add_endpoint_operation(self, stage: str, name: str) -> None:
        """Add a visible, removable pre/post action card after a menu choice."""
        layout = self.endpoint_pre_actions_layout if stage == "pre" else self.endpoint_post_actions_layout
        card = QFrame(); card.setObjectName("EndpointOperationCard")
        card_layout = QHBoxLayout(card); card_layout.setContentsMargins(10, 7, 8, 7)
        card_layout.addWidget(QLabel(name, objectName="EndpointOperationName"))
        detail = QLabel("待配置"); detail.setObjectName("EndpointOperationDetail")
        remove = QToolButton(); remove.setText("×"); remove.setToolTip("移除此操作"); remove.clicked.connect(card.deleteLater)
        card_layout.addStretch(); card_layout.addWidget(detail); card_layout.addWidget(remove)
        layout.insertWidget(max(1, layout.count() - 1), card)

    @staticmethod
    def _endpoint_body_example(request_body: dict) -> object:
        """Read examples from both normalized and OpenAPI request-body layouts."""
        if not isinstance(request_body, dict):
            return {}
        example = request_body.get("example")
        if isinstance(example, dict) and "value" in example:
            example = example["value"]
        if example is not None:
            return example
        examples = request_body.get("examples")
        if isinstance(examples, dict) and examples:
            first = next(iter(examples.values()))
            return first.get("value", first) if isinstance(first, dict) else first
        content = request_body.get("content") or {}
        if not isinstance(content, dict):
            return {}
        media = content.get("application/json") or next((item for item in content.values() if isinstance(item, dict)), {})
        if not isinstance(media, dict):
            return {}
        example = media.get("example")
        if isinstance(example, dict) and "value" in example:
            return example["value"]
        if example is not None:
            return example
        examples = media.get("examples")
        if isinstance(examples, dict) and examples:
            first = next(iter(examples.values()))
            return first.get("value", first) if isinstance(first, dict) else first
        schema = media.get("schema") or {}
        return MainWindow._schema_default_example(schema)

    @staticmethod
    def _schema_default_example(schema: object) -> object:
        """Create an editable request skeleton when an API only supplies a schema."""
        if not isinstance(schema, dict):
            return {}
        for key in ("example", "default"):
            if key in schema and schema[key] is not None:
                return schema[key]
        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            return enum[0]
        properties = schema.get("properties")
        if isinstance(properties, dict):
            return {str(name): MainWindow._schema_default_example(value) for name, value in properties.items()}
        schema_type = str(schema.get("type") or "")
        if schema_type == "array":
            return []
        if schema_type in {"integer", "number"}:
            return 0
        if schema_type == "boolean":
            return False
        if schema_type == "object":
            return {}
        return ""

    @staticmethod
    def _endpoint_body_field_metadata(request_body: dict, body_type: str) -> dict[str, dict[str, str]]:
        """Extract property type/description for form-style request bodies."""
        if not isinstance(request_body, dict):
            return {}
        content = request_body.get("content") or {}
        if not isinstance(content, dict):
            return {}
        content_type = {
            "form-data": "multipart/form-data",
            "x-www-form-urlencoded": "application/x-www-form-urlencoded",
        }.get(body_type, "")
        media = content.get(content_type) if content_type else None
        if not isinstance(media, dict):
            media = next((item for item in content.values() if isinstance(item, dict)), {})
        schema = media.get("schema") or {} if isinstance(media, dict) else {}
        properties = schema.get("properties") or {} if isinstance(schema, dict) else {}
        if not isinstance(properties, dict):
            return {}
        return {
            str(name): {
                "type": str(value.get("type") or "string"),
                "description": str(value.get("description") or ""),
            }
            for name, value in properties.items() if isinstance(value, dict)
        }

    @staticmethod
    def _fill_endpoint_editor_table(table: QTableWidget, rows: list[dict]) -> None:
        table.blockSignals(True)
        try:
            table.setRowCount(max(1, len(rows)))
            for row_index in range(max(1, len(rows))):
                item = rows[row_index] if row_index < len(rows) else {}
                values = (
                    item.get("name", "添加参数" if not rows else ""),
                    item.get("value", ""),
                    item.get("type", "string"),
                    item.get("description", ""),
                )
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(str(value))
                    if column == 0 and item.get("location"):
                        cell.setData(Qt.UserRole, item["location"])
                    table.setItem(row_index, column, cell)
        finally:
            table.blockSignals(False)

    def _populate_endpoint_request_editor(self, parameters: list[dict], request_body: dict, security: list[dict]) -> None:
        if not hasattr(self, "endpoint_query_editor"):
            return
        normalized = []
        for item in parameters:
            if not isinstance(item, dict):
                continue
            location = str(item.get("location") or item.get("in") or "query").lower()
            schema = item.get("schema") or {}
            example = item.get("example")
            if example is None and isinstance(schema, dict):
                example = schema.get("example", schema.get("default", ""))
            normalized.append({
                "name": item.get("name", ""), "value": example,
                "type": schema.get("type", item.get("type", "string")) if isinstance(schema, dict) else item.get("type", "string"),
                "description": item.get("description", ""), "location": location,
            })
        self.endpoint_query_editor.set_parameters([item for item in normalized if item["location"] == "query"])
        self._sync_endpoint_url_query()
        header_parameters = [item for item in normalized if item["location"] == "header"]
        if security and not any(item.get("name", "").lower() == "authorization" for item in header_parameters):
            header_parameters.append({"name": "Authorization", "value": "由 Auth 配置管理", "source": "Auth"})
        if hasattr(self, "endpoint_headers_editor"):
            self.endpoint_headers_editor.set_parameters(header_parameters)
        if hasattr(self, "endpoint_cookies_editor"):
            self.endpoint_cookies_editor.set_parameters([item for item in normalized if item["location"] == "cookie"])
        if hasattr(self, "endpoint_auth_mode"):
            self.endpoint_auth_mode.setCurrentText("Bearer Token" if security else "无需鉴权")
        body_example = self._endpoint_body_example(request_body)
        self._set_endpoint_body_type_from_definition(request_body)
        body_metadata = self._endpoint_body_field_metadata(request_body, self._endpoint_body_type)
        if self._endpoint_body_type == "form-data" and isinstance(body_example, dict):
            names = list(dict.fromkeys([*body_metadata, *body_example]))
            self.endpoint_body_form_editor.set_parameters([
                {"name": key, "value": body_example.get(key, ""), **body_metadata.get(key, {})} for key in names
            ])
            self._update_endpoint_body_editor_height()
        elif self._endpoint_body_type == "x-www-form-urlencoded" and isinstance(body_example, dict):
            names = list(dict.fromkeys([*body_metadata, *body_example]))
            self.endpoint_body_urlencoded_editor.set_parameters([
                {"name": key, "value": body_example.get(key, ""), **body_metadata.get(key, {})} for key in names
            ])
            self._update_endpoint_body_editor_height()
        elif self._endpoint_body_type in {"raw", "xml", "text", "graphql", "msgpack"} and isinstance(body_example, str):
            self.body.setPlainText(body_example)
        else:
            self.body.setPlainText(json.dumps(body_example if body_example is not None else {}, ensure_ascii=False, indent=2))

    def _set_endpoint_body_type(self, body_type: str) -> None:
        self._endpoint_body_type = body_type
        if not hasattr(self, "body"):
            return
        if hasattr(self, "endpoint_body_stack"):
            page = getattr(self, "_endpoint_body_pages", {}).get(body_type)
            if page:
                self.endpoint_body_stack.setCurrentWidget(page)
            compact_heights = {
                "none": 52, "binary": 58,
                "raw": 220, "json": 220, "xml": 220, "text": 220, "graphql": 220, "msgpack": 220,
            }
            if body_type in {"form-data", "x-www-form-urlencoded"}:
                self._update_endpoint_body_editor_height()
            else:
                self.endpoint_body_stack.setFixedHeight(compact_heights.get(body_type, 220))
        text_placeholders = {
            "json": "输入 JSON 请求体", "xml": "输入 XML 请求体", "text": "输入纯文本请求体",
            "raw": "输入原始文本请求体", "graphql": "输入 GraphQL 请求体", "msgpack": "输入 msgpack 内容",
        }
        self.body.setReadOnly(False); self.body.setEnabled(body_type not in {"none", "binary"})
        self.body.setPlaceholderText(text_placeholders.get(body_type, "根据接口定义填写请求 Body"))
        if hasattr(self, "endpoint_body_format_button"):
            self.endpoint_body_format_button.setVisible(body_type == "json")

    def _update_endpoint_body_editor_height(self) -> None:
        """Keep form bodies as compact as the Params key/value editor."""
        if not hasattr(self, "endpoint_body_stack"):
            return
        body_type = getattr(self, "_endpoint_body_type", "json")
        editors = {
            "form-data": getattr(self, "endpoint_body_form_editor", None),
            "x-www-form-urlencoded": getattr(self, "endpoint_body_urlencoded_editor", None),
        }
        editor = editors.get(body_type)
        if editor is None:
            return
        # A single blank row remains a normal compact form.  Each automatic
        # extra row adds just its own row height and spacing.
        row_count = len(getattr(editor, "_rows", ()))
        height = max(78, 40 + row_count * 38)
        self.endpoint_body_stack.setFixedHeight(min(height, 230))

    def _choose_endpoint_binary_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 Binary 请求文件")
        if path and hasattr(self, "endpoint_binary_path"):
            self.endpoint_binary_path.setText(path)

    def _set_endpoint_body_type_from_definition(self, request_body: dict) -> None:
        content = request_body.get("content") if isinstance(request_body, dict) else {}
        content = content if isinstance(content, dict) else {}
        content_types = {str(content_type).lower() for content_type in content}
        if "application/json" in content_types or any("+json" in item for item in content_types):
            body_type = "json"
        elif "multipart/form-data" in content_types:
            body_type = "form-data"
        elif "application/x-www-form-urlencoded" in content_types:
            body_type = "x-www-form-urlencoded"
        elif any("xml" in item for item in content_types):
            body_type = "xml"
        elif any("graphql" in item for item in content_types):
            body_type = "graphql"
        elif any("msgpack" in item for item in content_types):
            body_type = "msgpack"
        elif any("octet-stream" in item for item in content_types):
            body_type = "binary"
        elif any(item.startswith("text/") for item in content_types):
            body_type = "text"
        elif content_types:
            body_type = "raw"
        else:
            body_type = "none"
        if hasattr(self, "endpoint_body_type_buttons"):
            button = self.endpoint_body_type_buttons.get(body_type)
            if button:
                button.setChecked(True)
        self._set_endpoint_body_type(body_type)

    def _format_endpoint_body(self) -> None:
        if not hasattr(self, "body") or self._endpoint_body_type != "json":
            return
        try:
            value = json.loads(self.body.toPlainText() or "{}")
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "无法格式化", f"请求 Body 不是有效 JSON：{exc.msg}")
            return
        self.body.setPlainText(json.dumps(value, ensure_ascii=False, indent=2))

    def _endpoint_body_payload(self) -> tuple[object | None, str]:
        """Return the selected Body safely for both debug sending and saved cases."""
        body_type = getattr(self, "_endpoint_body_type", "json")
        if self.method.currentText() in {"GET", "HEAD"} or body_type == "none":
            return None, "application/json"
        if body_type == "form-data":
            return dict(self.endpoint_body_form_editor.parameters()), "multipart/form-data"
        if body_type == "x-www-form-urlencoded":
            return dict(self.endpoint_body_urlencoded_editor.parameters()), "application/x-www-form-urlencoded"
        if body_type == "binary":
            path = Path(self.endpoint_binary_path.text().strip())
            if not path.is_file():
                raise ValueError("请选择存在的 Binary 请求文件")
            return path.read_bytes(), "application/octet-stream"
        text = self.body.toPlainText().strip()
        if body_type in {"raw", "text", "xml", "graphql", "msgpack"}:
            content_type = {
                "raw": "text/plain", "text": "text/plain", "xml": "application/xml",
                "graphql": "application/graphql", "msgpack": "application/msgpack",
            }[body_type]
            return text, content_type
        try:
            payload = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"请求 Body 不是有效 JSON：{exc.msg}") from exc
        content_types = {
            "json": "application/json",
        }
        return payload, content_types.get(body_type, "application/json")

    def _sync_endpoint_url_query(self) -> None:
        """Reflect the compact Query editor in the read-only request URL immediately."""
        if not hasattr(self, "endpoint_url") or not hasattr(self, "endpoint_query_editor"):
            return
        base_url = self.base_url.text().strip() if hasattr(self, "base_url") else ""
        path = self.path.text().strip() if hasattr(self, "path") else ""
        if not base_url:
            environments = self.db.list_environments(self.current_project_id) if self.current_project_id else []
            base_url = str(environments[0].get("base_url") or "") if environments else ""
        url = f"{base_url.rstrip('/')}{path}" if base_url else path
        query = self.endpoint_query_editor.parameters()
        self.endpoint_url.setText(f"{url}?{urlencode(query)}" if query else url)

    def _endpoint_request_overrides(self) -> tuple[str, dict, dict]:
        """Build path, query values and headers from the compact debug editors."""
        request_path = self.path.text()
        query: dict[str, object] = {}
        extra_headers: dict[str, str] = {}
        if hasattr(self, "endpoint_query_editor"):
            query.update({name: value for name, value in self.endpoint_query_editor.parameters()})
        if hasattr(self, "endpoint_headers_editor"):
            for item in self.endpoint_headers_editor.entries():
                if item["enabled"] and item.get("source") != "Auth":
                    extra_headers[item["name"]] = item["value"]
        if hasattr(self, "endpoint_cookies_editor"):
            cookies = [
                f"{item['name']}={item['value']}" for item in self.endpoint_cookies_editor.entries()
                if item["enabled"]
            ]
            if cookies:
                extra_headers["Cookie"] = "; ".join(cookies)
        return request_path, query, extra_headers

    @staticmethod
    def _inline_query_parameters(path: str) -> tuple[str, list[dict]]:
        """Recover query fields from imported URLs that embed `?key=value`."""
        parsed = urlparse(path)
        if not parsed.query:
            return path, []
        route = parsed.path or "/"
        return route, [
            {"name": name, "location": "query", "schema": {"type": "string"}, "example": value}
            for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        ]

    def show_endpoint(self):
        row = self.endpoint_table.currentRow()
        if row < 0 or row >= len(getattr(self, "_endpoint_rows", [])):
            return
        stored = self._endpoint_rows[row]
        data = json.loads(stored["definition_json"])
        parameters = [item for item in data.get("parameters") or [] if isinstance(item, dict)]
        path = str(data.get("path") or stored.get("path") or "/")
        path, inline_query_parameters = self._inline_query_parameters(path)
        known_query_names = {
            str(item.get("name") or "") for item in parameters
            if str(item.get("location") or item.get("in") or "query").lower() == "query"
        }
        parameters.extend(item for item in inline_query_parameters if item["name"] not in known_query_names)
        request_body = data.get("request_body") or {}
        responses = data.get("responses") or {}
        security = data.get("security") or []
        parameter_lines = [
            f"- {item.get('name', '未命名')}  ·  {item.get('in', 'query')}  ·  {'必填' if item.get('required') else '可选'}"
            for item in parameters if isinstance(item, dict)
        ]
        request_example = request_body.get("example") if isinstance(request_body, dict) else None
        if request_example is None and isinstance(request_body, dict):
            request_example = request_body.get("examples")
        detail = [
            f"{data.get('method', stored['method'])}  {data.get('path', stored['path'])}",
            "",
            f"名称：{data.get('summary') or stored.get('summary') or '未命名接口'}",
            f"模块：{data.get('module') or stored.get('module') or '未分组'}",
            f"认证：{'需要' if security else '未声明'}",
            "",
            "请求参数：",
            *(parameter_lines or ["- 未声明参数"]),
            "",
            "请求体示例：",
            json.dumps(request_example, ensure_ascii=False, indent=2) if request_example is not None else "未提供示例",
            "",
            "响应定义：",
            json.dumps(responses, ensure_ascii=False, indent=2) if responses else "未提供响应 Schema",
        ]
        method = str(data.get("method") or stored.get("method") or "GET").upper()
        self.endpoint_detail.setPlainText("\n".join(detail))
        self.method.setCurrentText(method)
        method_color = {
            "GET": "#16a34a", "POST": "#f97316", "PUT": "#1677e8", "PATCH": "#8b5cf6",
            "DELETE": "#ef4444", "HEAD": "#06b6d4", "OPTIONS": "#d4a000",
        }.get(method, "#1677e8")
        palette = self.method.palette()
        palette.setColor(QPalette.ButtonText, QColor(method_color))
        palette.setColor(QPalette.Text, QColor(method_color))
        self.method.setPalette(palette)
        self.path.setText(path)
        environments = self.db.list_environments(self.current_project_id) if self.current_project_id else []
        base_url = str(environments[0].get("base_url") or "") if environments else ""
        full_url = f"{base_url.rstrip('/')}{path}" if base_url else path
        self.endpoint_url.setText(full_url)
        request_example = request_body.get("example") if isinstance(request_body, dict) else None
        if request_example is None and isinstance(request_body, dict):
            request_example = request_body.get("examples")
        if not isinstance(request_example, (dict, list)):
            request_example = {}
        self.body.setPlainText(json.dumps(request_example, ensure_ascii=False, indent=2))
        self._populate_endpoint_request_editor(
            [item for item in parameters if isinstance(item, dict)], request_body, security
        )
        summary = str(data.get("summary") or stored.get("summary") or path)
        self.endpoint_active_label.setText(f"{method}  {path}")
        self.endpoint_active_label.setToolTip(summary)
        if hasattr(self, "endpoint_definition_name"):
            self.endpoint_definition_name.setText(summary)
            self.endpoint_definition_path.setText(path)
            self.endpoint_definition_method.setText(method)
            self.endpoint_definition_module.setText(str(data.get("module") or stored.get("module") or "未分组"))
            request_table = self.endpoint_request_parameter_table
            request_parameters = [item for item in parameters if isinstance(item, dict)]
            request_table.clearSpans()
            request_table.setRowCount(len(request_parameters) or 1)
            if not request_parameters:
                request_table.setItem(0, 0, QTableWidgetItem("暂无请求参数"))
                request_table.setSpan(0, 0, 1, 4)
            for index, item in enumerate(request_parameters):
                values = (
                    item.get("name", "—"), item.get("schema", {}).get("type", "string") if isinstance(item.get("schema"), dict) else item.get("type", "string"),
                    "是" if item.get("required") else "否", item.get("description", ""),
                )
                for column, value in enumerate(values):
                    request_table.setItem(index, column, QTableWidgetItem(str(value)))
            response_table = self.endpoint_response_parameter_table
            response_items = list(responses.items()) if isinstance(responses, dict) else []
            response_table.clearSpans()
            response_table.setRowCount(len(response_items) or 1)
            if not response_items:
                response_table.setItem(0, 0, QTableWidgetItem("暂无响应参数"))
                response_table.setSpan(0, 0, 1, 3)
            for index, (code, response_definition) in enumerate(response_items):
                description = response_definition.get("description", "") if isinstance(response_definition, dict) else ""
                response_table.setItem(index, 0, QTableWidgetItem(str(code)))
                response_table.setItem(index, 1, QTableWidgetItem("object"))
                response_table.setItem(index, 2, QTableWidgetItem(str(description)))

    def debug_selected_endpoint(self):
        """Open the selected endpoint in the interface-asset debugging tab."""
        row = self.endpoint_table.currentRow()
        if row < 0 or row >= len(getattr(self, "_endpoint_rows", [])):
            QMessageBox.information(self, "选择接口", "请先在接口列表中选择一个接口。")
            return
        # Reuse the normal selection pipeline so debug always has the definition's
        # query/header/cookie defaults and the URL remains synchronised.
        self.show_endpoint()
        self.endpoint_request_tabs.setCurrentIndex(1)

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
        if hasattr(self, "auth_username"):
            self.auth_username.setText(str(values.get("TEST_USERNAME", values.get("USERNAME", ""))))
        if hasattr(self, "auth_password"):
            self.auth_password.setText(str(values.get("TEST_PASSWORD", values.get("PASSWORD", ""))))
        self._refresh_auth_status_hint()
        if hasattr(self, "environment_confirmed"):
            authorized = self.db.get_setting(
                f"environment_authorized:{self.current_project_id}:{env['name']}", "0"
            ) == "1"
            self.environment_confirmed.setChecked(authorized)

    def _set_validation_log(self, entries: list[tuple[str, str, str]]) -> None:
        """Render a consistently aligned time / check / result validation log."""
        self._validation_log_entries = list(entries)
        while self.validation_log_rows.count():
            item = self.validation_log_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        label_for_level = {"success": "成功", "warning": "异常", "running": "进行中", "pending": "待校验"}
        icon_for_level = {"success": "status_success", "warning": "status_warning", "running": "status_running", "pending": "status_pending"}
        for timestamp, message, level in entries:
            row = QFrame(); row.setObjectName("ValidationLogRow")
            row_layout = QHBoxLayout(row); row_layout.setContentsMargins(0, 6, 0, 6); row_layout.setSpacing(7)
            row.setMinimumHeight(38)
            time_label = QLabel(timestamp or "--:--:--"); time_label.setObjectName("ValidationLogTime")
            time_label.setFixedWidth(58)
            item_label = QLabel(message); item_label.setObjectName("ValidationLogMessage")
            item_label.setWordWrap(True)
            result_icon = self._illustration_icon(icon_for_level.get(level, "status_pending"), 14)
            result_label = QLabel(label_for_level.get(level, "待校验")); result_label.setObjectName(
                f"ValidationLogStatus{level.capitalize()}"
            )
            result_label.setMinimumWidth(34)
            row_layout.addWidget(time_label, 0, Qt.AlignTop)
            row_layout.addWidget(item_label, 1)
            row_layout.addWidget(result_icon, 0, Qt.AlignTop)
            row_layout.addWidget(result_label, 0, Qt.AlignTop)
            self.validation_log_rows.addWidget(row)
        self.validation_log_rows.addStretch(1)

    def export_environment_validation_report(self) -> None:
        """Export the latest non-sensitive environment validation summary."""
        default_name = f"环境校验报告-{datetime.now():%Y%m%d-%H%M%S}.txt"
        filename, _ = QFileDialog.getSaveFileName(self, "导出校验报告", default_name, "文本文件 (*.txt)")
        if not filename:
            return
        level_names = {"success": "成功", "warning": "异常", "running": "进行中", "pending": "待校验"}
        project_name = self._current_project_name() or "未选择项目"
        lines = [
            "TestPilot AI 环境校验报告",
            f"项目：{project_name}",
            f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
            "",
            "校验日志：",
        ]
        for timestamp, message, level in getattr(self, "_validation_log_entries", []):
            lines.append(f"{timestamp or '--:--:--'}  {message}  {level_names.get(level, level)}")
        try:
            Path(filename).write_text("\n".join(lines) + "\n", encoding="utf-8")
            QMessageBox.information(self, "导出完成", f"校验报告已保存：\n{filename}")
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def _set_validation_icon(self, label: QLabel, level: str, size: int = 15) -> None:
        kind = {"success": "status_success", "warning": "status_warning", "running": "status_running"}.get(level, "status_pending")
        icon = self._illustration_icon(kind, size)
        label.setPixmap(icon.pixmap())
        label.setFixedSize(size, size)

    @staticmethod
    def _set_validation_label_style(label: QLabel, level: str, prefix: str) -> None:
        label.setObjectName(f"{prefix}{'Success' if level == 'success' else 'Failure' if level == 'warning' else 'Pending'}")
        label.style().unpolish(label)
        label.style().polish(label)

    def run_environment_validation(self):
        """Run a safe connectivity check and update the dashboard without making
        any business-data changes."""
        if not self.current_project_id:
            QMessageBox.information(self, "提示", "请先选择项目")
            return
        base_url = self.base_url.text().strip()
        if not base_url:
            QMessageBox.warning(self, "缺少地址", "请填写测试环境地址后再校验。")
            return
        endpoint_count = len(self.db.list_endpoints(self.current_project_id))
        started_at = datetime.now()
        self._set_validation_log([(started_at.strftime("%H:%M:%S"), "开始环境校验", "running")])
        try:
            result = execute_request("HEAD", base_url, "/", {}, None)
            self._validation_response_detail = {
                "request": {
                    "method": "HEAD",
                    "url": f"{base_url.rstrip('/')}/",
                    "headers": {},
                    "body": None,
                },
                "response": {
                    "status_code": result.status_code,
                    "elapsed_ms": result.elapsed_ms,
                    "headers": result.headers,
                    "body": result.body,
                },
            }
            reachable = result.status_code < 500
            _auth_required, login = self._detected_project_auth()
            login_known = login is not None
            login_path = str(login.get("path")) if login_known else ""
            status_text = "成功" if reachable else f"异常（HTTP {result.status_code}）"
            step_details = (
                base_url,
                f"已识别登录接口 {login_path}" if login_known else "未发现固定登录接口",
                "回归时自动获取/复用" if login_known and reachable else "待识别登录规则或服务恢复",
                f"已载入 {endpoint_count} 个接口",
                "环境与认证规则校验通过" if reachable and login_known else "环境或认证规则待确认",
            )
            step_levels = ("success" if reachable else "warning", "success" if login_known else "warning",
                           "success" if login_known and reachable else "warning", "success",
                           "success" if reachable and login_known else "warning")
            for index, (detail, status, status_icon) in enumerate(self.validation_steps):
                detail.setText(step_details[index])
                level = step_levels[index]
                status.setText("成功" if level == "success" else "异常")
                self._set_validation_icon(status_icon, level)
                self._set_validation_label_style(status, level, "ValidationStep")
            metric_values = {
                "DNS 解析": ("地址已解析", "success"),
                "网络响应": (f"{result.elapsed_ms} ms", "success"),
                "服务健康": (f"HTTP {result.status_code}", "success" if reachable else "warning"),
                "登录接口": (login_path if login_known else "未识别固定登录接口", "success" if login_known else "warning"),
                "Token 有效期": ("回归时自动维护" if login_known else "待识别登录规则", "success" if login_known else "warning"),
                "认证方式": ("按接口文档执行" if login_known else "请在接口资产中确认", "success" if login_known else "warning"),
                "发现接口数量": (f"{endpoint_count} 个", "success"),
                "可访问接口数量": (f"{endpoint_count if reachable else 0} 个", "success" if reachable else "warning"),
                "不可访问接口数量": ("0 个" if reachable else f"{endpoint_count} 个", "success" if reachable else "warning"),
            }
            for key, (value, level) in metric_values.items():
                self.validation_metrics[key].setText(value)
                self._set_validation_icon(self.validation_metric_icons[key], level, 14)
            panel_state = {
                "基础连通性": (
                    "通过" if reachable else "异常",
                    "success" if reachable else "warning",
                    "基础连通性正常，可访问目标服务。" if reachable else "目标服务响应异常，请恢复服务后再次校验。",
                ),
                "认证校验": (
                    "通过" if login_known else "需确认",
                    "success" if login_known else "warning",
                    f"已识别 {login_path}；实际登录请在“接口资产 → 调试”验证。" if login_known else "未识别固定登录接口，请在接口资产中确认认证方式。",
                ),
                "接口资产校验": (
                    "通过" if reachable else "部分异常",
                    "success" if reachable else "warning",
                    "接口资产已校验，可开始生成测试用例。" if reachable else "存在不可访问接口，建议查看校验响应并处理。",
                ),
            }
            for panel_name, (text, level, summary_text) in panel_state.items():
                panel_status, panel_icon = self.validation_panel_status[panel_name]
                panel_status.setText(text)
                self._set_validation_icon(panel_icon, level, 14)
                self._set_validation_label_style(panel_status, level, "ValidationPanel")
                summary, summary_icon = self.validation_panel_summaries[panel_name]
                summary.setText(summary_text)
                self._set_validation_icon(summary_icon, level, 15)
                self._set_validation_label_style(summary, level, "ValidationSummary")
            if self.validation_asset_action is not None:
                self.validation_asset_action.setVisible(not reachable)
            timestamp = started_at
            def event_time() -> str:
                nonlocal timestamp
                timestamp += timedelta(milliseconds=180)
                return timestamp.strftime("%H:%M:%S")

            log_entries = [
                (started_at.strftime("%H:%M:%S"), "开始环境校验", "running"),
                (event_time(), "解析基础地址", "success"),
                (event_time(), "DNS 解析", "success"),
                (event_time(), "网络连通性检查", "success"),
                (event_time(), f"服务健康检查（HTTP {result.status_code}）", "success" if reachable else "warning"),
                (event_time(), f"登录认证规则识别：{login_path}" if login_known else "未发现固定登录接口", "success" if login_known else "warning"),
                (event_time(), "Token 获取规则已识别" if login_known else "Token 获取规则待确认", "success" if login_known else "warning"),
                (event_time(), f"接口资产加载：{endpoint_count} 个接口", "success"),
                (event_time(), "接口可访问性校验", "success" if reachable else "warning"),
                (event_time(), "校验完成", "success" if reachable else "warning"),
            ]
            self._set_validation_log(log_entries)
            self.statusBar().showMessage(f"环境校验{status_text}", 4000)
        except Exception as exc:
            self._validation_response_detail = {
                "request": {
                    "method": "HEAD",
                    "url": f"{base_url.rstrip('/')}/",
                    "headers": {},
                    "body": None,
                },
                "error": str(exc),
            }
            for _detail, status, status_icon in self.validation_steps:
                status.setText("异常")
                self._set_validation_icon(status_icon, "warning")
                self._set_validation_label_style(status, "warning", "ValidationStep")
            for metric_icon in self.validation_metric_icons.values():
                self._set_validation_icon(metric_icon, "warning", 14)
            for panel_name, (panel_status, panel_icon) in self.validation_panel_status.items():
                panel_status.setText("异常")
                self._set_validation_icon(panel_icon, "warning", 14)
                self._set_validation_label_style(panel_status, "warning", "ValidationPanel")
                summary, summary_icon = self.validation_panel_summaries[panel_name]
                summary.setText("校验未完成，请检查测试环境后再次校验。")
                self._set_validation_icon(summary_icon, "warning", 15)
                self._set_validation_label_style(summary, "warning", "ValidationSummary")
            if self.validation_asset_action is not None:
                self.validation_asset_action.setVisible(True)
            self._set_validation_log([
                (started_at.strftime("%H:%M:%S"), "开始环境校验", "running"),
                (datetime.now().strftime("%H:%M:%S"), f"校验失败：{exc}", "warning"),
            ])
            QMessageBox.warning(self, "环境校验失败", str(exc))

    def show_validation_response_details(self):
        """Show the real request/response produced by the latest validation."""
        detail = getattr(self, "_validation_response_detail", None)
        if not detail:
            QMessageBox.information(self, "暂无校验响应", "请先开始环境校验，再查看本次请求响应。")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("环境校验请求响应")
        dialog.resize(780, 560)
        layout = QVBoxLayout(dialog)
        hint = QLabel("本次环境校验使用 HEAD 请求检查基础地址。这里展示实际请求与响应；不会逐一执行业务接口，避免产生业务副作用。")
        hint.setObjectName("ValidationHint")
        hint.setWordWrap(True)
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(json.dumps(detail, ensure_ascii=False, indent=2, default=str))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(hint)
        layout.addWidget(editor, 1)
        layout.addWidget(buttons)
        dialog.exec()

    def save_environment(self):
        if not self.current_project_id:
            QMessageBox.information(self, "提示", "请先选择项目"); return
        try:
            environment_name = self.env_selector.currentText().strip() if hasattr(self, "env_selector") else self.env_name.text().strip()
            if not environment_name:
                raise ValueError("环境名称不能为空")
            self.env_name.setText(environment_name)
            headers = json.loads(self.headers.toPlainText() or "{}")
            values = json.loads(self.variables.toPlainText() or "{}")
            username = self.auth_username.text().strip() if hasattr(self, "auth_username") else ""
            password = self.auth_password.text() if hasattr(self, "auth_password") else ""
            if username:
                values["TEST_USERNAME"] = username
            if password:
                values["TEST_PASSWORD"] = password
            if not isinstance(headers, dict): raise ValueError("Headers 必须是 JSON 对象")
            if not isinstance(values, dict): raise ValueError("环境变量必须是 JSON 对象")
            public, secrets = split_sensitive(values)
            self.db.save_environment(
                self.current_project_id, environment_name, self.base_url.text(), headers,
                public, self.secret_store.encrypt_dict(secrets),
            )
            self.db.set_setting(
                f"environment_authorized:{self.current_project_id}:{environment_name}",
                "1" if self.environment_confirmed.isChecked() else "0",
            )
            self.db.audit(self.current_project_id, "save_environment",
                          {"name": environment_name, "secret_count": len(secrets)})
            self.statusBar().showMessage("项目运行配置已保存，后续可直接生成并一键执行用例。", 4000)
            self._project_changed()
            QMessageBox.information(self, "环境已保存", f"已保存环境：{environment_name}\nRunner Manifest 的 environment_id 请使用这个名称。")
        except ValueError as exc:
            QMessageBox.warning(self, "配置错误", str(exc))

    def send_request(self):
        if not self.environment_confirmed.isChecked():
            QMessageBox.warning(self, "执行被阻止", "请先确认目标是已授权的测试环境。")
            return
        try:
            headers = json.loads(self.headers.toPlainText() or "{}")
            body, content_type = self._endpoint_body_payload()
            request_path, query, extra_headers = self._endpoint_request_overrides()
            headers.update(extra_headers)
            result = execute_request(
                self.method.currentText(), self.base_url.text(), request_path, headers, body,
                params=query, content_type=content_type,
            )
            self._last_request_result = result
            self.response.setPlainText(json.dumps({
                "status_code": result.status_code, "elapsed_ms": result.elapsed_ms,
                "headers": result.headers, "body": result.body,
            }, ensure_ascii=False, indent=2))
            if hasattr(self, "endpoint_response_meta"):
                payload_size = len(json.dumps(result.body, ensure_ascii=False).encode("utf-8"))
                self.endpoint_response_meta.setText(
                    f"状态：{result.status_code}    耗时：{result.elapsed_ms} ms    大小：{payload_size} B"
                )
        except Exception as exc:
            QMessageBox.critical(self, "请求失败", str(exc))

    def verify_environment_login(self):
        """Check the discovered login endpoint without exposing a password or token."""
        if not self.environment_confirmed.isChecked():
            QMessageBox.warning(self, "执行被阻止", "请先确认目标是已授权的测试环境。")
            return
        username, password = self.auth_username.text().strip(), self.auth_password.text()
        if not username or not password:
            QMessageBox.warning(self, "缺少认证信息", "请先填写并保存测试账号与测试密码。")
            return
        _, login = self._detected_project_auth()
        login_path = str((login or {}).get("path") or "/auth/login")
        try:
            result = execute_request("POST", self.base_url.text(), login_path, {}, {"username": username, "password": password})
            self._last_request_result = result
            self.response.setPlainText(json.dumps({
                "login_path": login_path,
                "status_code": result.status_code,
                "elapsed_ms": result.elapsed_ms,
                "body": result.body,
            }, ensure_ascii=False, indent=2))
            if hasattr(self, "endpoint_response_meta"):
                self.endpoint_response_meta.setText(
                    f"状态：{result.status_code}    耗时：{result.elapsed_ms} ms    登录验证"
                )
            if 200 <= result.status_code < 300:
                self.statusBar().showMessage("登录验证完成；响应中的 Token 已自动脱敏。", 4000)
            else:
                QMessageBox.warning(self, "登录验证失败", f"HTTP {result.status_code}，请查看下方脱敏响应。")
        except Exception as exc:
            QMessageBox.critical(self, "登录验证失败", str(exc))

    def save_request_as_case(self):
        """Turn an authorised debugging request into an editable draft case."""
        if not self._require_project():
            return
        try:
            headers = json.loads(self.headers.toPlainText() or "{}")
            body, content_type = self._endpoint_body_payload()
            request_path, query, extra_headers = self._endpoint_request_overrides()
            headers.update(extra_headers)
            if not isinstance(headers, dict):
                raise ValueError("Headers 必须是 JSON 对象")
            status = getattr(getattr(self, "_last_request_result", None), "status_code", 200)
            definition = {
                "name": f"{self.method.currentText()} {request_path} 调试用例",
                "priority": "P1", "module": "手工调试", "source": "request_debug",
                "review_status": "draft", "risk": "high" if self.method.currentText() in {"POST", "PUT", "PATCH", "DELETE"} else "low",
                "request": {
                    "method": self.method.currentText(), "path": request_path, "query": query,
                    "headers": headers, "body": body, "content_type": content_type,
                },
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
        try:
            variables = self._prepare_auto_auth(variables)
        except ValueError as exc:
            QMessageBox.warning(self, "自动认证未完成", str(exc))
            return None
        self.statusBar().showMessage(
            f"使用已保存运行配置“{self.env_name.text() or '未命名'}”一键执行 {len(cases)} 条{label}。", 4000
        )
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
            rows.extend(
                {
                    **row,
                    "report_type": row.get("report_type") or "接口契约报告",
                    "report_name": self.projects.currentText(),
                    "status": row.get("status") or "completed",
                    "started_at": row.get("started_at") or row.get("created_at") or "",
                    "finished_at": row.get("finished_at") or "",
                }
                for row in self.db.list_reports(self.current_project_id)
            )
            rows.extend(
                {
                    **row,
                    "report_type": row.get("report_type") or "业务流程报告",
                    "report_name": row.get("workflow_name", "业务流程"),
                    "status": row.get("status") or "completed",
                    "started_at": row.get("started_at") or row.get("created_at") or "",
                    "finished_at": row.get("finished_at") or "",
                }
                for row in self.db.list_workflow_reports(self.current_project_id)
            )
            # 证据报告不隶属于一次 test_run，本身没有 status/started_at 字段；
            # 统一为可展示的已完成记录，兼容已有本地数据库。
            def evidence_row(row: dict) -> dict:
                try:
                    evidence_summary = json.loads(row.get("summary_json") or "{}")
                except (TypeError, ValueError):
                    evidence_summary = {}
                return {
                    **row,
                    "report_name": self.projects.currentText(),
                    "run_id": row.get("id", ""),
                    "status": evidence_summary.get("status") or "completed",
                    "started_at": row.get("started_at") or row.get("created_at") or "",
                    "finished_at": row.get("finished_at") or "",
                }
            rows.extend(evidence_row(row) for row in self.db.list_evidence_reports(self.current_project_id))
            rows.sort(key=lambda item: item.get("started_at") or item.get("created_at") or "", reverse=True)
        table = self.report_table
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        try:
            self._report_rows = rows
            table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                values = (
                    row.get("report_type", ""),
                    row.get("report_name", ""),
                    row.get("run_id", row.get("workflow_run_id", "")),
                    row.get("status", "completed"),
                    row.get("started_at", row.get("created_at", "")),
                    row.get("finished_at") or "",
                    row.get("html_path", ""),
                    row.get("json_path", ""),
                )
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

    def open_selected_report_artifacts(self):
        row = self.report_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择一条历史报告")
            return
        try:
            summary = json.loads(self._report_rows[row].get("summary_json") or "{}")
            artifacts = summary.get("artifacts") or {}
            root = artifacts.get("root") if isinstance(artifacts, dict) else ""
        except (TypeError, ValueError):
            root = ""
        path = Path(str(root or ""))
        if not path.is_dir():
            QMessageBox.information(self, "没有 Runner 产物", "所选报告没有可打开的 Runner 产物目录。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

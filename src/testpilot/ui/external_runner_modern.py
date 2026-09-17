"""External Runner prototype page for the TestPilot desktop client."""
from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
import shiboken6
from PySide6.QtCore import QByteArray, QEvent, QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea,
    QTextBrowser,
    QSizePolicy, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget,
)

from testpilot.engines.suite_catalog import SuiteCatalogError, load_suite_catalog


BLUE = "#2b83ea"
NAVY = "#123f70"
MUTED = "#7190b1"
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
CANVAS = "#f4f8fc"
BORDER = "#d6e5f4"


def _svg(name: str, size: int = 24, color: str = BLUE) -> QIcon:
    render_scale = 3
    pixel_size = size * render_scale
    paths = {
        "task": "<rect x='6' y='3' width='12' height='18' rx='2'/><path d='M9 8h6M9 12h6M9 16h4'/>",
        "chart": "<path d='M4 19V5M4 19h16M7 15l4-4 3 2 5-6'/><circle cx='7' cy='15' r='1'/><circle cx='11' cy='11' r='1'/><circle cx='14' cy='13' r='1'/><circle cx='19' cy='7' r='1'/>",
        "catalog": "<path d='M12 3 4 7l8 4 8-4-8-4ZM4 12l8 4 8-4M4 17l8 4 8-4'/>",
        "settings": "<path d='M4 7h16M4 12h16M4 17h16'/><circle cx='8' cy='7' r='2'/><circle cx='15' cy='12' r='2'/><circle cx='11' cy='17' r='2'/>",
        "confirm": "<circle cx='12' cy='12' r='8'/><path d='m8.5 12 2.3 2.4 4.8-5'/>",
        "view": "<path d='M2.5 12s3.2-5.5 9.5-5.5S21.5 12 21.5 12 18.3 17.5 12 17.5 2.5 12 2.5 12z'/><circle cx='12' cy='12' r='2.5'/>",
        "download": "<path d='M12 3v11M8 10l4 4 4-4M4 19h16'/>",
        "delete": "<path d='M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5'/>",
        "check": "<path d='m6 12 4 4 8-9'/>",
        "refresh": "<path d='M20 6v5h-5M4 18v-5h5'/><path d='M18.2 9A7 7 0 0 0 6.5 6.5L4 9M5.8 15A7 7 0 0 0 17.5 17.5L20 15'/>",
    }
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{size}' height='{size}' viewBox='0 0 24 24'>"
           f"<g fill='none' stroke='{color}' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'>{paths[name]}</g></svg>")
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(pixel_size, pixel_size); pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing); renderer.render(painter); painter.end()
    pixmap.setDevicePixelRatio(render_scale)
    return QIcon(pixmap)


class _BlueCheckBox(QCheckBox):
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box_size = 20
        box = QRectF(1, (self.height() - box_size) / 2, box_size, box_size)
        checked = self.isChecked()
        fill = QColor(BLUE if self.isEnabled() else "#91b9df") if checked else QColor("#ffffff")
        border = fill if checked else QColor("#aebfd0")
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(fill)
        painter.drawRoundedRect(box, 4, 4)
        if checked:
            mark = QPainterPath()
            mark.moveTo(box.left() + 5, box.center().y())
            mark.lineTo(box.left() + 9, box.bottom() - 5)
            mark.lineTo(box.right() - 4, box.top() + 5)
            pen = QPen(QColor("#ffffff"), 2.2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(mark)
        painter.setPen(QColor("#2677cf" if checked else "#365674"))
        painter.drawText(
            self.rect().adjusted(box_size + 10, 0, 0, 0),
            Qt.AlignLeft | Qt.AlignVCenter,
            self.text(),
        )


class _BelowPopupComboBox(QComboBox):
    """Keep the choices below the field so the current value remains visible."""

    def showPopup(self) -> None:
        super().showPopup()
        popup = self.view().window()
        if popup is None:
            return
        popup.setMinimumWidth(max(self.width(), popup.minimumWidth()))
        anchor = self.mapToGlobal(QPoint(0, self.height()))
        screen = self.screen()
        available = screen.availableGeometry() if screen else None
        popup_height = popup.height() or popup.sizeHint().height()
        if available and anchor.y() + popup_height > available.bottom():
            anchor.setY(self.mapToGlobal(QPoint(0, 0)).y() - popup_height)
        popup.move(anchor)


def _text(value: str, name: str = "", *, wrap: bool = False) -> QLabel:
    label = QLabel(value)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def _card(name: str) -> QFrame:
    card = QFrame()
    card.setObjectName(name)
    card.setFrameShape(QFrame.StyledPanel)
    return card


def _rule() -> QFrame:
    line = QFrame(); line.setObjectName("RunnerRule")
    line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Plain)
    return line


def _run_with_loading(button, callback, busy_text: str = "加载中…") -> None:
    """Give every Runner action a small, paintable response before it runs."""
    if button.property("runnerBusy"):
        return
    button.setProperty("runnerBusy", True)
    original_text = button.text()
    original_icon = button.icon()
    original_style = button.toolButtonStyle() if isinstance(button, QToolButton) else None
    button.setEnabled(False)
    if isinstance(button, QToolButton):
        button.setIcon(QIcon())
        button.setText("…")
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
    else:
        button.setText(busy_text)

    def restore() -> None:
        if not shiboken6.isValid(button):
            return
        if isinstance(button, QToolButton):
            button.setText(original_text)
            button.setIcon(original_icon)
            button.setToolButtonStyle(original_style)
        elif button.text() == busy_text:
            button.setText(original_text)
            button.setIcon(original_icon)
        button.setEnabled(True)
        button.setProperty("runnerBusy", False)

    def invoke() -> None:
        try:
            callback()
        finally:
            QTimer.singleShot(180, restore)

    QTimer.singleShot(0, invoke)


def _bind_loading(button, callback, busy_text: str = "加载中…") -> None:
    button.clicked.connect(lambda _checked=False: _run_with_loading(button, callback, busy_text))


def _parse_timestamp(value) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _format_local_timestamp(value) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return "—"
    return parsed.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def _duration_seconds(record: dict) -> int | None:
    started = _parse_timestamp(record.get("started_at") or record.get("created_at"))
    if started is None:
        return None
    finished = _parse_timestamp(record.get("finished_at"))
    status = str(record.get("status") or "").lower()
    if finished is None and status != "running":
        return None
    if finished is None:
        finished = datetime.now(started.tzinfo)
    return max(0, int((finished - started).total_seconds()))


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds} 秒"
    minutes, second = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} 分 {second} 秒"
    hours, minute = divmod(minutes, 60)
    return f"{hours} 小时 {minute} 分"


def _heading(icon: str, title: str, hint: str = "", code: str = "") -> QWidget:
    box = QWidget(); box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0); row.setSpacing(12)
    mark = QLabel(); mark.setObjectName("RunnerHeadingIcon")
    mark.setPixmap(_svg(icon, 24).pixmap(24, 24)); mark.setFixedSize(42, 42); mark.setAlignment(Qt.AlignCenter)
    copy = QWidget(); stack = QVBoxLayout(copy); stack.setContentsMargins(0, 0, 0, 0); stack.setSpacing(2)
    stack.addWidget(_text(title, "RunnerHeadingTitle"))
    if hint:
        stack.addWidget(_text(hint, "RunnerHeadingHint"))
    row.addWidget(mark, 0, Qt.AlignVCenter); row.addWidget(copy, 1, Qt.AlignVCenter)
    if code:
        row.addWidget(_text(code, "RunnerHeadingCode"), 0, Qt.AlignVCenter)
    return box


class _SuiteRow(QFrame):
    def __init__(self, suite, index: int, select_callback):
        super().__init__()
        self.suite = suite
        self.setObjectName("RunnerSuiteChoice")
        self.setCursor(Qt.PointingHandCursor)
        self._select_callback = select_callback
        self.setMinimumHeight(112)
        layout = QHBoxLayout(self); layout.setContentsMargins(24, 16, 22, 16); layout.setSpacing(18)
        number = _text(f"{index:02d}", "RunnerSuiteNumber")
        number.setFixedWidth(38)
        body = QWidget(); stack = QVBoxLayout(body); stack.setContentsMargins(0, 0, 0, 0); stack.setSpacing(5)
        title_row = QHBoxLayout(); title_row.setContentsMargins(0, 0, 0, 0); title_row.setSpacing(8)
        title_row.addWidget(_text(suite.name, "RunnerSuiteName"))
        risk = {"readonly": "只读", "mutation": "需授权确认", "offline": "离线"}.get(suite.risk, suite.risk)
        title_row.addWidget(_text(risk, "RunnerRiskTag")); title_row.addStretch()
        stack.addLayout(title_row)
        stack.addWidget(_text(f"{suite.description}    预计 {max(1, suite.timeout_seconds // 60)} 分钟", "RunnerSuiteDescription", wrap=True))
        self.check = QLabel(); self.check.setObjectName("RunnerSuiteCheck"); self.check.setFixedSize(28, 28); self.check.setAlignment(Qt.AlignCenter)
        layout.addWidget(number, 0, Qt.AlignVCenter); layout.addWidget(body, 1, Qt.AlignVCenter); layout.addWidget(self.check, 0, Qt.AlignVCenter)
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.check.setProperty("selected", selected)
        self.check.setPixmap(_svg("check", 17, "#ffffff").pixmap(17, 17) if selected else QPixmap())
        self.style().unpolish(self); self.style().polish(self)
        self.check.style().unpolish(self.check); self.check.style().polish(self.check)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._select_callback(self)
        super().mousePressEvent(event)


def _catalog_root(window) -> Path:
    registered = None
    if getattr(window, "current_project_id", None):
        registered = window.db.get_runner_by_name(window.current_project_id, "steelmill-runner")
    return Path(str((registered or {}).get("working_directory") or Path.cwd()))


def _catalog_suites(window) -> tuple:
    root = _catalog_root(window)
    try:
        return load_suite_catalog(root)
    except SuiteCatalogError:
        return ()


def _compact_suite_name(value) -> str:
    text = str(value or "").strip()
    positions = [position for mark in ("（", "(") if (position := text.find(mark)) >= 0]
    return text[:min(positions)].rstrip() if positions else text


def _status(status: str) -> tuple[str, str, str]:
    states = {
        "passed": ("已通过", "#e8f8ef", "#148349"),
        "failed": ("未通过", "#fff0f0", "#d94d4d"),
        "error": ("执行异常", "#fff0f0", "#d94d4d"),
        "queued": ("排队中", "#fff3db", "#a86912"),
        "running": ("执行中", "#eaf4ff", "#267acb"),
        "pending_approval": ("待人工审批", "#fff3db", "#a86912"),
        "rejected": ("已驳回", "#f2f4f7", "#66788a"),
        "cancelled": ("已取消", "#f2f4f7", "#66788a"),
    }
    return states.get(status, (status or "未知", "#f2f4f7", "#66788a"))


_FLOW_SCENARIOS = {
    "room-queue-outbound": "整炉装载 · 队列流转 · 正常出库",
    "box-queue-outbound": "单料箱装载 · 队列流转 · 正常出库",
    "box-all-outbound": "单料箱装载 · 整体流转 · 正常出库",
    "box-queue-rework": "单料箱装载 · 队列流转 · 返修复测（不出库）",
}


def _scenario_id(case_id: object) -> str:
    value = str(case_id or "")
    if "[" in value and value.endswith("]"):
        return value.rsplit("[", 1)[-1][:-1]
    return value.rsplit("::", 1)[-1]


def _runner_artifacts_root(record: dict) -> Path | None:
    result = record.get("result") or {}
    root = (result.get("artifacts") or {}).get("root") or record.get("artifacts_dir")
    if not str(root or "").strip():
        return None
    path = Path(str(root))
    return path if path.is_dir() else None


def _execution_content_text(record: dict) -> str:
    manifest = record.get("manifest") or {}
    result = record.get("result") or {}
    selection = manifest.get("selection") or {}
    policy = manifest.get("policy") or {}
    summary = result.get("summary") or {}
    paths = selection.get("paths") or []
    markers = selection.get("markers") or []
    lines = [
        "本次测试做了什么",
        f"测试文件：{', '.join(map(str, paths)) or '—'}",
        f"测试标记：{', '.join(map(str, markers)) or '—'}",
        f"执行策略：{'允许写入并在结束后清理测试数据' if policy.get('allow_mutation') else '只读'}；"
        f"串行度 {policy.get('parallel_workers', 1)}；超时 {policy.get('timeout_seconds', '—')} 秒",
        f"执行结果：共 {summary.get('total', 0)} 项，通过 {summary.get('passed', 0)} 项，"
        f"失败 {summary.get('failed', 0)} 项，异常 {summary.get('error', 0)} 项",
    ]
    error = str(result.get("error") or "").strip()
    if error:
        lines.append(f"失败原因：{error}")
    result_metadata = result.get("metadata") or {}
    source_items = [
        ("Git SHA", result_metadata.get("git_sha")),
        ("CI 任务", result_metadata.get("ci_job_url")),
        ("CI Job ID", result_metadata.get("ci_job_id")),
        ("执行节点", result_metadata.get("runner_host")),
    ]
    source_text = "；".join(f"{label}：{value}" for label, value in source_items if value)
    if source_text:
        lines.append(f"执行来源：{source_text}")
    root = _runner_artifacts_root(record)
    log_path = root / "runner.log" if root is not None else None
    if log_path is not None and log_path.is_file():
        try:
            warning_count = log_path.read_text(encoding="utf-8", errors="replace").count(
                "PytestUnhandledThreadExceptionWarning: Exception in thread"
            )
        except OSError:
            warning_count = 0
        if warning_count:
            lines.append(
                f"执行提示：Runner 日志记录 {warning_count} 条子进程输出解码警告；"
                "本次业务断言全部通过，但建议检查运行环境编码。"
            )
    lines.extend(["", "测试场景"])
    cases = result.get("cases") or []
    if not cases:
        lines.append("任务尚未返回具体测试场景。")
    for index, case in enumerate(cases, 1):
        scenario = _scenario_id(case.get("id") or case.get("name"))
        label = _FLOW_SCENARIOS.get(scenario, scenario)
        status = "通过" if case.get("status") == "passed" else str(case.get("status") or "未知")
        duration = _format_duration(round(float(case.get("duration_ms") or 0) / 1000))
        lines.append(f"{index}. {label} ｜ {status} ｜ {duration}")
    lines.extend(
        [
            "",
            "每个现场作业场景均校验：物料数量与条码一致、完整状态链存在、状态记录关联入库明细、"
            "出库数量符合预期、炉室格位已释放、内部状态时间顺序正确。",
        ]
    )
    return "\n".join(lines)


def _flow_data_text(record: dict) -> str:
    root = _runner_artifacts_root(record)
    if root is None:
        return "任务尚未产生可读取的流转数据。"
    flow_root = root / "artifacts" / "process_flow"
    if not flow_root.is_dir():
        return "该套件没有输出现场作业流转数据；可在“执行结果”中查看 Runner 返回内容。"
    sections = []
    case_order = {
        _scenario_id(case.get("id") or case.get("name")): index
        for index, case in enumerate((record.get("result") or {}).get("cases") or [])
    }
    scenario_dirs = (path for path in flow_root.iterdir() if path.is_dir())
    for scenario_dir in sorted(scenario_dirs, key=lambda path: case_order.get(path.name, 10_000)):
        result_path = scenario_dir / "result.json"
        if not result_path.is_file():
            continue
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            sections.append(f"{_FLOW_SCENARIOS.get(scenario_dir.name, scenario_dir.name)}\n读取失败：{exc}")
            continue
        barcodes = payload.get("barcodes") or []
        batch_trace = payload.get("batchTrace") or {}
        items = batch_trace.get("items") or []
        sample = items[0] if items else {}
        product = sample.get("product") or {}
        nodes = sample.get("traceNodes") or []
        node_names = [
            str(node.get("nodeName") or node.get("materialStatusName") or "未知节点")
            for node in nodes
        ]
        barcode_range = "—"
        if barcodes:
            barcode_range = str(barcodes[0]) if len(barcodes) == 1 else f"{barcodes[0]} ～ {barcodes[-1]}"
        outcome = "返修后完成质检，按场景要求不出库" if payload.get("rework") else (
            "完成质检并正常出库" if payload.get("outbound") else "完成质检"
        )
        batch = batch_trace.get("batch") or {}
        sections.append(
            "\n".join(
                [
                    _FLOW_SCENARIOS.get(scenario_dir.name, scenario_dir.name),
                    f"批次号：{payload.get('batchNo') or '—'}",
                    f"测试物料：{payload.get('materialCount', len(barcodes))} 件；条码范围：{barcode_range}",
                    f"供应商 / 规格：{batch.get('supplierName') or '—'} / {batch.get('specName') or '—'}",
                    f"最后记录位置 / 最终状态：{product.get('positionText') or '—'} / "
                    f"{product.get('currentStatusName') or '—'}；质检：{product.get('inspectionResultName') or '—'}",
                    f"场景结论：{outcome}",
                    f"代表条码：{sample.get('barcode') or '—'}（共 {sample.get('nodeCount', len(nodes))} 个轨迹节点）",
                    "流转轨迹：" + (" → ".join(node_names) if node_names else "—"),
                ]
            )
        )
    return "\n\n".join(sections) if sections else "未找到可读取的现场作业场景产物。"


def _result_summary_text(record: dict) -> str:
    result = record.get("result") or {}
    summary = result.get("summary") or {}
    if not summary:
        return "等待 Runner 返回"
    total = int(summary.get("total") or 0)
    passed = int(summary.get("passed") or 0)
    failed = int(summary.get("failed") or 0) + int(summary.get("error") or 0)
    if total and failed == 0 and passed == total:
        return f"{passed} / {total} 通过"
    if total:
        return f"{passed} / {total} 通过 · {failed} 失败"
    return "无测试项"


def _readable_detail_html(value: str) -> str:
    sections = [section.splitlines() for section in str(value or "").split("\n\n") if section.strip()]
    output = [
        "<style>",
        "body{font-family:'Microsoft YaHei UI';font-size:13px;color:#294f72;background:#fff;margin:8px;}",
        ".section{background:#f8fbff;border:1px solid #d8e7f5;border-radius:8px;margin:0 0 10px 0;padding:11px 13px;}",
        ".title{font-size:15px;font-weight:700;color:#123f70;margin-bottom:8px;}",
        ".row{margin:4px 0;line-height:1.55;}",
        ".label{color:#7890a8;}",
        ".value{color:#294f72;font-weight:600;}",
        ".scenario{background:#fff;border-left:3px solid #2b83ea;padding:7px 10px;margin:6px 0;}",
        ".trace{background:#eef6ff;color:#24679f;padding:8px 10px;margin-top:7px;line-height:1.65;}",
        ".warning{background:#fff7e8;color:#9b6719;border:1px solid #f0d7a6;padding:8px 10px;margin:7px 0;}",
        ".note{color:#577796;line-height:1.65;}",
        "</style>",
    ]
    for lines in sections:
        output.append("<div class='section'>")
        output.append(f"<div class='title'>{html.escape(lines[0])}</div>")
        for line in lines[1:]:
            escaped = html.escape(line)
            stripped = line.strip()
            if stripped.startswith("执行提示："):
                output.append(f"<div class='warning'>{escaped}</div>")
            elif stripped[:1].isdigit() and ". " in stripped[:4]:
                output.append(f"<div class='scenario'>{escaped}</div>")
            elif stripped.startswith("流转轨迹："):
                output.append(f"<div class='trace'>{escaped}</div>")
            elif "：" in line:
                label, content = line.split("：", 1)
                output.append(
                    f"<div class='row'><span class='label'>{html.escape(label)}：</span>"
                    f"<span class='value'>{html.escape(content)}</span></div>"
                )
            else:
                output.append(f"<div class='note'>{escaped}</div>")
        output.append("</div>")
    return "".join(output)


def _build_results_tab(window) -> QWidget:
    tab = QWidget(); tab.setObjectName("RunnerResultsTab")
    layout = QVBoxLayout(tab); layout.setContentsMargins(0, 12, 0, 0); layout.setSpacing(14)
    metrics = QHBoxLayout(); metrics.setSpacing(16)
    window.runner_metrics = {}
    for key, label in (("today", "今日任务"), ("pass_rate", "通过率（7 天）"), ("queued", "执行中 / 排队"), ("latest", "平均耗时")):
        card = _card("RunnerMetricCard"); c = QVBoxLayout(card); c.setContentsMargins(28, 22, 28, 22); c.setSpacing(12)
        c.addWidget(_text(label, "RunnerMetricLabel")); value = _text("--", "RunnerMetricValue"); c.addWidget(value)
        window.runner_metrics[key] = value; metrics.addWidget(card, 1)
    layout.addLayout(metrics)

    card = _card("RunnerResultsCard"); body = QVBoxLayout(card); body.setContentsMargins(28, 25, 28, 26); body.setSpacing(16)
    head = QHBoxLayout(); head.addWidget(_heading("chart", "测试任务与结果", "执行中的任务不可编辑；请复制为新任务后调整。")); head.addStretch()
    refresh = QPushButton("刷新数据"); refresh.setObjectName("RunnerGhostButton")
    refresh.setIcon(_svg("refresh", 17)); refresh.setIconSize(QSize(17, 17))
    _bind_loading(refresh, window.refresh_external_runner_runs, "刷新中…"); head.addWidget(refresh)
    body.addLayout(head)
    filters = QHBoxLayout(); filters.setSpacing(12)
    search = QLineEdit(); search.setPlaceholderText("搜索任务、run_id、工单、套件或环境…"); search.setObjectName("RunnerResultsSearch")
    state = _BelowPopupComboBox()
    for label, value in (("全部状态", ""), ("已通过", "passed"), ("执行中", "running"), ("排队中", "queued"), ("未通过", "failed"), ("执行异常", "error")):
        state.addItem(label, value)
    module = _BelowPopupComboBox(); module.addItems(["全部模块"])
    for control in (state, module): control.setObjectName("RunnerInputCombo")
    filter_button = QPushButton("筛选"); filter_button.setObjectName("RunnerPrimaryAction")
    reset = QPushButton("重置"); reset.setObjectName("RunnerGhostButton")
    filters.addWidget(search, 1); filters.addWidget(state); filters.addWidget(module); filters.addWidget(filter_button); filters.addWidget(reset)
    body.addLayout(filters)
    window.runner_result_search = search
    window.runner_result_state = state
    window.runner_result_module = module
    count = _text("共 0 条任务", "RunnerResultsCount"); body.addWidget(count)
    window.runner_result_count = count
    table = QTableWidget(0, 7); table.setObjectName("RunnerRunTable")
    table.setHorizontalHeaderLabels(["任务", "任务工单", "测试套件", "环境", "状态", "执行时间", "操作"])
    table.setSelectionBehavior(QAbstractItemView.SelectRows); table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setFocusPolicy(Qt.NoFocus)
    table.setAlternatingRowColors(False); table.verticalHeader().setVisible(False); table.verticalHeader().setDefaultSectionSize(56)
    table.setMinimumHeight(300); table.setMaximumHeight(500)
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.Stretch)
    header.setSectionResizeMode(1, QHeaderView.Fixed); table.setColumnWidth(1, 150)
    header.setSectionResizeMode(2, QHeaderView.Stretch)
    header.setSectionResizeMode(3, QHeaderView.Fixed); table.setColumnWidth(3, 140)
    header.setSectionResizeMode(4, QHeaderView.Fixed); table.setColumnWidth(4, 160)
    header.setSectionResizeMode(5, QHeaderView.Fixed); table.setColumnWidth(5, 140)
    header.setSectionResizeMode(6, QHeaderView.Fixed); table.setColumnWidth(6, 136)
    window.runner_run_table = table
    body.addWidget(table)

    detail = _card("RunnerDetailCard"); detail.setVisible(False)
    detail_layout = QVBoxLayout(detail); detail_layout.setContentsMargins(24, 20, 24, 22); detail_layout.setSpacing(14)
    detail_head = QHBoxLayout()
    detail_title_box = QWidget()
    detail_title_layout = QVBoxLayout(detail_title_box)
    detail_title_layout.setContentsMargins(0, 0, 0, 0); detail_title_layout.setSpacing(2)
    detail_title = _text("任务详情", "RunnerDetailTitle")
    detail_title_layout.addWidget(detail_title)
    detail_title_layout.addWidget(_text("查看任务范围、执行时间线与 Runner 返回结果。", "RunnerHeadingHint"))
    close_detail = QPushButton("收起"); close_detail.setObjectName("RunnerGhostButton")
    detail_head.addWidget(detail_title_box); detail_head.addStretch(); detail_head.addWidget(close_detail); detail_layout.addLayout(detail_head)
    detail_grid = QGridLayout(); detail_grid.setHorizontalSpacing(10); detail_grid.setVerticalSpacing(10)
    detail_values = {}
    fields = (
        ("task_id", "平台任务"), ("status", "执行状态"), ("result_summary", "执行结果"),
        ("suite", "测试套件"), ("environment", "运行环境"),
        ("work_order", "任务工单"), ("run_id", "Runner run_id"), ("started", "开始时间"),
        ("finished", "完成时间"), ("duration", "执行耗时"),
    )
    for index, (key, label) in enumerate(fields):
        field = QFrame(); field.setObjectName("RunnerDetailField")
        field_layout = QVBoxLayout(field); field_layout.setContentsMargins(13, 10, 13, 11); field_layout.setSpacing(4)
        field_layout.addWidget(_text(label, "RunnerDetailLabel"))
        value = _text("—", "RunnerDetailStatus" if key == "status" else "RunnerDetailValue", wrap=True)
        if key == "status":
            value.setAlignment(Qt.AlignCenter); value.setFixedHeight(28); value.setMaximumWidth(112)
        field_layout.addWidget(value); detail_values[key] = value
        detail_grid.addWidget(field, index // 5, index % 5)
    for column in range(5):
        detail_grid.setColumnStretch(column, 1)
    detail_layout.addLayout(detail_grid)
    detail_error = _text("", "RunnerDetailError", wrap=True); detail_error.setVisible(False); detail_layout.addWidget(detail_error)
    detail_tabs = QTabWidget(); detail_tabs.setObjectName("RunnerDetailTabs")
    content_view = QTextBrowser(); content_view.setObjectName("RunnerReadableDetail")
    flow_view = QTextBrowser(); flow_view.setObjectName("RunnerReadableDetail")
    for readable_view in (content_view, flow_view):
        readable_view.setOpenExternalLinks(False)
        readable_view.setFrameShape(QFrame.NoFrame)
    manifest_view = QPlainTextEdit(); manifest_view.setReadOnly(True)
    result_view = QPlainTextEdit(); result_view.setReadOnly(True)
    detail_tabs.addTab(content_view, "测试内容")
    detail_tabs.addTab(flow_view, "流转数据")
    detail_tabs.addTab(manifest_view, "原始 Manifest")
    detail_tabs.addTab(result_view, "原始结果")
    detail_tabs.setFixedHeight(330); detail_layout.addWidget(detail_tabs)
    detail_actions = QHBoxLayout(); open_artifacts = QPushButton("打开产物目录"); open_artifacts.setObjectName("RunnerGhostButton")
    copy_detail = QPushButton("复制详情 JSON"); copy_detail.setObjectName("RunnerGhostButton")
    detail_actions.addStretch(); detail_actions.addWidget(open_artifacts); detail_actions.addWidget(copy_detail); detail_layout.addLayout(detail_actions)
    body.addWidget(detail)
    window.runner_detail_card = detail
    window.runner_detail_title = detail_title
    window.runner_detail_values = detail_values
    window.runner_detail_error = detail_error
    window.runner_detail_content = content_view
    window.runner_detail_flow = flow_view
    window.runner_detail_manifest = manifest_view
    window.runner_detail_result = result_view
    window.runner_detail_open = open_artifacts
    window.runner_detail_copy = copy_detail
    _bind_loading(close_detail, detail.hide, "收起中…")
    _bind_loading(open_artifacts, lambda: _open_detail_artifacts(window), "打开中…")
    _bind_loading(copy_detail, lambda: _copy_run_detail(window), "复制中…")

    _bind_loading(filter_button, lambda: _apply_result_filters(window), "筛选中…")
    _bind_loading(reset, lambda: _reset_result_filters(window), "重置中…")
    search.returnPressed.connect(lambda: _run_with_loading(filter_button, lambda: _apply_result_filters(window), "筛选中…"))
    table.cellClicked.connect(lambda row, _column: _show_run_detail(window, window._runner_run_rows[row]) if 0 <= row < len(getattr(window, "_runner_run_rows", [])) else None)
    body.addStretch()
    layout.addWidget(card, 0, Qt.AlignTop)
    layout.addStretch()
    return tab


def _record_module(window, record: dict) -> str:
    manifest = record.get("manifest") or {}
    metadata = manifest.get("metadata") or {}
    module = str(metadata.get("module") or "").strip()
    if module:
        return module
    suite_name = str(metadata.get("suite") or "")
    for suite in getattr(window, "_runner_suites", ()):
        if suite.name == suite_name:
            return suite.module
    return ""


def _apply_result_filters(window) -> None:
    query = window.runner_result_search.text().strip().lower()
    status_filter = str(window.runner_result_state.currentData() or "")
    module_filter = window.runner_result_module.currentText()
    visible = []
    for record in getattr(window, "_runner_all_rows", []):
        manifest = record.get("manifest") or {}
        metadata = manifest.get("metadata") or {}
        status = str(record.get("status") or "queued").lower()
        module = _record_module(window, record)
        searchable = " ".join(str(value) for value in (
            record.get("id"), record.get("run_key"), metadata.get("test_name"),
            metadata.get("work_order"), metadata.get("suite"), module,
            record.get("environment_name"), status,
        ) if value is not None).lower()
        if query and query not in searchable:
            continue
        if status_filter and status != status_filter:
            continue
        if module_filter != "全部模块" and module != module_filter:
            continue
        visible.append(record)
    _render_result_rows(window, visible)


def _reset_result_filters(window) -> None:
    window.runner_result_search.clear()
    window.runner_result_state.setCurrentIndex(0)
    window.runner_result_module.setCurrentIndex(0)
    _render_result_rows(window, list(getattr(window, "_runner_all_rows", [])))


def _show_run_detail(window, record: dict) -> None:
    manifest = record.get("manifest") or {}
    metadata = manifest.get("metadata") or {}
    result = record.get("result") or {}
    status_text, _background, _foreground = _status(str(record.get("status") or "queued").lower())
    duration = _format_duration(_duration_seconds(record))
    values = {
        "task_id": f"#{record.get('id', '—')}",
        "status": status_text,
        "result_summary": _result_summary_text(record),
        "suite": _compact_suite_name(metadata.get("suite") or manifest.get("suite") or "—"),
        "environment": record.get("environment_name") or manifest.get("environment_id") or "—",
        "work_order": metadata.get("work_order") or "未关联",
        "run_id": record.get("run_key") or "—",
        "started": _format_local_timestamp(record.get("started_at")),
        "finished": _format_local_timestamp(record.get("finished_at")),
        "duration": duration,
    }
    for key, value in values.items():
        window.runner_detail_values[key].setText(str(value))
    window.runner_detail_values["status"].setStyleSheet(
        f"background:{_background};color:{_foreground};border:1px solid {_background};"
        "border-radius:14px;padding:0 12px;font-weight:700;"
    )
    window.runner_detail_values["result_summary"].setStyleSheet(
        f"color:{_foreground};font-weight:700;"
    )
    task_name = metadata.get("test_name") or "未命名任务"
    window.runner_detail_title.setText(f"任务详情 · #{record.get('id', '—')} {task_name}")
    error = str(result.get("error") or "").strip()
    window.runner_detail_error.setText(f"执行说明：{error}")
    window.runner_detail_error.setVisible(bool(error))
    window.runner_detail_content.setHtml(_readable_detail_html(_execution_content_text(record)))
    window.runner_detail_flow.setHtml(_readable_detail_html(_flow_data_text(record)))
    window.runner_detail_manifest.setPlainText(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    window.runner_detail_result.setPlainText(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) if result else "任务尚未产生执行结果。"
    )
    window._runner_detail_record = record
    window.runner_detail_card.setVisible(True)
    for index, row in enumerate(getattr(window, "_runner_run_rows", [])):
        if int(row.get("id", -1)) == int(record.get("id", -2)):
            window.runner_run_table.selectRow(index)
            break


def _open_detail_artifacts(window) -> None:
    record = getattr(window, "_runner_detail_record", None)
    if not record:
        return
    for index, row in enumerate(getattr(window, "_runner_run_rows", [])):
        if int(row.get("id", -1)) == int(record.get("id", -2)):
            window.open_runner_artifacts(index)
            return


def _copy_run_detail(window) -> None:
    record = getattr(window, "_runner_detail_record", None)
    if not record:
        return
    payload = {"manifest": record.get("manifest") or {}, "result": record.get("result") or {}}
    QApplication.clipboard().setText(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    window.statusBar().showMessage("任务详情 JSON 已复制。", 3000)


def _render_result_rows(window, rows: list[dict]) -> None:
    window._runner_run_rows = rows
    table = window.runner_run_table
    visible_rows = min(max(len(rows), 2), 7)
    table.setFixedHeight(50 + visible_rows * table.verticalHeader().defaultSectionSize())
    table.blockSignals(True); table.setRowCount(len(rows))
    try:
        for index, record in enumerate(rows):
            manifest = record.get("manifest") or {}; metadata = manifest.get("metadata") or {}
            task_name = str(metadata.get("test_name") or "未命名任务")
            task = f"#{record.get('id', '—')} {task_name}"
            full_suite = str(metadata.get("suite") or manifest.get("suite") or "—")
            values = (
                task,
                str(metadata.get("work_order") or "—"),
                _compact_suite_name(full_suite),
                str(record.get("environment_name") or manifest.get("environment_id") or "—"),
                "",
                _format_duration(_duration_seconds(record)),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(full_suite if column == 2 else str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable); table.setItem(index, column, item)
            status, background, foreground = _status(str(record.get("status") or "queued").lower())
            badge = QLabel(status); badge.setObjectName("RunnerStatusBadge"); badge.setAlignment(Qt.AlignCenter)
            badge.setFixedSize(116, 34); badge.setStyleSheet(f"background:{background};color:{foreground};")
            status_cell = QWidget(); status_cell.setObjectName("RunnerStatusCell")
            status_layout = QHBoxLayout(status_cell); status_layout.setContentsMargins(4, 0, 4, 0)
            status_layout.addStretch(); status_layout.addWidget(badge); status_layout.addStretch()
            table.setCellWidget(index, 4, status_cell)
            actions = QWidget(); actions.setObjectName("RunnerTableActions")
            action_layout = QHBoxLayout(actions); action_layout.setContentsMargins(4, 0, 4, 0); action_layout.setSpacing(8)
            action_layout.addStretch()
            callbacks = (
                ("view", "在下方查看任务详情", lambda record=record: _show_run_detail(window, record)),
                ("download", "打开产物目录", lambda i=index: window.open_runner_artifacts(i)),
                ("delete", "删除任务", lambda i=index: window.delete_runner_task(i)),
            )
            for kind, tip, callback in callbacks:
                button = QToolButton(); button.setIcon(_svg(kind, 22)); button.setIconSize(QSize(22, 22))
                button.setAutoRaise(True); button.setToolTip(tip); button.setFixedSize(34, 34)
                _bind_loading(button, callback, "处理中…"); action_layout.addWidget(button)
            action_layout.addStretch(); table.setCellWidget(index, 6, actions)
    finally:
        table.blockSignals(False)
    window.runner_result_count.setText(f"显示 {len(rows)} / {len(getattr(window, '_runner_all_rows', rows))} 条任务")


def _build_catalog_tab(window, suites, tabs) -> QWidget:
    tab = QWidget(); tab.setObjectName("RunnerCatalogTab")
    layout = QVBoxLayout(tab); layout.setContentsMargins(0, 12, 0, 0); layout.setSpacing(14)
    card = _card("RunnerCatalogCard"); body = QVBoxLayout(card); body.setContentsMargins(24, 22, 24, 24); body.setSpacing(14)
    head = QHBoxLayout(); head.addWidget(_heading("catalog", "测试套件目录", "从测试分支的 config/test_suites.yaml 受控加载。")); head.addStretch()
    refresh = QPushButton("刷新目录"); refresh.setObjectName("RunnerGhostButton")
    refresh.setIcon(_svg("refresh", 17)); refresh.setIconSize(QSize(17, 17))
    _bind_loading(refresh, lambda: _reload_catalog(window, tabs), "刷新中…"); head.addWidget(refresh); body.addLayout(head)
    query = QLineEdit(); query.setObjectName("RunnerSuiteSearch"); query.setPlaceholderText("搜索套件、标签或路径…"); body.addWidget(query)
    pills = QHBoxLayout(); pills.addWidget(_text(f"全部 {len(suites)}", "RunnerCatalogPill")); pills.addStretch()
    visible_count = _text(f"显示 {len(suites)} / {len(suites)} 个套件", "RunnerCatalogCount")
    pills.addWidget(visible_count); body.addLayout(pills)

    detail = QDialog(window); detail.setObjectName("RunnerSuiteDialog")
    detail.setWindowTitle("测试套件范围"); detail.setWindowModality(Qt.WindowModal); detail.setModal(True)
    detail.setMinimumSize(760, 500); detail.resize(820, 540)
    detail_layout = QVBoxLayout(detail); detail_layout.setContentsMargins(24, 20, 24, 22); detail_layout.setSpacing(14)
    detail_head = QHBoxLayout()
    detail_title = _text("套件详情", "RunnerDetailTitle")
    detail_hint = _text("查看测试范围，也可以编辑目录中的展示信息与执行策略。", "RunnerHeadingHint")
    title_box = QWidget(); title_layout = QVBoxLayout(title_box); title_layout.setContentsMargins(0, 0, 0, 0); title_layout.setSpacing(2)
    title_layout.addWidget(detail_title); title_layout.addWidget(detail_hint)
    close = QPushButton("关闭"); close.setObjectName("RunnerGhostButton")
    detail_head.addWidget(title_box, 1); detail_head.addWidget(close); detail_layout.addLayout(detail_head)

    fields = {}
    editor_grid = QGridLayout(); editor_grid.setHorizontalSpacing(14); editor_grid.setVerticalSpacing(8)
    name = QLineEdit(); module = QLineEdit(); manifest = QLineEdit(); manifest.setReadOnly(True)
    risk = _BelowPopupComboBox(); risk.setObjectName("RunnerInputCombo")
    for label, value in (("只读", "readonly"), ("离线", "offline"), ("需授权确认", "mutation")):
        risk.addItem(label, value)
    timeout = QSpinBox(); timeout.setRange(1, 7200); timeout.setSuffix(" 秒")
    description = QPlainTextEdit(); description.setObjectName("RunnerSuiteDescriptionEditor"); description.setMaximumHeight(82)
    for key, label, widget, row, column, column_span in (
        ("name", "套件名称", name, 0, 0, 1),
        ("module", "所属模块", module, 0, 1, 1),
        ("risk", "风险类型", risk, 0, 2, 1),
        ("timeout", "默认超时", timeout, 2, 0, 1),
        ("manifest", "Manifest 路径（只读）", manifest, 2, 1, 2),
    ):
        editor_grid.addWidget(_text(label, "RunnerFieldLabel"), row, column, 1, column_span)
        editor_grid.addWidget(widget, row + 1, column, 1, column_span)
        fields[key] = widget
    editor_grid.addWidget(_text("套件说明", "RunnerFieldLabel"), 4, 0, 1, 3)
    editor_grid.addWidget(description, 5, 0, 1, 3); fields["description"] = description
    for column in range(3):
        editor_grid.setColumnStretch(column, 1)
    detail_layout.addLayout(editor_grid)
    edit_status = _text("", "RunnerSuiteEditStatus", wrap=True); edit_status.setVisible(False)
    actions = QHBoxLayout(); edit = QPushButton("编辑套件"); edit.setObjectName("RunnerGhostButton")
    cancel = QPushButton("取消"); cancel.setObjectName("RunnerGhostButton"); cancel.setVisible(False)
    save = QPushButton("保存修改"); save.setObjectName("RunnerPrimaryAction"); save.setVisible(False)
    actions.addWidget(edit_status, 1); actions.addStretch(); actions.addWidget(edit); actions.addWidget(cancel); actions.addWidget(save)
    detail_layout.addLayout(actions)
    window.runner_catalog_detail = detail
    window.runner_catalog_detail_title = detail_title
    window.runner_catalog_fields = fields
    window.runner_catalog_edit = edit
    window.runner_catalog_cancel = cancel
    window.runner_catalog_save = save
    window.runner_catalog_edit_status = edit_status
    _bind_loading(close, detail.reject, "关闭中…")
    _bind_loading(edit, lambda: _set_suite_editor_mode(window, True), "编辑中…")
    _bind_loading(cancel, lambda: _cancel_suite_edit(window), "取消中…")
    _bind_loading(save, lambda: _save_suite_edit(window), "保存中…")

    grid = QGridLayout(); grid.setHorizontalSpacing(14); grid.setVerticalSpacing(14); grid.setAlignment(Qt.AlignTop)
    for column in range(3):
        grid.setColumnStretch(column, 1)
    cards = []
    for index, suite in enumerate(suites):
        item = _card("RunnerCatalogSuite"); item.setFixedHeight(188); box = QVBoxLayout(item); box.setContentsMargins(18, 15, 18, 14); box.setSpacing(6)
        title = QHBoxLayout(); icon = QLabel(); icon.setPixmap(_svg("catalog", 19).pixmap(19, 19)); icon.setFixedSize(19, 19); icon.setAlignment(Qt.AlignCenter)
        name = _text(suite.name, "RunnerCatalogName", wrap=True); name.setMaximumHeight(40)
        title.addWidget(icon, 0, Qt.AlignTop); title.addWidget(name, 1); box.addLayout(title)
        description = _text(suite.description, "RunnerCatalogDescription", wrap=True); description.setMaximumHeight(36); box.addWidget(description)
        tagrow = QHBoxLayout(); tagrow.addWidget(_text({"readonly":"只读", "mutation":"需授权确认", "offline":"离线"}.get(suite.risk, suite.risk), "RunnerRiskTag")); tagrow.addWidget(_text(suite.module, "RunnerModuleTag")); tagrow.addStretch(); box.addLayout(tagrow)
        box.addWidget(_text(f"模块：{suite.module} · 默认超时：{suite.timeout_seconds} 秒", "RunnerCatalogMeta")); box.addStretch()
        footer = QHBoxLayout(); footer.setSpacing(8); scope = QPushButton("查看范围"); create = QPushButton("创建任务 ›")
        for button in (scope, create): button.setObjectName("RunnerCatalogAction")
        _bind_loading(scope, lambda suite=suite: _show_suite_scope(window, suite), "加载中…")
        _bind_loading(create, lambda i=index: _choose_suite(window, i, tabs), "选择中…")
        footer.addWidget(scope); footer.addStretch(); footer.addWidget(create); box.addLayout(footer)
        grid.addWidget(item, index // 3, index % 3); cards.append((item, suite))
    body.addLayout(grid); layout.addWidget(card, 0, Qt.AlignTop)
    def filter_catalog(text: str) -> None:
        shown = 0
        for item, suite in cards:
            visible = not text or text.lower() in (suite.name + suite.module + suite.description).lower()
            item.setVisible(visible)
            shown += int(visible)
        visible_count.setText(f"显示 {shown} / {len(suites)} 个套件")
    query.textChanged.connect(filter_catalog)
    return tab


def _choose_suite(window, index: int, tabs) -> None:
    if 0 <= index < window.auto_runner_suite.count():
        window.auto_runner_suite.setCurrentIndex(index)
    _update_preview(window)
    tabs.setCurrentIndex(0)


def _show_suite_scope(window, suite) -> None:
    fields = window.runner_catalog_fields
    window._runner_catalog_selected_suite = suite
    window.runner_catalog_detail_title.setText(f"套件详情 · {_compact_suite_name(suite.name)}")
    fields["name"].setText(suite.name)
    fields["module"].setText(suite.module)
    fields["manifest"].setText(suite.manifest)
    fields["description"].setPlainText(suite.description)
    fields["timeout"].setValue(suite.timeout_seconds)
    risk_index = fields["risk"].findData(suite.risk)
    fields["risk"].setCurrentIndex(max(0, risk_index))
    catalog_path = _catalog_root(window) / "config" / "test_suites.yaml"
    window.runner_catalog_edit.setEnabled(catalog_path.is_file())
    window.runner_catalog_edit.setToolTip(
        "编辑 config/test_suites.yaml 中的此套件" if catalog_path.is_file() else "内置默认套件没有可编辑的目录文件"
    )
    window.runner_catalog_edit_status.setVisible(False)
    _set_suite_editor_mode(window, False)
    window.runner_catalog_detail.show()
    window.runner_catalog_detail.raise_()
    window.runner_catalog_detail.activateWindow()


def _set_suite_editor_mode(window, editing: bool) -> None:
    fields = window.runner_catalog_fields
    for key in ("name", "module"):
        fields[key].setReadOnly(not editing)
    fields["description"].setReadOnly(not editing)
    fields["risk"].setEnabled(editing)
    fields["timeout"].setReadOnly(not editing)
    fields["timeout"].setButtonSymbols(QSpinBox.UpDownArrows if editing else QSpinBox.NoButtons)
    window.runner_catalog_edit.setVisible(not editing)
    window.runner_catalog_cancel.setVisible(editing)
    window.runner_catalog_save.setVisible(editing)
    window.runner_catalog_edit_status.setVisible(False)
    if editing:
        fields["name"].setFocus()
        fields["name"].selectAll()


def _cancel_suite_edit(window) -> None:
    suite = getattr(window, "_runner_catalog_selected_suite", None)
    if suite is not None:
        _show_suite_scope(window, suite)


def _show_suite_edit_error(window, message: str) -> None:
    window.runner_catalog_edit_status.setText(message)
    window.runner_catalog_edit_status.setVisible(True)


def _save_suite_edit(window) -> None:
    suite = getattr(window, "_runner_catalog_selected_suite", None)
    if suite is None:
        return
    root = _catalog_root(window)
    catalog_path = root / "config" / "test_suites.yaml"
    if not catalog_path.is_file():
        _show_suite_edit_error(window, "内置默认套件不可直接编辑，请先在 Runner 工作目录创建 config/test_suites.yaml。")
        return
    fields = window.runner_catalog_fields
    name = fields["name"].text().strip()
    module = fields["module"].text().strip()
    description = fields["description"].toPlainText().strip()
    risk = str(fields["risk"].currentData() or "")
    timeout = fields["timeout"].value()
    if not name or not module or not description:
        _show_suite_edit_error(window, "套件名称、所属模块和套件说明不能为空。")
        return
    original = ""
    temporary = catalog_path.with_suffix(".yaml.testpilot.tmp")
    try:
        original = catalog_path.read_text(encoding="utf-8")
        payload = yaml.safe_load(original)
        if not isinstance(payload, dict) or not isinstance(payload.get("suites"), list):
            raise SuiteCatalogError("test_suites.yaml 结构无效")
        target = next((item for item in payload["suites"] if isinstance(item, dict) and str(item.get("id")) == suite.id), None)
        if target is None:
            raise SuiteCatalogError(f"目录中未找到套件：{suite.id}")
        target.update({
            "name": name,
            "module": module,
            "description": description,
            "risk": risk,
            "timeout_seconds": timeout,
            "approval_required": risk == "mutation",
        })
        temporary.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
        temporary.replace(catalog_path)
        try:
            load_suite_catalog(root)
        except SuiteCatalogError:
            catalog_path.write_text(original, encoding="utf-8")
            raise
    except (OSError, ValueError, yaml.YAMLError, SuiteCatalogError) as exc:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        _show_suite_edit_error(window, f"保存失败：{exc}")
        return
    window.statusBar().showMessage(f"测试套件“{name}”已保存到目录。", 4000)
    window.runner_catalog_detail.accept()
    QTimer.singleShot(240, lambda: _reload_catalog(window, window.runner_tabs))


def _sync_suite_selector(window, suites) -> None:
    if not hasattr(window, "auto_runner_suite"):
        return
    selected = window.auto_runner_suite.currentData()
    window._runner_suites = suites
    window.auto_runner_suite.blockSignals(True); window.auto_runner_suite.clear()
    for suite in suites:
        window.auto_runner_suite.addItem(suite.name, suite.manifest.removeprefix("examples/"))
    index = window.auto_runner_suite.findData(selected)
    window.auto_runner_suite.setCurrentIndex(index if index >= 0 else (0 if suites else -1))
    window.auto_runner_suite.blockSignals(False)
    if hasattr(window, "runner_suite_count"):
        window.runner_suite_count.setText(f"{len(suites)} 个可选")
    if hasattr(window, "runner_context_suites"):
        window.runner_context_suites.setText(f"{len(suites)} 个测试套件")
    if hasattr(window, "runner_execute_button"):
        window.runner_execute_button.setEnabled(bool(suites))
    if hasattr(window, "runner_module"):
        selected_module = window.runner_module.currentText()
        window.runner_module.clear()
        for suite in suites:
            if window.runner_module.findText(suite.module) < 0:
                window.runner_module.addItem(suite.module)
        module_index = window.runner_module.findText(selected_module)
        window.runner_module.setCurrentIndex(module_index if module_index >= 0 else (0 if suites else -1))
    _update_preview(window)


def _reload_catalog(window, tabs) -> None:
    current = tabs.currentIndex()
    suites = _catalog_suites(window)
    _sync_suite_selector(window, suites)
    old_detail = getattr(window, "runner_catalog_detail", None)
    if old_detail is not None:
        old_detail.close()
        old_detail.deleteLater()
    old_catalog = getattr(window, "_runner_catalog_tab", None)
    old_index = tabs.indexOf(old_catalog) if old_catalog is not None else -1
    if old_index >= 0:
        tabs.removeTab(old_index)
    catalog = _build_catalog_tab(window, suites, tabs)
    window._runner_catalog_tab = catalog
    tabs.addTab(catalog, _svg("catalog"), "测试套件目录")
    tabs.setCurrentIndex(min(current, tabs.count() - 1))


def _update_preview(window) -> None:
    index = window.auto_runner_suite.currentIndex()
    suites = getattr(window, "_runner_suites", ())
    if not (0 <= index < len(suites)):
        return
    suite = suites[index]
    window.runner_preview_suite.setText(suite.name)
    window.runner_preview_risk.setText({"readonly": "只读", "mutation": "可清理写入", "offline": "离线"}.get(suite.risk, suite.risk))
    window.runner_preview_scope.setText(suite.module)
    if hasattr(window, "runner_suite_summary"):
        risk = {"readonly": "只读", "mutation": "需授权确认", "offline": "离线"}.get(suite.risk, suite.risk)
        window.runner_suite_summary.setText(
            f"{suite.description}  ·  模块：{suite.module}  ·  {risk}  ·  预计 {max(1, suite.timeout_seconds // 60)} 分钟"
        )


def _draft_key(window) -> str:
    return f"external_runner_draft:{getattr(window, 'current_project_id', None) or 0}"


def _save_runner_draft(window) -> None:
    payload = {
        "task_name": window.runner_task_name.text(),
        "work_order": window.runner_work_order.text(),
        "environment": window.auto_runner_environment.currentData(),
        "module": window.runner_module.currentText(),
        "suite": window.auto_runner_suite.currentData(),
    }
    window.db.set_setting(_draft_key(window), json.dumps(payload, ensure_ascii=False))
    window.auto_runner_status.setText("草稿已保存；环境授权确认不会随草稿保存。")
    window.auto_runner_status.setVisible(True)
    window.statusBar().showMessage("外部 Runner 任务草稿已保存。", 3000)


def _restore_runner_draft(window) -> None:
    try:
        payload = json.loads(window.db.get_setting(_draft_key(window), "{}") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict) or not payload:
        return
    window.runner_task_name.setText(str(payload.get("task_name") or window.runner_task_name.text()))
    window.runner_work_order.setText(str(payload.get("work_order") or ""))
    for combo, value in (
        (window.auto_runner_environment, payload.get("environment")),
        (window.runner_module, payload.get("module")),
        (window.auto_runner_suite, payload.get("suite")),
    ):
        index = combo.findData(value)
        if index < 0:
            index = combo.findText(str(value or ""))
        if index >= 0:
            combo.setCurrentIndex(index)
    _update_preview(window)


def modern_external_runner_page(window):
    suites = _catalog_suites(window)
    window._runner_suites = suites
    shell = QScrollArea(); shell.setObjectName("RunnerWorkspace"); shell.setWidgetResizable(True)
    window.runner_workspace_shell = shell
    shell.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); shell.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    page = QWidget(); page.setObjectName("RunnerWorkspaceContent"); page.setMinimumWidth(1020)
    root = QVBoxLayout(page); root.setContentsMargins(34, 26, 34, 30); root.setSpacing(16)
    shell.setWidget(page)

    top = QHBoxLayout(); top.addWidget(_text("外部 Runner", "RunnerPageTitle")); top.addStretch(); top.addWidget(_text("● 运行中", "RunnerOnlineBadge")); root.addLayout(top)
    root.addWidget(_text("从已登记、版本受控的测试套件创建任务；平台生成 Manifest，并由 SteelMill Runner 执行和归档结果。", "RunnerPageSubtitle"))
    banner = _card("RunnerContextBar"); b = QHBoxLayout(banner); b.setContentsMargins(20, 13, 20, 13); b.setSpacing(14)
    window.runner_context_project = _text("当前项目：未选择", "RunnerContextStrong")
    window.runner_context_runner = _text("Runner：未配置", "RunnerContextValue")
    window.runner_context_suites = _text(f"{len(suites)} 个测试套件", "RunnerContextValue")
    b.addWidget(window.runner_context_project)
    b.addWidget(_text("·", "RunnerContextDivider"))
    b.addWidget(window.runner_context_runner)
    b.addWidget(_text("·", "RunnerContextDivider"))
    b.addWidget(window.runner_context_suites)
    b.addStretch()
    advanced = QPushButton("高级设置 ›"); advanced.setObjectName("RunnerGhostButton"); b.addWidget(advanced); root.addWidget(banner)

    advanced_panel = _card("RunnerAdvancedPanel"); advanced_panel.setVisible(False); advanced_layout = QGridLayout(advanced_panel); advanced_layout.setContentsMargins(24, 18, 24, 18); advanced_layout.setHorizontalSpacing(14); advanced_layout.setVerticalSpacing(8)
    window.runner_name = QLineEdit("steelmill-runner"); window.runner_version = QLineEdit("0.1.0"); window.runner_image = QLineEdit("registry.example.com/steelmill/runner:0.1.0")
    window.runner_project_key = QLineEdit("steelmill"); window.runner_python_executable = QLineEdit(); window.runner_workdir = QLineEdit(); window.runner_enabled = _BlueCheckBox("启用此 Runner"); window.runner_enabled.setChecked(True)
    window.runner_save_status = _text("", "RunnerFieldHint")
    fields = (("Runner 名称", window.runner_name), ("Runner 版本", window.runner_version), ("镜像标识", window.runner_image), ("项目 Adapter Key", window.runner_project_key), ("SteelMill Python", window.runner_python_executable), ("工作目录", window.runner_workdir))
    for i, (name, field) in enumerate(fields):
        row, col = divmod(i, 2); advanced_layout.addWidget(_text(name, "RunnerFieldLabel"), row * 2, col); advanced_layout.addWidget(field, row * 2 + 1, col)
    advanced_layout.addWidget(window.runner_enabled, 6, 0); advanced_layout.addWidget(window.runner_save_status, 6, 1)
    save = QPushButton("保存当前配置"); save.setObjectName("RunnerPrimaryAction")
    _bind_loading(save, window.save_external_runner, "保存中…"); advanced_layout.addWidget(save, 7, 1)
    root.addWidget(advanced_panel)

    tabs = QTabWidget(); tabs.setObjectName("RunnerCenterTabs"); tabs.setIconSize(QSize(22, 22))
    tabs.setDocumentMode(True); tabs.tabBar().setExpanding(False); tabs.tabBar().setFixedHeight(50)
    root.addWidget(tabs)
    create = QWidget(); create.setObjectName("RunnerCreateTab"); outer = QHBoxLayout(create); outer.setContentsMargins(0, 12, 0, 0); outer.setSpacing(18)
    form = _card("RunnerTaskForm"); form.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    fl = QVBoxLayout(form); fl.setContentsMargins(26, 24, 26, 24); fl.setSpacing(12); fl.setAlignment(Qt.AlignTop)
    fl.addWidget(_heading("task", "任务信息", "为本次执行建立可追溯的任务记录", "JOB / 01"))
    grid1 = QGridLayout(); grid1.setHorizontalSpacing(18); grid1.setVerticalSpacing(5); grid1.setAlignment(Qt.AlignTop)
    window.runner_task_name = QLineEdit("炉室状态回归 - 2026/09/15"); window.auto_runner_test_name = window.runner_task_name
    window.runner_work_order = QLineEdit(); window.runner_work_order.setPlaceholderText("例如：SM-248 炉室状态调整")
    for column, title, field in ((0, "任务名称 *", window.runner_task_name), (1, "关联开发工单（可选）", window.runner_work_order)):
        grid1.addWidget(_text(title, "RunnerFieldLabel"), 0, column); grid1.addWidget(field, 1, column)
    fl.addLayout(grid1); fl.addWidget(_rule())
    fl.addWidget(_heading("settings", "执行上下文", "选择本次任务所属的环境与业务范围", "SCOPE / 02"))
    grid2 = QGridLayout(); grid2.setHorizontalSpacing(18); grid2.setVerticalSpacing(5); grid2.setAlignment(Qt.AlignTop)
    window.auto_runner_environment = _BelowPopupComboBox(); window.auto_runner_environment.setObjectName("RunnerInputCombo")
    window.auto_runner_environment.addItem("测试环境 · 本机 127.0.0.1:5010", "测试环境")
    window.runner_module = _BelowPopupComboBox(); window.runner_module.setObjectName("RunnerInputCombo")
    for suite in suites:
        if window.runner_module.findText(suite.module) < 0: window.runner_module.addItem(suite.module)
    if not suites: window.runner_module.addItem("现场作业")
    for column, title, field in ((0, "运行环境 *", window.auto_runner_environment), (1, "改动模块 *", window.runner_module)):
        grid2.addWidget(_text(title, "RunnerFieldLabel"), 0, column); grid2.addWidget(field, 1, column)
    fl.addLayout(grid2); fl.addWidget(_rule())
    suite_header = QHBoxLayout(); suite_header.addWidget(_heading("catalog", "测试套件", "从已登记、通过质量门禁的动态套件目录中选择")); suite_header.addStretch()
    window.runner_suite_count = _text(f"{len(suites)} 个可选", "RunnerCatalogCount")
    suite_header.addWidget(window.runner_suite_count); fl.addLayout(suite_header)
    fl.addWidget(_text("选择测试套件 *", "RunnerFieldLabel"))
    window.auto_runner_suite = _BelowPopupComboBox(); window.auto_runner_suite.setObjectName("RunnerInputCombo")
    window.auto_runner_suite.setMaxVisibleItems(12)
    for suite in suites:
        window.auto_runner_suite.addItem(suite.name, suite.manifest.removeprefix("examples/"))
    fl.addWidget(window.auto_runner_suite)
    window.runner_suite_summary = _text("暂无可用测试套件，请检查 Runner 工作目录。", "RunnerSuiteSummary", wrap=True)
    fl.addWidget(window.runner_suite_summary)
    window.auto_runner_suite.currentIndexChanged.connect(lambda _index: _update_preview(window))
    window.runner_mutation_confirmation = _BlueCheckBox("我已确认仅在已授权测试环境执行，并允许创建、流转和清理测试数据")
    fl.addWidget(window.runner_mutation_confirmation)
    fl.addWidget(_text("该确认即为执行前的人工授权；确认后任务会直接进入排队或执行状态。", "RunnerPreviewHint", wrap=True))
    window.auto_runner_status = _text("", "RunnerFieldHint"); window.auto_runner_status.setVisible(False); fl.addWidget(window.auto_runner_status)
    fl.addStretch(1)

    preview = _card("RunnerPreviewCard"); preview.setFixedWidth(360); pl = QVBoxLayout(preview); pl.setContentsMargins(26, 24, 26, 24); pl.setSpacing(12)
    pl.addWidget(_heading("confirm", "执行确认", "请确认此任务的执行范围与风险策略。")); pl.addWidget(_rule())
    assigned = _card("RunnerAssignedRunner"); al = QHBoxLayout(assigned); al.setContentsMargins(16, 13, 16, 13); al.setSpacing(10)
    al.addWidget(_text("●", "RunnerAssignedDot"), 0, Qt.AlignVCenter); copy = QWidget(); cs = QVBoxLayout(copy); cs.setContentsMargins(0, 0, 0, 0); cs.setSpacing(1); cs.addWidget(_text("ASSIGNED RUNNER", "RunnerAssignedCaption")); cs.addWidget(_text("steelmill-runner", "RunnerAssignedName")); al.addWidget(copy, 1, Qt.AlignVCenter); al.addWidget(_text("v0.1.0", "RunnerAssignedVersion"), 0, Qt.AlignVCenter); pl.addWidget(assigned)
    window.runner_preview_suite = _text("未选择", "RunnerPreviewValue"); window.runner_preview_risk = _text("只读", "RunnerPreviewRisk"); window.runner_preview_scope = _text("现场作业", "RunnerPreviewValue")
    for label, value in (("测试套件", window.runner_preview_suite), ("风险等级", window.runner_preview_risk), ("选择范围", window.runner_preview_scope), ("执行策略", _text("立即执行", "RunnerPreviewValue")), ("清理策略", _text("ResourceLedger 逆序清理", "RunnerPreviewValue"))):
        item = QWidget(); il = QVBoxLayout(item); il.setContentsMargins(0, 8, 0, 8); il.setSpacing(3); il.addWidget(_text(label, "RunnerPreviewLabel")); il.addWidget(value); pl.addWidget(item); pl.addWidget(_rule())
    pl.addWidget(_text("任务开始后，Manifest、环境和选择范围不可编辑。", "RunnerPreviewHint", wrap=True))
    run = QPushButton("创建并执行"); run.setObjectName("RunnerPrimaryAction")
    def execute():
        if not window.runner_mutation_confirmation.isChecked():
            window.auto_runner_status.setText("请先确认授权测试环境与数据清理许可。"); window.auto_runner_status.setVisible(True); return
        window.run_registered_steelmill()
    _bind_loading(run, execute, "正在创建…")
    window.runner_execute_button = run
    run.setEnabled(bool(suites))
    draft = QPushButton("保存为草稿"); draft.setObjectName("RunnerGhostButton")
    _bind_loading(draft, lambda: _save_runner_draft(window), "保存中…")
    pl.addWidget(run); pl.addWidget(draft); pl.addStretch()
    outer.addWidget(form, 3); outer.addWidget(preview, 2); tabs.addTab(create, _svg("task"), "创建任务")
    results = _build_results_tab(window); window._runner_results_tab = results
    catalog = _build_catalog_tab(window, suites, tabs); window._runner_catalog_tab = catalog
    tabs.addTab(catalog, _svg("catalog"), "测试套件目录")
    window.runner_tabs = tabs
    def toggle_advanced() -> None:
        if tabs.currentIndex() != 0:
            return
        advanced_panel.setVisible(not advanced_panel.isVisible())
        advanced.setText("收起设置 ›" if advanced_panel.isVisible() else "高级设置 ›")

    def remember_scroll(_index: int) -> None:
        window._runner_tab_scroll_position = shell.verticalScrollBar().value()

    def tab_changed(index: int) -> None:
        on_create_tab = index == 0
        advanced.setEnabled(on_create_tab)
        if not on_create_tab:
            advanced_panel.hide()
            advanced.setText("高级设置 ›")
        previous = int(getattr(window, "_runner_tab_scroll_position", shell.verticalScrollBar().value()))
        QTimer.singleShot(
            0,
            lambda value=previous: shell.verticalScrollBar().setValue(
                min(value, shell.verticalScrollBar().maximum())
            ),
        )

    _bind_loading(advanced, toggle_advanced, "加载中…")
    tabs.tabBar().tabBarClicked.connect(remember_scroll)
    tabs.currentChanged.connect(tab_changed)
    tab_changed(tabs.currentIndex())
    _update_preview(window)
    _restore_runner_draft(window)
    return shell


def refresh_external_runner_runs(window):
    if not hasattr(window, "runner_run_table"):
        return
    project_name = window.projects.currentText().strip() if window.current_project_id else "未选择"
    if hasattr(window, "runner_context_project"):
        window.runner_context_project.setText(f"当前项目：{project_name}")
    registered = (
        window.db.get_runner_by_name(window.current_project_id, "steelmill-runner")
        if window.current_project_id else None
    )
    if hasattr(window, "runner_context_runner"):
        if registered:
            runner_name = str(registered.get("name") or "steelmill-runner")
            runner_version = str(registered.get("version") or "").strip()
            suffix = f" {runner_version}" if runner_version else ""
            window.runner_context_runner.setText(f"Runner：{runner_name}{suffix}")
        else:
            window.runner_context_runner.setText("Runner：未配置")
    environments = window.db.list_environments(window.current_project_id) if window.current_project_id else []
    selected = window.auto_runner_environment.currentData()
    window.auto_runner_environment.blockSignals(True); window.auto_runner_environment.clear()
    for environment in environments: window.auto_runner_environment.addItem(environment["name"], environment["name"])
    if window.auto_runner_environment.count() == 0: window.auto_runner_environment.addItem("测试环境 · 本机 127.0.0.1:5010", "测试环境")
    window.auto_runner_environment.setCurrentIndex(max(0, window.auto_runner_environment.findData(selected))); window.auto_runner_environment.blockSignals(False)
    rows = window.db.list_runner_runs(window.current_project_id) if window.current_project_id else []
    active_processes = getattr(window, "_external_runner_processes", {})
    for record in rows:
        status = str(record.get("status") or "")
        artifacts_dir = Path(str(record.get("artifacts_dir") or ""))
        if (
            status in {"queued", "running"}
            and bool(str(record.get("artifacts_dir") or "").strip())
            and int(record.get("id", -1)) not in active_processes
            and (artifacts_dir / "result.json").is_file()
        ):
            window._finish_registered_steelmill(int(record["id"]), artifacts_dir, 0)
            return
    window._runner_all_rows = rows
    if hasattr(window, "_backfill_runner_reports"):
        window._backfill_runner_reports(rows)
    selected_module = window.runner_result_module.currentText()
    modules = sorted({module for record in rows if (module := _record_module(window, record))})
    window.runner_result_module.blockSignals(True); window.runner_result_module.clear()
    window.runner_result_module.addItem("全部模块")
    window.runner_result_module.addItems(modules)
    module_index = window.runner_result_module.findText(selected_module)
    window.runner_result_module.setCurrentIndex(module_index if module_index >= 0 else 0)
    window.runner_result_module.blockSignals(False)
    _apply_result_filters(window)
    current_detail = getattr(window, "_runner_detail_record", None)
    if current_detail and window.runner_detail_card.isVisible():
        refreshed = next((row for row in rows if int(row.get("id", -1)) == int(current_detail.get("id", -2))), None)
        if refreshed is None:
            window.runner_detail_card.hide()
        else:
            _show_run_detail(window, refreshed)
    terminal = [row for row in rows if str(row.get("status") or "") in {"passed", "error", "failed"}]
    today = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d")
    durations = [seconds for row in terminal if (seconds := _duration_seconds(row)) is not None]
    window.runner_metrics["today"].setText(
        str(sum(_format_local_timestamp(row.get("created_at")).startswith(today) for row in rows))
    )
    window.runner_metrics["pass_rate"].setText(
        f"{sum(str(row.get('status')) == 'passed' for row in terminal) / len(terminal):.1%}" if terminal else "--"
    )
    window.runner_metrics["queued"].setText(str(sum(str(row.get("status")) in {"queued", "running"} for row in rows)))
    window.runner_metrics["latest"].setText(_format_duration(round(sum(durations) / len(durations))) if durations else "--")
    tabs = window.runner_tabs
    result_index = tabs.indexOf(window._runner_results_tab)
    if rows and result_index < 0: tabs.insertTab(1, window._runner_results_tab, _svg("chart"), "任务与结果")
    if not rows and result_index >= 0: tabs.removeTab(result_index)


def install(window_cls):
    window_cls._external_runner_page = modern_external_runner_page
    window_cls.refresh_external_runner_runs = refresh_external_runner_runs

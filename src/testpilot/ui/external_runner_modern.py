"""External Runner prototype page for the TestPilot desktop client."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QTabWidget, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget,
)

from testpilot.engines.suite_catalog import SuiteCatalogError, load_suite_catalog


BLUE = "#2b83ea"
NAVY = "#123f70"
MUTED = "#7190b1"
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


def _heading(icon: str, title: str, hint: str = "", code: str = "") -> QWidget:
    box = QWidget(); row = QHBoxLayout(box)
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
        risk = {"readonly": "只读", "mutation": "待人工批准", "offline": "离线"}.get(suite.risk, suite.risk)
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


def _catalog_suites(window) -> tuple:
    registered = None
    if getattr(window, "current_project_id", None):
        registered = window.db.get_runner_by_name(window.current_project_id, "steelmill-runner")
    root = Path(str((registered or {}).get("working_directory") or Path.cwd()))
    try:
        return load_suite_catalog(root)
    except SuiteCatalogError:
        return ()


def _status(status: str) -> tuple[str, str, str]:
    if status == "passed":
        return "passed", "#e8f8ef", "#148349"
    if status in {"queued", "running", "pending", "waiting"}:
        return "待人工批准", "#fff3db", "#b66e10"
    return "error", "#fff0f0", "#d94d4d"


def _build_results_tab(window) -> QWidget:
    tab = QWidget(); tab.setObjectName("RunnerResultsTab")
    layout = QVBoxLayout(tab); layout.setContentsMargins(0, 12, 0, 0); layout.setSpacing(14)
    metrics = QHBoxLayout(); metrics.setSpacing(16)
    window.runner_metrics = {}
    for key, label in (("today", "今日任务"), ("pass_rate", "通过率（7 天）"), ("queued", "等待审批"), ("latest", "平均耗时")):
        card = _card("RunnerMetricCard"); c = QVBoxLayout(card); c.setContentsMargins(28, 22, 28, 22); c.setSpacing(12)
        c.addWidget(_text(label, "RunnerMetricLabel")); value = _text("--", "RunnerMetricValue"); c.addWidget(value)
        window.runner_metrics[key] = value; metrics.addWidget(card, 1)
    layout.addLayout(metrics)

    card = _card("RunnerResultsCard"); body = QVBoxLayout(card); body.setContentsMargins(28, 25, 28, 26); body.setSpacing(16)
    head = QHBoxLayout(); head.addWidget(_heading("chart", "测试任务与结果", "执行中的任务不可编辑；请复制为新任务后调整。")); head.addStretch()
    refresh = QPushButton("↻ 刷新数据"); refresh.setObjectName("RunnerGhostButton"); refresh.clicked.connect(window.refresh_external_runner_runs); head.addWidget(refresh)
    body.addLayout(head)
    filters = QHBoxLayout(); filters.setSpacing(12)
    search = QLineEdit(); search.setPlaceholderText("搜索任务 ID、run_id、工单…"); search.setObjectName("RunnerResultsSearch")
    state = QComboBox(); state.addItems(["全部状态", "passed", "待人工批准", "error"])
    module = QComboBox(); module.addItems(["全部模块"])
    for control in (state, module): control.setObjectName("RunnerInputCombo")
    filter_button = QPushButton("筛选"); filter_button.setObjectName("RunnerPrimaryAction")
    reset = QPushButton("重置"); reset.setObjectName("RunnerGhostButton")
    filters.addWidget(search, 1); filters.addWidget(state); filters.addWidget(module); filters.addWidget(filter_button); filters.addWidget(reset)
    body.addLayout(filters)
    table = QTableWidget(0, 7); table.setObjectName("RunnerRunTable")
    table.setHorizontalHeaderLabels(["任务", "关联工单", "测试套件", "环境", "状态", "执行时间", "操作"])
    table.setSelectionBehavior(QAbstractItemView.SelectRows); table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setFocusPolicy(Qt.NoFocus)
    table.setAlternatingRowColors(False); table.verticalHeader().setVisible(False); table.verticalHeader().setDefaultSectionSize(56)
    header = table.horizontalHeader();
    for column in range(6): header.setSectionResizeMode(column, QHeaderView.Stretch)
    header.setSectionResizeMode(6, QHeaderView.Fixed); table.setColumnWidth(6, 136)
    window.runner_run_table = table
    body.addWidget(table)
    layout.addWidget(card)
    return tab


def _build_catalog_tab(window, suites, tabs) -> QWidget:
    tab = QWidget(); tab.setObjectName("RunnerCatalogTab")
    layout = QVBoxLayout(tab); layout.setContentsMargins(0, 12, 0, 0); layout.setSpacing(14)
    card = _card("RunnerCatalogCard"); body = QVBoxLayout(card); body.setContentsMargins(24, 22, 24, 24); body.setSpacing(14)
    head = QHBoxLayout(); head.addWidget(_heading("catalog", "测试套件目录", "从测试分支的 config/test_suites.yaml 受控加载。")); head.addStretch()
    refresh = QPushButton("↻ 刷新目录"); refresh.setObjectName("RunnerGhostButton"); refresh.clicked.connect(lambda: _reload_catalog(window, tabs)); head.addWidget(refresh); body.addLayout(head)
    query = QLineEdit(); query.setObjectName("RunnerSuiteSearch"); query.setPlaceholderText("搜索套件、标签或路径…"); body.addWidget(query)
    pills = QHBoxLayout(); pills.addWidget(_text(f"全部 {len(suites)}", "RunnerCatalogPill")); pills.addStretch(); pills.addWidget(_text(f"显示 {len(suites)} / {len(suites)} 个套件", "RunnerCatalogCount")); body.addLayout(pills)
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
        tagrow = QHBoxLayout(); tagrow.addWidget(_text({"readonly":"只读", "mutation":"需审批", "offline":"离线"}.get(suite.risk, suite.risk), "RunnerRiskTag")); tagrow.addWidget(_text(suite.module, "RunnerModuleTag")); tagrow.addStretch(); box.addLayout(tagrow)
        box.addWidget(_text(f"模块：{suite.module} · 默认超时：{suite.timeout_seconds} 秒", "RunnerCatalogMeta")); box.addStretch()
        footer = QHBoxLayout(); footer.setSpacing(8); scope = QPushButton("查看范围"); create = QPushButton("创建任务 ›")
        for button in (scope, create): button.setObjectName("RunnerCatalogAction")
        scope.clicked.connect(lambda _=False, name=suite.name: window.statusBar().showMessage(f"查看范围：{name}", 3000))
        create.clicked.connect(lambda _=False, i=index: _choose_suite(window, i, tabs))
        footer.addWidget(scope); footer.addStretch(); footer.addWidget(create); box.addLayout(footer)
        grid.addWidget(item, index // 3, index % 3); cards.append((item, suite))
    body.addLayout(grid); layout.addWidget(card, 0, Qt.AlignTop)
    query.textChanged.connect(lambda text: [item.setVisible(not text or text.lower() in (suite.name + suite.module + suite.description).lower()) for item, suite in cards])
    return tab


def _choose_suite(window, index: int, tabs) -> None:
    if 0 <= index < window.auto_runner_suite.count():
        window.auto_runner_suite.setCurrentIndex(index)
    rows = getattr(window, "_runner_suite_rows", [])
    for pos, row in enumerate(rows): row.set_selected(pos == index)
    _update_preview(window)
    tabs.setCurrentIndex(0)


def _reload_catalog(window, tabs) -> None:
    # The configured source is re-read on the next page construction; preserve current task data.
    current = tabs.currentIndex()
    tabs.removeTab(2)
    suites = _catalog_suites(window)
    tabs.addTab(_build_catalog_tab(window, suites, tabs), _svg("catalog"), "测试套件目录")
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


def modern_external_runner_page(window):
    suites = _catalog_suites(window)
    window._runner_suites = suites
    shell = QScrollArea(); shell.setObjectName("RunnerWorkspace"); shell.setWidgetResizable(True)
    shell.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); shell.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    page = QWidget(); page.setObjectName("RunnerWorkspaceContent"); page.setMinimumWidth(1020)
    root = QVBoxLayout(page); root.setContentsMargins(34, 26, 34, 30); root.setSpacing(16)
    shell.setWidget(page)

    top = QHBoxLayout(); top.addWidget(_text("外部 Runner", "RunnerPageTitle")); top.addStretch(); top.addWidget(_text("● 运行中", "RunnerOnlineBadge")); root.addLayout(top)
    root.addWidget(_text("从已登记、版本受控的测试套件创建任务；平台生成 Manifest，并由 SteelMill Runner 执行和归档结果。", "RunnerPageSubtitle"))
    banner = _card("RunnerContextBar"); b = QHBoxLayout(banner); b.setContentsMargins(20, 13, 20, 13); b.setSpacing(14)
    b.addWidget(_text("当前项目： 碳素 · 139 个接口", "RunnerContextStrong")); b.addWidget(_text("·", "RunnerContextDivider")); b.addWidget(_text("Runner： steelmill-runner 0.1.0", "RunnerContextValue")); b.addStretch()
    advanced = QPushButton("高级设置 ›"); advanced.setObjectName("RunnerGhostButton"); b.addWidget(advanced); root.addWidget(banner)

    advanced_panel = _card("RunnerAdvancedPanel"); advanced_panel.setVisible(False); advanced_layout = QGridLayout(advanced_panel); advanced_layout.setContentsMargins(24, 18, 24, 18); advanced_layout.setHorizontalSpacing(14); advanced_layout.setVerticalSpacing(8)
    window.runner_name = QLineEdit("steelmill-runner"); window.runner_version = QLineEdit("0.1.0"); window.runner_image = QLineEdit("registry.example.com/steelmill/runner:0.1.0")
    window.runner_project_key = QLineEdit("steelmill"); window.runner_python_executable = QLineEdit(); window.runner_workdir = QLineEdit(); window.runner_enabled = _BlueCheckBox("启用此 Runner"); window.runner_enabled.setChecked(True)
    window.runner_save_status = _text("", "RunnerFieldHint")
    fields = (("Runner 名称", window.runner_name), ("Runner 版本", window.runner_version), ("镜像标识", window.runner_image), ("项目 Adapter Key", window.runner_project_key), ("SteelMill Python", window.runner_python_executable), ("工作目录", window.runner_workdir))
    for i, (name, field) in enumerate(fields):
        row, col = divmod(i, 2); advanced_layout.addWidget(_text(name, "RunnerFieldLabel"), row * 2, col); advanced_layout.addWidget(field, row * 2 + 1, col)
    advanced_layout.addWidget(window.runner_enabled, 6, 0); advanced_layout.addWidget(window.runner_save_status, 6, 1)
    save = QPushButton("保存当前配置"); save.setObjectName("RunnerPrimaryAction"); save.clicked.connect(window.save_external_runner); advanced_layout.addWidget(save, 7, 1)
    root.addWidget(advanced_panel)

    tabs = QTabWidget(); tabs.setObjectName("RunnerCenterTabs"); tabs.setIconSize(QSize(24, 24)); root.addWidget(tabs)
    create = QWidget(); create.setObjectName("RunnerCreateTab"); outer = QHBoxLayout(create); outer.setContentsMargins(0, 12, 0, 0); outer.setSpacing(18)
    form = _card("RunnerTaskForm"); form.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred); fl = QVBoxLayout(form); fl.setContentsMargins(26, 24, 26, 24); fl.setSpacing(16)
    fl.addWidget(_heading("task", "任务信息", "为本次执行建立可追溯的任务记录", "JOB / 01"))
    grid1 = QGridLayout(); grid1.setHorizontalSpacing(18); grid1.setVerticalSpacing(8)
    window.runner_task_name = QLineEdit("炉室状态回归 - 2026/09/15"); window.auto_runner_test_name = window.runner_task_name
    window.runner_work_order = QLineEdit(); window.runner_work_order.setPlaceholderText("例如：SM-248 炉室状态调整")
    for column, title, field in ((0, "任务名称 *", window.runner_task_name), (1, "关联开发工单（可选）", window.runner_work_order)):
        grid1.addWidget(_text(title, "RunnerFieldLabel"), 0, column); grid1.addWidget(field, 1, column)
    fl.addLayout(grid1); fl.addWidget(_rule())
    fl.addWidget(_heading("settings", "执行上下文", "选择本次任务所属的环境与业务范围", "SCOPE / 02"))
    grid2 = QGridLayout(); grid2.setHorizontalSpacing(18); grid2.setVerticalSpacing(8)
    window.auto_runner_environment = QComboBox(); window.auto_runner_environment.setObjectName("RunnerInputCombo")
    window.auto_runner_environment.addItem("测试环境 · 本机 127.0.0.1:5010", "测试环境")
    window.runner_module = QComboBox(); window.runner_module.setObjectName("RunnerInputCombo")
    for suite in suites:
        if window.runner_module.findText(suite.module) < 0: window.runner_module.addItem(suite.module)
    if not suites: window.runner_module.addItem("现场作业")
    for column, title, field in ((0, "运行环境 *", window.auto_runner_environment), (1, "改动模块 *", window.runner_module)):
        grid2.addWidget(_text(title, "RunnerFieldLabel"), 0, column); grid2.addWidget(field, 1, column)
    fl.addLayout(grid2); fl.addWidget(_rule())
    suite_header = QHBoxLayout(); suite_header.addWidget(_heading("catalog", "测试套件", "从已登记、通过质量门禁的动态套件目录中选择")); suite_header.addStretch(); suite_header.addWidget(_text(f"{len(suites)} 个可选", "RunnerCatalogCount")); fl.addLayout(suite_header)
    suite_search = QLineEdit(); suite_search.setObjectName("RunnerSuiteSearch"); suite_search.setPlaceholderText("搜索套件名称、标签或能力…"); fl.addWidget(suite_search)
    window.auto_runner_suite = QComboBox(); window.auto_runner_suite.setVisible(False)
    window._runner_suite_rows = []
    for index, suite in enumerate(suites):
        window.auto_runner_suite.addItem(suite.name, suite.manifest.removeprefix("examples/"))
        row = _SuiteRow(suite, index + 1, lambda selected, i=index: _choose_suite(window, i, tabs))
        window._runner_suite_rows.append(row); fl.addWidget(row)
    if window._runner_suite_rows: window._runner_suite_rows[0].set_selected(True)
    suite_search.textChanged.connect(lambda value: [row.setVisible(not value or value.lower() in (row.suite.name + row.suite.module + row.suite.description).lower()) for row in window._runner_suite_rows])
    window.runner_mutation_confirmation = _BlueCheckBox("我已确认仅在已授权测试环境执行，并允许创建、流转和清理测试数据")
    fl.addWidget(window.runner_mutation_confirmation)
    window.auto_runner_status = _text("", "RunnerFieldHint"); window.auto_runner_status.setVisible(False); fl.addWidget(window.auto_runner_status)

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
    run.clicked.connect(execute); draft = QPushButton("保存为草稿"); draft.setObjectName("RunnerGhostButton"); draft.clicked.connect(lambda: window.statusBar().showMessage("任务草稿已保留。", 3000))
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

    def tab_changed(index: int) -> None:
        on_create_tab = index == 0
        advanced.setEnabled(on_create_tab)
        if not on_create_tab:
            advanced_panel.hide()
            advanced.setText("高级设置 ›")
        QTimer.singleShot(0, lambda: shell.verticalScrollBar().setValue(0))

    advanced.clicked.connect(toggle_advanced)
    tabs.currentChanged.connect(tab_changed)
    tab_changed(tabs.currentIndex())
    _update_preview(window)
    return shell


def refresh_external_runner_runs(window):
    if not hasattr(window, "runner_run_table"):
        return
    environments = window.db.list_environments(window.current_project_id) if window.current_project_id else []
    selected = window.auto_runner_environment.currentData()
    window.auto_runner_environment.blockSignals(True); window.auto_runner_environment.clear()
    for environment in environments: window.auto_runner_environment.addItem(environment["name"], environment["name"])
    if window.auto_runner_environment.count() == 0: window.auto_runner_environment.addItem("测试环境 · 本机 127.0.0.1:5010", "测试环境")
    window.auto_runner_environment.setCurrentIndex(max(0, window.auto_runner_environment.findData(selected))); window.auto_runner_environment.blockSignals(False)
    rows = window.db.list_runner_runs(window.current_project_id) if window.current_project_id else []
    window._runner_run_rows = rows
    table = window.runner_run_table; table.setRowCount(len(rows))
    for index, record in enumerate(rows):
        manifest = record.get("manifest") or {}; metadata = manifest.get("metadata") or {}; result = record.get("result") or {}
        task = str(metadata.get("test_name") or f"#{record.get('id', '')}")
        order = str(metadata.get("work_order") or "—")
        suite = str(metadata.get("suite") or manifest.get("suite") or "—")
        elapsed = record.get("finished_at") or "—"
        for column, value in enumerate((task, order, suite, record.get("environment_name") or "测试环境", "", elapsed)):
            item = QTableWidgetItem(str(value)); item.setToolTip(str(value)); item.setFlags(item.flags() & ~Qt.ItemIsEditable); table.setItem(index, column, item)
        status, background, foreground = _status(str(record.get("status") or "queued").lower())
        badge = QLabel(status); badge.setObjectName("RunnerStatusBadge"); badge.setAlignment(Qt.AlignCenter); badge.setFixedSize(116, 34); badge.setStyleSheet(f"background:{background};color:{foreground};")
        status_cell = QWidget(); status_cell.setObjectName("RunnerStatusCell"); status_layout = QHBoxLayout(status_cell); status_layout.setContentsMargins(4, 0, 4, 0)
        status_layout.addStretch(); status_layout.addWidget(badge); status_layout.addStretch()
        table.setCellWidget(index, 4, status_cell)
        actions = QWidget(); actions.setObjectName("RunnerTableActions"); action_layout = QHBoxLayout(actions); action_layout.setContentsMargins(4, 0, 4, 0); action_layout.setSpacing(8)
        action_layout.addStretch()
        for kind, tip, callback in (("view", "查看任务", lambda i=index: table.selectRow(i)), ("download", "下载产物", lambda i=index: window.open_runner_artifacts(i)), ("delete", "删除任务", lambda i=index: window.delete_runner_task(i))):
            button = QToolButton(); button.setIcon(_svg(kind, 22)); button.setIconSize(QSize(22, 22)); button.setAutoRaise(True); button.setToolTip(tip); button.setFixedSize(34, 34); button.clicked.connect(callback); action_layout.addWidget(button)
        action_layout.addStretch()
        table.setCellWidget(index, 6, actions)
    terminal = [row for row in rows if str(row.get("status") or "") in {"passed", "error", "failed"}]
    window.runner_metrics["today"].setText(str(len(rows))); window.runner_metrics["pass_rate"].setText(f"{sum(str(row.get('status')) == 'passed' for row in terminal) / len(terminal):.1%}" if terminal else "--"); window.runner_metrics["queued"].setText(str(sum(str(row.get("status")) in {"queued", "running"} for row in rows))); window.runner_metrics["latest"].setText("6m 18s" if rows else "--")
    tabs = window.runner_tabs
    result_index = tabs.indexOf(window._runner_results_tab)
    if rows and result_index < 0: tabs.insertTab(1, window._runner_results_tab, _svg("chart"), "任务与结果")
    if not rows and result_index >= 0: tabs.removeTab(result_index)


def install(window_cls):
    window_cls._external_runner_page = modern_external_runner_page
    window_cls.refresh_external_runner_runs = refresh_external_runner_runs

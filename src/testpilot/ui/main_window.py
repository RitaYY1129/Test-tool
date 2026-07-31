from __future__ import annotations

import json
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QProcess
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QSpinBox, QStackedWidget, QStyle, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from testpilot.engines.http_engine import execute_request
from testpilot.cases.generator import generate_cases, generate_plan
from testpilot.engines.batch_runner import run_cases
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
from testpilot.common.security import SecretStore, split_sensitive
from testpilot.cases.schema import TEST_GENERATION_SCHEMA, validate_generation
from testpilot.model_providers.openai_compatible import OpenAICompatibleProvider
from testpilot.model_providers.codex_cli import CodexCliProvider, find_codex
from testpilot.model_providers.ollama import OllamaProvider
from testpilot.parsers.difference_checker import compare_documents
from testpilot.domain.api import ApiDocument, ApiEndpoint, ApiParameter


class MainWindow(QMainWindow):
    def __init__(self, database):
        super().__init__()
        self.db = database
        self.secret_store = SecretStore(self.db.path.parent / "config" / "master.key")
        self.current_project_id: int | None = None
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
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(14, 12, 12, 0)
        toggle_row.addStretch()
        self.sidebar_toggle = QToolButton()
        self.sidebar_toggle.setObjectName("SidebarToggle")
        self.sidebar_toggle.setIcon(self.style().standardIcon(QStyle.SP_ArrowLeft))
        self.sidebar_toggle.setToolTip("收缩/展开侧边栏")
        self.sidebar_toggle.clicked.connect(self.toggle_sidebar)
        toggle_row.addWidget(self.sidebar_toggle)
        self.brand = QLabel("TestPilot AI")
        self.brand.setObjectName("Brand")
        self.brand_sub = QLabel("智能接口测试工作台")
        self.brand_sub.setObjectName("BrandSub")
        self.menu_container = QWidget()
        self.menu_container.setObjectName("MenuContainer")
        self.menu_layout = QVBoxLayout(self.menu_container)
        self.menu_layout.setContentsMargins(10, 8, 10, 8)
        self.menu_layout.setSpacing(8)
        self._nav_buttons = {}
        self._menu_groups = []
        self._add_sidebar_group("工作空间", QStyle.SP_DirHomeIcon, [
            ("项目中心", 0, QStyle.SP_DirIcon),
        ])
        self._add_sidebar_group("接口测试", QStyle.SP_ComputerIcon, [
            ("接口资产", 1, QStyle.SP_FileDialogDetailedView),
            ("环境与请求", 2, QStyle.SP_DriveNetIcon),
            ("用例与执行", 3, QStyle.SP_MediaPlay),
            ("历史报告", 4, QStyle.SP_FileDialogInfoView),
            ("AI 模型", 6, QStyle.SP_MessageBoxInformation),
        ])
        self._add_sidebar_group("测试能力", QStyle.SP_DesktopIcon, [
            ("能力中心", 5, QStyle.SP_FileDialogListView),
        ])
        self.menu_layout.addStretch()
        sidebar.setFixedWidth(220)
        sidebar_layout.addLayout(toggle_row)
        sidebar_layout.addWidget(self.brand)
        sidebar_layout.addWidget(self.brand_sub)
        sidebar_layout.addWidget(self.menu_container, 1)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._project_page())
        self.pages.addWidget(self._endpoint_page())
        self.pages.addWidget(self._request_page())
        self.pages.addWidget(self._cases_page())
        self.pages.addWidget(self._reports_page())
        self.pages.addWidget(self._capability_page())
        self.pages.addWidget(self._ai_settings_page())
        self._activate_page(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("就绪")
        self._sidebar_collapsed = False

    def _add_sidebar_group(self, title, icon, entries):
        group = QWidget()
        group.setObjectName("MenuGroup")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(4)
        header = QToolButton()
        header.setObjectName("MenuHeader")
        header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        header.setIcon(self.style().standardIcon(icon))
        header.setText(title)
        header.setProperty("menuText", title)
        submenu = QWidget()
        submenu.setObjectName("Submenu")
        submenu_layout = QVBoxLayout(submenu)
        submenu_layout.setContentsMargins(12, 2, 0, 2)
        submenu_layout.setSpacing(4)
        for text, page_index, item_icon in entries:
            button = QPushButton(text)
            button.setObjectName("NavItem")
            button.setIcon(self.style().standardIcon(item_icon))
            button.setProperty("menuText", text)
            button.setToolTip(text)
            button.clicked.connect(lambda checked=False, index=page_index: self._activate_page(index))
            submenu_layout.addWidget(button)
            self._nav_buttons[page_index] = button
        header.clicked.connect(lambda checked=False, panel=submenu, control=header: self._toggle_menu_group(panel, control))
        group_layout.addWidget(header)
        group_layout.addWidget(submenu)
        self.menu_layout.addWidget(group)
        self._menu_groups.append((header, submenu))

    @staticmethod
    def _toggle_menu_group(submenu, header):
        submenu.setVisible(not submenu.isVisible())
        header.setProperty("expanded", submenu.isVisible())
        header.style().unpolish(header)
        header.style().polish(header)

    def _activate_page(self, page_index):
        self.pages.setCurrentIndex(page_index)
        for index, button in self._nav_buttons.items():
            button.setProperty("active", index == page_index)
            button.style().unpolish(button)
            button.style().polish(button)

    def toggle_sidebar(self):
        self._sidebar_collapsed = not self._sidebar_collapsed
        collapsed = self._sidebar_collapsed
        self.sidebar.setFixedWidth(68 if collapsed else 220)
        self.sidebar_toggle.setIcon(
            self.style().standardIcon(QStyle.SP_ArrowRight if collapsed else QStyle.SP_ArrowLeft)
        )
        self.brand.setVisible(not collapsed)
        self.brand_sub.setVisible(not collapsed)
        for header, submenu in self._menu_groups:
            header.setText("" if collapsed else header.property("menuText"))
            header.setToolButtonStyle(Qt.ToolButtonIconOnly if collapsed else Qt.ToolButtonTextBesideIcon)
            submenu.layout().setContentsMargins(0 if collapsed else 12, 2, 0, 2)
        for button in self._nav_buttons.values():
            button.setText("" if collapsed else button.property("menuText"))

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
        row.addWidget(self.projects, 1); row.addWidget(new_btn); row.addWidget(delete_btn)
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
        title = QLabel("智能用例与执行"); title.setObjectName("PageTitle")
        subtitle = QLabel("从测试计划到用例确认、批量执行与结果分析"); subtitle.setObjectName("PageSubtitle")
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
        self.ai_status_label = QLabel("AI：未配置时使用离线规则引擎")
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
        stop_btn = QPushButton("停止任务"); stop_btn.clicked.connect(self.stop_run)
        for button in (plan_btn, generate_btn, confirm_btn, edit_btn, copy_btn, delete_case_btn, run_btn, stop_btn):
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

    def _reports_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("历史测试报告"); title.setObjectName("PageTitle")
        subtitle = QLabel("追踪每次执行结果、通过率和报告文件"); subtitle.setObjectName("PageSubtitle")
        self.report_project_label = QLabel("当前项目：未选择"); self.report_project_label.setObjectName("ContextBanner")
        refresh = QPushButton("刷新历史"); refresh.clicked.connect(self.refresh_reports)
        self.report_table = QTableWidget(0, 6)
        self.report_table.setHorizontalHeaderLabels(["运行", "状态", "开始", "结束", "HTML", "JSON"])
        self.report_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.report_detail = QTextEdit(); self.report_detail.setReadOnly(True)
        self.report_table.itemSelectionChanged.connect(self.show_report)
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(self.report_project_label); layout.addWidget(refresh)
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
            ("接口测试", "第一阶段", "可用", "路线 B 完整闭环；路线 A 支持 ASP.NET Core 与 Spring Boot 源码"),
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

    def _ai_settings_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel("AI 与 Codex"); title.setObjectName("PageTitle")
        subtitle = QLabel("选择 ChatGPT 登录、兼容 API 或本地 Ollama，统一生成可审核的接口测试用例")
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
        detect = QPushButton("检测 Codex"); detect.clicked.connect(self.check_codex_connection)
        login = QPushButton("登录 ChatGPT"); login.setProperty("primary", True); login.clicked.connect(self.login_codex)
        codex_buttons.addWidget(install); codex_buttons.addWidget(detect)
        codex_buttons.addWidget(login); codex_buttons.addStretch()
        codex_form.addRow("源码目录", source_row)
        codex_form.addRow("Codex 模型", self.codex_model)
        codex_form.addRow("账号连接", codex_buttons)
        codex_note = QLabel("使用官方 Codex CLI 的 ChatGPT 登录；TestPilot 不读取或保存登录凭证。")
        codex_note.setWordWrap(True); codex_form.addRow("", codex_note)
        self.ai_tabs.addTab(codex_tab, "Codex · ChatGPT 登录")

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

        actions = QHBoxLayout()
        save = QPushButton("保存当前配置"); save.setProperty("primary", True); save.clicked.connect(self.save_ai_settings)
        test = QPushButton("测试当前连接"); test.clicked.connect(self.test_ai_connection)
        clear = QPushButton("清除 API Token"); clear.setProperty("danger", True); clear.clicked.connect(self.clear_ai_token)
        actions.addWidget(save); actions.addWidget(test); actions.addWidget(clear); actions.addStretch()
        self.ai_connection_result = QTextEdit(); self.ai_connection_result.setReadOnly(True)
        self.ai_connection_result.setPlaceholderText("安装、登录和模型连接状态会显示在这里。")
        layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(explanation)
        layout.addWidget(self.ai_tabs); layout.addLayout(actions); layout.addWidget(self.ai_connection_result, 1)
        self._finish_page(page, layout)
        self._load_ai_settings()
        return page

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
        self.search.textChanged.connect(self.refresh_endpoints)
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
        buttons.addWidget(save); buttons.addWidget(send); buttons.addStretch()
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
        encrypted = self.db.get_setting("ai_token_encrypted")
        if encrypted:
            try:
                self.model_key.setText(self.secret_store.decrypt_dict(encrypted).get("api_key", ""))
            except Exception:
                self.model_key.clear()
        self._update_ai_status()

    def _update_ai_status(self):
        if not hasattr(self, "ai_status_label"):
            return
        mode = self.ai_tabs.currentIndex() if hasattr(self, "ai_tabs") else 1
        if mode == 0:
            self.ai_status_label.setText("AI：Codex · ChatGPT 登录")
        elif mode == 2:
            model = self.ollama_model.text().strip() or "未选择模型"
            self.ai_status_label.setText(f"AI：本地 Ollama · {model}")
        elif self.model_url.text().strip() and self.model_name.text().strip() and self.model_key.text():
            self.ai_status_label.setText(f"AI：兼容 API · {self.model_name.text().strip()}")
        else:
            self.ai_status_label.setText("AI：兼容 API 尚未完成配置")

    def _ai_mode_changed(self, _index=None):
        self._update_ai_status()

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
        encrypted = self.secret_store.encrypt_dict({"api_key": self.model_key.text()}) if self.model_key.text() else ""
        self.db.set_setting("ai_token_encrypted", encrypted)
        self._update_ai_status()
        self.ai_connection_result.setPlainText(
            f"已保存 {self.ai_tabs.tabText(self.ai_tabs.currentIndex())} 配置。"
            + (" API Token 已使用本机密钥加密。" if self.model_key.text() else "")
        )

    def clear_ai_token(self):
        self.model_key.clear()
        self.db.set_setting("ai_token_encrypted", "")
        self._update_ai_status()
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
            self.ai_connection_result.setPlainText(
                f"已检测到 Codex：{executable}\n"
                + (f"账号状态：{status}" if ok else f"尚未登录：{status}\n请点击“登录 ChatGPT”。")
            )
        except Exception as exc:
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
                "Codex 安装进程已经启动。安装完成后点击“检测 Codex”。"
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
                "完成后点击“检测 Codex”。"
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
        self.project_table.blockSignals(True)
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
        self.project_table.blockSignals(False)
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

    def refresh_asset_tree(self):
        if not hasattr(self, "asset_tree"):
            return
        self.asset_tree.clear()
        if not self.current_project_id:
            return
        project_name = self.projects.currentText()
        project_root = QTreeWidgetItem([project_name, "测试项目", ""])
        self.asset_tree.addTopLevelItem(project_root)
        source_nodes = {}
        module_nodes = {}
        rows = self.db.project_asset_tree(self.current_project_id)
        for row in rows:
            source_id = row["source_id"]
            if source_id not in source_nodes:
                source_nodes[source_id] = QTreeWidgetItem(
                    project_root, [row["source_name"], row["kind"], ""]
                )
            if row["endpoint_id"] is None:
                continue
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
            count = sum(1 for row in rows if row["source_id"] == source_id and row["endpoint_id"] is not None)
            source_node.setText(2, f"{count} 个接口")
        project_root.setText(2, f"{len(source_nodes)} 个资料源")
        project_root.setExpanded(True)
        for node in source_nodes.values():
            node.setExpanded(True)

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
        for attribute in ("request_project_label", "case_project_label", "report_project_label"):
            label = getattr(self, attribute, None)
            if label:
                label.setText(context)

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
            document = BackendSourceParser().parse_directory(path)
            if not document.endpoints:
                raise ValueError(
                    f"已识别为 {document.specification}，但没有找到接口。"
                    "请确认选择的是包含 Controller 的后端项目目录。"
                )
            removed = self.db.delete_empty_sources(self.current_project_id)
            self._save_document(Path(path).name, document)
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

    def _save_document(self, name, document):
        report = check_completeness(document)
        self.db.save_document(self.current_project_id, name, document, report)
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
        rows = self.db.list_endpoints(self.current_project_id) if self.current_project_id else []
        query = self.search.text().lower() if hasattr(self, "search") else ""
        source_id = self.source_filter.currentData() if hasattr(self, "source_filter") else None
        module = self.module_filter.currentData() if hasattr(self, "module_filter") else None
        if source_id is not None:
            rows = [row for row in rows if row["source_id"] == source_id]
        if module is not None:
            rows = [row for row in rows if row["module"] == module]
        rows = [r for r in rows if query in " ".join(str(r[k]) for k in ("method", "path", "module", "summary")).lower()]
        self.endpoint_table.setRowCount(len(rows)); self._endpoint_rows = rows
        for i, row in enumerate(rows):
            for col, key in enumerate(("method", "path", "module", "summary")):
                self.endpoint_table.setItem(i, col, QTableWidgetItem(str(row[key])))
        self.endpoint_table.resizeColumnsToContents()

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
            self.response.setPlainText(json.dumps({
                "status_code": result.status_code, "elapsed_ms": result.elapsed_ms,
                "headers": result.headers, "body": result.body,
            }, ensure_ascii=False, indent=2))
        except Exception as exc:
            QMessageBox.critical(self, "请求失败", str(exc))

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
        self._case_rows = rows; self.case_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            definition = json.loads(row["definition_json"])
            values = (row["id"], row["name"], row["priority"], row["review_status"], definition.get("risk", "low"))
            for column, value in enumerate(values):
                self.case_table.setItem(index, column, QTableWidgetItem(str(value)))
        self.case_table.resizeColumnsToContents()

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
        if not cases:
            QMessageBox.information(self, "提示", "没有已确认的用例")
            return
        if not self.environment_confirmed.isChecked():
            QMessageBox.warning(self, "执行被阻止", "请先确认目标是已授权的测试环境。")
            return
        try:
            headers = json.loads(self.headers.toPlainText() or "{}")
            variables = json.loads(self.variables.toPlainText() or "{}")
            run_id = self.db.create_run(self.current_project_id)
            self._stop_event = Event()
            self.run_progress.setValue(0)
            completed = 0
            def update_progress(result):
                nonlocal completed
                completed += 1
                self.run_progress.setValue(round(completed * 100 / len(cases)))
                self.statusBar().showMessage(f"正在执行：{result['name']} → {result['status']}")
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            results, summary = run_cases(
                cases, self.base_url.text(), headers, on_result=update_progress,
                variables=variables, stop_event=self._stop_event, max_workers=self.max_workers.value(),
            )
            for result in results:
                self.db.save_result(run_id, result.get("case_id"), result)
            self.db.finish_run(run_id, summary)
            project_name = self.projects.currentText()
            html_path, json_path = generate_report(self.db.path.parent / "reports", project_name, results, summary)
            self.db.save_report(run_id, str(html_path), str(json_path))
            self.run_output.setPlainText(
                json.dumps(summary, ensure_ascii=False, indent=2) + f"\n\nHTML：{html_path}\nJSON：{json_path}"
            )
            self.refresh_reports()
        except Exception as exc:
            QMessageBox.critical(self, "执行失败", str(exc))

    def stop_run(self):
        if hasattr(self, "_stop_event"):
            self._stop_event.set()
            self.statusBar().showMessage("正在停止任务……")

    def refresh_reports(self):
        rows = self.db.list_reports(self.current_project_id) if self.current_project_id else []
        self._report_rows = rows
        self.report_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (row["run_id"], row["status"], row["started_at"], row["finished_at"] or "",
                      row["html_path"], row["json_path"])
            for column, value in enumerate(values):
                self.report_table.setItem(index, column, QTableWidgetItem(str(value)))
        self.report_table.resizeColumnsToContents()

    def show_report(self):
        row = self.report_table.currentRow()
        if row < 0:
            return
        stored = self._report_rows[row]
        self.report_detail.setPlainText(
            json.dumps(json.loads(stored["summary_json"] or "{}"), ensure_ascii=False, indent=2)
            + f"\n\nHTML：{stored['html_path']}\nJSON：{stored['json_path']}"
        )

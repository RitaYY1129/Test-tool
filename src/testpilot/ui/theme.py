from __future__ import annotations

BLUE_WHITE_THEME = """
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
    color: #1e293b;
}
QMainWindow, QWidget#AppRoot {
    background: #f3f6fa;
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
    background: #f3f6fa;
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
    background: #f3f6fa;
}
QLabel#PageTitle {
    color: #26384a;
    font-size: 22px;
    font-weight: 700;
}
QLabel#PageSubtitle {
    color: #64748b;
    font-size: 13px;
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
QLabel#PanelTitle {
    color: #26384a;
    font-size: 16px;
    font-weight: 700;
}
QFrame#ProjectStatCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    min-height: 76px;
}
QLabel#ProjectStatBadge {
    color: #1677e8;
    border-radius: 17px;
    min-width: 34px;
    min-height: 34px;
    max-width: 34px;
    max-height: 34px;
    qproperty-alignment: AlignCenter;
    font-size: 14px;
    font-weight: 700;
}
QLabel#ProjectStatValue {
    color: #1e293b;
    font-size: 22px;
    font-weight: 700;
}
QLabel#ProjectStatCaption {
    color: #718096;
    font-size: 12px;
}
QLabel#AssetHint {
    color: #7a8ba0;
    background: #f8fafc;
    border: 1px solid #e5ebf2;
    border-radius: 5px;
    padding: 8px 10px;
    min-height: 18px;
    max-height: 34px;
}
QLabel#SelectedSource {
    color: #1677e8;
    background: #ffffff;
    border: 1px solid #d8e6f5;
    border-radius: 5px;
    padding: 8px 12px;
    font-weight: 600;
}
QFrame#Card, QFrame#ProjectPanel, QGroupBox {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
}
QFrame#RunnerQuickCard {
    background: #ffffff;
    border: 1px solid #cfe1f8;
    border-left: 3px solid #1677e8;
    border-radius: 7px;
}
QFrame#RunnerConfigCard, QFrame#RunnerManualCard, QFrame#RunnerDetailCard {
    background: #ffffff;
    border: 1px solid #e0e8f1;
    border-radius: 7px;
}
QFrame#RunnerManualCard { background: #f8fbff; }
QLabel#RunnerProjectContext {
    color: #244564;
    font-size: 14px;
    font-weight: 700;
}
QLabel#RunnerHealthBadge {
    color: #16834a;
    background: #e9f8ef;
    border: 1px solid #c7ecd7;
    border-radius: 12px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 700;
}
QLabel#RunnerFirstRunHint {
    color: #8b681e;
    background: #fff9e8;
    border: 1px solid #f0dfad;
    border-radius: 6px;
    padding: 9px 11px;
    font-size: 12px;
}
QFrame#RunnerPreviewCard {
    background: #f8fbff;
    border: 1px solid #d5e5f6;
    border-radius: 8px;
}
QLabel#RunnerPreviewLabel {
    color: #71839a;
    font-size: 12px;
}
QLabel#RunnerPreviewValue {
    color: #2b4b6c;
    font-size: 12px;
    font-weight: 600;
}
QFrame#RunnerMetricBlue, QFrame#RunnerMetricGreen, QFrame#RunnerMetricAmber {
    background: #ffffff;
    border: 1px solid #e0e8f1;
    border-radius: 8px;
    min-height: 78px;
}
QLabel#RunnerMetricCaption { color: #71839a; font-size: 12px; }
QLabel#RunnerMetricValue { color: #253f5b; font-size: 22px; font-weight: 700; }
QFrame#RunnerMetricGreen QLabel#RunnerMetricValue { color: #16834a; }
QFrame#RunnerMetricAmber QLabel#RunnerMetricValue { color: #b7791f; }
QFrame#RunnerSuiteCard {
    background: #ffffff;
    border: 1px solid #dfe8f1;
    border-radius: 8px;
    min-height: 162px;
}
QLabel#RunnerSuiteMeta {
    color: #52718f;
    background: #edf5ff;
    border-radius: 10px;
    padding: 5px 8px;
    font-size: 11px;
}
QPushButton#RunnerSuiteAction {
    color: #1677e8;
    background: #ffffff;
    border-color: #bdd8f6;
    min-height: 28px;
}
QLabel#RunnerCatalogEmpty {
    color: #7a6b48;
    background: #fffaf0;
    border: 1px dashed #e7d5a6;
    border-radius: 7px;
    padding: 12px;
}

QTableWidget#RunnerRunTable {
    background: #ffffff;
    border: 1px solid #e0e8f1;
    border-radius: 7px;
    gridline-color: #edf2f7;
    alternate-background-color: #f8fbff;
}
QTableWidget#RunnerRunTable::item { padding: 8px 7px; color: #35506d; }
QTableWidget#RunnerRunTable::item:selected { background: #eaf3ff; color: #135eae; }
QTextEdit#RunnerRunDetail {
    background: #fbfdff;
    border: 1px solid #e6edf5;
    border-radius: 5px;
    color: #40566d;
    font-family: Consolas, "Microsoft YaHei UI";
    font-size: 12px;
    padding: 8px;
}
QToolButton {
    color: #28618f;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 5px 8px;
    font-weight: 600;
}
QToolButton:hover { background: #f0f7ff; border-color: #cfe1f8; }
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
    min-height: 32px;
    padding: 0 14px;
    border-radius: 5px;
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
QPushButton#InlineDeleteButton {
    min-width: 46px;
    max-width: 46px;
    min-height: 22px;
    max-height: 22px;
    padding: 0;
    font-size: 12px;
    border-radius: 3px;
}
QPushButton#AdvancedToggle {
    min-height: 28px;
    padding: 0 12px;
    color: #4e6580;
    background: #f8fafc;
    border-color: #dbe4ee;
}
QPushButton#AdvancedToggle:checked {
    color: #1677e8;
    background: #eef6ff;
    border-color: #9cc4f3;
}
QFrame#InlineAdvancedPanel {
    background: #f8fafc;
    border: 1px solid #dfe8f2;
    border-radius: 5px;
    padding: 8px;
}
QFrame#WorkflowStepBar {
    background: #ffffff;
    border: 1px solid #e1e9f3;
    border-radius: 7px;
}
QLabel#WorkflowStep {
    color: #71839a;
    font-weight: 600;
    padding: 6px 8px;
}
QLabel#WorkflowStep[active="true"] {
    color: #1677e8;
    background: #edf5ff;
    border-radius: 14px;
}
QFrame#WorkflowStepDivider {
    color: #b9d5f5;
    background: #b9d5f5;
    min-height: 1px;
    max-height: 1px;
}
QFrame#AnalysisTrack, QFrame#ValidationTrack {
    background: #f8fbff;
    border: 1px solid #dce9f8;
    border-radius: 6px;
}
QLabel#AnalysisTrackItem, QLabel#ValidationTrackItem {
    color: #48627f;
    background: #ffffff;
    border: 1px solid #e1eaf5;
    border-radius: 6px;
    padding: 10px 12px;
    font-size: 12px;
}
QLabel#AnalysisTrackItem {
    font-weight: 600;
    color: #24557e;
}
QLabel#AnalysisTrackArrow {
    color: #2b82e8;
    font-size: 22px;
    font-weight: 700;
}
QLineEdit, QTextEdit, QComboBox, QSpinBox {
    background: white;
    border: 1px solid #d9e0e8;
    border-radius: 5px;
    padding: 6px 10px;
    selection-background-color: #2b82e8;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #2b82e8;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d8e3ef;
    border-radius: 5px;
    outline: none;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 2px 9px;
    border-radius: 4px;
}
QComboBox QAbstractItemView::item:hover { background: #f5f8fc; }
QComboBox QAbstractItemView::item:selected { background: #eaf3ff; }
QTableWidget {
    background: white;
    alternate-background-color: #fafbfd;
    border: 1px solid #e1e6ec;
    border-radius: 6px;
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
    padding: 7px 10px;
    border: none;
}
QTableWidget::item:selected {
    background: #e7f1ff;
    color: #163d69;
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
QTabWidget#ResourceTabs::pane {
    border: none;
    background: transparent;
}
QTabWidget#ResourceTabs QTabBar::tab {
    min-width: 82px;
    padding: 7px 10px;
    margin-right: 2px;
    border-radius: 5px;
}
QHeaderView::section {
    background: #f5f7fa;
    color: #40566d;
    border: none;
    border-bottom: 1px solid #e1e6ec;
    padding: 9px 10px;
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
QScrollBar:horizontal {
    background: transparent;
    height: 9px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #bfd0e5;
    border-radius: 4px;
    min-width: 32px;
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
QCheckBox:checked {
    color: #1677e8;
    font-weight: 600;
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
QFrame#ValidationConfigCard, QFrame#ValidationResultCard, QFrame#ValidationLogCard,
QFrame#RecognitionCard, QFrame#WorkflowExecutionCard {
    background: #ffffff;
    border: 1px solid #dfe8f3;
    border-radius: 8px;
}
QFrame#RuntimeSetupCard {
    background: #ffffff;
    border: 1px solid #dfe8f3;
    border-radius: 8px;
}
QFrame#RuntimeHelpCard {
    background: #f2f8ff;
    border: 1px solid #d3e6ff;
    border-radius: 6px;
    min-height: 126px;
}
QLabel#RuntimeHelpTitle { color: #1677e8; font-size: 14px; font-weight: 700; }
QLabel#RuntimeHelpText { color: #54708d; font-size: 12px; line-height: 1.55; }
QSplitter#EndpointWorkspace::handle { background: #dfe8f3; width: 1px; }
QSplitter#EndpointWorkbench::handle { background: #f1f5f9; width: 8px; }
QFrame#EndpointRequestCard, QFrame#EndpointDefinitionCard {
    background: #ffffff;
    border: 1px solid #dfe8f2;
    border-radius: 7px;
}
QFrame#EndpointGroupCard { background: #ffffff; border: none; }
QLabel#EndpointPaneTitle { color: #1f3957; font-size: 13px; font-weight: 700; }
QLineEdit#EndpointSearch {
    background: #ffffff;
    border: 1px solid #dce6f1;
    border-radius: 5px;
    min-height: 28px;
    padding-left: 9px;
}
QPushButton#EndpointNewGroup {
    background: #ffffff;
    border: 1px solid #dce7f3;
    border-radius: 4px;
    color: #1677e8;
    min-height: 27px;
}
QPushButton#EndpointNewGroup:hover { background: #f0f7ff; border-color: #9ec8fb; }
QComboBox#EndpointMethod {
    background: #ffffff;
    border: 1px solid #dce6f1;
    border-right: none;
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
    font-weight: 700;
    min-width: 84px;
    min-height: 36px;
    max-height: 36px;
}
QComboBox#EndpointMethod::drop-down {
    width: 20px;
    border-left: 1px solid #e3ebf4;
}
QComboBox#EndpointMethod QAbstractItemView {
    background: #ffffff;
    border: 1px solid #cfdceb;
    outline: none;
    selection-background-color: #eef6ff;
}
QComboBox#EndpointEnvironment {
    background: #ffffff;
    border: 1px solid #dce6f1;
    border-radius: 4px;
    color: #36526d;
    min-height: 27px;
    padding: 0 7px;
}
QLineEdit#EndpointUrl {
    background: #ffffff;
    border: 1px solid #dce6f1;
    border-left: 1px solid #dce6f1;
    border-top-left-radius: 0;
    border-bottom-left-radius: 0;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    min-height: 36px;
    max-height: 36px;
    color: #41607f;
}
QPushButton#EndpointSend {
    border-radius: 5px;
    min-width: 54px;
    max-width: 54px;
    min-height: 36px;
    max-height: 36px;
    padding: 0;
    border: 1px solid #1677e8;
}
QPushButton#EndpointToolbarButton {
    background: #ffffff;
    border: 1px solid #dce6f1;
    border-radius: 5px;
    color: #36526d;
    min-width: 56px;
    font-size: 13px;
}
QPushButton#EndpointToolbarButton:hover { background: #f6faff; border-color: #9ec8fb; color: #1677e8; }
QLabel#EndpointActiveTab {
    background: #f0f7ff;
    border: 1px solid #bfdbfe;
    border-radius: 4px;
    color: #243b53;
    font-weight: 700;
    min-height: 25px;
    padding: 3px 9px;
}
QTabWidget#EndpointRequestTabs::pane {
    background: #ffffff;
    border: 1px solid #e4edf6;
    border-radius: 5px;
    top: -1px;
}
QTabWidget#EndpointRequestTabs::tab-bar { alignment: left; }
QTabWidget#EndpointRequestTabs QTabBar::tab {
    background: transparent;
    border: none;
    color: #7086a0;
    min-width: 48px;
    padding: 7px 8px;
}
QTabWidget#EndpointRequestTabs QTabBar::tab:selected {
    color: #1677e8;
    border-bottom: 2px solid #1677e8;
    font-weight: 700;
}
QTabWidget#EndpointBodyTabs::pane, QTabWidget#EndpointResponseTabs::pane,
QTabWidget#EndpointDefinitionTabs::pane {
    background: #ffffff;
    border: 1px solid #e5edf6;
    border-radius: 4px;
    top: -1px;
}
QTabWidget#EndpointBodyTabs QTabBar::tab, QTabWidget#EndpointResponseTabs QTabBar::tab,
QTabWidget#EndpointDefinitionTabs QTabBar::tab {
    background: transparent;
    border: none;
    color: #6f8297;
    padding: 6px 8px;
}
QTabWidget#EndpointBodyTabs QTabBar::tab:selected, QTabWidget#EndpointResponseTabs QTabBar::tab:selected,
QTabWidget#EndpointDefinitionTabs QTabBar::tab:selected {
    color: #1677e8;
    border-bottom: 2px solid #1677e8;
    font-weight: 700;
}
QLabel#EndpointEmptyHint { color: #7990a8; padding: 12px; }
QLabel#EndpointFormTitle { color: #36526d; font-size: 12px; font-weight: 700; padding: 4px 0; }
QWidget#QueryParameterEditor {
    background: #ffffff;
    border: 1px solid #edf1f6;
    border-radius: 5px;
    padding: 5px;
}
QLabel#QueryParameterHeader { color: #697f96; font-size: 11px; font-weight: 700; }
QWidget#QueryParameterRow { background: transparent; }
QLineEdit#QueryParameterName, QLineEdit#QueryParameterValue {
    background: #fbfdff;
    border: 1px solid #e2eaf3;
    border-radius: 5px;
    color: #304b67;
    min-height: 27px;
    padding: 1px 8px;
}
QLineEdit#QueryParameterName:focus, QLineEdit#QueryParameterValue:focus {
    background: #ffffff;
    border-color: #8bbefa;
}
QToolButton#QueryParameterDelete {
    background: transparent;
    border: none;
    color: #a6b4c2;
    min-width: 22px;
    min-height: 26px;
    font-size: 16px;
}
QToolButton#QueryParameterDelete:hover { color: #ef4444; background: #fff3f3; border-radius: 4px; }
QWidget#KeyValueParameterEditor {
    background: #ffffff;
    border: 1px solid #edf1f6;
    border-radius: 5px;
    padding: 7px;
}
QLabel#KeyValueParameterHeader {
    color: #697f96;
    font-size: 11px;
    font-weight: 700;
    padding-bottom: 1px;
}
QWidget#KeyValueParameterRow { background: transparent; }
QLineEdit#KeyValueParameterName, QLineEdit#KeyValueParameterValue,
QLineEdit#KeyValueParameterType, QLineEdit#KeyValueParameterDescription {
    background: #fbfdff;
    border: 1px solid #e2eaf3;
    border-radius: 5px;
    color: #304b67;
    min-height: 30px;
    padding: 1px 8px;
}
QLineEdit#KeyValueParameterName:focus, QLineEdit#KeyValueParameterValue:focus {
    background: #ffffff;
    border-color: #8bbefa;
}
QCheckBox#KeyValueParameterEnabled { min-width: 18px; max-width: 18px; }
QLabel#KeyValueParameterSource {
    background: #eef6ff;
    border: 1px solid #bfdbfe;
    border-radius: 4px;
    color: #1677e8;
    font-size: 10px;
    padding: 2px 5px;
}
QToolButton#KeyValueParameterDelete {
    background: transparent;
    border: none;
    color: #94a3b8;
    min-width: 32px;
    min-height: 32px;
    font-size: 17px;
}
QToolButton#KeyValueParameterDelete:hover { color: #ef4444; background: #fff3f3; border-radius: 4px; }
QTableWidget#EndpointInputTable {
    background: #ffffff;
    border: none;
    border-top: 1px solid #edf1f6;
    gridline-color: #edf1f6;
    color: #405c79;
    font-size: 12px;
}
QTableWidget#EndpointInputTable::item { padding: 5px 8px; }
QFrame#EndpointAuthHelp, QFrame#EndpointActionPage {
    background: #f8fafc;
    border: 1px solid #edf1f6;
    border-radius: 7px;
    color: #4c627d;
}
QFrame#EndpointOperationCard {
    background: #f7fbff;
    border: 1px solid #cfe4fb;
    border-radius: 5px;
}
QLabel#EndpointOperationName { color: #2465a5; font-weight: 700; }
QLabel#EndpointOperationDetail { color: #8091a5; font-size: 11px; }
QLabel#EndpointAddAction, QPushButton#EndpointAddAction {
    background: #ffffff;
    border: 1px dashed #c9d8e9;
    border-radius: 7px;
    color: #8b5cf6;
    font-weight: 700;
    padding: 9px;
    text-align: center;
}
QMenu#EndpointOperationMenu {
    background: #ffffff;
    border: 1px solid #dfe8f2;
    border-radius: 7px;
    padding: 5px;
}
QMenu#EndpointOperationMenu::item { padding: 7px 12px; border-radius: 4px; color: #36526d; }
QMenu#EndpointOperationMenu::item:selected { background: #f0f7ff; color: #1677e8; }
QFrame#EndpointResponsePanel { background: #ffffff; border: 1px solid #e2ebf5; border-radius: 5px; }
QFrame#EndpointActionBar { background: #f8fbfe; border: 1px solid #e5edf5; border-radius: 5px; }
QPushButton#EndpointActionButton { background: #ffffff; border: 1px solid #dce6f1; border-radius: 4px; color: #36526d; padding: 0 10px; }
QLabel#EndpointResponseMeta { color: #72859a; font-size: 11px; }
QLabel#EndpointDefinitionSection { color: #36526d; font-size: 12px; font-weight: 700; padding-top: 2px; }
QTableWidget#EndpointDefinitionTable {
    background: #ffffff;
    border: 1px solid #e2ebf5;
    border-radius: 4px;
    gridline-color: #edf2f7;
    color: #45617e;
    font-size: 11px;
    min-height: 54px;
}
QTableWidget#EndpointDefinitionTable::item { padding: 4px 5px; }
QTextEdit#EndpointEditor {
    background: #fbfdff;
    border: 1px solid #e1eaf3;
    border-radius: 4px;
    color: #2f4965;
    font-family: Consolas, "Microsoft YaHei UI";
    font-size: 12px;
    min-height: 112px;
    padding: 7px;
}
QRadioButton#EndpointBodyType { color: #46627e; spacing: 4px; min-height: 25px; }
QPushButton#EndpointBodyFormat {
    background: #ffffff;
    border: 1px solid #dce7f3;
    border-radius: 4px;
    color: #1677e8;
    min-height: 26px;
    padding: 1px 8px;
}
QPushButton#EndpointBodyFormat:hover { background: #f0f7ff; border-color: #9ec8fb; }
QTextEdit#EndpointBodyEditor {
    background: #fbfdff;
    border: 1px solid #e1eaf3;
    border-radius: 5px;
    color: #2f4965;
    font-family: Consolas, "Microsoft YaHei UI";
    font-size: 12px;
    min-height: 150px;
    padding: 7px;
}
QTextEdit#EndpointBodyEditor:disabled { color: #9aabba; background: #f8fafc; }
QLabel#EndpointResponseTitle { color: #1f3957; font-weight: 700; padding: 2px 0; }
QTreeWidget#EndpointNavigator, QTableWidget#EndpointList {
    background: #ffffff;
    border: 1px solid #e0e8f1;
    border-radius: 7px;
    color: #344b63;
}
QTreeWidget#EndpointNavigator::item { min-height: 30px; padding: 1px 8px; }
QTreeWidget#EndpointNavigator::item:selected { background: #eef6ff; color: #243b53; font-weight: 400; }
QWidget#EndpointTreeLeaf { background: transparent; }
QLabel#EndpointTreeMethod { font-size: 12px; font-weight: 600; background: transparent; }
QLabel#EndpointTreeName { color: #243b53; font-size: 13px; background: transparent; }
QTableWidget#EndpointList::item { padding: 7px 8px; }
QTableWidget#EndpointList::item:selected { background: #eef6ff; color: #135eae; }
QFrame#EndpointDetailCard {
    background: #ffffff;
    border: 1px solid #e0e8f1;
    border-radius: 7px;
}
QTextEdit#EndpointDetail {
    background: #fbfdff;
    border: 1px solid #e6edf5;
    border-radius: 5px;
    color: #40566d;
    font-family: Consolas, "Microsoft YaHei UI";
    font-size: 12px;
    padding: 8px;
}
QLabel#ValidationProjectName, QLabel#ValidationHint {
    color: #607996;
    min-height: 28px;
    padding: 4px 8px;
}
QComboBox#ValidationProjectSelector {
    min-height: 30px;
    color: #294563;
    font-weight: 700;
}
QFrame#ValidationStepCard {
    background: #ffffff;
    border: 1px solid #b9d6fb;
    border-radius: 7px;
    min-height: 188px;
}
QLabel#ValidationStepTitle { color: #294563; font-weight: 700; }
QLabel#ValidationStepIcon { background: transparent; border: none; }
QLabel#ValidationStepDetail { color: #58718e; font-size: 12px; }
QLabel#ValidationStepPending { color: #7e8fa2; font-weight: 600; }
QLabel#ValidationStepSuccess { color: #16a34a; font-weight: 700; }
QLabel#ValidationStepFailure { color: #e28b17; font-weight: 700; }
QLabel#ValidationArrow { color: #1677e8; font-size: 30px; font-weight: 800; min-width: 28px; }
QFrame#ValidationDetailPanel {
    background: #ffffff;
    border: 1px solid #e3ebf4;
    border-radius: 7px;
    min-height: 168px;
}
QLabel#ValidationDetailTitle { color: #294563; font-size: 14px; font-weight: 700; }
QLabel#ValidationPanelPending { color: #7e8fa2; font-size: 12px; font-weight: 600; }
QLabel#ValidationPanelSuccess { color: #16a34a; font-size: 12px; font-weight: 700; }
QLabel#ValidationPanelFailure { color: #e28b17; font-size: 12px; font-weight: 700; }
QFrame#ValidationMetricDivider {
    background: #edf2f7;
    border: none;
    min-height: 1px;
    max-height: 1px;
}
QFrame#ValidationMetricRow { border: none; min-height: 34px; }
QLabel#ValidationMetric { color: #54708d; font-size: 12px; padding: 6px 2px; font-weight: 700; }
QLabel#ValidationMetricValue { color: #54708d; font-size: 12px; padding: 6px 2px; font-weight: 700; }
QLabel#ValidationSummary { color: #70839a; font-size: 12px; padding: 7px 2px 0 2px; font-weight: 700; }
QLabel#ValidationSummarySuccess { color: #389765; font-size: 12px; padding: 7px 2px 0 2px; font-weight: 700; }
QLabel#ValidationSummaryFailure { color: #d98518; font-size: 12px; padding: 7px 2px 0 2px; font-weight: 700; }
QPushButton#ValidationDetailAction, QPushButton#ValidationExportReport {
    background: #ffffff;
    color: #1677e8;
    border: 1px solid #d7e3f0;
    border-radius: 5px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 700;
}
QPushButton#ValidationDetailAction:hover, QPushButton#ValidationExportReport:hover {
    background: #f3f8ff;
    border-color: #8bbcff;
}
QScrollArea#ValidationLog, QWidget#ValidationLogContent { background: #ffffff; border: none; }
QFrame#ValidationLogRow { background: #ffffff; border: none; border-bottom: 1px solid #eff3f8; }
QLabel#ValidationLogTime { color: #7d91a8; font-size: 12px; font-weight: 700; }
QLabel#ValidationLogMessage { color: #54708d; font-size: 12px; font-weight: 700; }
QLabel#ValidationLogStatusPending { color: #7e8fa2; font-size: 12px; font-weight: 600; }
QLabel#ValidationLogStatusRunning { color: #1677e8; font-size: 12px; font-weight: 700; }
QLabel#ValidationLogStatusSuccess { color: #16a34a; font-size: 12px; font-weight: 700; }
QLabel#ValidationLogStatusWarning { color: #e28b17; font-size: 12px; font-weight: 700; }
QFrame#BusinessStepper { background: transparent; border: none; }
QLabel#BusinessStepActive, QLabel#BusinessStep { font-weight: 700; padding: 7px 10px; }
QLabel#BusinessStepActive { color: #1677e8; background: #edf5ff; border-radius: 16px; }
QLabel#BusinessStep { color: #75869a; }
QFrame#BusinessStepLine { min-height: 1px; max-height: 1px; background: #d7e3f0; border: none; }
QFrame#RecognitionVisual { background: #fbfdff; border: 1px dashed #cfdded; border-radius: 7px; }
QWidget#RecognitionVisualItem { background: transparent; border: none; }
QLabel#RecognitionVisualLabel { color: #315a87; font-size: 13px; font-weight: 700; padding: 2px; }
QLabel#RecognitionArrow { color: #1877f2; font-size: 35px; font-weight: 700; min-width: 42px; }
QFrame#ExpectedOutputItem { background: #ffffff; border: 1px solid #dfeafb; border-radius: 7px; }
QLabel#ExpectedOutputLabel { color: #315a87; font-size: 13px; font-weight: 700; }
QFrame#ExpectedOutputPanel { background: #fbfdff; border: 1px solid #dfe8f3; border-radius: 7px; }
QLabel#ExpectedOutputTitle { color: #425d7d; font-weight: 700; padding: 4px 2px; }
QLabel#SafetyHint { color: #1677e8; background: #f0f7ff; border: 1px solid #cfe2fc; border-radius: 6px; padding: 12px; font-weight: 600; }
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


BLUE_WHITE_THEME += """
/* External Runner real workspace: central content only */
QWidget#RunnerWorkspace { background:#f4f8fc; }
QLabel#RunnerPageTitle { color:#163b63; font-size:29px; font-weight:700; }
QLabel#RunnerPageSubtitle { color:#718bab; font-size:14px; padding-bottom:2px; }
QLabel#RunnerOnlineBadge { color:#138950; background:#def7e9; border-radius:14px; padding:6px 12px; font-weight:700; }
QFrame#RunnerContextBar { background:#ffffff; border:1px solid #d7e4ef; border-left:5px solid #2788ed; border-radius:9px; }
QLabel#RunnerContextStrong { color:#173e65; font-size:15px; font-weight:700; }
QLabel#RunnerContextValue { color:#244c74; font-size:14px; }
QLabel#RunnerContextDivider { color:#9ab0c4; font-size:14px; }
QPushButton#RunnerGhostButton { min-height:34px; padding:0 13px; color:#2678cf; background:#ffffff; border:1px solid #c9dced; border-radius:6px; font-weight:700; }
QPushButton#RunnerGhostButton:hover { background:#f0f7ff; border-color:#8ec0f3; }
QTabWidget#RunnerCenterTabs::pane { background:transparent; border:none; top:-1px; }
QTabWidget#RunnerCenterTabs QTabBar::tab { min-width:0; background:transparent; color:#7189a6; border:none; border-bottom:3px solid transparent; border-radius:0; padding:13px 19px; margin-right:12px; font-size:15px; }
QTabWidget#RunnerCenterTabs QTabBar::tab:selected { background:transparent; color:#237ee4; border-bottom:3px solid #2587ee; font-weight:700; }
QFrame#RunnerCreateCard, QFrame#RunnerPreviewCard, QFrame#RunnerResultCard, QFrame#RunnerCatalogCard { background:#ffffff; border:1px solid #d7e4ef; border-radius:11px; }
QFrame#RunnerPreviewCard { background:#f8fbff; border-color:#d4e5f5; }
QLabel#RunnerSectionTitle { color:#173e65; font-size:19px; font-weight:700; }
QLabel#RunnerSectionHint { color:#7892ae; font-size:12px; }
QLabel#RunnerSectionLabel, QLabel#RunnerFieldLabel { color:#294f77; font-weight:700; font-size:13px; }
QLineEdit#RunnerSuiteSearch, QLineEdit#RunnerFilterInput { min-height:40px; border:1px solid #d2e0ed; border-radius:7px; padding:0 12px; }
QFrame#RunnerSuiteChoice { background:#ffffff; border:1px solid #dde7f0; border-radius:8px; }
QFrame#RunnerSuiteChoice:hover { background:#f6faff; border-color:#9bc6f4; }
QPushButton#RunnerPrimaryAction, QPushButton#RunnerFilterAction { min-height:42px; color:white; background:#2784e8; border:1px solid #2784e8; border-radius:7px; font-weight:700; padding:0 16px; }
QPushButton#RunnerSecondaryAction { min-height:42px; color:#2678cf; background:#ffffff; border:1px solid #9ec9f6; border-radius:7px; font-weight:700; }
QWidget#RunnerPreviewRow { border-bottom:1px solid #e3ebf3; }
QLabel#RunnerPreviewKey { color:#7892ae; font-size:11px; }
QLabel#RunnerPreviewValue { color:#315778; font-size:13px; font-weight:700; }
QFrame#RunnerMetricBlue, QFrame#RunnerMetricAmber { background:#ffffff; border:1px solid #d7e4ef; border-radius:11px; min-height:112px; }
QLabel#RunnerMetricCaption { color:#7b92aa; font-size:13px; }
QLabel#RunnerMetricValue { color:#173e65; font-size:28px; font-weight:700; }
QFrame#RunnerMetricAmber QLabel#RunnerMetricValue { color:#bf7619; }
QTableWidget#RunnerRunTable { background:#ffffff; border:none; gridline-color:#e7eef4; color:#365978; }
QTableWidget#RunnerRunTable::item { padding:11px 9px; }
QHeaderView::section { background:#f4f8fc; color:#6e88a5; padding:12px 9px; border:none; border-bottom:1px solid #e3ebf3; font-weight:700; }
QPushButton#RunnerChip, QPushButton#RunnerActiveChip { min-height:38px; padding:0 14px; border:1px solid #d4e1ed; border-radius:19px; background:#ffffff; color:#5e7b98; }
QPushButton#RunnerActiveChip { background:#edf6ff; border-color:#9fc9f6; color:#2378d1; font-weight:700; }
QLabel#RunnerCatalogCount { color:#6986a3; background:#f1f6fc; border-radius:16px; padding:8px 12px; }
QFrame#RunnerSuiteCard { background:#ffffff; border:1px solid #d8e5ef; border-radius:11px; min-height:174px; }
QLabel#RunnerSuiteName { color:#163d65; font-size:16px; font-weight:700; }
QPushButton#RunnerSuiteAction { text-align:left; border:none; background:transparent; color:#237bd6; font-weight:700; padding:3px 0; }
"""

BLUE_WHITE_THEME += """

/* Resize-safe real Runner controls */
QWidget#RunnerWorkspace QLineEdit, QWidget#RunnerWorkspace QComboBox {
    min-height: 42px;
    max-height: 42px;
    padding: 0 12px;
    font-size: 13px;
}
QFrame#RunnerSuiteChoice { min-height: 74px; }
QFrame#RunnerAdvancedInline {
    background: #ffffff;
    border: 1px solid #d7e4ef;
    border-radius: 10px;
    margin: 0 0 2px 0;
}
QLabel#RunnerSuiteMeta { color:#6986a2; font-size:11px; }
QScrollArea, QAbstractScrollArea { background: transparent; }

"""

BLUE_WHITE_THEME += """

/* Prevent runner form distortion on window resize */
QScrollArea#RunnerCreateScroll {
    background: transparent;
    border: none;
}
QScrollArea#RunnerCreateScroll > QWidget > QWidget {
    background: transparent;
}
QScrollArea#RunnerCreateScroll QScrollBar:vertical {
    width: 10px;
    margin: 3px;
}
QScrollArea#RunnerCreateScroll QScrollBar::handle:vertical {
    background: #b9cce0;
    border-radius: 5px;
    min-height: 36px;
}
QFrame#RunnerCreateCard QLineEdit, QFrame#RunnerCreateCard QComboBox {
    min-height: 44px;
    max-height: 44px;
}

"""

BLUE_WHITE_THEME += """

/* Prototype-aligned live task table and scroll behavior */
QScrollArea#RunnerCreateScroll QWidget#RunnerCreateCard,
QScrollArea#RunnerCreateScroll QFrame#RunnerPreviewCard {
    min-height: 0;
}
QTableWidget#RunnerRunTable {
    border: none;
    alternate-background-color: #ffffff;
}
QTableWidget#RunnerRunTable::item {
    padding: 10px 9px;
    border-bottom: 1px solid #e8eef4;
}

"""

BLUE_WHITE_THEME += """

/* Exact reference hierarchy for the real External Runner content */
QFrame#RunnerReferenceForm, QFrame#RunnerReferencePreview, QFrame#RunnerResultCard, QFrame#RunnerCatalogCard { background:#fff; border:1px solid #d8e5ef; border-radius:12px; }
QFrame#RunnerReferencePreview { background:#f7fbff; border-color:#d4e4f3; }
QFrame#RunnerReferenceRule { min-height:1px; max-height:1px; border:none; background:#e6edf4; }
QLabel#RunnerReferenceHeading { color:#153b63; font-size:20px; font-weight:700; }
QLabel#RunnerReferenceSubheading { color:#7892ad; font-size:13px; }
QLabel#RunnerReferenceCode { color:#9badbd; font-family:Consolas; font-size:11px; }
QFrame#RunnerReferenceSuite { background:#fff; border:1px solid #dce6ef; border-radius:9px; }
QFrame#RunnerReferenceSuite:hover { background:#f7fbff; border-color:#a8cef7; }
QLabel#RunnerSuiteNumber { color:#7b98b5; min-width:24px; font-family:Consolas; }
QLabel#RunnerSuiteReferenceName { color:#183e65; font-size:15px; font-weight:700; }
QLabel#RunnerSuiteReferenceMeta { color:#7690aa; font-size:12px; }
QRadioButton#RunnerReferenceRadio::indicator { width:18px; height:18px; border-radius:9px; border:1px solid #aec3d8; background:#fff; }
QRadioButton#RunnerReferenceRadio::indicator:checked { border:5px solid #2784e9; }
QFrame#RunnerReferenceCatalogCard { background:#fff; border:1px solid #d9e5ee; border-radius:11px; }
QLabel#RunnerCatalogReferenceName { color:#153b63; font-size:17px; font-weight:700; }
QLabel#RunnerCatalogReferenceDescription { color:#7991aa; font-size:12px; }
QLabel#RunnerCatalogTag { color:#2378d4; background:#eaf3ff; border-radius:3px; padding:3px 6px; font-size:11px; }
QPushButton#RunnerCatalogAction { color:#247ad2; border:none; background:transparent; text-align:left; font-weight:700; padding:3px 0; }

"""

BLUE_WHITE_THEME += """

/* Exact tab navigation and controlled selection behavior for External Runner. */
QTabWidget#RunnerCenterTabs QTabBar::tab {
    min-height: 58px;
    padding: 12px 18px;
    margin-right: 20px;
    color: #7188a4;
    font-size: 16px;
}
QTabWidget#RunnerCenterTabs QTabBar::tab:selected {
    color: #247fe6;
    border-bottom: 4px solid #2b86ea;
    font-weight: 700;
}
QComboBox#RunnerInputCombo QAbstractItemView {
    background: #ffffff;
    border: 1px solid #bcd8f2;
    padding: 4px;
    outline: none;
    selection-background-color: #eef6ff;
    selection-color: #193e65;
}
QComboBox#RunnerInputCombo QAbstractItemView::item {
    min-height: 32px;
    padding: 4px 10px;
    border-radius: 5px;
}
QComboBox#RunnerInputCombo QAbstractItemView::item:selected,
QComboBox#RunnerInputCombo QAbstractItemView::item:hover {
    background: #eef6ff;
    color: #1c70c6;
}
QRadioButton#RunnerReferenceRadio { min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; }
QRadioButton#RunnerReferenceRadio::indicator {
    width: 18px; height: 18px; border-radius: 9px;
    border: 1px solid #aec3d8; background: #ffffff;
}
QRadioButton#RunnerReferenceRadio::indicator:checked {
    border: 5px solid #2784e9; background: #ffffff;
}

"""

BLUE_WHITE_THEME += """
QLabel#RunnerTabCount { min-width:22px; min-height:22px; border-radius:11px; padding:0 5px; color:#287ee0; background:#eaf3ff; font-size:12px; }
QLabel#RunnerTabLive { min-height:24px; border-radius:12px; padding:0 8px; color:#2378d4; background:#eaf3ff; font-size:12px; font-weight:700; }
"""
BLUE_WHITE_THEME += """

/* Reference execution-confirmation card and single-suite checked state. */
QFrame#RunnerReferencePreview { background: #fbfdff; border-color: #cfe1f3; }
QFrame#RunnerAssignedRunner { background:#effbf4; border:1px solid #c6efd9; border-radius:11px; }
QLabel#RunnerAssignedDot { color:#31be76; font-size:22px; }
QLabel#RunnerAssignedCaption { color:#669681; font-size:11px; letter-spacing:1.1px; }
QLabel#RunnerAssignedName { color:#147d4d; font-size:16px; font-weight:700; }
QLabel#RunnerAssignedVersion { color:#21805a; font-family:Consolas; font-size:14px; }
QWidget#RunnerPreviewItem { border-bottom:1px solid #dce8f3; }
QLabel#RunnerPreviewRisk { color:#c87427; font-size:16px; font-weight:700; }
QLabel#RunnerPreviewNote { color:#8299b1; font-size:12px; padding:4px 0 10px; }
QFrame#RunnerReferenceSuite[selected="true"] { background:#eff6ff; border:2px solid #2b84e9; }
QFrame#RunnerReferenceSuite[selected="true"] QLabel#RunnerSuiteNumber { color:#2178d5; font-weight:700; }
QPushButton#RunnerSuiteSelector {
    min-width:28px; max-width:28px; min-height:28px; max-height:28px;
    padding:0; border:1px solid #aec3d8; border-radius:14px;
    background:#ffffff; color:transparent; font-size:16px; font-weight:800;
}
QPushButton#RunnerSuiteSelector:checked {
    border:1px solid #2b84e9; background:#2b84e9; color:#ffffff;
}
QPushButton#RunnerSuiteSelector:hover { border-color:#2b84e9; }

"""

BLUE_WHITE_THEME += """
QLabel#RunnerTableSuiteText { background:transparent; border:none; color:#355b7f; padding:0 9px; }
"""
BLUE_WHITE_THEME += """

/* Clean white Runner surface, prototype information rows and readable table values. */
QScrollArea#RunnerWorkspace, QScrollArea#RunnerWorkspace > QWidget > QWidget#RunnerWorkspaceContent,
QScrollArea#RunnerTabScroll, QScrollArea#RunnerTabScroll > QWidget > QWidget { background:#ffffff; }
QScrollArea#RunnerWorkspace { border:none; }
QScrollArea#RunnerWorkspace QScrollBar:vertical { width:10px; margin:4px; }
QScrollArea#RunnerWorkspace QScrollBar::handle:vertical { background:#b9cce0; border-radius:5px; min-height:42px; }
QFrame#RunnerAssignedRunner { border:none; border-radius:0; background:#effbf4; }
QFrame#RunnerAssignedRunner + QWidget { margin-top:0; }
QLabel#RunnerTableSuiteText { background:transparent; border:none; color:#355b7f; padding:0 9px; }
QLabel#RunnerStatusBadge { min-width:86px; max-width:126px; min-height:28px; }
QFrame#RunnerReferenceForm, QFrame#RunnerReferencePreview, QFrame#RunnerResultCard,
QFrame#RunnerCatalogCard, QFrame#RunnerMetricBlue, QFrame#RunnerMetricAmber { background:#ffffff; }

"""
BLUE_WHITE_THEME += """

/* The Runner uses the same pale system canvas as the reference prototype. */
QScrollArea#RunnerWorkspace, QScrollArea#RunnerWorkspace > QWidget > QWidget#RunnerWorkspaceContent { background:#f4f8fc; }
QScrollArea#RunnerWorkspace QScrollBar:vertical, QScrollArea#RunnerWorkspace QScrollBar:horizontal { width:0; height:0; background:transparent; }
QFrame#RunnerReferenceSuite { background:#ffffff; }

"""
BLUE_WHITE_THEME += """

/* Runner tab pages inherit the reference system canvas—no nested grey panel. */
QTabWidget#RunnerCenterTabs::pane,
QTabWidget#RunnerCenterTabs QStackedWidget,
QTabWidget#RunnerCenterTabs > QWidget { background:#f4f8fc; border:none; }
QWidget#RunnerWorkspaceContent { background:#f4f8fc; }
QWidget#RunnerTableActions { background:transparent; border:none; }
QWidget#RunnerTableActions QToolButton { background:transparent; border:none; padding:3px; }
QWidget#RunnerTableActions QToolButton:hover { background:#eaf3ff; border-radius:5px; }

"""
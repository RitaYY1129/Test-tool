"""Modern three-tab External Runner screen; installed without changing domain logic."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QTabWidget, QTableWidget, QTextEdit,
    QVBoxLayout, QWidget, QHeaderView, QAbstractItemView, QCheckBox,
)

C = lambda s: s if any(ord(ch) > 127 for ch in s) else s.encode("ascii").decode("unicode_escape")


def _card(name="RunnerConfigCard"):
    w = QFrame(); w.setObjectName(name); return w


def _label(text, name=None):
    w = QLabel(C(text));
    if name: w.setObjectName(name)
    return w


def _suite_choice(title, detail, count, selected=False):
    row = _card("RunnerSuiteChoice")
    box = QHBoxLayout(row); box.setContentsMargins(16, 12, 16, 12)
    radio = QRadioButton(C(title)); radio.setChecked(selected)
    radio.setObjectName("RunnerSuiteRadio")
    body = QVBoxLayout(); body.addWidget(radio); body.addWidget(_label(detail, "ValidationHint"))
    box.addLayout(body, 1); box.addWidget(_label(count, "ValidationHint"))
    return row, radio


def modern_external_runner_page(self):
    page = QWidget(); layout = QVBoxLayout(page)
    layout.setContentsMargins(28, 20, 28, 22); layout.setSpacing(16)
    title_row = QHBoxLayout()
    title = _label("\u5916\u90e8 Runner", "PageTitle")
    status = _label("\u2022 \u8fd0\u884c\u4e2d", "RunnerOnlineBadge")
    title_row.addWidget(title); title_row.addWidget(status); title_row.addStretch()
    subtitle = _label("\u4ece\u5df2\u767b\u8bb0\u3001\u7248\u672c\u53d7\u63a7\u7684\u6d4b\u8bd5\u5957\u4ef6\u521b\u5efa\u4efb\u52a1\uff1b\u5e73\u53f0\u751f\u6210 Manifest\uff0c\u4ea4\u7531 SteelMill Runner \u6267\u884c\u5e76\u81ea\u52a8\u5f52\u6863\u7ed3\u679c\u3002", "PageSubtitle")
    banner = _card("ContextBanner"); bl=QHBoxLayout(banner); bl.setContentsMargins(18, 12, 18, 12)
    self.runner_project_label = _label("\u5f53\u524d\u9879\u76ee\uff1a\u78b3\u7d20    |    139 \u4e2a\u63a5\u53e3    |    Runner: steelmill-runner 0.1.0")
    advanced = QPushButton(C("\u2699  \u9ad8\u7ea7\u8bbe\u7f6e")); advanced.clicked.connect(lambda: None)
    bl.addWidget(self.runner_project_label, 1); bl.addWidget(advanced)
    layout.addLayout(title_row); layout.addWidget(subtitle); layout.addWidget(banner)
    tabs = QTabWidget(); tabs.setObjectName("RunnerCenterTabs")

    # Create task
    create = QWidget(); outer=QHBoxLayout(create); outer.setContentsMargins(0, 8, 0, 0); outer.setSpacing(16)
    form = _card(); fl=QGridLayout(form); fl.setContentsMargins(22, 20, 22, 20); fl.setHorizontalSpacing(16); fl.setVerticalSpacing(10)
    fl.addWidget(_label("\u25a3  \u521b\u5efa\u6d4b\u8bd5\u4efb\u52a1", "PanelTitle"),0,0,1,4)
    fl.addWidget(_label("\u5de5\u5355\u7528\u4e8e\u5173\u8054\u9700\u6c42\u6216\u7f3a\u9677\uff1b\u771f\u6b63\u51b3\u5b9a\u8fd0\u884c\u5185\u5bb9\u7684\u662f\u300c\u6a21\u5757 + \u5df2\u767b\u8bb0\u6d4b\u8bd5\u5957\u4ef6\u300d\u3002", "ValidationHint"),1,0,1,4)
    self.runner_task_name=QLineEdit(); self.runner_task_name.setPlaceholderText(C("\u4f8b\u5982\uff1a\u672c\u673a\u5b8c\u6574\u73b0\u573a\u5de5\u827a\u56de\u5f52"))
    self.runner_work_order=QLineEdit(); self.runner_work_order.setPlaceholderText(C("\u4f8b\u5982\uff1aSM-248 \u7089\u5ba4\u72b6\u6001\u673a\u8c03\u6574\uff08\u53ef\u9009\uff09"))
    self.auto_runner_environment=QComboBox(); self.auto_runner_environment.addItem(C("\u6d4b\u8bd5\u73af\u5883"), C("\u6d4b\u8bd5\u73af\u5883"))
    self.runner_module=QComboBox(); self.runner_module.addItem(C("\u73b0\u573a\u4f5c\u4e1a"))
    self.auto_runner_suite=QComboBox(); self.auto_runner_suite.addItem(C("\u53ea\u8bfb Smoke"),"run-manifest.readonly-smoke.example.json"); self.auto_runner_suite.addItem(C("\u5b8c\u6574\u73b0\u573a\u4f5c\u4e1a Flow"),"run-manifest.field-operation-flow.local.json")
    for row,cap,field in ((3,"\u6d4b\u8bd5\u4efb\u52a1\u540d\u79f0 *",self.runner_task_name),(3,"\u5173\u8054\u5f00\u53d1\u5de5\u5355\uff08\u53ef\u9009\uff09",self.runner_work_order),(5,"\u8fd0\u884c\u73af\u5883 *",self.auto_runner_environment),(5,"\u6539\u52a8\u6a21\u5757",self.runner_module)):
        col=0 if field in (self.runner_task_name,self.auto_runner_environment) else 2; fl.addWidget(_label(cap),row,col,1,2); fl.addWidget(field,row+1,col,1,2)
    fl.addWidget(_label("\u6d4b\u8bd5\u5957\u4ef6", "RunnerFieldLabel"),7,0,1,4)
    choices=[]
    for i,(a,b,c) in enumerate((("\u53ea\u8bfb Smoke","\u57fa\u7840\u5192\u70df\u6d4b\u8bd5\uff0c\u5feb\u901f\u9a8c\u8bc1\u73af\u5883\u8fde\u901a\u6027","\u7ea6 12 \u4e2a\u7528\u4f8b"),("\u7089\u5ba4\u72b6\u6001\u56de\u5f52","\u6a21\u5757\u811a\u672c + \u7089\u5ba4\u72b6\u6001\u65ad\u8a00 + Redis \u89c2\u5bdf","\u7ea6 48 \u4e2a\u7528\u4f8b"),("\u5b8c\u6574\u73b0\u573a\u4f5c\u4e1a Flow","\u7aef\u5230\u7aef\u6d41\u8f6c\uff0c\u8986\u76d6\u73b0\u573a\u4f5c\u4e1a\u6838\u5fc3\u573a\u666f","\u7ea6 92 \u4e2a\u7528\u4f8b"))):
        choice,radio=_suite_choice(a,b,c,i==1); choices.append(radio); fl.addWidget(choice,8+i,0,1,4)
    self.runner_mutation_confirmation=QCheckBox(C("\u6211\u5df2\u786e\u8ba4\uff1a\u4ec5\u5728\u5df2\u6388\u6743\u7684\u672c\u673a\u6d4b\u8bd5\u73af\u5883\u6267\u884c\uff1b\u5141\u8bb8\u521b\u5efa\u3001\u6d41\u8f6c\u5e76\u6e05\u7406\u672c\u6b21\u6d4b\u8bd5\u6570\u636e")); fl.addWidget(self.runner_mutation_confirmation,11,0,1,4)
    self.auto_runner_status=_label("", "ValidationHint"); self.auto_runner_status.setVisible(False); fl.addWidget(self.auto_runner_status,12,0,1,4)
    preview=_card(); pl=QVBoxLayout(preview); pl.setContentsMargins(22,20,22,20); pl.addWidget(_label("\u25b6  \u6267\u884c\u9884\u89c8","PanelTitle")); pl.addWidget(_label("\u8bf7\u786e\u8ba4\u4ee5\u4e0b\u914d\u7f6e\uff0c\u521b\u5efa\u540e\u5c06\u7acb\u5373\u63d0\u4ea4\u5230 Runner \u6267\u884c\u3002","ValidationHint"));
    for a,b in (("\u6d4b\u8bd5\u5957\u4ef6","\u7089\u5ba4\u72b6\u6001\u56de\u5f52"),("\u98ce\u9669\u7b49\u7ea7","\u25cf \u4e2d"),("\u9009\u62e9\u8303\u56f4","\u6a21\u5757\u811a\u672c + \u7089\u5ba4\u72b6\u6001\u65ad\u8a00 + Redis \u89c2\u5bdf"),("\u6e05\u7406\u7b56\u7565","\u4ec5\u9650\u672c\u673a\uff1b\u81ea\u52a8\u5efa\u7acb ResourceLedger")):
        r=QHBoxLayout(); r.addWidget(_label(a)); r.addStretch(); r.addWidget(_label(b)); pl.addLayout(r)
    run=QPushButton(C("\u25b6  \u521b\u5efa\u5e76\u6267\u884c")); run.setProperty("primary",True); run.clicked.connect(lambda: _run(self)); pl.addWidget(run)
    draft=QPushButton(C("\u25a3  \u4fdd\u5b58\u8349\u7a3f")); pl.addWidget(draft); pl.addStretch(); outer.addWidget(form,3); outer.addWidget(preview,2); tabs.addTab(create,C("\u521b\u5efa\u4efb\u52a1"))

    results=QWidget(); rl=QVBoxLayout(results); stats=QHBoxLayout()
    for a,b in (("\u4eca\u65e5\u4efb\u52a1","3"),("\u901a\u8fc7\u7387\uff087 \u5929\uff09","96.8%"),("\u7b49\u5f85\u5ba1\u6279","1"),("\u5e73\u5747\u8017\u65f6","6m 18s")):
        box=_card(); q=QVBoxLayout(box);q.addWidget(_label(a,"ValidationHint"));q.addWidget(_label(b,"RunnerMetricValue"));stats.addWidget(box)
    rl.addLayout(stats); tablecard=_card();tl=QVBoxLayout(tablecard);tl.addWidget(_label("\u6d4b\u8bd5\u4efb\u52a1\u4e0e\u7ed3\u679c","PanelTitle")); self.runner_run_table=QTableWidget(0,9);self.runner_run_table.setHorizontalHeaderLabels([C(x) for x in ("\u4efb\u52a1 ID","run_id","Runner","\u73af\u5883","\u72b6\u6001","\u521b\u5efa\u65f6\u95f4","\u7ed3\u675f\u65f6\u95f4","\u4ea7\u7269\u76ee\u5f55","\u64cd\u4f5c")]);self.runner_run_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.runner_run_table.setMinimumHeight(300);tl.addWidget(self.runner_run_table);rl.addWidget(tablecard);tabs.addTab(results,C("\u4efb\u52a1\u4e0e\u7ed3\u679c"))
    catalog=QWidget(); cl=QGridLayout(catalog); cl.addWidget(_label("\u6d4b\u8bd5\u5957\u4ef6\u76ee\u5f55\uff1a\u4ece config/test_suites.yaml \u53d7\u63a7\u52a0\u8f7d","PanelTitle"),0,0,1,3)
    for i,name in enumerate(("\u53ea\u8bfb Smoke","\u7089\u5ba4\u72b6\u6001\u56de\u5f52","\u5b8c\u6574\u73b0\u573a\u4f5c\u4e1a Flow","\u79bb\u7ebf Unit","\u57fa\u7840\u6570\u636e\u914d\u7f6e\u6821\u9a8c","\u65b0\u589e\u6d4b\u8bd5\u5957\u4ef6")):
        c=_card("RunnerSuiteCard");x=QVBoxLayout(c);x.addWidget(_label(name,"PanelTitle"));x.addWidget(_label("\u6a21\u5757\u3001\u6807\u7b7e\u3001\u65f6\u95f4\u548c\u98ce\u9669\u7b56\u7565\u5747\u53d7\u7248\u672c\u63a7\u5236\u3002","ValidationHint"));x.addStretch();x.addWidget(QPushButton(C("\u521b\u5efa\u4efb\u52a1 \u203a")));cl.addWidget(c,1+i//3,i%3)
    tabs.addTab(catalog,C("\u6d4b\u8bd5\u5957\u4ef6\u76ee\u5f55")); layout.addWidget(tabs,1); return page


def _run(self):
    if not self.runner_task_name.text().strip():
        self.runner_task_name.setStyleSheet("QLineEdit { border:1px solid #e54d42; background:#fff7f5; }")
        self.auto_runner_status.setText(C("\u8bf7\u5148\u586b\u5199\u6d4b\u8bd5\u4efb\u52a1\u540d\u79f0\uff0c\u4f8b\u5982\u201c\u672c\u673a\u5b8c\u6574\u73b0\u573a\u5de5\u827a\u56de\u5f52\u201d\u3002")); self.auto_runner_status.setVisible(True); self.runner_task_name.setFocus(); return
    self._legacy_run_registered_steelmill()


def install(window_cls):
    if not hasattr(window_cls,"_legacy_run_registered_steelmill"):
        window_cls._legacy_run_registered_steelmill=window_cls.run_registered_steelmill
    window_cls._external_runner_page=modern_external_runner_page
# --- External Runner reference workspace (real application UI) ---
from PySide6.QtWidgets import QTableWidgetItem

def _runner_card(name="RunnerPanel"):
    card = QFrame()
    card.setObjectName(name)
    return card


def _runner_title(icon, title, subtitle=""):
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(3)
    lay.addWidget(_label(f"{icon}  {title}", "RunnerSectionTitle"))
    if subtitle:
        lay.addWidget(_label(subtitle, "RunnerSectionHint"))
    return box


def modern_external_runner_page(self):
    page = QWidget()
    page.setObjectName("RunnerWorkspace")
    root = QVBoxLayout(page)
    root.setContentsMargins(36, 26, 36, 30)
    root.setSpacing(16)

    title_row = QHBoxLayout()
    title_row.addWidget(_label("澶栭儴 Runner", "RunnerPageTitle"))
    title_row.addStretch()
    title_row.addWidget(_label("鈼?杩愯涓?, "RunnerOnlineBadge"))
    root.addLayout(title_row)
    root.addWidget(_label("浠庡凡鐧昏銆佺増鏈彈鎺х殑娴嬭瘯濂椾欢鍒涘缓浠诲姟锛涘钩鍙扮敓鎴?Manifest锛屽苟鐢?SteelMill Runner 鎵ц鍜屽綊妗ｇ粨鏋溿€?, "RunnerPageSubtitle"))

    context = _runner_card("RunnerContextBar")
    cl = QHBoxLayout(context); cl.setContentsMargins(20, 13, 20, 13); cl.setSpacing(18)
    self.runner_project_label = _label("褰撳墠椤圭洰锛氱⒊绱?, "RunnerContextStrong")
    self.runner_api_count = _label("139 涓帴鍙?, "RunnerContextValue")
    self.runner_context_runner = _label("Runner锛歴teelmill-runner 0.1.0", "RunnerContextValue")
    cl.addWidget(self.runner_project_label); cl.addWidget(_label("路", "RunnerContextDivider")); cl.addWidget(self.runner_api_count); cl.addWidget(_label("路", "RunnerContextDivider")); cl.addWidget(self.runner_context_runner)
    cl.addStretch()
    advanced = QPushButton("楂樼骇璁剧疆 鈥?); advanced.setObjectName("RunnerGhostButton")
    cl.addWidget(advanced)
    root.addWidget(context)

    tabs = QTabWidget(); tabs.setObjectName("RunnerCenterTabs")
    root.addWidget(tabs, 1)

    # Create task
    create = QWidget(); create_l = QHBoxLayout(create); create_l.setContentsMargins(0, 12, 0, 0); create_l.setSpacing(18)
    form = _runner_card("RunnerCreateCard"); form_l = QVBoxLayout(form); form_l.setContentsMargins(26, 25, 26, 22); form_l.setSpacing(18)
    form_l.addWidget(_runner_title("鈻?, "鍒涘缓娴嬭瘯浠诲姟", "鍏宠仈宸ヤ綔椤癸紝骞朵粠鍔ㄦ€佸浠剁洰褰曚腑閫夋嫨鍙墽琛岃寖鍥淬€?))
    fields = QGridLayout(); fields.setHorizontalSpacing(16); fields.setVerticalSpacing(8)
    self.runner_task_name = QLineEdit("鐐夊鐘舵€佸洖褰?- 2026/09/15")
    self.runner_work_order = QLineEdit(); self.runner_work_order.setPlaceholderText("渚嬪锛歋M-248 鐐夊鐘舵€佽皟鏁?)
    self.auto_runner_environment = QComboBox(); self.auto_runner_environment.addItems(["娴嬭瘯鐜 路 鏈満 127.0.0.1:5010", "鍏变韩娴嬭瘯鐜"])
    self.runner_module = QComboBox(); self.runner_module.addItems(["鐜板満浣滀笟", "鍩虹鏁版嵁涓庡伐鑹洪厤缃?, "鎶ヨ"])
    for col, label, field in ((0, "浠诲姟鍚嶇О *", self.runner_task_name), (1, "鍏宠仈寮€鍙戝伐鍗曪紙鍙€夛級", self.runner_work_order), (0, "杩愯鐜 *", self.auto_runner_environment), (1, "鏀瑰姩妯″潡 *", self.runner_module)):
        row = 0 if col == 0 and label.startswith("浠诲姟") else 0 if col == 1 and label.startswith("鍏宠仈") else 2
        fields.addWidget(_label(label, "RunnerFieldLabel"), row, col)
        fields.addWidget(field, row + 1, col)
    form_l.addLayout(fields)
    form_l.addWidget(_label("娴嬭瘯濂椾欢", "RunnerSectionLabel"))
    suite_search = QLineEdit(); suite_search.setPlaceholderText("鎼滅储濂椾欢鍚嶇О銆佹爣绛炬垨鑳藉姏鈥?); suite_search.setObjectName("RunnerSuiteSearch")
    form_l.addWidget(suite_search)
    self.auto_runner_suite = QComboBox()
    choices = []
    for idx, (name, detail, cases) in enumerate((
        ("鍙 Smoke", "鍩虹鍐掔儫娴嬭瘯锛屽揩閫熼獙璇佺幆澧冭繛閫氭€?, "绾?12 涓敤渚?),
        ("鐐夊鐘舵€佸洖褰?, "妯″潡鑴氭湰 + 鐐夊鐘舵€佹柇瑷€ + Redis 瑙傚療", "绾?48 涓敤渚?),
        ("瀹屾暣鐜板満浣滀笟 Flow", "瑕嗙洊鐜板満浣滀笟鏍稿績涓氬姟鍦烘櫙", "绾?92 涓敤渚?),
    )):
        self.auto_runner_suite.addItem(name, name)
        row, radio = _suite_choice(name, detail, cases, idx == 1)
        row.setObjectName("RunnerSuiteChoice")
        choices.append((row, name.lower()))
        form_l.addWidget(row)
    self.runner_mutation_confirmation = QCheckBox("鎴戝凡纭浠呭湪宸叉巿鏉冩祴璇曠幆澧冩墽琛岋紝骞跺厑璁稿垱寤恒€佹祦杞拰娓呯悊娴嬭瘯鏁版嵁")
    form_l.addWidget(self.runner_mutation_confirmation)
    self.auto_runner_status = _label("", "ValidationHint"); self.auto_runner_status.setVisible(False); form_l.addWidget(self.auto_runner_status)
    suite_search.textChanged.connect(lambda term: [row.setVisible(term.lower() in text or not term) for row, text in choices])

    preview = _runner_card("RunnerPreviewCard"); pre_l = QVBoxLayout(preview); pre_l.setContentsMargins(22, 22, 22, 22); pre_l.setSpacing(12)
    pre_l.addWidget(_runner_title("鈻?, "鎵ц纭", "璇风‘璁や换鍔＄殑鎵ц鑼冨洿涓庨闄╃瓥鐣ャ€?))
    for key, value in (("鍒嗛厤 Runner", "steelmill-runner  v0.1.0"), ("娴嬭瘯濂椾欢", "鐐夊鐘舵€佸洖褰?), ("椋庨櫓绛夌骇", "鍙竻鐞嗗啓鍏?), ("閫夋嫨鑼冨洿", "Flow + Redis 瑙傚療"), ("娓呯悊绛栫暐", "ResourceLedger 閫嗗簭娓呯悊")):
        row = QWidget(); row.setObjectName("RunnerPreviewRow"); r = QVBoxLayout(row); r.setContentsMargins(0, 8, 0, 8); r.setSpacing(2)
        r.addWidget(_label(key, "RunnerPreviewKey")); r.addWidget(_label(value, "RunnerPreviewValue")); pre_l.addWidget(row)
    run = QPushButton("鈻? 鍒涘缓骞舵墽琛?); run.setProperty("primary", True); run.setObjectName("RunnerPrimaryAction"); run.clicked.connect(lambda: _run(self)); pre_l.addWidget(run)
    draft = QPushButton("鈻? 淇濆瓨鑽夌"); draft.setObjectName("RunnerSecondaryAction"); pre_l.addWidget(draft); pre_l.addStretch()
    create_l.addWidget(form, 3); create_l.addWidget(preview, 2)
    tabs.addTab(create, "鈻? 鍒涘缓浠诲姟")

    # Task results
    results = QWidget(); result_l = QVBoxLayout(results); result_l.setContentsMargins(0, 12, 0, 0); result_l.setSpacing(18)
    stat_l = QHBoxLayout(); stat_l.setSpacing(18)
    for title, value, kind in (("浠婃棩浠诲姟", "3", "RunnerMetricBlue"), ("閫氳繃鐜囷紙7 澶╋級", "96.8%", "RunnerMetricBlue"), ("绛夊緟瀹℃壒", "1", "RunnerMetricAmber"), ("骞冲潎鑰楁椂", "6m 18s", "RunnerMetricBlue")):
        stat = _runner_card(kind); sl = QVBoxLayout(stat); sl.setContentsMargins(24, 18, 24, 18); sl.addWidget(_label(title, "RunnerMetricCaption")); sl.addWidget(_label(value, "RunnerMetricValue")); stat_l.addWidget(stat)
    result_l.addLayout(stat_l)
    result_card = _runner_card("RunnerResultCard"); rc = QVBoxLayout(result_card); rc.setContentsMargins(26, 24, 26, 24); rc.setSpacing(16)
    header = QHBoxLayout(); header.addWidget(_label("鈱? 娴嬭瘯浠诲姟涓庣粨鏋?, "RunnerSectionTitle")); header.addWidget(_label("鎵ц涓殑浠诲姟涓嶅彲缂栬緫锛涜澶嶅埗涓烘柊浠诲姟鍚庤皟鏁淬€?, "RunnerSectionHint")); header.addStretch(); refresh = QPushButton("鈫?鍒锋柊鏁版嵁"); refresh.setObjectName("RunnerGhostButton"); header.addWidget(refresh); rc.addLayout(header)
    filters = QHBoxLayout(); filters.setSpacing(12)
    run_search = QLineEdit(); run_search.setPlaceholderText("鎼滅储浠诲姟 ID銆乺un_id銆佸伐鍗曗€?); run_search.setObjectName("RunnerFilterInput")
    status_filter = QComboBox(); status_filter.addItems(["鍏ㄩ儴鐘舵€?, "passed", "queued", "寰呬汉宸ユ壒鍑?])
    module_filter = QComboBox(); module_filter.addItems(["鍏ㄩ儴妯″潡", "鐜板満浣滀笟", "鍩虹鏁版嵁"])
    apply = QPushButton("绛涢€?); apply.setObjectName("RunnerFilterAction")
    reset = QPushButton("閲嶇疆"); reset.setObjectName("RunnerGhostButton")
    filters.addWidget(run_search, 3); filters.addWidget(status_filter, 1); filters.addWidget(module_filter, 1); filters.addWidget(apply); filters.addWidget(reset); rc.addLayout(filters)
    self.runner_run_table = QTableWidget(3, 7); self.runner_run_table.setObjectName("RunnerRunTable")
    self.runner_run_table.setHorizontalHeaderLabels(["浠诲姟", "鍏宠仈宸ュ崟", "娴嬭瘯濂椾欢", "鐜", "鐘舵€?, "鎵ц鏃堕棿", "鎿嶄綔"])
    data = [("#1428\nsteelmill_20260914_101500", "SM-248", "鐜板満浣滀笟 / 鐐夊鐘舵€佸洖褰?, "鏈満 127.0.0.1", "passed", "6m 18s", "鈼? 鈬? 猝?), ("#1429\nsteelmill_20260914_104200", "鈥?, "鐜板満浣滀笟 / 鍙 Smoke", "鏈満 127.0.0.1", "queued", "鈥?, "鈼? 鈬? 猝?), ("#1430\nsteelmill_20260914_110000", "SM-251", "鐜板満浣滀笟 / 瀹屾暣 Flow", "鏈満 127.0.0.1", "寰呬汉宸ユ壒鍑?, "鈥?, "鈼? 鈬? 猝?)]
    for r, row in enumerate(data):
        for c, value in enumerate(row):
            item = QTableWidgetItem(value); self.runner_run_table.setItem(r, c, item)
    self.runner_run_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.runner_run_table.verticalHeader().hide(); self.runner_run_table.setMinimumHeight(260); self.runner_run_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    rc.addWidget(self.runner_run_table); result_l.addWidget(result_card); tabs.addTab(results, "鈱? 浠诲姟涓庣粨鏋? 3")

    # Dynamic suite catalog
    catalog = QWidget(); catalog_l = QVBoxLayout(catalog); catalog_l.setContentsMargins(0, 12, 0, 0); catalog_l.setSpacing(0)
    catalog_card = _runner_card("RunnerCatalogCard"); cat_l = QVBoxLayout(catalog_card); cat_l.setContentsMargins(26, 24, 26, 24); cat_l.setSpacing(18)
    cat_h = QHBoxLayout(); cat_h.addWidget(_label("鈻? 娴嬭瘯濂椾欢鐩綍", "RunnerSectionTitle")); cat_h.addWidget(_label("浠庢祴璇曞垎鏀殑 config/test_suites.yaml 鍙楁帶鍔犺浇", "RunnerSectionHint")); cat_h.addStretch(); cat_refresh = QPushButton("鈫?鍒锋柊鐩綍"); cat_refresh.setObjectName("RunnerGhostButton"); cat_h.addWidget(cat_refresh); cat_l.addLayout(cat_h)
    cat_filters = QHBoxLayout(); cat_filters.setSpacing(12)
    cat_search = QLineEdit(); cat_search.setPlaceholderText("鎼滅储濂椾欢銆佹爣绛炬垨璺緞鈥?); cat_search.setObjectName("RunnerFilterInput")
    search_field = QComboBox(); search_field.addItems(["鍏ㄩ儴瀛楁", "濂椾欢鍚嶇О", "鏍囩", "鎵€灞炴ā鍧?])
    cat_help = QPushButton("濂椾欢鐧昏璇存槑"); cat_help.setObjectName("RunnerGhostButton")
    cat_filters.addWidget(cat_search, 4); cat_filters.addWidget(search_field, 1); cat_filters.addStretch(); cat_filters.addWidget(cat_help); cat_l.addLayout(cat_filters)
    chips = QHBoxLayout(); chips.setSpacing(10)
    for text, active in (("鍏ㄩ儴 6", True), ("鐜板満浣滀笟 3", False), ("鍩虹鏁版嵁 1", False), ("鎶ヨ 0", False), ("绂荤嚎 1", False)):
        chip = QPushButton(text); chip.setObjectName("RunnerActiveChip" if active else "RunnerChip"); chips.addWidget(chip)
    chips.addStretch(); chips.addWidget(_label("鏄剧ず 6 / 6 涓浠?, "RunnerCatalogCount")); cat_l.addLayout(chips)
    grid = QGridLayout(); grid.setHorizontalSpacing(16); grid.setVerticalSpacing(16)
    for i, name in enumerate(("鍙 Smoke", "鐐夊鐘舵€佸洖褰?, "瀹屾暣鐜板満浣滀笟 Flow", "绂荤嚎 Unit", "鍩虹鏁版嵁閰嶇疆鏍￠獙", "鏂板娴嬭瘯濂椾欢")):
        suite = _runner_card("RunnerSuiteCard"); su = QVBoxLayout(suite); su.setContentsMargins(20, 18, 20, 16); su.setSpacing(8)
        su.addWidget(_label("鈼? " + name, "RunnerSuiteName")); su.addWidget(_label("妯″潡銆佹爣绛俱€侀闄╃瓥鐣ュ拰鏈€杩戦獙璇佷俊鎭潎鐢卞彈鎺х洰褰曞姩鎬佸姞杞姐€?, "RunnerSectionHint")); su.addStretch(); action = QPushButton("鏌ョ湅鑼冨洿      鍒涘缓浠诲姟 鈥?); action.setObjectName("RunnerSuiteAction"); su.addWidget(action); grid.addWidget(suite, i // 3, i % 3)
    cat_l.addLayout(grid); catalog_l.addWidget(catalog_card); tabs.addTab(catalog, "鈻? 娴嬭瘯濂椾欢鐩綍  6")
    return page

# --- Runner workspace behaviour, dynamic catalog and resize safety ---
from pathlib import Path
from testpilot.engines.suite_catalog import load_suite_catalog, SuiteCatalogError


_runner_reference_page = modern_external_runner_page


def _runner_dynamic_suites():
    try:
        return load_suite_catalog(Path.cwd())
    except (OSError, SuiteCatalogError):
        return ()


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear_layout(item.layout())


def _runner_suite_card(suite):
    card = _runner_card("RunnerSuiteCard")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(20, 18, 20, 16)
    lay.setSpacing(8)
    lay.addWidget(_label("鈼? " + suite.name, "RunnerSuiteName"))
    lay.addWidget(_label(suite.description, "RunnerSectionHint"))
    lay.addWidget(_label(f"妯″潡锛歿suite.module}  路  榛樿瓒呮椂锛歿suite.timeout_seconds} 绉?, "RunnerSuiteMeta"))
    lay.addStretch()
    action = QPushButton("鏌ョ湅鑼冨洿      鍒涘缓浠诲姟 鈥?)
    action.setObjectName("RunnerSuiteAction")
    lay.addWidget(action)
    return card


def _install_runner_advanced_panel(page, trigger):
    root = page.layout()
    panel = _runner_card("RunnerAdvancedInline")
    panel.setVisible(False)
    grid = QGridLayout(panel)
    grid.setContentsMargins(26, 20, 26, 20)
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(10)
    grid.addWidget(_label("鈿? Runner 楂樼骇璁剧疆", "RunnerSectionTitle"), 0, 0, 1, 4)
    grid.addWidget(_label("褰撳墠閰嶇疆浠呭簲鐢ㄤ簬鏈鍒涘缓浠诲姟锛屾彁浜ゅ悗浼氬浐鍖栧埌 Manifest銆?, "RunnerSectionHint"), 1, 0, 1, 4)
    fields = (
        ("Runner 鍚嶇О *", QComboBox(), ["steelmill-runner 路 鏈満鍙敤"]),
        ("Runner 鐗堟湰", QComboBox(), ["0.1.0锛堟帹鑽愶級"]),
        ("闀滃儚鏍囪瘑", QLineEdit("registry.example.com/steelmill/runner:0.1.0"), None),
        ("椤圭洰 Adapter Key *", QLineEdit("steelmill"), None),
        ("SteelMill Python", QLineEdit(r"C:\workspace\steel_mill\.venv\Scripts\python.exe"), None),
        ("宸ヤ綔鐩綍", QLineEdit(r"C:\workspace\steel_mill"), None),
    )
    for i, (label, field, choices) in enumerate(fields):
        if choices:
            field.addItems(choices)
        col = i % 2 * 2
        row = 2 + (i // 2) * 2
        grid.addWidget(_label(label, "RunnerFieldLabel"), row, col, 1, 2)
        grid.addWidget(field, row + 1, col, 1, 2)
    save = QPushButton("淇濆瓨褰撳墠閰嶇疆")
    save.setObjectName("RunnerPrimaryAction")
    grid.addWidget(save, 8, 3)
    save.clicked.connect(lambda: save.setText("鉁?宸蹭繚瀛?))
    tabs = page.findChild(QTabWidget, "RunnerCenterTabs")
    root.insertWidget(root.indexOf(tabs), panel)
    def toggle():
        panel.setVisible(not panel.isVisible())
        trigger.setText("鏀惰捣璁剧疆 鈥? if panel.isVisible() else "楂樼骇璁剧疆 鈥?)
        if panel.isVisible():
            panel.adjustSize()
    trigger.clicked.connect(toggle)


def _rebuild_dynamic_catalog(page):
    tabs = page.findChild(QTabWidget, "RunnerCenterTabs")
    if not tabs:
        return
    suites = _runner_dynamic_suites()
    if not suites:
        return
    catalog_page = tabs.widget(2)
    catalog_card = catalog_page.findChild(QFrame, "RunnerCatalogCard")
    catalog_layout = catalog_card.layout()
    grid_item = catalog_layout.itemAt(3)
    if not grid_item or not grid_item.layout():
        return
    grid = grid_item.layout()
    _clear_layout(grid)
    cards = []
    for i, suite in enumerate(suites):
        card = _runner_suite_card(suite)
        grid.addWidget(card, i // 3, i % 3)
        cards.append((card, suite))
    for label in catalog_page.findChildren(QLabel, "RunnerCatalogCount"):
        label.setText(f"鏄剧ず {len(suites)} / {len(suites)} 涓浠?)
    tabs.setTabText(2, f"鈻? 娴嬭瘯濂椾欢鐩綍  {len(suites)}")
    inputs = catalog_page.findChildren(QLineEdit, "RunnerFilterInput")
    if inputs:
        search = inputs[-1]
        def apply_filter(text):
            text = text.strip().lower()
            for card, suite in cards:
                source = " ".join((suite.name, suite.module, suite.description, suite.risk)).lower()
                card.setVisible(not text or text in source)
        search.textChanged.connect(apply_filter)


def modern_external_runner_page(self):
    page = _runner_reference_page(self)
    # Prevent control collapse while still allowing the content column to scale.
    for field in (*page.findChildren(QLineEdit), *page.findChildren(QComboBox)):
        field.setMinimumHeight(42)
        field.setSizePolicy(field.sizePolicy().horizontalPolicy(), field.sizePolicy().verticalPolicy())
    for row in page.findChildren(QFrame, "RunnerSuiteChoice"):
        row.setMinimumHeight(74)
    table = page.findChild(QTableWidget, "RunnerRunTable")
    if table:
        table.setMinimumHeight(300)
        table.setWordWrap(False)
    trigger = next((button for button in page.findChildren(QPushButton, "RunnerGhostButton") if "楂樼骇璁剧疆" in button.text()), None)
    if trigger:
        _install_runner_advanced_panel(page, trigger)
    _rebuild_dynamic_catalog(page)
    return page

# --- Stable Runner create-page geometry: scroll instead of compression ---
from PySide6.QtWidgets import QScrollArea

_runner_dynamic_page = modern_external_runner_page


def _stabilize_runner_create_page(page):
    tabs = page.findChild(QTabWidget, "RunnerCenterTabs")
    if not tabs or isinstance(tabs.widget(0), QScrollArea):
        return
    create = tabs.widget(0)
    tab_text = tabs.tabText(0)
    tabs.removeTab(0)
    create.setMinimumWidth(1080)
    create.setMinimumHeight(760)
    outer = create.layout()
    outer.setContentsMargins(0, 12, 0, 0)
    form = create.findChild(QFrame, "RunnerCreateCard")
    preview = create.findChild(QFrame, "RunnerPreviewCard")
    if form:
        form.setMinimumWidth(650)
        form_layout = form.layout()
        fields = form_layout.itemAt(1).layout() if form_layout and form_layout.count() > 1 else None
        if fields:
            fields.setRowMinimumHeight(0, 24)
            fields.setRowMinimumHeight(1, 44)
            fields.setRowMinimumHeight(2, 24)
            fields.setRowMinimumHeight(3, 44)
            fields.setColumnMinimumWidth(0, 260)
            fields.setColumnMinimumWidth(1, 260)
        for choice in form.findChildren(QFrame, "RunnerSuiteChoice"):
            choice.setMinimumHeight(82)
            choice.setMaximumHeight(82)
    if preview:
        preview.setMinimumWidth(370)
        preview.setMinimumHeight(620)
    scroll = QScrollArea()
    scroll.setObjectName("RunnerCreateScroll")
    scroll.setWidgetResizable(False)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setWidget(create)
    tabs.insertTab(0, scroll, tab_text)
    tabs.setCurrentIndex(0)


def modern_external_runner_page(self):
    page = _runner_dynamic_page(self)
    _stabilize_runner_create_page(page)
    return page

# --- Native SVG icon replacement for the real Runner workspace ---
from PySide6.QtCore import QByteArray
from PySide6.QtSvgWidgets import QSvgWidget


def _runner_svg(kind, size=22):
    paths = {
        "task": '<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M9 3.5h6M9 10h6M9 14h6M9 18h4"/>',
        "preview": '<path d="m9 6 7 6-7 6V6Z"/><path d="M4 4h16v16H4z"/>',
        "results": '<path d="M4 19V5M4 19h16"/><path d="m7 14 3-3 3 2 5-7"/><circle cx="18" cy="6" r="1"/>',
        "catalog": '<path d="m12 3 8 4-8 4-8-4 8-4Z"/><path d="m4 12 8 4 8-4M4 16l8 4 8-4"/>',
        "settings": '<circle cx="12" cy="12" r="3"/><path d="M19 12h2M3 12h2M12 3v2M12 19v2M17 7l1.5-1.5M5.5 18.5 7 17M17 17l1.5 1.5M5.5 5.5 7 7"/>',
    }
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#2584e9" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">{paths[kind]}</svg>'
    widget = QSvgWidget()
    widget.load(QByteArray(svg.encode("utf-8")))
    widget.setFixedSize(size, size)
    return widget


def _runner_title(icon, title, subtitle=""):
    block = QWidget()
    row = QHBoxLayout(block)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(9)
    row.addWidget(_runner_svg("task" if icon == "鈻? else "preview"))
    text = QWidget(); stack = QVBoxLayout(text); stack.setContentsMargins(0, 0, 0, 0); stack.setSpacing(3)
    stack.addWidget(_label(title, "RunnerSectionTitle"))
    if subtitle:
        stack.addWidget(_label(subtitle, "RunnerSectionHint"))
    row.addWidget(text, 1)
    return block


_runner_svg_page = modern_external_runner_page


def _replace_runner_header_glyphs(page):
    icon_by_prefix = (("鈱?, "results"), ("鈻?, "catalog"), ("鈿?, "settings"))
    for label in page.findChildren(QLabel, "RunnerSectionTitle"):
        raw = label.text().strip()
        for prefix, kind in icon_by_prefix:
            if raw.startswith(prefix):
                label.setText(raw.lstrip(prefix).strip())
                parent_layout = label.parentWidget().layout() if label.parentWidget() else None
                if parent_layout and hasattr(parent_layout, "insertWidget") and parent_layout.indexOf(label) >= 0:
                    parent_layout.insertWidget(parent_layout.indexOf(label), _runner_svg(kind))
                break


def modern_external_runner_page(self):
    page = _runner_svg_page(self)
    _replace_runner_header_glyphs(page)
    return page

# --- Prototype-aligned live data binding (task results and dynamic catalog) ---
from datetime import datetime
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QToolButton


def _prototype_refresh_runner_runs(self):
    if not hasattr(self, "runner_run_table"):
        return
    rows = self.db.list_runner_runs(self.current_project_id) if self.current_project_id else []
    self._runner_run_rows = rows
    table = self.runner_run_table
    table.blockSignals(True)
    table.clearContents()
    table.setRowCount(len(rows))
    table.setColumnCount(7)
    table.setHorizontalHeaderLabels(["浠诲姟", "鍏宠仈宸ュ崟", "娴嬭瘯濂椾欢", "鐜", "鐘舵€?, "鎵ц鏃堕棿", "鎿嶄綔"])
    try:
        for index, row in enumerate(rows):
            manifest = row.get("manifest") or {}
            metadata = manifest.get("metadata") or {}
            result = row.get("result") or {}
            task_name = str(metadata.get("test_name") or f"#{row.get('id', '')}")
            run_key = str(row.get("run_key") or "")
            suite = str(metadata.get("suite") or manifest.get("suite") or "鈥?)
            work_order = str(metadata.get("work_order") or "鈥?)
            duration = result.get("duration") or result.get("duration_seconds") or "鈥?
            if isinstance(duration, (int, float)):
                duration = f"{int(duration) // 60}m {int(duration) % 60}s"
            values = (f"{task_name}\n{run_key}" if run_key else task_name, work_order, suite,
                      str(row.get("environment_name") or "鈥?), "", str(duration))
            for column, value in enumerate(values):
                table.setItem(index, column, QTableWidgetItem(str(value or "鈥?)))
            status = str(row.get("status") or "queued").lower()
            status_label = QLabel(status)
            status_label.setAlignment(Qt.AlignCenter)
            status_colors = {
                "passed": ("#e8f8ef", "#16834a"), "failed": ("#fff0f0", "#cf3f3f"),
                "error": ("#fff0f0", "#cf3f3f"), "running": ("#eaf4ff", "#1677e8"),
                "queued": ("#fff8e7", "#9a6800"),
            }
            bg, fg = status_colors.get(status, status_colors["queued"])
            status_label.setStyleSheet(f"background:{bg}; color:{fg}; border:none; border-radius:11px; padding:4px 8px; font-weight:700;")
            table.setCellWidget(index, 4, status_label)
            actions = QWidget(); action_layout = QHBoxLayout(actions); action_layout.setContentsMargins(2, 0, 2, 0); action_layout.setSpacing(4)
            for kind, tip in (("view", "鏌ョ湅浠诲姟"), ("download", "鎵撳紑浜х墿"), ("copy", "澶嶅埗浠诲姟")):
                button = QToolButton(); button.setIcon(self._runner_action_icon(kind if kind != "copy" else "view")); button.setIconSize(QSize(17, 17)); button.setAutoRaise(True); button.setToolTip(tip); button.setFixedSize(28, 28)
                if kind == "view":
                    button.clicked.connect(lambda _=False, i=index: table.selectRow(i))
                elif kind == "download":
                    button.clicked.connect(lambda _=False, i=index: self.open_runner_artifacts(i))
                else:
                    button.clicked.connect(lambda _=False, i=index: self.run_registered_steelmill())
                action_layout.addWidget(button)
            table.setCellWidget(index, 6, actions)
    finally:
        table.blockSignals(False)


def _prototype_refresh_catalog_chips(page):
    tabs = page.findChild(QTabWidget, "RunnerCenterTabs")
    if not tabs:
        return
    suites = _runner_dynamic_suites()
    catalog = tabs.widget(2)
    if not catalog:
        return
    buttons = catalog.findChildren(QPushButton)
    modules = {}
    for suite in suites:
        modules[suite.module] = modules.get(suite.module, 0) + 1
    for button in buttons:
        if button.objectName() == "RunnerActiveChip":
            button.setText(f"鍏ㄩ儴 {len(suites)}")
        elif button.objectName() == "RunnerChip":
            original = button.text().split(" ")[0]
            count = modules.get(original, 0)
            button.setVisible(count > 0)
            if count:
                button.setText(f"{original} {count}")


_runner_live_page = modern_external_runner_page


def modern_external_runner_page(self):
    page = _runner_live_page(self)
    tabs = page.findChild(QTabWidget, "RunnerCenterTabs")
    if tabs and isinstance(tabs.widget(0), QScrollArea):
        tabs.widget(0).setWidgetResizable(True)
    _prototype_refresh_catalog_chips(page)
    return page


def install(window_cls):
    if not hasattr(window_cls, "_legacy_run_registered_steelmill"):
        window_cls._legacy_run_registered_steelmill = window_cls.run_registered_steelmill
    window_cls._external_runner_page = modern_external_runner_page
    window_cls.refresh_external_runner_runs = _prototype_refresh_runner_runs

# --- Clean, prototype-faithful External Runner workspace ---
from PySide6.QtWidgets import QButtonGroup


def _reference_rule():
    line = QFrame()
    line.setObjectName("RunnerReferenceRule")
    line.setFrameShape(QFrame.HLine)
    return line


def _reference_heading(kind, title, subtitle, code=""):
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(12)
    row.addWidget(_runner_svg(kind, 28), 0, Qt.AlignTop)
    copy = QWidget(); col = QVBoxLayout(copy); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(3)
    col.addWidget(_label(title, "RunnerReferenceHeading"))
    col.addWidget(_label(subtitle, "RunnerReferenceSubheading"))
    row.addWidget(copy, 1)
    if code:
        row.addWidget(_label(code, "RunnerReferenceCode"), 0, Qt.AlignTop)
    return box


def _reference_suite_row(suite, index, selected):
    row = _runner_card("RunnerReferenceSuite")
    row.setProperty("selected", selected)
    row.setMinimumHeight(84)
    lay = QHBoxLayout(row); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(12)
    number = _label(f"{index:02d}", "RunnerSuiteNumber")
    selector = QPushButton("鉁?); selector.setCheckable(True); selector.setChecked(selected)
    selector.setObjectName("RunnerSuiteSelector"); selector.setFixedSize(28, 28)
    text = QWidget(); stack = QVBoxLayout(text); stack.setContentsMargins(0, 0, 0, 0); stack.setSpacing(4)
    title = QHBoxLayout(); title.setSpacing(7)
    title.addWidget(_label(suite.name, "RunnerSuiteReferenceName"))
    risk = {"readonly": "鍙", "mutation": "鍙竻鐞嗗啓鍏?, "offline": "绂荤嚎"}.get(suite.risk, suite.risk)
    risk_label = _label(risk, "RunnerSuiteRisk")
    title.addWidget(risk_label); title.addStretch()
    stack.addLayout(title)
    stack.addWidget(_label(f"{suite.description}    棰勮 {max(1, suite.timeout_seconds // 60)} 鍒嗛挓", "RunnerSuiteReferenceMeta"))
    lay.addWidget(number); lay.addWidget(text, 1); lay.addWidget(selector)
    return row, selector


def _reference_catalog_card(suite):
    card = _runner_card("RunnerReferenceCatalogCard")
    card.setMinimumHeight(236); card.setMaximumHeight(236)
    lay = QVBoxLayout(card); lay.setContentsMargins(22, 19, 22, 17); lay.setSpacing(8)
    header = QHBoxLayout(); header.addWidget(_runner_svg("catalog", 22)); header.addWidget(_label(suite.name, "RunnerCatalogReferenceName")); header.addStretch(); lay.addLayout(header)
    lay.addWidget(_label(suite.description, "RunnerCatalogReferenceDescription"))
    tags = QHBoxLayout(); tags.setSpacing(6)
    tags.addWidget(_label({"readonly": "鍙", "mutation": "闇€浜哄伐鎵瑰噯", "offline": "绂荤嚎"}.get(suite.risk, suite.risk), "RunnerSuiteRisk"))
    tags.addWidget(_label(suite.module, "RunnerCatalogTag")); tags.addStretch(); lay.addLayout(tags)
    lay.addWidget(_label(f"妯″潡锛歿suite.module}  路  榛樿瓒呮椂锛歿suite.timeout_seconds} 绉?, "RunnerSuiteReferenceMeta"))
    lay.addStretch()
    footer = QHBoxLayout(); footer.setContentsMargins(0, 0, 0, 0); footer.setSpacing(8)
    scope = QPushButton("查看范围"); scope.setObjectName("RunnerCatalogAction")
    create = QPushButton("创建任务 ›"); create.setObjectName("RunnerCatalogAction")
    footer.addWidget(scope); footer.addStretch(); footer.addWidget(create); lay.addLayout(footer)
    return card


def modern_external_runner_page(self):
    page = QWidget(); page.setObjectName("RunnerWorkspace")
    root = QVBoxLayout(page); root.setContentsMargins(34, 26, 34, 24); root.setSpacing(15)

    title = QHBoxLayout(); title.addWidget(_label("澶栭儴 Runner", "RunnerPageTitle")); title.addStretch(); title.addWidget(_label("鈼?杩愯涓?, "RunnerOnlineBadge")); root.addLayout(title)
    root.addWidget(_label("浠庡凡鐧昏銆佺増鏈彈鎺х殑娴嬭瘯濂椾欢鍒涘缓浠诲姟锛涘钩鍙扮敓鎴?Manifest锛屽苟鐢?SteelMill Runner 鎵ц鍜屽綊妗ｇ粨鏋溿€?, "RunnerPageSubtitle"))

    banner = _runner_card("RunnerContextBar"); bar = QHBoxLayout(banner); bar.setContentsMargins(20, 13, 20, 13); bar.setSpacing(14)
    self.runner_project_label = _label("褰撳墠椤圭洰锛氱⒊绱? 路  139 涓帴鍙?, "RunnerContextStrong")
    bar.addWidget(self.runner_project_label); bar.addWidget(_label("路", "RunnerContextDivider")); bar.addWidget(_label("Runner锛歴teelmill-runner 0.1.0", "RunnerContextValue")); bar.addStretch()
    advanced = QPushButton("楂樼骇璁剧疆 鈥?); advanced.setObjectName("RunnerGhostButton"); bar.addWidget(advanced); root.addWidget(banner)

    advanced_panel = _runner_card("RunnerAdvancedInline"); advanced_panel.setVisible(False)
    ap = QGridLayout(advanced_panel); ap.setContentsMargins(24, 18, 24, 18); ap.setHorizontalSpacing(15); ap.setVerticalSpacing(8)
    ap.addWidget(_reference_heading("settings", "Runner 楂樼骇璁剧疆", "浠ヤ笅閰嶇疆浠呭簲鐢ㄤ簬褰撳墠鍒涘缓浠诲姟"), 0, 0, 1, 4)
    self.runner_name = QLineEdit("steelmill-runner")
    self.runner_version = QLineEdit("0.1.0")
    self.runner_image = QLineEdit("registry.example.com/steelmill/runner:0.1.0")
    self.runner_project_key = QLineEdit("steelmill")
    self.runner_python_executable = QLineEdit()
    self.runner_python_executable.setPlaceholderText("SteelMill Python 瑙ｉ噴鍣ㄥ畬鏁磋矾寰?)
    self.runner_workdir = QLineEdit()
    self.runner_workdir.setPlaceholderText("SteelMill 宸ヤ綔鐩綍")
    self.runner_enabled = QCheckBox("鍚敤姝?Runner")
    self.runner_enabled.setChecked(True)
    self.runner_save_status = _label("", "ValidationHint")
    settings = (("Runner 鍚嶇О *", self.runner_name), ("闀滃儚鏍囪瘑", self.runner_image), ("Runner 鐗堟湰", self.runner_version), ("椤圭洰 Adapter Key *", self.runner_project_key), ("SteelMill Python", self.runner_python_executable), ("宸ヤ綔鐩綍", self.runner_workdir))
    for i, (label, field) in enumerate(settings):
        c = (i % 2) * 2; r = 2 + (i // 2) * 2
        ap.addWidget(_label(label, "RunnerFieldLabel"), r, c, 1, 2); ap.addWidget(field, r + 1, c, 1, 2)
    ap.addWidget(self.runner_enabled, 8, 0, 1, 2); ap.addWidget(self.runner_save_status, 8, 2)
    save = QPushButton("淇濆瓨褰撳墠閰嶇疆"); save.setObjectName("RunnerPrimaryAction"); ap.addWidget(save, 8, 3)
    save.clicked.connect(self.save_external_runner)
    advanced.clicked.connect(lambda: (advanced_panel.setVisible(not advanced_panel.isVisible()), advanced.setText("鏀惰捣璁剧疆 鈥? if advanced_panel.isVisible() else "楂樼骇璁剧疆 鈥?)))
    root.addWidget(advanced_panel)

    tabs = QTabWidget(); tabs.setObjectName("RunnerCenterTabs"); root.addWidget(tabs, 1)
    suites = _runner_dynamic_suites()

    # Page 1: Create task, matching reference sections
    create_content = QWidget(); create_content.setMinimumWidth(1020)
    create_outer = QHBoxLayout(create_content); create_outer.setContentsMargins(0, 12, 0, 0); create_outer.setSpacing(18)
    form = _runner_card("RunnerReferenceForm"); fl = QVBoxLayout(form); fl.setContentsMargins(26, 24, 26, 22); fl.setSpacing(18)
    fl.addWidget(_reference_heading("task", "浠诲姟淇℃伅", "涓烘湰娆℃墽琛屽缓绔嬪彲杩芥函鐨勪换鍔¤褰?, "JOB / 01"))
    grid1 = QGridLayout(); grid1.setHorizontalSpacing(18); grid1.setVerticalSpacing(8)
    self.runner_task_name = QLineEdit("鐐夊鐘舵€佸洖褰?- 2026/09/15")
    self.runner_work_order = QLineEdit(); self.runner_work_order.setPlaceholderText("渚嬪锛歋M-248 鐐夊鐘舵€佽皟鏁?)
    for c, name, field in ((0, "浠诲姟鍚嶇О *", self.runner_task_name), (1, "鍏宠仈寮€鍙戝伐鍗曪紙鍙€夛級", self.runner_work_order)):
        grid1.addWidget(_label(name, "RunnerFieldLabel"), 0, c); grid1.addWidget(field, 1, c)
    fl.addLayout(grid1); fl.addWidget(_reference_rule())
    fl.addWidget(_reference_heading("settings", "鎵ц涓婁笅鏂?, "閫夋嫨鏈浠诲姟鎵€灞炵殑鐜涓庝笟鍔¤寖鍥?, "SCOPE / 02"))
    grid2 = QGridLayout(); grid2.setHorizontalSpacing(18); grid2.setVerticalSpacing(8)
    self.auto_runner_environment = RunnerBelowPopupComboBox(); self.auto_runner_environment.addItem("娴嬭瘯鐜 路 鏈満 127.0.0.1:5010", "娴嬭瘯鐜")
    self.runner_module = RunnerBelowPopupComboBox(); self.runner_module.addItem("鐜板満浣滀笟")
    for c, name, field in ((0, "杩愯鐜 *", self.auto_runner_environment), (1, "鏀瑰姩妯″潡 *", self.runner_module)):
        grid2.addWidget(_label(name, "RunnerFieldLabel"), 0, c); grid2.addWidget(field, 1, c)
    fl.addLayout(grid2); fl.addWidget(_reference_rule())
    suite_header = QHBoxLayout(); suite_header.addWidget(_reference_heading("catalog", "娴嬭瘯濂椾欢", "浠庡凡鐧昏銆侀€氳繃璐ㄩ噺闂ㄧ鐨勫姩鎬佸浠剁洰褰曚腑閫夋嫨")); suite_header.addStretch(); suite_header.addWidget(_label(f"{len(suites)} 涓彲閫?, "RunnerCatalogCount")); fl.addLayout(suite_header)
    suite_search = QLineEdit(); suite_search.setPlaceholderText("鎼滅储濂椾欢鍚嶇О銆佹爣绛炬垨鑳藉姏鈥?); suite_search.setObjectName("RunnerSuiteSearch"); fl.addWidget(suite_search)
    self.auto_runner_suite = QComboBox(); self.auto_runner_suite.setVisible(False)
    group = QButtonGroup(form); suite_rows = []
    for i, suite in enumerate(suites):
        self.auto_runner_suite.addItem(suite.name, suite.manifest.removeprefix("examples/"))
        row, radio = _reference_suite_row(suite, i + 1, i == 0); group.addButton(radio, i); fl.addWidget(row); suite_rows.append((row, suite))
    group.idClicked.connect(self.auto_runner_suite.setCurrentIndex)
    suite_search.textChanged.connect(lambda text: [row.setVisible(not text or text.lower() in (suite.name + suite.module + suite.description).lower()) for row, suite in suite_rows])
    self.runner_mutation_confirmation = QCheckBox("鎴戝凡纭浠呭湪宸叉巿鏉冩祴璇曠幆澧冩墽琛岋紝骞跺厑璁稿垱寤恒€佹祦杞拰娓呯悊娴嬭瘯鏁版嵁"); fl.addWidget(self.runner_mutation_confirmation)
    self.auto_runner_status = _label("", "ValidationHint"); self.auto_runner_status.setVisible(False); fl.addWidget(self.auto_runner_status)

    preview = _runner_card("RunnerReferencePreview"); pl = QVBoxLayout(preview); pl.setContentsMargins(40, 38, 40, 34); pl.setSpacing(14)
    pl.addWidget(_reference_heading("preview", "鎵ц纭", "璇风‘璁ゆ浠诲姟鐨勬墽琛岃寖鍥翠笌椋庨櫓绛栫暐銆?))
    pl.addWidget(_reference_rule())
    assigned = _runner_card("RunnerAssignedRunner"); al = QHBoxLayout(assigned); al.setContentsMargins(18, 14, 18, 14); al.setSpacing(12)
    al.addWidget(_label("鈼?, "RunnerAssignedDot")); identity = QWidget(); il = QVBoxLayout(identity); il.setContentsMargins(0, 0, 0, 0); il.setSpacing(2)
    il.addWidget(_label("ASSIGNED RUNNER", "RunnerAssignedCaption")); il.addWidget(_label("steelmill-runner", "RunnerAssignedName")); al.addWidget(identity, 1); al.addWidget(_label("v0.1.0", "RunnerAssignedVersion")); pl.addWidget(assigned)
    self.runner_preview_suite = _label(suites[0].name if suites else "鏈€夋嫨", "RunnerPreviewValue")
    self.runner_preview_risk = _label("鍙竻鐞嗗啓鍏?, "RunnerPreviewRisk")
    self.runner_preview_scope = _label("Flow + Redis 瑙傚療", "RunnerPreviewValue")
    self.runner_preview_policy = _label("绔嬪嵆鎵ц", "RunnerPreviewValue")
    self.runner_preview_clean = _label("ResourceLedger 閫嗗簭娓呯悊", "RunnerPreviewValue")
    for label, value in (("娴嬭瘯濂椾欢", self.runner_preview_suite), ("椋庨櫓绛夌骇", self.runner_preview_risk), ("閫夋嫨鑼冨洿", self.runner_preview_scope), ("鎵ц绛栫暐", self.runner_preview_policy), ("娓呯悊绛栫暐", self.runner_preview_clean)):
        item = QWidget(); item.setObjectName("RunnerPreviewItem"); il = QVBoxLayout(item); il.setContentsMargins(0, 10, 0, 10); il.setSpacing(3); il.addWidget(_label(label, "RunnerPreviewKey")); il.addWidget(value); pl.addWidget(item)
    note = _label("浠诲姟寮€濮嬪悗锛孧anifest銆佺幆澧冨拰閫夋嫨鑼冨洿涓嶅彲缂栬緫銆?, "RunnerPreviewNote"); note.setWordWrap(True); pl.addWidget(note)
    run = QPushButton("鍒涘缓骞舵墽琛?); run.setObjectName("RunnerPrimaryAction"); run.clicked.connect(lambda: _run(self)); pl.addWidget(run)
    draft = QPushButton("淇濆瓨涓鸿崏绋?); draft.setObjectName("RunnerSecondaryAction"); pl.addWidget(draft); pl.addStretch()
    def refresh_preview(index):
        if index < 0 or index >= len(suites): return
        suite = suites[index]
        self.runner_preview_suite.setText(suite.name)
        self.runner_preview_risk.setText({"readonly": "鍙", "mutation": "鍙竻鐞嗗啓鍏?, "offline": "绂荤嚎"}.get(suite.risk, suite.risk))
        self.runner_preview_scope.setText(suite.module)
        self.runner_preview_policy.setText("寰呬汉宸ユ壒鍑? if suite.approval_required else "绔嬪嵆鎵ц")
    self.auto_runner_suite.currentIndexChanged.connect(refresh_preview)
    create_outer.addWidget(form, 3); create_outer.addWidget(preview, 2)
    create_scroll = QScrollArea(); create_scroll.setObjectName("RunnerCreateScroll"); create_scroll.setWidgetResizable(True); create_scroll.setFrameShape(QFrame.NoFrame); create_scroll.setWidget(create_content)
    tabs.addTab(create_scroll, "鍒涘缓浠诲姟")

    # Page 2: Results, reference columns
    results_content = QWidget(); results_l = QVBoxLayout(results_content); results_l.setContentsMargins(0, 12, 0, 0); results_l.setSpacing(18)
    metrics = QHBoxLayout(); metrics.setSpacing(18)
    self.runner_metrics = {}
    for key, caption, value, name in (("today", "浠婃棩浠诲姟", "3", "RunnerMetricBlue"), ("pass_rate", "閫氳繃鐜囷紙7 澶╋級", "96.8%", "RunnerMetricBlue"), ("queued", "绛夊緟瀹℃壒", "1", "RunnerMetricAmber"), ("latest", "骞冲潎鑰楁椂", "6m 18s", "RunnerMetricBlue")):
        card = _runner_card(name); lay = QVBoxLayout(card); lay.setContentsMargins(24, 18, 24, 18); lay.addWidget(_label(caption, "RunnerMetricCaption")); metric = _label(value, "RunnerMetricValue"); lay.addWidget(metric); self.runner_metrics[key] = metric; metrics.addWidget(card)
    results_l.addLayout(metrics)
    result = _runner_card("RunnerResultCard"); rl = QVBoxLayout(result); rl.setContentsMargins(26, 24, 26, 24); rl.setSpacing(16)
    h = QHBoxLayout(); h.addWidget(_reference_heading("results", "娴嬭瘯浠诲姟涓庣粨鏋?, "鎵ц涓殑浠诲姟涓嶅彲缂栬緫锛涜澶嶅埗涓烘柊浠诲姟鍚庤皟鏁淬€?)); h.addStretch(); refresh = QPushButton("鈫?鍒锋柊鏁版嵁"); refresh.setObjectName("RunnerGhostButton"); refresh.clicked.connect(lambda: self.refresh_external_runner_runs()); h.addWidget(refresh); rl.addLayout(h)
    filters = QHBoxLayout(); filters.setSpacing(12); finder = QLineEdit(); finder.setPlaceholderText("鎼滅储浠诲姟 ID銆乺un_id銆佸伐鍗曗€?); status = QComboBox(); status.addItems(["鍏ㄩ儴鐘舵€?, "passed", "queued", "寰呬汉宸ユ壒鍑?]); module = QComboBox(); module.addItems(["鍏ㄩ儴妯″潡", "鐜板満浣滀笟"]); apply = QPushButton("绛涢€?); apply.setObjectName("RunnerFilterAction"); reset = QPushButton("閲嶇疆"); reset.setObjectName("RunnerGhostButton"); filters.addWidget(finder, 3); filters.addWidget(status); filters.addWidget(module); filters.addWidget(apply); filters.addWidget(reset); rl.addLayout(filters)
    self.runner_run_table = QTableWidget(0, 7); self.runner_run_table.setObjectName("RunnerRunTable"); self.runner_run_table.setHorizontalHeaderLabels(["浠诲姟", "鍏宠仈宸ュ崟", "娴嬭瘯濂椾欢", "鐜", "鐘舵€?, "鎵ц鏃堕棿", "鎿嶄綔"]); self.runner_run_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.runner_run_table.verticalHeader().hide(); self.runner_run_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.runner_run_table.setMinimumHeight(310); rl.addWidget(self.runner_run_table)
    results_l.addWidget(result)
    results_content.setMinimumWidth(1020)
    results_scroll = QScrollArea(); results_scroll.setObjectName("RunnerTabScroll"); results_scroll.setWidgetResizable(True); results_scroll.setFrameShape(QFrame.NoFrame); results_scroll.setWidget(results_content)
    tabs.addTab(results_scroll, "浠诲姟涓庣粨鏋? 0")

    # Page 3: catalog from dynamic definitions only
    catalog_content = QWidget(); cat_l = QVBoxLayout(catalog_content); cat_l.setContentsMargins(0, 12, 0, 0)
    catalog = _runner_card("RunnerCatalogCard"); cl = QVBoxLayout(catalog); cl.setContentsMargins(26, 24, 26, 24); cl.setSpacing(17)
    ch = QHBoxLayout(); ch.addWidget(_reference_heading("catalog", "娴嬭瘯濂椾欢鐩綍", "浠庢祴璇曞垎鏀殑 config/test_suites.yaml 鍙楁帶鍔犺浇")); ch.addStretch(); reload = QPushButton("鈫?鍒锋柊鐩綍"); reload.setObjectName("RunnerGhostButton"); ch.addWidget(reload); cl.addLayout(ch)
    search_row = QHBoxLayout(); search = QLineEdit(); search.setPlaceholderText("鎼滅储濂椾欢銆佹爣绛炬垨璺緞鈥?); field = QComboBox(); field.addItems(["鍏ㄩ儴瀛楁", "濂椾欢鍚嶇О", "鏍囩", "鎵€灞炴ā鍧?]); help_button = QPushButton("濂椾欢鐧昏璇存槑"); help_button.setObjectName("RunnerGhostButton"); search_row.addWidget(search, 4); search_row.addWidget(field, 1); search_row.addStretch(); search_row.addWidget(help_button); cl.addLayout(search_row)
    chips = QHBoxLayout(); chips.setSpacing(10); all_chip = QPushButton(f"鍏ㄩ儴 {len(suites)}"); all_chip.setObjectName("RunnerActiveChip"); chips.addWidget(all_chip)
    modules = sorted({suite.module for suite in suites})
    for module_name in modules: chip = QPushButton(f"{module_name} {sum(1 for s in suites if s.module == module_name)}"); chip.setObjectName("RunnerChip"); chips.addWidget(chip)
    chips.addStretch(); chips.addWidget(_label(f"鏄剧ず {len(suites)} / {len(suites)} 涓浠?, "RunnerCatalogCount")); cl.addLayout(chips)
    grid = QGridLayout(); grid.setHorizontalSpacing(16); grid.setVerticalSpacing(16)
    catalog_cards = []
    for i, suite in enumerate(suites):
        card = _reference_catalog_card(suite); grid.addWidget(card, i // 3, i % 3); catalog_cards.append((card, suite))
    cl.addLayout(grid); cl.addStretch()
    search.textChanged.connect(lambda text: [card.setVisible(not text or text.lower() in (suite.name + suite.module + suite.description).lower()) for card, suite in catalog_cards])
    reload.clicked.connect(lambda: self._external_runner_page())
    cat_l.addWidget(catalog)
    catalog_content.setMinimumWidth(1020)
    catalog_scroll = QScrollArea(); catalog_scroll.setObjectName("RunnerTabScroll"); catalog_scroll.setWidgetResizable(True); catalog_scroll.setFrameShape(QFrame.NoFrame); catalog_scroll.setWidget(catalog_content)
    tabs.addTab(catalog_scroll, f"娴嬭瘯濂椾欢鐩綍  {len(suites)}")
    return page


def install(window_cls):
    if not hasattr(window_cls, "_legacy_run_registered_steelmill"):
        window_cls._legacy_run_registered_steelmill = window_cls.run_registered_steelmill
    window_cls._external_runner_page = modern_external_runner_page
    window_cls.refresh_external_runner_runs = _prototype_refresh_runner_runs

# The prototype uses fixed, legible content columns.  At smaller sizes each
# tab scrolls rather than allowing the forms and table cells to collapse.
_runner_reference_workspace = modern_external_runner_page


def _runner_rebuild_current_page(self, active_tab=2):
    old_page = None
    for index in range(self.pages.count()):
        candidate = self.pages.widget(index)
        if candidate and candidate.objectName() == "RunnerWorkspace":
            old_page = candidate
            old_index = index
            break
    if old_page is None:
        return
    replacement = modern_external_runner_page(self)
    self.pages.removeWidget(old_page)
    old_page.deleteLater()
    self.pages.insertWidget(old_index, replacement)
    self.pages.setCurrentWidget(replacement)
    tabs = replacement.findChild(QTabWidget, "RunnerCenterTabs")
    if tabs:
        tabs.setCurrentIndex(active_tab)


def modern_external_runner_page(self):
    page = _runner_reference_workspace(self)
    # Keep legacy execution APIs connected to the prototype field names.
    self.auto_runner_test_name = self.runner_task_name
    tabs = page.findChild(QTabWidget, "RunnerCenterTabs")
    if not tabs:
        return page

    # The create tab already owns a scroll surface.  Results and catalog use
    # the same responsive treatment so no card, grid, or table is compressed.
    for index in ():
        content = tabs.widget(index)
        caption = tabs.tabText(index)
        if isinstance(content, QScrollArea):
            continue
        content.setMinimumWidth(1020)
        scroll = QScrollArea()
        scroll.setObjectName("RunnerTabScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        tabs.removeTab(index)
        tabs.insertTab(index, scroll, caption)

    for button in page.findChildren(QPushButton):
        if button.text() == "鈫?鍒锋柊鐩綍":
            try:
                button.clicked.disconnect()
            except RuntimeError:
                pass
            button.clicked.connect(lambda: _runner_rebuild_current_page(self, 2))
            break
    return page


def install(window_cls):
    if not hasattr(window_cls, "_legacy_run_registered_steelmill"):
        window_cls._legacy_run_registered_steelmill = window_cls.run_registered_steelmill
    window_cls._external_runner_page = modern_external_runner_page
    window_cls.refresh_external_runner_runs = _prototype_refresh_runner_runs
# Final prototype-navigation layer.  These are native SVG icons, so Windows
# font substitution cannot change the reference visual language.
from PySide6.QtCore import QByteArray, QPoint, QSize
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QTabBar


class RunnerBelowPopupComboBox(QComboBox):
    """Keep Runner option lists below their input, as in the prototype."""
    def showPopup(self):  # noqa: N802
        super().showPopup()
        popup = self.view().window()
        if popup is None:
            return
        popup.setMinimumWidth(max(popup.minimumWidth(), self.width()))
        popup.move(self.mapToGlobal(QPoint(0, self.height())))


def _runner_tab_icon(kind):
    paths = {
        "task": "<rect x='6' y='4' width='12' height='16' rx='2'/><path d='M9 9h6M9 13h6M9 17h4'/>",
        "results": "<path d='M5 19V6M5 19h14'/><path d='m8 14 3-3 3 2 4-6'/>",
        "catalog": "<path d='m12 4 7 3.5-7 3.5-7-3.5L12 4Z'/><path d='m5 12 7 3.5 7-3.5M5 16l7 3.5 7-3.5'/>",
    }
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
           "<rect x='1' y='1' width='30' height='30' rx='8' fill='#eaf3ff'/>"
           "<g fill='none' stroke='#2584e9' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'>"
           + paths[kind] + "</g></svg>")
    renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
    pixmap = QPixmap(32, 32); pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap); renderer.render(painter); painter.end()
    return QIcon(pixmap)


def _runner_tab_badge(text, name):
    badge = QLabel(text)
    badge.setObjectName(name)
    badge.setAlignment(Qt.AlignCenter)
    return badge


_runner_navigation_workspace = modern_external_runner_page
_runner_existing_refresh = _prototype_refresh_runner_runs


def _prototype_refresh_runner_runs(self):
    _runner_existing_refresh(self)
    page = next((self.pages.widget(i) for i in range(self.pages.count())
                 if self.pages.widget(i).objectName() == "RunnerWorkspace"), None)
    tabs = page.findChild(QTabWidget, "RunnerCenterTabs") if page else None
    if not tabs:
        return
    rows = getattr(self, "_runner_run_rows", [])
    completed = [row for row in rows if bool(row.get("result"))]
    tabs.setTabVisible(1, bool(completed))
    tabs.setTabText(1, "浠诲姟涓庣粨鏋?)
    tabs.tabBar().setTabButton(1, QTabBar.RightSide,
                      _runner_tab_badge(str(len(completed)), "RunnerTabCount") if completed else None)


def modern_external_runner_page(self):
    page = _runner_navigation_workspace(self)
    tabs = page.findChild(QTabWidget, "RunnerCenterTabs")
    if not tabs:
        return page
    suites = _runner_dynamic_suites()
    tabs.setIconSize(QSize(32, 32))
    tabs.setTabText(0, "鍒涘缓浠诲姟")
    tabs.setTabIcon(0, _runner_tab_icon("task"))
    tabs.setTabIcon(1, _runner_tab_icon("results"))
    tabs.setTabIcon(2, _runner_tab_icon("catalog"))
    tabs.setTabText(2, "娴嬭瘯濂椾欢鐩綍")
    catalog_badges = QWidget(); badges = QHBoxLayout(catalog_badges)
    badges.setContentsMargins(5, 0, 0, 0); badges.setSpacing(7)
    badges.addWidget(_runner_tab_badge(str(len(suites)), "RunnerTabCount"))
    badges.addWidget(_runner_tab_badge("鍔ㄦ€佸姞杞?, "RunnerTabLive"))
    tabs.tabBar().setTabButton(2, QTabBar.RightSide, catalog_badges)
    for combo in page.findChildren(RunnerBelowPopupComboBox):
        combo.setObjectName("RunnerInputCombo")
    _prototype_refresh_runner_runs(self)
    return page


def install(window_cls):
    if not hasattr(window_cls, "_legacy_run_registered_steelmill"):
        window_cls._legacy_run_registered_steelmill = window_cls.run_registered_steelmill
    window_cls._external_runner_page = modern_external_runner_page
    window_cls.refresh_external_runner_runs = _prototype_refresh_runner_runs
# Keep the suite selection state visibly synchronized with the one-choice group.
_runner_final_reference_workspace = modern_external_runner_page


def modern_external_runner_page(self):
    page = _runner_final_reference_workspace(self)
    for selector in page.findChildren(QPushButton, "RunnerSuiteSelector"):
        row = selector.parentWidget()
        row.setProperty("selected", selector.isChecked())
        selector.toggled.connect(
            lambda checked, target=row: (
                target.setProperty("selected", checked),
                target.style().unpolish(target),
                target.style().polish(target),
                target.update(),
            )
        )
    return page


def install(window_cls):
    if not hasattr(window_cls, "_legacy_run_registered_steelmill"):
        window_cls._legacy_run_registered_steelmill = window_cls.run_registered_steelmill
    window_cls._external_runner_page = modern_external_runner_page
    window_cls.refresh_external_runner_runs = _prototype_refresh_runner_runs
# The reference navigation is intentionally quiet: icons and labels only.
_runner_minimal_navigation_workspace = modern_external_runner_page
_runner_plain_result_refresh = _prototype_refresh_runner_runs


def _prototype_refresh_runner_runs(self):
    _runner_plain_result_refresh(self)
    table = getattr(self, "runner_run_table", None)
    if table:
        # Suite names are read-only display text, never editors or selectors.
        for row in range(table.rowCount()):
            source = table.item(row, 2)
            value = source.text() if source else "鈥?
            label = QLabel(value)
            label.setObjectName("RunnerTableSuiteText")
            label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            table.setCellWidget(row, 2, label)
    page = next((self.pages.widget(i) for i in range(self.pages.count())
                 if self.pages.widget(i).objectName() == "RunnerWorkspace"), None)
    tabs = page.findChild(QTabWidget, "RunnerCenterTabs") if page else None
    if tabs:
        tabs.tabBar().setTabButton(1, QTabBar.RightSide, None)
        tabs.tabBar().setTabButton(2, QTabBar.RightSide, None)


def modern_external_runner_page(self):
    page = _runner_minimal_navigation_workspace(self)
    tabs = page.findChild(QTabWidget, "RunnerCenterTabs")
    if tabs:
        tabs.setTabText(0, "鍒涘缓浠诲姟")
        tabs.setTabText(1, "浠诲姟涓庣粨鏋?)
        tabs.setTabText(2, "娴嬭瘯濂椾欢鐩綍")
        tabs.tabBar().setTabButton(1, QTabBar.RightSide, None)
        tabs.tabBar().setTabButton(2, QTabBar.RightSide, None)
    return page


def install(window_cls):
    if not hasattr(window_cls, "_legacy_run_registered_steelmill"):
        window_cls._legacy_run_registered_steelmill = window_cls.run_registered_steelmill
    window_cls._external_runner_page = modern_external_runner_page
    window_cls.refresh_external_runner_runs = _prototype_refresh_runner_runs
# Final data presentation and scroll shell for the real Runner workspace.
_runner_scroll_workspace = modern_external_runner_page
_runner_status_refresh = _prototype_refresh_runner_runs


def _prototype_refresh_runner_runs(self):
    _runner_status_refresh(self)
    table = getattr(self, "runner_run_table", None)
    rows = getattr(self, "_runner_run_rows", [])
    if not table:
        return
    styles = {
        "passed": ("passed", "#e8f8ef", "#16834a"),
        "queued": ("寰呬汉宸ユ壒鍑?, "#fff3df", "#b6771b"),
        "waiting": ("寰呬汉宸ユ壒鍑?, "#fff3df", "#b6771b"),
        "pending": ("寰呬汉宸ユ壒鍑?, "#fff3df", "#b6771b"),
        "failed": ("error", "#fff0f0", "#ca4c45"),
        "error": ("error", "#fff0f0", "#ca4c45"),
    }
    for row_index, record in enumerate(rows):
        table.setRowHeight(row_index, 54)
        source = table.item(row_index, 2)
        suite_name = source.text() if source else "鈥?
        table.takeItem(row_index, 2)  # do not paint an item underneath the display label
        suite = QLabel(suite_name); suite.setObjectName("RunnerTableSuiteText")
        suite.setToolTip(suite_name); suite.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        table.setCellWidget(row_index, 2, suite)
        status = str(record.get("status") or "queued").lower()
        caption, background, foreground = styles.get(status, styles["queued"])
        badge = QLabel(caption); badge.setObjectName("RunnerStatusBadge")
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"background:{background}; color:{foreground}; border:none; border-radius:13px; padding:5px 10px; font-weight:700;")
        table.setCellWidget(row_index, 4, badge)


def modern_external_runner_page(self):
    content = _runner_scroll_workspace(self)
    content.setObjectName("RunnerWorkspaceContent")
    content.setMinimumWidth(1020)
    shell = QScrollArea(); shell.setObjectName("RunnerWorkspace")
    shell.setWidgetResizable(True); shell.setFrameShape(QFrame.NoFrame)
    shell.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    shell.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    shell.setWidget(content)
    return shell


def install(window_cls):
    if not hasattr(window_cls, "_legacy_run_registered_steelmill"):
        window_cls._legacy_run_registered_steelmill = window_cls.run_registered_steelmill
    window_cls._external_runner_page = modern_external_runner_page
    window_cls.refresh_external_runner_runs = _prototype_refresh_runner_runs
# Single outer scroll surface: mouse-wheel scrolling covers title, settings and tabs.
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QSizePolicy
_runner_whole_surface = modern_external_runner_page
_runner_plain_table_refresh = _prototype_refresh_runner_runs


class _RunnerSuiteRowClickFilter(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            selector = watched.findChild(QPushButton, "RunnerSuiteSelector")
            if selector:
                selector.click()
                return True
        return super().eventFilter(watched, event)


def _prototype_refresh_runner_runs(self):
    _runner_plain_table_refresh(self)
    table = getattr(self, "runner_run_table", None)
    rows = getattr(self, "_runner_run_rows", [])
    if not table:
        return
    for row_index, record in enumerate(rows):
        metadata = (record.get("manifest") or {}).get("metadata") or {}
        suite_name = str(metadata.get("suite") or (record.get("manifest") or {}).get("suite") or "鈥?)
        table.removeCellWidget(row_index, 2)
        item = QTableWidgetItem(suite_name)
        item.setToolTip(suite_name)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        table.setItem(row_index, 2, item)


def modern_external_runner_page(self):
    shell = _runner_whole_surface(self)
    content = shell.widget()
    tabs = content.findChild(QTabWidget, "RunnerCenterTabs") if content else None
    if tabs:
        selected = tabs.currentIndex()
        for index in range(tabs.count() - 1, -1, -1):
            scroll = tabs.widget(index)
            if not isinstance(scroll, QScrollArea):
                continue
            caption, icon = tabs.tabText(index), tabs.tabIcon(index)
            body = scroll.takeWidget()
            tabs.removeTab(index)
            tabs.insertTab(index, body, caption)
            tabs.setTabIcon(index, icon)
        tabs.setCurrentIndex(selected)
        tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        def fit_current_tab(_=None):
            body = tabs.currentWidget()
            if body:
                tabs.setMinimumHeight(body.sizeHint().height() + tabs.tabBar().sizeHint().height() + 14)
        tabs.currentChanged.connect(fit_current_tab)
        fit_current_tab()
    if content:
        self._runner_suite_row_click_filter = _RunnerSuiteRowClickFilter(content)
        for row in content.findChildren(QFrame, "RunnerReferenceSuite"):
            row.setCursor(Qt.PointingHandCursor)
            row.installEventFilter(self._runner_suite_row_click_filter)
    shell.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    shell.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    return shell


def install(window_cls):
    if not hasattr(window_cls, "_legacy_run_registered_steelmill"):
        window_cls._legacy_run_registered_steelmill = window_cls.run_registered_steelmill
    window_cls._external_runner_page = modern_external_runner_page
    window_cls.refresh_external_runner_runs = _prototype_refresh_runner_runs
# Final list actions follow the prototype: view, download, then confirmed delete.
_runner_actions_refresh = _prototype_refresh_runner_runs


def _prototype_refresh_runner_runs(self):
    _runner_actions_refresh(self)
    table = getattr(self, "runner_run_table", None)
    if not table:
        return
    for row_index in range(table.rowCount()):
        actions = QWidget(); actions.setObjectName("RunnerTableActions")
        layout = QHBoxLayout(actions); layout.setContentsMargins(4, 0, 4, 0); layout.setSpacing(8)
        view = QToolButton(); view.setIcon(self._runner_action_icon("view")); view.setIconSize(QSize(18, 18)); view.setAutoRaise(True); view.setToolTip("鏌ョ湅浠诲姟")
        view.clicked.connect(lambda _=False, i=row_index: table.selectRow(i))
        download = QToolButton(); download.setIcon(self._runner_action_icon("download")); download.setIconSize(QSize(18, 18)); download.setAutoRaise(True); download.setToolTip("涓嬭浇浜х墿")
        download.clicked.connect(lambda _=False, i=row_index: self.open_runner_artifacts(i))
        delete = QToolButton(); delete.setIcon(self._runner_action_icon("delete")); delete.setIconSize(QSize(18, 18)); delete.setAutoRaise(True); delete.setToolTip("鍒犻櫎浠诲姟")
        delete.clicked.connect(lambda _=False, i=row_index: self.delete_runner_task(i))
        for button in (view, download, delete): button.setFixedSize(30, 30); layout.addWidget(button)
        table.setCellWidget(row_index, 6, actions)


def install(window_cls):
    if not hasattr(window_cls, "_legacy_run_registered_steelmill"):
        window_cls._legacy_run_registered_steelmill = window_cls.run_registered_steelmill
    window_cls._external_runner_page = modern_external_runner_page
    window_cls.refresh_external_runner_runs = _prototype_refresh_runner_runs

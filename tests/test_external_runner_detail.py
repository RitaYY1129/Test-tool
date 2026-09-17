from __future__ import annotations

import json

from testpilot.ui.external_runner_modern import (
    _execution_content_text,
    _flow_data_text,
    _format_local_timestamp,
    _readable_detail_html,
    _result_summary_text,
)


def _record(tmp_path):
    root = tmp_path / "run"
    flow = root / "artifacts" / "process_flow" / "box-queue-rework"
    flow.mkdir(parents=True)
    (flow / "result.json").write_text(
        json.dumps(
            {
                "batchNo": "RMI001",
                "barcodes": ["E2E001", "E2E002"],
                "materialCount": 2,
                "rework": True,
                "outbound": False,
                "batchTrace": {
                    "batch": {"supplierName": "中正", "specName": "650*1300"},
                    "items": [
                        {
                            "barcode": "E2E001",
                            "nodeCount": 3,
                            "product": {
                                "positionText": "1#料箱-1，位置1",
                                "currentStatusName": "已质检",
                                "inspectionResultName": "合格",
                            },
                            "traceNodes": [
                                {"nodeName": "供应商入厂"},
                                {"nodeName": "质量检验"},
                                {"nodeName": "返修完成"},
                            ],
                        }
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "runner.log").write_text(
        "PytestUnhandledThreadExceptionWarning: Exception in thread A\n"
        "PytestUnhandledThreadExceptionWarning: Exception in thread B",
        encoding="utf-8",
    )
    return {
        "artifacts_dir": str(root),
        "manifest": {
            "selection": {"paths": ["modules/现场作业/e2e/test_process_flow_e2e.py"], "markers": ["field_e2e"]},
            "policy": {"allow_mutation": True, "parallel_workers": 1, "timeout_seconds": 1800},
        },
        "result": {
            "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0},
            "cases": [
                {
                    "id": "test_process_flow[box-queue-rework]",
                    "status": "passed",
                    "duration_ms": 39546,
                }
            ],
        },
    }


def test_execution_content_translates_flow_case(tmp_path):
    content = _execution_content_text(_record(tmp_path))

    assert "允许写入并在结束后清理测试数据" in content
    assert "单料箱装载 · 队列流转 · 返修复测（不出库）" in content
    assert "通过 ｜ 40 秒" in content
    assert "炉室格位已释放" in content
    assert "Runner 日志记录 2 条子进程输出解码警告" in content


def test_flow_data_reads_human_readable_artifact(tmp_path):
    content = _flow_data_text(_record(tmp_path))

    assert "批次号：RMI001" in content
    assert "测试物料：2 件；条码范围：E2E001 ～ E2E002" in content
    assert "供应商 / 规格：中正 / 650*1300" in content
    assert "返修后完成质检，按场景要求不出库" in content
    assert "供应商入厂 → 质量检验 → 返修完成" in content


def test_flow_data_handles_missing_artifact(tmp_path):
    record = {"artifacts_dir": str(tmp_path / "missing"), "result": {}}

    assert _flow_data_text(record) == "任务尚未产生可读取的流转数据。"



def test_runner_timestamp_is_displayed_in_local_timezone():
    assert _format_local_timestamp("2026-09-17 02:21:06") == "2026-09-17 10:21:06"
    assert _format_local_timestamp("2026-09-17T02:23:53Z") == "2026-09-17 10:23:53"


def test_result_summary_and_readable_html(tmp_path):
    record = _record(tmp_path)

    assert _result_summary_text(record) == "1 / 1 通过"
    rendered = _readable_detail_html(_execution_content_text(record))
    assert "class='scenario'" in rendered
    assert "单料箱装载 · 队列流转 · 返修复测（不出库）" in rendered

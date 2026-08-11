from __future__ import annotations

import sqlite3

import pytest

from testpilot.engines.workflow_runner import SqliteTestDatabase, WorkflowError, run_workflow


def test_workflow_fixture_db_assertion_and_compensation(tmp_path):
    database_path = tmp_path / "test.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)")

    workflow = {
        "review_status": "confirmed",
        "steps": [
            {
                "name": "准备用户",
                "kind": "fixture",
                "fixture": {"table": "users", "rows": [{"name": "Ada"}]},
                "compensation": {"kind": "db_delete", "table": "users", "where": {"name": "${USER_NAME}"}},
            },
            {
                "name": "检查用户",
                "kind": "db_assertion",
                "assertion": {"query": "SELECT name FROM users WHERE name = ?", "params": ["${USER_NAME}"], "row_count": 1},
            },
        ],
    }
    database = SqliteTestDatabase(str(database_path), read_only=False)
    results, summary = run_workflow(
        workflow, "https://example.test", variables={"USER_NAME": "Ada"}, database=database,
    )
    assert summary["status"] == "passed"
    assert results[0]["status"] == "passed"
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_workflow_requires_confirmation_and_read_only_blocks_fixture(tmp_path):
    database_path = tmp_path / "test.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    workflow = {
        "review_status": "draft",
        "steps": [],
    }
    with pytest.raises(WorkflowError, match="人工确认"):
        run_workflow(workflow, "https://example.test")
    with pytest.raises(WorkflowError, match="只读"):
        SqliteTestDatabase(str(database_path), read_only=True).insert_fixture(
            {"table": "users", "rows": [{"id": 1, "name": "Ada"}]}
        )


def test_workflow_state_observation_records_before_after(tmp_path):
    database_path = tmp_path / "state.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, state TEXT)")
        connection.execute("INSERT INTO orders VALUES (1, 'draft')")
    workflow = {
        "review_status": "confirmed",
        "state_observations": [{"name": "order_state", "query": "SELECT state FROM orders WHERE id=1"}],
        "state_expectations": {"order_state": [{"state": "draft"}]},
        "steps": [{"name": "验证状态", "kind": "db_assertion", "assertion": {"query": "SELECT state FROM orders WHERE id=1", "equals": "draft"}}],
    }
    _, summary = run_workflow(workflow, "https://example.test", database=SqliteTestDatabase(str(database_path)))
    assert summary["status"] == "passed"
    assert summary["state_observations"]["check"]["status"] == "passed"

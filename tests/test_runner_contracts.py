from __future__ import annotations

import pytest

from testpilot.contracts.runner import ContractError, RunManifest, RunResult
from testpilot.engines.external_runner import complete_external_run, queue_external_run, validate_local_runner_artifacts
from testpilot.storage.database import Database


def _manifest() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "run_001",
        "project_id": "steelmill",
        "runner": {"name": "steelmill-runner", "version": "0.1.0"},
        "environment_id": "staging",
        "selection": {"paths": ["modules/现场作业"], "markers": ["api", "smoke"], "case_ids": []},
        "policy": {"allow_mutation": False, "timeout_seconds": 1800, "parallel_workers": 1, "retry_policy": "read_only_only"},
        "artifacts_dir": "/artifacts/run_001",
    }


def test_manifest_and_result_contract_reject_invalid_values() -> None:
    manifest = RunManifest.from_dict(_manifest())
    assert manifest.to_dict()["runner"]["name"] == "steelmill-runner"

    invalid = _manifest()
    invalid["selection"] = {"paths": [], "markers": [], "case_ids": []}
    with pytest.raises(ContractError, match="至少"):
        RunManifest.from_dict(invalid)

    result = RunResult.from_dict({
        "schema_version": "1.0", "run_id": "run_001", "status": "passed",
        "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "skipped": 0},
        "cases": [{"id": "smoke.health", "status": "passed"}],
        "artifacts": {"html": "report.html", "junit": "junit.xml"},
    })
    assert result.summary["passed"] == 1


def test_platform_persists_project_adapter_runner_and_external_result(tmp_path) -> None:
    db = Database(tmp_path / "testpilot.db")
    project_id = db.create_project("SteelMill")
    db.save_environment(
        project_id, "staging", "https://staging.example.test", {},
        capabilities={"allow_mutation": False, "allow_database_observation": True},
        secret_refs=["steelmill-staging-account"],
    )
    db.save_project_adapter(project_id, "steelmill", {"authentication": {"kind": "bearer_login"}})
    db.save_runner(
        project_id, "steelmill-runner", version="0.1.0", command="steelmill-runner run --manifest {manifest}",
        capabilities={"markers": ["api", "smoke", "flow"], "database_observation": True},
    )

    run_id = queue_external_run(db, _manifest())
    queued = db.list_runner_runs(project_id)
    assert queued[0]["id"] == run_id
    assert queued[0]["status"] == "queued"
    assert queued[0]["manifest"]["project_id"] == "steelmill"
    assert queued[0]["environment_name"] == "staging"

    db.start_runner_run(run_id)
    assert db.get_runner_run(run_id)["status"] == "running"

    complete_external_run(db, run_id, {
        "schema_version": "1.0", "run_id": "run_001", "status": "passed",
        "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "skipped": 0},
        "cases": [{"id": "smoke.health", "status": "passed"}],
        "artifacts": {"root": "/artifacts/run_001", "html": "report.html"},
    })
    completed = db.list_runner_runs(project_id)[0]
    assert completed["status"] == "passed"
    assert completed["artifacts_dir"] == "/artifacts/run_001"
    assert completed["result"]["summary"]["passed"] == 1


def test_external_runner_rejects_policy_and_result_identity_violations(tmp_path) -> None:
    db = Database(tmp_path / "testpilot.db")
    project_id = db.create_project("SteelMill")
    db.save_environment(project_id, "staging", "https://staging.example.test", {}, capabilities={"allow_mutation": False})
    db.save_project_adapter(project_id, "steelmill", {})
    db.save_runner(project_id, "steelmill-runner", version="0.1.0")

    mutation_manifest = _manifest()
    mutation_manifest["policy"]["allow_mutation"] = True
    with pytest.raises(ContractError, match="不允许 mutation"):
        queue_external_run(db, mutation_manifest)

    unapproved_mutation = _manifest()
    unapproved_mutation["selection"]["markers"] = ["api", "mutation"]
    with pytest.raises(ContractError, match="未显式允许 mutation"):
        queue_external_run(db, unapproved_mutation)

    run_id = queue_external_run(db, _manifest())
    wrong_result = {
        "schema_version": "1.0", "run_id": "another_run", "status": "passed",
        "summary": {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0},
        "cases": [], "artifacts": {},
    }
    with pytest.raises(ContractError, match="run_id"):
        complete_external_run(db, run_id, wrong_result)


def test_local_runner_artifacts_stay_in_platform_directory(tmp_path) -> None:
    artifacts = tmp_path / "run_001"
    artifacts.mkdir()
    for filename in ("junit.xml", "report.html", "runner.log"):
        (artifacts / filename).write_text("evidence", encoding="utf-8")
    payload = {
        "artifacts": {
            "root": str(artifacts), "junit": "junit.xml", "html": "report.html", "log": "runner.log",
        }
    }
    validate_local_runner_artifacts(artifacts, payload)

    payload["artifacts"]["html"] = "../outside.html"
    with pytest.raises(ContractError, match="受控目录"):
        validate_local_runner_artifacts(artifacts, payload)

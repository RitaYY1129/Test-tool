from testpilot.storage.database import Database


def test_project_lifecycle(tmp_path):
    db = Database(tmp_path / "test.db")
    project_id = db.create_project("示例项目")
    assert db.list_projects()[0]["name"] == "示例项目"
    assert db.list_environments(project_id)[0]["name"] == "测试环境"
    db.save_environment(project_id, "预发布", "https://staging.example.test", {"X-App": "test"})
    assert len(db.list_environments(project_id)) == 2
    db.delete_project(project_id)
    assert db.list_projects() == []


def test_delete_empty_sources(tmp_path):
    db = Database(tmp_path / "test.db")
    project_id = db.create_project("source cleanup")
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO api_sources(project_id,name,kind) VALUES (?,?,?)",
            (project_id, "legacy empty import", "openapi"),
        )
    assert db.delete_empty_sources(project_id) == 1
    assert db.list_sources(project_id) == []

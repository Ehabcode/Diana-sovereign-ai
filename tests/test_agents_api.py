import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import server  # noqa: E402
from agent_orchestrator import AgentOrchestrator  # noqa: E402


def fake_executor(task, emit, cancelled):
    emit(step="RESEARCHER", progress=40, message="fake source step")
    emit(step="REVIEWER", progress=80, message="fake review step")
    return {"result": "fake agent result", "sources": [{"title": "Test source", "url": "https://example.com"}], "mode_resolved": "local"}


with tempfile.TemporaryDirectory() as temp_dir:
    orchestrator = AgentOrchestrator(Path(temp_dir), fake_executor)
    server.agent_orchestrator = orchestrator
    server.app.config["TESTING"] = True
    client = server.app.test_client()

    response = client.post("/agents/run", json={"command": "test command", "persona": "texty", "mode": "local"})
    assert response.status_code == 202, response.get_data(as_text=True)
    task_id = response.get_json()["task"]["id"]

    for _ in range(30):
        task = client.get(f"/agents/tasks/{task_id}").get_json()["task"]
        if task["status"] == "done":
            break
        time.sleep(0.02)
    assert task["status"] == "done", task
    assert task["result"] == "fake agent result"
    assert any(event["message"] == "fake review step" for event in task["events"])

    schedule_response = client.post("/agents/schedules", json={"name": "Morning", "command": "summarize", "frequency": "daily", "time": "09:00"})
    assert schedule_response.status_code == 201, schedule_response.get_data(as_text=True)
    schedule_id = schedule_response.get_json()["schedule"]["id"]
    assert client.get("/agents/schedules").get_json()["schedules"][0]["id"] == schedule_id
    assert client.patch(f"/agents/schedules/{schedule_id}", json={"enabled": False}).status_code == 200
    assert client.delete(f"/agents/schedules/{schedule_id}").get_json()["deleted"] is True
    assert client.get("/agents/knowledge").get_json()["notes"] == []

    orchestrator.close()

print("AGENTS_API_AND_SCHEDULER_OK")

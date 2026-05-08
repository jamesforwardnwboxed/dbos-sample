from __future__ import annotations

from dataclasses import dataclass

from conftest import create_control_plane_app, create_control_plane_client


@dataclass
class FakeRecord:
    request_id: str
    status: str
    response_payload: dict


class FakeManager:
    async def snapshot(self):
        return {
            "session": {"status": "ready"},
            "requests": [],
            "events": [],
            "last_list_workflows_output": [],
            "last_list_queued_workflows_output": [],
            "last_workflow_output": None,
            "last_steps_output": [],
        }

    async def send_list_workflows(self, body):
        assert body == {"limit": 1}
        return FakeRecord(request_id="req-1", status="succeeded", response_payload={"output": []})

    async def send_list_queued_workflows(self, body):
        assert body == {"limit": 2}
        return FakeRecord(request_id="req-queued", status="succeeded", response_payload={"output": []})

    async def send_get_workflow(self, workflow_id, *, load_input, load_output):
        assert workflow_id == "wf-1"
        assert load_input is True
        assert load_output is False
        return FakeRecord(request_id="req-get", status="succeeded", response_payload={"output": {"WorkflowUUID": workflow_id}})

    async def send_list_steps(self, workflow_id, *, load_output, limit, offset):
        assert workflow_id == "wf-1"
        assert load_output is False
        assert limit == 3
        assert offset == 1
        return FakeRecord(request_id="req-steps", status="succeeded", response_payload={"output": []})

    async def send_recovery(self, executor_ids):
        assert executor_ids == ["executor-1"]
        return FakeRecord(request_id="req-2", status="succeeded", response_payload={"success": True})

    async def send_cancel(self, workflow_id):
        assert workflow_id == "wf-1"
        return FakeRecord(request_id="req-cancel", status="succeeded", response_payload={"success": True})

    async def send_resume(self, workflow_id, *, queue_name=None):
        assert workflow_id == "wf-1"
        assert queue_name == "critical"
        return FakeRecord(request_id="req-resume", status="succeeded", response_payload={"success": True})

    async def send_restart(self, workflow_id):
        assert workflow_id == "wf-1"
        return FakeRecord(request_id="req-restart", status="succeeded", response_payload={"success": True})


def test_ui_and_static_assets_are_served() -> None:
    with create_control_plane_client() as client:
        ui_response = client.get("/")
        js_response = client.get("/static/app.js")

        assert ui_response.status_code == 200
        assert "Control Plane" in ui_response.text
        assert js_response.status_code == 200
        assert "setInterval(refresh, 1500);" in js_response.text


def test_http_routes_delegate_to_manager() -> None:
    app = create_control_plane_app()
    app.state.conductor_manager = FakeManager()

    with create_control_plane_client() as _unused:
        pass

    with create_control_plane_client().__class__(app) as client:
        state_response = client.get("/api/control-plane/state")
        list_response = client.post("/api/control-plane/list-workflows", json={"body": {"limit": 1}})
        queued_response = client.post("/api/control-plane/list-queued-workflows", json={"body": {"limit": 2}})
        workflow_response = client.post(
            "/api/control-plane/get-workflow",
            json={"workflow_id": "wf-1", "load_input": True, "load_output": False},
        )
        steps_response = client.post(
            "/api/control-plane/list-steps",
            json={"workflow_id": "wf-1", "load_output": False, "limit": 3, "offset": 1},
        )
        recovery_response = client.post("/api/control-plane/recovery", json={"executor_ids": ["executor-1"]})
        cancel_response = client.post("/api/control-plane/cancel", json={"workflow_id": "wf-1"})
        resume_response = client.post(
            "/api/control-plane/resume",
            json={"workflow_id": "wf-1", "queue_name": "critical"},
        )
        restart_response = client.post("/api/control-plane/restart", json={"workflow_id": "wf-1"})

        assert state_response.status_code == 200
        assert state_response.json()["session"]["status"] == "ready"
        assert list_response.status_code == 200
        assert list_response.json()["request_id"] == "req-1"
        assert queued_response.status_code == 200
        assert queued_response.json()["request_id"] == "req-queued"
        assert workflow_response.status_code == 200
        assert workflow_response.json()["request_id"] == "req-get"
        assert steps_response.status_code == 200
        assert steps_response.json()["request_id"] == "req-steps"
        assert recovery_response.status_code == 200
        assert recovery_response.json()["request_id"] == "req-2"
        assert cancel_response.status_code == 200
        assert cancel_response.json()["request_id"] == "req-cancel"
        assert resume_response.status_code == 200
        assert resume_response.json()["request_id"] == "req-resume"
        assert restart_response.status_code == 200
        assert restart_response.json()["request_id"] == "req-restart"


def test_routes_validate_required_workflow_id() -> None:
    app = create_control_plane_app()
    app.state.conductor_manager = FakeManager()

    with create_control_plane_client().__class__(app) as client:
        assert client.post("/api/control-plane/get-workflow", json={}).status_code == 400
        assert client.post("/api/control-plane/list-steps", json={}).status_code == 400
        assert client.post("/api/control-plane/cancel", json={}).status_code == 400
        assert client.post("/api/control-plane/resume", json={}).status_code == 400
        assert client.post("/api/control-plane/restart", json={}).status_code == 400

from __future__ import annotations

from dataclasses import dataclass

from conftest import create_control_plane_app, create_control_plane_client


@dataclass
class FakeRecord:
    request_id: str
    status: str
    response_payload: dict


class FakeManager:
    def __init__(self) -> None:
        self.last_fork_call = None
        self.last_stage_edited_fork_call = None
        self.last_run_edited_fork_call = None
        self.last_execute_staged_fork_call = None

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
        return FakeRecord(
            request_id="req-get",
            status="succeeded",
            response_payload={
                "output": {
                    "WorkflowUUID": workflow_id,
                    "Input": "{'args': (), 'kwargs': {'name': 'world'}}",
                }
            },
        )

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

    async def send_fork_workflow(
        self,
        workflow_id,
        start_step,
        *,
        new_workflow_id=None,
        application_version=None,
        queue_name=None,
    ):
        self.last_fork_call = {
            "workflow_id": workflow_id,
            "start_step": start_step,
            "new_workflow_id": new_workflow_id,
            "application_version": application_version,
            "queue_name": queue_name,
        }
        return FakeRecord(
            request_id="req-fork",
            status="succeeded",
            response_payload={"new_workflow_id": new_workflow_id or "generated-fork-id"},
        )

    async def stage_edited_fork(
        self,
        workflow_id,
        start_step,
        *,
        workflow_input_override=None,
        step_output_overrides=None,
        new_workflow_id=None,
        cancel_original_if_active=False,
    ):
        self.last_stage_edited_fork_call = {
            "workflow_id": workflow_id,
            "start_step": start_step,
            "workflow_input_override": workflow_input_override,
            "step_output_overrides": step_output_overrides,
            "new_workflow_id": new_workflow_id,
            "cancel_original_if_active": cancel_original_if_active,
        }
        return FakeRecord(
            request_id="req-override",
            status="succeeded",
            response_payload={
                "new_workflow_id": new_workflow_id or "generated-override-id",
                "stage_mode": "edited_fork",
                "requires_manual_execution": True,
            },
        )

    async def run_edited_fork(
        self,
        workflow_id,
        start_step,
        *,
        workflow_input_override=None,
        step_output_overrides=None,
        new_workflow_id=None,
        cancel_original_if_active=False,
    ):
        self.last_run_edited_fork_call = {
            "workflow_id": workflow_id,
            "start_step": start_step,
            "workflow_input_override": workflow_input_override,
            "step_output_overrides": step_output_overrides,
            "new_workflow_id": new_workflow_id,
            "cancel_original_if_active": cancel_original_if_active,
        }
        return FakeRecord(
            request_id="req-run",
            status="succeeded",
            response_payload={
                "new_workflow_id": new_workflow_id or "generated-run-id",
                "stage_mode": "run_edited_fork",
                "execution_requested": True,
                "requires_manual_execution": False,
            },
        )

    async def execute_staged_fork(self, workflow_id):
        self.last_execute_staged_fork_call = {"workflow_id": workflow_id}
        return FakeRecord(
            request_id="req-execute",
            status="succeeded",
            response_payload={
                "workflow_id": workflow_id,
                "execution_requested": True,
            },
        )


def test_ui_and_static_assets_are_served() -> None:
    with create_control_plane_client() as client:
        ui_response = client.get("/")
        js_response = client.get("/static/app.js")

        assert ui_response.status_code == 200
        assert "Control Plane" in ui_response.text
        assert "fork-input-override" in ui_response.text
        assert "fork-cancel-original" in ui_response.text
        assert "Execute this forked workflow now?" in ui_response.text
        assert js_response.status_code == 200
        assert "setInterval(refresh, 1500);" in js_response.text
        assert "cancel_original_if_active" in js_response.text
        assert "/api/control-plane/execute-staged-fork" in js_response.text


def test_http_routes_delegate_to_manager() -> None:
    app = create_control_plane_app()
    manager = FakeManager()
    app.state.conductor_manager = manager

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
        execute_response = client.post("/api/control-plane/execute-staged-fork", json={"workflow_id": "wf-1"})
        fork_response = client.post(
            "/api/control-plane/fork",
            json={
                "workflow_id": "wf-1",
                "start_step": 2,
                "new_workflow_id": "wf-2",
                "application_version": "v2",
                "queue_name": "critical",
            },
        )

        assert state_response.status_code == 200
        assert state_response.json()["session"]["status"] == "ready"
        assert list_response.status_code == 200
        assert list_response.json()["request_id"] == "req-1"
        assert queued_response.status_code == 200
        assert queued_response.json()["request_id"] == "req-queued"
        assert workflow_response.status_code == 200
        assert workflow_response.json()["request_id"] == "req-get"
        assert workflow_response.json()["workflow_input_seed"] == {"args": [], "kwargs": {"name": "world"}}
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
        assert execute_response.status_code == 200
        assert execute_response.json()["request_id"] == "req-execute"
        assert manager.last_execute_staged_fork_call == {"workflow_id": "wf-1"}
        assert fork_response.status_code == 200
        assert fork_response.json()["request_id"] == "req-fork"
        assert manager.last_fork_call == {
            "workflow_id": "wf-1",
            "start_step": 2,
            "new_workflow_id": "wf-2",
            "application_version": "v2",
            "queue_name": "critical",
        }


def test_fork_route_accepts_minimal_ui_payload() -> None:
    app = create_control_plane_app()
    manager = FakeManager()
    app.state.conductor_manager = manager

    with create_control_plane_client().__class__(app) as client:
        response = client.post(
            "/api/control-plane/fork",
            json={"workflow_id": "wf-1", "start_step": 1},
        )

        assert response.status_code == 200
        assert response.json()["request_id"] == "req-fork"
        assert manager.last_fork_call == {
            "workflow_id": "wf-1",
            "start_step": 1,
            "new_workflow_id": None,
            "application_version": None,
            "queue_name": None,
        }


def test_get_workflow_returns_no_input_override_seed_when_input_is_not_parseable() -> None:
    app = create_control_plane_app()
    manager = FakeManager()

    async def fake_send_get_workflow(workflow_id, *, load_input, load_output):
        return FakeRecord(
            request_id="req-get",
            status="succeeded",
            response_payload={
                "output": {
                    "WorkflowUUID": workflow_id,
                    "Input": "not-json-or-python-literal",
                }
            },
        )

    manager.send_get_workflow = fake_send_get_workflow
    app.state.conductor_manager = manager

    with create_control_plane_client().__class__(app) as client:
        response = client.post(
            "/api/control-plane/get-workflow",
            json={"workflow_id": "wf-1", "load_input": True, "load_output": False},
        )

        assert response.status_code == 200
        assert response.json()["workflow_input_seed"] is None


def test_fork_route_uses_local_staged_edit_flow_for_workflow_input_override() -> None:
    app = create_control_plane_app()
    manager = FakeManager()
    app.state.conductor_manager = manager

    with create_control_plane_client().__class__(app) as client:
        response = client.post(
            "/api/control-plane/fork",
            json={
                "workflow_id": "wf-1",
                "start_step": 0,
                "new_workflow_id": "wf-override",
                "workflow_input_override": {"name": "Ada"},
                "cancel_original_if_active": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["request_id"] == "req-override"
        assert response.json()["response"] == {
            "new_workflow_id": "wf-override",
            "stage_mode": "edited_fork",
            "requires_manual_execution": True,
        }
        assert manager.last_stage_edited_fork_call == {
            "workflow_id": "wf-1",
            "start_step": 0,
            "workflow_input_override": {"name": "Ada"},
            "step_output_overrides": None,
            "new_workflow_id": "wf-override",
            "cancel_original_if_active": True,
        }
        assert manager.last_fork_call is None


def test_fork_route_uses_local_staged_edit_flow_for_checkpoint_override() -> None:
    app = create_control_plane_app()
    manager = FakeManager()
    app.state.conductor_manager = manager

    with create_control_plane_client().__class__(app) as client:
        response = client.post(
            "/api/control-plane/fork",
            json={
                "workflow_id": "wf-1",
                "start_step": 2,
                "step_output_overrides": {"1": 3},
                "cancel_original_if_active": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["request_id"] == "req-override"
        assert manager.last_stage_edited_fork_call == {
            "workflow_id": "wf-1",
            "start_step": 2,
            "workflow_input_override": None,
            "step_output_overrides": {"1": 3},
            "new_workflow_id": None,
            "cancel_original_if_active": True,
        }
        assert manager.last_fork_call is None


def test_fork_route_run_mode_dispatches_to_run_edited_fork() -> None:
    app = create_control_plane_app()
    manager = FakeManager()
    app.state.conductor_manager = manager

    with create_control_plane_client().__class__(app) as client:
        response = client.post(
            "/api/control-plane/fork",
            json={
                "workflow_id": "wf-1",
                "start_step": 0,
                "mode": "run",
                "workflow_input_override": {"name": "Ada"},
                "cancel_original_if_active": True,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["request_id"] == "req-run"
        assert body["response"]["execution_requested"] is True
        assert body["response"]["stage_mode"] == "run_edited_fork"
        assert manager.last_run_edited_fork_call == {
            "workflow_id": "wf-1",
            "start_step": 0,
            "workflow_input_override": {"name": "Ada"},
            "step_output_overrides": None,
            "new_workflow_id": None,
            "cancel_original_if_active": True,
        }
        assert manager.last_stage_edited_fork_call is None


def test_fork_route_rejects_unknown_mode() -> None:
    app = create_control_plane_app()
    manager = FakeManager()
    app.state.conductor_manager = manager

    with create_control_plane_client().__class__(app) as client:
        response = client.post(
            "/api/control-plane/fork",
            json={
                "workflow_id": "wf-1",
                "start_step": 0,
                "mode": "magic",
                "workflow_input_override": {"name": "Ada"},
            },
        )

        assert response.status_code == 400
        assert "mode" in response.json()["detail"]


def test_fork_route_returns_not_found_for_missing_override_source() -> None:
    app = create_control_plane_app()
    manager = FakeManager()

    async def fake_missing_source(*args, **kwargs):
        raise LookupError("Unknown workflow_id: wf-missing")

    manager.stage_edited_fork = fake_missing_source
    app.state.conductor_manager = manager

    with create_control_plane_client().__class__(app) as client:
        response = client.post(
            "/api/control-plane/fork",
            json={
                "workflow_id": "wf-missing",
                "start_step": 0,
                "workflow_input_override": {"name": "Ada"},
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Unknown workflow_id: wf-missing"


def test_execute_staged_fork_route_returns_not_found_for_missing_workflow() -> None:
    app = create_control_plane_app()
    manager = FakeManager()

    async def fake_missing_workflow(workflow_id):
        raise LookupError(f"Unknown workflow_id: {workflow_id}")

    manager.execute_staged_fork = fake_missing_workflow
    app.state.conductor_manager = manager

    with create_control_plane_client().__class__(app) as client:
        response = client.post(
            "/api/control-plane/execute-staged-fork",
            json={"workflow_id": "wf-missing"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Unknown workflow_id: wf-missing"


def test_fork_route_validates_input_override_shape() -> None:
    app = create_control_plane_app()
    app.state.conductor_manager = FakeManager()

    with create_control_plane_client().__class__(app) as client:
        response = client.post(
            "/api/control-plane/fork",
            json={
                "workflow_id": "wf-1",
                "start_step": 0,
                "workflow_input_override": "name=Ada",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "input_override must be a JSON object"


def test_fork_route_validates_step_output_override_shape() -> None:
    app = create_control_plane_app()
    app.state.conductor_manager = FakeManager()

    with create_control_plane_client().__class__(app) as client:
        response = client.post(
            "/api/control-plane/fork",
            json={
                "workflow_id": "wf-1",
                "start_step": 2,
                "step_output_overrides": ["bad"],
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "step_output_overrides must be a JSON object keyed by step id"


def test_routes_validate_required_workflow_id() -> None:
    app = create_control_plane_app()
    app.state.conductor_manager = FakeManager()

    with create_control_plane_client().__class__(app) as client:
        assert client.post("/api/control-plane/get-workflow", json={}).status_code == 400
        assert client.post("/api/control-plane/list-steps", json={}).status_code == 400
        assert client.post("/api/control-plane/cancel", json={}).status_code == 400
        assert client.post("/api/control-plane/resume", json={}).status_code == 400
        assert client.post("/api/control-plane/restart", json={}).status_code == 400
        assert client.post("/api/control-plane/execute-staged-fork", json={}).status_code == 400
        assert client.post("/api/control-plane/fork", json={}).status_code == 400


def test_fork_route_validates_start_step() -> None:
    app = create_control_plane_app()
    app.state.conductor_manager = FakeManager()

    with create_control_plane_client().__class__(app) as client:
        missing_response = client.post("/api/control-plane/fork", json={"workflow_id": "wf-1"})
        invalid_response = client.post(
            "/api/control-plane/fork",
            json={"workflow_id": "wf-1", "start_step": "not-a-number"},
        )

        assert missing_response.status_code == 400
        assert missing_response.json()["detail"] == "start_step is required"
        assert invalid_response.status_code == 400
        assert invalid_response.json()["detail"] == "start_step must be an integer"


def test_derive_input_override_seed_python_repr() -> None:
    from control_plane.routes import _derive_input_override_seed

    seed = _derive_input_override_seed(
        {"Input": "{'args': ('x', 'y'), 'kwargs': {'name': 'world'}}"}
    )
    assert seed == {"args": ["x", "y"], "kwargs": {"name": "world"}}


def test_derive_input_override_seed_portable_json() -> None:
    from control_plane.routes import _derive_input_override_seed

    seed = _derive_input_override_seed(
        {"Input": '{"positionalArgs": ["x", 1], "namedArgs": {"k": "v"}}'}
    )
    assert seed == {"args": ["x", 1], "kwargs": {"k": "v"}}


def test_derive_input_override_seed_json_args_kwargs() -> None:
    from control_plane.routes import _derive_input_override_seed

    seed = _derive_input_override_seed(
        {"Input": '{"args": [1, 2], "kwargs": {"foo": "bar"}}'}
    )
    assert seed == {"args": [1, 2], "kwargs": {"foo": "bar"}}


def test_derive_input_override_seed_legacy_flat_kwargs() -> None:
    from control_plane.routes import _derive_input_override_seed

    seed = _derive_input_override_seed({"Input": '{"name": "world"}'})
    assert seed == {"args": [], "kwargs": {"name": "world"}}


def test_derive_input_override_seed_invalid_returns_none() -> None:
    from control_plane.routes import _derive_input_override_seed

    assert _derive_input_override_seed({"Input": "not parseable"}) is None
    assert _derive_input_override_seed({"Input": ""}) is None
    assert _derive_input_override_seed({}) is None
    assert _derive_input_override_seed(None) is None

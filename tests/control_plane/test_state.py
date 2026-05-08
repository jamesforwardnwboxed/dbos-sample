from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from control_plane import protocol
from control_plane.protocol import ExecutorInfoResponse, MessageType
from control_plane.state import ConductorManager


class DummyWebSocket:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_text(self, _message: str) -> None:
        self.messages.append(_message)


async def make_ready_manager() -> tuple[ConductorManager, DummyWebSocket]:
    websocket = DummyWebSocket()
    manager = ConductorManager(app_name="dbos-starter", conductor_key="local-conductor-key")
    await manager.register_connection(
        websocket=websocket,
        app_name="dbos-starter",
        conductor_key="local-conductor-key",
    )
    _session, request_id = await manager.begin_handshake()
    await manager.mark_handshake_complete(
        ExecutorInfoResponse(
            type=MessageType.EXECUTOR_INFO,
            request_id=request_id,
            executor_id="executor-1",
            application_version="v1",
            hostname="host-1",
            language="python",
            dbos_version="1.0.0",
        )
    )
    return manager, websocket


@pytest.mark.asyncio
async def test_snapshot_reflects_handshake_completion() -> None:
    manager = ConductorManager(app_name="dbos-starter", conductor_key="local-conductor-key")

    await manager.register_connection(websocket=DummyWebSocket(), app_name="dbos-starter", conductor_key="local-conductor-key")
    _session, request_id = await manager.begin_handshake()
    await manager.mark_handshake_complete(
        ExecutorInfoResponse(
            type=MessageType.EXECUTOR_INFO,
            request_id=request_id,
            executor_id="executor-1",
            application_version="v1",
            hostname="host-1",
            language="python",
            dbos_version="1.0.0",
        )
    )

    snapshot = await manager.snapshot()

    assert snapshot["session"]["status"] == "ready"
    assert snapshot["session"]["executor_info"]["executor_id"] == "executor-1"


@pytest.mark.asyncio
async def test_list_workflows_round_trip_completes_request() -> None:
    manager, websocket = await make_ready_manager()

    send_task = asyncio.create_task(manager.send_list_workflows({"limit": 1}))
    await asyncio.sleep(0)

    request = protocol.ListWorkflowsRequest.from_json(websocket.messages[-1])
    await manager.complete_request_from_message(
        protocol.ListWorkflowsResponse(
            type=MessageType.LIST_WORKFLOWS,
            request_id=request.request_id,
            output=[
                protocol.WorkflowsOutput(
                    WorkflowUUID="wf-1",
                    Status="SUCCESS",
                    WorkflowName="demo",
                    WorkflowClassName=None,
                    WorkflowConfigName=None,
                    AuthenticatedUser=None,
                    AssumedRole=None,
                    AuthenticatedRoles=None,
                    Input=None,
                    Output=None,
                    Error=None,
                    CreatedAt=None,
                    UpdatedAt=None,
                    QueueName=None,
                    ApplicationVersion="v1",
                    ExecutorID="executor-1",
                    WorkflowTimeoutMS=None,
                    WorkflowDeadlineEpochMS=None,
                    DeduplicationID=None,
                    Priority=None,
                    QueuePartitionKey=None,
                    ForkedFrom=None,
                    WasForkedFrom=False,
                    ParentWorkflowID=None,
                    DequeuedAt=None,
                    DelayUntilEpochMS=None,
                )
            ],
        ).to_json()
    )
    record = await send_task
    snapshot = await manager.snapshot()

    assert record.status == "succeeded"
    assert snapshot["last_list_workflows_output"][0]["WorkflowUUID"] == "wf-1"


@pytest.mark.asyncio
async def test_recovery_round_trip_completes_request() -> None:
    manager, websocket = await make_ready_manager()

    send_task = asyncio.create_task(manager.send_recovery(["executor-1"]))
    await asyncio.sleep(0)

    request = protocol.RecoveryRequest.from_json(websocket.messages[-1])
    assert request.executor_ids == ["executor-1"]
    await manager.complete_request_from_message(
        protocol.RecoveryResponse(
            type=MessageType.RECOVERY,
            request_id=request.request_id,
            success=True,
        ).to_json()
    )
    record = await send_task
    snapshot = await manager.snapshot()

    assert record.status == "succeeded"
    assert snapshot["requests"][0]["message_type"] == "recovery"


@pytest.mark.asyncio
async def test_get_workflow_round_trip_updates_snapshot() -> None:
    manager, websocket = await make_ready_manager()

    send_task = asyncio.create_task(manager.send_get_workflow("wf-1"))
    await asyncio.sleep(0)

    request = protocol.GetWorkflowRequest.from_json(websocket.messages[-1])
    assert request.workflow_id == "wf-1"
    await manager.complete_request_from_message(
        protocol.GetWorkflowResponse(
            type=MessageType.GET_WORKFLOW,
            request_id=request.request_id,
            output=protocol.WorkflowsOutput(
                WorkflowUUID="wf-1",
                Status="SUCCESS",
                WorkflowName="demo",
                WorkflowClassName=None,
                WorkflowConfigName=None,
                AuthenticatedUser=None,
                AssumedRole=None,
                AuthenticatedRoles=None,
                Input=None,
                Output="done",
                Error=None,
                CreatedAt=None,
                UpdatedAt=None,
                QueueName=None,
                ApplicationVersion="v1",
                ExecutorID="executor-1",
                WorkflowTimeoutMS=None,
                WorkflowDeadlineEpochMS=None,
                DeduplicationID=None,
                Priority=None,
                QueuePartitionKey=None,
                ForkedFrom=None,
                WasForkedFrom=False,
                ParentWorkflowID=None,
                DequeuedAt=None,
                DelayUntilEpochMS=None,
            ),
        ).to_json()
    )

    record = await send_task
    snapshot = await manager.snapshot()

    assert record.status == "succeeded"
    assert snapshot["last_workflow_output"]["WorkflowUUID"] == "wf-1"


@pytest.mark.asyncio
async def test_list_steps_round_trip_updates_snapshot() -> None:
    manager, websocket = await make_ready_manager()

    send_task = asyncio.create_task(manager.send_list_steps("wf-1"))
    await asyncio.sleep(0)

    request = protocol.ListStepsRequest.from_json(websocket.messages[-1])
    assert request.workflow_id == "wf-1"
    await manager.complete_request_from_message(
        protocol.ListStepsResponse(
            type=MessageType.LIST_STEPS,
            request_id=request.request_id,
            output=[
                protocol.WorkflowSteps(
                    function_id=1,
                    function_name="step_one",
                    output="5",
                    error=None,
                    child_workflow_id=None,
                    started_at_epoch_ms="1",
                    completed_at_epoch_ms="2",
                )
            ],
        ).to_json()
    )

    record = await send_task
    snapshot = await manager.snapshot()

    assert record.status == "succeeded"
    assert snapshot["last_steps_output"][0]["function_name"] == "step_one"


@pytest.mark.asyncio
async def test_control_actions_complete_requests() -> None:
    manager, websocket = await make_ready_manager()

    cancel_task = asyncio.create_task(manager.send_cancel("wf-1"))
    await asyncio.sleep(0)
    cancel_request = protocol.CancelRequest.from_json(websocket.messages[-1])
    await manager.complete_request_from_message(
        protocol.CancelResponse(
            type=MessageType.CANCEL,
            request_id=cancel_request.request_id,
            success=True,
        ).to_json()
    )
    cancel_record = await cancel_task

    resume_task = asyncio.create_task(manager.send_resume("wf-1"))
    await asyncio.sleep(0)
    resume_request = protocol.ResumeRequest.from_json(websocket.messages[-1])
    await manager.complete_request_from_message(
        protocol.ResumeResponse(
            type=MessageType.RESUME,
            request_id=resume_request.request_id,
            success=True,
        ).to_json()
    )
    resume_record = await resume_task

    restart_task = asyncio.create_task(manager.send_restart("wf-1"))
    await asyncio.sleep(0)
    restart_request = protocol.RestartRequest.from_json(websocket.messages[-1])
    await manager.complete_request_from_message(
        protocol.RestartResponse(
            type=MessageType.RESTART,
            request_id=restart_request.request_id,
            success=True,
        ).to_json()
    )
    restart_record = await restart_task

    assert cancel_record.status == "succeeded"
    assert resume_record.status == "succeeded"
    assert restart_record.status == "succeeded"


@pytest.mark.asyncio
async def test_fork_workflow_round_trip_completes_request() -> None:
    manager, websocket = await make_ready_manager()

    fork_task = asyncio.create_task(
        manager.send_fork_workflow(
            "wf-1",
            2,
            new_workflow_id="wf-2",
            application_version="v2",
            queue_name="critical",
        )
    )
    await asyncio.sleep(0)

    request = protocol.ForkWorkflowRequest.from_json(websocket.messages[-1])
    assert request.body["workflow_id"] == "wf-1"
    assert request.body["start_step"] == 2
    assert request.body["new_workflow_id"] == "wf-2"
    assert request.body["application_version"] == "v2"
    assert request.body["queue_name"] == "critical"

    await manager.complete_request_from_message(
        protocol.ForkWorkflowResponse(
            type=MessageType.FORK_WORKFLOW,
            request_id=request.request_id,
            new_workflow_id="wf-2",
        ).to_json()
    )
    fork_record = await fork_task

    assert fork_record.status == "succeeded"
    assert fork_record.response_payload == {
        "type": "fork_workflow",
        "request_id": request.request_id,
        "new_workflow_id": "wf-2",
        "error_message": None,
    }


@pytest.mark.asyncio
async def test_fork_workflow_request_includes_optional_keys_when_omitted() -> None:
    manager, websocket = await make_ready_manager()

    fork_task = asyncio.create_task(manager.send_fork_workflow("wf-1", 1))
    await asyncio.sleep(0)

    request = protocol.ForkWorkflowRequest.from_json(websocket.messages[-1])
    assert request.body == {
        "workflow_id": "wf-1",
        "start_step": 1,
        "new_workflow_id": None,
        "application_version": None,
    }

    await manager.complete_request_from_message(
        protocol.ForkWorkflowResponse(
            type=MessageType.FORK_WORKFLOW,
            request_id=request.request_id,
            new_workflow_id="generated-fork-id",
        ).to_json()
    )
    fork_record = await fork_task

    assert fork_record.status == "succeeded"
    assert fork_record.response_payload == {
        "type": "fork_workflow",
        "request_id": request.request_id,
        "new_workflow_id": "generated-fork-id",
        "error_message": None,
    }


@pytest.mark.asyncio
async def test_record_local_action_updates_snapshot() -> None:
    manager = ConductorManager(app_name="dbos-starter", conductor_key="local-conductor-key")

    record = await manager.record_local_action(
        "stage_edited_fork",
        {
            "workflow_id": "wf-1",
            "start_step": 0,
            "workflow_input_override": {"name": "Ada"},
            "step_output_overrides": None,
            "cancel_original_if_active": True,
        },
        {
            "new_workflow_id": "wf-override",
            "stage_mode": "edited_fork",
        },
    )
    snapshot = await manager.snapshot()

    assert record.status == "succeeded"
    assert snapshot["requests"][0]["message_type"] == "stage_edited_fork"
    assert snapshot["requests"][0]["request_payload"]["workflow_input_override"] == {"name": "Ada"}
    assert snapshot["events"][0]["summary"] == "completed local stage_edited_fork action"


def test_stage_edited_fork_sync_uses_native_fork_and_patches_workflow_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = ConductorManager(
        app_name="dbos-starter",
        conductor_key="local-conductor-key",
        system_database_url="postgres://postgres:dbos@postgres:5432/dbos_starter",
    )

    source_status = {
        "status": "PENDING",
        "name": "dbos_workflow",
        "class_name": None,
        "config_name": None,
        "queue_name": None,
        "app_version": "v1",
        "app_id": "dbos-starter",
        "authenticated_user": None,
        "authenticated_roles": json.dumps(["admin"]),
        "assumed_role": None,
        "priority": 0,
        "queue_partition_key": None,
        "workflow_timeout_ms": None,
        "parent_workflow_id": None,
        "inputs": "serialized-inputs",
        "serialization": "py_pickle",
    }

    captured: dict[str, object] = {}

    class DummyClient:
        def __init__(self, system_database_url: str) -> None:
            captured["system_database_url"] = system_database_url
            self._serializer = object()
            self._sys_db = SimpleNamespace(
                get_workflow_status=lambda workflow_id: source_status if workflow_id == "wf-1" else None,
                fork_workflow=lambda original_ids, forked_ids, start_steps, application_version, queue_name=None: captured.setdefault(
                    "fork_calls",
                    [],
                ).append(
                    {
                        "original_ids": original_ids,
                        "forked_ids": forked_ids,
                        "start_steps": start_steps,
                        "application_version": application_version,
                        "queue_name": queue_name,
                    }
                ),
                engine=SimpleNamespace(begin=lambda: _DummyBeginContext(captured)),
            )

        def destroy(self) -> None:
            captured["destroyed"] = True

    monkeypatch.setattr("control_plane.state.DBOSClient", DummyClient)
    monkeypatch.setattr(
        "control_plane.state.deserialize_args",
        lambda inputs, serialization, serializer: {"args": (), "kwargs": {"name": "world"}},
    )
    monkeypatch.setattr(
        "control_plane.state._serialize_workflow_inputs",
        lambda args, kwargs, serialization, serializer: ("serialized-override", "py_pickle"),
    )

    response = manager._stage_edited_fork_sync(
        "wf-1",
        0,
        {"name": "Ada"},
        None,
        "wf-override",
        "executor-1",
        "v-ready",
    )

    staged_update = captured["statements"][0]
    workflow_input_update = captured["statements"][1]
    source_lineage_update = captured["statements"][2]
    staged_params = staged_update.compile().params
    workflow_input_params = workflow_input_update.compile().params

    assert captured["system_database_url"] == "postgres://postgres:dbos@postgres:5432/dbos_starter"
    assert captured["fork_calls"] == [
        {
            "original_ids": ["wf-1"],
            "forked_ids": ["wf-override"],
            "start_steps": [0],
            "application_version": "v-ready",
            "queue_name": None,
        }
    ]
    assert staged_params["status"] == "PENDING"
    assert staged_params["executor_id"] == "executor-1"
    assert workflow_input_params["inputs"] == "serialized-override"
    assert workflow_input_params["serialization"] == "py_pickle"
    assert "was_forked_from" in str(source_lineage_update)
    # Source cancellation is now handled via websocket send_cancel before the
    # threaded sync stage runs; the sync helper no longer issues a CANCELLED
    # update statement.
    assert len(captured["statements"]) == 3
    assert response == {
        "new_workflow_id": "wf-override",
        "stage_mode": "edited_fork",
        "source_workflow_id": "wf-1",
        "workflow_input_override": {"name": "Ada"},
        "step_output_overrides": {},
        "patched_step_ids": [],
        "start_step": 0,
        "workflow_status": "PENDING",
        "requires_manual_execution": True,
        "source_workflow_status": "PENDING",
        "source_workflow_is_active": True,
    }
    assert captured["destroyed"] is True


def test_stage_edited_fork_sync_allows_workflow_input_override_for_non_restart_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ConductorManager(
        app_name="dbos-starter",
        conductor_key="local-conductor-key",
        system_database_url="postgres://postgres:dbos@postgres:5432/dbos_starter",
    )

    source_status = {
        "status": "ERROR",
        "name": "dbos_workflow",
        "class_name": None,
        "config_name": None,
        "queue_name": None,
        "app_version": "v1",
        "app_id": "dbos-starter",
        "authenticated_user": None,
        "authenticated_roles": None,
        "assumed_role": None,
        "priority": 7,
        "queue_partition_key": None,
        "workflow_timeout_ms": None,
        "parent_workflow_id": None,
        "inputs": "serialized-inputs",
        "serialization": "py_pickle",
    }

    captured: dict[str, object] = {}

    class DummyClient:
        def __init__(self, system_database_url: str) -> None:
            self._serializer = object()
            self._sys_db = SimpleNamespace(
                get_workflow_status=lambda workflow_id: source_status,
                fork_workflow=lambda original_ids, forked_ids, start_steps, application_version, queue_name=None: None,
                engine=SimpleNamespace(begin=lambda: _DummyBeginContext(captured)),
            )

        def destroy(self) -> None:
            return None

    monkeypatch.setattr("control_plane.state.DBOSClient", DummyClient)
    monkeypatch.setattr(
        "control_plane.state._build_workflow_input_override",
        lambda source_status, workflow_input_override, serializer: ("serialized-override", "py_pickle"),
    )

    response = manager._stage_edited_fork_sync(
        "wf-1", 2, {"name": "Ada"}, None, None, "executor-1", "v1"
    )

    workflow_input_params = captured["statements"][1].compile().params
    assert workflow_input_params["inputs"] == "serialized-override"
    assert workflow_input_params["serialization"] == "py_pickle"
    assert response["workflow_input_override"] == {"name": "Ada"}
    assert response["start_step"] == 2


def test_stage_edited_fork_sync_patches_preserved_step_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = ConductorManager(
        app_name="dbos-starter",
        conductor_key="local-conductor-key",
        system_database_url="postgres://postgres:dbos@postgres:5432/dbos_starter",
    )

    source_status = {
        "status": "ERROR",
        "name": "dbos_workflow",
        "class_name": None,
        "config_name": None,
        "queue_name": None,
        "app_version": "v1",
        "app_id": "dbos-starter",
        "authenticated_user": None,
        "authenticated_roles": None,
        "assumed_role": None,
        "priority": 7,
        "queue_partition_key": None,
        "workflow_timeout_ms": None,
        "parent_workflow_id": None,
        "inputs": "serialized-inputs",
        "serialization": "py_pickle",
    }

    captured: dict[str, object] = {}

    class DummyClient:
        def __init__(self, system_database_url: str) -> None:
            self._serializer = object()
            self._sys_db = SimpleNamespace(
                get_workflow_status=lambda workflow_id: source_status,
                fork_workflow=lambda original_ids, forked_ids, start_steps, application_version, queue_name=None: None,
                engine=SimpleNamespace(begin=lambda: _DummyBeginContext(captured)),
            )

        def destroy(self) -> None:
            return None

    monkeypatch.setattr("control_plane.state.DBOSClient", DummyClient)
    monkeypatch.setattr(
        "control_plane.state.deserialize_value",
        lambda serialized_value, serialization, serializer: 5,
    )
    monkeypatch.setattr(
        "control_plane.state.serialize_value_as",
        lambda value, serialization, serializer: ("serialized-step-override", "py_pickle"),
    )

    captured["fetchone_results"] = [SimpleNamespace(function_name="step_one", serialization="py_pickle", output="serialized-step")]

    response = manager._stage_edited_fork_sync(
        "wf-1",
        2,
        None,
        {"1": 3},
        None,
        "executor-1",
        "v1",
    )

    step_patch_update = captured["statements"][2]
    assert step_patch_update.compile().params["output"] == "serialized-step-override"
    assert response["patched_step_ids"] == [1]
    assert response["step_output_overrides"] == {"1": 3}


def test_stage_edited_fork_sync_no_longer_issues_source_cancel_statement(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sync helper must not perform any DB-level source cancellation —
    cancellation is delegated to the websocket send_cancel command, invoked
    from the async wrapper before the threaded sync stage runs."""
    manager = ConductorManager(
        app_name="dbos-starter",
        conductor_key="local-conductor-key",
        system_database_url="postgres://postgres:dbos@postgres:5432/dbos_starter",
    )

    source_status = {
        "status": "PENDING",
        "name": "dbos_workflow",
        "class_name": None,
        "config_name": None,
        "queue_name": None,
        "app_version": "v1",
        "app_id": "dbos-starter",
        "authenticated_user": None,
        "authenticated_roles": None,
        "assumed_role": None,
        "priority": 0,
        "queue_partition_key": None,
        "workflow_timeout_ms": None,
        "parent_workflow_id": None,
        "inputs": "serialized-inputs",
        "serialization": "py_pickle",
    }

    captured: dict[str, object] = {}

    class DummyClient:
        def __init__(self, system_database_url: str) -> None:
            self._serializer = object()
            self._sys_db = SimpleNamespace(
                get_workflow_status=lambda workflow_id: source_status,
                fork_workflow=lambda original_ids, forked_ids, start_steps, application_version, queue_name=None: None,
                engine=SimpleNamespace(begin=lambda: _DummyBeginContext(captured)),
            )

        def destroy(self) -> None:
            return None

    monkeypatch.setattr("control_plane.state.DBOSClient", DummyClient)
    response = manager._stage_edited_fork_sync("wf-1", 0, None, None, None, "executor-1", "v1")

    # Statements: (1) PENDING reset on fork, (2) was_forked_from on source.
    assert len(captured["statements"]) == 2
    for statement in captured["statements"]:
        assert "CANCELLED" not in str(statement)
    assert "source_workflow_cancelled" not in response
    assert "cancel_original_if_active" not in response


@pytest.mark.asyncio
async def test_stage_edited_fork_calls_send_cancel_before_sync_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, _ws = await make_ready_manager()

    call_order: list[str] = []

    async def fake_send_cancel(workflow_id: str):
        call_order.append(f"cancel:{workflow_id}")
        return SimpleNamespace(
            request_id="req-cancel",
            status="succeeded",
            response_payload={"success": True},
        )

    def fake_sync(*args, **kwargs):
        call_order.append("sync")
        return {
            "new_workflow_id": "wf-new",
            "stage_mode": "edited_fork",
            "source_workflow_id": args[0],
            "workflow_input_override": args[2],
            "step_output_overrides": {},
            "patched_step_ids": [],
            "start_step": args[1],
            "workflow_status": "PENDING",
            "requires_manual_execution": True,
            "source_workflow_status": "PENDING",
            "source_workflow_is_active": True,
        }

    monkeypatch.setattr(manager, "send_cancel", fake_send_cancel)
    monkeypatch.setattr(manager, "_stage_edited_fork_sync", fake_sync)

    record = await manager.stage_edited_fork(
        "wf-1",
        0,
        workflow_input_override={"name": "Ada"},
        cancel_original_if_active=True,
    )

    assert call_order == ["cancel:wf-1", "sync"]
    assert record.response_payload["source_workflow_cancelled"] is True
    assert record.response_payload["cancel_original_if_active"] is True
    assert record.response_payload["new_workflow_id"] == "wf-new"


@pytest.mark.asyncio
async def test_stage_edited_fork_skips_send_cancel_when_not_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, _ws = await make_ready_manager()

    cancel_calls: list[str] = []

    async def fake_send_cancel(workflow_id: str):  # pragma: no cover - must not run
        cancel_calls.append(workflow_id)
        return SimpleNamespace(request_id="req", status="succeeded", response_payload={})

    def fake_sync(*args, **kwargs):
        return {
            "new_workflow_id": "wf-new",
            "stage_mode": "edited_fork",
            "source_workflow_id": args[0],
            "workflow_input_override": args[2],
            "step_output_overrides": {},
            "patched_step_ids": [],
            "start_step": args[1],
            "workflow_status": "PENDING",
            "requires_manual_execution": True,
            "source_workflow_status": "PENDING",
            "source_workflow_is_active": False,
        }

    monkeypatch.setattr(manager, "send_cancel", fake_send_cancel)
    monkeypatch.setattr(manager, "_stage_edited_fork_sync", fake_sync)

    record = await manager.stage_edited_fork(
        "wf-1",
        0,
        workflow_input_override={"name": "Ada"},
        cancel_original_if_active=False,
    )

    assert cancel_calls == []
    assert record.response_payload["source_workflow_cancelled"] is False
    assert record.response_payload["cancel_original_if_active"] is False


@pytest.mark.asyncio
async def test_run_edited_fork_stages_then_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, _ws = await make_ready_manager()

    def fake_sync(*args, **kwargs):
        return {
            "new_workflow_id": "wf-staged",
            "stage_mode": "edited_fork",
            "source_workflow_id": args[0],
            "workflow_input_override": args[2],
            "step_output_overrides": {},
            "patched_step_ids": [],
            "start_step": args[1],
            "workflow_status": "PENDING",
            "requires_manual_execution": True,
            "source_workflow_status": "PENDING",
            "source_workflow_is_active": True,
        }

    monkeypatch.setattr(manager, "_stage_edited_fork_sync", fake_sync)

    async def fake_send_cancel(workflow_id: str):
        return SimpleNamespace(request_id="req-cancel", status="succeeded", response_payload={})

    monkeypatch.setattr(manager, "send_cancel", fake_send_cancel)

    execute_calls: list[str] = []

    async def fake_execute(workflow_id: str):
        execute_calls.append(workflow_id)
        return SimpleNamespace(
            request_id="req-exec",
            status="succeeded",
            response_payload={"execution_requested": True},
        )

    monkeypatch.setattr(manager, "execute_staged_fork", fake_execute)

    cancel_orphan_calls: list[tuple[str, str, str]] = []

    def fake_cancel_orphans(keep_workflow_id, executor_id, application_version):
        cancel_orphan_calls.append((keep_workflow_id, executor_id, application_version))
        return ["wf-orphan-1"]

    monkeypatch.setattr(manager, "_cancel_orphan_staged_forks_sync", fake_cancel_orphans)

    record = await manager.run_edited_fork(
        "wf-1",
        0,
        workflow_input_override={"name": "Ada"},
        cancel_original_if_active=True,
    )

    assert execute_calls == ["wf-staged"]
    assert cancel_orphan_calls == [("wf-staged", "executor-1", "v1")]
    assert record.message_type == "run_edited_fork"
    payload = record.response_payload
    assert payload["new_workflow_id"] == "wf-staged"
    assert payload["execution_requested"] is True
    assert payload["execute_request_id"] == "req-exec"
    assert payload["execute_status"] == "succeeded"
    assert payload["requires_manual_execution"] is False
    assert payload["stage_mode"] == "run_edited_fork"
    assert payload["cancelled_orphan_staged_forks"] == ["wf-orphan-1"]


def test_validate_execute_staged_fork_sync_rejects_other_pending_workflows(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = ConductorManager(
        app_name="dbos-starter",
        conductor_key="local-conductor-key",
        system_database_url="postgres://postgres:dbos@postgres:5432/dbos_starter",
    )

    workflow_status = {
        "status": "PENDING",
        "queue_name": None,
        "forked_from": "wf-source",
        "executor_id": "executor-1",
        "app_version": "v1",
    }

    class DummyPending:
        def __init__(self, workflow_id: str) -> None:
            self.workflow_id = workflow_id

    class DummyClient:
        def __init__(self, system_database_url: str) -> None:
            self._sys_db = SimpleNamespace(
                get_workflow_status=lambda workflow_id: workflow_status,
                get_pending_workflows=lambda executor_id, app_version: [
                    DummyPending("wf-staged"),
                    DummyPending("wf-other"),
                ],
            )

        def destroy(self) -> None:
            return None

    monkeypatch.setattr("control_plane.state.DBOSClient", DummyClient)

    with pytest.raises(RuntimeError) as exc_info:
        manager._validate_execute_staged_fork_sync("wf-staged", "executor-1", "v1")

    assert "other pending workflows exist" in str(exc_info.value)
    assert "wf-other" in str(exc_info.value)


def test_cancel_orphan_staged_forks_sync_cancels_other_pending_forks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ConductorManager(
        app_name="dbos-starter",
        conductor_key="local-conductor-key",
        system_database_url="postgres://postgres:dbos@postgres:5432/dbos_starter",
    )

    captured: dict[str, object] = {
        "fetchone_results": [],
        "fetchall_results": [
            [SimpleNamespace(workflow_uuid="wf-orphan-1"), SimpleNamespace(workflow_uuid="wf-orphan-2")],
        ],
    }

    class DummyClient:
        def __init__(self, system_database_url: str) -> None:
            self._sys_db = SimpleNamespace(
                engine=SimpleNamespace(begin=lambda: _DummyBeginContext(captured)),
            )

        def destroy(self) -> None:
            captured["destroyed"] = True

    monkeypatch.setattr("control_plane.state.DBOSClient", DummyClient)

    cancelled = manager._cancel_orphan_staged_forks_sync("wf-keep", "executor-1", "v1")

    assert cancelled == ["wf-orphan-1", "wf-orphan-2"]
    assert captured["destroyed"] is True
    # Statements: (1) SELECT for orphan ids, (2) UPDATE to CANCELLED.
    statements = captured["statements"]
    assert len(statements) == 2
    assert statements[1].compile().params["status"] == "CANCELLED"


def test_cancel_orphan_staged_forks_sync_no_orphans_skips_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ConductorManager(
        app_name="dbos-starter",
        conductor_key="local-conductor-key",
        system_database_url="postgres://postgres:dbos@postgres:5432/dbos_starter",
    )

    captured: dict[str, object] = {
        "fetchone_results": [],
        "fetchall_results": [[]],
    }

    class DummyClient:
        def __init__(self, system_database_url: str) -> None:
            self._sys_db = SimpleNamespace(
                engine=SimpleNamespace(begin=lambda: _DummyBeginContext(captured)),
            )

        def destroy(self) -> None:
            return None

    monkeypatch.setattr("control_plane.state.DBOSClient", DummyClient)

    cancelled = manager._cancel_orphan_staged_forks_sync("wf-keep", "executor-1", "v1")

    assert cancelled == []
    # Only the SELECT statement runs; no UPDATE when there's nothing to cancel.
    assert len(captured["statements"]) == 1


def test_stage_edited_fork_sync_cancels_forked_workflow_when_override_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If override application raises after fork_workflow has committed, the
    forked workflow must be marked CANCELLED so we don't leave a runnable
    fork without its intended overrides applied."""
    manager = ConductorManager(
        app_name="dbos-starter",
        conductor_key="local-conductor-key",
        system_database_url="postgres://postgres:dbos@postgres:5432/dbos_starter",
    )

    source_status = {
        "status": "ERROR",
        "name": "dbos_workflow",
        "queue_name": None,
        "app_version": "v1",
        "parent_workflow_id": None,
        "inputs": "serialized-inputs",
        "serialization": "py_pickle",
    }

    captured: dict[str, object] = {"fork_calls": []}

    # The first engine.begin() (override block) will raise on first execute.
    # The second engine.begin() (cleanup) must succeed and run a CANCELLED
    # update.
    class _RaisingConn:
        def __init__(self, captured: dict[str, object]) -> None:
            self.captured = captured

        def execute(self, statement):
            self.captured.setdefault("override_attempts", []).append(statement)
            raise ValueError("simulated override failure")

    class _RaisingBegin:
        def __init__(self, captured: dict[str, object]) -> None:
            self.captured = captured

        def __enter__(self):
            return _RaisingConn(self.captured)

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    begin_calls = {"count": 0}

    def begin():
        begin_calls["count"] += 1
        if begin_calls["count"] == 1:
            return _RaisingBegin(captured)
        return _DummyBeginContext(captured)

    class DummyClient:
        def __init__(self, system_database_url: str) -> None:
            self._serializer = object()
            self._sys_db = SimpleNamespace(
                get_workflow_status=lambda workflow_id: source_status,
                fork_workflow=lambda original_ids, forked_ids, start_steps, application_version, queue_name=None: captured["fork_calls"].append(forked_ids[0]),
                engine=SimpleNamespace(begin=begin),
            )

        def destroy(self) -> None:
            captured["destroyed"] = True

    monkeypatch.setattr("control_plane.state.DBOSClient", DummyClient)

    with pytest.raises(ValueError, match="simulated override failure"):
        manager._stage_edited_fork_sync(
            "wf-1",
            0,
            {"name": "Ada"},
            None,
            "wf-fork",
            "executor-1",
            "v1",
        )

    # fork_workflow ran; cleanup ran a CANCELLED update on the forked id.
    assert captured["fork_calls"] == ["wf-fork"]
    cleanup_statements = captured["statements"]
    assert len(cleanup_statements) == 1
    assert cleanup_statements[0].compile().params["status"] == "CANCELLED"
    assert captured["destroyed"] is True


@pytest.mark.asyncio
async def test_execute_staged_fork_requests_recovery_for_single_pending_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, _websocket = await make_ready_manager()

    monkeypatch.setattr(
        manager,
        "_validate_execute_staged_fork_sync",
        lambda workflow_id, executor_id, application_version: {
            "validated_workflow_id": workflow_id,
            "pending_workflow_ids": [workflow_id],
        },
    )

    captured: dict[str, object] = {}

    async def fake_send_recovery(executor_ids: list[str]):
        captured["executor_ids"] = executor_ids
        return SimpleNamespace(
            request_id="req-recovery",
            status="succeeded",
            response_payload={"success": True},
        )

    monkeypatch.setattr(manager, "send_recovery", fake_send_recovery)

    record = await manager.execute_staged_fork("wf-staged")

    assert captured["executor_ids"] == ["executor-1"]
    assert record.message_type == "execute_staged_fork"
    assert record.response_payload["execution_requested"] is True
    assert record.response_payload["validated_workflow_id"] == "wf-staged"


class _DummyBeginContext:
    def __init__(self, captured: dict[str, object]) -> None:
        self.captured = captured

    def __enter__(self):
        return _DummyConnection(self.captured)

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _DummyConnection:
    def __init__(self, captured: dict[str, object]) -> None:
        self.captured = captured

    def execute(self, statement):
        assert isinstance(statement, sa.sql.Executable)
        self.captured.setdefault("statements", []).append(statement)
        is_select = getattr(statement, "is_select", False)
        fetchall_results = self.captured.get("fetchall_results")
        if is_select and isinstance(fetchall_results, list) and fetchall_results:
            rows = fetchall_results.pop(0)
            return SimpleNamespace(fetchall=lambda: rows, fetchone=lambda: (rows[0] if rows else None), rowcount=len(rows))
        fetchone_results = self.captured.get("fetchone_results")
        if is_select and isinstance(fetchone_results, list) and fetchone_results:
            row = fetchone_results.pop(0)
            return SimpleNamespace(fetchone=lambda: row, rowcount=1)
        rowcounts = self.captured.get("rowcounts")
        if isinstance(rowcounts, list) and rowcounts:
            return SimpleNamespace(rowcount=rowcounts.pop(0))
        return SimpleNamespace(rowcount=1, fetchone=lambda: None, fetchall=lambda: [])

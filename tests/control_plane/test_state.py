from __future__ import annotations

import asyncio

import pytest

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

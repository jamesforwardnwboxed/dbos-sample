from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, cast
from uuid import uuid4

from dbos._conductor import protocol as dbos_protocol

MessageType = dbos_protocol.MessageType
BaseMessage = dbos_protocol.BaseMessage
CancelRequest = dbos_protocol.CancelRequest
CancelResponse = dbos_protocol.CancelResponse
ExecutorInfoRequest = dbos_protocol.ExecutorInfoRequest
ExecutorInfoResponse = dbos_protocol.ExecutorInfoResponse
ForkWorkflowRequest = dbos_protocol.ForkWorkflowRequest
ForkWorkflowResponse = dbos_protocol.ForkWorkflowResponse
GetWorkflowRequest = dbos_protocol.GetWorkflowRequest
GetWorkflowResponse = dbos_protocol.GetWorkflowResponse
ListQueuedWorkflowsRequest = dbos_protocol.ListQueuedWorkflowsRequest
ListQueuedWorkflowsResponse = dbos_protocol.ListQueuedWorkflowsResponse
ListStepsRequest = dbos_protocol.ListStepsRequest
ListStepsResponse = dbos_protocol.ListStepsResponse
ListWorkflowsRequest = dbos_protocol.ListWorkflowsRequest
ListWorkflowsResponse = dbos_protocol.ListWorkflowsResponse
RecoveryRequest = dbos_protocol.RecoveryRequest
RecoveryResponse = dbos_protocol.RecoveryResponse
RestartRequest = dbos_protocol.RestartRequest
RestartResponse = dbos_protocol.RestartResponse
ResumeRequest = dbos_protocol.ResumeRequest
ResumeResponse = dbos_protocol.ResumeResponse
WorkflowSteps = dbos_protocol.WorkflowSteps
WorkflowsOutput = dbos_protocol.WorkflowsOutput


def new_request_id() -> str:
    return str(uuid4())


def parse_base_message(message: str) -> BaseMessage:
    return BaseMessage.from_json(message)


def parse_executor_info_response(message: str) -> ExecutorInfoResponse:
    return ExecutorInfoResponse.from_json(message)


def parse_list_workflows_response(message: str) -> ListWorkflowsResponse:
    return ListWorkflowsResponse.from_json(message)


def parse_list_queued_workflows_response(message: str) -> ListQueuedWorkflowsResponse:
    return ListQueuedWorkflowsResponse.from_json(message)


def parse_get_workflow_response(message: str) -> GetWorkflowResponse:
    return GetWorkflowResponse.from_json(message)


def parse_list_steps_response(message: str) -> ListStepsResponse:
    return ListStepsResponse.from_json(message)


def parse_recovery_response(message: str) -> RecoveryResponse:
    return RecoveryResponse.from_json(message)


def parse_cancel_response(message: str) -> CancelResponse:
    return CancelResponse.from_json(message)


def parse_resume_response(message: str) -> ResumeResponse:
    return ResumeResponse.from_json(message)


def parse_restart_response(message: str) -> RestartResponse:
    return RestartResponse.from_json(message)


def parse_fork_workflow_response(message: str) -> ForkWorkflowResponse:
    return ForkWorkflowResponse.from_json(message)


def build_executor_info_request(request_id: str) -> ExecutorInfoRequest:
    return ExecutorInfoRequest(type=MessageType.EXECUTOR_INFO, request_id=request_id)


def build_list_workflows_request(request_id: str, body: dict[str, Any]) -> ListWorkflowsRequest:
    return ListWorkflowsRequest(
        type=MessageType.LIST_WORKFLOWS,
        request_id=request_id,
        body=cast(dbos_protocol.ListWorkflowsBody, body),
    )


def build_list_queued_workflows_request(
    request_id: str, body: dict[str, Any]
) -> ListQueuedWorkflowsRequest:
    return ListQueuedWorkflowsRequest(
        type=MessageType.LIST_QUEUED_WORKFLOWS,
        request_id=request_id,
        body=cast(dbos_protocol.ListQueuedWorkflowsBody, body),
    )


def build_get_workflow_request(
    request_id: str,
    workflow_id: str,
    *,
    load_input: bool = True,
    load_output: bool = True,
) -> GetWorkflowRequest:
    return GetWorkflowRequest(
        type=MessageType.GET_WORKFLOW,
        request_id=request_id,
        workflow_id=workflow_id,
        load_input=load_input,
        load_output=load_output,
    )


def build_list_steps_request(
    request_id: str,
    workflow_id: str,
    *,
    load_output: bool = True,
    limit: int | None = None,
    offset: int | None = None,
) -> ListStepsRequest:
    return ListStepsRequest(
        type=MessageType.LIST_STEPS,
        request_id=request_id,
        workflow_id=workflow_id,
        load_output=load_output,
        limit=limit,
        offset=offset,
    )


def build_recovery_request(request_id: str, executor_ids: list[str]) -> RecoveryRequest:
    return RecoveryRequest(
        type=MessageType.RECOVERY,
        request_id=request_id,
        executor_ids=executor_ids,
    )


def build_cancel_request(
    request_id: str,
    workflow_id: str,
    workflow_ids: list[str] | None = None,
) -> CancelRequest:
    return CancelRequest(
        type=MessageType.CANCEL,
        request_id=request_id,
        workflow_id=workflow_id,
        workflow_ids=workflow_ids,
    )


def build_resume_request(
    request_id: str,
    workflow_id: str,
    *,
    workflow_ids: list[str] | None = None,
    queue_name: str | None = None,
) -> ResumeRequest:
    return ResumeRequest(
        type=MessageType.RESUME,
        request_id=request_id,
        workflow_id=workflow_id,
        workflow_ids=workflow_ids,
        queue_name=queue_name,
    )


def build_restart_request(request_id: str, workflow_id: str) -> RestartRequest:
    return RestartRequest(
        type=MessageType.RESTART,
        request_id=request_id,
        workflow_id=workflow_id,
    )


def build_fork_workflow_request(
    request_id: str,
    workflow_id: str,
    start_step: int,
    *,
    new_workflow_id: str | None = None,
    application_version: str | None = None,
    queue_name: str | None = None,
) -> ForkWorkflowRequest:
    body: dict[str, Any] = {
        "workflow_id": workflow_id,
        "start_step": start_step,
        "new_workflow_id": new_workflow_id,
        "application_version": application_version,
    }
    if queue_name is not None:
        body["queue_name"] = queue_name
    return ForkWorkflowRequest(
        type=MessageType.FORK_WORKFLOW,
        request_id=request_id,
        body=cast(dbos_protocol.ForkWorkflowBody, body),
    )


def message_to_dict(message: Any) -> dict[str, Any]:
    if is_dataclass(message):
        return cast(dict[str, Any], asdict(message))
    raise TypeError("Expected dataclass message")


def message_type_value(message_type: Any) -> str:
    return message_type.value if hasattr(message_type, "value") else str(message_type)

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from dbos._client import DBOSClient
from dbos._schemas.system_database import SystemSchema
from dbos._serialization import (
    DBOSDefaultSerializer,
    DBOSPortableJSON,
    deserialize_args,
    deserialize_value,
    serialize_value_as,
)
import sqlalchemy as sa

from . import protocol


ACTIVE_SOURCE_STATUSES = {"PENDING", "ENQUEUED", "DELAYED"}


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def utc_now_epoch_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


@dataclass
class ExecutorSession:
    session_id: str
    app_name: str
    conductor_key: str
    connected_at: str
    last_seen_at: str
    status: str = "connecting"
    executor_info: dict[str, Any] | None = None
    handshake_request_id: str | None = None
    websocket: WebSocket | None = field(default=None, repr=False)


@dataclass
class ConductorRequestRecord:
    request_id: str
    message_type: str
    request_payload: dict[str, Any]
    created_at: str
    status: str = "queued"
    dispatched_at: str | None = None
    completed_at: str | None = None
    response_payload: dict[str, Any] | None = None
    error_payload: str | None = None


@dataclass
class ConductorEvent:
    timestamp: str
    direction: str
    message_type: str
    request_id: str | None
    summary: str


class ConductorManager:
    def __init__(
        self,
        app_name: str,
        conductor_key: str,
        request_timeout_seconds: float = 5.0,
        *,
        system_database_url: str | None = None,
    ):
        self.app_name = app_name
        self.conductor_key = conductor_key
        self.request_timeout_seconds = request_timeout_seconds
        self.system_database_url = system_database_url
        self._lock = asyncio.Lock()
        self._session: ExecutorSession | None = None
        self._requests: dict[str, ConductorRequestRecord] = {}
        self._pending_futures: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._events: list[ConductorEvent] = []
        self._last_list_workflows_output: list[dict[str, Any]] = []
        self._last_list_queued_workflows_output: list[dict[str, Any]] = []
        self._last_workflow_output: dict[str, Any] | None = None
        self._last_steps_output: list[dict[str, Any]] = []

    async def register_connection(self, websocket: WebSocket, app_name: str, conductor_key: str) -> ExecutorSession:
        async with self._lock:
            session = ExecutorSession(
                session_id=protocol.new_request_id(),
                app_name=app_name,
                conductor_key=conductor_key,
                connected_at=utc_now(),
                last_seen_at=utc_now(),
                websocket=websocket,
            )
            self._session = session
            self._append_event_locked("system", "connection", None, f"executor connected for {app_name}")
            return session

    async def begin_handshake(self) -> tuple[ExecutorSession, str]:
        async with self._lock:
            if self._session is None or self._session.websocket is None:
                raise RuntimeError("No active websocket session")
            request_id = protocol.new_request_id()
            self._session.handshake_request_id = request_id
            self._append_event_locked("outbound", protocol.message_type_value(protocol.MessageType.EXECUTOR_INFO), request_id, "sent executor_info request")
            websocket = self._session.websocket
            return self._session, request_id

    async def mark_handshake_complete(self, response: protocol.ExecutorInfoResponse) -> None:
        async with self._lock:
            if self._session is None:
                raise RuntimeError("No session to complete")
            self._session.status = "ready"
            self._session.last_seen_at = utc_now()
            self._session.executor_info = protocol.message_to_dict(response)
            self._append_event_locked("inbound", protocol.message_type_value(response.type), response.request_id, f"executor ready: {response.executor_id}")

    async def disconnect(self) -> None:
        async with self._lock:
            if self._session is not None:
                self._append_event_locked("system", "disconnect", None, "executor disconnected")
                self._session.status = "closed"
            self._session = None
            for future in self._pending_futures.values():
                if not future.done():
                    future.set_exception(RuntimeError("executor disconnected"))
            self._pending_futures = {}

    async def send_list_workflows(self, body: dict[str, Any]) -> ConductorRequestRecord:
        request = protocol.build_list_workflows_request(protocol.new_request_id(), body)
        return await self._send_request(request.type.value, protocol.message_to_dict(request), request.to_json())

    async def send_list_queued_workflows(self, body: dict[str, Any]) -> ConductorRequestRecord:
        request = protocol.build_list_queued_workflows_request(protocol.new_request_id(), body)
        return await self._send_request(request.type.value, protocol.message_to_dict(request), request.to_json())

    async def send_get_workflow(
        self,
        workflow_id: str,
        *,
        load_input: bool = True,
        load_output: bool = True,
    ) -> ConductorRequestRecord:
        request = protocol.build_get_workflow_request(
            protocol.new_request_id(),
            workflow_id,
            load_input=load_input,
            load_output=load_output,
        )
        return await self._send_request(request.type.value, protocol.message_to_dict(request), request.to_json())

    async def send_list_steps(
        self,
        workflow_id: str,
        *,
        load_output: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> ConductorRequestRecord:
        request = protocol.build_list_steps_request(
            protocol.new_request_id(),
            workflow_id,
            load_output=load_output,
            limit=limit,
            offset=offset,
        )
        return await self._send_request(request.type.value, protocol.message_to_dict(request), request.to_json())

    async def send_recovery(self, executor_ids: list[str]) -> ConductorRequestRecord:
        request = protocol.build_recovery_request(protocol.new_request_id(), executor_ids)
        return await self._send_request(request.type.value, protocol.message_to_dict(request), request.to_json())

    async def send_cancel(self, workflow_id: str) -> ConductorRequestRecord:
        request = protocol.build_cancel_request(protocol.new_request_id(), workflow_id)
        return await self._send_request(request.type.value, protocol.message_to_dict(request), request.to_json())

    async def send_resume(
        self, workflow_id: str, *, queue_name: str | None = None
    ) -> ConductorRequestRecord:
        request = protocol.build_resume_request(
            protocol.new_request_id(), workflow_id, queue_name=queue_name
        )
        return await self._send_request(request.type.value, protocol.message_to_dict(request), request.to_json())

    async def send_restart(self, workflow_id: str) -> ConductorRequestRecord:
        request = protocol.build_restart_request(protocol.new_request_id(), workflow_id)
        return await self._send_request(request.type.value, protocol.message_to_dict(request), request.to_json())

    async def send_fork_workflow(
        self,
        workflow_id: str,
        start_step: int,
        *,
        new_workflow_id: str | None = None,
        application_version: str | None = None,
        queue_name: str | None = None,
    ) -> ConductorRequestRecord:
        request = protocol.build_fork_workflow_request(
            protocol.new_request_id(),
            workflow_id,
            start_step,
            new_workflow_id=new_workflow_id,
            application_version=application_version,
            queue_name=queue_name,
        )
        return await self._send_request(request.type.value, protocol.message_to_dict(request), request.to_json())

    async def record_local_action(
        self,
        message_type: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
    ) -> ConductorRequestRecord:
        async with self._lock:
            record = ConductorRequestRecord(
                request_id=protocol.new_request_id(),
                message_type=message_type,
                request_payload=request_payload,
                created_at=utc_now(),
                status="succeeded",
                dispatched_at=utc_now(),
                completed_at=utc_now(),
                response_payload=response_payload,
            )
            self._requests[record.request_id] = record
            self._append_event_locked(
                "system",
                message_type,
                record.request_id,
                f"completed local {message_type} action",
            )
            return record

    async def stage_edited_fork(
        self,
        workflow_id: str,
        start_step: int,
        *,
        workflow_input_override: dict[str, Any] | None = None,
        step_output_overrides: dict[str, Any] | None = None,
        new_workflow_id: str | None = None,
        cancel_original_if_active: bool = False,
    ) -> ConductorRequestRecord:
        executor_id, application_version = await self._require_ready_executor_target()

        # Cancel the original via the same websocket cancel command the UI Cancel
        # button uses, BEFORE we fork. This avoids racing the executor.
        source_cancelled = False
        if cancel_original_if_active:
            try:
                cancel_record = await self.send_cancel(workflow_id)
                source_cancelled = cancel_record.status == "succeeded"
            except RuntimeError:
                source_cancelled = False

        response_payload = await asyncio.to_thread(
            self._stage_edited_fork_sync,
            workflow_id,
            start_step,
            workflow_input_override,
            step_output_overrides,
            new_workflow_id,
            executor_id,
            application_version,
        )
        response_payload["source_workflow_cancelled"] = source_cancelled
        response_payload["cancel_original_if_active"] = cancel_original_if_active
        return await self.record_local_action(
            "stage_edited_fork",
            {
                "workflow_id": workflow_id,
                "start_step": start_step,
                "workflow_input_override": workflow_input_override,
                "step_output_overrides": step_output_overrides,
                "new_workflow_id": new_workflow_id,
                "cancel_original_if_active": cancel_original_if_active,
            },
            response_payload,
        )

    async def run_edited_fork(
        self,
        workflow_id: str,
        start_step: int,
        *,
        workflow_input_override: dict[str, Any] | None = None,
        step_output_overrides: dict[str, Any] | None = None,
        new_workflow_id: str | None = None,
        cancel_original_if_active: bool = False,
    ) -> ConductorRequestRecord:
        stage_record = await self.stage_edited_fork(
            workflow_id,
            start_step,
            workflow_input_override=workflow_input_override,
            step_output_overrides=step_output_overrides,
            new_workflow_id=new_workflow_id,
            cancel_original_if_active=cancel_original_if_active,
        )
        staged_workflow_id = (stage_record.response_payload or {}).get("new_workflow_id")
        if not staged_workflow_id:
            raise RuntimeError("Staged fork did not return a new_workflow_id")
        execute_record = await self.execute_staged_fork(staged_workflow_id)
        combined_payload = dict(stage_record.response_payload or {})
        combined_payload.update(
            {
                "execution_requested": True,
                "execute_request_id": execute_record.request_id,
                "execute_status": execute_record.status,
                "requires_manual_execution": False,
                "stage_mode": "run_edited_fork",
            }
        )
        return await self.record_local_action(
            "run_edited_fork",
            {
                "workflow_id": workflow_id,
                "start_step": start_step,
                "workflow_input_override": workflow_input_override,
                "step_output_overrides": step_output_overrides,
                "new_workflow_id": new_workflow_id,
                "cancel_original_if_active": cancel_original_if_active,
            },
            combined_payload,
        )

    async def execute_staged_fork(self, workflow_id: str) -> ConductorRequestRecord:
        executor_id, application_version = await self._require_ready_executor_target()
        validation = await asyncio.to_thread(
            self._validate_execute_staged_fork_sync,
            workflow_id,
            executor_id,
            application_version,
        )
        recovery_record = await self.send_recovery([executor_id])
        return await self.record_local_action(
            "execute_staged_fork",
            {
                "workflow_id": workflow_id,
                "executor_id": executor_id,
                "application_version": application_version,
            },
            {
                "workflow_id": workflow_id,
                "execution_requested": True,
                "recovery_request_id": recovery_record.request_id,
                "recovery_status": recovery_record.status,
                "executor_id": executor_id,
                "application_version": application_version,
                **validation,
            },
        )

    def _stage_edited_fork_sync(
        self,
        workflow_id: str,
        start_step: int,
        workflow_input_override: dict[str, Any] | None,
        step_output_overrides: dict[str, Any] | None,
        new_workflow_id: str | None,
        executor_id: str,
        application_version: str,
    ) -> dict[str, Any]:
        if self.system_database_url is None:
            raise RuntimeError("Control plane system database URL is not configured")

        normalized_input_override = (
            dict(workflow_input_override) if workflow_input_override is not None else None
        )
        normalized_step_overrides = _normalize_step_output_overrides(step_output_overrides)

        client = DBOSClient(system_database_url=self.system_database_url)
        try:
            source_status = client._sys_db.get_workflow_status(workflow_id)
            if source_status is None:
                raise LookupError(f"Unknown workflow_id: {workflow_id}")
            if source_status.get("parent_workflow_id") is not None:
                raise RuntimeError("edited fork does not yet support child workflows")

            new_workflow_uuid = new_workflow_id or protocol.new_request_id()
            current_time_ms = utc_now_epoch_ms()
            source_status_value = source_status.get("status")
            source_is_active = source_status_value in ACTIVE_SOURCE_STATUSES

            with client._sys_db.engine.begin() as conn:
                client._sys_db.fork_workflow(
                    [workflow_id],
                    [new_workflow_uuid],
                    [start_step],
                    application_version=application_version,
                    queue_name=None,
                )
                conn.execute(
                    sa.update(SystemSchema.workflow_status)
                    .where(SystemSchema.workflow_status.c.workflow_uuid == new_workflow_uuid)
                    .values(
                        status="PENDING",
                        queue_name=None,
                        executor_id=executor_id,
                        updated_at=current_time_ms,
                        workflow_deadline_epoch_ms=None,
                        started_at_epoch_ms=None,
                        delay_until_epoch_ms=None,
                        rate_limited=False,
                        output=None,
                        error=None,
                        recovery_attempts=0,
                        deduplication_id=None,
                    )
                )

                if normalized_input_override is not None:
                    serialized_inputs, serialization = _build_workflow_input_override(
                        source_status,
                        normalized_input_override,
                        client._serializer,
                    )
                    conn.execute(
                        sa.update(SystemSchema.workflow_status)
                        .where(SystemSchema.workflow_status.c.workflow_uuid == new_workflow_uuid)
                        .values(
                            inputs=serialized_inputs,
                            serialization=serialization,
                            updated_at=current_time_ms,
                        )
                    )

                patched_step_ids: list[int] = []
                for function_id, output_override in normalized_step_overrides.items():
                    if function_id >= start_step:
                        raise ValueError(
                            f"step_output_overrides only supports preserved steps before start_step {start_step}"
                        )
                    patched_step_ids.append(
                        _patch_forked_step_output(
                            conn,
                            source_workflow_id=workflow_id,
                            forked_workflow_id=new_workflow_uuid,
                            function_id=function_id,
                            serializer=client._serializer,
                            output_override=output_override,
                        )
                    )

                conn.execute(
                    sa.update(SystemSchema.workflow_status)
                    .where(SystemSchema.workflow_status.c.workflow_uuid == workflow_id)
                    .values(was_forked_from=True)
                )

            return {
                "new_workflow_id": new_workflow_uuid,
                "stage_mode": "edited_fork",
                "source_workflow_id": workflow_id,
                "workflow_input_override": normalized_input_override,
                "step_output_overrides": {
                    str(function_id): normalized_step_overrides[function_id]
                    for function_id in sorted(normalized_step_overrides)
                },
                "patched_step_ids": sorted(patched_step_ids),
                "start_step": start_step,
                "workflow_status": "PENDING",
                "requires_manual_execution": True,
                "source_workflow_status": source_status_value,
                "source_workflow_is_active": source_is_active,
            }
        finally:
            client.destroy()

    def _validate_execute_staged_fork_sync(
        self,
        workflow_id: str,
        executor_id: str,
        application_version: str,
    ) -> dict[str, Any]:
        if self.system_database_url is None:
            raise RuntimeError("Control plane system database URL is not configured")

        client = DBOSClient(system_database_url=self.system_database_url)
        try:
            workflow_status = client._sys_db.get_workflow_status(workflow_id)
            if workflow_status is None:
                raise LookupError(f"Unknown workflow_id: {workflow_id}")
            if workflow_status.get("status") != "PENDING":
                raise RuntimeError("Only staged PENDING forks can be executed")
            if workflow_status.get("queue_name") is not None:
                raise RuntimeError("Only staged non-queued forks can be executed")
            if workflow_status.get("forked_from") is None:
                raise RuntimeError("Only forked workflows can be executed from this action")
            if workflow_status.get("executor_id") != executor_id:
                raise RuntimeError("Staged fork executor does not match the active executor session")
            if workflow_status.get("app_version") != application_version:
                raise RuntimeError("Staged fork application version does not match the active executor session")

            pending_workflows = client._sys_db.get_pending_workflows(
                executor_id,
                application_version,
            )
            pending_workflow_ids = sorted(item.workflow_id for item in pending_workflows)
            if pending_workflow_ids != [workflow_id]:
                raise RuntimeError(
                    "Cannot execute staged fork while other pending workflows exist for the same executor/version"
                )

            return {
                "validated_workflow_id": workflow_id,
                "pending_workflow_ids": pending_workflow_ids,
            }
        finally:
            client.destroy()

    async def launch_input_override_rerun(
        self,
        workflow_id: str,
        start_step: int,
        *,
        input_override: dict[str, Any],
        new_workflow_id: str | None = None,
        cancel_original_if_active: bool = False,
    ) -> ConductorRequestRecord:
        return await self.stage_edited_fork(
            workflow_id,
            start_step,
            workflow_input_override=input_override,
            new_workflow_id=new_workflow_id,
            cancel_original_if_active=cancel_original_if_active,
        )

    async def _require_ready_executor_target(self) -> tuple[str, str]:
        async with self._lock:
            if self._session is None or self._session.status != "ready":
                raise RuntimeError("No ready executor session")
            executor_info = self._session.executor_info or {}

        executor_id = executor_info.get("executor_id")
        application_version = executor_info.get("application_version")
        if not isinstance(executor_id, str) or not executor_id:
            raise RuntimeError("Ready executor session is missing executor_id")
        if not isinstance(application_version, str) or not application_version:
            raise RuntimeError("Ready executor session is missing application_version")
        return executor_id, application_version

    async def _send_request(self, message_type: str, request_payload: dict[str, Any], payload_json: str) -> ConductorRequestRecord:
        async with self._lock:
            if self._session is None or self._session.websocket is None or self._session.status != "ready":
                raise RuntimeError("No ready executor session")
            record = ConductorRequestRecord(
                request_id=request_payload["request_id"],
                message_type=message_type,
                request_payload=request_payload,
                created_at=utc_now(),
            )
            record.status = "sent"
            record.dispatched_at = utc_now()
            self._requests[record.request_id] = record
            loop = asyncio.get_running_loop()
            future: asyncio.Future[dict[str, Any]] = loop.create_future()
            self._pending_futures[record.request_id] = future
            websocket = self._session.websocket
            self._session.last_seen_at = utc_now()
            self._append_event_locked("outbound", message_type, record.request_id, f"sent {message_type} request")
        assert websocket is not None
        await websocket.send_text(payload_json)
        try:
            await asyncio.wait_for(future, timeout=self.request_timeout_seconds)
        except Exception as exc:
            async with self._lock:
                record.status = "timed_out" if isinstance(exc, TimeoutError) else "failed"
                record.error_payload = str(exc)
                record.completed_at = utc_now()
                self._append_event_locked("system", message_type, record.request_id, f"request {record.status}")
                self._pending_futures.pop(record.request_id, None)
            raise
        return record

    async def complete_request_from_message(self, message: str) -> None:
        base_message = protocol.parse_base_message(message)
        async with self._lock:
            if self._session is not None:
                self._session.last_seen_at = utc_now()

        if base_message.type == protocol.MessageType.EXECUTOR_INFO:
            response = protocol.parse_executor_info_response(message)
            await self.mark_handshake_complete(response)
            return

        if base_message.type == protocol.MessageType.LIST_WORKFLOWS:
            response = protocol.parse_list_workflows_response(message)
            response_payload = protocol.message_to_dict(response)
            async with self._lock:
                self._complete_request_locked(base_message.request_id, response_payload)
                self._last_list_workflows_output = [
                    item if isinstance(item, dict) else protocol.message_to_dict(item)
                    for item in response.output
                ]
            return

        if base_message.type == protocol.MessageType.LIST_QUEUED_WORKFLOWS:
            response = protocol.parse_list_queued_workflows_response(message)
            response_payload = protocol.message_to_dict(response)
            async with self._lock:
                self._complete_request_locked(base_message.request_id, response_payload)
                self._last_list_queued_workflows_output = [
                    item if isinstance(item, dict) else protocol.message_to_dict(item)
                    for item in response.output
                ]
            return

        if base_message.type == protocol.MessageType.GET_WORKFLOW:
            response = protocol.parse_get_workflow_response(message)
            response_payload = protocol.message_to_dict(response)
            async with self._lock:
                self._complete_request_locked(base_message.request_id, response_payload)
                self._last_workflow_output = response_payload.get("output")
            return

        if base_message.type == protocol.MessageType.LIST_STEPS:
            response = protocol.parse_list_steps_response(message)
            response_payload = protocol.message_to_dict(response)
            async with self._lock:
                self._complete_request_locked(base_message.request_id, response_payload)
                self._last_steps_output = response_payload.get("output") or []
            return

        if base_message.type == protocol.MessageType.RECOVERY:
            response = protocol.parse_recovery_response(message)
            response_payload = protocol.message_to_dict(response)
            async with self._lock:
                self._complete_request_locked(base_message.request_id, response_payload)
            return

        if base_message.type == protocol.MessageType.CANCEL:
            response = protocol.parse_cancel_response(message)
            response_payload = protocol.message_to_dict(response)
            async with self._lock:
                self._complete_request_locked(base_message.request_id, response_payload)
            return

        if base_message.type == protocol.MessageType.RESUME:
            response = protocol.parse_resume_response(message)
            response_payload = protocol.message_to_dict(response)
            async with self._lock:
                self._complete_request_locked(base_message.request_id, response_payload)
            return

        if base_message.type == protocol.MessageType.RESTART:
            response = protocol.parse_restart_response(message)
            response_payload = protocol.message_to_dict(response)
            async with self._lock:
                self._complete_request_locked(base_message.request_id, response_payload)
            return

        if base_message.type == protocol.MessageType.FORK_WORKFLOW:
            response = protocol.parse_fork_workflow_response(message)
            response_payload = protocol.message_to_dict(response)
            async with self._lock:
                self._complete_request_locked(base_message.request_id, response_payload)
            return

        async with self._lock:
            self._append_event_locked("system", protocol.message_type_value(base_message.type), base_message.request_id, "unsupported response type")
        raise RuntimeError(f"Unsupported message type: {base_message.type}")

    def _complete_request_locked(self, request_id: str, response_payload: dict[str, Any]) -> None:
        record = self._requests.get(request_id)
        if record is None:
            self._append_event_locked("system", response_payload.get("type", "unknown"), request_id, "response for unknown request")
            raise RuntimeError(f"Unknown request_id: {request_id}")
        record.status = "succeeded" if not response_payload.get("error_message") else "failed"
        record.completed_at = utc_now()
        record.response_payload = response_payload
        if response_payload.get("error_message"):
            record.error_payload = response_payload["error_message"]
        self._append_event_locked("inbound", record.message_type, request_id, f"completed {record.message_type} request")
        future = self._pending_futures.pop(request_id, None)
        if future is not None and not future.done():
            future.set_result(response_payload)

    def _append_event_locked(self, direction: str, message_type: str, request_id: str | None, summary: str) -> None:
        self._events.append(
            ConductorEvent(
                timestamp=utc_now(),
                direction=direction,
                message_type=message_type,
                request_id=request_id,
                summary=summary,
            )
        )
        self._events = self._events[-25:]

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            session = None if self._session is None else {
                "session_id": self._session.session_id,
                "app_name": self._session.app_name,
                "conductor_key": self._session.conductor_key,
                "connected_at": self._session.connected_at,
                "last_seen_at": self._session.last_seen_at,
                "status": self._session.status,
                "executor_info": self._session.executor_info,
            }
            requests = [
                asdict(record)
                for record in sorted(self._requests.values(), key=lambda item: item.created_at, reverse=True)
            ]
            events = [asdict(event) for event in reversed(self._events)]
            return {
                "configured_app_name": self.app_name,
                "session": session,
                "requests": requests,
                "events": events,
                "last_list_workflows_output": self._last_list_workflows_output,
                "last_list_queued_workflows_output": self._last_list_queued_workflows_output,
                "last_workflow_output": self._last_workflow_output,
                "last_steps_output": self._last_steps_output,
            }


def _serialize_workflow_inputs(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    serialization: str | None,
    serializer: Any,
) -> tuple[str, str]:
    if serialization == DBOSPortableJSON.name():
        return (
            DBOSPortableJSON.serialize(
                {"positionalArgs": list(args), "namedArgs": kwargs}
            ),
            DBOSPortableJSON.name(),
        )
    if serialization == DBOSDefaultSerializer.name():
        return DBOSDefaultSerializer.serialize({"args": args, "kwargs": kwargs}), DBOSDefaultSerializer.name()
    if serialization is not None and serialization != serializer.name():
        raise RuntimeError(f"Serialization {serialization} is not available")
    return serializer.serialize({"args": args, "kwargs": kwargs}), serializer.name()


def _build_workflow_input_override(
    source_status: dict[str, Any],
    workflow_input_override: dict[str, Any],
    serializer: Any,
) -> tuple[str, str]:
    workflow_inputs = deserialize_args(
        source_status["inputs"],
        source_status.get("serialization"),
        serializer,
    )
    args = tuple(workflow_inputs.get("args") or ())
    kwargs = dict(workflow_input_override)
    return _serialize_workflow_inputs(
        args,
        kwargs,
        source_status.get("serialization"),
        serializer,
    )


def _normalize_step_output_overrides(
    step_output_overrides: dict[str, Any] | None,
) -> dict[int, Any]:
    if step_output_overrides is None:
        return {}
    normalized: dict[int, Any] = {}
    for raw_function_id, value in step_output_overrides.items():
        try:
            function_id = int(raw_function_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("step_output_overrides keys must be integer step ids") from exc
        if function_id < 0:
            raise ValueError("step_output_overrides keys must be non-negative step ids")
        normalized[function_id] = value
    return normalized


def _patch_forked_step_output(
    conn: sa.Connection,
    *,
    source_workflow_id: str,
    forked_workflow_id: str,
    function_id: int,
    output_override: Any,
    serializer: Any,
) -> int:
    step_row = conn.execute(
        sa.select(
            SystemSchema.operation_outputs.c.function_name,
            SystemSchema.operation_outputs.c.serialization,
            SystemSchema.operation_outputs.c.output,
        )
        .where(SystemSchema.operation_outputs.c.workflow_uuid == source_workflow_id)
        .where(SystemSchema.operation_outputs.c.function_id == function_id)
    ).fetchone()
    if step_row is None:
        raise LookupError(
            f"Cannot override missing step output for function_id {function_id}"
        )

    if step_row.output is None:
        raise ValueError(f"Step {function_id} has no recorded output to override")

    original_value = deserialize_value(step_row.output, step_row.serialization, serializer)
    if type(output_override) is not type(original_value):
        raise ValueError(
            f"Step {function_id} override type {type(output_override).__name__} does not match recorded output type {type(original_value).__name__}"
        )

    serialized_output, serialization = serialize_value_as(
        output_override,
        step_row.serialization,
        serializer,
    )
    update_result = conn.execute(
        sa.update(SystemSchema.operation_outputs)
        .where(SystemSchema.operation_outputs.c.workflow_uuid == forked_workflow_id)
        .where(SystemSchema.operation_outputs.c.function_id == function_id)
        .values(
            output=serialized_output,
            error=None,
            serialization=serialization,
        )
    )
    if update_result.rowcount != 1:
        raise LookupError(
            f"Forked workflow is missing preserved step output for function_id {function_id}"
        )
    return function_id

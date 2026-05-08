from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from . import protocol


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


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
    def __init__(self, app_name: str, conductor_key: str, request_timeout_seconds: float = 5.0):
        self.app_name = app_name
        self.conductor_key = conductor_key
        self.request_timeout_seconds = request_timeout_seconds
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

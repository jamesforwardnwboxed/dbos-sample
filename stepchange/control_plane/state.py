from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import MISSING, asdict, dataclass, field, fields, is_dataclass
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
from dbos._sys_db import INTERNAL_QUEUE_NAME, WorkflowStatusString
import sqlalchemy as sa

from . import protocol


ACTIVE_SOURCE_STATUSES = {"PENDING", "ENQUEUED", "DELAYED"}

# Serializer name used by the DBOS Go (and TypeScript) SDKs. Encodes a single
# raw value as base64(json.dumps(value)) — no {args, kwargs} wrapper. The
# Python SDK does not register this codec natively, so the control plane
# carries its own implementation in order to read/write workflow inputs and
# step outputs on databases owned by non-Python executors.
DBOS_JSON_NAME = "DBOS_JSON"

# The TypeScript SDK uses superjson and tags rows with `serialization=js_superjson`.
# Workflow inputs are stored as `{"json": <positional_args_list>,
# "__dbos_serializer": "superjson"}` (no kwargs), and step outputs as
# `{"json": <value>, "__dbos_serializer": "superjson"}`. The Python SDK has no
# built-in superjson codec, so the control plane carries a minimal one.
JS_SUPERJSON_NAME = "js_superjson"

# The Java SDK (`java_jackson`) uses Jackson with default polymorphic typing
# enabled (NON_FINAL types tagged via WRAPPER_ARRAY). Workflow inputs are stored
# as `["[Ljava.lang.Object;", [<args>...]]` — i.e. a Jackson-typed Object[]
# whose first element is the JVM internal class name and the second is the
# concrete payload. Step outputs use the same wrapper-array shape but with the
# value-type tag (e.g. `["java.lang.Integer", 5]`) or a raw scalar for
# primitive results. The Python SDK has no native java_jackson codec, so the
# control plane carries a minimal one for forks against Java schemas.
JAVA_JACKSON_NAME = "java_jackson"
JAVA_OBJECT_ARRAY_TYPE = "[Ljava.lang.Object;"


def _dbos_json_encode(value: Any) -> str:
    return base64.b64encode(json.dumps(value).encode("utf-8")).decode("ascii")


def _js_superjson_encode(value: Any) -> str:
    # Match the TypeScript SDK's exact wire format. The SDK detects superjson
    # rows by literal substring match on `"__dbos_serializer":"superjson"`
    # (no spaces around the colon), so we must emit compact JSON or recovery
    # falls through to the legacy DBOSJSON path and the inputs are parsed as
    # an opaque object instead of the expected positional-args array.
    return json.dumps(
        {"json": value, "__dbos_serializer": "superjson"},
        separators=(",", ":"),
    )


def _java_jackson_encode_args(args: list[Any]) -> str:
    # Java workflows take positional args of any types. We always wrap the
    # outer array as `Object[]` (matching the SDK) and let each element be
    # encoded as a plain JSON scalar; the SDK's Jackson reader will attempt
    # to coerce values into the workflow method's declared parameter types.
    return json.dumps([JAVA_OBJECT_ARRAY_TYPE, list(args)], separators=(",", ":"))


def _java_jackson_encode_value(value: Any) -> str:
    # Step outputs that are scalars (numbers, booleans, null) are stored
    # without a type tag by Jackson's default typer. Strings and complex
    # objects do get a tag, but for forks we only ever round-trip values that
    # came back from `_java_jackson_decode` — so re-emit the same shape.
    return json.dumps(value, separators=(",", ":"))


def _java_jackson_decode(serialized: str) -> Any:
    parsed = json.loads(serialized)
    if (
        isinstance(parsed, list)
        and len(parsed) == 2
        and isinstance(parsed[0], str)
    ):
        # Wrapper-array form: drop the type tag and unwrap nested wrappers.
        return _java_jackson_unwrap(parsed[1])
    return _java_jackson_unwrap(parsed)


def _java_jackson_unwrap(value: Any) -> Any:
    if isinstance(value, list):
        return [_java_jackson_unwrap(v) for v in value]
    if isinstance(value, dict):
        return {k: _java_jackson_unwrap(v) for k, v in value.items()}
    return value


def _js_superjson_decode(serialized: str) -> Any:
    payload = json.loads(serialized)
    if not isinstance(payload, dict) or "json" not in payload:
        raise RuntimeError(
            "js_superjson payload missing top-level 'json' field"
        )
    return payload["json"]


def _dbos_json_decode(serialized: str) -> Any:
    return json.loads(base64.b64decode(serialized.encode("ascii")).decode("utf-8"))


def _columns_for_workflow_status(engine: sa.Engine) -> frozenset[str]:
    """Return the set of column names actually present on dbos.workflow_status
    for the given engine. The Go and TypeScript DBOS SDKs ship slightly
    different schemas than the Python SDK (they omit `was_forked_from` and
    `rate_limited`), so the control plane must adapt its writes at runtime."""
    cached = getattr(engine, "_control_plane_workflow_status_columns", None)
    if cached is not None:
        return cached
    inspector = sa.inspect(engine)
    cols = frozenset(c["name"] for c in inspector.get_columns("workflow_status", schema="dbos"))
    try:
        engine._control_plane_workflow_status_columns = cols  # type: ignore[attr-defined]
    except Exception:
        pass
    return cols


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def utc_now_epoch_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def _json_safe_preview(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        return {key: _json_safe_preview(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        return [_json_safe_preview(item) for item in value]
    if isinstance(value, list):
        return [_json_safe_preview(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_preview(item) for key, item in value.items()}
    return repr(value)


def _coerce_override_like(template: Any, value: Any) -> Any:
    if is_dataclass(template):
        if not isinstance(value, dict):
            raise ValueError(
                f"Expected object override for {type(template).__name__}, got {type(value).__name__}"
            )
        coerced_fields: dict[str, Any] = {}
        for dataclass_field in fields(template):
            if dataclass_field.name in value:
                coerced_fields[dataclass_field.name] = _coerce_override_like(
                    getattr(template, dataclass_field.name),
                    value[dataclass_field.name],
                )
            elif dataclass_field.default is not MISSING:
                coerced_fields[dataclass_field.name] = getattr(template, dataclass_field.name)
            elif dataclass_field.default_factory is not MISSING:  # type: ignore[attr-defined]
                coerced_fields[dataclass_field.name] = getattr(template, dataclass_field.name)
            else:
                raise ValueError(
                    f"Missing field '{dataclass_field.name}' for {type(template).__name__} override"
                )
        return type(template)(**coerced_fields)
    if isinstance(template, tuple) and isinstance(value, list):
        return tuple(
            _coerce_override_like(template[min(index, len(template) - 1)], item) if template else item
            for index, item in enumerate(value)
        )
    if isinstance(template, list) and isinstance(value, list):
        if not template:
            return value
        return [
            _coerce_override_like(template[min(index, len(template) - 1)], item)
            for index, item in enumerate(value)
        ]
    if isinstance(template, dict) and isinstance(value, dict):
        return {
            key: _coerce_override_like(template[key], item) if key in template else item
            for key, item in value.items()
        }
    return value


def _normalize_raw_step_output_overrides(
    step_output_overrides: dict[str, str] | None,
) -> dict[int, str]:
    if step_output_overrides is None:
        return {}
    normalized: dict[int, str] = {}
    for raw_function_id, value in step_output_overrides.items():
        try:
            function_id = int(raw_function_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("raw_step_output_overrides keys must be integer step ids") from exc
        if function_id < 0:
            raise ValueError("raw_step_output_overrides keys must be non-negative step ids")
        if not isinstance(value, str):
            raise ValueError("raw_step_output_overrides values must be strings")
        normalized[function_id] = value
    return normalized


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
        raw_workflow_input_override: str | None = None,
        step_output_overrides: dict[str, Any] | None = None,
        raw_step_output_overrides: dict[str, str] | None = None,
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
            raw_workflow_input_override,
            step_output_overrides,
            raw_step_output_overrides,
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
                "raw_workflow_input_override": raw_workflow_input_override,
                "step_output_overrides": step_output_overrides,
                "raw_step_output_overrides": raw_step_output_overrides,
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
        raw_workflow_input_override: str | None = None,
        step_output_overrides: dict[str, Any] | None = None,
        raw_step_output_overrides: dict[str, str] | None = None,
        new_workflow_id: str | None = None,
        cancel_original_if_active: bool = False,
    ) -> ConductorRequestRecord:
        stage_record = await self.stage_edited_fork(
            workflow_id,
            start_step,
            workflow_input_override=workflow_input_override,
            raw_workflow_input_override=raw_workflow_input_override,
            step_output_overrides=step_output_overrides,
            raw_step_output_overrides=raw_step_output_overrides,
            new_workflow_id=new_workflow_id,
            cancel_original_if_active=cancel_original_if_active,
        )
        staged_workflow_id = (stage_record.response_payload or {}).get("new_workflow_id")
        if not staged_workflow_id:
            raise RuntimeError("Staged fork did not return a new_workflow_id")
        # Clear any prior orphan staged PENDING forks for this executor so the
        # recovery-driven execute step can run without tripping the
        # "other pending workflows exist" guard.
        executor_id, application_version = await self._require_ready_executor_target()
        cancelled_orphans = await asyncio.to_thread(
            self._cancel_orphan_staged_forks_sync,
            staged_workflow_id,
            executor_id,
            application_version,
        )
        execute_record = await self.execute_staged_fork(staged_workflow_id)
        combined_payload = dict(stage_record.response_payload or {})
        combined_payload.update(
            {
                "execution_requested": True,
                "execute_request_id": execute_record.request_id,
                "execute_status": execute_record.status,
                "requires_manual_execution": False,
                "stage_mode": "run_edited_fork",
                "cancelled_orphan_staged_forks": cancelled_orphans,
            }
        )
        return await self.record_local_action(
            "run_edited_fork",
            {
                "workflow_id": workflow_id,
                "start_step": start_step,
                "workflow_input_override": workflow_input_override,
                "raw_workflow_input_override": raw_workflow_input_override,
                "step_output_overrides": step_output_overrides,
                "raw_step_output_overrides": raw_step_output_overrides,
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
        raw_workflow_input_override: str | None,
        step_output_overrides: dict[str, Any] | None,
        raw_step_output_overrides: dict[str, str] | None,
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
        normalized_raw_step_overrides = _normalize_raw_step_output_overrides(raw_step_output_overrides)

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

            # Detect optional columns: the Go and TypeScript DBOS SDKs ship
            # workflow_status without `was_forked_from`/`rate_limited`, so we
            # must skip those writes when targeting their schemas.
            workflow_status_columns = _columns_for_workflow_status(client._sys_db.engine)
            has_was_forked_from = "was_forked_from" in workflow_status_columns
            has_rate_limited = "rate_limited" in workflow_status_columns

            # Stage the fork ourselves rather than via the SDK's fork_workflow
            # method, which would unconditionally update `was_forked_from` on
            # the source row and break on non-Python schemas.
            with client._sys_db.engine.begin() as fork_conn:
                _fork_workflow_compat(
                    fork_conn,
                    original_workflow_id=workflow_id,
                    forked_workflow_id=new_workflow_uuid,
                    start_step=start_step,
                    application_version=application_version,
                    source_status=source_status,
                    has_was_forked_from=has_was_forked_from,
                )

            try:
                with client._sys_db.engine.begin() as conn:
                    pending_values: dict[str, Any] = dict(
                        status="PENDING",
                        queue_name=None,
                        executor_id=executor_id,
                        updated_at=current_time_ms,
                        workflow_deadline_epoch_ms=None,
                        started_at_epoch_ms=None,
                        delay_until_epoch_ms=None,
                        output=None,
                        error=None,
                        recovery_attempts=0,
                        deduplication_id=None,
                    )
                    if has_rate_limited:
                        pending_values["rate_limited"] = False
                    conn.execute(
                        sa.update(SystemSchema.workflow_status)
                        .where(SystemSchema.workflow_status.c.workflow_uuid == new_workflow_uuid)
                        .values(**pending_values)
                    )

                    if raw_workflow_input_override is not None:
                        conn.execute(
                            sa.update(SystemSchema.workflow_status)
                            .where(SystemSchema.workflow_status.c.workflow_uuid == new_workflow_uuid)
                            .values(
                                inputs=raw_workflow_input_override,
                                serialization=source_status.get("serialization"),
                                updated_at=current_time_ms,
                            )
                        )
                    elif normalized_input_override is not None:
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
                    for function_id, output_override in normalized_raw_step_overrides.items():
                        if function_id >= start_step:
                            raise ValueError(
                                f"raw_step_output_overrides only supports preserved steps before start_step {start_step}"
                            )
                        patched_step_ids.append(
                            _patch_forked_raw_step_output(
                                conn,
                                source_workflow_id=workflow_id,
                                forked_workflow_id=new_workflow_uuid,
                                function_id=function_id,
                                raw_output_override=output_override,
                            )
                        )

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

                    if has_was_forked_from:
                        conn.execute(
                            sa.update(SystemSchema.workflow_status)
                            .where(SystemSchema.workflow_status.c.workflow_uuid == workflow_id)
                            .values(was_forked_from=True)
                        )
            except Exception:
                # Override application failed AFTER the fork rows were
                # committed. Mark the forked workflow CANCELLED so we don't
                # leave behind a runnable fork without its intended overrides.
                try:
                    with client._sys_db.engine.begin() as cleanup_conn:
                        cleanup_conn.execute(
                            sa.update(SystemSchema.workflow_status)
                            .where(SystemSchema.workflow_status.c.workflow_uuid == new_workflow_uuid)
                            .values(status="CANCELLED", updated_at=utc_now_epoch_ms())
                        )
                except Exception:
                    pass
                raise

            return {
                "new_workflow_id": new_workflow_uuid,
                "stage_mode": "edited_fork",
                "source_workflow_id": workflow_id,
                "workflow_input_override": normalized_input_override,
                "raw_workflow_input_override": raw_workflow_input_override,
                "step_output_overrides": {
                    str(function_id): normalized_step_overrides[function_id]
                    for function_id in sorted(normalized_step_overrides)
                },
                "raw_step_output_overrides": {
                    str(function_id): normalized_raw_step_overrides[function_id]
                    for function_id in sorted(normalized_raw_step_overrides)
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

    async def load_workflow_input_metadata(self, workflow_id: str) -> dict[str, Any] | None:
        if self.system_database_url is None:
            return None
        return await asyncio.to_thread(self._load_workflow_input_metadata_sync, workflow_id)

    def _load_workflow_input_metadata_sync(self, workflow_id: str) -> dict[str, Any] | None:
        if self.system_database_url is None:
            return None

        client = DBOSClient(system_database_url=self.system_database_url)
        try:
            with client._sys_db.engine.begin() as conn:
                row = conn.execute(
                    sa.select(
                        SystemSchema.workflow_status.c.inputs,
                        SystemSchema.workflow_status.c.serialization,
                    )
                    .where(SystemSchema.workflow_status.c.workflow_uuid == workflow_id)
                ).fetchone()
                if row is None:
                    return None
                editor = None
                if row.serialization == DBOS_JSON_NAME and isinstance(row.inputs, str):
                    try:
                        editor = {
                            "mode": "decoded-json",
                            "value": _json_safe_preview(_dbos_json_decode(row.inputs)),
                        }
                    except Exception:
                        editor = None
                elif row.serialization == DBOSPortableJSON.name() and isinstance(row.inputs, str):
                    try:
                        decoded = _deserialize_workflow_args(
                            row.inputs,
                            row.serialization,
                            client._serializer,
                        )
                        editor = {
                            "mode": "portable-args-kwargs",
                            "value": _json_safe_preview(
                                {
                                    "args": list(decoded.get("args") or ()),
                                    "kwargs": dict(decoded.get("kwargs") or {}),
                                }
                            ),
                        }
                    except Exception:
                        editor = None
                elif row.serialization == DBOSDefaultSerializer.name() and isinstance(row.inputs, str):
                    try:
                        decoded = deserialize_args(row.inputs, row.serialization, client._serializer)
                        editor = {
                            "mode": "python-args-kwargs",
                            "value": _json_safe_preview(
                                {
                                    "args": list(decoded.get("args") or ()),
                                    "kwargs": dict(decoded.get("kwargs") or {}),
                                }
                            ),
                        }
                    except Exception:
                        editor = None
                return {
                    "value": row.inputs,
                    "serialization": row.serialization,
                    "editor": editor,
                }
        finally:
            client.destroy()

    async def load_step_output_metadata(self, workflow_id: str) -> dict[int, dict[str, Any]]:
        if self.system_database_url is None:
            return {}
        return await asyncio.to_thread(self._load_step_output_metadata_sync, workflow_id)

    def _load_step_output_metadata_sync(self, workflow_id: str) -> dict[int, dict[str, Any]]:
        if self.system_database_url is None:
            return {}

        client = DBOSClient(system_database_url=self.system_database_url)
        try:
            with client._sys_db.engine.begin() as conn:
                rows = conn.execute(
                    sa.select(
                        SystemSchema.operation_outputs.c.function_id,
                        SystemSchema.operation_outputs.c.output,
                        SystemSchema.operation_outputs.c.serialization,
                    )
                    .where(SystemSchema.operation_outputs.c.workflow_uuid == workflow_id)
                ).fetchall()
                return {
                    int(row.function_id): {
                        "value": row.output,
                        "serialization": row.serialization,
                        "editor": _step_output_editor_metadata(
                            row.output,
                            row.serialization,
                            client._serializer,
                        ),
                    }
                    for row in rows
                }
        finally:
            client.destroy()

    def _cancel_orphan_staged_forks_sync(
        self,
        keep_workflow_id: str,
        executor_id: str,
        application_version: str,
    ) -> list[str]:
        """Cancel any other PENDING staged forks for the same executor/version,
        so the recovery-driven execute path doesn't fail validation. Returns
        the workflow ids that were cancelled."""
        if self.system_database_url is None:
            raise RuntimeError("Control plane system database URL is not configured")

        client = DBOSClient(system_database_url=self.system_database_url)
        try:
            with client._sys_db.engine.begin() as conn:
                rows = conn.execute(
                    sa.select(SystemSchema.workflow_status.c.workflow_uuid)
                    .where(SystemSchema.workflow_status.c.status == "PENDING")
                    .where(SystemSchema.workflow_status.c.executor_id == executor_id)
                    .where(SystemSchema.workflow_status.c.application_version == application_version)
                    .where(SystemSchema.workflow_status.c.queue_name.is_(None))
                    .where(SystemSchema.workflow_status.c.forked_from.is_not(None))
                    .where(SystemSchema.workflow_status.c.workflow_uuid != keep_workflow_id)
                ).fetchall()
                orphan_ids = [row.workflow_uuid for row in rows]
                if orphan_ids:
                    conn.execute(
                        sa.update(SystemSchema.workflow_status)
                        .where(SystemSchema.workflow_status.c.workflow_uuid.in_(orphan_ids))
                        .values(status="CANCELLED", updated_at=utc_now_epoch_ms())
                    )
                return orphan_ids
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
                other_ids = [pid for pid in pending_workflow_ids if pid != workflow_id]
                raise RuntimeError(
                    "Cannot execute staged fork while other pending workflows exist for the same executor/version: "
                    + ", ".join(other_ids)
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
    if serialization == DBOS_JSON_NAME:
        # DBOS_JSON (Go/TS SDK) carries a single positional value, no kwargs,
        # encoded as base64(json.dumps(value)). Honour that contract.
        if kwargs:
            raise RuntimeError(
                "DBOS_JSON workflows do not support keyword arguments; supply the override as {'args': [value]}"
            )
        if len(args) != 1:
            raise RuntimeError(
                "DBOS_JSON workflows expect exactly one positional argument"
            )
        return _dbos_json_encode(args[0]), DBOS_JSON_NAME
    if serialization == JS_SUPERJSON_NAME:
        # TS SDK superjson: {"json": <positional_args_list>,
        # "__dbos_serializer": "superjson"}. No kwargs supported.
        if kwargs:
            raise RuntimeError(
                "js_superjson workflows do not support keyword arguments; supply the override as {'args': [...]}"
            )
        return _js_superjson_encode(list(args)), JS_SUPERJSON_NAME
    if serialization == JAVA_JACKSON_NAME:
        # Java SDK: positional Object[] args, Jackson wrapper-array typed.
        if kwargs:
            raise RuntimeError(
                "java_jackson workflows do not support keyword arguments; supply the override as {'args': [...]}"
            )
        return _java_jackson_encode_args(list(args)), JAVA_JACKSON_NAME
    if serialization is not None and serialization != serializer.name():
        raise RuntimeError(f"Serialization {serialization} is not available")
    return serializer.serialize({"args": args, "kwargs": kwargs}), serializer.name()


def _deserialize_workflow_args(
    serialized_value: str | None,
    serialization: str | None,
    serializer: Any,
) -> dict[str, Any]:
    """Like dbos._serialization.deserialize_args, but also understands the
    DBOS_JSON encoding used by Go/TS executors (single positional arg, no
    kwargs, base64(json.dumps(value)))."""
    if serialization == DBOS_JSON_NAME:
        if serialized_value is None:
            return {"args": (), "kwargs": {}}
        return {"args": (_dbos_json_decode(serialized_value),), "kwargs": {}}
    if serialization == JS_SUPERJSON_NAME:
        if serialized_value is None:
            return {"args": (), "kwargs": {}}
        decoded = _js_superjson_decode(serialized_value)
        if not isinstance(decoded, list):
            raise RuntimeError("js_superjson workflow inputs must encode a JSON array")
        return {"args": tuple(decoded), "kwargs": {}}
    if serialization == JAVA_JACKSON_NAME:
        if serialized_value is None:
            return {"args": (), "kwargs": {}}
        decoded = _java_jackson_decode(serialized_value)
        if not isinstance(decoded, list):
            raise RuntimeError("java_jackson workflow inputs must encode a JSON array")
        return {"args": tuple(decoded), "kwargs": {}}
    return deserialize_args(serialized_value, serialization, serializer)


def _deserialize_step_value(
    serialized_value: str | None,
    serialization: str | None,
    serializer: Any,
) -> Any:
    if serialization is None:
        if serialized_value is None:
            return None
        try:
            return json.loads(serialized_value)
        except (TypeError, ValueError):
            try:
                return ast.literal_eval(serialized_value)
            except (ValueError, SyntaxError):
                return serialized_value
    if serialization == DBOS_JSON_NAME:
        if serialized_value is None:
            return None
        return _dbos_json_decode(serialized_value)
    if serialization == JS_SUPERJSON_NAME:
        if serialized_value is None:
            return None
        return _js_superjson_decode(serialized_value)
    if serialization == JAVA_JACKSON_NAME:
        if serialized_value is None:
            return None
        return _java_jackson_decode(serialized_value)
    return deserialize_value(serialized_value, serialization, serializer)


def _serialize_step_value_as(
    value: Any,
    serialization: str | None,
    serializer: Any,
) -> tuple[str | None, str]:
    if serialization is None:
        return json.dumps(value), None
    if serialization == DBOS_JSON_NAME:
        return _dbos_json_encode(value), DBOS_JSON_NAME
    if serialization == JS_SUPERJSON_NAME:
        return _js_superjson_encode(value), JS_SUPERJSON_NAME
    if serialization == JAVA_JACKSON_NAME:
        return _java_jackson_encode_value(value), JAVA_JACKSON_NAME
    return serialize_value_as(value, serialization, serializer)


def _build_workflow_input_override(
    source_status: dict[str, Any],
    workflow_input_override: dict[str, Any],
    serializer: Any,
) -> tuple[str, str]:
    workflow_inputs = _deserialize_workflow_args(
        source_status["inputs"],
        source_status.get("serialization"),
        serializer,
    )
    # Accept either the explicit {args, kwargs} shape (cross-language safe)
    # or, for back-compat, treat any other dict as kwargs-only with the
    # source workflow's positional args preserved.
    if (
        isinstance(workflow_input_override, dict)
        and ("args" in workflow_input_override or "kwargs" in workflow_input_override)
    ):
        raw_args = workflow_input_override.get("args") or []
        raw_kwargs = workflow_input_override.get("kwargs") or {}
        if not isinstance(raw_args, (list, tuple)):
            raise RuntimeError("workflow_input_override.args must be a JSON array")
        if not isinstance(raw_kwargs, dict):
            raise RuntimeError("workflow_input_override.kwargs must be a JSON object")
        args = tuple(raw_args)
        kwargs = dict(raw_kwargs)
    else:
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

    original_value = _deserialize_step_value(step_row.output, step_row.serialization, serializer)
    coerced_override = _coerce_override_like(original_value, output_override)
    if type(coerced_override) is not type(original_value):
        raise ValueError(
            f"Step {function_id} override type {type(output_override).__name__} does not match recorded output type {type(original_value).__name__}"
        )

    serialized_output, serialization = _serialize_step_value_as(
        coerced_override,
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


def _patch_forked_raw_step_output(
    conn: sa.Connection,
    *,
    source_workflow_id: str,
    forked_workflow_id: str,
    function_id: int,
    raw_output_override: str,
) -> int:
    step_row = conn.execute(
        sa.select(
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

    update_result = conn.execute(
        sa.update(SystemSchema.operation_outputs)
        .where(SystemSchema.operation_outputs.c.workflow_uuid == forked_workflow_id)
        .where(SystemSchema.operation_outputs.c.function_id == function_id)
        .values(
            output=raw_output_override,
            error=None,
            serialization=step_row.serialization,
        )
    )
    if update_result.rowcount != 1:
        raise LookupError(
            f"Forked workflow is missing preserved step output for function_id {function_id}"
        )
    return function_id


def _step_output_editor_metadata(
    serialized_value: str | None,
    serialization: str | None,
    serializer: Any,
) -> dict[str, Any] | None:
    if serialized_value is None:
        return None
    if serialization == DBOS_JSON_NAME:
        try:
            return {
                "mode": "decoded-json",
                "value": _json_safe_preview(_dbos_json_decode(serialized_value)),
            }
        except Exception:
            return None
    if serialization == DBOSPortableJSON.name():
        try:
            return {
                "mode": "portable-value",
                "value": _json_safe_preview(
                    deserialize_value(serialized_value, serialization, serializer)
                ),
            }
        except Exception:
            return None
    if serialization == DBOSDefaultSerializer.name():
        try:
            decoded = deserialize_value(serialized_value, serialization, serializer)
            return {
                "mode": "python-value",
                "value": _json_safe_preview(decoded),
            }
        except Exception:
            return None
    return None


def _fork_workflow_compat(
    conn: sa.Connection,
    *,
    original_workflow_id: str,
    forked_workflow_id: str,
    start_step: int,
    application_version: str,
    source_status: dict[str, Any],
    has_was_forked_from: bool,
) -> None:
    """Schema-aware reimplementation of dbos._sys_db.fork_workflow for the
    single-workflow case the control plane needs. Mirrors the SDK's behaviour
    (insert a new ENQUEUED row that copies the source's identity columns,
    optionally mark the source as `was_forked_from=True`, and copy preserved
    step checkpoints/events/streams when start_step > 1) but skips writes to
    columns that may not exist on the target schema (the Go and TypeScript
    DBOS SDKs do not provision `was_forked_from`).

    Source identity is taken from ``source_status`` (the dict returned by
    ``SystemDatabase.get_workflow_status``) to avoid a redundant SELECT — the
    caller has already fetched it for its own validation.
    """
    cols = SystemSchema.workflow_status.c
    conn.execute(
        sa.insert(SystemSchema.workflow_status).values(
            workflow_uuid=forked_workflow_id,
            status=WorkflowStatusString.ENQUEUED.value,
            name=source_status.get("name"),
            class_name=source_status.get("class_name"),
            config_name=source_status.get("config_name"),
            application_version=application_version,
            application_id=source_status.get("app_id"),
            authenticated_user=source_status.get("authenticated_user"),
            authenticated_roles=source_status.get("authenticated_roles"),
            serialization=source_status.get("serialization"),
            queue_name=INTERNAL_QUEUE_NAME,
            inputs=source_status.get("inputs"),
            assumed_role=source_status.get("assumed_role"),
            forked_from=original_workflow_id,
        )
    )

    if has_was_forked_from:
        conn.execute(
            sa.update(SystemSchema.workflow_status)
            .where(cols.workflow_uuid == original_workflow_id)
            .values(was_forked_from=True)
        )

    if start_step > 0:
        oo = SystemSchema.operation_outputs
        conn.execute(
            sa.insert(oo).from_select(
                [
                    "workflow_uuid",
                    "function_id",
                    "output",
                    "error",
                    "serialization",
                    "function_name",
                    "child_workflow_id",
                    "started_at_epoch_ms",
                    "completed_at_epoch_ms",
                ],
                sa.select(
                    sa.literal(forked_workflow_id).label("workflow_uuid"),
                    oo.c.function_id,
                    oo.c.output,
                    oo.c.error,
                    oo.c.serialization,
                    oo.c.function_name,
                    oo.c.child_workflow_id,
                    oo.c.started_at_epoch_ms,
                    oo.c.completed_at_epoch_ms,
                ).where(oo.c.workflow_uuid == original_workflow_id)
                 .where(oo.c.function_id < start_step),
            )
        )

        weh = SystemSchema.workflow_events_history
        conn.execute(
            sa.insert(weh).from_select(
                ["workflow_uuid", "function_id", "key", "value", "serialization"],
                sa.select(
                    sa.literal(forked_workflow_id).label("workflow_uuid"),
                    weh.c.function_id,
                    weh.c.key,
                    weh.c.value,
                    weh.c.serialization,
                ).where(weh.c.workflow_uuid == original_workflow_id)
                 .where(weh.c.function_id < start_step),
            )
        )

        ranked = (
            sa.select(
                sa.literal(forked_workflow_id).label("workflow_uuid"),
                weh.c.key,
                weh.c.value,
                weh.c.serialization,
                sa.func.row_number()
                .over(
                    partition_by=[weh.c.workflow_uuid, weh.c.key],
                    order_by=weh.c.function_id.desc(),
                )
                .label("rn"),
            )
            .where(weh.c.workflow_uuid == original_workflow_id)
            .where(weh.c.function_id < start_step)
        ).subquery("ranked")
        conn.execute(
            sa.insert(SystemSchema.workflow_events).from_select(
                ["workflow_uuid", "key", "value", "serialization"],
                sa.select(
                    ranked.c.workflow_uuid,
                    ranked.c.key,
                    ranked.c.value,
                    ranked.c.serialization,
                ).where(ranked.c.rn == 1),
            )
        )

        streams = SystemSchema.streams
        conn.execute(
            sa.insert(streams).from_select(
                ["workflow_uuid", "function_id", "key", "value", "serialization", "offset"],
                sa.select(
                    sa.literal(forked_workflow_id).label("workflow_uuid"),
                    streams.c.function_id,
                    streams.c.key,
                    streams.c.value,
                    streams.c.serialization,
                    streams.c.offset,
                ).where(streams.c.workflow_uuid == original_workflow_id)
                 .where(streams.c.function_id < start_step),
            )
        )

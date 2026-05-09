from __future__ import annotations

import ast
import binascii
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .state import (
    JAVA_OBJECT_ARRAY_TYPE,
    _dbos_json_decode,
    _java_jackson_decode,
    _js_superjson_decode,
)

STATIC_DIR = Path(__file__).with_name("static")

# A pure-base64 token (no JSON delimiters). Used to distinguish Go's DBOS_JSON
# wire format (base64(json.dumps(value))) from JSON or Python-repr inputs.
_BASE64_ONLY_RE = re.compile(r"^[A-Za-z0-9+/]+=*$")


def _validate_input_override(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="input_override must be a JSON object")
    return value


def _validate_step_output_overrides(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=400,
            detail="step_output_overrides must be a JSON object keyed by step id",
        )
    return value


def _validate_raw_input_override(value: Any) -> str:
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="raw_workflow_input_override must be a string")
    return value


def _validate_raw_step_output_overrides(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=400,
            detail="raw_step_output_overrides must be a JSON object keyed by step id",
        )
    validated: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, str):
            raise HTTPException(
                status_code=400,
                detail="raw_step_output_overrides values must be strings",
            )
        validated[str(key)] = item
    return validated


def _derive_input_override_seed(workflow_output: Any) -> dict[str, Any] | None:
    """Derive an editable input seed from a workflow's recorded Input.

    DBOS apps in different languages serialize workflow inputs differently
    over the conductor protocol:
      - Python (pickle):    "{'args': (...), 'kwargs': {...}}" (Python repr
                            of the deserialized dict).
      - Portable JSON:      '{"positionalArgs": [...], "namedArgs": {...}}'.
      - Plain JSON kwargs:  '{"name": "x"}' (legacy / direct dict).
      - Java (java_jackson):'["[Ljava.lang.Object;", [<args>...]]'
                            (Jackson WRAPPER_ARRAY polymorphic typing).
      - TypeScript (js_superjson):
                            '{"json": [<args>...], "__dbos_serializer": "superjson"}'
                            for complex types; or a JS-style single-quoted
                            array string like "[ 'bob' ]" when the executor
                            forwards util.inspect-ed values. The latter is
                            recovered via ast.literal_eval.
      - Go (DBOS_JSON):     either base64(json.dumps(value)) when the raw
                            DB column is forwarded, or the JSON-decoded form
                            of that value when the executor pre-deserializes
                            (e.g. '"bob"' for a single string arg, or '42'
                            for a single number arg).

    This function normalizes any of those into the editable shape
    {"args": [...], "kwargs": {...}} so the UI can edit both positional and
    named arguments regardless of the source language.
    """
    if not isinstance(workflow_output, dict):
        return None

    raw_input = workflow_output.get("Input")
    if not isinstance(raw_input, str) or not raw_input.strip():
        return None

    stripped = raw_input.strip()

    # Go DBOS_JSON: pure-base64 string. Detect first because base64 tokens
    # never contain JSON or Python-repr delimiters, but may incidentally
    # parse as JSON scalars (e.g. "12345").
    if _BASE64_ONLY_RE.fullmatch(stripped) and len(stripped) % 4 == 0:
        try:
            decoded = _dbos_json_decode(stripped)
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError):
            decoded = None
        if decoded is not None:
            # DBOS_JSON encodes a single positional value (Go workflows take
            # one input arg). Wrap it as args=[value] for the editor.
            return {"args": [decoded], "kwargs": {}}

    # Try JSON next (TS / Java / portable JSON / plain dicts / scalars).
    parsed_input: Any = None
    try:
        parsed_input = json.loads(stripped)
    except (ValueError, TypeError):
        # Fall back to Python literal_eval (Python pickle->repr round-trip).
        try:
            parsed_input = ast.literal_eval(stripped)
        except (ValueError, SyntaxError):
            return None

    # Java java_jackson: top-level wrapper array ["[Ljava.lang.Object;", [...]]
    if (
        isinstance(parsed_input, list)
        and len(parsed_input) == 2
        and isinstance(parsed_input[0], str)
        and (
            parsed_input[0] == JAVA_OBJECT_ARRAY_TYPE
            or parsed_input[0].startswith("[L")  # Jackson Object[] tag form
        )
    ):
        try:
            decoded = _java_jackson_decode(stripped)
        except (ValueError, TypeError, json.JSONDecodeError):
            decoded = None
        if isinstance(decoded, list):
            return {"args": list(decoded), "kwargs": {}}

    if isinstance(parsed_input, dict):
        # TypeScript js_superjson: {"json": [args], "__dbos_serializer": "superjson"}
        if parsed_input.get("__dbos_serializer") == "superjson":
            try:
                decoded = _js_superjson_decode(stripped)
            except (ValueError, TypeError, RuntimeError, json.JSONDecodeError):
                return None
            if isinstance(decoded, list):
                return {"args": list(decoded), "kwargs": {}}
            # Defensive: superjson payload that isn't a list — single arg.
            return {"args": [decoded], "kwargs": {}}

        # Portable JSON shape (cross-language)
        if "positionalArgs" in parsed_input or "namedArgs" in parsed_input:
            args = parsed_input.get("positionalArgs") or []
            kwargs = parsed_input.get("namedArgs") or {}
            if isinstance(args, (list, tuple)) and isinstance(kwargs, dict):
                return {"args": list(args), "kwargs": kwargs}

        # Python pickle-deserialized shape
        if "args" in parsed_input or "kwargs" in parsed_input:
            args = parsed_input.get("args") or []
            kwargs = parsed_input.get("kwargs") or {}
            if isinstance(args, (list, tuple)) and isinstance(kwargs, dict):
                return {"args": list(args), "kwargs": kwargs}

        # Legacy: treat the whole dict as kwargs.
        return {"args": [], "kwargs": parsed_input}

    # Bare JSON array of positional args (no Java wrapper).
    if isinstance(parsed_input, list):
        return {"args": list(parsed_input), "kwargs": {}}

    # JSON scalar — Go executors that pre-deserialize DBOS_JSON before
    # forwarding return the raw value (e.g. '"bob"', '42', 'true', 'null').
    # Treat as a single positional arg.
    if parsed_input is None or isinstance(parsed_input, (str, int, float, bool)):
        return {"args": [parsed_input], "kwargs": {}}

    return None

router = APIRouter()


@router.get("/")
async def ui_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/api/control-plane/state")
async def get_state(request: Request) -> dict[str, Any]:
    return await request.app.state.conductor_manager.snapshot()


@router.post("/api/control-plane/list-workflows")
async def list_workflows(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        record = await request.app.state.conductor_manager.send_list_workflows(
            (payload or {}).get("body", {})
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
    }


@router.post("/api/control-plane/list-queued-workflows")
async def list_queued_workflows(
    request: Request, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    try:
        record = await request.app.state.conductor_manager.send_list_queued_workflows(
            (payload or {}).get("body", {})
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
    }


@router.post("/api/control-plane/get-workflow")
async def get_workflow(
    request: Request, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = payload or {}
    workflow_id = data.get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=400, detail="workflow_id is required")
    try:
        record = await request.app.state.conductor_manager.send_get_workflow(
            workflow_id,
            load_input=data.get("load_input", True),
            load_output=data.get("load_output", True),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    workflow_input_seed = _derive_input_override_seed(record.response_payload.get("output"))
    raw_input_metadata = await request.app.state.conductor_manager.load_workflow_input_metadata(workflow_id)
    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
        "workflow_input_seed": workflow_input_seed,
        "raw_workflow_input": raw_input_metadata,
    }


@router.post("/api/control-plane/list-steps")
async def list_steps(
    request: Request, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = payload or {}
    workflow_id = data.get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=400, detail="workflow_id is required")
    try:
        record = await request.app.state.conductor_manager.send_list_steps(
            workflow_id,
            load_output=data.get("load_output", True),
            limit=data.get("limit"),
            offset=data.get("offset"),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raw_step_outputs = await request.app.state.conductor_manager.load_step_output_metadata(workflow_id)
    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
        "raw_step_outputs": raw_step_outputs,
    }


@router.post("/api/control-plane/recovery")
async def recovery(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    executor_ids = (payload or {}).get("executor_ids") or []
    try:
        record = await request.app.state.conductor_manager.send_recovery(executor_ids)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
    }


@router.post("/api/control-plane/cancel")
async def cancel_workflow(
    request: Request, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    workflow_id = (payload or {}).get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=400, detail="workflow_id is required")
    try:
        record = await request.app.state.conductor_manager.send_cancel(workflow_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
    }


@router.post("/api/control-plane/resume")
async def resume_workflow(
    request: Request, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = payload or {}
    workflow_id = data.get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=400, detail="workflow_id is required")
    try:
        record = await request.app.state.conductor_manager.send_resume(
            workflow_id, queue_name=data.get("queue_name")
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
    }


@router.post("/api/control-plane/restart")
async def restart_workflow(
    request: Request, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    workflow_id = (payload or {}).get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=400, detail="workflow_id is required")
    try:
        record = await request.app.state.conductor_manager.send_restart(workflow_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
    }


@router.post("/api/control-plane/execute-staged-fork")
async def execute_staged_fork(
    request: Request, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    workflow_id = (payload or {}).get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=400, detail="workflow_id is required")
    try:
        record = await request.app.state.conductor_manager.execute_staged_fork(workflow_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
    }


@router.post("/api/control-plane/fork")
async def fork_workflow(
    request: Request, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = payload or {}
    workflow_id = data.get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=400, detail="workflow_id is required")
    start_step = data.get("start_step")
    if start_step is None:
        raise HTTPException(status_code=400, detail="start_step is required")

    try:
        parsed_start_step = int(start_step)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="start_step must be an integer") from exc

    workflow_input_override = data.get("workflow_input_override")
    if workflow_input_override is None and "input_override" in data:
        workflow_input_override = data.get("input_override")
    raw_workflow_input_override = data.get("raw_workflow_input_override")
    step_output_overrides = data.get("step_output_overrides")
    raw_step_output_overrides = data.get("raw_step_output_overrides")

    if (
        workflow_input_override is not None
        or raw_workflow_input_override is not None
        or step_output_overrides is not None
        or raw_step_output_overrides is not None
    ):
        mode = data.get("mode", "stage")
        if mode not in ("stage", "run"):
            raise HTTPException(status_code=400, detail="mode must be 'stage' or 'run'")
        manager = request.app.state.conductor_manager
        method = manager.run_edited_fork if mode == "run" else manager.stage_edited_fork
        try:
            record = await method(
                workflow_id,
                parsed_start_step,
                workflow_input_override=(
                    _validate_input_override(workflow_input_override)
                    if workflow_input_override is not None
                    else None
                ),
                raw_workflow_input_override=(
                    _validate_raw_input_override(raw_workflow_input_override)
                    if raw_workflow_input_override is not None
                    else None
                ),
                step_output_overrides=(
                    _validate_step_output_overrides(step_output_overrides)
                    if step_output_overrides is not None
                    else None
                ),
                raw_step_output_overrides=(
                    _validate_raw_step_output_overrides(raw_step_output_overrides)
                    if raw_step_output_overrides is not None
                    else None
                ),
                new_workflow_id=data.get("new_workflow_id") or None,
                cancel_original_if_active=bool(data.get("cancel_original_if_active", False)),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "request_id": record.request_id,
            "status": record.status,
            "response": record.response_payload,
        }

    try:
        record = await request.app.state.conductor_manager.send_fork_workflow(
            workflow_id,
            parsed_start_step,
            new_workflow_id=data.get("new_workflow_id") or None,
            application_version=data.get("application_version") or None,
            queue_name=data.get("queue_name") or None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
    }

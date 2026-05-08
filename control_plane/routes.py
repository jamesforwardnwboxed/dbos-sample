from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).with_name("static")


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


def _derive_input_override_seed(workflow_output: Any) -> dict[str, Any] | None:
    if not isinstance(workflow_output, dict):
        return None

    raw_input = workflow_output.get("Input")
    if not isinstance(raw_input, str) or not raw_input.strip():
        return None

    try:
        parsed_input = ast.literal_eval(raw_input)
    except (ValueError, SyntaxError):
        return None

    if not isinstance(parsed_input, dict):
        return None

    kwargs = parsed_input.get("kwargs")
    if isinstance(kwargs, dict):
        return kwargs

    return parsed_input

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
    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
        "workflow_input_seed": workflow_input_seed,
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
    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
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
    step_output_overrides = data.get("step_output_overrides")

    if workflow_input_override is not None or step_output_overrides is not None:
        try:
            record = await request.app.state.conductor_manager.stage_edited_fork(
                workflow_id,
                parsed_start_step,
                workflow_input_override=(
                    _validate_input_override(workflow_input_override)
                    if workflow_input_override is not None
                    else None
                ),
                step_output_overrides=(
                    _validate_step_output_overrides(step_output_overrides)
                    if step_output_overrides is not None
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

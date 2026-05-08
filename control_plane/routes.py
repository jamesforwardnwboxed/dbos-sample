from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).with_name("static")

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
    return {
        "request_id": record.request_id,
        "status": record.status,
        "response": record.response_payload,
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

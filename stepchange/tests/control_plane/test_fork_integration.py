"""End-to-end regression tests for the edited-fork flow.

These hit a live control plane + DBOS executor + Postgres stack. They are
skipped unless CONTROL_PLANE_URL is set, e.g.::

    CONTROL_PLANE_URL=http://localhost:8001 .venv/bin/pytest \
        tests/control_plane/test_fork_integration.py -v

Run `docker compose up -d` first so the app, control-plane, and postgres
services are reachable.
"""
from __future__ import annotations

import os
import time

import httpx
import pytest


CONTROL_PLANE_URL = os.environ.get("CONTROL_PLANE_URL")

pytestmark = pytest.mark.skipif(
    not CONTROL_PLANE_URL,
    reason="CONTROL_PLANE_URL not set; integration test requires running stack",
)


def _post(client: httpx.Client, path: str, body: dict) -> httpx.Response:
    return client.post(path, json=body)


def _wait_for_status(client: httpx.Client, workflow_id: str, target_status: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    last_payload: dict = {}
    while time.time() < deadline:
        res = _post(client, "/api/control-plane/get-workflow", {"workflow_id": workflow_id})
        if res.status_code == 200:
            output = (res.json().get("response") or {}).get("output") or {}
            last_payload = output
            if output.get("Status") == target_status:
                return output
        time.sleep(0.5)
    raise AssertionError(f"workflow {workflow_id} never reached {target_status}; last={last_payload}")


def _trigger_source_workflow(name: str = "shrek") -> str:
    """Trigger the demo workflow via its FastAPI route and return the new wf id."""
    app_url = os.environ.get("APP_URL", "http://localhost:8000")
    with httpx.Client(base_url=app_url, timeout=10.0) as client:
        client.get(f"/?name={name}")
    # Find the most recently created SUCCESS workflow with this input.
    with httpx.Client(base_url=CONTROL_PLANE_URL, timeout=10.0) as client:
        for _ in range(20):
            res = _post(client, "/api/control-plane/list-workflows", {})
            if res.status_code == 200:
                workflows = (res.json().get("response") or {}).get("output") or []
                for wf in workflows:
                    inputs = wf.get("Input") or ""
                    if name in inputs and wf.get("Status") == "SUCCESS":
                        return wf["WorkflowUUID"]
            time.sleep(0.5)
    raise AssertionError(f"Could not find a SUCCESS workflow with input containing {name!r}")


def test_run_edited_fork_applies_input_override() -> None:
    """Submit an edited fork in 'run' mode and verify the new workflow ran
    with the override applied."""
    source_id = _trigger_source_workflow("shrek")
    override_name = f"James-{int(time.time())}"

    with httpx.Client(base_url=CONTROL_PLANE_URL, timeout=15.0) as client:
        res = _post(
            client,
            "/api/control-plane/fork",
            {
                "workflow_id": source_id,
                "start_step": 0,
                "mode": "run",
                "workflow_input_override": {"name": override_name},
                "cancel_original_if_active": False,
            },
        )
        assert res.status_code == 200, f"fork failed: {res.status_code} {res.text}"
        body = res.json()
        assert body["status"] == "succeeded"
        new_id = body["response"]["new_workflow_id"]
        assert body["response"]["workflow_input_override"] == {"name": override_name}
        assert body["response"]["execution_requested"] is True

        forked = _wait_for_status(client, new_id, "SUCCESS", timeout=20.0)
        # The recorded Input must reflect the override, not the source.
        assert override_name in (forked.get("Input") or ""), forked


def test_run_edited_fork_cancels_orphan_staged_forks() -> None:
    """Stage one fork (which leaves PENDING orphan), then run another - the
    second should auto-cancel the orphan and execute successfully."""
    source_id = _trigger_source_workflow("shrek")

    with httpx.Client(base_url=CONTROL_PLANE_URL, timeout=15.0) as client:
        # Stage first (leaves PENDING orphan).
        stage_res = _post(
            client,
            "/api/control-plane/fork",
            {
                "workflow_id": source_id,
                "start_step": 0,
                "mode": "stage",
                "workflow_input_override": {"name": "orphan-stage"},
                "cancel_original_if_active": False,
            },
        )
        assert stage_res.status_code == 200, stage_res.text
        orphan_id = stage_res.json()["response"]["new_workflow_id"]

        # Now run another edited fork - should auto-clear orphan and succeed.
        run_res = _post(
            client,
            "/api/control-plane/fork",
            {
                "workflow_id": source_id,
                "start_step": 0,
                "mode": "run",
                "workflow_input_override": {"name": "post-orphan"},
                "cancel_original_if_active": False,
            },
        )
        assert run_res.status_code == 200, f"expected 200, got {run_res.status_code}: {run_res.text}"
        body = run_res.json()
        assert body["status"] == "succeeded"
        assert orphan_id in body["response"].get("cancelled_orphan_staged_forks", []), body["response"]

        new_id = body["response"]["new_workflow_id"]
        forked = _wait_for_status(client, new_id, "SUCCESS", timeout=20.0)
        assert "post-orphan" in (forked.get("Input") or ""), forked

        # Orphan should be CANCELLED.
        orphan_status = _wait_for_status(client, orphan_id, "CANCELLED", timeout=10.0)
        assert orphan_status["Status"] == "CANCELLED"

from __future__ import annotations

import asyncio
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from control_plane import protocol
from conftest import create_control_plane_client


def wait_for_ready_snapshot(client, timeout: float = 1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snapshot = asyncio.run(client.app.state.conductor_manager.snapshot())
        if snapshot["session"] is not None and snapshot["session"]["status"] == "ready":
            return snapshot
        time.sleep(0.01)
    return asyncio.run(client.app.state.conductor_manager.snapshot())


def test_websocket_sends_executor_info_first() -> None:
    with create_control_plane_client() as client:
        with client.websocket_connect("/websocket/dbos-starter/local-conductor-key") as websocket:
            first_message = websocket.receive_text()
            request = protocol.parse_base_message(first_message)

            assert request.type == protocol.MessageType.EXECUTOR_INFO

            websocket.send_text(
                protocol.ExecutorInfoResponse(
                    type=protocol.MessageType.EXECUTOR_INFO,
                    request_id=request.request_id,
                    executor_id="executor-1",
                    application_version="v1",
                    hostname="localhost",
                    language="python",
                    dbos_version="1.0.0",
                ).to_json()
            )

            snapshot = wait_for_ready_snapshot(client)

            assert snapshot["session"]["status"] == "ready"
            assert snapshot["session"]["executor_info"]["executor_id"] == "executor-1"


def test_websocket_rejects_wrong_key() -> None:
    with create_control_plane_client() as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/websocket/dbos-starter/wrong-key"):
                pass

        assert exc_info.value.code == 1008

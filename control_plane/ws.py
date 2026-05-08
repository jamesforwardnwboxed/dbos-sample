from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from . import protocol

router = APIRouter()


@router.websocket("/websocket/{app_name}/{conductor_key}")
async def conductor_websocket(websocket: WebSocket, app_name: str, conductor_key: str) -> None:
    manager = websocket.app.state.conductor_manager
    if app_name != manager.app_name or conductor_key != manager.conductor_key:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await manager.register_connection(websocket, app_name, conductor_key)

    try:
        _session, request_id = await manager.begin_handshake()
        await websocket.send_text(protocol.build_executor_info_request(request_id).to_json())

        while True:
            message = await websocket.receive_text()
            await manager.complete_request_from_message(message)
    except WebSocketDisconnect:
        await manager.disconnect()
    except Exception:
        await manager.disconnect()
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)

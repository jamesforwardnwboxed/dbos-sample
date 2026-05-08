from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane.app import create_app
from control_plane.config import ControlPlaneConfig


def create_control_plane_app():
    return create_app(
        ControlPlaneConfig(
            app_name="dbos-starter",
            conductor_key="local-conductor-key",
            request_timeout_seconds=1.0,
        )
    )


def create_control_plane_client() -> TestClient:
    app = create_control_plane_app()
    return TestClient(app)

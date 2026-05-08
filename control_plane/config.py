from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ControlPlaneConfig:
    app_name: str = "dbos-starter"
    conductor_key: str = "local-conductor-key"
    system_database_url: str = "postgres://postgres:dbos@postgres:5432/dbos_starter"
    host: str = "0.0.0.0"
    port: int = 8001
    request_timeout_seconds: float = 5.0


def load_config() -> ControlPlaneConfig:
    return ControlPlaneConfig(
        app_name=os.environ.get("CONTROL_PLANE_APP_NAME", "dbos-starter"),
        conductor_key=os.environ.get("CONTROL_PLANE_CONDUCTOR_KEY", "local-conductor-key"),
        system_database_url=os.environ.get(
            "CONTROL_PLANE_SYSTEM_DATABASE_URL",
            os.environ.get("DBOS_SYSTEM_DATABASE_URL", "postgres://postgres:dbos@postgres:5432/dbos_starter"),
        ),
        host=os.environ.get("CONTROL_PLANE_HOST", "0.0.0.0"),
        port=int(os.environ.get("CONTROL_PLANE_PORT", "8001")),
        request_timeout_seconds=float(
            os.environ.get("CONTROL_PLANE_REQUEST_TIMEOUT_SECONDS", "5.0")
        ),
    )

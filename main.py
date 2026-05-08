import os

import uvicorn
from dbos import DBOS

from app_runtime import app, build_dbos_config, configure_logging


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

if __name__ == "__main__":
    configure_logging()
    DBOS(config=build_dbos_config())
    DBOS.launch()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=os.environ.get("APP_LOG_LEVEL", "warning").lower(),
        access_log=_env_flag("APP_ACCESS_LOG", False),
    )

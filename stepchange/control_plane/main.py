import uvicorn

from .app import create_app
from .config import load_config


if __name__ == "__main__":
    config = load_config()
    uvicorn.run(
        create_app(config),
        host=config.host,
        port=config.port,
        log_level=config.log_level,
        access_log=config.access_log,
    )

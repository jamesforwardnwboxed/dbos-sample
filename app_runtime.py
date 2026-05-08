import logging
import os
from typing import Any

from dbos import DBOS, DBOSConfig
from fastapi import FastAPI

app = FastAPI()
logger = logging.getLogger("dbos_starter")


@DBOS.step()
def step_one(name: str) -> int:
    logger.info("Hello %s", name)
    logger.info("Step one completed")
    return len(name)


@DBOS.step()
def step_two(name: str, name_length: int) -> None:
    logger.info("Step two completed for %s; the name has %d characters.", name, name_length)


def configure_logging() -> None:
    level_name = os.environ.get("APP_LOG_LEVEL", "info").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s", force=True)


def get_existing_file_path() -> str:
    return os.path.join(os.path.dirname(__file__), "existing.txt")


def run_workflow_logic(name: str = "world") -> None:
    logger.info("Starting workflow for %s", name)
    name_length = step_one(name)
    existing_file = get_existing_file_path()
    if not os.path.exists(existing_file):
        logger.warning("existing.txt missing; creating it and exiting to simulate a crash")
        with open(existing_file, "w"):
            pass
        os._exit(1)
    step_two(name, name_length)
    logger.info("Completed workflow for %s", name)


@app.get("/")
@DBOS.workflow()
def dbos_workflow(name: str = "world") -> Any:
    return run_workflow_logic(name)


def build_dbos_config() -> DBOSConfig:
    return {
        "name": os.environ.get("DBOS_APP_NAME", "dbos-starter"),
        "system_database_url": os.environ.get("DBOS_SYSTEM_DATABASE_URL"),
        "conductor_url": os.environ.get("DBOS_CONDUCTOR_URL"),
        "conductor_key": os.environ.get("DBOS_CONDUCTOR_KEY"),
    }

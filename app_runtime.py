import os
from typing import Any

from dbos import DBOS, DBOSConfig
from fastapi import FastAPI

app = FastAPI()


@DBOS.step()
def step_one(name: str) -> int:
    print(f"Hello {name}")
    print("Step one completed!")
    return len(name)


@DBOS.step()
def step_two(name: str, name_length: int) -> None:
    print(f"Step two completed for {name}; the name has {name_length} characters.")


def get_existing_file_path() -> str:
    return os.path.join(os.path.dirname(__file__), "existing.txt")


def run_workflow_logic(name: str = "world") -> None:
    name_length = step_one(name)
    existing_file = get_existing_file_path()
    if not os.path.exists(existing_file):
        with open(existing_file, "w"):
            pass
        os._exit(1)
    step_two(name, name_length)


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

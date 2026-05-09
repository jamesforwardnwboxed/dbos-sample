import logging
import os
from dataclasses import dataclass
from typing import Any

from dbos import DBOS, DBOSConfig, WorkflowSerializationFormat
from fastapi import FastAPI

app = FastAPI()
logger = logging.getLogger("dbos_starter")


@dataclass
class WorkflowInput:
    name: str
    aliases: list[str]
    weights: dict[str, int]


@dataclass
class StepOneResult:
    greeting: str
    name_length: int
    metrics: dict[str, int]


@DBOS.step()
def step_one(input_data: WorkflowInput) -> StepOneResult:
    logger.info("Hello %s", input_data.name)
    logger.info("Step one completed")
    return StepOneResult(
        greeting=f"Hello {input_data.name}",
        name_length=len(input_data.name),
        metrics={
            "name_length": len(input_data.name),
            "alias_count": len(input_data.aliases),
            "weight_count": len(input_data.weights),
        },
    )


@DBOS.step()
def step_two(input_data: WorkflowInput, step_one_result: StepOneResult) -> None:
    logger.info(
        "Step two completed for %s; the name has %d characters.",
        input_data.name,
        step_one_result.name_length,
    )


def configure_logging() -> None:
    level_name = os.environ.get("APP_LOG_LEVEL", "info").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s", force=True)


def build_workflow_input(name: str = "world") -> WorkflowInput:
    return WorkflowInput(
        name=name,
        aliases=[name.upper(), name[::-1]],
        weights={"primary": len(name), "secondary": max(1, len(name) // 2)},
    )


def run_workflow_logic(name: str = "world") -> None:
    workflow_input = build_workflow_input(name)
    logger.info("Starting workflow for %s", workflow_input.name)
    step_one_result = step_one(workflow_input)
    if workflow_input.name == "poison":
        logger.warning("poison input received; exiting to simulate a crash")
        raise SystemExit(1)
    step_two(workflow_input, step_one_result)
    logger.info("Completed workflow for %s", workflow_input.name)


@app.get("/")
@DBOS.workflow(serialization_type=WorkflowSerializationFormat.PORTABLE)
def dbos_workflow(name: str = "world") -> Any:
    return run_workflow_logic(name)


def build_dbos_config() -> DBOSConfig:
    return {
        "name": os.environ.get("DBOS_APP_NAME", "dbos-starter"),
        "system_database_url": os.environ.get("DBOS_SYSTEM_DATABASE_URL"),
        "conductor_url": os.environ.get("DBOS_CONDUCTOR_URL"),
        "conductor_key": os.environ.get("DBOS_CONDUCTOR_KEY"),
    }

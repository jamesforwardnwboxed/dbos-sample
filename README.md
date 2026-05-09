# StepChange Sample Apps

This repository contains sample applications for DBOS in multiple languages (Go, TypeScript, Python, and Java), alongside the `StepChange` control plane service used by them.

## What It Does

Each language directory (`go`, `typescript`, `python`, `java`) contains a complete, containerized sample application that uses the DBOS SDK to run durable workflows. These applications are designed to demonstrate:

- Durable workflow execution with automatic checkpointing and recovery.
- Integration with the `StepChange` control plane for operator actions (recovery, cancel, resume, restart, fork) and monitoring via a browser dashboard.
- Cross-language interoperability through shared serialization formats.

## StepChange Features

The `StepChange` service acts as a conductor bridge between DBOS executors and an operator UI/API. It provides:

### Dashboard and Request Log
The UI at `GET /` is a static single-page app served directly by FastAPI. It shows:
- Current executor connection state and metadata.
- Recent control-plane events and request/response history.
- Workflow lists, queued workflows, details, and step details.

### Conductor Protocol Bridge
The WebSocket endpoint lives at `WS /websocket/{app_name}/{conductor_key}` and supports:
- `list_workflows`
- `list_queued_workflows`
- `get_workflow`
- `list_steps`
- `recovery`, `cancel`, `resume`, `restart`
- `fork`

### Edited Fork Workflows
Beyond native forks, this repo adds an edited-fork path that can stage or run a rewritten fork directly against the DBOS system database. You can:
- Seed editable workflow input from the source workflow's persisted input.
- Override workflow inputs before re-execution.
- Override preserved step outputs before the restart point.

### Cross-language Serialization Support
The control plane understands various serialization shapes (Python, Go/TypeScript `DBOS_JSON`, TypeScript `js_superjson`, Java `java_jackson`) to allow cross-language fork inspection and reruns.

## Architecture

The project is split into two main components:

1. **Sample Applications**: Language-specific implementations of a simple workflow that simulates a crash when a specific input is provided (`name=poison`). This allows you to test the recovery and operator features.
2. **StepChange Control Plane**: A standalone service (provided as a Docker image/build context) that acts as a conductor bridge between the DBOS executors and an operator UI/API.

## Running the Samples

All samples are containerized with Docker Compose. You should first build the `stepchange` control plane image locally before running any of the language-specific stacks.

### 1. Build StepChange Control Plane

```bash
git clone https://github.com/eeveebank/stepchange.git
docker build -t stepchange:latest stepchange
```
*(Note: If you are working within this repo, the build context is `.`)*

```bash
docker build -t stepchange:latest .
```

### 2. Run a specific language stack

Navigate to the desired directory and use `docker compose up`. For example, to run the Go sample:

```bash
cd go
docker compose up --build
```

The services will be available at:
- **App**: `http://localhost:8000`
- **StepChange Dashboard**: `http://localhost:8001`

### Enabling Debug Logs

To enable more detailed logs for both the app and the control plane during debugging:

```bash
# Example for Go
APP_LOG_LEVEL=info APP_ACCESS_LOG=true \
CONTROL_PLANE_LOG_LEVEL=info CONTROL_PLANE_ACCESS_LOG=true \
docker compose up --build
```

## Testing Recovery and Forking

### Try the recovery flow

1. Start the stack: `docker compose up --build`
2. Open `http://localhost:8000/?name=world` to create a successful workflow.
3. Open `http://localhost:8000/?name=poison` to make the app container crash intentionally.
4. Docker Compose will restart the app container automatically.
5. Open `http://localhost:8001` and use the dashboard to inspect the stalled/failed workflow and trigger a **recovery**.

### Try the fork flow

1. Start the stack: `docker compose up --build`
2. Open `http://localhost:8000/?name=world` once to create a workflow history.
3. Open `http://localhost:8001` and click **List Workflows**.
4. Use the `fork` action on a workflow row.
5. Select the step you want to re-execute from and optionally provide a new workflow ID.
6. Submit the fork and confirm the new workflow appears in the list.

## Supported Languages

- [Go](./go/README.md)
- [TypeScript](./typescript/README.md)
- [Python](./python/README.md)
- [Java](./java/README.md)

## Stopping the Stack

```bash
docker compose down
```

To also remove the database volumes:

```bash
docker compose down -v
```

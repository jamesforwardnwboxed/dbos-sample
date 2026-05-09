# StepChange

`StepChange` is a DBOS control plane focused on workflow operations, inspection, and replay.

This repository is primarily about the control plane itself: a standalone service that sits between DBOS executors and an operator-facing UI/API. The sample apps in `go`, `typescript`, `python`, `javalin`, `spring-boot`, and `micronaut` are here to show the control plane working end-to-end across multiple SDKs and serialization formats.

## What StepChange Does

StepChange provides:

- A browser dashboard for inspecting workflows, steps, queued work, executor state, and request history.
- A conductor bridge that speaks to DBOS executors over WebSocket.
- Operator actions for workflow recovery, cancel, resume, restart, and fork.
- Edited fork support so operators can replay workflows with rewritten inputs or preserved step outputs.
- Cross-language workflow inspection and reruns across multiple DBOS serialization formats.

## Control Plane Features

### Dashboard and Request Log

The UI at `GET /` is a static single-page app served by FastAPI. It shows:

- Current executor connection state and metadata.
- Recent control-plane events and request/response history.
- Workflow lists, queued workflows, workflow details, and step details.

### Conductor Protocol Bridge

The WebSocket endpoint lives at `WS /websocket/{app_name}/{conductor_key}` and supports:

- `list_workflows`
- `list_queued_workflows`
- `get_workflow`
- `list_steps`
- `recovery`, `cancel`, `resume`, `restart`
- `fork`

### Edited Fork Workflows

Beyond native forks, StepChange adds an edited-fork path that can stage or run a rewritten fork directly against the DBOS system database. You can:

- Seed editable workflow input from the source workflow's persisted input.
- Override workflow inputs before re-execution.
- Override preserved step outputs before the restart point.

### Cross-language Serialization Support

The control plane understands multiple serialization formats used by the sample apps so workflows can be inspected and rerun across languages and frameworks.

Portable serialization is the recommended default. It is the best-supported option here, the easiest format to understand when inspecting workflow state, and it gives StepChange the cleanest path to better UI/UX over time. In particular, it opens the door to much nicer workflow input and step-output editing experiences later instead of forcing operators to work directly with raw JSON-shaped payloads everywhere.

## Repository Layout

This repo has two main parts:

1. `stepchange/`: the actual control plane service.
2. Sample apps: containerized DBOS applications used to exercise the control plane across Go, TypeScript, Python, Javalin, Spring Boot, and Micronaut.

The sample apps intentionally include crash-and-recovery flows such as `name=poison` so you can test operator features in a realistic way.

## Micronaut Integration

This repo also includes a custom Micronaut DBOS integration under `micronaut/dbos-micronaut` so the Micronaut sample can participate in the same StepChange workflows as the other apps.

Because apparently shipping a control plane and a custom DBOS Micronaut integration in the same repo was the sensible thing to do.

## Running StepChange With a Sample App

Build the StepChange image first:

```bash
docker build -t stepchange:latest .
```

Then run one of the sample stacks. For example, the Go stack:

```bash
docker compose -f docker-compose-go.yml up --build
```

The services will be available at:

- App: `http://localhost:8000`
- StepChange dashboard: `http://localhost:8001`

## Debug Logging

To enable more detailed logs for both the app and the control plane:

```bash
APP_LOG_LEVEL=info APP_ACCESS_LOG=true \
CONTROL_PLANE_LOG_LEVEL=info CONTROL_PLANE_ACCESS_LOG=true \
docker compose -f docker-compose-go.yml up --build
```

## Trying the Main Flows

### Recovery

1. Start a stack with `docker compose -f docker-compose-go.yml up --build`.
2. Open `http://localhost:8000/?name=world` to create a successful workflow.
3. Open `http://localhost:8000/?name=poison` to trigger an intentional crash.
4. Let Docker Compose restart the app.
5. Open `http://localhost:8001` and use StepChange to inspect the workflow and trigger recovery.

### Fork and Edit

1. Start a stack with `docker compose -f docker-compose-go.yml up --build`.
2. Open `http://localhost:8000/?name=world` to create workflow history.
3. Open `http://localhost:8001` and list workflows.
4. Use the fork action on a workflow row.
5. Choose the step to restart from and optionally edit workflow input or preserved step outputs.
6. Submit the fork and confirm the new workflow appears in the list.

## Sample Apps

- [Go](./go/README.md)
- [TypeScript](./typescript/README.md)
- [Python](./python/README.md)
- [Javalin](./javalin/README.md)
- [Spring Boot](./spring-boot/README.md)
- [Micronaut](./micronaut/README.md)

## Stopping the Stack

```bash
docker compose down
```

To also remove database volumes:

```bash
docker compose down -v
```

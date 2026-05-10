# DBOS Python Starter

This branch contains the Python version of the sample app plus a separate local control-plane runtime.

## What it does

The DBOS app service exposes `GET /` and runs a DBOS workflow with two steps:

- the workflow input is a structured Python object built from the `name` query parameter
- `step_one` prints a greeting and returns a structured Python object containing the greeting, name length, and extra metrics
- `step_two` raises an ordinary exception when `name=poison`
- otherwise the workflow completes normally

Call the endpoint with an optional `name` query parameter, for example `/?name=James`.

## Why DBOS is interesting

DBOS gives you durable workflows directly inside normal application code. Instead of wiring together queues, consumers, retry topics, compensating jobs, and hand-rolled recovery logic, you write the flow once and DBOS checkpoints workflow inputs and step outputs in Postgres.

That is useful because:

- if the process crashes halfway through a multi-step flow, DBOS resumes from the last completed step instead of replaying everything from the beginning
- the control flow stays in code, with regular branches, loops, retries, and function calls, instead of being split across multiple consumers or an explicit DAG definition
- there is no separate orchestration server to run for the core workflow engine; DBOS is a library in your app plus a Postgres database
- queueing and workflow state live in the same durability model, so waiting for child work and collecting results is much simpler than stitching together separate async primitives
- execution state is queryable in ordinary Postgres tables, which makes debugging and operational inspection more straightforward

## Why this can be nicer than broker-heavy async systems

Compared with a Kafka or broker-first design for business workflows:

- you do not have to decompose every step into separate producers and consumers just to get reliability
- you avoid a lot of message choreography boilerplate, including retry topics, dead-letter handling, and “what already ran?” bookkeeping
- you keep the workflow state model close to the application instead of spreading it across code, broker state, and ad hoc tables
- you reduce schema-evolution pressure on event payloads for internal workflow progress because step outputs and workflow state are checkpointed as part of one execution model
- each application can own its own DBOS system database, so one service's workflow load is isolated at the database boundary instead of sharing a centralized broker cluster with every other service
- for many background jobs, agents, payments, and approval flows, durability comes from Postgres writes rather than from building and operating a larger eventing platform

That does not mean DBOS replaces Kafka for every case. Kafka is still a strong fit for high-volume event streaming, fan-out analytics, and durable event logs across many independent consumers. DBOS is especially compelling when the problem is durable execution of a business process, not just moving messages around.

## Other positives

- durable queues are built in, so background task execution and workflow orchestration use the same model
- application versioning and workflow patching exist for handling long-running workflow code changes safely
- the architecture scales with Postgres and can be sharded further if needed
- the model is a strong fit for AI agents, long-running jobs, payment flows, and human-in-the-loop processes where partial progress matters
- because the workflow is regular code, the happy path is usually easier to read than equivalent state-machine or message-choreography implementations

## Runtime split

The repo now runs two Python services:

- `app`: the DBOS workflow runtime on `http://localhost:8000`
- `control-plane`: a separate FastAPI/WebSocket runtime on `http://localhost:8001`

The control-plane service is a narrow Conductor-compatible shim. It accepts the SDK connection at `/websocket/{app_name}/{conductor_key}`, sends `executor_info` first, and currently supports:

- `list_workflows`
- `list_queued_workflows`
- `get_workflow`
- `list_steps`
- `recovery`
- `cancel`
- `resume`
- `restart`
- `fork`

The control-plane UI is served directly by that runtime at `http://localhost:8001/`. There is no Node/Vite frontend for v1. The dashboard can inspect workflow state, trigger operator actions, and fork a workflow from a selected step into a new execution.

Important operator boundary:

- native `recovery` still means DBOS resumes pending workflows with their original persisted input
- native `fork` still means DBOS reuses persisted input and completed step outputs before the selected step
- editable input override is implemented in the shim as a custom rerun launch from the fork modal, and currently only supports a full rerun from `step 0`

## Run

The whole sample is containerized. You only need Docker and Docker Compose on the host.

The control-plane runs as a separate prebuilt image sourced from the [`dbos-control-plane`](https://github.com/jamesforwardnwboxed/dbos-control-plane) repo. Build it once locally as `stepchange:latest` before starting the stack:

```bash
git clone https://github.com/jamesforwardnwboxed/dbos-control-plane.git
docker build -t stepchange:latest dbos-control-plane
```

Then bring up the stack from this repo:

```bash
docker compose up --build
```

This starts:

- the app container
- the control-plane container
- a Postgres container for the DBOS system database

The app is available at `http://localhost:8000`.
The control-plane UI is available at `http://localhost:8001`.

Both services are quiet by default. To enable routine request and step logs while debugging:

```bash
APP_LOG_LEVEL=info APP_ACCESS_LOG=true \
CONTROL_PLANE_LOG_LEVEL=info CONTROL_PLANE_ACCESS_LOG=true \
docker compose up --build
```

Default behavior keeps workflow and lifecycle logs at `info` while leaving HTTP access logs off.

## Try the recovery flow

1. Start the stack with `docker compose up --build`.
2. Open `http://localhost:8000/?name=world`.
3. Open `http://localhost:8000/?name=poison` to make `step_two` fail.
4. Inspect the workflow in StepChange and confirm it is recorded as an error.
5. Trigger restart, resume, or fork flows from the control-plane UI as needed.

## Try the fork flow

1. Start the stack with `docker compose up --build`.
2. Open `http://localhost:8000/?name=world` once to create workflow history.
3. Open `http://localhost:8001` and click `List Workflows`.
4. Use the `fork` action on a workflow row.
5. Select the step you want to re-execute from and optionally provide a new workflow ID.
6. Submit the fork and confirm the new workflow appears in the workflow list with `ForkedFrom` pointing at the original execution.

## Try editable input override rerun

1. Start the stack with `docker compose up --build`.
2. Open `http://localhost:8000/?name=world` once to create workflow history.
3. Open `http://localhost:8001` and click `List Workflows`.
4. Use the `fork` action on a workflow row.
5. Leave the selection on `step 0` and edit the `Input override` JSON to something like `{ "name": "Ada" }`.
6. Submit the rerun and confirm the new workflow appears in the workflow list.
7. Inspect the rerun request in the control-plane request log and confirm the app output reflects the overridden input.

## Control-plane verification

1. Start the stack with `docker compose up --build`.
2. Confirm the control-plane UI loads at `http://localhost:8001`.
3. Confirm the DBOS app still responds at `http://localhost:8000/?name=world`.
4. Inspect the control-plane dashboard to verify the executor session becomes ready after the `executor_info` handshake.
5. Use `List Workflows` to confirm workflow data loads into the dashboard.
6. Open a workflow with `inspect`, load its steps through the fork modal, and verify the step list renders.
7. Send a fork request and verify the returned workflow ID appears in later `list_workflows` results.
8. Send an edited-input rerun from `step 0` and verify the returned workflow ID appears in later `list_workflows` results.
9. Trigger native recovery and verify it still resumes pending workflows without any input-edit UI.

## Stop the stack

```bash
docker compose down
```

To also remove the Postgres volume:

```bash
docker compose down -v
```

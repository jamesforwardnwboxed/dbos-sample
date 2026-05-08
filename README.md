# DBOS Go Starter

This branch contains the Go version of the sample app.

## What it does

The app exposes `GET /` and runs a DBOS workflow with two steps:

- the workflow input is a structured Go object built from the `name` query parameter
- `stepOne` prints a greeting and returns a structured Go object containing the greeting, name length, and extra metrics
- the workflow exits immediately when `name=poison` to simulate a crash
- otherwise the workflow continues to `stepTwo`

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
- you avoid a lot of message choreography boilerplate, including retry topics, dead-letter handling, and "what already ran?" bookkeeping
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

## Run

The whole sample is containerized. You only need Docker and Docker Compose on the host.

The control-plane runs as a separate prebuilt image sourced from the [`dbos-control-plane`](https://github.com/jamesforwardnwboxed/dbos-control-plane) repo. Build it once locally before starting the stack:

```bash
git clone https://github.com/jamesforwardnwboxed/dbos-control-plane.git
docker build -t dbos-control-plane:latest dbos-control-plane
```

Then bring up the stack from this repo:

```bash
docker compose up --build
```

This starts:

- the app container
- the control-plane container (DBOS conductor + dashboard)
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
3. Open `http://localhost:8000/?name=poison` to make the app container exit intentionally.
4. Docker Compose restarts the app container automatically.
5. Trigger recovery or inspect the control-plane UI to observe the poisoned workflow state.

## Stop the stack

```bash
docker compose down
```

To also remove the Postgres volume:

```bash
docker compose down -v
```

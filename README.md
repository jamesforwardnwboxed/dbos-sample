# StepChange

StepChange is the standalone control plane / conductor service used by the [`dbos-starter`](https://github.com/eeveebank/dbos-starter) sample apps (Python, Go, Java, TypeScript). It exposes a FastAPI service on port `8001`, talks directly to the DBOS system database, serves a browser UI, and maintains the WebSocket session that DBOS executors use for operator commands.

## What It Does

This project splits the DBOS control-plane concerns out of the sample application repo so every language branch can point at the same StepChange image instead of carrying its own copy of the Python shim.

At runtime it provides:

- a browser dashboard for inspecting workflow state and recent conductor traffic
- a conductor-compatible WebSocket endpoint for DBOS executors
- HTTP endpoints that translate UI actions into conductor messages
- direct system-database reads and writes for advanced fork workflows
- cross-language input/output decoding so forks work across Python, Go, TypeScript, and Java starters

The service is intentionally narrow: it is not a general DBOS replacement or a standalone workflow engine. The executor still runs inside the app container. This repo provides the operator surface around that executor.

## Feature Set

### Dashboard and request log

The UI at `GET /` is a static single-page app served directly by FastAPI. It shows:

- current executor connection state
- executor metadata from the initial `executor_info` handshake
- recent control-plane events and request/response history
- workflow lists, queued workflow lists, workflow details, and step details

This is useful both for operator actions and for debugging the conductor protocol itself.

### Conductor protocol bridge

The WebSocket endpoint lives at:

- `WS /websocket/{app_name}/{conductor_key}`

Behavior:

- validates the expected app name and shared conductor key before accepting the session
- initiates the DBOS handshake by sending `executor_info`
- tracks session lifecycle, request timeouts, and disconnects
- forwards operator requests to the connected executor and records responses

Supported conductor operations include:

- `list_workflows`
- `list_queued_workflows`
- `get_workflow`
- `list_steps`
- `recovery`
- `cancel`
- `resume`
- `restart`
- `fork`

### Edited fork workflows

Beyond the native conductor fork command, this repo adds an edited-fork path that can stage or run a rewritten fork directly against the DBOS system database.

Supported behaviors:

- seed editable workflow input from the source workflow's persisted input
- override workflow inputs before re-execution
- override preserved step outputs before the restart point
- optionally cancel the original workflow first if it is still active
- stage a new workflow for recovery-driven execution
- immediately trigger that staged workflow via `recovery`

There are two modes:

- `stage`: create the new staged workflow and stop there
- `run`: stage the new workflow, clear conflicting orphan staged forks for the same executor, and then trigger recovery automatically

Current limitations:

- edited fork does not support child workflows yet
- step output overrides only apply to preserved steps before `start_step`
- execution of staged forks is tied to a ready executor session and its `application_version`

### Cross-language serialization support

The control plane has custom serialization handling so it can read and rewrite workflow inputs and step outputs created by different DBOS SDKs.

It understands:

- Python serializer shapes
- portable JSON workflow input shape (`positionalArgs` / `namedArgs`)
- Go/TypeScript `DBOS_JSON`
- TypeScript `js_superjson`
- Java `java_jackson`

This matters because the Python DBOS SDK does not natively register all of the codecs used by the other language SDKs. Without these compatibility layers, cross-language fork inspection and edited reruns would fail or write unreadable payloads.

### Schema compatibility across SDKs

The DBOS SDKs do not all ship identical `dbos.workflow_status` schemas. In particular, Go and TypeScript can omit columns such as `was_forked_from` and `rate_limited`.

This repo adapts to the actual database schema at runtime so the same control-plane image can safely target databases owned by different language executors.

## Architecture

High-level flow:

1. The app container starts and connects to `ws://control-plane:8001/websocket/{app_name}/{conductor_key}`.
2. This service validates the connection and requests `executor_info`.
3. The UI or HTTP API triggers an operator action.
4. The control plane either:
   - sends a conductor request over WebSocket to the executor, or
   - performs local database work for edited-fork staging, then optionally sends `recovery`.
5. The service records events and responses so the UI can show current state.

This split keeps the executor inside the app runtime while making the operator UX and conductor bridge reusable across all starter languages.

## Build

```bash
docker build -t stepchange:latest .
```

The `dbos-starter` per-language `docker-compose.yml` files reference this image by name (`stepchange:latest`) and expect it to exist locally — there is no registry push.

## Run

Usually invoked via `docker compose` from a `dbos-starter` checkout. To run standalone:

```bash
docker run --rm -p 8001:8001 \
  -e CONTROL_PLANE_SYSTEM_DATABASE_URL=postgres://postgres:dbos@host.docker.internal:5432/dbos_starter \
  stepchange:latest
```

The corresponding app container should be configured with:

```bash
DBOS_CONDUCTOR_URL=ws://control-plane:8001/websocket
DBOS_CONDUCTOR_KEY=local-conductor-key
DBOS_APP_NAME=dbos-starter
```

## Configuration

| Env var | Default | Purpose |
| --- | --- | --- |
| `CONTROL_PLANE_APP_NAME` | `dbos-starter` | App name reported to conductor clients |
| `CONTROL_PLANE_CONDUCTOR_KEY` | `local-conductor-key` | Shared key clients use as `DBOS_CONDUCTOR_KEY` |
| `CONTROL_PLANE_SYSTEM_DATABASE_URL` / `DBOS_SYSTEM_DATABASE_URL` | `postgres://postgres:dbos@postgres:5432/dbos_starter` | DBOS system DB connection |
| `CONTROL_PLANE_HOST` | `0.0.0.0` | Bind host |
| `CONTROL_PLANE_PORT` | `8001` | Bind port |
| `CONTROL_PLANE_REQUEST_TIMEOUT_SECONDS` | `5.0` | Per-request timeout |
| `CONTROL_PLANE_LOG_LEVEL` | `info` | Uvicorn log level |
| `CONTROL_PLANE_ACCESS_LOG` | `false` | Enable HTTP access logging |

The control plane leaves startup and lifecycle logging on by default and keeps request logging off. To turn request logging back on while debugging:

```bash
CONTROL_PLANE_LOG_LEVEL=info
CONTROL_PLANE_ACCESS_LOG=true
```

## API Surface

### UI and state

- `GET /` : static dashboard UI
- `GET /api/control-plane/state` : current snapshot of session state, cached outputs, request history, and events

### Executor-backed workflow operations

- `POST /api/control-plane/list-workflows`
- `POST /api/control-plane/list-queued-workflows`
- `POST /api/control-plane/get-workflow`
- `POST /api/control-plane/list-steps`
- `POST /api/control-plane/recovery`
- `POST /api/control-plane/cancel`
- `POST /api/control-plane/resume`
- `POST /api/control-plane/restart`
- `POST /api/control-plane/fork`

Native `fork` requests can pass through DBOS options such as:

- `new_workflow_id`
- `application_version`
- `queue_name`

### Edited fork operations

`POST /api/control-plane/fork` also supports local edited-fork execution when either of these fields is present:

- `workflow_input_override`
- `step_output_overrides`

Additional edited-fork fields:

- `mode`: `stage` or `run`
- `new_workflow_id`
- `cancel_original_if_active`

There is also a dedicated follow-up endpoint:

- `POST /api/control-plane/execute-staged-fork`

Use that when a workflow was staged earlier and you want the control plane to validate it and trigger execution via recovery.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

The test suite covers:

- handshake and websocket lifecycle
- state snapshot behavior
- UI and API routes
- fork and edited-fork flows
- cross-language serialization handling in fork state

## Endpoints

- `GET /` — UI
- `GET /api/...` — JSON API for state, workflow inspection, recovery, lifecycle actions, and fork actions
- `WS /websocket/{app_name}/{conductor_key}` — DBOS conductor protocol endpoint

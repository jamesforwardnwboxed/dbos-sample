# DBOS Conductor-Compat + Zero-Build UI Implementation Plan

## Goal and risk posture

Deliver in two waves on one FastAPI server process:
1. **First:** local DBOS Conductor-compatible WebSocket control plane (MVP compatibility, narrow protocol).
2. **Second:** fancy zero-build UI served by FastAPI from static files on the same server.

Risk posture: **MVP compatibility shim, not full Conductor parity**. Keep scope tight, observable, and test-driven.

Important protocol correction from DBOS Python source:
- The Python SDK is the **WebSocket client**.
- It connects to `.../websocket/{app_name}/{conductor_key}`.
- The server sends an `executor_info` request first.
- The SDK responds with executor metadata, then continues answering specific conductor request types.

So the safest MVP is a **tiny Conductor-style control plane**, not a custom queue dispatcher.

---

## Current repo facts (baseline)

- `main.py` is the entrypoint; DBOS is launched inline (`DBOS(config)`, `DBOS.launch()`, `uvicorn.run(...)`).
- `GET /` is the crash-and-recovery workflow.
- `Dockerfile` currently copies only `main.py`, `requirements.txt`, and `README.md`.
- No `static/`, no templates, no frontend toolchain.

---

## Wave 0 — structural prep + protocol freeze (readability and lowest-risk split)

### Files to add

- `app/__init__.py`
- `app/server.py` — app factory + startup/shutdown wiring.
- `app/dbos_runtime.py` — DBOS init/launch wrapper and existing workflow registration.
- `app/conductor_protocol.py` — the only module allowed to import `dbos._conductor.protocol`.
- `app/conductor_state.py` — in-memory session/request/event state.
- `app/conductor_ws.py` — websocket route + conductor request/response loop.
- `app/routes_workflow.py` — existing `GET /` workflow route (unchanged semantics).
- `app/routes_ui.py` — UI shell + read/admin JSON routes.

### Files to update

- `main.py` — reduce to thin runner importing app factory.

### Design choices

- Keep the existing workflow behavior exactly as-is in `routes_workflow.py`.
- Use `dbos._conductor.protocol` types/constants via `app/conductor_protocol.py` instead of hand-rolled wire schema.
- Keep the conductor shim in-memory first (single-process dev target).
- Keep the UI thin and app-scoped; do not couple UI code to raw private protocol details.

---

## Wave 1 — Conductor-compatible websocket control plane (MVP)

## WebSocket endpoint shape

- `WS /websocket/{app_name}/{conductor_key}`
- Validate path params are present/non-empty.
- Accept one executor connection per app for MVP.
- Register per-connection session in manager.

## Minimal protocol subset to implement first

Implement only what is required to safely talk to the Python SDK for local development:

1. **Server-sent `executor_info` request immediately after connect**
   - Send request with generated `request_id`.
   - Do not consider the session ready until the matching response is received.

2. **Inbound `executor_info` response parsing**
   - Capture `executor_id`, `application_version`, `hostname`, `language`, `dbos_version`, `executor_metadata`.
   - Mark session `ready` only after a valid response.

3. **One read-only conductor request first: `list_workflows`**
   - Safest first operator action.
   - Gives immediate UI value without mutating workflow state.
   - Correlate request/response by `request_id`.

4. **One low-risk admin action next: `recovery`**
   - Limited, explicit operator-triggered action.
   - Keep the request body narrow and visible in UI.

5. **Optional next admin actions after MVP proves stable**
   - `cancel`
   - `resume`
   - `get_workflow`
   - `exist_pending_workflows`

6. **Transport handling**
   - Rely on normal WebSocket ping/pong transport behavior.
   - Track `last_seen_at` when frames are received/sent.
   - No custom app-level heartbeat protocol unless the DBOS protocol requires one.

7. **Error path**
   - Invalid handshake response, malformed payload, request timeout, or unknown message type => log, mark request failed, and close when needed.

### Explicitly deferred (non-MVP)

- Multi-executor balancing.
- All scheduling/version/retention/metrics/export/import surfaces.
- Durable persistence for conductor state.
- Full parity with hosted DBOS Conductor behaviors.
- Inventing a new request model that does not mirror DBOS protocol requests.

## WebSocket manager/state organization

### `app/conductor_state.py`

Dataclasses:
- `ExecutorSession`
  - `session_id`, `app_name`, `conductor_key`, `connected_at`, `last_seen_at`
  - `executor_info`
  - `websocket_ref`
  - `status` (`connecting|ready|closing|closed`)

- `ConductorRequestRecord`
  - `request_id`, `created_at`, `dispatched_at`, `completed_at`
  - `target_app_name`, `message_type`, `request_payload`
  - `status` (`queued|sent|succeeded|failed|timed_out`)
  - `response_payload`, `error_payload`

- `ConductorEvent`
  - `timestamp`, `direction`, `message_type`, `request_id`, `summary`

- `ConductorSnapshot`
  - derived read model for UI/API (connection state, latest events, recent requests, last workflow listing)

Manager class:
- `ConductorManager`
  - `register_connection(...)`
  - `complete_executor_info(...)`
  - `create_request(...)`
  - `mark_request_sent(...)`
  - `complete_request(...)`
  - `append_event(...)`
  - `disconnect(...)`
  - `snapshot()`

Threading model:
- Single-process async with `asyncio.Lock` around mutable maps.
- Keep manager owned by FastAPI `app.state.conductor_manager`.
- Prefer one active executor session for the configured app name in MVP.

---

## Wave 2 — HTTP control plane + zero-build UI on same FastAPI app

## Routes

Keep current workflow route untouched:
- `GET /` -> existing DBOS workflow behavior.

Add conductor/UI routes:
- `GET /conductor` -> serve UI shell (`static/conductor/index.html`).
- `GET /api/conductor/state` -> JSON snapshot for dashboard polling.
- `POST /api/conductor/list-workflows` -> issue a `list_workflows` protocol request.
- `POST /api/conductor/recovery` -> issue a `recovery` protocol request.
- `POST /api/conductor/cancel` -> defer until after MVP unless specifically needed.
- `GET /api/conductor/events` (optional for MVP; can defer if snapshot already includes recent events).

WebSocket route:
- `WS /websocket/{app_name}/{conductor_key}` (from Wave 1).

## Static assets (zero-build)

### Files to add

- `static/conductor/index.html`
- `static/conductor/styles.css`
- `static/conductor/app.js`

UI approach:
- Vanilla HTML/CSS/ES modules only.
- No bundler, no node toolchain.
- Poll `/api/conductor/state` every 1–2s.
- Panels: connection status, executor info, recent requests, recent protocol events, workflow list/results, errors.
- “Fancy” via CSS (cards, badges, responsive grid, subtle motion), but operationally simple.

UI boundary:
- UI should call simple HTTP routes.
- Only backend code should know about `dbos._conductor.protocol` dataclasses.
- This keeps the private protocol coupling isolated to Python server code.

---

## Container/runtime updates

### Files to update

- `Dockerfile`
  - copy `app/` and `static/` (plus tests if included in image strategy).
  - keep command `python main.py` unless switching to `uvicorn app.server:create_app` style.

- `README.md`
  - document new routes, local conductor shim scope, and MVP limitations.
  - document expected local wiring for SDK conductor URL and app/key values.

- `docker-compose.yml`
  - keep existing db + app topology.
  - ensure env wiring allows SDK in app process to target local shim endpoint when desired.

---

## Test-first verification sequence (TDD-oriented)

### Files to add

- `tests/test_workflow_route.py`
  - lock current `GET /` behavior (non-regression).

- `tests/test_conductor_state.py`
  - manager transitions: register -> handshake -> request sent -> response complete -> disconnect.

- `tests/test_conductor_ws_handshake.py`
  - websocket accepts connection, server sends `executor_info` request first, valid response marks session ready.

- `tests/test_conductor_ws_list_workflows.py`
  - issue `list_workflows` via API, send protocol request over WS, ingest response, verify snapshot contains results.

- `tests/test_conductor_ws_recovery.py`
  - issue `recovery` via API, send protocol request over WS, ingest response, verify terminal status.

- `tests/test_ui_routes.py`
  - `/conductor` returns HTML; static assets served with 200 and expected content-type.

### Recommended test order

1. Write failing state-manager unit tests.
2. Implement manager until green.
3. Write failing WS handshake tests.
4. Implement `executor_info` request/response loop until green.
5. Write failing `list_workflows` integration test.
6. Implement read-only request cycle until green.
7. Write failing `recovery` integration test.
8. Implement the recovery action until green.
9. Write failing UI route/static tests.
10. Implement UI serving and snapshot endpoint until green.
11. Re-run full suite + smoke manual checks.

---

## Ultrawork-friendly wave execution plan (minimal context switching)

### Wave A (protocol-safe foundation)
- Create package split (`app/*`) + move existing workflow unchanged.
- Introduce protocol adapter and state manager skeleton.
- Land unit tests for manager.

### Wave B (ws compatibility MVP)
- Implement websocket endpoint.
- Server sends `executor_info` request on connect.
- Implement correlation and response handling.
- Land WS handshake tests.

### Wave C (read-first operator actions)
- Add `/api/conductor/state`, `/api/conductor/list-workflows`, `/conductor`.
- Implement `list_workflows` end-to-end.
- Land read-only integration tests.

### Wave D (minimal admin action + UX)
- Add `/api/conductor/recovery`.
- Implement `recovery` end-to-end.
- Add static assets and dashboard polish.
- Keep UI polling-based and zero-build.
- Land UI route/static tests.

### Wave E (container/docs hardening)
- Update Dockerfile copy rules.
- Update compose/env docs and README limitations.
- Final regression run.

---

## Atomic commit strategy

1. **`refactor(app): split starter into app package without behavior change`**
   - move workflow route and DBOS bootstrap into modules.

2. **`feat(conductor): add in-memory conductor state manager with tests`**
   - manager dataclasses + state transition tests.

3. **`feat(conductor-ws): add executor-info handshake for local conductor compatibility`**
   - `/websocket/{app_name}/{conductor_key}` + protocol adapter + handshake integration tests.

4. **`feat(conductor-read): add list-workflows operator flow and state API`**
   - read-only protocol request, HTTP wrapper route, and integration tests.

5. **`feat(ui): add zero-build conductor dashboard and recovery action`**
   - `/conductor`, static assets, recovery route, UI route tests.

6. **`chore(docker-docs): include new app/static files and document local shim limits`**
   - Dockerfile + README + compose notes.

Each commit should keep tests green at that step.

---

## MVP acceptance criteria

- App still serves existing `GET /` crash-recovery workflow.
- Local websocket endpoint accepts SDK connection at `/websocket/{app_name}/{conductor_key}`.
- Server initiates `executor_info`; the SDK response is captured and validated.
- At least one read-only protocol round-trip (`list_workflows`) works and is visible in `/api/conductor/state`.
- One low-risk admin round-trip (`recovery`) works and is visible in `/api/conductor/state`.
- `/conductor` serves a zero-build UI from FastAPI static files.
- Docker image contains all runtime files (`app/`, `static/`) needed for the above.

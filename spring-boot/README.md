# DBOS Spring Boot Starter

This directory contains the Spring Boot counterpart to the Javalin sample app.

## What it does

The app exposes `GET /` and runs the same DBOS workflow as the Javalin sample:

- the workflow input is a structured Java object built from the `name` query parameter
- `stepOne` prints a greeting and returns a structured Java object containing the greeting, name length, and extra metrics
- the workflow exits immediately when `name=poison` to simulate a crash
- otherwise the workflow continues to `stepTwo`

Call the endpoint with an optional `name` query parameter, for example `/?name=James`.

## Run

The whole sample is containerized. You only need Docker and Docker Compose on the host.

The control-plane runs as a separate prebuilt image sourced from the [`dbos-control-plane`](https://github.com/jamesforwardnwboxed/dbos-control-plane) repo. Build it once locally as `stepchange:latest` before starting the stack:

```bash
git clone https://github.com/jamesforwardnwboxed/dbos-control-plane.git
docker build -t stepchange:latest dbos-control-plane
```

Then bring up the stack from this repo:

```bash
docker compose -f docker-compose-spring-boot.yml up --build
```

This starts:

- the app container
- the control-plane container (DBOS conductor + dashboard at `http://localhost:8001`)
- a Postgres container for the DBOS system database

The app is available at `http://localhost:8000`.

Both services are quiet by default. To enable routine request and step logs while debugging:

```bash
APP_LOG_LEVEL=info APP_ACCESS_LOG=true \
CONTROL_PLANE_LOG_LEVEL=info CONTROL_PLANE_ACCESS_LOG=true \
docker compose -f docker-compose-spring-boot.yml up --build
```

## Try the recovery flow

1. Start the stack with `docker compose -f docker-compose-spring-boot.yml up --build`.
2. Open `http://localhost:8000/?name=world`.
3. Open `http://localhost:8000/?name=poison` to make the app container exit intentionally.
4. Docker Compose restarts the app container automatically.
5. Trigger recovery or inspect the control-plane UI to observe the poisoned workflow state.

## Stop the stack

```bash
docker compose -f docker-compose-spring-boot.yml down
```

To also remove the Postgres volume:

```bash
docker compose -f docker-compose-spring-boot.yml down -v
```

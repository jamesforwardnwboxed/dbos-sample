# DBOS TypeScript Starter

This branch contains the TypeScript version of the sample app.

## What it does

The app exposes `GET /` and runs a DBOS workflow with two steps:

- `step_one` logs a greeting and returns the length of the `name` query parameter
- the workflow creates `existing.txt` and exits once to simulate a crash
- after restart, DBOS resumes the workflow and runs `step_two`

Call the endpoint with an optional `name` query parameter, for example `/?name=James`.

## Run

The whole sample is containerized. You only need Docker and Docker Compose on the host.

```bash
docker compose up --build
```

This starts:

- the app container
- a Postgres container for the DBOS system database

The app is available at `http://localhost:8000`.

## Try the recovery flow

1. Start the stack with `docker compose up --build`.
2. Open `http://localhost:8000/?name=world`.
3. The first request creates `existing.txt` and exits the app container intentionally.
4. Docker Compose restarts the app container automatically.
5. DBOS resumes the workflow from the point after `step_one`.

## Stop the stack

```bash
docker compose down
```

To also remove the Postgres volume:

```bash
docker compose down -v
```

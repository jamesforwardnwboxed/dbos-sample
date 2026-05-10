# DBOS Micronaut Starter

This directory contains a Micronaut sample app plus an in-repo Micronaut integration library for DBOS.

## What it does

The app exposes `GET /` and runs the same DBOS workflow as the Javalin and Spring Boot samples:

- the workflow input is a structured Java object built from the `name` query parameter
- `stepOne` prints a greeting and returns a structured Java object containing the greeting, name length, and extra metrics
- `stepTwo` throws an ordinary exception when `name=poison`
- otherwise the workflow completes normally

The `dbos-micronaut` module is an in-repo Micronaut-native integration that mirrors the Spring Boot starter responsibilities using Micronaut conventions:

- compile-time configuration binding
- compile-time method interception for `@Workflow` and `@Step`
- startup-time workflow registration via `ExecutableMethodProcessor`
- DBOS launch and shutdown via Micronaut lifecycle events

## Run

Build `stepchange:latest` first, then run:

```bash
docker compose -f docker-compose-micronaut.yml up --build
```

The app is available at `http://localhost:8000`.

## Stop the stack

```bash
docker compose -f docker-compose-micronaut.yml down
```

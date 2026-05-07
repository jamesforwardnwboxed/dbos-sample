# DBOS Java Starter

This branch contains the Java version of the sample app.

## What it does

The app exposes `GET /` and runs a DBOS workflow with two steps:

- `stepOne` prints a greeting and returns the length of the `name` query parameter
- the workflow creates `existing.txt` and exits once to simulate a crash
- after restart, DBOS resumes the workflow and runs `stepTwo`

Call the endpoint with an optional `name` query parameter, for example `/?name=James`.

## Requirements

- Java 21+
- PostgreSQL for the DBOS system database
- `PGUSER`, `PGPASSWORD`, and `DBOS_SYSTEM_JDBC_URL` set in your environment

## Run

```bash
./gradlew run
```

The server listens on `http://localhost:8000`.

## Try the recovery flow

1. Start the app.
2. Open `http://localhost:8000/?name=world`.
3. The first request creates `existing.txt` and exits the process intentionally.
4. Start the app again with `./gradlew run`.
5. DBOS resumes the workflow from the point after `stepOne`.

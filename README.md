# DBOS Go Starter

This branch contains the Go version of the sample app.

## What it does

The app exposes `GET /` and runs a DBOS workflow with two steps:

- `stepOne` prints a greeting and returns the length of the `name` query parameter
- the workflow creates `existing.txt` and exits once to simulate a crash
- after restart, DBOS resumes the workflow and runs `stepTwo`

Call the endpoint with an optional `name` query parameter, for example `/?name=James`.

## Requirements

- Go 1.26+
- PostgreSQL for the DBOS system database
- `DBOS_SYSTEM_DATABASE_URL` set in your environment

If you do not already have Postgres running, DBOS can start one for you:

```bash
go install github.com/dbos-inc/dbos-transact-golang/cmd/dbos@latest
dbos postgres start
```

## Run

```bash
go mod tidy
go run main.go
```

The server listens on `http://localhost:8000`.

## Try the recovery flow

1. Start the app.
2. Open `http://localhost:8000/?name=world`.
3. The first request creates `existing.txt` and exits the process intentionally.
4. Start the app again with `go run main.go`.
5. DBOS resumes the workflow from the point after `stepOne`.

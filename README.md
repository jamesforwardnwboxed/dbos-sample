# DBOS TypeScript Starter

This branch contains the TypeScript version of the sample app.

## What it does

The app exposes `GET /` and runs a DBOS workflow with two steps:

- `step_one` logs a greeting and returns the length of the `name` query parameter
- the workflow creates `existing.txt` and exits once to simulate a crash
- after restart, DBOS resumes the workflow and runs `step_two`

Call the endpoint with an optional `name` query parameter, for example `/?name=James`.

## Requirements

- Node.js 20+
- PostgreSQL for the DBOS system database
- `DBOS_SYSTEM_DATABASE_URL` set in your environment

If you do not already have Postgres running, DBOS can start one for you:

```bash
npm install
npx dbos postgres start
```

## Run

```bash
npm install
npm run build
npm run start
```

The server listens on `http://localhost:8000`.

## Try the recovery flow

1. Start the app.
2. Open `http://localhost:8000/?name=world`.
3. The first request creates `existing.txt` and exits the process intentionally.
4. Start the app again with `npm run start`.
5. DBOS resumes the workflow from the point after `step_one`.

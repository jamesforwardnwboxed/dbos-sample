import { existsSync, writeFileSync } from "node:fs";
import path from "node:path";

import { DBOS } from "@dbos-inc/dbos-sdk";
import express from "express";

const app = express();
app.use(express.json());

type LogLevel = "debug" | "info" | "warn" | "error";

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

function getLogLevel(): LogLevel {
  const raw = process.env.APP_LOG_LEVEL?.trim().toLowerCase();
  if (raw === "debug" || raw === "info" || raw === "warn" || raw === "error") {
    return raw;
  }
  if (raw === "warning") {
    return "warn";
  }
  return "info";
}

function envFlag(name: string, defaultValue: boolean): boolean {
  const raw = process.env[name];
  if (raw == null) {
    return defaultValue;
  }
  return ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
}

const appLogLevel = getLogLevel();

function log(level: LogLevel, message: string): void {
  if (LOG_LEVELS[level] < LOG_LEVELS[appLogLevel]) {
    return;
  }

  if (level === "error") {
    console.error(message);
    return;
  }

  if (level === "warn") {
    console.warn(message);
    return;
  }

  console.log(message);
}

if (envFlag("APP_ACCESS_LOG", false)) {
  app.use((req, res, next) => {
    res.on("finish", () => {
      log("info", `${req.method} ${req.originalUrl} -> ${res.statusCode}`);
    });
    next();
  });
}

async function stepOne(name: string): Promise<number> {
  log("debug", `Hello ${name}`);
  log("debug", "Step one completed");
  return name.length;
}

async function stepTwo(name: string, nameLength: number): Promise<void> {
  log(
    "debug",
    `Step two completed for ${name}; the name has ${nameLength} characters.`,
  );
}

async function workflow(name = "world"): Promise<void> {
  log("info", `Starting workflow for ${name}`);
  const nameLength = await DBOS.runStep(() => stepOne(name), { name: "step_one" });

  const existingFile = path.join(process.cwd(), "existing.txt");
  if (!existsSync(existingFile)) {
    log("warn", "existing.txt missing; creating it and exiting to simulate a crash");
    writeFileSync(existingFile, "");
    process.exit(1);
  }

  await DBOS.runStep(() => stepTwo(name, nameLength), { name: "step_two" });
  log("info", `Completed workflow for ${name}`);
}

const dbosWorkflow = DBOS.registerWorkflow(workflow);

app.get("/", async (req, res, next) => {
  try {
    const queryName = req.query.name;
    const name = typeof queryName === "string" && queryName.length > 0 ? queryName : "world";

    await dbosWorkflow(name);
    res.status(200).send("workflow executed");
  } catch (error) {
    next(error);
  }
});

async function main(): Promise<void> {
  DBOS.setConfig({
    name: process.env.DBOS_APP_NAME ?? "dbos-starter",
    systemDatabaseUrl: process.env.DBOS_SYSTEM_DATABASE_URL,
  });

  const conductorKey = process.env.DBOS_CONDUCTOR_KEY;
  const conductorURL = process.env.DBOS_CONDUCTOR_URL;
  await DBOS.launch(conductorKey ? { conductorKey, conductorURL } : undefined);

  app.listen(8000, () => {
    log("info", "Server is running on http://localhost:8000");
  });
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});

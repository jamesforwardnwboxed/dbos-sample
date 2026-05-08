import { existsSync, writeFileSync } from "node:fs";
import path from "node:path";

import { DBOS } from "@dbos-inc/dbos-sdk";
import express from "express";

const app = express();
app.use(express.json());

async function stepOne(name: string): Promise<number> {
  DBOS.logger.info(`Hello ${name}`);
  DBOS.logger.info("Step one completed!");
  return name.length;
}

async function stepTwo(name: string, nameLength: number): Promise<void> {
  DBOS.logger.info(
    `Step two completed for ${name}; the name has ${nameLength} characters.`,
  );
}

async function workflow(name = "world"): Promise<void> {
  const nameLength = await DBOS.runStep(() => stepOne(name), { name: "step_one" });

  const existingFile = path.join(process.cwd(), "existing.txt");
  if (!existsSync(existingFile)) {
    writeFileSync(existingFile, "");
    process.exit(1);
  }

  await DBOS.runStep(() => stepTwo(name, nameLength), { name: "step_two" });
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
    DBOS.logger.info("Server is running on http://localhost:8000");
  });
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});

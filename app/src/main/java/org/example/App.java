package org.example;

import dev.dbos.transact.DBOS;
import dev.dbos.transact.config.DBOSConfig;
import dev.dbos.transact.workflow.Workflow;
import io.javalin.Javalin;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

interface Example {
  String workflow(String name);
}

class ExampleImpl implements Example {
  private final DBOS dbos;

  ExampleImpl(DBOS dbos) {
    this.dbos = dbos;
  }

  private int stepOne(String name) {
    System.out.printf("Hello %s%n", name);
    System.out.println("Step one completed!");
    return name.length();
  }

  private void stepTwo(String name, int nameLength) {
    System.out.printf(
        "Step two completed for %s; the name has %d characters.%n", name, nameLength);
  }

  @Override
  @Workflow
  public String workflow(String name) {
    int nameLength = dbos.runStep(() -> stepOne(name), "step_one");

    Path existingFile = Path.of("existing.txt");
    if (Files.notExists(existingFile)) {
      try {
        Files.createFile(existingFile);
      } catch (IOException e) {
        throw new RuntimeException(e);
      }
      System.exit(1);
    }

    dbos.runStep(() -> stepTwo(name, nameLength), "step_two");
    return "workflow executed";
  }
}

public class App {
  public static void main(String[] args) {
    DBOSConfig dbosConfig = DBOSConfig.defaultsFromEnv("dbos-starter");
    String conductorUrl = System.getenv("DBOS_CONDUCTOR_URL");
    String conductorKey = System.getenv("DBOS_CONDUCTOR_KEY");
    if (conductorUrl != null && !conductorUrl.isBlank()) {
      dbosConfig = dbosConfig.withConductorDomain(conductorUrl);
    }
    if (conductorKey != null && !conductorKey.isBlank()) {
      dbosConfig = dbosConfig.withConductorKey(conductorKey);
    }
    DBOS dbos = new DBOS(dbosConfig);
    Example proxy = dbos.registerProxy(Example.class, new ExampleImpl(dbos));

    Javalin.create(config -> {
          config.events.serverStarting(dbos::launch);
          config.events.serverStopping(dbos::shutdown);
          config.routes.get("/", ctx -> {
            String name = ctx.queryParam("name");
            if (name == null || name.isBlank()) {
              name = "world";
            }
            ctx.result(proxy.workflow(name));
          });
        })
        .start(8000);
  }
}

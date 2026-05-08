package org.example;

import dev.dbos.transact.DBOS;
import dev.dbos.transact.config.DBOSConfig;
import dev.dbos.transact.workflow.Workflow;
import io.javalin.Javalin;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

interface Example {
  String workflow(String name);
}

class ExampleImpl implements Example {
  private static final Logger logger = LoggerFactory.getLogger(ExampleImpl.class);
  private final DBOS dbos;

  ExampleImpl(DBOS dbos) {
    this.dbos = dbos;
  }

  private int stepOne(String name) {
    logger.info("Hello {}", name);
    logger.info("Step one completed");
    return name.length();
  }

  private void stepTwo(String name, int nameLength) {
    logger.info("Step two completed for {}; the name has {} characters.", name, nameLength);
  }

  @Override
  @Workflow
  public String workflow(String name) {
    logger.info("Starting workflow for {}", name);
    int nameLength = dbos.runStep(() -> stepOne(name), "step_one");

    Path existingFile = Path.of("existing.txt");
    if (Files.notExists(existingFile)) {
      logger.warn("existing.txt missing; creating it and exiting to simulate a crash");
      try {
        Files.createFile(existingFile);
      } catch (IOException e) {
        throw new RuntimeException(e);
      }
      System.exit(1);
    }

    dbos.runStep(() -> stepTwo(name, nameLength), "step_two");
    logger.info("Completed workflow for {}", name);
    return "workflow executed";
  }
}

public class App {
  private static final Logger logger = LoggerFactory.getLogger(App.class);

  private static boolean envFlag(String name, boolean defaultValue) {
    String raw = System.getenv(name);
    if (raw == null) {
      return defaultValue;
    }
    return switch (raw.trim().toLowerCase()) {
      case "1", "true", "yes", "on" -> true;
      default -> false;
    };
  }

  private static void configureLogging() {
    String level = System.getenv().getOrDefault("APP_LOG_LEVEL", "info").toLowerCase();
    System.setProperty("org.slf4j.simpleLogger.defaultLogLevel", level);
    System.setProperty("org.slf4j.simpleLogger.log.dev.dbos.transact.conductor", "warn");
    System.setProperty("org.slf4j.simpleLogger.showDateTime", "false");
    System.setProperty("org.slf4j.simpleLogger.showThreadName", "false");
    System.setProperty("org.slf4j.simpleLogger.showLogName", "false");
    System.setProperty("org.slf4j.simpleLogger.showShortLogName", "true");
  }

  public static void main(String[] args) {
    configureLogging();
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

    boolean accessLog = envFlag("APP_ACCESS_LOG", false);

    Javalin.create(config -> {
          config.http.defaultContentType = "text/plain";
          if (accessLog) {
            config.bundledPlugins.enableDevLogging();
          }
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

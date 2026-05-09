package org.example;

import dev.dbos.transact.DBOS;
import dev.dbos.transact.config.DBOSConfig;
import io.javalin.Javalin;
import java.util.List;
import java.util.Map;

public class App {

  @SuppressWarnings("SameParameterValue")
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
    try (DBOS dbos = new DBOS(dbosConfig)) {

      MySteps proxySteps = dbos.registerProxy(MySteps.class, new MyStepsImpl());
      MyWorkflow proxyWorkflow = dbos.registerProxy(MyWorkflow.class, new MyWorkflowImpl(proxySteps));

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
                  WorkflowInput input =
                          new WorkflowInput(
                                  name,
                                  List.of(name.toUpperCase(), new StringBuilder(name).reverse().toString()),
                                  Map.of("primary", name.length(), "secondary", Math.max(1, name.length() / 2)));
                  ctx.result(proxyWorkflow.runWorkflow(input));
                });
              })
              .start(8000);
    }
  }
}

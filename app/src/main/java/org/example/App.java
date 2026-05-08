package org.example;

import dev.dbos.transact.DBOS;
import dev.dbos.transact.config.DBOSConfig;
import dev.dbos.transact.workflow.Workflow;
import io.javalin.Javalin;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

record WorkflowInput(String name, List<String> aliases, Map<String, Integer> weights) {}

record StepOneResult(String greeting, int nameLength, Map<String, Integer> metrics) {}

interface Example {
  String workflow(WorkflowInput input);
}

class ExampleImpl implements Example {
  private static final Logger logger = LoggerFactory.getLogger(ExampleImpl.class);
  private final DBOS dbos;

  ExampleImpl(DBOS dbos) {
    this.dbos = dbos;
  }

  private StepOneResult stepOne(WorkflowInput input) {
    logger.info("Hello {}", input.name());
    logger.info("Step one completed");
    return new StepOneResult(
        "Hello " + input.name(),
        input.name().length(),
        Map.of(
            "nameLength", input.name().length(),
            "aliasCount", input.aliases().size(),
            "weightCount", input.weights().size()));
  }

  private void stepTwo(WorkflowInput input, StepOneResult result) {
    logger.info(
        "Step two completed for {}; the name has {} characters.",
        input.name(),
        result.nameLength());
  }

  @Override
  @Workflow
  public String workflow(WorkflowInput input) {
    logger.info("Starting workflow for {}", input.name());
    StepOneResult stepOneResult = dbos.runStep(() -> stepOne(input), "step_one");

    if ("poison".equals(input.name())) {
      logger.warn("poison input received; exiting to simulate a crash");
      System.exit(1);
    }

    dbos.runStep(() -> stepTwo(input, stepOneResult), "step_two");
    logger.info("Completed workflow for {}", input.name());
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
            WorkflowInput input =
                new WorkflowInput(
                    name,
                    List.of(name.toUpperCase(), new StringBuilder(name).reverse().toString()),
                    Map.of("primary", name.length(), "secondary", Math.max(1, name.length() / 2)));
            ctx.result(proxy.workflow(input));
          });
        })
        .start(8000);
  }
}

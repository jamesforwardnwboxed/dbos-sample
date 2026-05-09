package org.example.dbos.micronaut;

import dev.dbos.transact.config.DBOSConfig;
import io.micronaut.context.ApplicationContext;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DbosConfigurationPropertiesTest {

    @Test
    void bindsDbosConfigurationIntoFactoryInputs() {
        Map<String, Object> properties = new LinkedHashMap<>();
        properties.put("micronaut.application.name", "fallback-name");
        properties.put("dbos.lifecycle.enabled", false);
        properties.put("dbos.application.name", "dbos-starter");
        properties.put("dbos.application.version", "1.2.3");
        properties.put("dbos.datasource.url", "jdbc:postgresql://localhost:5432/dbos_starter");
        properties.put("dbos.datasource.username", "postgres");
        properties.put("dbos.datasource.password", "dbos");
        properties.put("dbos.datasource.schema", "public");
        properties.put("dbos.datasource.migrate", false);
        properties.put("dbos.conductor.domain", "ws://control-plane:8001");
        properties.put("dbos.conductor.key", "local-conductor-key");
        properties.put("dbos.enable-patching", true);
        properties.put("dbos.scheduler-polling-interval", "15s");
        properties.put("dbos.admin-server.enabled", true);
        properties.put("dbos.admin-server.port", 3010);
        properties.put("dbos.listen-queues[0]", "alpha");
        properties.put("dbos.listen-queues[1]", "beta");

        try (ApplicationContext context = ApplicationContext.run(properties)) {
            DbosApplicationProperties application = context.getBean(DbosApplicationProperties.class);
            DbosDatasourceProperties datasource = context.getBean(DbosDatasourceProperties.class);
            DbosConductorProperties conductor = context.getBean(DbosConductorProperties.class);
            DbosAdminServerProperties adminServer = context.getBean(DbosAdminServerProperties.class);
            DbosProperties dbos = context.getBean(DbosProperties.class);
            DBOSConfig config = context.getBean(DBOSConfig.class);

            assertEquals("dbos-starter", application.getName());
            assertEquals("1.2.3", application.getVersion());

            assertEquals("jdbc:postgresql://localhost:5432/dbos_starter", datasource.getUrl());
            assertEquals("postgres", datasource.getUsername());
            assertEquals("dbos", datasource.getPassword());
            assertEquals("public", datasource.getSchema());
            assertFalse(datasource.isMigrate());

            assertEquals("ws://control-plane:8001", conductor.getDomain());
            assertEquals("local-conductor-key", conductor.getKey());

            assertTrue(adminServer.isEnabled());
            assertEquals(3010, adminServer.getPort());

            assertNull(dbos.getExecutorId());
            assertTrue(dbos.isEnablePatching());
            assertEquals(Duration.ofSeconds(15), dbos.getSchedulerPollingInterval());
            assertEquals(2, dbos.getListenQueues().size());
            assertEquals("alpha", dbos.getListenQueues().get(0));
            assertEquals("beta", dbos.getListenQueues().get(1));

            assertEquals("dbos-starter", config.appName());
            assertEquals("jdbc:postgresql://localhost:5432/dbos_starter", config.databaseUrl());
            assertEquals("postgres", config.dbUser());
            assertEquals("dbos", config.dbPassword());
            assertEquals("public", config.databaseSchema());
            assertFalse(config.migrate());
            assertEquals("ws://control-plane:8001", config.conductorDomain());
            assertEquals("local-conductor-key", config.conductorKey());
            assertEquals("1.2.3", config.appVersion());
            assertNull(config.executorId());
            assertTrue(config.enablePatching());
            assertEquals(Duration.ofSeconds(15), config.schedulerPollingInterval());
            assertTrue(config.adminServer());
            assertEquals(3010, config.adminServerPort());
            assertEquals(java.util.Set.of("alpha", "beta"), config.listenQueues());
        }
    }
}

package org.example.dbos.micronaut;

import dev.dbos.transact.DBOS;
import dev.dbos.transact.config.DBOSConfig;
import io.micronaut.context.BeanContext;
import io.micronaut.context.annotation.Factory;
import io.micronaut.context.annotation.Value;
import jakarta.inject.Singleton;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.Objects;

@Factory
public class DbosConfiguration {

    @Singleton
    public DBOSConfig dbosConfig(DbosProperties properties,
                                 DbosApplicationProperties applicationProperties,
                                 DbosDatasourceProperties datasourceProperties,
                                 DbosConductorProperties conductorProperties,
                                 DbosAdminServerProperties adminServerProperties,
                                 @Value("${micronaut.application.name:}") String micronautAppName,
                                 BeanContext beanContext) {
        String appName = applicationProperties.getName();
        if (appName == null || appName.isBlank()) {
            appName = micronautAppName;
        }
        Objects.requireNonNull(appName, "neither dbos.application.name nor micronaut.application.name are set");

        DBOSConfig config = DBOSConfig.defaults(appName);
        if (datasourceProperties.getUrl() != null && !datasourceProperties.getUrl().isBlank()) {
            config = config.withDatabaseUrl(datasourceProperties.getUrl());
        }
        if (datasourceProperties.getUsername() != null && !datasourceProperties.getUsername().isBlank()) {
            config = config.withDbUser(datasourceProperties.getUsername());
        }
        if (datasourceProperties.getPassword() != null && !datasourceProperties.getPassword().isBlank()) {
            config = config.withDbPassword(datasourceProperties.getPassword());
        }
        if (datasourceProperties.getSchema() != null && !datasourceProperties.getSchema().isBlank()) {
            config = config.withDatabaseSchema(datasourceProperties.getSchema());
        }
        if (conductorProperties.getKey() != null && !conductorProperties.getKey().isBlank()) {
            config = config.withConductorKey(conductorProperties.getKey());
        }
        if (conductorProperties.getDomain() != null && !conductorProperties.getDomain().isBlank()) {
            config = config.withConductorDomain(conductorProperties.getDomain());
        }
        if (applicationProperties.getVersion() != null && !applicationProperties.getVersion().isBlank()) {
            config = config.withAppVersion(applicationProperties.getVersion());
        }
        if (properties.getExecutorId() != null && !properties.getExecutorId().isBlank()) {
            config = config.withExecutorId(properties.getExecutorId());
        }
        if (properties.getSchedulerPollingInterval() != null) {
            config = config.withSchedulerPollingInterval(properties.getSchedulerPollingInterval());
        }
        config = config.withAdminServer(adminServerProperties.isEnabled());
        config = config.withAdminServerPort(adminServerProperties.getPort());
        config = config.withMigrate(datasourceProperties.isMigrate());
        config = config.withEnablePatching(properties.isEnablePatching());
        if (!properties.getListenQueues().isEmpty()) {
            config = config.withListenQueues(properties.getListenQueues().toArray(String[]::new));
        }

        for (DbosConfigCustomizer customizer : beanContext.getBeansOfType(DbosConfigCustomizer.class)) {
            config = customizer.customize(config);
        }
        return config;
    }

    @Singleton
    public DBOS dbos(DBOSConfig config, BeanContext beanContext) {
        if (config.databaseUrl() == null && config.dataSource() == null) {
            beanContext.findBean(DataSource.class).ifPresent(dataSource -> {
                validatePostgresDataSource(dataSource);
            });

            DataSource dataSource = beanContext.findBean(DataSource.class).orElse(null);
            if (dataSource != null) {
                config = config.withDataSource(dataSource);
            }
        } else if (config.dataSource() != null) {
            validatePostgresDataSource(config.dataSource());
        }
        return new DBOS(config);
    }

    private static void validatePostgresDataSource(DataSource dataSource) {
        try (Connection connection = dataSource.getConnection()) {
            String productName = connection.getMetaData().getDatabaseProductName();
            if (!productName.toLowerCase().contains("postgresql")) {
                throw new IllegalStateException(
                        "DBOS requires a PostgreSQL datasource, but the provided datasource reports: " + productName);
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Failed to validate DBOS datasource", e);
        }
    }
}

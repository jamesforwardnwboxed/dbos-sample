package org.example.dbos.micronaut;

import dev.dbos.transact.config.DBOSConfig;

@FunctionalInterface
public interface DbosConfigCustomizer {
    DBOSConfig customize(DBOSConfig config);
}

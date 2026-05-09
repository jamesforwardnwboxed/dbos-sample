package org.example.dbos.micronaut;

import dev.dbos.transact.DBOS;
import io.micronaut.context.annotation.Requires;
import io.micronaut.context.event.ApplicationEventListener;
import io.micronaut.context.event.ShutdownEvent;
import io.micronaut.context.event.StartupEvent;
import jakarta.inject.Singleton;

@Singleton
@Requires(property = "dbos.lifecycle.enabled", notEquals = "false")
public class DbosLifecycleListener implements ApplicationEventListener<StartupEvent> {

    private final DBOS dbos;

    public DbosLifecycleListener(DBOS dbos) {
        this.dbos = dbos;
    }

    @Override
    public void onApplicationEvent(StartupEvent event) {
        dbos.launch();
    }

    @Singleton
    @Requires(property = "dbos.lifecycle.enabled", notEquals = "false")
    public static class ShutdownListener implements ApplicationEventListener<ShutdownEvent> {

        private final DBOS dbos;

        public ShutdownListener(DBOS dbos) {
            this.dbos = dbos;
        }

        @Override
        public void onApplicationEvent(ShutdownEvent event) {
            dbos.shutdown();
        }
    }
}

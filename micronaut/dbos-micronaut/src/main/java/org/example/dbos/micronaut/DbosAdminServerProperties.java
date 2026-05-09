package org.example.dbos.micronaut;

import io.micronaut.context.annotation.ConfigurationProperties;

@ConfigurationProperties("dbos.admin-server")
public class DbosAdminServerProperties {

    private boolean enabled;
    private int port = 3001;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }
}

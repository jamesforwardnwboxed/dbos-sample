package org.example.dbos.micronaut;

import io.micronaut.context.annotation.ConfigurationProperties;

@ConfigurationProperties("dbos.application")
public class DbosApplicationProperties {

    private String name;
    private String version;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }
}

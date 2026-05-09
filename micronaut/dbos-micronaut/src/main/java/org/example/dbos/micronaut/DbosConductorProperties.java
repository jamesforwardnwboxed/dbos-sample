package org.example.dbos.micronaut;

import io.micronaut.context.annotation.ConfigurationProperties;

@ConfigurationProperties("dbos.conductor")
public class DbosConductorProperties {

    private String key;
    private String domain;

    public String getKey() {
        return key;
    }

    public void setKey(String key) {
        this.key = key;
    }

    public String getDomain() {
        return domain;
    }

    public void setDomain(String domain) {
        this.domain = domain;
    }
}

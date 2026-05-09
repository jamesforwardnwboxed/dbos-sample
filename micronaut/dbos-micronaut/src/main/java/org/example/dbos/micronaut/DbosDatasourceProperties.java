package org.example.dbos.micronaut;

import io.micronaut.context.annotation.ConfigurationProperties;

@ConfigurationProperties("dbos.datasource")
public class DbosDatasourceProperties {

    private String url;
    private String username;
    private String password;
    private String schema;
    private boolean migrate = true;

    public String getUrl() {
        return url;
    }

    public void setUrl(String url) {
        this.url = url;
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public String getSchema() {
        return schema;
    }

    public void setSchema(String schema) {
        this.schema = schema;
    }

    public boolean isMigrate() {
        return migrate;
    }

    public void setMigrate(boolean migrate) {
        this.migrate = migrate;
    }
}

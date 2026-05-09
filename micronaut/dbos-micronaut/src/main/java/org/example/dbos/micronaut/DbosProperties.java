package org.example.dbos.micronaut;

import io.micronaut.context.annotation.ConfigurationProperties;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

@ConfigurationProperties("dbos")
public class DbosProperties {

    private String executorId;
    private boolean enablePatching = false;
    private List<String> listenQueues = new ArrayList<>();
    private Duration schedulerPollingInterval;

    public String getExecutorId() {
        return executorId;
    }

    public void setExecutorId(String executorId) {
        this.executorId = executorId;
    }

    public boolean isEnablePatching() {
        return enablePatching;
    }

    public void setEnablePatching(boolean enablePatching) {
        this.enablePatching = enablePatching;
    }

    public List<String> getListenQueues() {
        return listenQueues;
    }

    public void setListenQueues(List<String> listenQueues) {
        this.listenQueues = listenQueues;
    }

    public Duration getSchedulerPollingInterval() {
        return schedulerPollingInterval;
    }

    public void setSchedulerPollingInterval(Duration schedulerPollingInterval) {
        this.schedulerPollingInterval = schedulerPollingInterval;
    }
}

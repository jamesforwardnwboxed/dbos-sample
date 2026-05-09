package org.example;

import io.micronaut.http.MediaType;
import io.micronaut.http.annotation.Controller;
import io.micronaut.http.annotation.Get;
import io.micronaut.http.annotation.QueryValue;

import java.util.List;
import java.util.Map;

@Controller("/")
public class WorkflowController {

    private final WorkflowService workflowService;

    public WorkflowController(WorkflowService workflowService) {
        this.workflowService = workflowService;
    }

    @Get(produces = MediaType.TEXT_PLAIN)
    public String runWorkflow(@QueryValue(defaultValue = "world") String name) {
        WorkflowInput input = new WorkflowInput(
                name,
                List.of(name.toUpperCase(), new StringBuilder(name).reverse().toString()),
                Map.of("primary", name.length(), "secondary", Math.max(1, name.length() / 2)));
        return workflowService.runWorkflow(input);
    }
}

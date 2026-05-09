package org.example;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
class WorkflowController {

    private final WorkflowService workflowService;

    WorkflowController(WorkflowService workflowService) {
        this.workflowService = workflowService;
    }

    @GetMapping(path = "/", produces = MediaType.TEXT_PLAIN_VALUE)
    String runWorkflow(@RequestParam(defaultValue = "world") String name) {
        WorkflowInput input = new WorkflowInput(
                name,
                List.of(name.toUpperCase(), new StringBuilder(name).reverse().toString()),
                Map.of("primary", name.length(), "secondary", Math.max(1, name.length() / 2)));
        return workflowService.runWorkflow(input);
    }
}

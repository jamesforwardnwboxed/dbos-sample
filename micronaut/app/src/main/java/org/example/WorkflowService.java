package org.example;

import dev.dbos.transact.workflow.SerializationStrategy;
import dev.dbos.transact.workflow.Workflow;
import jakarta.inject.Singleton;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Singleton
public class WorkflowService {

    private static final Logger logger = LoggerFactory.getLogger(WorkflowService.class);

    private final StepService stepService;

    public WorkflowService(StepService stepService) {
        this.stepService = stepService;
    }

    @Workflow(name = "basic-workflow", serializationStrategy = SerializationStrategy.PORTABLE)
    public String runWorkflow(WorkflowInput input) {
        logger.info("Starting workflow for {}", input.name());
        StepOneResult stepOneResult = stepService.stepOne(input);
        stepService.stepTwo(input, stepOneResult);
        logger.info("Completed workflow for {}", input.name());
        return "workflow executed";
    }
}

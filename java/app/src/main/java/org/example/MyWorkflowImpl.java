package org.example;

import dev.dbos.transact.workflow.Workflow;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

class MyWorkflowImpl implements MyWorkflow {
    private static final Logger logger = LoggerFactory.getLogger(MyWorkflowImpl.class);

    private final MySteps mySteps;

    public MyWorkflowImpl(MySteps mySteps) {
        this.mySteps = mySteps;
    }

    @Workflow(name = "basic-workflow")
    public String runWorkflow(WorkflowInput input) {
        logger.info("Starting workflow for {}", input.name());
        StepOneResult stepOneResult = mySteps.stepOne(input);
        mySteps.stepTwo(input, stepOneResult);
        logger.info("Completed workflow for {}", input.name());
        return "workflow executed";
    }
}

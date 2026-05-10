package org.example;

import dev.dbos.transact.workflow.Step;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.Map;

@Service
public class StepService {

    private static final Logger logger = LoggerFactory.getLogger(StepService.class);

    @Step(name = "step_one")
    public StepOneResult stepOne(WorkflowInput input) {
        logger.info("Hello {}", input.name());
        logger.info("Step one completed");
        return new StepOneResult(
                "Hello " + input.name(),
                input.name().length(),
                Map.of(
                        "nameLength", input.name().length(),
                        "aliasCount", input.aliases().size(),
                        "weightCount", input.weights().size()));
    }

    @Step(name = "step_two")
    public void stepTwo(WorkflowInput input, StepOneResult result) {
        if ("poison".equals(input.name())) {
            logger.warn("poison input received; failing step two");
            throw new RuntimeException("poison input received");
        }

        logger.info(
                "Step two completed for {}; the name has {} characters.",
                input.name(),
                result.nameLength());
    }
}

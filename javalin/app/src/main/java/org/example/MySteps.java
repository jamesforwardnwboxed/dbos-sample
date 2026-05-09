package org.example;

interface MySteps {

    StepOneResult stepOne(WorkflowInput input);

    void stepTwo(WorkflowInput input, StepOneResult result);
}

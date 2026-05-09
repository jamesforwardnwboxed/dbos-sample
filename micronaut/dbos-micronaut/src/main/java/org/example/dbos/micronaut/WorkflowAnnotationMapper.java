package org.example.dbos.micronaut;

import io.micronaut.core.annotation.AnnotationValue;
import io.micronaut.inject.visitor.VisitorContext;

import java.util.List;

public final class WorkflowAnnotationMapper extends DbosAnnotationMapper {

    @Override
    public String getName() {
        return "dev.dbos.transact.workflow.Workflow";
    }

    @Override
    protected List<AnnotationValue<?>> doMap(AnnotationValue<java.lang.annotation.Annotation> annotation,
                                             VisitorContext visitorContext) {
        return List.of(
                AnnotationValue.builder(DbosWorkflowAdvice.class).build(),
                AnnotationValue.builder(DbosWorkflowExecutable.class).build()
        );
    }
}

package org.example.dbos.micronaut;

import io.micronaut.core.annotation.AnnotationValue;
import io.micronaut.inject.visitor.VisitorContext;

import java.util.List;

public final class StepAnnotationMapper extends DbosAnnotationMapper {

    @Override
    public String getName() {
        return "dev.dbos.transact.workflow.Step";
    }

    @Override
    protected List<AnnotationValue<?>> doMap(AnnotationValue<java.lang.annotation.Annotation> annotation,
                                             VisitorContext visitorContext) {
        return List.of(AnnotationValue.builder(DbosStepAdvice.class).build());
    }
}

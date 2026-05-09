package org.example.dbos.micronaut;

import io.micronaut.core.annotation.AnnotationValue;
import io.micronaut.inject.annotation.NamedAnnotationMapper;
import io.micronaut.inject.visitor.VisitorContext;

import java.util.List;

public abstract class DbosAnnotationMapper implements NamedAnnotationMapper {

    @Override
    public final List<AnnotationValue<?>> map(AnnotationValue<java.lang.annotation.Annotation> annotation,
                                              VisitorContext visitorContext) {
        return doMap(annotation, visitorContext);
    }

    protected abstract List<AnnotationValue<?>> doMap(
            AnnotationValue<java.lang.annotation.Annotation> annotation,
            VisitorContext visitorContext);
}

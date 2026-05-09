package org.example.dbos.micronaut;

import dev.dbos.transact.DBOS;
import dev.dbos.transact.workflow.Workflow;
import io.micronaut.context.BeanContext;
import io.micronaut.context.processor.ExecutableMethodProcessor;
import io.micronaut.inject.BeanDefinition;
import io.micronaut.inject.ExecutableMethod;
import jakarta.inject.Singleton;

import java.lang.reflect.Method;

@Singleton
public class DbosWorkflowMethodProcessor implements ExecutableMethodProcessor<DbosWorkflowExecutable> {

    private final DBOS dbos;
    private final BeanContext beanContext;

    public DbosWorkflowMethodProcessor(DBOS dbos, BeanContext beanContext) {
        this.dbos = dbos;
        this.beanContext = beanContext;
    }

    @Override
    public void process(BeanDefinition<?> beanDefinition, ExecutableMethod<?, ?> method) {
        Object bean = beanContext.getBean(beanDefinition.getBeanType());
        bean = DbosTargetResolver.unwrapTarget(bean);

        Method targetMethod = DbosTargetResolver.findTargetMethod(bean.getClass(), method);
        Workflow workflow = targetMethod.getAnnotation(Workflow.class);
        if (workflow == null) {
            return;
        }

        dbos.integration().registerWorkflow(workflow, bean, targetMethod, "");
    }
}

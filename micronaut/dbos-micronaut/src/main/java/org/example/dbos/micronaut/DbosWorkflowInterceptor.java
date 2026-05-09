package org.example.dbos.micronaut;

import dev.dbos.transact.DBOS;
import dev.dbos.transact.workflow.Workflow;
import io.micronaut.aop.InterceptorBean;
import io.micronaut.aop.MethodInterceptor;
import io.micronaut.aop.MethodInvocationContext;
import jakarta.inject.Singleton;

import java.lang.reflect.Method;

@Singleton
@InterceptorBean(DbosWorkflowAdvice.class)
public class DbosWorkflowInterceptor implements MethodInterceptor<Object, Object> {

    private final DBOS dbos;

    public DbosWorkflowInterceptor(DBOS dbos) {
        this.dbos = dbos;
    }

    @Override
    public Object intercept(MethodInvocationContext<Object, Object> context) {
        Object target = DbosTargetResolver.unwrapTarget(context.getTarget());
        Method method = DbosTargetResolver.findTargetMethod(target.getClass(), context.getTargetMethod());
        Workflow workflow = method.getAnnotation(Workflow.class);
        if (workflow == null) {
            return context.proceed();
        }

        try {
            return dbos.integration().runWorkflow(target, "", method, context.getParameterValues(), workflow);
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}

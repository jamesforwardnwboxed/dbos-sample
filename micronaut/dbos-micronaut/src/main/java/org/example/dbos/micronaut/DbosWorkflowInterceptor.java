package org.example.dbos.micronaut;

import dev.dbos.transact.DBOS;
import dev.dbos.transact.workflow.Workflow;
import io.micronaut.context.BeanContext;
import io.micronaut.context.Qualifier;
import io.micronaut.inject.BeanDefinition;
import io.micronaut.aop.InterceptorBean;
import io.micronaut.aop.MethodInterceptor;
import io.micronaut.aop.MethodInvocationContext;
import jakarta.inject.Singleton;

import java.lang.reflect.Method;

@Singleton
@InterceptorBean(DbosWorkflowAdvice.class)
public class DbosWorkflowInterceptor implements MethodInterceptor<Object, Object> {

    private final DBOS dbos;
    private final BeanContext beanContext;

    public DbosWorkflowInterceptor(DBOS dbos, BeanContext beanContext) {
        this.dbos = dbos;
        this.beanContext = beanContext;
    }

    @Override
    public Object intercept(MethodInvocationContext<Object, Object> context) {
        Object target = resolveTargetBean(context.getDeclaringType());
        Method method = DbosTargetResolver.findTargetMethod(target.getClass(), context.getExecutableMethod());
        Workflow workflow = method.getAnnotation(Workflow.class);
        if (workflow == null) {
            return context.proceed();
        }

        try {
            return dbos.integration().runWorkflow(target, null, method, context.getParameterValues(), workflow);
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private Object resolveTargetBean(Class<?> declaringType) {
        BeanDefinition<?> beanDefinition = beanContext.getBeanDefinition(declaringType);
        Qualifier qualifier = beanDefinition.getDeclaredQualifier();
        return beanContext.getProxyTargetBean((Class) declaringType, qualifier);
    }
}

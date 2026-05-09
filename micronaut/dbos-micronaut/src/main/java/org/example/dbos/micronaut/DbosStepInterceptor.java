package org.example.dbos.micronaut;

import dev.dbos.transact.DBOS;
import dev.dbos.transact.workflow.Step;
import dev.dbos.transact.workflow.StepOptions;
import io.micronaut.aop.InterceptorBean;
import io.micronaut.aop.MethodInterceptor;
import io.micronaut.aop.MethodInvocationContext;
import io.micronaut.context.BeanContext;
import io.micronaut.context.Qualifier;
import io.micronaut.inject.BeanDefinition;
import jakarta.inject.Singleton;

import java.lang.reflect.Method;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Singleton
@InterceptorBean(DbosStepAdvice.class)
public class DbosStepInterceptor implements MethodInterceptor<Object, Object> {

    private final DBOS dbos;
    private final BeanContext beanContext;
    private final Map<Method, StepOptions> stepCache = new ConcurrentHashMap<>();

    public DbosStepInterceptor(DBOS dbos, BeanContext beanContext) {
        this.dbos = dbos;
        this.beanContext = beanContext;
    }

    @Override
    public Object intercept(MethodInvocationContext<Object, Object> context) {
        Object target = resolveTargetBean(context.getDeclaringType());
        Method method = DbosTargetResolver.findTargetMethod(target.getClass(), context.getExecutableMethod());
        Step step = method.getAnnotation(Step.class);
        if (step == null) {
            return context.proceed();
        }

        StepOptions stepOptions = stepCache.computeIfAbsent(method, key -> StepOptions.create(step, key));

        try {
            return dbos.runStep(() -> {
                try {
                    return context.proceed();
                } catch (Exception e) {
                    throw e;
                } catch (Throwable throwable) {
                    throw new WrappedThrowableException(throwable);
                }
            }, stepOptions);
        } catch (WrappedThrowableException e) {
            throw e;
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

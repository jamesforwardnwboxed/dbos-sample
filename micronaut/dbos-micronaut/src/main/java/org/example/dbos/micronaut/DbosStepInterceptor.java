package org.example.dbos.micronaut;

import dev.dbos.transact.DBOS;
import dev.dbos.transact.workflow.Step;
import dev.dbos.transact.workflow.StepOptions;
import io.micronaut.aop.InterceptorBean;
import io.micronaut.aop.MethodInterceptor;
import io.micronaut.aop.MethodInvocationContext;
import jakarta.inject.Singleton;

import java.lang.reflect.Method;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Singleton
@InterceptorBean(DbosStepAdvice.class)
public class DbosStepInterceptor implements MethodInterceptor<Object, Object> {

    private final DBOS dbos;
    private final Map<Method, StepOptions> stepCache = new ConcurrentHashMap<>();

    public DbosStepInterceptor(DBOS dbos) {
        this.dbos = dbos;
    }

    @Override
    public Object intercept(MethodInvocationContext<Object, Object> context) {
        Method method = context.getTargetMethod();
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
}

package org.example.dbos.micronaut;

import io.micronaut.aop.InterceptedProxy;
import io.micronaut.inject.ExecutableMethod;

import java.lang.reflect.Method;
import java.util.Objects;

final class DbosTargetResolver {

    private DbosTargetResolver() {
    }

    static Object unwrapTarget(Object bean) {
        if (bean instanceof InterceptedProxy<?> interceptedProxy) {
            return interceptedProxy.interceptedTarget();
        }
        return bean;
    }

    static Method findTargetMethod(Class<?> beanClass, ExecutableMethod<?, ?> executableMethod) {
        Class<?> current = beanClass;
        Class<?>[] argumentTypes = executableMethod.getArgumentTypes();
        while (current != null && current != Object.class) {
            try {
                Method method = current.getDeclaredMethod(executableMethod.getMethodName(), argumentTypes);
                method.setAccessible(true);
                return method;
            } catch (NoSuchMethodException ignored) {
                current = current.getSuperclass();
            }
        }
        throw new IllegalStateException(
                "Could not resolve target workflow method %s on %s".formatted(
                        executableMethod.getMethodName(), Objects.requireNonNull(beanClass).getName()));
    }

    static Method findTargetMethod(Class<?> beanClass, Method interceptedMethod) {
        Class<?> current = beanClass;
        Class<?>[] argumentTypes = interceptedMethod.getParameterTypes();
        while (current != null && current != Object.class) {
            try {
                Method method = current.getDeclaredMethod(interceptedMethod.getName(), argumentTypes);
                method.setAccessible(true);
                return method;
            } catch (NoSuchMethodException ignored) {
                current = current.getSuperclass();
            }
        }
        throw new IllegalStateException(
                "Could not resolve target workflow method %s on %s".formatted(
                        interceptedMethod.getName(), Objects.requireNonNull(beanClass).getName()));
    }
}

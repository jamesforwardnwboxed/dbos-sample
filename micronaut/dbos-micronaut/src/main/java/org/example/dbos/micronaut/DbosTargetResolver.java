package org.example.dbos.micronaut;

import io.micronaut.aop.InterceptedProxy;
import io.micronaut.inject.ExecutableMethod;
import io.micronaut.inject.proxy.InterceptedBeanProxy;

import java.lang.annotation.Annotation;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Objects;

final class DbosTargetResolver {

    private DbosTargetResolver() {
    }

    static Object unwrapTarget(Object bean) {
        if (bean instanceof InterceptedProxy<?> interceptedProxy) {
            return interceptedProxy.interceptedTarget();
        }
        if (bean instanceof InterceptedBeanProxy<?> interceptedBeanProxy) {
            return interceptedBeanProxy.interceptedTarget();
        }
        try {
            Method interceptedTarget = bean.getClass().getMethod("interceptedTarget");
            interceptedTarget.setAccessible(true);
            Object target = interceptedTarget.invoke(bean);
            if (target != null) {
                return target;
            }
        } catch (NoSuchMethodException ignored) {
        } catch (IllegalAccessException | InvocationTargetException e) {
            throw new IllegalStateException("Failed to unwrap intercepted Micronaut target", e);
        }
        return bean;
    }

    static Method findTargetMethod(Class<?> beanClass, ExecutableMethod<?, ?> executableMethod) {
        return findTargetMethod(beanClass, executableMethod.getMethodName(), executableMethod.getArgumentTypes());
    }

    static Method findTargetMethod(Class<?> beanClass, Method interceptedMethod) {
        return findTargetMethod(beanClass, interceptedMethod.getName(), interceptedMethod.getParameterTypes());
    }

    private static Method findTargetMethod(Class<?> beanClass, String methodName, Class<?>[] argumentTypes) {
        Method fallback = null;
        Class<?> current = beanClass;
        while (current != null && current != Object.class) {
            try {
                Method method = current.getDeclaredMethod(methodName, argumentTypes);
                method.setAccessible(true);

                if (!isInterceptedSubclass(current) || hasDbosAnnotation(method)) {
                    return method;
                }

                if (fallback == null) {
                    fallback = method;
                }
            } catch (NoSuchMethodException ignored) {
            }
            current = current.getSuperclass();
        }

        if (fallback != null) {
            return fallback;
        }

        throw new IllegalStateException(
                "Could not resolve target workflow method %s on %s".formatted(
                        methodName, Objects.requireNonNull(beanClass).getName()));
    }

    private static boolean isInterceptedSubclass(Class<?> type) {
        return InterceptedProxy.class.isAssignableFrom(type) || type.getName().contains("$Intercepted");
    }

    private static boolean hasDbosAnnotation(Method method) {
        for (Annotation annotation : method.getDeclaredAnnotations()) {
            String annotationName = annotation.annotationType().getName();
            if (annotationName.equals("dev.dbos.transact.workflow.Workflow")
                    || annotationName.equals("dev.dbos.transact.workflow.Step")) {
                return true;
            }
        }
        return false;
    }
}

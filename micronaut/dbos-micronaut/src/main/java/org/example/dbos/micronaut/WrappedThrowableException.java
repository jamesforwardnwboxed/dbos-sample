package org.example.dbos.micronaut;

public class WrappedThrowableException extends RuntimeException {

    public WrappedThrowableException(Throwable wrappedThrowable) {
        super("Wrapped non-Exception throwable: " + validate(wrappedThrowable).getClass().getSimpleName(), wrappedThrowable);
    }

    private static Throwable validate(Throwable throwable) {
        if (throwable instanceof Exception) {
            throw new IllegalArgumentException("Should not wrap Exception types, only Error types");
        }
        return throwable;
    }

    public Throwable getWrappedThrowable() {
        return getCause();
    }
}

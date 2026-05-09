FROM gradle:9.5.0-jdk21 AS builder

WORKDIR /app

COPY settings.gradle.kts settings.gradle.kts
COPY build.gradle.kts build.gradle.kts
COPY dbos-micronaut dbos-micronaut
COPY app app

RUN gradle :app:installDist --no-daemon

FROM eclipse-temurin:21-jre

WORKDIR /app

COPY --from=builder /app/app/build/install/app /app

CMD ["/app/bin/app"]

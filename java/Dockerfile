FROM gradle:9.5.0-jdk21 AS builder

WORKDIR /app

COPY gradle gradle
COPY gradlew gradlew
COPY gradlew.bat gradlew.bat
COPY settings.gradle.kts settings.gradle.kts
COPY app app

RUN ./gradlew installDist --no-daemon

FROM eclipse-temurin:21-jre

WORKDIR /app

COPY --from=builder /app/app/build/install/app /app

CMD ["/app/bin/app"]

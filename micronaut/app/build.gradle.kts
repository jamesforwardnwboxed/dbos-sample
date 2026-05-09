plugins {
    id("io.micronaut.application")
}

micronaut {
    version("4.10.7")
    runtime("netty")
    testRuntime("junit5")
    processing {
        incremental(true)
        annotations.add("org.example.*")
    }
}

dependencies {
    annotationProcessor("io.micronaut:micronaut-inject-java")
    annotationProcessor("io.micronaut:micronaut-http-validation")
    annotationProcessor(project(":dbos-micronaut"))

    implementation(project(":dbos-micronaut"))
    implementation("io.micronaut:micronaut-http-server-netty")
    implementation("io.micronaut:micronaut-jackson-databind")
    implementation("io.micronaut:micronaut-runtime")
    implementation("ch.qos.logback:logback-classic:1.5.18")
    runtimeOnly("org.postgresql:postgresql:42.7.5")
    runtimeOnly("org.yaml:snakeyaml")

    testImplementation("io.micronaut.test:micronaut-test-junit5")
    testImplementation("org.junit.jupiter:junit-jupiter-api:5.12.2")
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.12.2")
}

application {
    mainClass = "org.example.Application"
}

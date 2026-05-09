plugins {
    id("io.micronaut.library")
}

micronaut {
    version("4.10.7")
    processing {
        incremental(true)
        annotations.add("org.example.dbos.micronaut.*")
    }
}

dependencies {
    annotationProcessor("io.micronaut:micronaut-inject-java")
    annotationProcessor("io.micronaut:micronaut-core-processor")

    api("dev.dbos:transact:0.8.0")
    api("io.micronaut:micronaut-context")
    api("io.micronaut:micronaut-aop")
    api("jakarta.inject:jakarta.inject-api")
    compileOnly("io.micronaut:micronaut-core-processor")

    compileOnly("org.slf4j:slf4j-api:2.0.17")

    testImplementation("io.micronaut.test:micronaut-test-junit5")
    testImplementation("io.micronaut:micronaut-inject")
    testImplementation("org.junit.jupiter:junit-jupiter-api:5.12.2")
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.12.2")
}

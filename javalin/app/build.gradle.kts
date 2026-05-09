plugins {
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("dev.dbos:transact:0.8.0")
    implementation("io.javalin:javalin:7.2.0")
    implementation("org.slf4j:slf4j-simple:2.0.17")
}

application {
    mainClass = "org.example.App"
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

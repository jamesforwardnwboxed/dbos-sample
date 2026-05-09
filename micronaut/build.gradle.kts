import org.gradle.api.plugins.JavaPluginExtension

plugins {
    id("io.micronaut.application") version "4.5.3" apply false
    id("io.micronaut.library") version "4.5.3" apply false
}

allprojects {
    group = "org.example"
    version = "0.1.0"

    repositories {
        mavenCentral()
    }
}

subprojects {
    apply(plugin = "java")

    extensions.configure<JavaPluginExtension> {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    tasks.withType<Test> {
        useJUnitPlatform()
    }
}

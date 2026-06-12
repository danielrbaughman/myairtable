plugins {
    // Auto-provisions the JDK named by the toolchain block (we pin 21) when absent.
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

rootProject.name = "myairtable-java-static"

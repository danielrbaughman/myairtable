// Unit-test harness for the hand-written Kotlin static runtime (static/kotlin/).
// The main source set points directly at static/kotlin so the runtime is compiled
// and tested in place — no symlinks, no copying.
//
// Version pins (K-F1 decision record):
//   Kotlin 2.2.20 · kotlinx.serialization 1.9.0 · kotlinx-coroutines 1.10.2 · Ktor 3.2.3

plugins {
    kotlin("jvm") version "2.2.20"
    kotlin("plugin.serialization") version "2.2.20"
}

kotlin {
    jvmToolchain(21)
}

repositories {
    mavenCentral()
}

sourceSets {
    main {
        kotlin.srcDir("../../static/kotlin")
    }
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2")
    implementation("io.ktor:ktor-client-core:3.2.3")
    implementation("io.ktor:ktor-client-cio:3.2.3")
    implementation("io.ktor:ktor-client-content-negotiation:3.2.3")
    implementation("io.ktor:ktor-serialization-kotlinx-json:3.2.3")

    testImplementation(kotlin("test"))
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
}

tasks.test {
    useJUnitPlatform()
}

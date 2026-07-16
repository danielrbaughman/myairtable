// Unit-test harness for the hand-written Java static runtime (src/myairtable/static/java/).
// The main source set points directly at src/myairtable/static/java so the runtime is compiled
// and tested in place — no symlinks, no copying. src/proofmain holds the
// package-vs-directory compile proof (java-plan-v2 §2.3.5): a file declaring
// `package myairtable` from a non-matching directory, mirroring the generated
// dynamic/{models,...} layout.
//
// Version pins (J-F1 decision record):
//   Jackson databind 2.18.2 · JUnit 5 (BOM 5.11.4) · toolchain 21
//
// jackson-datatype-jsr310 is DELIBERATELY absent: its Duration codec would
// shadow AirtableJacksonModule's numeric-seconds codec (java-plan-v2 §2.3.6).

plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

sourceSets {
    main {
        java.srcDir("../../src/myairtable/static/java")
        java.srcDir("src/proofmain")
    }
}

dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:2.18.2")

    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
    testLogging {
        events("passed", "skipped", "failed")
    }
}

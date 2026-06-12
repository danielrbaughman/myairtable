package myairtable

import kotlin.test.Test
import kotlin.test.assertEquals

/** Proves the Gradle harness compiles static/kotlin and runs JUnit 5 tests. */
class TestHarness {
    @Test
    fun staticRuntimeIsOnTheClasspath() {
        assertEquals("0.0.1-dev", MyAirtableRuntimeInfo.VERSION)
    }
}

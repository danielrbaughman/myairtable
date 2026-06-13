package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

/** Proves the Gradle harness compiles static/java and runs JUnit 5 tests. */
class TestHarness {

  @Test
  void staticRuntimeIsOnTheClasspath() {
    assertEquals("0.0.1-dev", MyAirtableRuntimeInfo.VERSION);
  }
}

package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.BooleanNode;
import com.fasterxml.jackson.databind.node.DoubleNode;
import com.fasterxml.jackson.databind.node.LongNode;
import com.fasterxml.jackson.databind.node.NullNode;
import com.fasterxml.jackson.databind.node.TextNode;
import org.junit.jupiter.api.Test;

/**
 * J8.10 — Formula-function semantics of {@link AirtableRuntime}. Port of the Kotlin twin
 * (tests/kotlin_static TestAirtableRuntime, K2.9); parity also with Swift TestAirtableRuntime and
 * tests/test_airtable_runtime.rs (formula sections). Coercion-helper basics (N/S/A/V/isTruthy) live
 * in TestValueCoercion and are not repeated here.
 *
 * <p>Integral results use {@link LongNode} (the Java runtime's canonical integer node, mirroring
 * Kotlin's {@code JsonPrimitive(Long)}; kotlinx primitives compare by content so Int-vs-Long was
 * invisible there, while Jackson equality is node-type strict).
 */
class TestAirtableRuntime {

  private static JsonNode i(long value) {
    return LongNode.valueOf(value);
  }

  private static JsonNode f(double value) {
    return DoubleNode.valueOf(value);
  }

  private static JsonNode s(String value) {
    return TextNode.valueOf(value);
  }

  private static JsonNode b(boolean value) {
    return BooleanNode.valueOf(value);
  }

  private static JsonNode nul() {
    return NullNode.getInstance();
  }

  private static JsonNode arr(JsonNode... items) {
    ArrayNode node = AirtableJson.MAPPER.createArrayNode();
    for (JsonNode item : items) {
      node.add(item);
    }
    return node;
  }

  private static void assertNaN(JsonNode value) {
    assertTrue(Double.isNaN(AirtableRuntime.N(value)), "expected NaN, got " + value);
  }

  // region Logic (J8.2)

  @Test
  void ifTrue() {
    assertEquals(i(1), AirtableRuntime.IF(b(true), i(1), i(2)));
  }

  @Test
  void ifFalse() {
    assertEquals(i(2), AirtableRuntime.IF(b(false), i(1), i(2)));
  }

  @Test
  void ifNullIsFalse() {
    assertEquals(i(2), AirtableRuntime.IF(null, i(1), i(2)));
  }

  @Test
  void ifZeroIsFalsy() {
    assertEquals(s("no"), AirtableRuntime.IF(i(0), s("yes"), s("no")));
  }

  @Test
  void ifNumberIsTruthy() {
    assertEquals(s("yes"), AirtableRuntime.IF(i(1), s("yes"), s("no")));
  }

  @Test
  void ifEmptyStringIsFalsy() {
    assertEquals(s("no"), AirtableRuntime.IF(s(""), s("yes"), s("no")));
  }

  @Test
  void switchMatch() {
    assertEquals(s("two"), AirtableRuntime.SWITCH(i(2), null, i(1), s("one"), i(2), s("two")));
  }

  @Test
  void switchDefault() {
    assertEquals(s("other"), AirtableRuntime.SWITCH(i(99), s("other"), i(1), s("one")));
  }

  @Test
  void switchNoMatchNoDefault() {
    assertEquals(nul(), AirtableRuntime.SWITCH(i(99), null, i(1), s("one")));
  }

  @Test
  void blankIsNull() {
    assertEquals(nul(), AirtableRuntime.BLANK());
  }

  @Test
  void trueIsBool() {
    assertEquals(b(true), AirtableRuntime.TRUE());
  }

  @Test
  void falseIsBool() {
    assertEquals(b(false), AirtableRuntime.FALSE());
  }

  @Test
  void iserrorNaN() {
    assertEquals(b(true), AirtableRuntime.ISERROR(f(Double.NaN)));
  }

  @Test
  void iserrorNormal() {
    assertEquals(b(false), AirtableRuntime.ISERROR(i(5)));
  }

  @Test
  void iserrorNullIsFalse() {
    // Swift parity: only NaN doubles are errors (the Rust runtime differs here).
    assertEquals(b(false), AirtableRuntime.ISERROR(nul()));
    assertEquals(b(false), AirtableRuntime.ISERROR(null));
  }

  @Test
  void errorIsNaN() {
    assertNaN(AirtableRuntime.ERROR());
    assertEquals(b(true), AirtableRuntime.ISERROR(AirtableRuntime.ERROR(s("boom"))));
  }

  // endregion

  // region Math (J8.2)

  @Test
  void sumBasic() {
    assertEquals(i(6), AirtableRuntime.SUM(i(1), i(2), i(3)));
  }

  @Test
  void sumWithArray() {
    assertEquals(i(6), AirtableRuntime.SUM(arr(i(1), i(2)), i(3)));
  }

  @Test
  void sumWithStrings() {
    assertEquals(i(6), AirtableRuntime.SUM(i(1), s("5")));
  }

  @Test
  void averageBasic() {
    assertEquals(i(3), AirtableRuntime.AVERAGE(i(2), i(4)));
  }

  @Test
  void averageThree() {
    assertEquals(i(20), AirtableRuntime.AVERAGE(i(10), i(20), i(30)));
  }

  @Test
  void averageEmptyIsNaN() {
    assertNaN(AirtableRuntime.AVERAGE());
  }

  @Test
  void minBasic() {
    assertEquals(i(1), AirtableRuntime.MIN(i(3), i(1), i(2)));
  }

  @Test
  void maxBasic() {
    assertEquals(i(3), AirtableRuntime.MAX(i(3), i(1), i(2)));
  }

  @Test
  void minEmptyIsNaN() {
    assertNaN(AirtableRuntime.MIN());
  }

  @Test
  void maxEmptyIsNaN() {
    assertNaN(AirtableRuntime.MAX());
  }

  @Test
  void countSkipsStrings() {
    assertEquals(i(2), AirtableRuntime.COUNT(i(1), s("x"), i(2)));
  }

  @Test
  void countSkipsNulls() {
    assertEquals(i(2), AirtableRuntime.COUNT(i(1), s("a"), i(3), nul()));
  }

  @Test
  void countBoolsNotCounted() {
    assertEquals(i(0), AirtableRuntime.COUNT(b(true), b(false)));
  }

  @Test
  void countaSkipsNulls() {
    assertEquals(i(1), AirtableRuntime.COUNTA(i(1), nul(), s("")));
  }

  @Test
  void countaExcludesNullAndEmpty() {
    assertEquals(i(2), AirtableRuntime.COUNTA(i(1), s(""), nul(), s("hi")));
  }

  @Test
  void countaCountsBools() {
    assertEquals(i(2), AirtableRuntime.COUNTA(b(true), b(false)));
  }

  @Test
  void roundToInt() {
    assertEquals(i(4), AirtableRuntime.ROUND(f(3.7)));
  }

  @Test
  void roundToPrecision() {
    assertEquals(f(3.14), AirtableRuntime.ROUND(f(3.14159), i(2)));
  }

  @Test
  void roundBasic() {
    assertEquals(f(3.46), AirtableRuntime.ROUND(f(3.456), i(2)));
  }

  @Test
  void roundHalfAwayFromZero() {
    assertEquals(i(4), AirtableRuntime.ROUND(f(3.5), i(0)));
  }

  @Test
  void roundupInt() {
    assertEquals(i(4), AirtableRuntime.ROUNDUP(f(3.1)));
  }

  @Test
  void roundupPrecision() {
    assertEquals(f(3.2), AirtableRuntime.ROUNDUP(f(3.14), i(1)));
  }

  @Test
  void rounddownInt() {
    assertEquals(i(3), AirtableRuntime.ROUNDDOWN(f(3.9)));
  }

  @Test
  void rounddownPrecision() {
    assertEquals(f(3.1), AirtableRuntime.ROUNDDOWN(f(3.19), i(1)));
  }

  @Test
  void ceilingBasic() {
    assertEquals(i(4), AirtableRuntime.CEILING(f(3.2)));
  }

  @Test
  void ceilingSignificance() {
    assertEquals(i(6), AirtableRuntime.CEILING(f(4.3), i(2)));
  }

  @Test
  void ceilingZeroSignificanceDefaultsToOne() {
    assertEquals(i(5), AirtableRuntime.CEILING(f(4.3), i(0)));
  }

  @Test
  void floorBasic() {
    assertEquals(i(3), AirtableRuntime.FLOOR(f(3.8)));
  }

  @Test
  void floorSignificance() {
    assertEquals(i(4), AirtableRuntime.FLOOR(f(4.9), i(2)));
  }

  @Test
  void logBase10() {
    assertEquals(i(2), AirtableRuntime.LOG(i(100)));
  }

  @Test
  void logBase2() {
    assertEquals(3.0, AirtableRuntime.N(AirtableRuntime.LOG(i(8), i(2))), 1e-9);
  }

  @Test
  void evenRoundsUp() {
    assertEquals(i(4), AirtableRuntime.EVEN(f(3.0)));
  }

  @Test
  void evenAlreadyEven() {
    assertEquals(i(4), AirtableRuntime.EVEN(i(4)));
  }

  @Test
  void evenNegative() {
    assertEquals(i(-4), AirtableRuntime.EVEN(i(-3)));
  }

  @Test
  void oddRoundsUp() {
    assertEquals(i(3), AirtableRuntime.ODD(f(2.0)));
  }

  @Test
  void oddAlreadyOdd() {
    assertEquals(i(3), AirtableRuntime.ODD(i(3)));
  }

  @Test
  void oddNegative() {
    assertEquals(i(-5), AirtableRuntime.ODD(i(-4)));
  }

  @Test
  void valueString() {
    assertEquals(i(42), AirtableRuntime.VALUE(s("42")));
  }

  @Test
  void valueStringFloat() {
    assertEquals(f(3.14), AirtableRuntime.VALUE(s("3.14")));
  }

  @Test
  void valueInvalid() {
    assertNaN(AirtableRuntime.VALUE(s("abc")));
  }

  @Test
  void valueNullIsZero() {
    assertEquals(i(0), AirtableRuntime.VALUE(null));
  }

  @Test
  void powerBasic() {
    assertEquals(i(8), AirtableRuntime.POWER(i(2), i(3)));
  }

  @Test
  void modBasic() {
    assertEquals(i(1), AirtableRuntime.MOD(i(10), i(3)));
  }

  @Test
  void modNegativeDividendKeepsSign() {
    // Swift truncatingRemainder semantics: sign follows the dividend.
    assertEquals(i(-1), AirtableRuntime.MOD(i(-10), i(3)));
  }

  @Test
  void modDivZeroIsNaN() {
    assertNaN(AirtableRuntime.MOD(i(5), i(0)));
  }

  @Test
  void absNegative() {
    assertEquals(i(5), AirtableRuntime.ABS(i(-5)));
  }

  @Test
  void absPositive() {
    assertEquals(i(5), AirtableRuntime.ABS(i(5)));
  }

  @Test
  void sqrtBasic() {
    assertEquals(i(3), AirtableRuntime.SQRT(i(9)));
  }

  @Test
  void expBasic() {
    assertEquals(Math.E, AirtableRuntime.N(AirtableRuntime.EXP(i(1))), 1e-9);
  }

  @Test
  void intTruncates() {
    assertEquals(i(3), AirtableRuntime.INT(f(3.7)));
  }

  @Test
  void intNegativeFloors() {
    assertEquals(i(-4), AirtableRuntime.INT(f(-3.2)));
  }

  // endregion

  // region String (J8.3)

  @Test
  void lenString() {
    assertEquals(i(5), AirtableRuntime.LEN(s("hello")));
  }

  @Test
  void lenEmpty() {
    assertEquals(i(0), AirtableRuntime.LEN(s("")));
  }

  @Test
  void lenUnicode() {
    assertEquals(i(4), AirtableRuntime.LEN(s("café")));
  }

  @Test
  void leftBasic() {
    assertEquals(s("hel"), AirtableRuntime.LEFT(s("hello"), i(3)));
  }

  @Test
  void leftZero() {
    assertEquals(s(""), AirtableRuntime.LEFT(s("hello"), i(0)));
  }

  @Test
  void leftExceeds() {
    assertEquals(s("hi"), AirtableRuntime.LEFT(s("hi"), i(5)));
  }

  @Test
  void rightBasic() {
    assertEquals(s("llo"), AirtableRuntime.RIGHT(s("hello"), i(3)));
  }

  @Test
  void rightExceeds() {
    assertEquals(s("hi"), AirtableRuntime.RIGHT(s("hi"), i(5)));
  }

  @Test
  void midBasic() {
    assertEquals(s("ell"), AirtableRuntime.MID(s("hello"), i(2), i(3)));
  }

  @Test
  void midStartOne() {
    assertEquals(s("he"), AirtableRuntime.MID(s("hello"), i(1), i(2)));
  }

  @Test
  void midStartPastEndIsEmpty() {
    assertEquals(s(""), AirtableRuntime.MID(s("hello"), i(10), i(3)));
  }

  @Test
  void findFound() {
    assertEquals(i(3), AirtableRuntime.FIND(s("l"), s("hello")));
  }

  @Test
  void findMultiChar() {
    assertEquals(i(3), AirtableRuntime.FIND(s("ll"), s("hello")));
  }

  @Test
  void findNotFound() {
    assertEquals(i(0), AirtableRuntime.FIND(s("z"), s("hello")));
  }

  @Test
  void findCaseSensitive() {
    assertEquals(i(0), AirtableRuntime.FIND(s("LL"), s("hello")));
  }

  @Test
  void findWithStart() {
    assertEquals(i(4), AirtableRuntime.FIND(s("l"), s("hello"), i(4)));
  }

  @Test
  void findStartPastEndIsZero() {
    assertEquals(i(0), AirtableRuntime.FIND(s("l"), s("hello"), i(10)));
  }

  @Test
  void findUnicode() {
    // FIND counts character positions, not byte/UTF-16 positions.
    assertEquals(i(3), AirtableRuntime.FIND(s("f"), s("café")));
    assertEquals(i(4), AirtableRuntime.FIND(s("é"), s("café"), i(4)));
  }

  @Test
  void searchCaseInsensitive() {
    assertEquals(i(3), AirtableRuntime.SEARCH(s("L"), s("hello")));
  }

  @Test
  void searchMultiChar() {
    assertEquals(i(3), AirtableRuntime.SEARCH(s("LL"), s("hello")));
  }

  @Test
  void searchWithStart() {
    assertEquals(i(4), AirtableRuntime.SEARCH(s("l"), s("hello"), i(4)));
  }

  @Test
  void substituteAll() {
    assertEquals(s("a_b_c"), AirtableRuntime.SUBSTITUTE(s("a-b-c"), s("-"), s("_")));
  }

  @Test
  void substituteAllOverlapping() {
    assertEquals(s("bbb"), AirtableRuntime.SUBSTITUTE(s("aaa"), s("a"), s("b")));
  }

  @Test
  void substituteNth() {
    assertEquals(s("a-b_c"), AirtableRuntime.SUBSTITUTE(s("a-b-c"), s("-"), s("_"), i(2)));
  }

  @Test
  void substituteNthRepeated() {
    assertEquals(s("aba"), AirtableRuntime.SUBSTITUTE(s("aaa"), s("a"), s("b"), i(2)));
  }

  @Test
  void substituteEmptyOldIsNoop() {
    assertEquals(s("hello"), AirtableRuntime.SUBSTITUTE(s("hello"), s(""), s("x")));
  }

  @Test
  void replaceBasic() {
    assertEquals(s("hXXo"), AirtableRuntime.REPLACE(s("hello"), i(2), i(3), s("XX")));
  }

  @Test
  void replacePastEndAppends() {
    assertEquals(s("hiX"), AirtableRuntime.REPLACE(s("hi"), i(10), i(2), s("X")));
  }

  @Test
  void lowerBasic() {
    assertEquals(s("hi"), AirtableRuntime.LOWER(s("HI")));
  }

  @Test
  void upperBasic() {
    assertEquals(s("HI"), AirtableRuntime.UPPER(s("hi")));
  }

  @Test
  void trimBasic() {
    assertEquals(s("x"), AirtableRuntime.TRIM(s("  x  ")));
  }

  @Test
  void trimNoExtra() {
    assertEquals(s("hello"), AirtableRuntime.TRIM(s("hello")));
  }

  @Test
  void reptBasic() {
    assertEquals(s("ababab"), AirtableRuntime.REPT(s("ab"), i(3)));
  }

  @Test
  void reptZero() {
    assertEquals(s(""), AirtableRuntime.REPT(s("ab"), i(0)));
  }

  @Test
  void concatenateBasic() {
    assertEquals(s("a1b"), AirtableRuntime.CONCATENATE(s("a"), i(1), s("b")));
  }

  @Test
  void concatenateWithNumbers() {
    assertEquals(s("count: 5"), AirtableRuntime.CONCATENATE(s("count: "), i(5)));
  }

  @Test
  void tString() {
    assertEquals(s("hello"), AirtableRuntime.T(s("hello")));
  }

  @Test
  void tNumberIsEmpty() {
    assertEquals(s(""), AirtableRuntime.T(i(42)));
  }

  @Test
  void tNullIsEmpty() {
    assertEquals(s(""), AirtableRuntime.T(nul()));
  }

  @Test
  void encodeUrlComponentSpace() {
    assertEquals(s("hello%20world"), AirtableRuntime.ENCODE_URL_COMPONENT(s("hello world")));
  }

  @Test
  void encodeUrlComponentPercent() {
    assertEquals(s("100%25"), AirtableRuntime.ENCODE_URL_COMPONENT(s("100%")));
  }

  @Test
  void encodeUrlComponentQueryCharsPassThrough() {
    // Swift parity: CharacterSet.urlQueryAllowed leaves query sub-delims unencoded.
    assertEquals(s("a&b=c"), AirtableRuntime.ENCODE_URL_COMPONENT(s("a&b=c")));
  }

  @Test
  void encodeUrlComponentUnicode() {
    assertEquals(s("caf%C3%A9"), AirtableRuntime.ENCODE_URL_COMPONENT(s("café")));
  }

  // endregion

  // region Date/time (J8.4)

  @Test
  void yearOfIsoDate() {
    assertEquals(i(2025), AirtableRuntime.YEAR(s("2025-04-20T10:00:00Z")));
  }

  @Test
  void yearOfNullIsZero() {
    assertEquals(i(0), AirtableRuntime.YEAR(nul()));
  }

  @Test
  void monthOfIsoDate() {
    assertEquals(i(4), AirtableRuntime.MONTH(s("2025-04-20T10:00:00Z")));
  }

  @Test
  void dayOfIsoDate() {
    assertEquals(i(20), AirtableRuntime.DAY(s("2025-04-20T10:00:00Z")));
  }

  @Test
  void hourOfIsoDate() {
    assertEquals(i(10), AirtableRuntime.HOUR(s("2025-04-20T10:30:00Z")));
  }

  @Test
  void minuteBasic() {
    assertEquals(i(30), AirtableRuntime.MINUTE(s("2024-01-15T14:30:00Z")));
  }

  @Test
  void secondBasic() {
    assertEquals(i(45), AirtableRuntime.SECOND(s("2024-01-15T14:30:45Z")));
  }

  @Test
  void weekdaySunday() {
    // 2024-01-14 is a Sunday.
    assertEquals(i(0), AirtableRuntime.WEEKDAY(s("2024-01-14T00:00:00Z")));
  }

  @Test
  void weekdayMonday() {
    // 2024-01-15 is a Monday.
    assertEquals(i(1), AirtableRuntime.WEEKDAY(s("2024-01-15T00:00:00Z")));
  }

  @Test
  void weekdaySaturday() {
    // 2024-01-20 is a Saturday.
    assertEquals(i(6), AirtableRuntime.WEEKDAY(s("2024-01-20T00:00:00Z")));
  }

  @Test
  void weeknumBasic() {
    // Jan 15 2024 is in week 3 (Sunday start).
    assertEquals(i(3), AirtableRuntime.WEEKNUM(s("2024-01-15T00:00:00Z")));
  }

  @Test
  void datetimeDiffDays() {
    assertEquals(
        i(5),
        AirtableRuntime.DATETIME_DIFF(
            s("2025-04-20T00:00:00Z"), s("2025-04-15T00:00:00Z"), s("days")));
  }

  @Test
  void datetimeDiffHours() {
    assertEquals(
        i(12),
        AirtableRuntime.DATETIME_DIFF(
            s("2025-04-20T12:00:00Z"), s("2025-04-20T00:00:00Z"), s("hours")));
  }

  @Test
  void datetimeDiffMinutes() {
    assertEquals(
        i(90),
        AirtableRuntime.DATETIME_DIFF(
            s("2024-01-15T13:30:00Z"), s("2024-01-15T12:00:00Z"), s("minutes")));
  }

  @Test
  void datetimeDiffWeeks() {
    assertEquals(
        i(2),
        AirtableRuntime.DATETIME_DIFF(
            s("2024-01-29T00:00:00Z"), s("2024-01-15T00:00:00Z"), s("weeks")));
  }

  @Test
  void datetimeDiffMonths() {
    assertEquals(
        i(2),
        AirtableRuntime.DATETIME_DIFF(
            s("2024-03-15T00:00:00Z"), s("2024-01-15T00:00:00Z"), s("months")));
  }

  @Test
  void datetimeDiffYears() {
    assertEquals(
        i(1),
        AirtableRuntime.DATETIME_DIFF(
            s("2025-01-15T00:00:00Z"), s("2024-06-15T00:00:00Z"), s("years")));
  }

  @Test
  void datetimeDiffDefaultDays() {
    assertEquals(
        i(5), AirtableRuntime.DATETIME_DIFF(s("2024-01-20T00:00:00Z"), s("2024-01-15T00:00:00Z")));
  }

  @Test
  void datetimeDiffNullIsZero() {
    assertEquals(i(0), AirtableRuntime.DATETIME_DIFF(nul(), s("2024-01-15T00:00:00Z"), s("days")));
  }

  @Test
  void dateaddDays() {
    assertEquals(
        s("2024-01-20T00:00:00.000Z"),
        AirtableRuntime.DATEADD(s("2024-01-15T00:00:00Z"), i(5), s("days")));
  }

  @Test
  void dateaddMonthsClamp() {
    // Jan 31 + 1 month = Feb 29 (2024 is a leap year).
    assertEquals(
        s("2024-02-29T00:00:00.000Z"),
        AirtableRuntime.DATEADD(s("2024-01-31T00:00:00Z"), i(1), s("months")));
  }

  @Test
  void dateaddYears() {
    assertEquals(
        s("2025-01-15T00:00:00.000Z"),
        AirtableRuntime.DATEADD(s("2024-01-15T00:00:00Z"), i(1), s("years")));
  }

  @Test
  void dateaddHours() {
    assertEquals(
        s("2024-01-15T15:00:00.000Z"),
        AirtableRuntime.DATEADD(s("2024-01-15T12:00:00Z"), i(3), s("hours")));
  }

  @Test
  void dateaddNullIsNull() {
    assertEquals(nul(), AirtableRuntime.DATEADD(nul(), i(5), s("days")));
  }

  @Test
  void isSameSameDay() {
    assertEquals(
        b(true),
        AirtableRuntime.IS_SAME(s("2025-04-20T10:00:00Z"), s("2025-04-20T15:00:00Z"), s("days")));
  }

  @Test
  void isSameFalse() {
    assertEquals(
        b(false),
        AirtableRuntime.IS_SAME(s("2024-01-15T00:00:00Z"), s("2024-01-16T00:00:00Z"), s("days")));
  }

  @Test
  void isBeforeDay() {
    assertEquals(
        b(true),
        AirtableRuntime.IS_BEFORE(s("2025-04-20T10:00:00Z"), s("2025-04-21T10:00:00Z"), s("days")));
  }

  @Test
  void isBeforeFalseWhenAfter() {
    assertEquals(
        b(false),
        AirtableRuntime.IS_BEFORE(s("2025-04-22T10:00:00Z"), s("2025-04-21T10:00:00Z"), s("days")));
  }

  @Test
  void isAfterTrue() {
    assertEquals(
        b(true),
        AirtableRuntime.IS_AFTER(s("2024-01-16T00:00:00Z"), s("2024-01-15T00:00:00Z"), s("days")));
  }

  @Test
  void workdayBasic() {
    // Mon Jan 15 + 5 workdays = Mon Jan 22.
    assertEquals(
        s("2024-01-22T00:00:00.000Z"), AirtableRuntime.WORKDAY(s("2024-01-15T00:00:00Z"), i(5)));
  }

  @Test
  void workdaySkipWeekend() {
    // Fri Jan 19 + 1 workday = Mon Jan 22.
    assertEquals(
        s("2024-01-22T00:00:00.000Z"), AirtableRuntime.WORKDAY(s("2024-01-19T00:00:00Z"), i(1)));
  }

  @Test
  void workdayNegative() {
    // Mon Jan 22 - 1 workday = Fri Jan 19.
    assertEquals(
        s("2024-01-19T00:00:00.000Z"), AirtableRuntime.WORKDAY(s("2024-01-22T00:00:00Z"), i(-1)));
  }

  @Test
  void workdayNullIsNull() {
    assertEquals(nul(), AirtableRuntime.WORKDAY(nul(), i(5)));
  }

  @Test
  void workdayDiffBasic() {
    // Mon Jan 15 to Mon Jan 22 = 6 workdays (includes start day).
    assertEquals(
        i(6), AirtableRuntime.WORKDAY_DIFF(s("2024-01-15T00:00:00Z"), s("2024-01-22T00:00:00Z")));
  }

  @Test
  void workdayDiffReverseIsNegative() {
    assertEquals(
        i(-6), AirtableRuntime.WORKDAY_DIFF(s("2024-01-22T00:00:00Z"), s("2024-01-15T00:00:00Z")));
  }

  @Test
  void workdayDiffNullIsZero() {
    assertEquals(i(0), AirtableRuntime.WORKDAY_DIFF(nul(), s("2024-01-15T00:00:00Z")));
  }

  @Test
  void setTimezoneBasic() {
    // UTC 12:00 → America/New_York (UTC-5 in January) = 07:00 wall clock.
    assertEquals(
        s("2024-01-15T07:00:00.000Z"),
        AirtableRuntime.SET_TIMEZONE(s("2024-01-15T12:00:00Z"), s("America/New_York")));
  }

  @Test
  void setTimezoneInvalidZoneReturnsIso() {
    assertEquals(
        s("2024-01-15T12:00:00.000Z"),
        AirtableRuntime.SET_TIMEZONE(s("2024-01-15T12:00:00Z"), s("Not/AZone")));
  }

  @Test
  void datetimeFormatDefault() {
    assertEquals(
        s("2024-01-15T14:30:00.000Z"), AirtableRuntime.DATETIME_FORMAT(s("2024-01-15T14:30:00Z")));
  }

  @Test
  void datetimeFormatCustomDate() {
    assertEquals(
        s("2024-01-15"),
        AirtableRuntime.DATETIME_FORMAT(s("2024-01-15T14:30:00Z"), s("YYYY-MM-DD")));
  }

  @Test
  void datetimeFormatTime() {
    assertEquals(
        s("14:30"), AirtableRuntime.DATETIME_FORMAT(s("2024-01-15T14:30:00Z"), s("HH:mm")));
  }

  @Test
  void datetimeFormatNullIsEmpty() {
    assertEquals(s(""), AirtableRuntime.DATETIME_FORMAT(nul(), s("YYYY-MM-DD")));
  }

  @Test
  void datestrBasic() {
    assertEquals(s("2024-01-15"), AirtableRuntime.DATESTR(s("2024-01-15T14:30:00Z")));
  }

  @Test
  void datestrNullIsEmpty() {
    assertEquals(s(""), AirtableRuntime.DATESTR(nul()));
  }

  @Test
  void timestrBasic() {
    assertEquals(s("14:30:00"), AirtableRuntime.TIMESTR(s("2024-01-15T14:30:00Z")));
  }

  @Test
  void datetimeParseBasic() {
    assertEquals(s("2024-01-15T00:00:00.000Z"), AirtableRuntime.DATETIME_PARSE(s("2024-01-15")));
  }

  @Test
  void datetimeParseGarbageIsNull() {
    assertEquals(nul(), AirtableRuntime.DATETIME_PARSE(s("not a date")));
  }

  @Test
  void nowIsParseableIso() {
    assertNotNull(AirtableRuntime.D(AirtableRuntime.NOW()));
  }

  @Test
  void todayIsParseableIso() {
    assertNotNull(AirtableRuntime.D(AirtableRuntime.TODAY()));
  }

  @Test
  void tonowWithUnitIsPositiveForPastDate() {
    assertTrue(AirtableRuntime.N(AirtableRuntime.TONOW(s("2000-01-01T00:00:00Z"), s("days"))) > 0);
  }

  @Test
  void fromnowWithUnitIsNegativeForPastDate() {
    assertTrue(
        AirtableRuntime.N(AirtableRuntime.FROMNOW(s("2000-01-01T00:00:00Z"), s("days"))) < 0);
  }

  @Test
  void tonowHumanDurationForOldDateIsYears() {
    assertTrue(
        AirtableRuntime.S(AirtableRuntime.TONOW(s("2000-01-01T00:00:00Z"))).endsWith("years"));
  }

  // endregion

  // region Array (J8.5)

  @Test
  void arrayJoinDefault() {
    assertEquals(s("1, 2, 3"), AirtableRuntime.ARRAYJOIN(arr(i(1), i(2), i(3))));
  }

  @Test
  void arrayJoinCustomSep() {
    assertEquals(s("1-2"), AirtableRuntime.ARRAYJOIN(arr(i(1), i(2)), s("-")));
  }

  @Test
  void arrayJoinNonArray() {
    assertEquals(s("hello"), AirtableRuntime.ARRAYJOIN(s("hello")));
  }

  @Test
  void arrayJoinNullIsEmpty() {
    assertEquals(s(""), AirtableRuntime.ARRAYJOIN(null));
  }

  @Test
  void arrayUniqueBasic() {
    assertEquals(arr(i(1), i(2), i(3)), AirtableRuntime.ARRAYUNIQUE(arr(i(1), i(2), i(1), i(3))));
  }

  @Test
  void arrayUniquePreservesOrder() {
    assertEquals(
        arr(i(3), i(1), i(2)), AirtableRuntime.ARRAYUNIQUE(arr(i(3), i(1), i(2), i(1), i(3))));
  }

  @Test
  void arrayCompactStripsNullsAndEmptyStrings() {
    assertEquals(arr(i(1), i(2)), AirtableRuntime.ARRAYCOMPACT(arr(i(1), nul(), s(""), i(2))));
  }

  @Test
  void arrayCompactKeepsZeroAndFalse() {
    assertEquals(
        arr(i(0), b(false)), AirtableRuntime.ARRAYCOMPACT(arr(i(0), nul(), b(false), s(""))));
  }

  @Test
  void arrayCompactNullInputIsEmptyArray() {
    assertEquals(arr(), AirtableRuntime.ARRAYCOMPACT(null));
  }

  @Test
  void arrayFlattenNested() {
    assertEquals(
        arr(i(1), i(2), i(3), i(4)),
        AirtableRuntime.ARRAYFLATTEN(arr(i(1), arr(i(2), i(3)), i(4))));
  }

  @Test
  void arrayFlattenDeep() {
    assertEquals(
        arr(i(1), i(2), i(3), i(4)),
        AirtableRuntime.ARRAYFLATTEN(arr(i(1), arr(i(2), arr(i(3), i(4))))));
  }

  @Test
  void arrayFlattenAlreadyFlat() {
    assertEquals(arr(i(1), i(2), i(3)), AirtableRuntime.ARRAYFLATTEN(arr(i(1), i(2), i(3))));
  }

  @Test
  void arrayFlattenNonArrayWraps() {
    assertEquals(arr(i(5)), AirtableRuntime.ARRAYFLATTEN(i(5)));
  }

  // endregion

  // region Regex (J8.6)

  @Test
  void regexMatchTrue() {
    assertEquals(b(true), AirtableRuntime.REGEX_MATCH(s("hello"), s("^hel")));
  }

  @Test
  void regexMatchFalse() {
    assertEquals(b(false), AirtableRuntime.REGEX_MATCH(s("hello"), s("^xyz")));
  }

  @Test
  void regexMatchUnanchored() {
    assertEquals(b(true), AirtableRuntime.REGEX_MATCH(s("Hello"), s("^.e")));
  }

  @Test
  void regexMatchInvalidPatternIsFalse() {
    assertEquals(b(false), AirtableRuntime.REGEX_MATCH(s("hello"), s("(")));
  }

  @Test
  void regexExtractBasic() {
    assertEquals(s("123"), AirtableRuntime.REGEX_EXTRACT(s("hello123"), s("\\d+")));
  }

  @Test
  void regexExtractFirstMatch() {
    assertEquals(s("e"), AirtableRuntime.REGEX_EXTRACT(s("Hello"), s("[aeiou]")));
  }

  @Test
  void regexExtractNoMatchIsEmptyString() {
    // Swift parity: no match yields "" (the Rust runtime returns null here).
    assertEquals(s(""), AirtableRuntime.REGEX_EXTRACT(s("xyz"), s("[aeiou]")));
  }

  @Test
  void regexReplaceBasic() {
    assertEquals(s("hexo"), AirtableRuntime.REGEX_REPLACE(s("hello"), s("l+"), s("x")));
  }

  @Test
  void regexReplaceAllOccurrences() {
    assertEquals(s("H*ll*"), AirtableRuntime.REGEX_REPLACE(s("Hello"), s("[aeiou]"), s("*")));
  }

  // endregion
}

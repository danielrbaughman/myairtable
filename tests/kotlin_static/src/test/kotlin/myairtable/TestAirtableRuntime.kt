package myairtable

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * K2.9 — Formula-function semantics of [AirtableRuntime].
 * Parity: Swift TestAirtableRuntime + tests/test_airtable_runtime.rs (formula
 * sections). Coercion-helper basics (N/S/A/V/isTruthy) live in
 * TestValueCoercion and are not repeated here.
 */
class TestAirtableRuntime {
    private fun i(value: Int): JsonElement = JsonPrimitive(value)

    private fun f(value: Double): JsonElement = JsonPrimitive(value)

    private fun s(value: String): JsonElement = JsonPrimitive(value)

    private fun b(value: Boolean): JsonElement = JsonPrimitive(value)

    private fun arr(vararg items: JsonElement): JsonElement = JsonArray(items.toList())

    private fun assertNaN(value: JsonElement) {
        assertTrue(N(value).isNaN(), "expected NaN, got $value")
    }

    // region Logic (F8.4)

    @Test
    fun ifTrue() {
        assertEquals(i(1), AirtableRuntime.IF(b(true), i(1), i(2)))
    }

    @Test
    fun ifFalse() {
        assertEquals(i(2), AirtableRuntime.IF(b(false), i(1), i(2)))
    }

    @Test
    fun ifNullIsFalse() {
        assertEquals(i(2), AirtableRuntime.IF(null, i(1), i(2)))
    }

    @Test
    fun ifZeroIsFalsy() {
        assertEquals(s("no"), AirtableRuntime.IF(i(0), s("yes"), s("no")))
    }

    @Test
    fun ifNumberIsTruthy() {
        assertEquals(s("yes"), AirtableRuntime.IF(i(1), s("yes"), s("no")))
    }

    @Test
    fun ifEmptyStringIsFalsy() {
        assertEquals(s("no"), AirtableRuntime.IF(s(""), s("yes"), s("no")))
    }

    @Test
    fun switchMatch() {
        val cases = listOf<Pair<JsonElement, JsonElement>>(i(1) to s("one"), i(2) to s("two"))
        assertEquals(s("two"), AirtableRuntime.SWITCH(i(2), cases))
    }

    @Test
    fun switchDefault() {
        val cases = listOf<Pair<JsonElement, JsonElement>>(i(1) to s("one"))
        assertEquals(s("other"), AirtableRuntime.SWITCH(i(99), cases, s("other")))
    }

    @Test
    fun switchNoMatchNoDefault() {
        val cases = listOf<Pair<JsonElement, JsonElement>>(i(1) to s("one"))
        assertEquals(JsonNull, AirtableRuntime.SWITCH(i(99), cases))
    }

    @Test
    fun blankIsNull() {
        assertEquals(JsonNull, AirtableRuntime.BLANK())
    }

    @Test
    fun trueIsBool() {
        assertEquals(b(true), AirtableRuntime.TRUE())
    }

    @Test
    fun falseIsBool() {
        assertEquals(b(false), AirtableRuntime.FALSE())
    }

    @Test
    fun iserrorNaN() {
        assertEquals(b(true), AirtableRuntime.ISERROR(f(Double.NaN)))
    }

    @Test
    fun iserrorNormal() {
        assertEquals(b(false), AirtableRuntime.ISERROR(i(5)))
    }

    @Test
    fun iserrorNullIsFalse() {
        // Swift parity: only NaN doubles are errors (the Rust runtime differs here).
        assertEquals(b(false), AirtableRuntime.ISERROR(JsonNull))
        assertEquals(b(false), AirtableRuntime.ISERROR(null))
    }

    @Test
    fun errorIsNaN() {
        assertNaN(AirtableRuntime.ERROR())
        assertEquals(b(true), AirtableRuntime.ISERROR(AirtableRuntime.ERROR(s("boom"))))
    }

    // endregion

    // region Math (F8.4)

    @Test
    fun sumBasic() {
        assertEquals(i(6), AirtableRuntime.SUM(i(1), i(2), i(3)))
    }

    @Test
    fun sumWithArray() {
        assertEquals(i(6), AirtableRuntime.SUM(arr(i(1), i(2)), i(3)))
    }

    @Test
    fun sumWithStrings() {
        assertEquals(i(6), AirtableRuntime.SUM(i(1), s("5")))
    }

    @Test
    fun averageBasic() {
        assertEquals(i(3), AirtableRuntime.AVERAGE(i(2), i(4)))
    }

    @Test
    fun averageThree() {
        assertEquals(i(20), AirtableRuntime.AVERAGE(i(10), i(20), i(30)))
    }

    @Test
    fun averageEmptyIsNaN() {
        assertNaN(AirtableRuntime.AVERAGE())
    }

    @Test
    fun minBasic() {
        assertEquals(i(1), AirtableRuntime.MIN(i(3), i(1), i(2)))
    }

    @Test
    fun maxBasic() {
        assertEquals(i(3), AirtableRuntime.MAX(i(3), i(1), i(2)))
    }

    @Test
    fun minEmptyIsNaN() {
        assertNaN(AirtableRuntime.MIN())
    }

    @Test
    fun maxEmptyIsNaN() {
        assertNaN(AirtableRuntime.MAX())
    }

    @Test
    fun countSkipsStrings() {
        assertEquals(i(2), AirtableRuntime.COUNT(i(1), s("x"), i(2)))
    }

    @Test
    fun countSkipsNulls() {
        assertEquals(i(2), AirtableRuntime.COUNT(i(1), s("a"), i(3), JsonNull))
    }

    @Test
    fun countBoolsNotCounted() {
        assertEquals(i(0), AirtableRuntime.COUNT(b(true), b(false)))
    }

    @Test
    fun countaSkipsNulls() {
        assertEquals(i(1), AirtableRuntime.COUNTA(i(1), JsonNull, s("")))
    }

    @Test
    fun countaExcludesNullAndEmpty() {
        assertEquals(i(2), AirtableRuntime.COUNTA(i(1), s(""), JsonNull, s("hi")))
    }

    @Test
    fun countaCountsBools() {
        assertEquals(i(2), AirtableRuntime.COUNTA(b(true), b(false)))
    }

    @Test
    fun roundToInt() {
        assertEquals(i(4), AirtableRuntime.ROUND(f(3.7)))
    }

    @Test
    fun roundToPrecision() {
        assertEquals(f(3.14), AirtableRuntime.ROUND(f(3.14159), i(2)))
    }

    @Test
    fun roundBasic() {
        assertEquals(f(3.46), AirtableRuntime.ROUND(f(3.456), i(2)))
    }

    @Test
    fun roundHalfAwayFromZero() {
        assertEquals(i(4), AirtableRuntime.ROUND(f(3.5), i(0)))
    }

    @Test
    fun roundupInt() {
        assertEquals(i(4), AirtableRuntime.ROUNDUP(f(3.1)))
    }

    @Test
    fun roundupPrecision() {
        assertEquals(f(3.2), AirtableRuntime.ROUNDUP(f(3.14), i(1)))
    }

    @Test
    fun rounddownInt() {
        assertEquals(i(3), AirtableRuntime.ROUNDDOWN(f(3.9)))
    }

    @Test
    fun rounddownPrecision() {
        assertEquals(f(3.1), AirtableRuntime.ROUNDDOWN(f(3.19), i(1)))
    }

    @Test
    fun ceilingBasic() {
        assertEquals(i(4), AirtableRuntime.CEILING(f(3.2)))
    }

    @Test
    fun ceilingSignificance() {
        assertEquals(i(6), AirtableRuntime.CEILING(f(4.3), i(2)))
    }

    @Test
    fun ceilingZeroSignificanceDefaultsToOne() {
        assertEquals(i(5), AirtableRuntime.CEILING(f(4.3), i(0)))
    }

    @Test
    fun floorBasic() {
        assertEquals(i(3), AirtableRuntime.FLOOR(f(3.8)))
    }

    @Test
    fun floorSignificance() {
        assertEquals(i(4), AirtableRuntime.FLOOR(f(4.9), i(2)))
    }

    @Test
    fun logBase10() {
        assertEquals(i(2), AirtableRuntime.LOG(i(100)))
    }

    @Test
    fun logBase2() {
        assertEquals(3.0, N(AirtableRuntime.LOG(i(8), i(2))), 1e-9)
    }

    @Test
    fun evenRoundsUp() {
        assertEquals(i(4), AirtableRuntime.EVEN(f(3.0)))
    }

    @Test
    fun evenAlreadyEven() {
        assertEquals(i(4), AirtableRuntime.EVEN(i(4)))
    }

    @Test
    fun evenNegative() {
        assertEquals(i(-4), AirtableRuntime.EVEN(i(-3)))
    }

    @Test
    fun oddRoundsUp() {
        assertEquals(i(3), AirtableRuntime.ODD(f(2.0)))
    }

    @Test
    fun oddAlreadyOdd() {
        assertEquals(i(3), AirtableRuntime.ODD(i(3)))
    }

    @Test
    fun oddNegative() {
        assertEquals(i(-5), AirtableRuntime.ODD(i(-4)))
    }

    @Test
    fun valueString() {
        assertEquals(i(42), AirtableRuntime.VALUE(s("42")))
    }

    @Test
    fun valueStringFloat() {
        assertEquals(f(3.14), AirtableRuntime.VALUE(s("3.14")))
    }

    @Test
    fun valueInvalid() {
        assertNaN(AirtableRuntime.VALUE(s("abc")))
    }

    @Test
    fun valueNullIsZero() {
        assertEquals(i(0), AirtableRuntime.VALUE(null))
    }

    @Test
    fun powerBasic() {
        assertEquals(i(8), AirtableRuntime.POWER(i(2), i(3)))
    }

    @Test
    fun modBasic() {
        assertEquals(i(1), AirtableRuntime.MOD(i(10), i(3)))
    }

    @Test
    fun modNegativeDividendKeepsSign() {
        // Swift truncatingRemainder semantics: sign follows the dividend.
        assertEquals(i(-1), AirtableRuntime.MOD(i(-10), i(3)))
    }

    @Test
    fun modDivZeroIsNaN() {
        assertNaN(AirtableRuntime.MOD(i(5), i(0)))
    }

    @Test
    fun absNegative() {
        assertEquals(i(5), AirtableRuntime.ABS(i(-5)))
    }

    @Test
    fun absPositive() {
        assertEquals(i(5), AirtableRuntime.ABS(i(5)))
    }

    @Test
    fun sqrtBasic() {
        assertEquals(i(3), AirtableRuntime.SQRT(i(9)))
    }

    @Test
    fun expBasic() {
        assertEquals(Math.E, N(AirtableRuntime.EXP(i(1))), 1e-9)
    }

    @Test
    fun intTruncates() {
        assertEquals(i(3), AirtableRuntime.INT(f(3.7)))
    }

    @Test
    fun intNegativeFloors() {
        assertEquals(i(-4), AirtableRuntime.INT(f(-3.2)))
    }

    // endregion

    // region String (F8.6)

    @Test
    fun lenString() {
        assertEquals(i(5), AirtableRuntime.LEN(s("hello")))
    }

    @Test
    fun lenEmpty() {
        assertEquals(i(0), AirtableRuntime.LEN(s("")))
    }

    @Test
    fun lenUnicode() {
        assertEquals(i(4), AirtableRuntime.LEN(s("café")))
    }

    @Test
    fun leftBasic() {
        assertEquals(s("hel"), AirtableRuntime.LEFT(s("hello"), i(3)))
    }

    @Test
    fun leftZero() {
        assertEquals(s(""), AirtableRuntime.LEFT(s("hello"), i(0)))
    }

    @Test
    fun leftExceeds() {
        assertEquals(s("hi"), AirtableRuntime.LEFT(s("hi"), i(5)))
    }

    @Test
    fun rightBasic() {
        assertEquals(s("llo"), AirtableRuntime.RIGHT(s("hello"), i(3)))
    }

    @Test
    fun rightExceeds() {
        assertEquals(s("hi"), AirtableRuntime.RIGHT(s("hi"), i(5)))
    }

    @Test
    fun midBasic() {
        assertEquals(s("ell"), AirtableRuntime.MID(s("hello"), i(2), i(3)))
    }

    @Test
    fun midStartOne() {
        assertEquals(s("he"), AirtableRuntime.MID(s("hello"), i(1), i(2)))
    }

    @Test
    fun midStartPastEndIsEmpty() {
        assertEquals(s(""), AirtableRuntime.MID(s("hello"), i(10), i(3)))
    }

    @Test
    fun findFound() {
        assertEquals(i(3), AirtableRuntime.FIND(s("l"), s("hello")))
    }

    @Test
    fun findMultiChar() {
        assertEquals(i(3), AirtableRuntime.FIND(s("ll"), s("hello")))
    }

    @Test
    fun findNotFound() {
        assertEquals(i(0), AirtableRuntime.FIND(s("z"), s("hello")))
    }

    @Test
    fun findCaseSensitive() {
        assertEquals(i(0), AirtableRuntime.FIND(s("LL"), s("hello")))
    }

    @Test
    fun findWithStart() {
        assertEquals(i(4), AirtableRuntime.FIND(s("l"), s("hello"), i(4)))
    }

    @Test
    fun findStartPastEndIsZero() {
        assertEquals(i(0), AirtableRuntime.FIND(s("l"), s("hello"), i(10)))
    }

    @Test
    fun findUnicode() {
        // FIND counts character positions, not byte/UTF-16 positions.
        assertEquals(i(3), AirtableRuntime.FIND(s("f"), s("café")))
        assertEquals(i(4), AirtableRuntime.FIND(s("é"), s("café"), i(4)))
    }

    @Test
    fun searchCaseInsensitive() {
        assertEquals(i(3), AirtableRuntime.SEARCH(s("L"), s("hello")))
    }

    @Test
    fun searchMultiChar() {
        assertEquals(i(3), AirtableRuntime.SEARCH(s("LL"), s("hello")))
    }

    @Test
    fun searchWithStart() {
        assertEquals(i(4), AirtableRuntime.SEARCH(s("l"), s("hello"), i(4)))
    }

    @Test
    fun substituteAll() {
        assertEquals(s("a_b_c"), AirtableRuntime.SUBSTITUTE(s("a-b-c"), s("-"), s("_")))
    }

    @Test
    fun substituteAllOverlapping() {
        assertEquals(s("bbb"), AirtableRuntime.SUBSTITUTE(s("aaa"), s("a"), s("b")))
    }

    @Test
    fun substituteNth() {
        assertEquals(s("a-b_c"), AirtableRuntime.SUBSTITUTE(s("a-b-c"), s("-"), s("_"), i(2)))
    }

    @Test
    fun substituteNthRepeated() {
        assertEquals(s("aba"), AirtableRuntime.SUBSTITUTE(s("aaa"), s("a"), s("b"), i(2)))
    }

    @Test
    fun substituteEmptyOldIsNoop() {
        assertEquals(s("hello"), AirtableRuntime.SUBSTITUTE(s("hello"), s(""), s("x")))
    }

    @Test
    fun replaceBasic() {
        assertEquals(s("hXXo"), AirtableRuntime.REPLACE(s("hello"), i(2), i(3), s("XX")))
    }

    @Test
    fun replacePastEndAppends() {
        assertEquals(s("hiX"), AirtableRuntime.REPLACE(s("hi"), i(10), i(2), s("X")))
    }

    @Test
    fun lowerBasic() {
        assertEquals(s("hi"), AirtableRuntime.LOWER(s("HI")))
    }

    @Test
    fun upperBasic() {
        assertEquals(s("HI"), AirtableRuntime.UPPER(s("hi")))
    }

    @Test
    fun trimBasic() {
        assertEquals(s("x"), AirtableRuntime.TRIM(s("  x  ")))
    }

    @Test
    fun trimNoExtra() {
        assertEquals(s("hello"), AirtableRuntime.TRIM(s("hello")))
    }

    @Test
    fun reptBasic() {
        assertEquals(s("ababab"), AirtableRuntime.REPT(s("ab"), i(3)))
    }

    @Test
    fun reptZero() {
        assertEquals(s(""), AirtableRuntime.REPT(s("ab"), i(0)))
    }

    @Test
    fun concatenateBasic() {
        assertEquals(s("a1b"), AirtableRuntime.CONCATENATE(s("a"), i(1), s("b")))
    }

    @Test
    fun concatenateWithNumbers() {
        assertEquals(s("count: 5"), AirtableRuntime.CONCATENATE(s("count: "), i(5)))
    }

    @Test
    fun tString() {
        assertEquals(s("hello"), AirtableRuntime.T(s("hello")))
    }

    @Test
    fun tNumberIsEmpty() {
        assertEquals(s(""), AirtableRuntime.T(i(42)))
    }

    @Test
    fun tNullIsEmpty() {
        assertEquals(s(""), AirtableRuntime.T(JsonNull))
    }

    @Test
    fun encodeUrlComponentSpace() {
        assertEquals(s("hello%20world"), AirtableRuntime.ENCODE_URL_COMPONENT(s("hello world")))
    }

    @Test
    fun encodeUrlComponentPercent() {
        assertEquals(s("100%25"), AirtableRuntime.ENCODE_URL_COMPONENT(s("100%")))
    }

    @Test
    fun encodeUrlComponentEncodesReservedChars() {
        // encodeURIComponent (which Airtable matches) percent-encodes reserved chars like & = + .
        assertEquals(s("a%26b%3Dc"), AirtableRuntime.ENCODE_URL_COMPONENT(s("a&b=c")))
        assertEquals(s("a%2Bb"), AirtableRuntime.ENCODE_URL_COMPONENT(s("a+b")))
    }

    @Test
    fun encodeUrlComponentUnicode() {
        assertEquals(s("caf%C3%A9"), AirtableRuntime.ENCODE_URL_COMPONENT(s("café")))
    }

    // endregion

    // region Date/time (F8.7)

    @Test
    fun yearOfIsoDate() {
        assertEquals(i(2025), AirtableRuntime.YEAR(s("2025-04-20T10:00:00Z")))
    }

    @Test
    fun yearOfNullIsZero() {
        assertEquals(i(0), AirtableRuntime.YEAR(JsonNull))
    }

    @Test
    fun monthOfIsoDate() {
        assertEquals(i(4), AirtableRuntime.MONTH(s("2025-04-20T10:00:00Z")))
    }

    @Test
    fun dayOfIsoDate() {
        assertEquals(i(20), AirtableRuntime.DAY(s("2025-04-20T10:00:00Z")))
    }

    @Test
    fun hourOfIsoDate() {
        assertEquals(i(10), AirtableRuntime.HOUR(s("2025-04-20T10:30:00Z")))
    }

    @Test
    fun minuteBasic() {
        assertEquals(i(30), AirtableRuntime.MINUTE(s("2024-01-15T14:30:00Z")))
    }

    @Test
    fun secondBasic() {
        assertEquals(i(45), AirtableRuntime.SECOND(s("2024-01-15T14:30:45Z")))
    }

    @Test
    fun weekdaySunday() {
        // 2024-01-14 is a Sunday.
        assertEquals(i(0), AirtableRuntime.WEEKDAY(s("2024-01-14T00:00:00Z")))
    }

    @Test
    fun weekdayMonday() {
        // 2024-01-15 is a Monday.
        assertEquals(i(1), AirtableRuntime.WEEKDAY(s("2024-01-15T00:00:00Z")))
    }

    @Test
    fun weekdaySaturday() {
        // 2024-01-20 is a Saturday.
        assertEquals(i(6), AirtableRuntime.WEEKDAY(s("2024-01-20T00:00:00Z")))
    }

    @Test
    fun weeknumBasic() {
        // Jan 15 2024 is in week 3 (Sunday start).
        assertEquals(i(3), AirtableRuntime.WEEKNUM(s("2024-01-15T00:00:00Z")))
    }

    @Test
    fun datetimeDiffDays() {
        assertEquals(i(5), AirtableRuntime.DATETIME_DIFF(s("2025-04-20T00:00:00Z"), s("2025-04-15T00:00:00Z"), s("days")))
    }

    @Test
    fun datetimeDiffHours() {
        assertEquals(i(12), AirtableRuntime.DATETIME_DIFF(s("2025-04-20T12:00:00Z"), s("2025-04-20T00:00:00Z"), s("hours")))
    }

    @Test
    fun datetimeDiffMinutes() {
        assertEquals(i(90), AirtableRuntime.DATETIME_DIFF(s("2024-01-15T13:30:00Z"), s("2024-01-15T12:00:00Z"), s("minutes")))
    }

    @Test
    fun datetimeDiffWeeks() {
        assertEquals(i(2), AirtableRuntime.DATETIME_DIFF(s("2024-01-29T00:00:00Z"), s("2024-01-15T00:00:00Z"), s("weeks")))
    }

    @Test
    fun datetimeDiffMonths() {
        assertEquals(i(2), AirtableRuntime.DATETIME_DIFF(s("2024-03-15T00:00:00Z"), s("2024-01-15T00:00:00Z"), s("months")))
    }

    @Test
    fun datetimeDiffYears() {
        assertEquals(i(1), AirtableRuntime.DATETIME_DIFF(s("2025-01-15T00:00:00Z"), s("2024-06-15T00:00:00Z"), s("years")))
    }

    @Test
    fun datetimeDiffDefaultDays() {
        assertEquals(i(5), AirtableRuntime.DATETIME_DIFF(s("2024-01-20T00:00:00Z"), s("2024-01-15T00:00:00Z")))
    }

    @Test
    fun datetimeDiffNullIsZero() {
        assertEquals(i(0), AirtableRuntime.DATETIME_DIFF(JsonNull, s("2024-01-15T00:00:00Z"), s("days")))
    }

    @Test
    fun dateaddDays() {
        assertEquals(s("2024-01-20T00:00:00.000Z"), AirtableRuntime.DATEADD(s("2024-01-15T00:00:00Z"), i(5), s("days")))
    }

    @Test
    fun dateaddMonthsClamp() {
        // Jan 31 + 1 month = Feb 29 (2024 is a leap year).
        assertEquals(s("2024-02-29T00:00:00.000Z"), AirtableRuntime.DATEADD(s("2024-01-31T00:00:00Z"), i(1), s("months")))
    }

    @Test
    fun dateaddYears() {
        assertEquals(s("2025-01-15T00:00:00.000Z"), AirtableRuntime.DATEADD(s("2024-01-15T00:00:00Z"), i(1), s("years")))
    }

    @Test
    fun dateaddHours() {
        assertEquals(s("2024-01-15T15:00:00.000Z"), AirtableRuntime.DATEADD(s("2024-01-15T12:00:00Z"), i(3), s("hours")))
    }

    @Test
    fun dateaddNullIsNull() {
        assertEquals(JsonNull, AirtableRuntime.DATEADD(JsonNull, i(5), s("days")))
    }

    @Test
    fun isSameSameDay() {
        assertEquals(b(true), AirtableRuntime.IS_SAME(s("2025-04-20T10:00:00Z"), s("2025-04-20T15:00:00Z"), s("days")))
    }

    @Test
    fun isSameFalse() {
        assertEquals(b(false), AirtableRuntime.IS_SAME(s("2024-01-15T00:00:00Z"), s("2024-01-16T00:00:00Z"), s("days")))
    }

    @Test
    fun isBeforeDay() {
        assertEquals(b(true), AirtableRuntime.IS_BEFORE(s("2025-04-20T10:00:00Z"), s("2025-04-21T10:00:00Z"), s("days")))
    }

    @Test
    fun isBeforeFalseWhenAfter() {
        assertEquals(b(false), AirtableRuntime.IS_BEFORE(s("2025-04-22T10:00:00Z"), s("2025-04-21T10:00:00Z"), s("days")))
    }

    @Test
    fun isAfterTrue() {
        assertEquals(b(true), AirtableRuntime.IS_AFTER(s("2024-01-16T00:00:00Z"), s("2024-01-15T00:00:00Z"), s("days")))
    }

    @Test
    fun workdayBasic() {
        // Mon Jan 15 + 5 workdays = Mon Jan 22.
        assertEquals(s("2024-01-22T00:00:00.000Z"), AirtableRuntime.WORKDAY(s("2024-01-15T00:00:00Z"), i(5)))
    }

    @Test
    fun workdaySkipWeekend() {
        // Fri Jan 19 + 1 workday = Mon Jan 22.
        assertEquals(s("2024-01-22T00:00:00.000Z"), AirtableRuntime.WORKDAY(s("2024-01-19T00:00:00Z"), i(1)))
    }

    @Test
    fun workdayNegative() {
        // Mon Jan 22 - 1 workday = Fri Jan 19.
        assertEquals(s("2024-01-19T00:00:00.000Z"), AirtableRuntime.WORKDAY(s("2024-01-22T00:00:00Z"), i(-1)))
    }

    @Test
    fun workdayNullIsNull() {
        assertEquals(JsonNull, AirtableRuntime.WORKDAY(JsonNull, i(5)))
    }

    @Test
    fun workdayDiffBasic() {
        // Mon Jan 15 to Mon Jan 22 = 6 workdays (includes start day).
        assertEquals(i(6), AirtableRuntime.WORKDAY_DIFF(s("2024-01-15T00:00:00Z"), s("2024-01-22T00:00:00Z")))
    }

    @Test
    fun workdayDiffReverseIsNegative() {
        assertEquals(i(-6), AirtableRuntime.WORKDAY_DIFF(s("2024-01-22T00:00:00Z"), s("2024-01-15T00:00:00Z")))
    }

    @Test
    fun workdayDiffNullIsZero() {
        assertEquals(i(0), AirtableRuntime.WORKDAY_DIFF(JsonNull, s("2024-01-15T00:00:00Z")))
    }

    @Test
    fun setTimezoneBasic() {
        // UTC 12:00 → America/New_York (UTC-5 in January) = 07:00 wall clock.
        assertEquals(s("2024-01-15T07:00:00.000Z"), AirtableRuntime.SET_TIMEZONE(s("2024-01-15T12:00:00Z"), s("America/New_York")))
    }

    @Test
    fun setTimezoneInvalidZoneReturnsIso() {
        assertEquals(s("2024-01-15T12:00:00.000Z"), AirtableRuntime.SET_TIMEZONE(s("2024-01-15T12:00:00Z"), s("Not/AZone")))
    }

    @Test
    fun datetimeFormatDefault() {
        assertEquals(s("2024-01-15T14:30:00.000Z"), AirtableRuntime.DATETIME_FORMAT(s("2024-01-15T14:30:00Z")))
    }

    @Test
    fun datetimeFormatCustomDate() {
        assertEquals(s("2024-01-15"), AirtableRuntime.DATETIME_FORMAT(s("2024-01-15T14:30:00Z"), s("YYYY-MM-DD")))
    }

    @Test
    fun datetimeFormatTime() {
        assertEquals(s("14:30"), AirtableRuntime.DATETIME_FORMAT(s("2024-01-15T14:30:00Z"), s("HH:mm")))
    }

    @Test
    fun datetimeFormatNullIsEmpty() {
        assertEquals(s(""), AirtableRuntime.DATETIME_FORMAT(JsonNull, s("YYYY-MM-DD")))
    }

    @Test
    fun datestrBasic() {
        assertEquals(s("2024-01-15"), AirtableRuntime.DATESTR(s("2024-01-15T14:30:00Z")))
    }

    @Test
    fun datestrNullIsEmpty() {
        assertEquals(s(""), AirtableRuntime.DATESTR(JsonNull))
    }

    @Test
    fun timestrBasic() {
        assertEquals(s("14:30:00"), AirtableRuntime.TIMESTR(s("2024-01-15T14:30:00Z")))
    }

    @Test
    fun datetimeParseBasic() {
        assertEquals(s("2024-01-15T00:00:00.000Z"), AirtableRuntime.DATETIME_PARSE(s("2024-01-15")))
    }

    @Test
    fun datetimeParseGarbageIsNull() {
        assertEquals(JsonNull, AirtableRuntime.DATETIME_PARSE(s("not a date")))
    }

    @Test
    fun nowIsParseableIso() {
        assertNotNull(D(AirtableRuntime.NOW()))
    }

    @Test
    fun todayIsParseableIso() {
        assertNotNull(D(AirtableRuntime.TODAY()))
    }

    @Test
    fun tonowWithUnitIsPositiveForPastDate() {
        assertTrue(N(AirtableRuntime.TONOW(s("2000-01-01T00:00:00Z"), s("days"))) > 0)
    }

    @Test
    fun fromnowWithUnitIsNegativeForPastDate() {
        assertTrue(N(AirtableRuntime.FROMNOW(s("2000-01-01T00:00:00Z"), s("days"))) < 0)
    }

    @Test
    fun tonowHumanDurationForOldDateIsYears() {
        assertTrue(S(AirtableRuntime.TONOW(s("2000-01-01T00:00:00Z"))).endsWith("years"))
    }

    // endregion

    // region Array (F8.8)

    @Test
    fun arrayJoinDefault() {
        assertEquals(s("1, 2, 3"), AirtableRuntime.ARRAYJOIN(arr(i(1), i(2), i(3))))
    }

    @Test
    fun arrayJoinCustomSep() {
        assertEquals(s("1-2"), AirtableRuntime.ARRAYJOIN(arr(i(1), i(2)), s("-")))
    }

    @Test
    fun arrayJoinNonArray() {
        assertEquals(s("hello"), AirtableRuntime.ARRAYJOIN(s("hello")))
    }

    @Test
    fun arrayJoinNullIsEmpty() {
        assertEquals(s(""), AirtableRuntime.ARRAYJOIN(null))
    }

    @Test
    fun arrayUniqueBasic() {
        assertEquals(arr(i(1), i(2), i(3)), AirtableRuntime.ARRAYUNIQUE(arr(i(1), i(2), i(1), i(3))))
    }

    @Test
    fun arrayUniquePreservesOrder() {
        assertEquals(arr(i(3), i(1), i(2)), AirtableRuntime.ARRAYUNIQUE(arr(i(3), i(1), i(2), i(1), i(3))))
    }

    @Test
    fun arrayCompactStripsNullsAndEmptyStrings() {
        assertEquals(arr(i(1), i(2)), AirtableRuntime.ARRAYCOMPACT(arr(i(1), JsonNull, s(""), i(2))))
    }

    @Test
    fun arrayCompactKeepsZeroAndFalse() {
        assertEquals(arr(i(0), b(false)), AirtableRuntime.ARRAYCOMPACT(arr(i(0), JsonNull, b(false), s(""))))
    }

    @Test
    fun arrayCompactNullInputIsEmptyArray() {
        assertEquals(arr(), AirtableRuntime.ARRAYCOMPACT(null))
    }

    @Test
    fun arrayFlattenNested() {
        assertEquals(arr(i(1), i(2), i(3), i(4)), AirtableRuntime.ARRAYFLATTEN(arr(i(1), arr(i(2), i(3)), i(4))))
    }

    @Test
    fun arrayFlattenDeep() {
        assertEquals(arr(i(1), i(2), i(3), i(4)), AirtableRuntime.ARRAYFLATTEN(arr(i(1), arr(i(2), arr(i(3), i(4))))))
    }

    @Test
    fun arrayFlattenAlreadyFlat() {
        assertEquals(arr(i(1), i(2), i(3)), AirtableRuntime.ARRAYFLATTEN(arr(i(1), i(2), i(3))))
    }

    @Test
    fun arrayFlattenNonArrayWraps() {
        assertEquals(arr(i(5)), AirtableRuntime.ARRAYFLATTEN(i(5)))
    }

    // endregion

    // region Regex (F8.9)

    @Test
    fun regexMatchTrue() {
        assertEquals(b(true), AirtableRuntime.REGEX_MATCH(s("hello"), s("^hel")))
    }

    @Test
    fun regexMatchFalse() {
        assertEquals(b(false), AirtableRuntime.REGEX_MATCH(s("hello"), s("^xyz")))
    }

    @Test
    fun regexMatchUnanchored() {
        assertEquals(b(true), AirtableRuntime.REGEX_MATCH(s("Hello"), s("^.e")))
    }

    @Test
    fun regexMatchInvalidPatternIsFalse() {
        assertEquals(b(false), AirtableRuntime.REGEX_MATCH(s("hello"), s("(")))
    }

    @Test
    fun regexExtractBasic() {
        assertEquals(s("123"), AirtableRuntime.REGEX_EXTRACT(s("hello123"), s("\\d+")))
    }

    @Test
    fun regexExtractFirstMatch() {
        assertEquals(s("e"), AirtableRuntime.REGEX_EXTRACT(s("Hello"), s("[aeiou]")))
    }

    @Test
    fun regexExtractNoMatchIsEmptyString() {
        // Swift parity: no match yields "" (the Rust runtime returns null here).
        assertEquals(s(""), AirtableRuntime.REGEX_EXTRACT(s("xyz"), s("[aeiou]")))
    }

    @Test
    fun regexReplaceBasic() {
        assertEquals(s("hexo"), AirtableRuntime.REGEX_REPLACE(s("hello"), s("l+"), s("x")))
    }

    @Test
    fun regexReplaceAllOccurrences() {
        assertEquals(s("H*ll*"), AirtableRuntime.REGEX_REPLACE(s("Hello"), s("[aeiou]"), s("*")))
    }

    // endregion
}

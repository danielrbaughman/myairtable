// AirtableRuntime: implements Airtable formula functions and operators.
//
// All operators route through this object for correct Airtable semantics:
// - BLANK() is null (treated as 0 numerically, "" as string)
// - Type coercion follows Airtable rules (booleans → 1/0, strings parsed to numbers, etc.)
// - Division by zero returns NaN for consistency
//
// Values flow as `JsonElement?` so functions compose naturally. Coercion
// helpers (V/N/S/A/AN/AS/D/isTruthy) live in AirtableJson.kt as top-level
// functions shared with the transpiler output.
// Ported from static/swift/AirtableRuntime.swift.

// Formula functions deliberately use Airtable's UPPERCASE naming shared with
// the Rust/Swift targets; the formula transpiler emits calls to these exact names.
@file:Suppress("ktlint:standard:function-naming")

package myairtable

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.temporal.WeekFields
import java.util.Locale
import java.util.regex.Pattern
import java.util.regex.PatternSyntaxException
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sqrt

object AirtableRuntime {
    // =========================================================================
    // region Truthiness + special values (F8.4 logic)
    // =========================================================================

    fun BLANK(): JsonElement = JsonNull

    fun TRUE(): JsonElement = JsonPrimitive(true)

    fun FALSE(): JsonElement = JsonPrimitive(false)

    fun IF(
        condition: JsonElement?,
        ifTrue: JsonElement?,
        ifFalse: JsonElement?,
    ): JsonElement = if (isTruthy(condition)) ifTrue ?: JsonNull else ifFalse ?: JsonNull

    fun SWITCH(
        expr: JsonElement?,
        cases: List<Pair<JsonElement, JsonElement>>,
        defaultValue: JsonElement? = null,
    ): JsonElement {
        val key = S(expr)
        for ((candidate, value) in cases) {
            if (S(candidate) == key) return value
        }
        return defaultValue ?: JsonNull
    }

    /** ISERROR returns true for NaN doubles — signals a computation error. */
    fun ISERROR(value: JsonElement?): JsonElement {
        val isNan = value is JsonPrimitive && !value.isString && value.doubleOrNull?.isNaN() == true
        return JsonPrimitive(isNan)
    }

    @Suppress("UNUSED_PARAMETER")
    fun ERROR(message: JsonElement? = null): JsonElement {
        // Surface as NaN so ISERROR picks it up.
        return JsonPrimitive(Double.NaN)
    }

    // endregion

    // =========================================================================
    // region Math functions (F8.4)
    // =========================================================================

    /** Swift's `Double.rounded()`: round half away from zero. */
    private fun roundHalfAwayFromZero(d: Double): Double = if (d >= 0) floor(d + 0.5) else ceil(d - 0.5)

    private fun numValue(d: Double): JsonElement =
        if (d.isFinite() && d == floor(d) && abs(d) < 1e15) {
            JsonPrimitive(d.toLong())
        } else {
            JsonPrimitive(d)
        }

    fun SUM(vararg args: JsonElement?): JsonElement = numValue(AN(args.toList()).sum())

    fun AVERAGE(vararg args: JsonElement?): JsonElement {
        val nums = AN(args.toList())
        if (nums.isEmpty()) return JsonPrimitive(Double.NaN)
        return numValue(nums.sum() / nums.size)
    }

    fun MIN(vararg args: JsonElement?): JsonElement {
        val m = AN(args.toList()).minOrNull() ?: return JsonPrimitive(Double.NaN)
        return numValue(m)
    }

    fun MAX(vararg args: JsonElement?): JsonElement {
        val m = AN(args.toList()).maxOrNull() ?: return JsonPrimitive(Double.NaN)
        return numValue(m)
    }

    fun COUNT(vararg args: JsonElement?): JsonElement {
        val c =
            A(args.toList()).count { v ->
                v is JsonPrimitive && !v.isString && v.booleanOrNull == null && v.doubleOrNull != null
            }
        return JsonPrimitive(c)
    }

    fun COUNTA(vararg args: JsonElement?): JsonElement {
        val c =
            A(args.toList()).count { v ->
                when {
                    v is JsonNull -> false
                    v is JsonPrimitive && v.isString && v.content.isEmpty() -> false
                    else -> true
                }
            }
        return JsonPrimitive(c)
    }

    fun ROUND(
        value: JsonElement?,
        precision: JsonElement? = null,
    ): JsonElement {
        val n = N(value)
        val p = N(precision).toInt()
        val factor = 10.0.pow(p)
        return numValue(roundHalfAwayFromZero(n * factor) / factor)
    }

    fun ROUNDUP(
        value: JsonElement?,
        precision: JsonElement? = null,
    ): JsonElement {
        val n = N(value)
        val p = N(precision).toInt()
        val factor = 10.0.pow(p)
        val r = if (n >= 0) ceil(n * factor) / factor else floor(n * factor) / factor
        return numValue(r)
    }

    fun ROUNDDOWN(
        value: JsonElement?,
        precision: JsonElement? = null,
    ): JsonElement {
        val n = N(value)
        val p = N(precision).toInt()
        val factor = 10.0.pow(p)
        val r = if (n >= 0) floor(n * factor) / factor else ceil(n * factor) / factor
        return numValue(r)
    }

    fun CEILING(
        value: JsonElement?,
        significance: JsonElement? = null,
    ): JsonElement {
        val n = N(value)
        val s = if (significance == null) 1.0 else N(significance)
        val sig = if (s == 0.0) 1.0 else s
        return numValue(ceil(n / sig) * sig)
    }

    fun FLOOR(
        value: JsonElement?,
        significance: JsonElement? = null,
    ): JsonElement {
        val n = N(value)
        val s = if (significance == null) 1.0 else N(significance)
        val sig = if (s == 0.0) 1.0 else s
        return numValue(floor(n / sig) * sig)
    }

    fun LOG(
        value: JsonElement?,
        base: JsonElement? = null,
    ): JsonElement {
        val n = N(value)
        if (base != null) {
            return numValue(ln(n) / ln(N(base)))
        }
        return numValue(log10(n))
    }

    fun EVEN(value: JsonElement?): JsonElement {
        val n = N(value)
        val c = ceil(abs(n))
        var r = if (c % 2.0 == 0.0) c else c + 1
        if (n < 0) r = -r
        return JsonPrimitive(r.toLong())
    }

    fun ODD(value: JsonElement?): JsonElement {
        val n = N(value)
        val c = ceil(abs(n))
        var r = if (c % 2.0 == 1.0) c else c + 1
        if (n < 0) r = -r
        return JsonPrimitive(r.toLong())
    }

    fun VALUE(value: JsonElement?): JsonElement {
        if (value == null) return JsonPrimitive(0)
        val s = S(value)
        if (s.contains(".")) {
            s.toDoubleOrNull()?.let { return JsonPrimitive(it) }
        } else {
            s.toLongOrNull()?.let { return JsonPrimitive(it) }
        }
        return JsonPrimitive(Double.NaN)
    }

    fun POWER(
        base: JsonElement?,
        exp: JsonElement?,
    ): JsonElement = numValue(N(base).pow(N(exp)))

    fun MOD(
        value: JsonElement?,
        divisor: JsonElement?,
    ): JsonElement {
        val d = N(divisor)
        if (d == 0.0) return JsonPrimitive(Double.NaN)
        return numValue(N(value) % d)
    }

    fun ABS(value: JsonElement?): JsonElement = numValue(abs(N(value)))

    fun EXP(value: JsonElement?): JsonElement {
        val n = N(value)
        // JVM Math.exp(1.0) is one ULP above Math.E (2.7182818284590455 vs
        // ...45); V8 — and therefore Airtable — returns the correctly-rounded
        // E. Pin the integer-1 case so local evaluation matches the API.
        return numValue(if (n == 1.0) kotlin.math.E else kotlin.math.exp(n))
    }

    fun SQRT(value: JsonElement?): JsonElement = numValue(sqrt(N(value)))

    fun INT(value: JsonElement?): JsonElement = JsonPrimitive(floor(N(value)).toLong())

    // endregion

    // =========================================================================
    // region String functions (F8.6)
    // =========================================================================
    //
    // String positions/lengths count Unicode code points (Swift counts grapheme
    // clusters; code points are the closest JVM analog and match the Rust target).

    private fun cpLength(s: String): Int = s.codePointCount(0, s.length)

    private fun cpIndex(
        s: String,
        cpOffset: Int,
    ): Int = s.offsetByCodePoints(0, cpOffset)

    fun LEN(value: JsonElement?): JsonElement = JsonPrimitive(cpLength(S(value)))

    fun LEFT(
        text: JsonElement?,
        count: JsonElement?,
    ): JsonElement {
        val s = S(text)
        val n = max(0, N(count).toInt())
        val end = cpIndex(s, min(n, cpLength(s)))
        return JsonPrimitive(s.substring(0, end))
    }

    fun RIGHT(
        text: JsonElement?,
        count: JsonElement?,
    ): JsonElement {
        val s = S(text)
        val n = max(0, N(count).toInt())
        val total = cpLength(s)
        val start = cpIndex(s, total - min(n, total))
        return JsonPrimitive(s.substring(start))
    }

    fun MID(
        text: JsonElement?,
        start: JsonElement?,
        count: JsonElement?,
    ): JsonElement {
        val s = S(text)
        val startIdx = max(0, N(start).toInt() - 1)
        val len = max(0, N(count).toInt())
        val total = cpLength(s)
        if (startIdx >= total) return JsonPrimitive("")
        val begin = cpIndex(s, startIdx)
        val end = cpIndex(s, min(startIdx + len, total))
        return JsonPrimitive(s.substring(begin, end))
    }

    fun FIND(
        needle: JsonElement?,
        haystack: JsonElement?,
        start: JsonElement? = null,
    ): JsonElement {
        val hay = S(haystack)
        val nee = S(needle)
        val offset = if (start == null) 0 else max(0, N(start).toInt() - 1)
        if (offset >= cpLength(hay)) return JsonPrimitive(0)
        val idx = hay.indexOf(nee, cpIndex(hay, offset))
        if (idx < 0) return JsonPrimitive(0)
        return JsonPrimitive(hay.codePointCount(0, idx) + 1)
    }

    fun SEARCH(
        needle: JsonElement?,
        haystack: JsonElement?,
        start: JsonElement? = null,
    ): JsonElement {
        val hay = S(haystack).lowercase()
        val nee = S(needle).lowercase()
        val offset = if (start == null) 0 else max(0, N(start).toInt() - 1)
        if (offset >= cpLength(hay)) return JsonPrimitive(0)
        val idx = hay.indexOf(nee, cpIndex(hay, offset))
        if (idx < 0) return JsonPrimitive(0)
        return JsonPrimitive(hay.codePointCount(0, idx) + 1)
    }

    fun SUBSTITUTE(
        text: JsonElement?,
        old: JsonElement?,
        new: JsonElement?,
        occurrence: JsonElement? = null,
    ): JsonElement {
        val s = S(text)
        val o = S(old)
        val n = S(new)
        if (o.isEmpty()) return JsonPrimitive(s)
        if (occurrence == null) return JsonPrimitive(s.replace(o, n))
        // Replace only the Nth occurrence.
        val target = N(occurrence).toInt()
        var current = 1
        var searchFrom = 0
        while (true) {
            val idx = s.indexOf(o, searchFrom)
            if (idx < 0) break
            if (current == target) {
                return JsonPrimitive(s.substring(0, idx) + n + s.substring(idx + o.length))
            }
            current += 1
            searchFrom = idx + 1
        }
        return JsonPrimitive(s)
    }

    fun REPLACE(
        text: JsonElement?,
        start: JsonElement?,
        count: JsonElement?,
        replacement: JsonElement?,
    ): JsonElement {
        val s = S(text)
        val startIdx = max(0, N(start).toInt() - 1)
        val len = max(0, N(count).toInt())
        val r = S(replacement)
        val total = cpLength(s)
        if (startIdx > total) return JsonPrimitive(s + r)
        val begin = cpIndex(s, startIdx)
        val end = cpIndex(s, min(startIdx + len, total))
        return JsonPrimitive(s.substring(0, begin) + r + s.substring(end))
    }

    fun LOWER(value: JsonElement?): JsonElement = JsonPrimitive(S(value).lowercase())

    fun UPPER(value: JsonElement?): JsonElement = JsonPrimitive(S(value).uppercase())

    fun TRIM(value: JsonElement?): JsonElement = JsonPrimitive(S(value).trim())

    fun REPT(
        text: JsonElement?,
        count: JsonElement?,
    ): JsonElement {
        val s = S(text)
        val n = max(0, N(count).toInt())
        return JsonPrimitive(s.repeat(n))
    }

    fun CONCATENATE(vararg args: JsonElement?): JsonElement = JsonPrimitive(args.joinToString("") { S(it) })

    /** Characters NOT percent-encoded, mirroring Swift's `CharacterSet.urlQueryAllowed`. */
    private const val URL_QUERY_ALLOWED_EXTRA = "-._~!\$&'()*+,;=:@/?"

    fun ENCODE_URL_COMPONENT(value: JsonElement?): JsonElement {
        val s = S(value)
        val out = StringBuilder()
        for (byte in s.toByteArray(Charsets.UTF_8)) {
            val b = byte.toInt() and 0xFF
            val c = b.toChar()
            if (b < 0x80 && (c.isLetterOrDigit() || c in URL_QUERY_ALLOWED_EXTRA)) {
                out.append(c)
            } else {
                out.append('%').append("%02X".format(b))
            }
        }
        return JsonPrimitive(out.toString())
    }

    fun T(value: JsonElement?): JsonElement {
        if (value is JsonPrimitive && value !is JsonNull && value.isString) {
            return JsonPrimitive(value.content)
        }
        return JsonPrimitive("")
    }

    // endregion

    // =========================================================================
    // region Date/time functions (F8.7)
    // =========================================================================

    private val isoFormatter: DateTimeFormatter =
        DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.ROOT).withZone(ZoneOffset.UTC)

    private fun iso(d: Instant): String = isoFormatter.format(d)

    private fun utc(d: Instant): ZonedDateTime = d.atZone(ZoneOffset.UTC)

    private fun isWorkingDay(z: ZonedDateTime): Boolean = z.dayOfWeek != DayOfWeek.SATURDAY && z.dayOfWeek != DayOfWeek.SUNDAY

    fun NOW(): JsonElement = JsonPrimitive(iso(Instant.now()))

    fun TODAY(): JsonElement {
        val zone = ZoneId.systemDefault()
        val d = LocalDate.now(zone).atStartOfDay(zone).toInstant()
        return JsonPrimitive(iso(d))
    }

    fun YEAR(value: JsonElement?): JsonElement {
        val d = D(value) ?: return JsonPrimitive(0)
        return JsonPrimitive(utc(d).year)
    }

    fun MONTH(value: JsonElement?): JsonElement {
        val d = D(value) ?: return JsonPrimitive(0)
        return JsonPrimitive(utc(d).monthValue)
    }

    fun DAY(value: JsonElement?): JsonElement {
        val d = D(value) ?: return JsonPrimitive(0)
        return JsonPrimitive(utc(d).dayOfMonth)
    }

    fun HOUR(value: JsonElement?): JsonElement {
        val d = D(value) ?: return JsonPrimitive(0)
        return JsonPrimitive(utc(d).hour)
    }

    fun MINUTE(value: JsonElement?): JsonElement {
        val d = D(value) ?: return JsonPrimitive(0)
        return JsonPrimitive(utc(d).minute)
    }

    fun SECOND(value: JsonElement?): JsonElement {
        val d = D(value) ?: return JsonPrimitive(0)
        return JsonPrimitive(utc(d).second)
    }

    fun WEEKDAY(value: JsonElement?): JsonElement {
        val d = D(value) ?: return JsonPrimitive(0)
        // Airtable: Sunday=0, Monday=1, ..., Saturday=6.
        // java.time DayOfWeek.value is 1 (Monday) ... 7 (Sunday).
        return JsonPrimitive(utc(d).dayOfWeek.value % 7)
    }

    fun DATETIME_DIFF(
        d1v: JsonElement?,
        d2v: JsonElement?,
        unit: JsonElement? = null,
    ): JsonElement {
        val d1 = D(d1v) ?: return JsonPrimitive(0)
        val d2 = D(d2v) ?: return JsonPrimitive(0)
        val diffSecs = (d1.toEpochMilli() - d2.toEpochMilli()) / 1000.0
        val v =
            when (S(unit).lowercase()) {
                "milliseconds" -> {
                    diffSecs * 1000
                }

                "seconds" -> {
                    diffSecs
                }

                "minutes" -> {
                    diffSecs / 60
                }

                "hours" -> {
                    diffSecs / 3600
                }

                "days", "" -> {
                    diffSecs / 86400
                }

                "weeks" -> {
                    diffSecs / (86400.0 * 7)
                }

                "months" -> {
                    val z1 = utc(d1)
                    val z2 = utc(d2)
                    return JsonPrimitive((z1.year - z2.year) * 12 + (z1.monthValue - z2.monthValue))
                }

                "years" -> {
                    return JsonPrimitive(utc(d1).year - utc(d2).year)
                }

                else -> {
                    diffSecs / 86400
                }
            }
        return JsonPrimitive(v.toLong())
    }

    fun DATEADD(
        date: JsonElement?,
        count: JsonElement?,
        unit: JsonElement?,
    ): JsonElement {
        val d = D(date) ?: return JsonNull
        val n = N(count).toLong()
        val z = utc(d)
        val result =
            when (S(unit).lowercase()) {
                "years" -> z.plusYears(n)
                "months" -> z.plusMonths(n)
                "weeks" -> z.plusWeeks(n)
                "days" -> z.plusDays(n)
                "hours" -> z.plusHours(n)
                "minutes" -> z.plusMinutes(n)
                "seconds" -> z.plusSeconds(n)
                else -> z.plusDays(n)
            }
        return JsonPrimitive(iso(result.toInstant()))
    }

    fun IS_SAME(
        d1: JsonElement?,
        d2: JsonElement?,
        unit: JsonElement? = null,
    ): JsonElement {
        val u = unit ?: JsonPrimitive("days")
        val v = (DATETIME_DIFF(d1, d2, u) as? JsonPrimitive)?.longOrNull ?: return JsonPrimitive(false)
        return JsonPrimitive(v == 0L)
    }

    fun IS_BEFORE(
        d1: JsonElement?,
        d2: JsonElement?,
        unit: JsonElement? = null,
    ): JsonElement {
        val u = unit ?: JsonPrimitive("days")
        val v = (DATETIME_DIFF(d1, d2, u) as? JsonPrimitive)?.longOrNull ?: return JsonPrimitive(false)
        return JsonPrimitive(v < 0L)
    }

    fun IS_AFTER(
        d1: JsonElement?,
        d2: JsonElement?,
        unit: JsonElement? = null,
    ): JsonElement {
        val u = unit ?: JsonPrimitive("days")
        val v = (DATETIME_DIFF(d1, d2, u) as? JsonPrimitive)?.longOrNull ?: return JsonPrimitive(false)
        return JsonPrimitive(v > 0L)
    }

    /** Human-friendly duration string between two dates. */
    private fun humanDuration(
        d1v: JsonElement?,
        d2v: JsonElement?,
    ): String {
        val d1 = D(d1v) ?: return ""
        val d2 = D(d2v) ?: return ""
        val diff = abs(((d1.toEpochMilli() - d2.toEpochMilli()) / 1000.0).toLong())
        val minutes = diff / 60
        val hours = minutes / 60
        val days = hours / 24
        val z1 = utc(d1)
        val z2 = utc(d2)
        val months = abs((z1.year - z2.year) * 12 + (z1.monthValue - z2.monthValue)).toLong()
        val years = months / 12

        fun plural(
            n: Long,
            unit: String,
        ): String = "$n $unit" + if (n == 1L) "" else "s"
        if (years > 0) return plural(years, "year")
        if (months > 0) return plural(months, "month")
        if (days > 0) return plural(days, "day")
        if (hours > 0) return plural(hours, "hour")
        if (minutes > 0) return plural(minutes, "minute")
        return plural(diff, "second")
    }

    fun TONOW(
        date: JsonElement?,
        unit: JsonElement? = null,
    ): JsonElement {
        if (unit != null) {
            return DATETIME_DIFF(NOW(), date, unit)
        }
        return JsonPrimitive(humanDuration(date, NOW()))
    }

    fun FROMNOW(
        date: JsonElement?,
        unit: JsonElement? = null,
    ): JsonElement {
        if (unit != null) {
            return DATETIME_DIFF(date, NOW(), unit)
        }
        return JsonPrimitive(humanDuration(date, NOW()))
    }

    /** Week number of the year (week starts on the supplied day; default Sunday). */
    fun WEEKNUM(
        date: JsonElement?,
        startDay: JsonElement? = null,
    ): JsonElement {
        val d = D(date) ?: return JsonPrimitive(0)
        val names =
            mapOf(
                "sunday" to DayOfWeek.SUNDAY,
                "monday" to DayOfWeek.MONDAY,
                "tuesday" to DayOfWeek.TUESDAY,
                "wednesday" to DayOfWeek.WEDNESDAY,
                "thursday" to DayOfWeek.THURSDAY,
                "friday" to DayOfWeek.FRIDAY,
                "saturday" to DayOfWeek.SATURDAY,
            )
        val first = names[S(startDay).lowercase()] ?: DayOfWeek.SUNDAY
        // Minimal days in first week = 1, matching Apple's gregorian Calendar default.
        val weekFields = WeekFields.of(first, 1)
        return JsonPrimitive(utc(d).get(weekFields.weekOfYear()))
    }

    /** WORKDAY advances a date by N working days (Mon–Fri). */
    fun WORKDAY(
        start: JsonElement?,
        numDays: JsonElement?,
    ): JsonElement {
        val d = D(start) ?: return JsonNull
        var z = utc(d)
        var remaining = N(numDays).toInt()
        val direction = if (remaining >= 0) 1L else -1L
        remaining = abs(remaining)
        while (remaining > 0) {
            z = z.plusDays(direction)
            if (isWorkingDay(z)) remaining -= 1
        }
        return JsonPrimitive(iso(z.toInstant()))
    }

    /** Count working days (Mon–Fri) between two dates. Signed (start later → negative). */
    fun WORKDAY_DIFF(
        start: JsonElement?,
        end: JsonElement?,
    ): JsonElement {
        val d1 = D(start) ?: return JsonPrimitive(0)
        val d2 = D(end) ?: return JsonPrimitive(0)
        var count = 0
        var current = utc(d1)
        val direction = if (d2 > d1) 1 else -1
        if (isWorkingDay(current)) count += direction
        while ((direction == 1 && current.toInstant() < d2) || (direction == -1 && current.toInstant() > d2)) {
            current = current.plusDays(direction.toLong())
            if (isWorkingDay(current)) count += direction
        }
        return JsonPrimitive(count)
    }

    /**
     * Reinterpret a datetime in a different timezone. Returns the wall-clock
     * value as an ISO string (matching the Python runtime's behavior).
     */
    fun SET_TIMEZONE(
        date: JsonElement?,
        tz: JsonElement?,
    ): JsonElement {
        val d = D(date) ?: return JsonNull
        val zone =
            try {
                ZoneId.of(S(tz))
            } catch (_: Exception) {
                null
            } ?: return JsonPrimitive(iso(d))
        // Offset the UTC instant so the "clock face" matches the target zone.
        val offset = zone.rules.getOffset(d).totalSeconds
        return JsonPrimitive(iso(d.plusSeconds(offset.toLong())))
    }

    fun DATETIME_FORMAT(
        date: JsonElement?,
        fmt: JsonElement? = null,
    ): JsonElement {
        val d = D(date) ?: return JsonPrimitive("")
        if (fmt == null) return JsonPrimitive(iso(d))
        // Moment.js → DateTimeFormatter token mapping.
        val pattern =
            S(fmt)
                .replace("YYYY", "yyyy")
                .replace("YY", "yy")
                .replace("DD", "dd")
        return try {
            JsonPrimitive(DateTimeFormatter.ofPattern(pattern, Locale.US).withZone(ZoneOffset.UTC).format(d))
        } catch (_: Exception) {
            JsonPrimitive(iso(d))
        }
    }

    fun DATESTR(value: JsonElement?): JsonElement {
        val d = D(value) ?: return JsonPrimitive("")
        return JsonPrimitive(DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.ROOT).withZone(ZoneOffset.UTC).format(d))
    }

    fun TIMESTR(value: JsonElement?): JsonElement {
        val d = D(value) ?: return JsonPrimitive("")
        return JsonPrimitive(DateTimeFormatter.ofPattern("HH:mm:ss", Locale.ROOT).withZone(ZoneOffset.UTC).format(d))
    }

    @Suppress("UNUSED_PARAMETER")
    fun DATETIME_PARSE(
        value: JsonElement?,
        fmt: JsonElement? = null,
    ): JsonElement {
        // Input-format override is ignored — we try ISO 8601 then a few fallbacks.
        val d = D(value) ?: return JsonNull
        return JsonPrimitive(iso(d))
    }

    // endregion

    // =========================================================================
    // region Array functions (F8.8)
    // =========================================================================

    fun ARRAYJOIN(
        arr: JsonElement?,
        separator: JsonElement? = null,
    ): JsonElement {
        val sep = if (separator == null) ", " else S(separator)
        if (arr == null) return JsonPrimitive("")
        if (arr is JsonArray) {
            return JsonPrimitive(arr.joinToString(sep) { S(it) })
        }
        return JsonPrimitive(S(arr))
    }

    fun ARRAYUNIQUE(arr: JsonElement?): JsonElement {
        if (arr == null) return JsonArray(emptyList())
        if (arr !is JsonArray) return JsonArray(listOf(arr))
        val seen = mutableListOf<JsonElement>()
        for (v in arr) {
            if (v !in seen) seen.add(v)
        }
        return JsonArray(seen)
    }

    fun ARRAYCOMPACT(arr: JsonElement?): JsonElement {
        if (arr == null) return JsonArray(emptyList())
        if (arr !is JsonArray) return JsonArray(listOf(arr))
        return JsonArray(
            arr.filter { v ->
                when {
                    v is JsonNull -> false
                    v is JsonPrimitive && v.isString && v.content.isEmpty() -> false
                    else -> true
                }
            },
        )
    }

    fun ARRAYFLATTEN(arr: JsonElement?): JsonElement {
        if (arr == null) return JsonArray(emptyList())
        if (arr !is JsonArray) return JsonArray(listOf(arr))
        val out = mutableListOf<JsonElement>()

        fun flatten(xs: JsonArray) {
            for (x in xs) {
                if (x is JsonArray) flatten(x) else out.add(x)
            }
        }
        flatten(arr)
        return JsonArray(out)
    }

    // endregion

    // =========================================================================
    // region Regex (F8.9)
    // =========================================================================

    fun REGEX_EXTRACT(
        text: JsonElement?,
        pattern: JsonElement?,
    ): JsonElement {
        val s = S(text)
        val re =
            try {
                Pattern.compile(S(pattern))
            } catch (_: PatternSyntaxException) {
                return JsonPrimitive("")
            }
        val m = re.matcher(s)
        if (!m.find()) return JsonPrimitive("")
        return JsonPrimitive(m.group())
    }

    fun REGEX_MATCH(
        text: JsonElement?,
        pattern: JsonElement?,
    ): JsonElement {
        val s = S(text)
        val re =
            try {
                Pattern.compile(S(pattern))
            } catch (_: PatternSyntaxException) {
                return JsonPrimitive(false)
            }
        return JsonPrimitive(re.matcher(s).find())
    }

    fun REGEX_REPLACE(
        text: JsonElement?,
        pattern: JsonElement?,
        replacement: JsonElement?,
    ): JsonElement {
        val s = S(text)
        val r = S(replacement)
        val re =
            try {
                Pattern.compile(S(pattern))
            } catch (_: PatternSyntaxException) {
                return JsonPrimitive(s)
            }
        return JsonPrimitive(re.matcher(s).replaceAll(r))
    }

    // endregion
}

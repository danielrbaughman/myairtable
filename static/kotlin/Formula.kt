// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable

// =============================================================================
// region Combinators

/** Top-level formula combinators matching Airtable's logical functions. */
object Formulas {
    /** Combine formulas with AND logic. Empty strings are filtered out. */
    fun and(vararg args: String): String = and(args.toList())

    fun and(args: List<String>): String {
        val filtered = args.filter { it.isNotEmpty() }
        return when (filtered.size) {
            0 -> ""
            1 -> filtered[0]
            else -> "AND(${filtered.joinToString(",")})"
        }
    }

    /** Combine formulas with OR logic. Empty strings are filtered out. */
    fun or(vararg args: String): String = or(args.toList())

    fun or(args: List<String>): String {
        val filtered = args.filter { it.isNotEmpty() }
        return when (filtered.size) {
            0 -> ""
            1 -> filtered[0]
            else -> "OR(${filtered.joinToString(",")})"
        }
    }

    /** Negate a formula. */
    fun not(formula: String): String = "NOT($formula)"

    /** Exclusive OR. Empty strings are filtered out. */
    fun xor(vararg args: String): String = xor(args.toList())

    fun xor(args: List<String>): String {
        val filtered = args.filter { it.isNotEmpty() }
        return when (filtered.size) {
            0 -> ""
            1 -> filtered[0]
            else -> "XOR(${filtered.joinToString(",")})"
        }
    }
}

// endregion

// =============================================================================
// region Helpers

private fun wrapField(
    field: String,
    caseSensitive: Boolean,
    trim: Boolean,
): String {
    var v = field
    if (trim) v = "TRIM($v)"
    if (!caseSensitive) v = "LOWER($v)"
    return v
}

/**
 * Escape a value for an Airtable double-quoted formula string. Backslashes are
 * escaped FIRST, then quotes — otherwise a trailing `\` leaves the closing
 * quote live and the remainder of the value executes as formula code
 * (myairtable-53ip).
 */
internal fun escapeFormulaString(value: String): String = value.replace("\\", "\\\\").replace("\"", "\\\"")

/** Escape a value for an Airtable single-quoted formula string. */
internal fun escapeFormulaStringSingle(value: String): String = value.replace("\\", "\\\\").replace("'", "\\'")

private fun wrapValueStr(
    value: String,
    caseSensitive: Boolean,
    trim: Boolean,
): String {
    var v = "\"${escapeFormulaString(value)}\""
    if (trim) v = "TRIM($v)"
    if (!caseSensitive) v = "LOWER($v)"
    return v
}

// endregion

// =============================================================================
// region FormulaField interface

/**
 * Base interface for all formula field types. Provides field reference and
 * empty/not-empty checks.
 */
interface FormulaField {
    val fieldId: String

    /** Airtable field reference: `{fieldId}`. */
    val field: String get() = "{$fieldId}"

    /** Field is blank. */
    fun empty(): String = "$field=BLANK()"

    /** Field is not blank. */
    fun notEmpty(): String = "$field!=BLANK()"
}

// endregion

// =============================================================================
// region Text operations

/** Text operations shared by text, select, and lookup fields. */
interface FormulaTextOps : FormulaField {
    /**
     * Field reference used in string operations (FIND/LEN with LOWER/TRIM).
     * Lookup fields override this to wrap the reference in
     * `ARRAYJOIN(field, ", ")` so Airtable can coerce the array to a string.
     * Defaults to the bare `{field}` reference.
     *
     * `this.` is required: inside a getter the bare identifier `field` is
     * Kotlin's backing-field soft keyword.
     */
    val stringField: String get() = this.field

    /**
     * Exact equality.
     *
     * Named `eq` rather than `equals` because `equals(value)` would overload
     * `Any.equals` and silently resolve to the wrong method (§2.3.2).
     */
    fun eq(
        value: String,
        caseSensitive: Boolean = true,
        trim: Boolean = false,
    ): String {
        val f = wrapField(field, caseSensitive, trim)
        val v = wrapValueStr(value, caseSensitive, trim)
        return "$f=$v"
    }

    /** Equals any of the given values. */
    fun equalsAny(
        values: List<String>,
        caseSensitive: Boolean = true,
        trim: Boolean = false,
    ): String = Formulas.or(values.map { eq(it, caseSensitive, trim) })

    /** Not equal. Named `neq` for symmetry with `eq` (§2.3.2). */
    fun neq(
        value: String,
        caseSensitive: Boolean = true,
        trim: Boolean = false,
    ): String {
        val f = wrapField(field, caseSensitive, trim)
        val v = wrapValueStr(value, caseSensitive, trim)
        return "$f!=$v"
    }

    /** Contains substring. */
    fun contains(
        value: String,
        caseSensitive: Boolean = true,
        trim: Boolean = false,
    ): String {
        val f = wrapField(stringField, caseSensitive, trim)
        val v = wrapValueStr(value, caseSensitive, trim)
        return "FIND($v,$f)>0"
    }

    /** Contains any of the given values. */
    fun containsAny(
        values: List<String>,
        caseSensitive: Boolean = true,
        trim: Boolean = false,
    ): String = Formulas.or(values.map { contains(it, caseSensitive, trim) })

    /** Contains all of the given values. */
    fun containsAll(
        values: List<String>,
        caseSensitive: Boolean = true,
        trim: Boolean = false,
    ): String = Formulas.and(values.map { contains(it, caseSensitive, trim) })

    /** Does not contain substring. */
    fun notContains(
        value: String,
        caseSensitive: Boolean = true,
        trim: Boolean = false,
    ): String = Formulas.not(contains(value, caseSensitive, trim))

    /** Starts with the given value. */
    fun startsWith(
        value: String,
        caseSensitive: Boolean = true,
        trim: Boolean = false,
    ): String {
        val f = wrapField(stringField, caseSensitive, trim)
        val v = wrapValueStr(value, caseSensitive, trim)
        return "FIND($v,$f)=1"
    }

    /** Does not start with the given value. */
    fun notStartsWith(
        value: String,
        caseSensitive: Boolean = true,
        trim: Boolean = false,
    ): String {
        val f = wrapField(stringField, caseSensitive, trim)
        val v = wrapValueStr(value, caseSensitive, trim)
        return "FIND($v,$f)!=1"
    }

    /** Ends with the given value. */
    fun endsWith(
        value: String,
        caseSensitive: Boolean = true,
        trim: Boolean = false,
    ): String {
        val f = wrapField(stringField, caseSensitive, trim)
        val v = wrapValueStr(value, caseSensitive, trim)
        return "FIND($v,$f)=LEN($f)-LEN($v)+1"
    }

    /** Does not end with the given value. */
    fun notEndsWith(
        value: String,
        caseSensitive: Boolean = true,
        trim: Boolean = false,
    ): String {
        val f = wrapField(stringField, caseSensitive, trim)
        val v = wrapValueStr(value, caseSensitive, trim)
        return "FIND($v,$f)!=LEN($f)-LEN($v)+1"
    }

    /** Phone number equality (strips spaces, dashes, parens, plus, dots). */
    fun phoneEquals(value: String): String {
        val normalized = value.filter { it !in " -().+" }
        val strip = { s: String ->
            "SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE($s,\" \",\"\"),\"-\",\"\"),\"(\",\"\"),\")\",\"\"),\"+\",\"\"),\".\",\"\")"
        }
        return "${strip(field)}=\"${escapeFormulaString(normalized)}\""
    }

    /** Regex match. */
    fun regexMatch(pattern: String): String {
        // Escape for the formula-string context only; regex escapes like \\d
        // become \\\\d in the formula source, which Airtable's parser unescapes
        // back to \\d before handing the pattern to the regex engine.
        return "REGEX_MATCH($field,\"${escapeFormulaString(pattern)}\")"
    }
}

// endregion

// =============================================================================
// region Record ID

/** Formula builder for record IDs. */
class FormulaId {
    /** Match a specific record ID. */
    fun eq(id: String): String = "RECORD_ID()='${escapeFormulaStringSingle(id)}'"

    /** Match any of the given record IDs. */
    fun inList(ids: List<String>): String =
        when (ids.size) {
            0 -> "FALSE()"
            1 -> eq(ids[0])
            else -> Formulas.or(ids.map { eq(it) })
        }
}

// endregion

// =============================================================================
// region Text Field

/** Formula builder for text fields. */
class FormulaTextField(
    override val fieldId: String,
) : FormulaTextOps

// endregion

// =============================================================================
// region Lookup Field

/**
 * Formula builder for `multipleLookupValues` / lookup fields.
 *
 * Lookup field values are arrays. Airtable does not auto-coerce arrays through
 * `LOWER` / `TRIM` / `FIND`, so `contains`, `startsWith` and `endsWith` would
 * silently match nothing. `stringField` wraps the reference in
 * `ARRAYJOIN(field, ", ")` so string ops see a string.
 *
 * Equality (`=`) is unaffected — Airtable coerces array fields to a
 * comma-joined string under `=`, so direct equality already works.
 */
class FormulaLookupField(
    override val fieldId: String,
) : FormulaTextOps {
    override val stringField: String get() = "ARRAYJOIN(${this.field}, \", \")"
}

// endregion

// =============================================================================
// region Single Select Field

/** Formula builder for single-select fields. */
class FormulaSingleSelectField(
    override val fieldId: String,
) : FormulaTextOps

// endregion

// =============================================================================
// region Multi Select Field

/** Formula builder for multi-select fields. */
class FormulaMultiSelectField(
    override val fieldId: String,
) : FormulaTextOps

// endregion

// =============================================================================
// region Number Field

/** Formula builder for number fields. */
class FormulaNumberField(
    override val fieldId: String,
) : FormulaField {
    /** Equal to value. Named `eq` rather than `equals` (§2.3.2). */
    fun eq(value: Number): String = "$field=$value"

    /** Not equal to value. Named `neq` for symmetry with `eq` (§2.3.2). */
    fun neq(value: Number): String = "$field!=$value"

    /** Greater than value. */
    fun greaterThan(value: Number): String = "$field>$value"

    /** Less than value. */
    fun lessThan(value: Number): String = "$field<$value"

    /** Greater than or equal to value. */
    fun greaterThanOrEquals(value: Number): String = "$field>=$value"

    /** Less than or equal to value. */
    fun lessThanOrEquals(value: Number): String = "$field<=$value"

    /** Between min and max. Inclusive by default. */
    fun between(
        min: Number,
        max: Number,
        inclusive: Boolean = true,
    ): String =
        if (inclusive) {
            Formulas.and(greaterThanOrEquals(min), lessThanOrEquals(max))
        } else {
            Formulas.and(greaterThan(min), lessThan(max))
        }
}

// endregion

// =============================================================================
// region Boolean Field

/** Formula builder for checkbox/boolean fields. */
class FormulaBooleanField(
    override val fieldId: String,
) : FormulaField {
    /** Equal to boolean value. Named `eq` rather than `equals` (§2.3.2). */
    fun eq(value: Boolean): String = if (value) isTrue() else isFalse()

    /** Field is checked/true. */
    fun isTrue(): String = "$field=TRUE()"

    /** Field is unchecked/false. */
    fun isFalse(): String = "$field=FALSE()"
}

// endregion

// =============================================================================
// region Date Field

/**
 * Either side of a date comparison: a literal date string or another date
 * field. String literals are accepted via dedicated overloads on
 * [FormulaDateComparison] and [FormulaDateField].
 */
interface FormulaDateOperand {
    /** The operand wrapped in `DATETIME_PARSE(...)` for comparison. */
    val datetimeParseExpr: String
}

/** A literal date string operand, e.g. `"2025-01-15"`. */
private class FormulaDateLiteral(
    private val value: String,
) : FormulaDateOperand {
    override val datetimeParseExpr: String get() = "DATETIME_PARSE('${escapeFormulaStringSingle(value)}')"
}

/** Intermediate builder for date "time ago" comparisons. */
class FormulaDateComparison internal constructor(
    private val fieldId: String,
    private val op: String,
) {
    /** Compare against another date field (or any date operand). */
    fun date(other: FormulaDateOperand): String = "${other.datetimeParseExpr}${op}DATETIME_PARSE({$fieldId})"

    /** Compare against a literal date string. */
    fun date(other: String): String = date(FormulaDateLiteral(other))

    fun millisecondsAgo(n: Int): String = ago(n, "milliseconds")

    fun secondsAgo(n: Int): String = ago(n, "seconds")

    fun minutesAgo(n: Int): String = ago(n, "minutes")

    fun hoursAgo(n: Int): String = ago(n, "hours")

    fun daysAgo(n: Int): String = ago(n, "days")

    fun weeksAgo(n: Int): String = ago(n, "weeks")

    fun monthsAgo(n: Int): String = ago(n, "months")

    fun quartersAgo(n: Int): String = ago(n, "quarters")

    fun yearsAgo(n: Int): String = ago(n, "years")

    private fun ago(
        n: Int,
        unit: String,
    ): String = "DATETIME_DIFF(NOW(),{$fieldId},\"$unit\")$op$n"
}

/** Formula builder for date fields. */
class FormulaDateField(
    override val fieldId: String,
) : FormulaField,
    FormulaDateOperand {
    override val datetimeParseExpr: String get() = "DATETIME_PARSE(${this.field})"

    private fun comparison(op: String): FormulaDateComparison = FormulaDateComparison(fieldId, op)

    /** Date equals. Pass a date string or another date field. */
    fun on(date: FormulaDateOperand): String = comparison("=").date(date)

    fun on(date: String): String = on(FormulaDateLiteral(date))

    /** Returns a [FormulaDateComparison] for chaining with time-ago methods. */
    fun on(): FormulaDateComparison = comparison("=")

    fun notOn(date: FormulaDateOperand): String = comparison("!=").date(date)

    fun notOn(date: String): String = notOn(FormulaDateLiteral(date))

    fun notOn(): FormulaDateComparison = comparison("!=")

    fun onOrAfter(date: FormulaDateOperand): String = comparison("<=").date(date)

    fun onOrAfter(date: String): String = onOrAfter(FormulaDateLiteral(date))

    fun onOrAfter(): FormulaDateComparison = comparison("<=")

    fun onOrBefore(date: FormulaDateOperand): String = comparison(">=").date(date)

    fun onOrBefore(date: String): String = onOrBefore(FormulaDateLiteral(date))

    fun onOrBefore(): FormulaDateComparison = comparison(">=")

    fun after(date: FormulaDateOperand): String = comparison("<").date(date)

    fun after(date: String): String = after(FormulaDateLiteral(date))

    fun after(): FormulaDateComparison = comparison("<")

    fun before(date: FormulaDateOperand): String = comparison(">").date(date)

    fun before(date: String): String = before(FormulaDateLiteral(date))

    fun before(): FormulaDateComparison = comparison(">")

    /** Date is between start and end. Inclusive by default. */
    fun between(
        start: FormulaDateOperand,
        end: FormulaDateOperand,
        inclusive: Boolean = true,
    ): String =
        if (inclusive) {
            Formulas.and(onOrAfter(start), onOrBefore(end))
        } else {
            Formulas.and(after(start), before(end))
        }

    fun between(
        start: String,
        end: FormulaDateOperand,
        inclusive: Boolean = true,
    ): String = between(FormulaDateLiteral(start), end, inclusive)

    fun between(
        start: FormulaDateOperand,
        end: String,
        inclusive: Boolean = true,
    ): String = between(start, FormulaDateLiteral(end), inclusive)

    fun between(
        start: String,
        end: String,
        inclusive: Boolean = true,
    ): String = between(FormulaDateLiteral(start), FormulaDateLiteral(end), inclusive)
}

// endregion

// =============================================================================
// region Attachments Field

/** Formula builder for attachment fields. */
class FormulaAttachmentsField(
    override val fieldId: String,
) : FormulaField {
    /** Has exactly N attachments. */
    fun count(n: Int): String = "LEN($field)=$n"

    /** Has no attachments. */
    override fun empty(): String = "LEN($field)=0"

    /** Has attachments. */
    override fun notEmpty(): String = "LEN($field)>0"
}

// endregion

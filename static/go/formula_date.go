// ==========================================
// MyAirtable static runtime.
// ==========================================

package airtable

import "strconv"

// DateOperand is either side of a date comparison: a literal date string or
// another date field. Both render to a DATETIME_PARSE(...) expression.
type DateOperand interface {
	datetimeParseExpr() string
}

// dateLiteral is a literal date-string operand, e.g. "2025-01-15".
type dateLiteral struct{ value string }

// DateLiteral wraps a literal date string as a DateOperand. Used to pass a
// string where a DateOperand is required (e.g. DateField.Between).
func DateLiteral(value string) DateOperand { return dateLiteral{value: value} }

func (d dateLiteral) datetimeParseExpr() string {
	return "DATETIME_PARSE('" + escapeFormulaStringSingle(d.value) + "')"
}

// =============================================================================
// DateField
// =============================================================================

// DateField is the formula builder for date / dateTime / createdTime /
// lastModifiedTime fields. It implements DateOperand so two date fields can be
// compared directly (field-vs-field).
type DateField struct {
	name string // {Field Name}
}

// NewDateField builds a DateField for the given Airtable field name.
func NewDateField(name string) DateField {
	return DateField{name: fieldRef(name)}
}

func (d DateField) field() string { return d.name }

// datetimeParseExpr lets a DateField be used as a comparison operand.
func (d DateField) datetimeParseExpr() string { return "DATETIME_PARSE(" + d.field() + ")" }

// IsEmpty: field is blank.
func (d DateField) IsEmpty() Formula { return Formula{expr: d.field() + "=BLANK()"} }

// IsNotEmpty: field is not blank.
func (d DateField) IsNotEmpty() Formula { return Formula{expr: d.field() + "!=BLANK()"} }

func (d DateField) comparison(op string) DateComparison {
	return DateComparison{name: d.name, op: op}
}

// ---- operand comparisons (date string or another date field) ----------------

// On: date equals the given operand.
func (d DateField) On(date DateOperand) Formula { return d.comparison("=").date(date) }

// NotOn: date does not equal the given operand.
func (d DateField) NotOn(date DateOperand) Formula { return d.comparison("!=").date(date) }

// OnOrAfter: date is on or after the given operand.
func (d DateField) OnOrAfter(date DateOperand) Formula { return d.comparison("<=").date(date) }

// OnOrBefore: date is on or before the given operand.
func (d DateField) OnOrBefore(date DateOperand) Formula { return d.comparison(">=").date(date) }

// After: date is after the given operand.
func (d DateField) After(date DateOperand) Formula { return d.comparison("<").date(date) }

// Before: date is before the given operand.
func (d DateField) Before(date DateOperand) Formula { return d.comparison(">").date(date) }

// ---- string-literal convenience ---------------------------------------------

// OnDate: date equals the given date string.
func (d DateField) OnDate(date string) Formula { return d.On(dateLiteral{date}) }

// NotOnDate: date does not equal the given date string.
func (d DateField) NotOnDate(date string) Formula { return d.NotOn(dateLiteral{date}) }

// OnOrAfterDate: date is on or after the given date string.
func (d DateField) OnOrAfterDate(date string) Formula { return d.OnOrAfter(dateLiteral{date}) }

// OnOrBeforeDate: date is on or before the given date string.
func (d DateField) OnOrBeforeDate(date string) Formula { return d.OnOrBefore(dateLiteral{date}) }

// AfterDate: date is after the given date string.
func (d DateField) AfterDate(date string) Formula { return d.After(dateLiteral{date}) }

// BeforeDate: date is before the given date string.
func (d DateField) BeforeDate(date string) Formula { return d.Before(dateLiteral{date}) }

// ---- between ----------------------------------------------------------------

// Between: date is between start and end (operands). inclusive selects the
// on-or-after/on-or-before boundary vs strict after/before.
func (d DateField) Between(start, end DateOperand, inclusive bool) Formula {
	if inclusive {
		return And(d.OnOrAfter(start), d.OnOrBefore(end))
	}
	return And(d.After(start), d.Before(end))
}

// BetweenDates: date is between two date strings.
func (d DateField) BetweenDates(start, end string, inclusive bool) Formula {
	return d.Between(dateLiteral{start}, dateLiteral{end}, inclusive)
}

// ---- time-ago chaining entrypoints ------------------------------------------

// OnChain starts an "=" comparison for chaining with time-ago methods.
func (d DateField) OnChain() DateComparison { return d.comparison("=") }

// NotOnChain starts a "!=" comparison for chaining with time-ago methods.
func (d DateField) NotOnChain() DateComparison { return d.comparison("!=") }

// OnOrAfterChain starts a "<=" comparison for chaining with time-ago methods.
func (d DateField) OnOrAfterChain() DateComparison { return d.comparison("<=") }

// OnOrBeforeChain starts a ">=" comparison for chaining with time-ago methods.
func (d DateField) OnOrBeforeChain() DateComparison { return d.comparison(">=") }

// AfterChain starts a "<" comparison for chaining with time-ago methods.
func (d DateField) AfterChain() DateComparison { return d.comparison("<") }

// BeforeChain starts a ">" comparison for chaining with time-ago methods.
func (d DateField) BeforeChain() DateComparison { return d.comparison(">") }

// =============================================================================
// DateComparison — intermediate builder for date "time-ago" comparisons.
// =============================================================================

// DateComparison is the chained intermediate produced by DateField.*Chain(). It
// resolves either against another date operand (date) or a relative "time ago"
// quantity (DaysAgo, WeeksAgo, ...).
type DateComparison struct {
	name string // {Field Name}
	op   string
}

// date resolves the comparison against another date operand.
func (c DateComparison) date(other DateOperand) Formula {
	return Formula{expr: other.datetimeParseExpr() + c.op + "DATETIME_PARSE(" + c.name + ")"}
}

// Date resolves the comparison against another date field (or any date operand).
func (c DateComparison) Date(other DateOperand) Formula { return c.date(other) }

// DateStr resolves the comparison against a literal date string.
func (c DateComparison) DateStr(other string) Formula { return c.date(dateLiteral{other}) }

func (c DateComparison) ago(n int, unit string) Formula {
	return Formula{expr: "DATETIME_DIFF(NOW()," + c.name + ",\"" + unit + "\")" + c.op + strconv.Itoa(n)}
}

// MillisecondsAgo: n milliseconds ago.
func (c DateComparison) MillisecondsAgo(n int) Formula { return c.ago(n, "milliseconds") }

// SecondsAgo: n seconds ago.
func (c DateComparison) SecondsAgo(n int) Formula { return c.ago(n, "seconds") }

// MinutesAgo: n minutes ago.
func (c DateComparison) MinutesAgo(n int) Formula { return c.ago(n, "minutes") }

// HoursAgo: n hours ago.
func (c DateComparison) HoursAgo(n int) Formula { return c.ago(n, "hours") }

// DaysAgo: n days ago.
func (c DateComparison) DaysAgo(n int) Formula { return c.ago(n, "days") }

// WeeksAgo: n weeks ago.
func (c DateComparison) WeeksAgo(n int) Formula { return c.ago(n, "weeks") }

// MonthsAgo: n months ago.
func (c DateComparison) MonthsAgo(n int) Formula { return c.ago(n, "months") }

// QuartersAgo: n quarters ago.
func (c DateComparison) QuartersAgo(n int) Formula { return c.ago(n, "quarters") }

// YearsAgo: n years ago.
func (c DateComparison) YearsAgo(n int) Formula { return c.ago(n, "years") }

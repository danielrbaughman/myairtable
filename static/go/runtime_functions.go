// ==========================================
// MyAirtable static runtime.
// ==========================================

package airtable

// The ~80 Airtable formula functions (math / logic / string / date / array /
// regex), ported from the Java AirtableRuntime to operate on the native `any`
// value model used by the Go runtime (nil / bool / float64 / string / []any /
// map[string]any — decoded JSON). The transpiler emits bare same-package calls
// to these UPPERCASE names; signatures take `any` / `...any` and return `any`.
//
// Numeric results are returned as float64 (the JSON-native numeric form). S()
// already strips the trailing ".0" from whole-number floats, so an integral
// float64 stringifies identically to the Java LongNode canonicalization.

import (
	"math"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// =============================================================================
// Internal helpers
// =============================================================================

// numValue is the single place numeric results are produced. Go's `any` model is
// float64-native, so (unlike Java's LongNode/DoubleNode split) we always return
// float64; integral values stringify without a ".0" via S().
func numValue(d float64) any { return d }

// roundHalfAwayFromZero rounds .5 away from zero (Swift's Double.rounded()).
func roundHalfAwayFromZero(d float64) float64 {
	if d >= 0 {
		return math.Floor(d + 0.5)
	}
	return math.Ceil(d - 0.5)
}

// isNumber reports whether a native value is a numeric type (not a numeric
// string). Mirrors Jackson's isNumber()/JS typeof number.
func isNumber(v any) bool {
	switch v.(type) {
	case float64, int, int64:
		return true
	default:
		return false
	}
}

// cpLength counts Unicode code points (rune count), matching the Java code-point
// semantics for string positions/lengths.
func cpLength(s string) int { return len([]rune(s)) }

// =============================================================================
// Logic + special values
// =============================================================================

// BLANK returns the empty value (nil).
func BLANK() any { return nil }

// TRUE returns boolean true.
func TRUE() any { return true }

// FALSE returns boolean false.
func FALSE() any { return false }

// IF returns ifTrue when the condition is truthy, else ifFalse.
func IF(condition, ifTrue, ifFalse any) any {
	if IsTruthy(condition) {
		return ifTrue
	}
	return ifFalse
}

// IFS evaluates (condition, value) pairs in order, returning the first value
// whose condition is truthy. With no match it returns nil. A trailing lone arg
// (odd count) is treated as a fallback value.
func IFS(args ...any) any {
	i := 0
	for ; i+1 < len(args); i += 2 {
		if IsTruthy(args[i]) {
			return args[i+1]
		}
	}
	if i < len(args) {
		// trailing odd arg acts as a default
		return args[i]
	}
	return nil
}

// SWITCH matches expr against alternating (pattern, value) pairs using S()
// coercion, returning the matched value or the fallback. The fallback comes
// SECOND (mirrors the Java signature where varargs must be last).
func SWITCH(expr any, fallback any, pairs ...any) any {
	key := S(expr)
	for i := 0; i+1 < len(pairs); i += 2 {
		if S(pairs[i]) == key {
			return pairs[i+1]
		}
	}
	return fallback
}

// AND returns true iff every argument is truthy.
func AND(args ...any) any {
	for _, a := range args {
		if !IsTruthy(a) {
			return false
		}
	}
	return true
}

// OR returns true iff any argument is truthy.
func OR(args ...any) any {
	for _, a := range args {
		if IsTruthy(a) {
			return true
		}
	}
	return false
}

// NOT returns the logical negation of the argument's truthiness.
func NOT(value any) any { return !IsTruthy(value) }

// XOR returns true iff an odd number of arguments are truthy.
func XOR(args ...any) any {
	count := 0
	for _, a := range args {
		if IsTruthy(a) {
			count++
		}
	}
	return count%2 == 1
}

// ISERROR returns true for NaN numbers (the runtime's error sentinel).
func ISERROR(value any) any {
	return isNumber(value) && math.IsNaN(N(value))
}

// ERROR surfaces a computation error as NaN so ISERROR can detect it.
func ERROR(args ...any) any { return math.NaN() }

// =============================================================================
// Math functions
// =============================================================================

// SUM adds all (flattened, numerically coerced) arguments.
func SUM(args ...any) any {
	total := 0.0
	for _, n := range AN(args...) {
		total += n
	}
	return numValue(total)
}

// AVERAGE returns the mean of all (flattened) arguments, or NaN if empty.
func AVERAGE(args ...any) any {
	nums := AN(args...)
	if len(nums) == 0 {
		return math.NaN()
	}
	total := 0.0
	for _, n := range nums {
		total += n
	}
	return numValue(total / float64(len(nums)))
}

// MIN returns the smallest of the (flattened) arguments, or NaN if empty.
func MIN(args ...any) any {
	nums := AN(args...)
	if len(nums) == 0 {
		return math.NaN()
	}
	m := nums[0]
	for _, n := range nums {
		if n < m {
			m = n
		}
	}
	return numValue(m)
}

// MAX returns the largest of the (flattened) arguments, or NaN if empty.
func MAX(args ...any) any {
	nums := AN(args...)
	if len(nums) == 0 {
		return math.NaN()
	}
	m := nums[0]
	for _, n := range nums {
		if n > m {
			m = n
		}
	}
	return numValue(m)
}

// COUNT counts the numeric (not numeric-string, not boolean) arguments.
func COUNT(args ...any) any {
	c := 0.0
	for _, v := range A(args...) {
		if isNumber(v) {
			c++
		}
	}
	return numValue(c)
}

// COUNTA counts non-null, non-empty-string arguments (booleans count).
func COUNTA(args ...any) any {
	c := 0.0
	for _, v := range A(args...) {
		if v == nil {
			continue
		}
		if s, ok := v.(string); ok && s == "" {
			continue
		}
		c++
	}
	return numValue(c)
}

// argAt returns the arg at index i, or nil when absent — lets variadic
// math functions take an optional precision/significance argument.
func argAt(args []any, i int) any {
	if i < len(args) {
		return args[i]
	}
	return nil
}

// ROUND rounds value to the optional precision (default 0), half away from zero.
func ROUND(args ...any) any {
	n := N(argAt(args, 0))
	p := int(N(argAt(args, 1)))
	factor := math.Pow(10, float64(p))
	return numValue(roundHalfAwayFromZero(n*factor) / factor)
}

// ROUNDUP rounds value away from zero to the optional precision (default 0).
func ROUNDUP(args ...any) any {
	n := N(argAt(args, 0))
	p := int(N(argAt(args, 1)))
	factor := math.Pow(10, float64(p))
	if n >= 0 {
		return numValue(math.Ceil(n*factor) / factor)
	}
	return numValue(math.Floor(n*factor) / factor)
}

// ROUNDDOWN rounds value toward zero to the optional precision (default 0).
func ROUNDDOWN(args ...any) any {
	n := N(argAt(args, 0))
	p := int(N(argAt(args, 1)))
	factor := math.Pow(10, float64(p))
	if n >= 0 {
		return numValue(math.Floor(n*factor) / factor)
	}
	return numValue(math.Ceil(n*factor) / factor)
}

// CEILING rounds value up to the nearest multiple of the optional significance
// (default 1).
func CEILING(args ...any) any {
	n := N(argAt(args, 0))
	sig := 1.0
	if len(args) > 1 {
		sig = N(args[1])
	}
	if sig == 0 {
		sig = 1
	}
	return numValue(math.Ceil(n/sig) * sig)
}

// FLOOR rounds value down to the nearest multiple of the optional significance
// (default 1).
func FLOOR(args ...any) any {
	n := N(argAt(args, 0))
	sig := 1.0
	if len(args) > 1 {
		sig = N(args[1])
	}
	if sig == 0 {
		sig = 1
	}
	return numValue(math.Floor(n/sig) * sig)
}

// LOG returns log base 10, or log base `base` when a second arg is supplied.
func LOG(args ...any) any {
	n := N(argAt(args, 0))
	if len(args) > 1 {
		return numValue(math.Log(n) / math.Log(N(args[1])))
	}
	return numValue(math.Log10(n))
}

// EVEN rounds away from zero to the next even integer.
func EVEN(value any) any {
	n := N(value)
	c := math.Ceil(math.Abs(n))
	r := c
	if math.Mod(c, 2) != 0 {
		r = c + 1
	}
	if n < 0 {
		r = -r
	}
	return numValue(r)
}

// ODD rounds away from zero to the next odd integer.
func ODD(value any) any {
	n := N(value)
	c := math.Ceil(math.Abs(n))
	r := c
	if math.Mod(c, 2) != 1 {
		r = c + 1
	}
	if n < 0 {
		r = -r
	}
	return numValue(r)
}

// VALUE parses a string to a number; non-numeric input yields NaN, nil yields 0.
func VALUE(value any) any {
	if value == nil {
		return numValue(0)
	}
	s := S(value)
	if f, err := strconv.ParseFloat(strings.TrimSpace(s), 64); err == nil {
		return numValue(f)
	}
	return math.NaN()
}

// POWER raises base to exp.
func POWER(base, exp any) any { return numValue(math.Pow(N(base), N(exp))) }

// MOD returns value modulo divisor (NaN when divisor is 0).
func MOD(value, divisor any) any {
	d := N(divisor)
	if d == 0 {
		return math.NaN()
	}
	return numValue(math.Mod(N(value), d))
}

// ABS returns the absolute value.
func ABS(value any) any { return numValue(math.Abs(N(value))) }

// EXP returns e^value. EXP(1.0) is pinned to math.E so it matches V8/Airtable
// (whose Math.E differs from a naive math.Exp(1.0) by one ULP on some
// platforms).
func EXP(value any) any {
	n := N(value)
	if n == 1.0 {
		return numValue(math.E)
	}
	return numValue(math.Exp(n))
}

// SQRT returns the square root.
func SQRT(value any) any { return numValue(math.Sqrt(N(value))) }

// INT truncates toward negative infinity (floor).
func INT(value any) any { return numValue(math.Floor(N(value))) }

// =============================================================================
// String functions
// =============================================================================

// LEN returns the code-point length of the string coercion.
func LEN(value any) any { return numValue(float64(cpLength(S(value)))) }

// LEFT returns the first count code points.
func LEFT(text, count any) any {
	r := []rune(S(text))
	n := int(N(count))
	if n < 0 {
		n = 0
	}
	if n > len(r) {
		n = len(r)
	}
	return string(r[:n])
}

// RIGHT returns the last count code points.
func RIGHT(text, count any) any {
	r := []rune(S(text))
	n := int(N(count))
	if n < 0 {
		n = 0
	}
	if n > len(r) {
		n = len(r)
	}
	return string(r[len(r)-n:])
}

// MID returns count code points starting at 1-based start.
func MID(text, start, count any) any {
	r := []rune(S(text))
	startIdx := int(N(start)) - 1
	if startIdx < 0 {
		startIdx = 0
	}
	length := int(N(count))
	if length < 0 {
		length = 0
	}
	if startIdx >= len(r) {
		return ""
	}
	end := startIdx + length
	if end > len(r) {
		end = len(r)
	}
	return string(r[startIdx:end])
}

// findFrom is the shared core for FIND/SEARCH: returns the 1-based code-point
// position of needle in haystack starting at the 1-based start offset (default
// 1), or 0 when absent.
func findFrom(needle, haystack string, start any) any {
	hayRunes := []rune(haystack)
	offset := 0
	if start != nil {
		offset = int(N(start)) - 1
		if offset < 0 {
			offset = 0
		}
	}
	if offset >= len(hayRunes) {
		return numValue(0)
	}
	sub := string(hayRunes[offset:])
	idx := strings.Index(sub, needle)
	if idx < 0 {
		return numValue(0)
	}
	// idx is a byte offset into sub; convert to code points.
	cp := len([]rune(sub[:idx]))
	return numValue(float64(offset + cp + 1))
}

// FIND returns the 1-based position of needle in haystack (case-sensitive),
// optionally starting at a 1-based offset; 0 if not found.
func FIND(args ...any) any {
	needle := S(argAt(args, 0))
	haystack := S(argAt(args, 1))
	return findFrom(needle, haystack, argAt(args, 2))
}

// SEARCH is FIND but case-insensitive.
func SEARCH(args ...any) any {
	needle := strings.ToLower(S(argAt(args, 0)))
	haystack := strings.ToLower(S(argAt(args, 1)))
	return findFrom(needle, haystack, argAt(args, 2))
}

// SUBSTITUTE replaces old with new in text. With an occurrence index, only that
// Nth occurrence is replaced; otherwise all. An empty old returns text verbatim.
func SUBSTITUTE(args ...any) any {
	s := S(argAt(args, 0))
	o := S(argAt(args, 1))
	n := S(argAt(args, 2))
	if o == "" {
		return s
	}
	if len(args) < 4 || args[3] == nil {
		return strings.ReplaceAll(s, o, n)
	}
	target := int(N(args[3]))
	current := 1
	searchFrom := 0
	for {
		idx := strings.Index(s[searchFrom:], o)
		if idx < 0 {
			break
		}
		idx += searchFrom
		if current == target {
			return s[:idx] + n + s[idx+len(o):]
		}
		current++
		searchFrom = idx + 1
	}
	return s
}

// REPLACE replaces `count` code points starting at 1-based `start` with
// replacement.
func REPLACE(text, start, count, replacement any) any {
	r := []rune(S(text))
	startIdx := int(N(start)) - 1
	if startIdx < 0 {
		startIdx = 0
	}
	length := int(N(count))
	if length < 0 {
		length = 0
	}
	rep := S(replacement)
	if startIdx > len(r) {
		return string(r) + rep
	}
	end := startIdx + length
	if end > len(r) {
		end = len(r)
	}
	return string(r[:startIdx]) + rep + string(r[end:])
}

// LOWER lowercases the string coercion.
func LOWER(value any) any { return strings.ToLower(S(value)) }

// UPPER uppercases the string coercion.
func UPPER(value any) any { return strings.ToUpper(S(value)) }

// TRIM strips leading/trailing whitespace.
func TRIM(value any) any { return strings.TrimSpace(S(value)) }

// REPT repeats text count times.
func REPT(text, count any) any {
	n := int(N(count))
	if n < 0 {
		n = 0
	}
	return strings.Repeat(S(text), n)
}

// CONCATENATE joins the string coercions of all arguments.
func CONCATENATE(args ...any) any {
	var out strings.Builder
	for _, a := range args {
		out.WriteString(S(a))
	}
	return out.String()
}

// ENCODE_URL_COMPONENT percent-encodes the value like encodeURIComponent.
func ENCODE_URL_COMPONENT(value any) any {
	s := S(value)
	// url.QueryEscape encodes spaces as '+' and over-encodes some chars; emulate
	// JS encodeURIComponent: unreserved set A-Za-z0-9 -_.!~*'() stay literal.
	encoded := url.QueryEscape(s)
	encoded = strings.ReplaceAll(encoded, "+", "%20")
	// Un-escape the JS-unreserved characters QueryEscape encodes.
	replacer := strings.NewReplacer(
		"%21", "!",
		"%27", "'",
		"%28", "(",
		"%29", ")",
		"%2A", "*",
		"%7E", "~",
	)
	return replacer.Replace(encoded)
}

// T returns the value if it is a string, else the empty string.
func T(value any) any {
	if s, ok := value.(string); ok {
		return s
	}
	return ""
}

// =============================================================================
// Date/time functions
// =============================================================================

// isoFormat renders an instant as Airtable's ISO 8601 form: millis + Z.
func isoFormat(d time.Time) string {
	return d.UTC().Format("2006-01-02T15:04:05.000Z")
}

// dCoerce wraps D but distinguishes "no date" via the zero time.
func dCoerce(value any) (time.Time, bool) {
	switch v := value.(type) {
	case nil:
		return time.Time{}, false
	case string:
		if v == "" {
			return time.Time{}, false
		}
		t := D(v)
		if t.IsZero() {
			return time.Time{}, false
		}
		return t, true
	case float64:
		return time.UnixMilli(int64(v * 1000)).UTC(), true
	case int:
		return time.UnixMilli(int64(v) * 1000).UTC(), true
	case int64:
		return time.UnixMilli(v * 1000).UTC(), true
	case []any:
		if len(v) == 0 {
			return time.Time{}, false
		}
		return dCoerce(v[0])
	default:
		t := D(value)
		if t.IsZero() {
			return time.Time{}, false
		}
		return t, true
	}
}

func isWorkingDay(d time.Time) bool {
	wd := d.Weekday()
	return wd != time.Saturday && wd != time.Sunday
}

// NOW returns the current instant as an ISO string.
func NOW() any { return isoFormat(time.Now()) }

// TODAY returns midnight of the current local day as an ISO string.
func TODAY() any {
	now := time.Now()
	y, m, d := now.Date()
	return isoFormat(time.Date(y, m, d, 0, 0, 0, 0, now.Location()))
}

// YEAR returns the UTC year, or 0 for a non-date.
func YEAR(value any) any {
	d, ok := dCoerce(value)
	if !ok {
		return numValue(0)
	}
	return numValue(float64(d.UTC().Year()))
}

// MONTH returns the UTC month (1-12), or 0 for a non-date.
func MONTH(value any) any {
	d, ok := dCoerce(value)
	if !ok {
		return numValue(0)
	}
	return numValue(float64(int(d.UTC().Month())))
}

// DAY returns the UTC day of month, or 0 for a non-date.
func DAY(value any) any {
	d, ok := dCoerce(value)
	if !ok {
		return numValue(0)
	}
	return numValue(float64(d.UTC().Day()))
}

// HOUR returns the UTC hour, or 0 for a non-date.
func HOUR(value any) any {
	d, ok := dCoerce(value)
	if !ok {
		return numValue(0)
	}
	return numValue(float64(d.UTC().Hour()))
}

// MINUTE returns the UTC minute, or 0 for a non-date.
func MINUTE(value any) any {
	d, ok := dCoerce(value)
	if !ok {
		return numValue(0)
	}
	return numValue(float64(d.UTC().Minute()))
}

// SECOND returns the UTC second, or 0 for a non-date.
func SECOND(value any) any {
	d, ok := dCoerce(value)
	if !ok {
		return numValue(0)
	}
	return numValue(float64(d.UTC().Second()))
}

// WEEKDAY returns the day of week with Sunday=0 ... Saturday=6.
func WEEKDAY(value any) any {
	d, ok := dCoerce(value)
	if !ok {
		return numValue(0)
	}
	return numValue(float64(int(d.UTC().Weekday())))
}

// datetimeDiff is the shared core: (d1 - d2) in the given unit, as a float.
func datetimeDiff(d1v, d2v, unit any) (float64, bool) {
	d1, ok1 := dCoerce(d1v)
	if !ok1 {
		return 0, false
	}
	d2, ok2 := dCoerce(d2v)
	if !ok2 {
		return 0, false
	}
	diffSecs := float64(d1.UnixMilli()-d2.UnixMilli()) / 1000.0
	switch strings.ToLower(S(unit)) {
	case "milliseconds":
		return diffSecs * 1000, true
	case "seconds":
		return diffSecs, true
	case "minutes":
		return diffSecs / 60, true
	case "hours":
		return diffSecs / 3600, true
	case "weeks":
		return diffSecs / (86400.0 * 7), true
	case "months":
		z1, z2 := d1.UTC(), d2.UTC()
		return float64((z1.Year()-z2.Year())*12 + (int(z1.Month()) - int(z2.Month()))), true
	case "years":
		return float64(d1.UTC().Year() - d2.UTC().Year()), true
	default: // "days" and unknown
		return diffSecs / 86400, true
	}
}

// DATETIME_DIFF returns the integer difference d1-d2 in the optional unit
// (default "days").
func DATETIME_DIFF(args ...any) any {
	v, ok := datetimeDiff(argAt(args, 0), argAt(args, 1), argAt(args, 2))
	if !ok {
		return numValue(0)
	}
	return numValue(math.Trunc(v))
}

// DATEADD adds count of the given unit to a date, returning an ISO string.
func DATEADD(date, count, unit any) any {
	d, ok := dCoerce(date)
	if !ok {
		return nil
	}
	n := int(N(count))
	z := d.UTC()
	var result time.Time
	switch strings.ToLower(S(unit)) {
	case "years":
		result = z.AddDate(n, 0, 0)
	case "months":
		result = addMonthsClamped(z, n)
	case "weeks":
		result = z.AddDate(0, 0, 7*n)
	case "hours":
		result = z.Add(time.Duration(n) * time.Hour)
	case "minutes":
		result = z.Add(time.Duration(n) * time.Minute)
	case "seconds":
		result = z.Add(time.Duration(n) * time.Second)
	default: // "days" and unknown
		result = z.AddDate(0, 0, n)
	}
	return isoFormat(result)
}

// addMonthsClamped adds n months, clamping the day to the last day of the
// resulting month (Jan 31 + 1mo -> Feb 28/29) rather than Go's default rollover.
func addMonthsClamped(t time.Time, n int) time.Time {
	y, m, d := t.Date()
	totalMonths := int(m) - 1 + n
	newYear := y + totalMonths/12
	newMonth := totalMonths % 12
	if newMonth < 0 {
		newMonth += 12
		newYear--
	}
	targetMonth := time.Month(newMonth + 1)
	// last day of target month
	lastDay := time.Date(newYear, targetMonth+1, 0, 0, 0, 0, 0, time.UTC).Day()
	if d > lastDay {
		d = lastDay
	}
	return time.Date(newYear, targetMonth, d, t.Hour(), t.Minute(), t.Second(), t.Nanosecond(), time.UTC)
}

// IS_SAME reports whether two dates are equal within the optional unit (days).
func IS_SAME(args ...any) any {
	unit := argAt(args, 2)
	if unit == nil {
		unit = "days"
	}
	v, ok := datetimeDiff(argAt(args, 0), argAt(args, 1), unit)
	if !ok {
		return false
	}
	return math.Trunc(v) == 0
}

// IS_BEFORE reports whether d1 is before d2 within the optional unit (days).
func IS_BEFORE(args ...any) any {
	unit := argAt(args, 2)
	if unit == nil {
		unit = "days"
	}
	v, ok := datetimeDiff(argAt(args, 0), argAt(args, 1), unit)
	if !ok {
		return false
	}
	return math.Trunc(v) < 0
}

// IS_AFTER reports whether d1 is after d2 within the optional unit (days).
func IS_AFTER(args ...any) any {
	unit := argAt(args, 2)
	if unit == nil {
		unit = "days"
	}
	v, ok := datetimeDiff(argAt(args, 0), argAt(args, 1), unit)
	if !ok {
		return false
	}
	return math.Trunc(v) > 0
}

func plural(n int64, unit string) string {
	s := strconv.FormatInt(n, 10) + " " + unit
	if n != 1 {
		s += "s"
	}
	return s
}

// humanDuration is the human-friendly duration string between two dates.
func humanDuration(d1v, d2v any) string {
	d1, ok1 := dCoerce(d1v)
	if !ok1 {
		return ""
	}
	d2, ok2 := dCoerce(d2v)
	if !ok2 {
		return ""
	}
	diff := int64(math.Abs(float64(d1.UnixMilli()-d2.UnixMilli()) / 1000.0))
	minutes := diff / 60
	hours := minutes / 60
	days := hours / 24
	z1, z2 := d1.UTC(), d2.UTC()
	months := int64(math.Abs(float64((z1.Year()-z2.Year())*12 + (int(z1.Month()) - int(z2.Month())))))
	years := months / 12
	switch {
	case years > 0:
		return plural(years, "year")
	case months > 0:
		return plural(months, "month")
	case days > 0:
		return plural(days, "day")
	case hours > 0:
		return plural(hours, "hour")
	case minutes > 0:
		return plural(minutes, "minute")
	default:
		return plural(diff, "second")
	}
}

// TONOW returns the diff from now to date in unit, or a human duration.
func TONOW(args ...any) any {
	date := argAt(args, 0)
	if len(args) > 1 && args[1] != nil {
		return DATETIME_DIFF(NOW(), date, args[1])
	}
	return humanDuration(date, NOW())
}

// FROMNOW returns the diff from date to now in unit, or a human duration.
func FROMNOW(args ...any) any {
	date := argAt(args, 0)
	if len(args) > 1 && args[1] != nil {
		return DATETIME_DIFF(date, NOW(), args[1])
	}
	return humanDuration(date, NOW())
}

var weeknumStartDays = map[string]time.Weekday{
	"sunday":    time.Sunday,
	"monday":    time.Monday,
	"tuesday":   time.Tuesday,
	"wednesday": time.Wednesday,
	"thursday":  time.Thursday,
	"friday":    time.Friday,
	"saturday":  time.Saturday,
}

// WEEKNUM returns the week of the year (week starts on the optional start day,
// default Sunday; minimal-days-in-first-week = 1).
func WEEKNUM(args ...any) any {
	d, ok := dCoerce(argAt(args, 0))
	if !ok {
		return numValue(0)
	}
	first, found := weeknumStartDays[strings.ToLower(S(argAt(args, 1)))]
	if !found {
		first = time.Sunday
	}
	t := d.UTC()
	// Week 1 contains Jan 1 (minimal days = 1). Find the start-of-week on/before
	// Jan 1, then count weeks to the start-of-week on/before t.
	jan1 := time.Date(t.Year(), 1, 1, 0, 0, 0, 0, time.UTC)
	weekStart := func(x time.Time) time.Time {
		delta := (int(x.Weekday()) - int(first) + 7) % 7
		return x.AddDate(0, 0, -delta)
	}
	firstWeekStart := weekStart(jan1)
	curWeekStart := weekStart(t)
	days := int(curWeekStart.Sub(firstWeekStart).Hours() / 24)
	return numValue(float64(days/7 + 1))
}

// WORKDAY advances start by numDays working days (Mon-Fri), returning an ISO
// string.
func WORKDAY(start, numDays any) any {
	d, ok := dCoerce(start)
	if !ok {
		return nil
	}
	z := d.UTC()
	remaining := int(N(numDays))
	direction := 1
	if remaining < 0 {
		direction = -1
		remaining = -remaining
	}
	for remaining > 0 {
		z = z.AddDate(0, 0, direction)
		if isWorkingDay(z) {
			remaining--
		}
	}
	return isoFormat(z)
}

// WORKDAY_DIFF counts working days (Mon-Fri) between two dates, inclusive of the
// start day, signed (start later -> negative).
func WORKDAY_DIFF(start, end any) any {
	d1, ok1 := dCoerce(start)
	if !ok1 {
		return numValue(0)
	}
	d2, ok2 := dCoerce(end)
	if !ok2 {
		return numValue(0)
	}
	count := 0
	current := d1.UTC()
	direction := 1
	if !d2.After(d1) {
		direction = -1
	}
	if isWorkingDay(current) {
		count += direction
	}
	for (direction == 1 && current.Before(d2)) || (direction == -1 && current.After(d2)) {
		current = current.AddDate(0, 0, direction)
		if isWorkingDay(current) {
			count += direction
		}
	}
	return numValue(float64(count))
}

// SET_TIMEZONE reinterprets a datetime's wall clock in another timezone,
// returning the shifted instant as an ISO string.
func SET_TIMEZONE(date, tz any) any {
	d, ok := dCoerce(date)
	if !ok {
		return nil
	}
	loc, err := time.LoadLocation(S(tz))
	if err != nil {
		return isoFormat(d)
	}
	_, offset := d.In(loc).Zone()
	return isoFormat(d.Add(time.Duration(offset) * time.Second))
}

// momentToGo maps a Moment.js / Airtable format pattern to Go's reference-time
// layout. Longest tokens first so e.g. YYYY is consumed before YY.
func momentToGo(pattern string) string {
	type tok struct{ from, to string }
	toks := []tok{
		{"YYYY", "2006"},
		{"YY", "06"},
		{"MMMM", "January"},
		{"MMM", "Jan"},
		{"MM", "01"},
		{"DD", "02"},
		{"dddd", "Monday"},
		{"ddd", "Mon"},
		{"HH", "15"},
		{"hh", "03"},
		{"mm", "04"},
		{"ss", "05"},
		{"SSS", "000"},
		{"A", "PM"},
		{"a", "pm"},
		{"ZZ", "-0700"},
		{"Z", "-07:00"},
	}
	// Replace via a placeholder pass to avoid re-matching produced output.
	var out strings.Builder
	i := 0
	for i < len(pattern) {
		matched := false
		for _, t := range toks {
			if strings.HasPrefix(pattern[i:], t.from) {
				out.WriteString(t.to)
				i += len(t.from)
				matched = true
				break
			}
		}
		if !matched {
			out.WriteByte(pattern[i])
			i++
		}
	}
	return out.String()
}

// DATETIME_FORMAT formats a date with the optional Moment.js-style pattern
// (default ISO).
func DATETIME_FORMAT(args ...any) any {
	d, ok := dCoerce(argAt(args, 0))
	if !ok {
		return ""
	}
	if len(args) < 2 || args[1] == nil {
		return isoFormat(d)
	}
	layout := momentToGo(S(args[1]))
	return d.UTC().Format(layout)
}

// DATESTR returns the UTC date portion (yyyy-MM-dd).
func DATESTR(value any) any {
	d, ok := dCoerce(value)
	if !ok {
		return ""
	}
	return d.UTC().Format("2006-01-02")
}

// TIMESTR returns the UTC time portion (HH:mm:ss).
func TIMESTR(value any) any {
	d, ok := dCoerce(value)
	if !ok {
		return ""
	}
	return d.UTC().Format("15:04:05")
}

// DATETIME_PARSE parses a value to an ISO string (the input-format override is
// ignored — ISO 8601 then a few fallbacks are tried via D()).
func DATETIME_PARSE(args ...any) any {
	d, ok := dCoerce(argAt(args, 0))
	if !ok {
		return nil
	}
	return isoFormat(d)
}

// =============================================================================
// Array functions
// =============================================================================

// ARRAYJOIN joins array elements with the optional separator (default ", ").
func ARRAYJOIN(args ...any) any {
	arr := argAt(args, 0)
	sep := ", "
	if len(args) > 1 && args[1] != nil {
		sep = S(args[1])
	}
	if arr == nil {
		return ""
	}
	if items, ok := arr.([]any); ok {
		parts := make([]string, len(items))
		for i, v := range items {
			parts[i] = S(v)
		}
		return strings.Join(parts, sep)
	}
	return S(arr)
}

// jsonEqual compares two native values for ARRAYUNIQUE de-duplication. It
// matches JSON value equality (numbers compared numerically).
func jsonEqual(a, b any) bool {
	if isNumber(a) && isNumber(b) {
		return N(a) == N(b)
	}
	return a == b
}

// ARRAYUNIQUE returns the distinct elements, preserving first-seen order.
func ARRAYUNIQUE(arr any) any {
	out := []any{}
	if arr == nil {
		return out
	}
	items, ok := arr.([]any)
	if !ok {
		return []any{arr}
	}
	for _, v := range items {
		seen := false
		for _, s := range out {
			if jsonEqual(s, v) {
				seen = true
				break
			}
		}
		if !seen {
			out = append(out, v)
		}
	}
	return out
}

// ARRAYCOMPACT removes nulls and empty strings (keeping 0, false).
func ARRAYCOMPACT(arr any) any {
	out := []any{}
	if arr == nil {
		return out
	}
	items, ok := arr.([]any)
	if !ok {
		return []any{arr}
	}
	for _, v := range items {
		if v == nil {
			continue
		}
		if s, isStr := v.(string); isStr && s == "" {
			continue
		}
		out = append(out, v)
	}
	return out
}

// ARRAYFLATTEN recursively flattens nested arrays into a single level.
func ARRAYFLATTEN(arr any) any {
	out := []any{}
	if arr == nil {
		return out
	}
	items, ok := arr.([]any)
	if !ok {
		return []any{arr}
	}
	var flatten func(xs []any)
	flatten = func(xs []any) {
		for _, x := range xs {
			if nested, isArr := x.([]any); isArr {
				flatten(nested)
			} else {
				out = append(out, x)
			}
		}
	}
	flatten(items)
	return out
}

// =============================================================================
// Regex functions
// =============================================================================

// REGEX_EXTRACT returns the first match of pattern in text, or nil if none.
func REGEX_EXTRACT(text, pattern any) any {
	re, err := regexp.Compile(S(pattern))
	if err != nil {
		return nil
	}
	loc := re.FindStringIndex(S(text))
	if loc == nil {
		return nil
	}
	return S(text)[loc[0]:loc[1]]
}

// REGEX_MATCH reports whether pattern matches anywhere in text.
func REGEX_MATCH(text, pattern any) any {
	re, err := regexp.Compile(S(pattern))
	if err != nil {
		return false
	}
	return re.MatchString(S(text))
}

// REGEX_REPLACE replaces all matches of pattern in text with replacement.
func REGEX_REPLACE(text, pattern, replacement any) any {
	s := S(text)
	re, err := regexp.Compile(S(pattern))
	if err != nil {
		return s
	}
	return re.ReplaceAllString(s, S(replacement))
}

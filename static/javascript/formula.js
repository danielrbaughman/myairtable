const { BooleanSchema, NumberSchema, StringSchema, validateRecordIds } = require("./special-types");

// region LOGIC
/** AND(arg1, arg2, ...) */
function AND(...args) {
	const nonEmptyArgs = args.filter((arg) => arg !== "");
	return `AND(${nonEmptyArgs.join(",")})`;
}

/** OR(arg1, arg2, ...) */
function OR(...args) {
	const nonEmptyArgs = args.filter((arg) => arg !== "");
	return `OR(${nonEmptyArgs.join(",")})`;
}

/** XOR(arg1, arg2, ...) */
function XOR(...args) {
	const nonEmptyArgs = args.filter((arg) => arg !== "");
	return `XOR(${nonEmptyArgs.join(",")})`;
}

/** NOT(arg) */
function NOT(...args) {
	const nonEmptyArgs = args.filter((arg) => arg !== "");
	return `NOT(${nonEmptyArgs.join(",")})`;
}
// endregion

// region HELPERS
const FALSE = "FALSE()";
const TRUE = "TRUE()";
const BLANK = "BLANK()";
const RECORD_ID = "RECORD_ID()";
const NOW = "NOW()";

/** Check if a value is already a formula expression (contains function call syntax) */
function isFormula(value) {
	return typeof value === "string" && /^[A-Z_]+\(/.test(value);
}

/** Wrap a value for use in a formula - quotes strings, passes through formulas and fields */
function wrapValue(value) {
	if (value instanceof Field) {
		return value.field;
	} else if (isFormula(value)) {
		return value;
	} else {
		return `"${value}"`;
	}
}

function LOWER(value) {
	return `LOWER(${wrapValue(value)})`;
}
function FIND(left, right) {
	return `FIND(${wrapValue(left)}, ${wrapValue(right)})`;
}
function TRIM(value) {
	return `TRIM(${wrapValue(value)})`;
}
function LEN(value) {
	return `LEN(${wrapValue(value)})`;
}
function REGEX(value, pattern) {
	return `REGEX(${wrapValue(value)}, "${pattern}")`;
}
function DATETIME_PARSE(value) {
	if (value instanceof Field) {
		return `DATETIME_PARSE(${value.field})`;
	} else if (isFormula(value)) {
		return `DATETIME_PARSE(${value})`;
	} else {
		return `DATETIME_PARSE('${value}')`;
	}
}
function DATETIME_DIFF(left, right, unit) {
	const leftVal = left instanceof Field ? left.field : isFormula(left) ? left : `'${left}'`;
	const rightVal = right instanceof Field ? right.field : isFormula(right) ? right : `'${right}'`;
	return `DATETIME_DIFF(${leftVal}, ${rightVal}, '${unit}')`;
}
function SUBSTITUTE(value, oldText, newText) {
	return `SUBSTITUTE(${wrapValue(value)}, "${oldText}", "${newText}")`;
}

/** Record ID formulas */
class ID {
	/** RECORD_ID()='id' */
	equals(id) {
		validateRecordIds(id);
		return `${RECORD_ID}='${id}'`;
	}

	inList(ids) {
		validateRecordIds(ids);
		if (ids.length === 0) {
			return FALSE;
		} else if (ids.length === 1) {
			return this.equals(ids[0]);
		} else {
			return OR(...ids.map((id) => this.equals(id)));
		}
	}
}

/** Base class for all Airtable field types */
class Field {
	constructor(name) {
		this.nameOrId = name.replace(/[{}]/g, "").replace(/[\n\t\r]/g, "");
	}

	/** {field}=BLANK() */
	empty() {
		return `${this.field}=${BLANK}`;
	}

	/** {field} */
	notEmpty() {
		return this.field;
	}

	get field() {
		return `{${this.nameOrId}}`;
	}
}
// endregion

// region TEXT
/** String comparison formulas */
class TextField extends Field {
	/**
	 * Generates a formula string to compare the field value for equality with the specified value.
	 *
	 * @param value - The value to compare against.
	 * @param caseSensitive - Whether the comparison should be case-sensitive. Defaults to `true`.
	 * @param trim - Whether to trim whitespace from both values before comparison. Defaults to `false`.
	 */
	equals(value, caseSensitive = true, trim = false) {
		StringSchema.parse(value);
		const escapedValue = value.replace(/"/g, '\\"');

		if (caseSensitive) {
			if (trim) {
				const left = TRIM(this);
				const right = TRIM(escapedValue);
				return `${left}=${right}`;
			} else {
				return `${this.field}="${escapedValue}"`;
			}
		} else {
			if (trim) {
				const left = TRIM(LOWER(this));
				const right = TRIM(LOWER(escapedValue));
				return `${left}=${right}`;
			} else {
				const left = LOWER(this);
				const right = LOWER(escapedValue);
				return `${left}=${right}`;
			}
		}
	}

	phoneEquals(value) {
		StringSchema.parse(value);
		function normalize(s) {
			let f = TRIM(s);
			f = SUBSTITUTE(f, " ", "");
			f = SUBSTITUTE(f, "-", "");
			f = SUBSTITUTE(f, "(", "");
			f = SUBSTITUTE(f, ")", "");
			f = SUBSTITUTE(f, "+", "");
			f = SUBSTITUTE(f, ".", "");
			return f;
		}

		const left = normalize(this.field);
		const right = normalize(value);
		return `${left}=${right}`;
	}

	/** {field}!="value" */
	notEquals(value) {
		StringSchema.parse(value);
		const escapedValue = value.replace(/"/g, '\\"');
		return `${this.field}!="${escapedValue}"`;
	}

	_find(value, comparison, caseSensitive = false, trim = true) {
		StringSchema.parse(value);
		if (caseSensitive) {
			if (trim) {
				const left = TRIM(value);
				const right = TRIM(this);
				return FIND(left, right) + comparison;
			} else {
				return FIND(value, this.field) + comparison;
			}
		} else {
			if (trim) {
				const left = TRIM(LOWER(value));
				const right = TRIM(LOWER(this));
				return FIND(left, right) + comparison;
			} else {
				const left = LOWER(value);
				const right = LOWER(this);
				return FIND(left, right) + comparison;
			}
		}
	}

	/**
	 * Checks if field contains a substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 */
	contains(value, caseSensitive = false, trim = true) {
		return this._find(value, ">0", caseSensitive, trim);
	}

	/**
	 * Checks if the field contains any of the specified values.
	 *
	 * @param values - Array of string values to search for
	 * @param caseSensitive - Whether the search should be case sensitive. Defaults to false
	 * @param trim - Whether to trim whitespace from values before comparison. Defaults to true
	 */
	containsAny(values, caseSensitive = false, trim = true) {
		return OR(...values.map((value) => this.contains(value, caseSensitive, trim)));
	}

	/**
	 * Checks if the field contains all of the specified values.
	 *
	 * @param values - Array of string values to check for in the field
	 * @param caseSensitive - Whether the search should be case sensitive. Defaults to false
	 * @param trim - Whether to trim whitespace from values before comparison. Defaults to true
	 */
	containsAll(values, caseSensitive = false, trim = true) {
		return AND(...values.map((value) => this.contains(value, caseSensitive, trim)));
	}

	/**
	 * Checks if field does not contain a substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 */
	notContains(value, caseSensitive = false, trim = true) {
		return NOT(this.contains(value, caseSensitive, trim));
	}

	/**
	 * Checks if the field value starts with the specified substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 */
	startsWith(value, caseSensitive = false, trim = true) {
		return this._find(value, "=1", caseSensitive, trim);
	}

	/**
	 * Checks if the field value does not start with the specified substring
	 * @param value - The substring to check at the start of the field value
	 * @param caseSensitive - Whether the comparison should be case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace from the field value before checking (default: true)
	 */
	notStartsWith(value, caseSensitive = false, trim = true) {
		return this._find(value, "!=1", caseSensitive, trim);
	}

	_endsWith(value, comparison, caseSensitive = false, trim = true) {
		StringSchema.parse(value);
		if (caseSensitive) {
			if (trim) {
				const f = TRIM(this);
				const v = TRIM(value);
				const left = FIND(v, f);
				const right = `${LEN(f)} - ${LEN(v)} + 1`;
				return `${left} ${comparison} ${right}`;
			} else {
				const f = this.field;
				const v = value;
				const left = FIND(v, f);
				const right = `${LEN(f)} - ${LEN(v)} + 1`;
				return `${left} ${comparison} ${right}`;
			}
		} else {
			if (trim) {
				const f = TRIM(LOWER(this));
				const v = TRIM(LOWER(value));
				const left = FIND(v, f);
				const right = `${LEN(f)} - ${LEN(v)} + 1`;
				return `${left} ${comparison} ${right}`;
			} else {
				const f = LOWER(this);
				const v = LOWER(value);
				const left = FIND(v, f);
				const right = `${LEN(f)} - ${LEN(v)} + 1`;
				return `${left} ${comparison} ${right}`;
			}
		}
	}

	/**
	 * Checks if the target string ends with the specified substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 */
	endsWith(value, caseSensitive = false, trim = true) {
		return this._endsWith(value, "=", caseSensitive, trim);
	}

	/**
	 * Checks if the field value does not end with the specified substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 */
	notEndsWith(value, caseSensitive = false, trim = true) {
		return this._endsWith(value, "!=", caseSensitive, trim);
	}

	/**
	 * Tests field against a regular expression pattern
	 * @param pattern - The regex pattern to match
	 */
	regexMatch(pattern) {
		StringSchema.parse(pattern);
		return REGEX(this, pattern);
	}
}

/** Select comparison formulas */
class SingleSelectField extends TextField {
	/** {field}= "value" */
	equals(value, caseSensitive = true, trim = false) {
		return super.equals(value, caseSensitive, trim);
	}

	/** {field}!="value" */
	notEquals(value) {
		return super.notEquals(value);
	}
}

/** Multi-Select comparison formulas */
class MultiSelectField extends SingleSelectField {
	/** WARNING: May return false positives if the option you're searching for is a substring of another option. */
	containsOption(value, caseSensitive = true, trim = false) {
		return this.contains(value, caseSensitive, trim);
	}

	/** WARNING: May return false positives if the option you're searching for is a substring of another option. */
	containsAllOptions(values, caseSensitive = true, trim = false) {
		return this.containsAll(values, caseSensitive, trim);
	}

	/** WARNING: May return false positives if the option you're searching for is a substring of another option. */
	containsAnyOptions(values, caseSensitive = true, trim = false) {
		return this.containsAny(values, caseSensitive, trim);
	}

	/** WARNING: May return false positives if the option you're searching for is a substring of another option. */
	notContainsOption(value, caseSensitive = true, trim = false) {
		return this.notContains(value, caseSensitive, trim);
	}

	/** WARNING: May return false positives if the option you're searching for is a substring of another option. */
	notContainsOptions(values, caseSensitive = true, trim = false) {
		return AND(...values.map((value) => this.notContains(value, caseSensitive, trim)));
	}
}

// region NUMBER
/** Number comparison formulas */
class NumberField extends Field {
	_compare(comparison, value) {
		NumberSchema.parse(value);
		return `${this.field}${comparison}${value}`;
	}

	/** {field}=value */
	equals(value) {
		return this._compare("=", value);
	}

	/** {field}!=value */
	notEquals(value) {
		return this._compare("!=", value);
	}

	/** {field}>value */
	greaterThan(value) {
		return this._compare(">", value);
	}

	/** {field}<value */
	lessThan(value) {
		return this._compare("<", value);
	}

	/** {field}>=value */
	greaterThanOrEquals(value) {
		return this._compare(">=", value);
	}

	/** {field}<=value */
	lessThanOrEquals(value) {
		return this._compare("<=", value);
	}

	/** AND({field}>=min_value, {field}<=max_value) */
	between(minValue, maxValue, inclusive = true) {
		if (inclusive) {
			return AND(this.greaterThanOrEquals(minValue), this.lessThanOrEquals(maxValue));
		} else {
			return AND(this.greaterThan(minValue), this.lessThan(maxValue));
		}
	}
}
// endregion

// region BOOLEAN
/** Boolean comparison formulas */
class BooleanField extends Field {
	/** {field}=TRUE()|FALSE() */
	equals(value) {
		BooleanSchema.parse(value);
		return `${this.field}=${value ? TRUE : FALSE}`;
	}

	/** {field}=TRUE() */
	true() {
		return this.equals(true);
	}

	/** {field}=FALSE() */
	false() {
		return this.equals(false);
	}
}
// endregion

// region ATTACHMENTS
/** Attachment comparison formulas */
class AttachmentsField extends Field {
	/** LEN({field})>0 */
	notEmpty() {
		return LEN(this) + ">0";
	}

	/** LEN({field})=0 */
	empty() {
		return LEN(this) + "=0";
	}

	/** LEN({field})=count */
	count(count) {
		return LEN(this) + `=${count}`;
	}
}
// endregion

// region DATE
function parseDate(date) {
	if (date instanceof Date) {
		return date;
	}
	const parsed = new Date(date);
	if (isNaN(parsed.getTime())) {
		throw new Error(`Could not parse date: ${date}`);
	}
	return parsed;
}

class DateComparison extends Field {
	constructor(name, compare) {
		super(name);
		this.compare = compare;
	}

	_date(date) {
		const isoString = parseDate(date).toISOString();
		return `${DATETIME_PARSE(isoString)}${this.compare}${DATETIME_PARSE(this)}`;
	}

	_ago(unit, value) {
		return DATETIME_DIFF(NOW, this, unit) + this.compare + value;
	}

	/** Compare to time ago in milliseconds */
	millisecondsAgo(milliseconds) {
		return this._ago("milliseconds", milliseconds);
	}

	/** Compare to time ago in seconds */
	secondsAgo(seconds) {
		return this._ago("seconds", seconds);
	}

	/** Compare to time ago in minutes */
	minutesAgo(minutes) {
		return this._ago("minutes", minutes);
	}

	/** Compare to time ago in hours */
	hoursAgo(hours) {
		return this._ago("hours", hours);
	}

	/** Compare to time ago in days */
	daysAgo(days) {
		return this._ago("days", days);
	}

	/** Compare to time ago in weeks */
	weeksAgo(weeks) {
		return this._ago("weeks", weeks);
	}

	/** Compare to time ago in months */
	monthsAgo(months) {
		return this._ago("months", months);
	}

	/** Compare to time ago in quarters */
	quartersAgo(quarters) {
		return this._ago("quarters", quarters);
	}

	/** Compare to time ago in years */
	yearsAgo(years) {
		return this._ago("years", years);
	}
}

/** DateTime comparison formulas */
class DateField extends Field {
	/**
	 * Checks if the object's date matches the specified date.
	 *
	 * @param date - The date to compare against. Can be a `Date` object or a date string. If omitted, returns a `DateComparison` instance.
	 */
	on(date) {
		const dateComparison = new DateComparison(this.nameOrId, "=");
		if (date === undefined) {
			return dateComparison;
		}
		const parsedDate = parseDate(date);
		return dateComparison._date(parsedDate);
	}

	/**
	 * Checks if the date associated with this instance is on or after the specified date.
	 *
	 * @param date - The date to compare against, as a `Date` object or ISO string. Optional.
	 */
	onOrAfter(date) {
		const dateComparison = new DateComparison(this.nameOrId, ">=");
		if (date === undefined) {
			return dateComparison;
		}
		const parsedDate = parseDate(date);
		return dateComparison._date(parsedDate);
	}

	/**
	 * Checks if the date associated with this instance is on or before the specified date.
	 *
	 * @param date - The date to compare against, as a `Date` object or ISO string. Optional.
	 */
	onOrBefore(date) {
		const dateComparison = new DateComparison(this.nameOrId, "<=");
		if (date === undefined) {
			return dateComparison;
		}
		const parsedDate = parseDate(date);
		return dateComparison._date(parsedDate);
	}

	/**
	 * Checks if the date associated with this instance is after the specified date.
	 *
	 * @param date - The date to compare against, as a `Date` object or ISO string. Optional.
	 */
	after(date) {
		const dateComparison = new DateComparison(this.nameOrId, "<");
		if (date === undefined) {
			return dateComparison;
		}
		const parsedDate = parseDate(date);
		return dateComparison._date(parsedDate);
	}

	/**
	 * Checks if the date associated with this instance is before the specified date.
	 * If no date is provided, returns a `DateComparison` object for further chaining.
	 * If a date is provided, parses the date and returns the comparison as a string formula.
	 *
	 * @param date - The date to compare against, as a `Date` object or ISO string. Optional.
	 */
	before(date) {
		const dateComparison = new DateComparison(this.nameOrId, ">");
		if (date === undefined) {
			return dateComparison;
		}
		const parsedDate = parseDate(date);
		return dateComparison._date(parsedDate);
	}

	/**
	 * Checks if the field's date is not equal to the specified date.
	 *
	 * @param date - The date to compare against, as a `Date` object or a string. If omitted, returns a generic "not equal" comparison.
	 */
	notOn(date) {
		const dateComparison = new DateComparison(this.nameOrId, "!=");
		if (date === undefined) {
			return dateComparison;
		}
		const parsedDate = parseDate(date);
		return dateComparison._date(parsedDate);
	}

	/**
	 * Checks if the date is between two specified dates.
	 *
	 * @param startDate - The start date of the range. Can be a Date object or string.
	 * @param endDate - The end date of the range. Can be a Date object or string.
	 * @param inclusive - Whether to include the start and end dates in the range. Defaults to true.
	 */
	between(startDate, endDate, inclusive = true) {
		const startParsed = parseDate(startDate);
		const endParsed = parseDate(endDate);
		if (inclusive) {
			return AND(this.onOrAfter(startParsed), this.onOrBefore(endParsed));
		} else {
			return AND(this.after(startParsed), this.before(endParsed));
		}
	}
}
// endregion

module.exports = {
	AND,
	OR,
	XOR,
	NOT,
	ID,
	Field,
	TextField,
	SingleSelectField,
	MultiSelectField,
	NumberField,
	BooleanField,
	AttachmentsField,
	DateField,
};

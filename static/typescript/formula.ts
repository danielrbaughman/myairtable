/* eslint-disable no-unused-vars */
type Comparison = "=" | "!=" | ">" | "<" | ">=" | "<=";

// region LOGIC
/** AND(arg1, arg2, ...) */
export function AND(...args: string[]): string {
	const nonEmptyArgs = args.filter((arg) => arg !== "");
	return `AND(${nonEmptyArgs.join(",")})`;
}

/** OR(arg1, arg2, ...) */
export function OR(...args: string[]): string {
	const nonEmptyArgs = args.filter((arg) => arg !== "");
	return `OR(${nonEmptyArgs.join(",")})`;
}

/** XOR(arg1, arg2, ...) */
export function XOR(...args: string[]): string {
	const nonEmptyArgs = args.filter((arg) => arg !== "");
	return `XOR(${nonEmptyArgs.join(",")})`;
}

/** NOT(arg) */
export function NOT(...args: string[]): string {
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

function LOWER(value: string | Field): string {
	if (value instanceof Field) {
		return `LOWER(${value.field})`;
	} else {
		return `LOWER("${value}")`;
	}
}
function FIND(left: string | Field, right: string): string {
	if (left instanceof Field) {
		return `FIND(${left.field}, ${right})`;
	} else {
		return `FIND("${left}", ${right})`;
	}
}
function TRIM(value: string | Field): string {
	if (value instanceof Field) {
		return `TRIM(${value.field})`;
	} else {
		return `TRIM("${value}")`;
	}
}
function LEN(value: string | Field): string {
	if (value instanceof Field) {
		return `LEN(${value.field})`;
	} else {
		return `LEN("${value}")`;
	}
}
function REGEX(value: string | Field, pattern: string): string {
	if (value instanceof Field) {
		return `REGEX(${value.field}, "${pattern}")`;
	} else {
		return `REGEX("${value}", "${pattern}")`;
	}
}
function DATETIME_PARSE(value: string | Field): string {
	if (value instanceof Field) {
		return `DATETIME_PARSE(${value.field})`;
	} else {
		return `DATETIME_PARSE('${value}')`;
	}
}
function DATETIME_DIFF(left: string | Field, right: string | Field, unit: string): string {
	if (left instanceof Field && right instanceof Field) {
		return `DATETIME_DIFF(${left.field}, ${right.field}, '${unit}')`;
	} else if (left instanceof Field) {
		return `DATETIME_DIFF(${left.field}, ${right}, '${unit}')`;
	} else if (right instanceof Field) {
		return `DATETIME_DIFF(${left}, ${right.field}, '${unit}')`;
	} else {
		return `DATETIME_DIFF('${left}', '${right}', '${unit}')`;
	}
}
function SUBSTITUTE(value: string | Field, oldText: string, newText: string): string {
	if (value instanceof Field) {
		return `SUBSTITUTE(${value.field}, "${oldText}", "${newText}")`;
	} else {
		return `SUBSTITUTE("${value}", "${oldText}", "${newText}")`;
	}
}

/** Record ID formulas */
export class ID {
	/** RECORD_ID()='id' */
	equals(id: string): string {
		return `${RECORD_ID}='${id}'`;
	}

	inList(ids: string[]): string {
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
export class Field {
	protected readonly nameOrId: string;

	constructor(name: string) {
		this.nameOrId = name.replace(/[{}]/g, "").replace(/[\n\t\r]/g, "");
	}

	/** {field}=BLANK() */
	empty(): string {
		return `${this.field}=${BLANK}`;
	}

	/** {field} */
	notEmpty(): string {
		return this.field;
	}

	get field(): string {
		return `${this.nameOrId}`;
	}
}
// endregion

// region TEXT
/** String comparison formulas */
export class TextField extends Field {
	/**
	 * Generates a formula string to compare the field value for equality with the specified value.
	 *
	 * @param value - The value to compare against.
	 * @param caseSensitive - Whether the comparison should be case-sensitive. Defaults to `true`.
	 * @param trim - Whether to trim whitespace from both values before comparison. Defaults to `false`.
	 */
	equals(value: string, caseSensitive: boolean = true, trim: boolean = false): string {
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

	phoneEquals(value: string): string {
		function normalize(s: string): string {
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

	/** {field}!="value\" */
	notEquals(value: string): string {
		return `${this.field}!="${value}"`;
	}

	private _find(value: string, comparison: string, caseSensitive: boolean = false, trim: boolean = true): string {
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
	contains(value: string, caseSensitive: boolean = false, trim: boolean = true): string {
		return this._find(value, ">0", caseSensitive, trim);
	}

	/**
	 * Checks if the field contains any of the specified values.
	 *
	 * @param values - Array of string values to search for
	 * @param caseSensitive - Whether the search should be case sensitive. Defaults to false
	 * @param trim - Whether to trim whitespace from values before comparison. Defaults to true
	 */
	containsAny(values: string[], caseSensitive: boolean = false, trim: boolean = true): string {
		return OR(...values.map((value) => this.contains(value, caseSensitive, trim)));
	}

	/**
	 * Checks if the field contains all of the specified values.
	 *
	 * @param values - Array of string values to check for in the field
	 * @param caseSensitive - Whether the search should be case sensitive. Defaults to false
	 * @param trim - Whether to trim whitespace from values before comparison. Defaults to true
	 */
	containsAll(values: string[], caseSensitive: boolean = false, trim: boolean = true): string {
		return AND(...values.map((value) => this.contains(value, caseSensitive, trim)));
	}

	/**
	 * Checks if field does not contain a substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 */
	notContains(value: string, caseSensitive: boolean = false, trim: boolean = true): string {
		return this._find(value, "=0", caseSensitive, trim);
	}

	/**
	 * Checks if the field value starts with the specified substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 */
	startsWith(value: string, caseSensitive: boolean = false, trim: boolean = true): string {
		return this._find(value, "=1", caseSensitive, trim);
	}

	/**
	 * Checks if the field value does not start with the specified substring
	 * @param value - The substring to check at the start of the field value
	 * @param caseSensitive - Whether the comparison should be case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace from the field value before checking (default: true)
	 */
	notStartsWith(value: string, caseSensitive: boolean = false, trim: boolean = true): string {
		return this._find(value, "!=1", caseSensitive, trim);
	}

	private _endsWith(value: string, comparison: string, caseSensitive: boolean = false, trim: boolean = true): string {
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
	endsWith(value: string, caseSensitive: boolean = false, trim: boolean = true): string {
		return this._endsWith(value, "=", caseSensitive, trim);
	}

	/**
	 * Checks if the field value does not end with the specified substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 */
	notEndsWith(value: string, caseSensitive: boolean = false, trim: boolean = true): string {
		return this._endsWith(value, "!=", caseSensitive, trim);
	}

	/**
	 * Tests field against a regular expression pattern
	 * @param pattern - The regex pattern to match
	 */
	regexMatch(pattern: string): string {
		return REGEX(this, pattern);
	}
}

// region NUMBER
/** Number comparison formulas */
export class NumberField extends Field {
	private _compare(comparison: Comparison, value: number): string {
		return `${this.field}${comparison}${value}`;
	}

	/** {field}=value */
	equals(value: number): string {
		return this._compare("=", value);
	}

	/** {field}!=value */
	notEquals(value: number): string {
		return this._compare("!=", value);
	}

	/** {field}>value */
	greaterThan(value: number): string {
		return this._compare(">", value);
	}

	/** {field}<value */
	lessThan(value: number): string {
		return this._compare("<", value);
	}

	/** {field}>=value */
	greaterThanOrEquals(value: number): string {
		return this._compare(">=", value);
	}

	/** {field}<=value */
	lessThanOrEquals(value: number): string {
		return this._compare("<=", value);
	}

	/** AND({field}>=min_value, {field}<=max_value) */
	between(minValue: number, maxValue: number, inclusive: boolean = true): string {
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
export class BooleanField extends Field {
	/** {field}=TRUE()|FALSE() */
	equals(value: boolean): string {
		return `${this.field}=${value ? TRUE : FALSE}`;
	}

	/** {field}=TRUE() */
	true(): string {
		return this.equals(true);
	}

	/** {field}=FALSE() */
	false(): string {
		return this.equals(false);
	}
}
// endregion

// region ATTACHMENTS
/** Attachment comparison formulas */
export class AttachmentsField extends Field {
	/** LEN({field})>0 */
	override notEmpty(): string {
		return LEN(this) + ">0";
	}

	/** LEN({field})=0 */
	override empty(): string {
		return LEN(this) + "=0";
	}

	/** LEN({field})=count */
	count(count: number): string {
		return LEN(this) + `=${count}`;
	}
}
// endregion

// region DATE
function parseDate(date: Date | string): Date {
	if (date instanceof Date) {
		return date;
	}
	const parsed = new Date(date);
	if (isNaN(parsed.getTime())) {
		throw new Error(`Could not parse date: ${date}`);
	}
	return parsed;
}

type DateUnit = "milliseconds" | "seconds" | "minutes" | "hours" | "days" | "weeks" | "months" | "quarters" | "years";

class DateComparison extends Field {
	constructor(
		name: string,
		private compare: Comparison,
	) {
		super(name);
	}

	_date(date: Date | string): string {
		const isoString = parseDate(date).toISOString();
		return `${DATETIME_PARSE(isoString)}${this.compare}${DATETIME_PARSE(this)}`;
	}

	private _ago(unit: DateUnit, value: number): string {
		return DATETIME_DIFF(NOW, this, unit) + this.compare + value;
	}

	/** Compare to time ago in milliseconds */
	millisecondsAgo(milliseconds: number): string {
		return this._ago("milliseconds", milliseconds);
	}

	/** Compare to time ago in seconds */
	secondsAgo(seconds: number): string {
		return this._ago("seconds", seconds);
	}

	/** Compare to time ago in minutes */
	minutesAgo(minutes: number): string {
		return this._ago("minutes", minutes);
	}

	/** Compare to time ago in hours */
	hoursAgo(hours: number): string {
		return this._ago("hours", hours);
	}

	/** Compare to time ago in days */
	daysAgo(days: number): string {
		return this._ago("days", days);
	}

	/** Compare to time ago in weeks */
	weeksAgo(weeks: number): string {
		return this._ago("weeks", weeks);
	}

	/** Compare to time ago in months */
	monthsAgo(months: number): string {
		return this._ago("months", months);
	}

	/** Compare to time ago in quarters */
	quartersAgo(quarters: number): string {
		return this._ago("quarters", quarters);
	}

	/** Compare to time ago in years */
	yearsAgo(years: number): string {
		return this._ago("years", years);
	}
}

/** DateTime comparison formulas */
export class DateField extends Field {
	/**
	 * Checks if the object's date matches the specified date.
	 *
	 * @param date - The date to compare against. Can be a `Date` object or a date string. If omitted, returns a `DateComparison` instance.
	 */
	on(): DateComparison;
	on(date: Date | string): string;
	on(date?: Date | string): DateComparison | string {
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
	onOrAfter(): DateComparison;
	onOrAfter(date: Date | string): string;
	onOrAfter(date?: Date | string): DateComparison | string {
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
	onOrBefore(): DateComparison;
	onOrBefore(date: Date | string): string;
	onOrBefore(date?: Date | string): DateComparison | string {
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
	after(): DateComparison;
	after(date: Date | string): string;
	after(date?: Date | string): DateComparison | string {
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
	before(): DateComparison;
	before(date: Date | string): string;
	before(date?: Date | string): DateComparison | string {
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
	notOn(): DateComparison;
	notOn(date: Date | string): string;
	notOn(date?: Date | string): DateComparison | string {
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
	between(startDate: Date | string, endDate: Date | string, inclusive: boolean = true): string {
		const startParsed = parseDate(startDate);
		const endParsed = parseDate(endDate);
		if (inclusive) {
			return AND(this.onOrAfter(startParsed) as string, this.onOrBefore(endParsed) as string);
		} else {
			return AND(this.after(startParsed) as string, this.before(endParsed) as string);
		}
	}
}
// endregion

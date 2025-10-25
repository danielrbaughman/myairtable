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

/** IF(condition, valueIfTrue, valueIfFalse) */
export function IF(condition: string): Then {
	return new Then(condition);
}

class Then {
	constructor(protected condition: string) {}

	THEN(valueIfTrue: string, isString: boolean = false): Else {
		return new Else(this.condition, valueIfTrue, isString);
	}
}

class Else extends Then {
	constructor(
		condition: string,
		protected trueValue: string,
		protected isTrueString: boolean = false,
	) {
		super(condition);
	}

	ELSE(valueIfFalse: string, isString: boolean = false): string {
		const trueVal = this.isTrueString ? `"${this.trueValue}"` : this.trueValue;
		const falseVal = isString ? `"${valueIfFalse}"` : valueIfFalse;
		return `IF(${this.condition}, ${trueVal}, ${falseVal})`;
	}
}
// endregion

// region HELPERS
/** RECORD_ID()='id' */
export function idEquals(id: string): string {
	return `RECORD_ID()='${id}'`;
}

export function idInList(ids: string[]): string {
	if (ids.length === 0) {
		return "FALSE()";
	} else if (ids.length === 1) {
		return idEquals(ids[0]);
	} else {
		return OR(...ids.map((id) => idEquals(id)));
	}
}

/** Base class for all Airtable field types */
export class Field {
	public readonly name: string;
	public readonly id: string;

	constructor(name: string, nameToIdMap: Record<string, string> = {}) {
		if (!name) {
			throw new Error("Field name cannot be empty.");
		}
		this.id = nameToIdMap[name] || name;
		// Clean field name - remove braces, newlines, tabs, carriage returns
		this.name = name.replace(/[{}]/g, "").replace(/[\n\t\r]/g, "");
	}

	/** {field}=BLANK() */
	isEmpty(): string {
		return `{${this.id}}=BLANK()`;
	}

	/** {field} */
	isNotEmpty(): string {
		return `{${this.id}}`;
	}
}
// endregion

// region TEXT
/** String comparison formulas */
export class TextField extends Field {
	/** {field}="value\" */
	equals(value: string): string {
		const escapedValue = value.replace(/"/g, '\\"');
		return `{${this.id}}="${escapedValue}"`;
	}

	/** {field}!="value\" */
	notEquals(value: string): string {
		return `{${this.id}}!="${value}"`;
	}

	private _find(value: string, comparison: string, caseSensitive: boolean = false, trim: boolean = true): string {
		if (caseSensitive) {
			if (trim) {
				return `FIND(TRIM("${value}"), TRIM({${this.id}}))${comparison}`;
			} else {
				return `FIND("${value}", {${this.id}})${comparison}`;
			}
		} else {
			if (trim) {
				return `FIND(TRIM(LOWER("${value}")), TRIM(LOWER({${this.id}})))${comparison}`;
			} else {
				return `FIND(LOWER("${value}"), LOWER({${this.id}}))${comparison}`;
			}
		}
	}

	/**
	 * Checks if field contains a substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 * @returns Formula string
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
	 * @returns A formula string that evaluates to true if any of the values are found in the field
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
	 * @returns A formula string that evaluates to true if all values are found in the field
	 */
	containsAll(values: string[], caseSensitive: boolean = false, trim: boolean = true): string {
		return AND(...values.map((value) => this.contains(value, caseSensitive, trim)));
	}

	/**
	 * Checks if field does not contain a substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 * @returns Formula string
	 */
	notContains(value: string, caseSensitive: boolean = false, trim: boolean = true): string {
		return this._find(value, "=0", caseSensitive, trim);
	}

	/**
	 * Checks if the field value starts with the specified substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 * @returns Formula string
	 */
	startsWith(value: string, caseSensitive: boolean = false, trim: boolean = true): string {
		return this._find(value, "=1", caseSensitive, trim);
	}

	/**
	 * Checks if the field value does not start with the specified substring
	 * @param value - The substring to check at the start of the field value
	 * @param caseSensitive - Whether the comparison should be case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace from the field value before checking (default: true)
	 * @returns Formula string
	 */
	notStartsWith(value: string, caseSensitive: boolean = false, trim: boolean = true): string {
		return this._find(value, "!=1", caseSensitive, trim);
	}

	private _endsWith(value: string, comparison: string, caseSensitive: boolean = false, trim: boolean = true): string {
		if (caseSensitive) {
			if (trim) {
				return `FIND(TRIM("${value}"), TRIM({${this.id}})) ${comparison} LEN(TRIM({${this.id}})) - LEN(TRIM("${value}")) + 1`;
			} else {
				return `FIND("${value}", {${this.id}}) ${comparison} LEN({${this.id}}) - LEN("${value}") + 1`;
			}
		} else {
			if (trim) {
				return `FIND(TRIM(LOWER("${value}")), TRIM(LOWER({${this.id}}))) ${comparison} LEN(TRIM(LOWER({${this.id}}))) - LEN(TRIM(LOWER("${value}"))) + 1`;
			} else {
				return `FIND(LOWER("${value}"), LOWER({${this.id}})) ${comparison} LEN(LOWER({${this.id}})) - LEN(LOWER("${value}")) + 1`;
			}
		}
	}

	/**
	 * Checks if the target string ends with the specified substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 * @returns Formula string
	 */
	endsWith(value: string, caseSensitive: boolean = false, trim: boolean = true): string {
		return this._endsWith(value, "=", caseSensitive, trim);
	}

	/**
	 * Checks if the field value does not end with the specified substring
	 * @param value - The substring to search for
	 * @param caseSensitive - Whether search is case-sensitive (default: false)
	 * @param trim - Whether to trim whitespace (default: true)
	 * @returns Formula string
	 */
	notEndsWith(value: string, caseSensitive: boolean = false, trim: boolean = true): string {
		return this._endsWith(value, "!=", caseSensitive, trim);
	}

	/**
	 * Tests field against a regular expression pattern
	 * @param pattern - The regex pattern to match
	 * @returns Formula string
	 */
	regexMatch(pattern: string): string {
		return `REGEX_MATCH({${this.id}}, "${pattern}")`;
	}
}

// region NUMBER
/** Number comparison formulas */
export class NumberField extends Field {
	private _compare(comparison: Comparison, value: number): string {
		return `{${this.id}}${comparison}${value}`;
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
}
// endregion

// region BOOLEAN
/** Boolean comparison formulas */
export class BooleanField extends Field {
	/** {field}=TRUE()|FALSE() */
	equals(value: boolean): string {
		return `{${this.id}}=${value ? "TRUE()" : "FALSE()"}`;
	}

	/** {field}=TRUE() */
	isTrue(): string {
		return `{${this.id}}=TRUE()`;
	}

	/** {field}=FALSE() */
	isFalse(): string {
		return `{${this.id}}=FALSE()`;
	}
}
// endregion

// region ATTACHMENTS
/** Attachment comparison formulas */
export class AttachmentsField extends Field {
	/** LEN({field})>0 */
	override isNotEmpty(): string {
		return `LEN({${this.id}})>0`;
	}

	/** LEN({field})=0 */
	override isEmpty(): string {
		return `LEN({${this.id}})=0`;
	}

	/** LEN({field})=count */
	countIs(count: number): string {
		return `LEN({${this.id}})=${count}`;
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

class DateComparison extends Field {
	constructor(
		name: string,
		private compare: Comparison,
	) {
		super(name);
	}

	_date(date: Date | string): string {
		const parsedDate = parseDate(date);
		return `DATETIME_PARSE('${parsedDate.toISOString()}')${this.compare}DATETIME_PARSE({${this.id}})`;
	}

	private _ago(unit: string, value: number): string {
		return `DATETIME_DIFF(NOW(), {${this.id}}, '${unit}')${this.compare}${value}`;
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
	 * @returns A `DateComparison` instance if no date is provided, or a string formula if a date is specified.
	 */
	isOn(): DateComparison;
	isOn(date: Date | string): string;
	isOn(date?: Date | string): DateComparison | string {
		const dateComparison = new DateComparison(this.id, "=");
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
	 * @returns A `DateComparison` instance if no date is provided, or a string formula if a date is given.
	 */
	isOnOrAfter(): DateComparison;
	isOnOrAfter(date: Date | string): string;
	isOnOrAfter(date?: Date | string): DateComparison | string {
		const dateComparison = new DateComparison(this.id, ">=");
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
	 * @returns A `DateComparison` instance if no date is provided, or a string formula if a date is given.
	 */
	isOnOrBefore(): DateComparison;
	isOnOrBefore(date: Date | string): string;
	isOnOrBefore(date?: Date | string): DateComparison | string {
		const dateComparison = new DateComparison(this.id, "<=");
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
	 * @returns A `DateComparison` instance for further chaining, or a string representing the comparison formula.
	 */
	isAfter(): DateComparison;
	isAfter(date: Date | string): string;
	isAfter(date?: Date | string): DateComparison | string {
		const dateComparison = new DateComparison(this.id, "<");
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
	 * @returns A `DateComparison` instance if no date is provided, or a string formula if a date is given.
	 */
	isBefore(): DateComparison;
	isBefore(date: Date | string): string;
	isBefore(date?: Date | string): DateComparison | string {
		const dateComparison = new DateComparison(this.id, ">");
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
	 * @returns A `DateComparison` instance representing the "not equal" comparison, or a string if applicable.
	 */
	isNotOn(): DateComparison;
	isNotOn(date: Date | string): string;
	isNotOn(date?: Date | string): DateComparison | string {
		const dateComparison = new DateComparison(this.id, "!=");
		if (date === undefined) {
			return dateComparison;
		}
		const parsedDate = parseDate(date);
		return dateComparison._date(parsedDate);
	}
}
// endregion

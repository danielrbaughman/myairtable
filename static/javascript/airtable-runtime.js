/**
 * AirtableRuntime: Implements Airtable formula functions and operators in JavaScript.
 *
 * All operators route through this class for correct Airtable semantics:
 * - BLANK() is null (treated as 0 in numeric context, "" in string context)
 * - Division by zero returns NaN
 * - Type coercion follows Airtable rules, not JavaScript rules
 */

class AirtableRuntime {
	// region Utilities
	/** Check if value is null or undefined */
	static _isNull(v) {
		return v === null || v === undefined;
	}

	/** Coerce arguments to a flat array */
	static A(args) {
		const result = [];
		for (const a of args) {
			if (Array.isArray(a)) result.push(...a);
			else result.push(a);
		}
		return result;
	}

	/** Coerce arguments to a flat array of numbers */
	static AN(args) {
		return AirtableRuntime.A(args).map((v) => AirtableRuntime.N(v));
	}

	/** Coerce arguments to a flat array of strings */
	static AS(args) {
		return AirtableRuntime.A(args).map((v) => AirtableRuntime.S(v));
	}

	/** Coerce value to number */
	static N(v) {
		if (Array.isArray(v)) return AirtableRuntime.N(v[0]);
		if (AirtableRuntime._isNull(v)) return 0;
		if (typeof v === "boolean") return v ? 1 : 0;
		if (typeof v === "number") return v;
		if (typeof v === "string") {
			const n = Number(v);
			return isNaN(n) ? 0 : n;
		}
		return 0;
	}

	/** Coerce value to string */
	static S(v) {
		// Airtable coerces a multi-value field to a string by joining with ", ", not first element.
		if (Array.isArray(v)) return v.map((x) => AirtableRuntime.S(x)).join(", ");
		if (AirtableRuntime._isNull(v)) return "";
		if (typeof v === "boolean") return v ? "1" : "0";
		return String(v);
	}

	/** Coerce value to Date */
	static D(v) {
		if (Array.isArray(v)) return AirtableRuntime.D(v[0]);
		if (v instanceof Date) {
			if (isNaN(v.getTime())) throw new Error("Invalid date");
			return v;
		}
		if (typeof v === "number") {
			const d = new Date(v);
			if (isNaN(d.getTime())) throw new Error("Invalid date");
			return d;
		}
		const s = AirtableRuntime._isNull(v) ? "" : AirtableRuntime.S(v);
		const d = new Date(s);
		if (isNaN(d.getTime())) throw new Error("Invalid date");
		return d;
	}
	// endregion

	// region Numeric functions
	static SUM(...args) {
		const flat = AirtableRuntime.A(args);
		return flat.reduce((acc, v) => acc + AirtableRuntime.N(v), 0);
	}

	static AVERAGE(...args) {
		const flat = AirtableRuntime.A(args);
		if (flat.length === 0) return NaN;
		return AirtableRuntime.SUM(...flat) / flat.length;
	}

	static COUNT(...args) {
		const flat = AirtableRuntime.A(args);
		return flat.filter((v) => typeof v === "number" && !isNaN(v)).length;
	}

	static COUNTA(...args) {
		const flat = AirtableRuntime.A(args);
		return flat.filter((v) => !AirtableRuntime._isNull(v) && v !== "").length;
	}

	static ROUND(value, precision) {
		const n = AirtableRuntime.N(value);
		const p = AirtableRuntime.N(precision);
		const factor = Math.pow(10, p);
		return Math.round(n * factor) / factor;
	}

	static ROUNDUP(value, precision) {
		const n = AirtableRuntime.N(value);
		const p = AirtableRuntime.N(precision);
		const factor = Math.pow(10, p);
		return Math.ceil(n * factor) / factor;
	}

	static ROUNDDOWN(value, precision) {
		const n = AirtableRuntime.N(value);
		const p = AirtableRuntime.N(precision);
		const factor = Math.pow(10, p);
		return Math.floor(n * factor) / factor;
	}

	static CEILING(value, significance) {
		const n = AirtableRuntime.N(value);
		const s = AirtableRuntime.N(significance) || 1;
		return Math.ceil(n / s) * s;
	}

	static FLOOR(value, significance) {
		const n = AirtableRuntime.N(value);
		const s = AirtableRuntime.N(significance) || 1;
		return Math.floor(n / s) * s;
	}

	static LOG(value, base) {
		const n = AirtableRuntime.N(value);
		if (AirtableRuntime._isNull(base)) return Math.log(n) / Math.log(10);
		return Math.log(n) / Math.log(AirtableRuntime.N(base));
	}

	static EVEN(value) {
		const n = AirtableRuntime.N(value);
		const ceil = Math.ceil(Math.abs(n));
		const result = ceil % 2 === 0 ? ceil : ceil + 1;
		return n < 0 ? -result : result;
	}

	static ODD(value) {
		const n = AirtableRuntime.N(value);
		const ceil = Math.ceil(Math.abs(n));
		const result = ceil % 2 === 1 ? ceil : ceil + 1;
		return n < 0 ? -result : result;
	}

	static VALUE(value) {
		if (AirtableRuntime._isNull(value)) return 0;
		const n = Number(value);
		return isNaN(n) ? NaN : n;
	}
	// endregion

	// region String functions
	static LEFT(text, count) {
		return AirtableRuntime.S(text).slice(0, AirtableRuntime.N(count));
	}

	static RIGHT(text, count) {
		const s = AirtableRuntime.S(text);
		const n = AirtableRuntime.N(count);
		return s.slice(Math.max(0, s.length - n));
	}

	static MID(text, start, count) {
		const s = AirtableRuntime.S(text);
		const startIdx = AirtableRuntime.N(start) - 1;
		const len = AirtableRuntime.N(count);
		return s.slice(startIdx, startIdx + len);
	}

	static FIND(needle, haystack, start) {
		const s = AirtableRuntime.S(haystack);
		const n = AirtableRuntime.S(needle);
		const startIdx = AirtableRuntime._isNull(start) ? 0 : AirtableRuntime.N(start) - 1;
		const idx = s.indexOf(n, startIdx);
		return idx === -1 ? 0 : idx + 1;
	}

	static SEARCH(needle, haystack, start) {
		const s = AirtableRuntime.S(haystack).toLowerCase();
		const n = AirtableRuntime.S(needle).toLowerCase();
		const startIdx = AirtableRuntime._isNull(start) ? 0 : AirtableRuntime.N(start) - 1;
		const idx = s.indexOf(n, startIdx);
		return idx === -1 ? 0 : idx + 1;
	}

	static SUBSTITUTE(text, oldStr, newStr, index) {
		const s = AirtableRuntime.S(text);
		const o = AirtableRuntime.S(oldStr);
		const n = AirtableRuntime.S(newStr);
		if (AirtableRuntime._isNull(index)) {
			return s.split(o).join(n);
		}
		let count = 0;
		const target = AirtableRuntime.N(index);
		return s.replace(new RegExp(o.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g"), (match) => {
			count++;
			return count === target ? n : match;
		});
	}

	static REPLACE(text, start, count, replacement) {
		const s = AirtableRuntime.S(text);
		const startIdx = AirtableRuntime.N(start) - 1;
		const len = AirtableRuntime.N(count);
		return s.slice(0, startIdx) + AirtableRuntime.S(replacement) + s.slice(startIdx + len);
	}

	static T(value) {
		return typeof value === "string" ? value : "";
	}
	// endregion

	// region Date/Time functions
	static TODAY() {
		return new Date().toISOString().slice(0, 10);
	}

	static NOW() {
		return new Date().toISOString();
	}

	static DATEADD(date, count, unit) {
		if (AirtableRuntime._isNull(date)) return null;
		const d = AirtableRuntime.D(date);
		const n = AirtableRuntime.N(count);
		const u = AirtableRuntime.S(unit).toLowerCase();
		switch (u) {
			case "years":
				d.setUTCFullYear(d.getUTCFullYear() + n);
				break;
			case "months":
				d.setUTCMonth(d.getUTCMonth() + n);
				break;
			case "weeks":
				d.setUTCDate(d.getUTCDate() + n * 7);
				break;
			case "days":
				d.setUTCDate(d.getUTCDate() + n);
				break;
			case "hours":
				d.setUTCHours(d.getUTCHours() + n);
				break;
			case "minutes":
				d.setUTCMinutes(d.getUTCMinutes() + n);
				break;
			case "seconds":
				d.setUTCSeconds(d.getUTCSeconds() + n);
				break;
		}
		return d.toISOString();
	}

	static DATETIME_DIFF(date1, date2, unit) {
		if (AirtableRuntime._isNull(date1) || AirtableRuntime._isNull(date2)) return 0;
		const d1 = AirtableRuntime.D(date1);
		const d2 = AirtableRuntime.D(date2);
		const diffMs = d1.getTime() - d2.getTime();
		const u = AirtableRuntime.S(unit || "days").toLowerCase();
		switch (u) {
			case "milliseconds":
				return diffMs;
			case "seconds":
				return Math.floor(diffMs / 1000);
			case "minutes":
				return Math.floor(diffMs / 60000);
			case "hours":
				return Math.floor(diffMs / 3600000);
			case "days":
				return Math.floor(diffMs / 86400000);
			case "weeks":
				return Math.floor(diffMs / (86400000 * 7));
			case "months":
				return (d1.getUTCFullYear() - d2.getUTCFullYear()) * 12 + (d1.getUTCMonth() - d2.getUTCMonth());
			case "years":
				return d1.getUTCFullYear() - d2.getUTCFullYear();
			default:
				return Math.floor(diffMs / 86400000);
		}
	}

	static DATETIME_FORMAT(date, format) {
		if (AirtableRuntime._isNull(date)) return "";
		const d = AirtableRuntime.D(date);
		if (AirtableRuntime._isNull(format)) return d.toISOString();
		const f = AirtableRuntime.S(format);
		return f.replace(/YYYY|YY|MM|DD|HH|hh|mm|ss|A|a/g, (token) => {
			switch (token) {
				case "YYYY":
					return String(d.getUTCFullYear());
				case "YY":
					return String(d.getUTCFullYear()).slice(-2);
				case "MM":
					return String(d.getUTCMonth() + 1).padStart(2, "0");
				case "DD":
					return String(d.getUTCDate()).padStart(2, "0");
				case "HH":
					return String(d.getUTCHours()).padStart(2, "0");
				case "hh":
					return String(d.getUTCHours() % 12 || 12).padStart(2, "0");
				case "mm":
					return String(d.getUTCMinutes()).padStart(2, "0");
				case "ss":
					return String(d.getUTCSeconds()).padStart(2, "0");
				case "A":
					return d.getUTCHours() < 12 ? "AM" : "PM";
				case "a":
					return d.getUTCHours() < 12 ? "am" : "pm";
				default:
					return token;
			}
		});
	}

	static SET_TIMEZONE(date, timezone) {
		if (AirtableRuntime._isNull(date)) return null;
		const d = AirtableRuntime.D(date);
		const tz = AirtableRuntime.S(timezone);
		const parts = new Intl.DateTimeFormat("en-US", {
			timeZone: tz,
			year: "numeric",
			month: "2-digit",
			day: "2-digit",
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
			hour12: false,
		}).formatToParts(d);
		const get = (type) => parts.find((p) => p.type === type)?.value ?? "0";
		const adjusted = new Date(
			Date.UTC(
				parseInt(get("year")),
				parseInt(get("month")) - 1,
				parseInt(get("day")),
				parseInt(get("hour")),
				parseInt(get("minute")),
				parseInt(get("second")),
			),
		);
		return adjusted.toISOString();
	}

	static WEEKNUM(date, startDay) {
		if (AirtableRuntime._isNull(date)) return 0;
		const d = AirtableRuntime.D(date);
		const dayNames = { sunday: 0, monday: 1, tuesday: 2, wednesday: 3, thursday: 4, friday: 5, saturday: 6 };
		const startDow = AirtableRuntime._isNull(startDay) ? 0 : (dayNames[AirtableRuntime.S(startDay).toLowerCase()] ?? 0);
		const startOfYear = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
		const startDayOfWeek = startOfYear.getUTCDay();
		const dayOfYear = Math.floor((d.getTime() - startOfYear.getTime()) / 86400000);
		const adjusted = dayOfYear + ((startDayOfWeek - startDow + 7) % 7);
		return Math.ceil((adjusted + 1) / 7);
	}
	static DATESTR(date) {
		if (AirtableRuntime._isNull(date)) return "";
		return AirtableRuntime.D(date).toISOString().slice(0, 10);
	}
	static TIMESTR(date) {
		if (AirtableRuntime._isNull(date)) return "";
		return AirtableRuntime.D(date).toISOString().slice(11, 19);
	}
	static TONOW(date, unit) {
		if (!AirtableRuntime._isNull(unit)) return AirtableRuntime.DATETIME_DIFF(new Date().toISOString(), date, unit);
		return AirtableRuntime._humanDuration(date, new Date().toISOString());
	}
	static FROMNOW(date, unit) {
		if (!AirtableRuntime._isNull(unit)) return AirtableRuntime.DATETIME_DIFF(date, new Date().toISOString(), unit);
		return AirtableRuntime._humanDuration(date, new Date().toISOString());
	}
	static _humanDuration(date1, date2) {
		const d1 = AirtableRuntime.D(date1);
		const d2 = AirtableRuntime.D(date2);
		const diffMs = Math.abs(d1.getTime() - d2.getTime());
		const seconds = Math.floor(diffMs / 1000);
		const minutes = Math.floor(seconds / 60);
		const hours = Math.floor(minutes / 60);
		const days = Math.floor(hours / 24);
		const months = Math.abs((d1.getUTCFullYear() - d2.getUTCFullYear()) * 12 + (d1.getUTCMonth() - d2.getUTCMonth()));
		const years = Math.floor(months / 12);
		if (years > 0) return `${years} year${years !== 1 ? "s" : ""}`;
		if (months > 0) return `${months} month${months !== 1 ? "s" : ""}`;
		if (days > 0) return `${days} day${days !== 1 ? "s" : ""}`;
		if (hours > 0) return `${hours} hour${hours !== 1 ? "s" : ""}`;
		if (minutes > 0) return `${minutes} minute${minutes !== 1 ? "s" : ""}`;
		return `${seconds} second${seconds !== 1 ? "s" : ""}`;
	}
	static IS_SAME(date1, date2, unit) {
		return AirtableRuntime.DATETIME_DIFF(date1, date2, unit || "days") === 0;
	}
	static IS_BEFORE(date1, date2, unit) {
		return AirtableRuntime.DATETIME_DIFF(date1, date2, unit || "days") < 0;
	}
	static IS_AFTER(date1, date2, unit) {
		return AirtableRuntime.DATETIME_DIFF(date1, date2, unit || "days") > 0;
	}

	static WORKDAY(startDate, numDays) {
		if (AirtableRuntime._isNull(startDate)) return null;
		const d = AirtableRuntime.D(startDate);
		let remaining = AirtableRuntime.N(numDays);
		const direction = remaining > 0 ? 1 : -1;
		remaining = Math.abs(remaining);
		while (remaining > 0) {
			d.setUTCDate(d.getUTCDate() + direction);
			const dow = d.getUTCDay();
			if (dow !== 0 && dow !== 6) remaining--;
		}
		return d.toISOString();
	}

	static WORKDAY_DIFF(startDate, endDate) {
		if (AirtableRuntime._isNull(startDate) || AirtableRuntime._isNull(endDate)) return 0;
		const d1 = AirtableRuntime.D(startDate);
		const d2 = AirtableRuntime.D(endDate);
		let count = 0;
		const current = new Date(d1);
		const direction = d2 > d1 ? 1 : -1;
		const startDow = current.getUTCDay();
		if (startDow !== 0 && startDow !== 6) count += direction;
		while (direction === 1 ? current < d2 : current > d2) {
			current.setUTCDate(current.getUTCDate() + direction);
			const dow = current.getUTCDay();
			if (dow !== 0 && dow !== 6) count += direction;
		}
		return count;
	}
	// endregion

	// region Array functions
	static ARRAYJOIN(arr, separator) {
		if (!Array.isArray(arr)) return AirtableRuntime.S(arr);
		const sep = AirtableRuntime._isNull(separator) ? ", " : AirtableRuntime.S(separator);
		return arr.map((v) => AirtableRuntime.S(v)).join(sep);
	}
	static ARRAYUNIQUE(arr) {
		if (!Array.isArray(arr)) return [arr];
		return [...new Set(arr)];
	}
	static ARRAYCOMPACT(arr) {
		if (!Array.isArray(arr)) return AirtableRuntime._isNull(arr) ? [] : [arr];
		return arr.filter((v) => !AirtableRuntime._isNull(v) && v !== "");
	}
	static ARRAYFLATTEN(arr) {
		if (!Array.isArray(arr)) return [arr];
		return arr.flat(Infinity);
	}
	// endregion

	// region Record/Special
	static ERROR(message) {
		throw new Error(AirtableRuntime.S(message || "Error"));
	}
	static ISERROR(value) {
		try {
			return value instanceof Error || (typeof value === "number" && isNaN(value));
		} catch {
			return true;
		}
	}
	// endregion
}

module.exports = { AirtableRuntime };

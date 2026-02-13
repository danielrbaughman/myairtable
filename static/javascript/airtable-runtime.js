/**
 * AirtableRuntime: Implements Airtable formula functions and operators in JavaScript.
 *
 * All operators route through this class for correct Airtable semantics:
 * - BLANK() is null (treated as 0 in numeric context, "" in string context)
 * - Division by zero returns NaN
 * - Type coercion follows Airtable rules
 */

class AirtableRuntime {
	// region Utilities
	/** Check if value is null or undefined */
	static isNull(v) {
		return v === null || v === undefined;
	}

	/** Coerce value to number */
	static N(v) {
		if (Array.isArray(v)) return AirtableRuntime.N(v[0]);
		if (AirtableRuntime.isNull(v)) return 0;
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
		if (Array.isArray(v)) return AirtableRuntime.S(v[0]);
		if (AirtableRuntime.isNull(v)) return "";
		if (typeof v === "boolean") return v ? "1" : "0";
		return String(v);
	}

	static _flatArgs(args) {
		const result = [];
		for (const a of args) {
			if (Array.isArray(a)) result.push(...a);
			else result.push(a);
		}
		return result;
	}
	// endregion

	// region Numeric functions
	static SUM(...args) {
		const flat = AirtableRuntime._flatArgs(args);
		return flat.reduce((acc, v) => acc + AirtableRuntime.N(v), 0);
	}

	static AVERAGE(...args) {
		const flat = AirtableRuntime._flatArgs(args);
		if (flat.length === 0) return NaN;
		return AirtableRuntime.SUM(...flat) / flat.length;
	}

	static MIN(...args) {
		const flat = AirtableRuntime._flatArgs(args);
		if (flat.length === 0) return Infinity;
		return Math.min(...flat.map((v) => AirtableRuntime.N(v)));
	}

	static MAX(...args) {
		const flat = AirtableRuntime._flatArgs(args);
		if (flat.length === 0) return -Infinity;
		return Math.max(...flat.map((v) => AirtableRuntime.N(v)));
	}

	static COUNT(...args) {
		const flat = AirtableRuntime._flatArgs(args);
		return flat.filter((v) => typeof v === "number" && !isNaN(v)).length;
	}

	static COUNTA(...args) {
		const flat = AirtableRuntime._flatArgs(args);
		return flat.filter((v) => !AirtableRuntime.isNull(v) && v !== "").length;
	}

	static COUNTALL(...args) {
		return AirtableRuntime._flatArgs(args).length;
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
		if (AirtableRuntime.isNull(base)) return Math.log(n) / Math.log(10);
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
		if (AirtableRuntime.isNull(value)) return 0;
		const n = Number(value);
		return isNaN(n) ? NaN : n;
	}
	// endregion

	// region String functions
	static CONCATENATE(...args) {
		return args.map((a) => AirtableRuntime.S(a)).join("");
	}

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
		const startIdx = AirtableRuntime.isNull(start) ? 0 : AirtableRuntime.N(start) - 1;
		const idx = s.indexOf(n, startIdx);
		return idx === -1 ? 0 : idx + 1;
	}

	static SEARCH(needle, haystack, start) {
		const s = AirtableRuntime.S(haystack).toLowerCase();
		const n = AirtableRuntime.S(needle).toLowerCase();
		const startIdx = AirtableRuntime.isNull(start) ? 0 : AirtableRuntime.N(start) - 1;
		const idx = s.indexOf(n, startIdx);
		return idx === -1 ? 0 : idx + 1;
	}

	static SUBSTITUTE(text, oldStr, newStr, index) {
		const s = AirtableRuntime.S(text);
		const o = AirtableRuntime.S(oldStr);
		const n = AirtableRuntime.S(newStr);
		if (AirtableRuntime.isNull(index)) {
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

	static REPT(text, count) {
		return AirtableRuntime.S(text).repeat(Math.max(0, AirtableRuntime.N(count)));
	}
	static T(value) {
		return typeof value === "string" ? value : "";
	}
	static REGEX_MATCH(text, regex) {
		try {
			return new RegExp(AirtableRuntime.S(regex)).test(AirtableRuntime.S(text));
		} catch {
			return false;
		}
	}
	static REGEX_REPLACE(text, regex, replacement) {
		try {
			return AirtableRuntime.S(text).replace(new RegExp(AirtableRuntime.S(regex), "g"), AirtableRuntime.S(replacement));
		} catch {
			return AirtableRuntime.S(text);
		}
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
		if (AirtableRuntime.isNull(date)) return null;
		const d = new Date(AirtableRuntime.S(date));
		if (isNaN(d.getTime())) return null;
		const n = AirtableRuntime.N(count);
		const u = AirtableRuntime.S(unit).toLowerCase();
		switch (u) {
			case "years":
				d.setFullYear(d.getFullYear() + n);
				break;
			case "months":
				d.setMonth(d.getMonth() + n);
				break;
			case "weeks":
				d.setDate(d.getDate() + n * 7);
				break;
			case "days":
				d.setDate(d.getDate() + n);
				break;
			case "hours":
				d.setHours(d.getHours() + n);
				break;
			case "minutes":
				d.setMinutes(d.getMinutes() + n);
				break;
			case "seconds":
				d.setSeconds(d.getSeconds() + n);
				break;
		}
		return d.toISOString();
	}

	static DATETIME_DIFF(date1, date2, unit) {
		if (AirtableRuntime.isNull(date1) || AirtableRuntime.isNull(date2)) return 0;
		const d1 = new Date(AirtableRuntime.S(date1));
		const d2 = new Date(AirtableRuntime.S(date2));
		if (isNaN(d1.getTime()) || isNaN(d2.getTime())) return 0;
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
				return (d1.getFullYear() - d2.getFullYear()) * 12 + (d1.getMonth() - d2.getMonth());
			case "years":
				return d1.getFullYear() - d2.getFullYear();
			default:
				return Math.floor(diffMs / 86400000);
		}
	}

	static DATETIME_FORMAT(date, _format) {
		if (AirtableRuntime.isNull(date)) return "";
		const d = new Date(AirtableRuntime.S(date));
		return isNaN(d.getTime()) ? "" : d.toISOString();
	}

	static DATETIME_PARSE(text, _format, _locale) {
		if (AirtableRuntime.isNull(text)) return null;
		const d = new Date(AirtableRuntime.S(text));
		return isNaN(d.getTime()) ? null : d.toISOString();
	}

	static SET_LOCALE(date, _locale) {
		return date;
	}
	static SET_TIMEZONE(date, _timezone) {
		return date;
	}

	static YEAR(date) {
		if (AirtableRuntime.isNull(date)) return 0;
		const d = new Date(AirtableRuntime.S(date));
		return isNaN(d.getTime()) ? 0 : d.getFullYear();
	}
	static MONTH(date) {
		if (AirtableRuntime.isNull(date)) return 0;
		const d = new Date(AirtableRuntime.S(date));
		return isNaN(d.getTime()) ? 0 : d.getMonth() + 1;
	}
	static DAY(date) {
		if (AirtableRuntime.isNull(date)) return 0;
		const d = new Date(AirtableRuntime.S(date));
		return isNaN(d.getTime()) ? 0 : d.getDate();
	}
	static HOUR(date) {
		if (AirtableRuntime.isNull(date)) return 0;
		const d = new Date(AirtableRuntime.S(date));
		return isNaN(d.getTime()) ? 0 : d.getHours();
	}
	static MINUTE(date) {
		if (AirtableRuntime.isNull(date)) return 0;
		const d = new Date(AirtableRuntime.S(date));
		return isNaN(d.getTime()) ? 0 : d.getMinutes();
	}
	static SECOND(date) {
		if (AirtableRuntime.isNull(date)) return 0;
		const d = new Date(AirtableRuntime.S(date));
		return isNaN(d.getTime()) ? 0 : d.getSeconds();
	}
	static WEEKDAY(date) {
		if (AirtableRuntime.isNull(date)) return 0;
		const d = new Date(AirtableRuntime.S(date));
		return isNaN(d.getTime()) ? 0 : d.getDay();
	}
	static WEEKNUM(date, startDay) {
		if (AirtableRuntime.isNull(date)) return 0;
		const d = new Date(AirtableRuntime.S(date));
		if (isNaN(d.getTime())) return 0;
		const dayNames = { sunday: 0, monday: 1, tuesday: 2, wednesday: 3, thursday: 4, friday: 5, saturday: 6 };
		const startDow = AirtableRuntime.isNull(startDay) ? 0 : (dayNames[AirtableRuntime.S(startDay).toLowerCase()] ?? 0);
		const startOfYear = new Date(d.getFullYear(), 0, 1);
		const startDayOfWeek = startOfYear.getDay();
		const dayOfYear = Math.floor((d.getTime() - startOfYear.getTime()) / 86400000);
		const adjusted = dayOfYear + ((startDayOfWeek - startDow + 7) % 7);
		return Math.ceil((adjusted + 1) / 7);
	}
	static DATESTR(date) {
		if (AirtableRuntime.isNull(date)) return "";
		const d = new Date(AirtableRuntime.S(date));
		return isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10);
	}
	static TIMESTR(date) {
		if (AirtableRuntime.isNull(date)) return "";
		const d = new Date(AirtableRuntime.S(date));
		return isNaN(d.getTime()) ? "" : d.toISOString().slice(11, 19);
	}
	static TONOW(date, unit) {
		return AirtableRuntime.DATETIME_DIFF(new Date().toISOString(), date, unit || "days");
	}
	static FROMNOW(date, unit) {
		return AirtableRuntime.DATETIME_DIFF(date, new Date().toISOString(), unit || "days");
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
		if (AirtableRuntime.isNull(startDate)) return null;
		const d = new Date(AirtableRuntime.S(startDate));
		if (isNaN(d.getTime())) return null;
		let remaining = AirtableRuntime.N(numDays);
		const direction = remaining > 0 ? 1 : -1;
		remaining = Math.abs(remaining);
		while (remaining > 0) {
			d.setDate(d.getDate() + direction);
			const dow = d.getDay();
			if (dow !== 0 && dow !== 6) remaining--;
		}
		return d.toISOString();
	}

	static WORKDAY_DIFF(startDate, endDate) {
		if (AirtableRuntime.isNull(startDate) || AirtableRuntime.isNull(endDate)) return 0;
		const d1 = new Date(AirtableRuntime.S(startDate));
		const d2 = new Date(AirtableRuntime.S(endDate));
		if (isNaN(d1.getTime()) || isNaN(d2.getTime())) return 0;
		let count = 0;
		const current = new Date(d1);
		const direction = d2 > d1 ? 1 : -1;
		while (direction === 1 ? current < d2 : current > d2) {
			current.setDate(current.getDate() + direction);
			const dow = current.getDay();
			if (dow !== 0 && dow !== 6) count += direction;
		}
		return count;
	}
	// endregion

	// region Array functions
	static ARRAYJOIN(arr, separator) {
		if (!Array.isArray(arr)) return AirtableRuntime.S(arr);
		const sep = AirtableRuntime.isNull(separator) ? ", " : AirtableRuntime.S(separator);
		return arr.map((v) => AirtableRuntime.S(v)).join(sep);
	}
	static ARRAYUNIQUE(arr) {
		if (!Array.isArray(arr)) return [arr];
		return [...new Set(arr)];
	}
	static ARRAYCOMPACT(arr) {
		if (!Array.isArray(arr)) return AirtableRuntime.isNull(arr) ? [] : [arr];
		return arr.filter((v) => !AirtableRuntime.isNull(v) && v !== "");
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

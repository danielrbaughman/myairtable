/**
 * AirtableRuntime: Implements Airtable formula functions and operators in TypeScript.
 *
 * All operators route through this class for correct Airtable semantics:
 * - BLANK() is null (treated as 0 in numeric context, "" in string context)
 * - Division by zero returns NaN (Airtable shows #ERROR!)
 * - Type coercion follows Airtable rules, not JavaScript rules
 */

// eslint-disable-next-line @typescript-eslint/no-extraneous-class
export class AirtableRuntime {
	// region BLANK semantics
	private static _isBlank(v: unknown): boolean {
		return v === null || v === undefined;
	}

	static N(v: unknown): number {
		if (Array.isArray(v)) return AirtableRuntime._toNum(v[0]);
		return AirtableRuntime._toNum(v);
	}

	static S(v: unknown): string {
		if (Array.isArray(v)) return AirtableRuntime._toStr(v[0]);
		return AirtableRuntime._toStr(v);
	}

	private static _toNum(v: unknown): number {
		if (AirtableRuntime._isBlank(v)) return 0;
		if (typeof v === "boolean") return v ? 1 : 0;
		if (typeof v === "number") return v;
		if (typeof v === "string") {
			const n = Number(v);
			return isNaN(n) ? 0 : n;
		}
		return 0;
	}

	private static _toStr(v: unknown): string {
		if (AirtableRuntime._isBlank(v)) return "";
		if (typeof v === "boolean") return v ? "1" : "0";
		return String(v);
	}

	private static _flatArgs(args: unknown[]): unknown[] {
		const result: unknown[] = [];
		for (const a of args) {
			if (Array.isArray(a)) result.push(...a);
			else result.push(a);
		}
		return result;
	}
	// endregion

	// region Numeric functions
	static SUM(...args: unknown[]): number {
		const flat = AirtableRuntime._flatArgs(args);
		return flat.reduce<number>((acc, v) => acc + AirtableRuntime._toNum(v), 0);
	}

	static AVERAGE(...args: unknown[]): number {
		const flat = AirtableRuntime._flatArgs(args);
		if (flat.length === 0) return NaN;
		return AirtableRuntime.SUM(...flat) / flat.length;
	}

	static MIN(...args: unknown[]): number {
		const flat = AirtableRuntime._flatArgs(args);
		if (flat.length === 0) return Infinity;
		return Math.min(...flat.map((v) => AirtableRuntime._toNum(v)));
	}

	static MAX(...args: unknown[]): number {
		const flat = AirtableRuntime._flatArgs(args);
		if (flat.length === 0) return -Infinity;
		return Math.max(...flat.map((v) => AirtableRuntime._toNum(v)));
	}

	static COUNT(...args: unknown[]): number {
		const flat = AirtableRuntime._flatArgs(args);
		return flat.filter((v) => typeof v === "number" && !isNaN(v)).length;
	}

	static COUNTA(...args: unknown[]): number {
		const flat = AirtableRuntime._flatArgs(args);
		return flat.filter((v) => !AirtableRuntime._isBlank(v) && v !== "").length;
	}

	static COUNTALL(...args: unknown[]): number {
		const flat = AirtableRuntime._flatArgs(args);
		return flat.length;
	}

	static ROUND(value: unknown, precision?: unknown): number {
		const n = AirtableRuntime._toNum(value);
		const p = AirtableRuntime._toNum(precision);
		const factor = Math.pow(10, p);
		return Math.round(n * factor) / factor;
	}

	static ROUNDUP(value: unknown, precision?: unknown): number {
		const n = AirtableRuntime._toNum(value);
		const p = AirtableRuntime._toNum(precision);
		const factor = Math.pow(10, p);
		return Math.ceil(n * factor) / factor;
	}

	static ROUNDDOWN(value: unknown, precision?: unknown): number {
		const n = AirtableRuntime._toNum(value);
		const p = AirtableRuntime._toNum(precision);
		const factor = Math.pow(10, p);
		return Math.floor(n * factor) / factor;
	}

	static CEILING(value: unknown, significance?: unknown): number {
		const n = AirtableRuntime._toNum(value);
		const s = AirtableRuntime._toNum(significance) || 1;
		return Math.ceil(n / s) * s;
	}

	static FLOOR(value: unknown, significance?: unknown): number {
		const n = AirtableRuntime._toNum(value);
		const s = AirtableRuntime._toNum(significance) || 1;
		return Math.floor(n / s) * s;
	}

	static INT(value: unknown): number {
		return Math.floor(AirtableRuntime._toNum(value));
	}

	static ABS(value: unknown): number {
		return Math.abs(AirtableRuntime._toNum(value));
	}

	static SQRT(value: unknown): number {
		return Math.sqrt(AirtableRuntime._toNum(value));
	}

	static POWER(base: unknown, exponent: unknown): number {
		return Math.pow(AirtableRuntime._toNum(base), AirtableRuntime._toNum(exponent));
	}

	static EXP(value: unknown): number {
		return Math.exp(AirtableRuntime._toNum(value));
	}

	static LOG(value: unknown, base?: unknown): number {
		const n = AirtableRuntime._toNum(value);
		if (AirtableRuntime._isBlank(base)) return Math.log(n) / Math.log(10);
		return Math.log(n) / Math.log(AirtableRuntime._toNum(base));
	}

	static LOG10(value: unknown): number {
		return Math.log10(AirtableRuntime._toNum(value));
	}

	static MOD(value: unknown, divisor: unknown): number {
		const n = AirtableRuntime._toNum(value);
		const d = AirtableRuntime._toNum(divisor);
		if (d === 0) return NaN;
		return n % d;
	}

	static EVEN(value: unknown): number {
		const n = AirtableRuntime._toNum(value);
		const ceil = Math.ceil(Math.abs(n));
		const result = ceil % 2 === 0 ? ceil : ceil + 1;
		return n < 0 ? -result : result;
	}

	static ODD(value: unknown): number {
		const n = AirtableRuntime._toNum(value);
		const ceil = Math.ceil(Math.abs(n));
		const result = ceil % 2 === 1 ? ceil : ceil + 1;
		return n < 0 ? -result : result;
	}

	static VALUE(value: unknown): number {
		if (AirtableRuntime._isBlank(value)) return 0;
		const n = Number(value);
		return isNaN(n) ? NaN : n;
	}
	// endregion

	// region String functions
	static CONCATENATE(...args: unknown[]): string {
		return args.map((a) => AirtableRuntime._toStr(a)).join("");
	}

	static LEFT(text: unknown, count: unknown): string {
		return AirtableRuntime._toStr(text).slice(0, AirtableRuntime._toNum(count));
	}

	static RIGHT(text: unknown, count: unknown): string {
		const s = AirtableRuntime._toStr(text);
		const n = AirtableRuntime._toNum(count);
		return s.slice(Math.max(0, s.length - n));
	}

	static MID(text: unknown, start: unknown, count: unknown): string {
		const s = AirtableRuntime._toStr(text);
		const startIdx = AirtableRuntime._toNum(start) - 1; // Airtable is 1-indexed
		const len = AirtableRuntime._toNum(count);
		return s.slice(startIdx, startIdx + len);
	}

	static FIND(needle: unknown, haystack: unknown, start?: unknown): number {
		const s = AirtableRuntime._toStr(haystack);
		const n = AirtableRuntime._toStr(needle);
		const startIdx = AirtableRuntime._isBlank(start) ? 0 : AirtableRuntime._toNum(start) - 1;
		const idx = s.indexOf(n, startIdx);
		return idx === -1 ? 0 : idx + 1; // 1-indexed, 0 = not found
	}

	static SEARCH(needle: unknown, haystack: unknown, start?: unknown): number {
		const s = AirtableRuntime._toStr(haystack).toLowerCase();
		const n = AirtableRuntime._toStr(needle).toLowerCase();
		const startIdx = AirtableRuntime._isBlank(start) ? 0 : AirtableRuntime._toNum(start) - 1;
		const idx = s.indexOf(n, startIdx);
		return idx === -1 ? 0 : idx + 1;
	}

	static SUBSTITUTE(text: unknown, oldStr: unknown, newStr: unknown, index?: unknown): string {
		const s = AirtableRuntime._toStr(text);
		const o = AirtableRuntime._toStr(oldStr);
		const n = AirtableRuntime._toStr(newStr);
		if (AirtableRuntime._isBlank(index)) {
			return s.split(o).join(n);
		}
		let count = 0;
		const target = AirtableRuntime._toNum(index);
		return s.replace(new RegExp(o.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g"), (match) => {
			count++;
			return count === target ? n : match;
		});
	}

	static REPLACE(text: unknown, start: unknown, count: unknown, replacement: unknown): string {
		const s = AirtableRuntime._toStr(text);
		const startIdx = AirtableRuntime._toNum(start) - 1;
		const len = AirtableRuntime._toNum(count);
		return s.slice(0, startIdx) + AirtableRuntime._toStr(replacement) + s.slice(startIdx + len);
	}

	static LOWER(text: unknown): string {
		return AirtableRuntime._toStr(text).toLowerCase();
	}

	static UPPER(text: unknown): string {
		return AirtableRuntime._toStr(text).toUpperCase();
	}

	static TRIM(text: unknown): string {
		return AirtableRuntime._toStr(text).trim();
	}

	static REPT(text: unknown, count: unknown): string {
		return AirtableRuntime._toStr(text).repeat(Math.max(0, AirtableRuntime._toNum(count)));
	}

	static T(value: unknown): string {
		return typeof value === "string" ? value : "";
	}

	static ENCODE_URL_COMPONENT(text: unknown): string {
		return encodeURIComponent(AirtableRuntime._toStr(text));
	}

	static REGEX_MATCH(text: unknown, regex: unknown): boolean {
		try {
			return new RegExp(AirtableRuntime._toStr(regex)).test(AirtableRuntime._toStr(text));
		} catch {
			return false;
		}
	}

	static REGEX_EXTRACT(text: unknown, regex: unknown): string | null {
		try {
			const match = AirtableRuntime._toStr(text).match(new RegExp(AirtableRuntime._toStr(regex)));
			return match ? match[0] : null;
		} catch {
			return null;
		}
	}

	static REGEX_REPLACE(text: unknown, regex: unknown, replacement: unknown): string {
		try {
			return AirtableRuntime._toStr(text).replace(
				new RegExp(AirtableRuntime._toStr(regex), "g"),
				AirtableRuntime._toStr(replacement),
			);
		} catch {
			return AirtableRuntime._toStr(text);
		}
	}
	// endregion

	// region Date/Time functions
	static TODAY(): string {
		return new Date().toISOString().slice(0, 10);
	}

	static NOW(): string {
		return new Date().toISOString();
	}

	static DATEADD(date: unknown, count: unknown, unit: unknown): string | null {
		if (AirtableRuntime._isBlank(date)) return null;
		const d = new Date(AirtableRuntime._toStr(date));
		if (isNaN(d.getTime())) return null;
		const n = AirtableRuntime._toNum(count);
		const u = AirtableRuntime._toStr(unit).toLowerCase();
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

	static DATETIME_DIFF(date1: unknown, date2: unknown, unit?: unknown): number {
		if (AirtableRuntime._isBlank(date1) || AirtableRuntime._isBlank(date2)) return 0;
		const d1 = new Date(AirtableRuntime._toStr(date1));
		const d2 = new Date(AirtableRuntime._toStr(date2));
		if (isNaN(d1.getTime()) || isNaN(d2.getTime())) return 0;
		const diffMs = d1.getTime() - d2.getTime();
		const u = AirtableRuntime._toStr(unit || "days").toLowerCase();
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

	static DATETIME_FORMAT(date: unknown, _format?: unknown): string {
		if (AirtableRuntime._isBlank(date)) return "";
		const d = new Date(AirtableRuntime._toStr(date));
		if (isNaN(d.getTime())) return "";
		return d.toISOString();
	}

	static DATETIME_PARSE(text: unknown, _format?: unknown, _locale?: unknown): string | null {
		if (AirtableRuntime._isBlank(text)) return null;
		const d = new Date(AirtableRuntime._toStr(text));
		if (isNaN(d.getTime())) return null;
		return d.toISOString();
	}

	static SET_LOCALE(date: unknown, _locale: unknown): unknown {
		return date;
	}

	static SET_TIMEZONE(date: unknown, _timezone: unknown): unknown {
		return date;
	}

	static YEAR(date: unknown): number {
		if (AirtableRuntime._isBlank(date)) return 0;
		const d = new Date(AirtableRuntime._toStr(date));
		return isNaN(d.getTime()) ? 0 : d.getFullYear();
	}

	static MONTH(date: unknown): number {
		if (AirtableRuntime._isBlank(date)) return 0;
		const d = new Date(AirtableRuntime._toStr(date));
		return isNaN(d.getTime()) ? 0 : d.getMonth() + 1;
	}

	static DAY(date: unknown): number {
		if (AirtableRuntime._isBlank(date)) return 0;
		const d = new Date(AirtableRuntime._toStr(date));
		return isNaN(d.getTime()) ? 0 : d.getDate();
	}

	static HOUR(date: unknown): number {
		if (AirtableRuntime._isBlank(date)) return 0;
		const d = new Date(AirtableRuntime._toStr(date));
		return isNaN(d.getTime()) ? 0 : d.getHours();
	}

	static MINUTE(date: unknown): number {
		if (AirtableRuntime._isBlank(date)) return 0;
		const d = new Date(AirtableRuntime._toStr(date));
		return isNaN(d.getTime()) ? 0 : d.getMinutes();
	}

	static SECOND(date: unknown): number {
		if (AirtableRuntime._isBlank(date)) return 0;
		const d = new Date(AirtableRuntime._toStr(date));
		return isNaN(d.getTime()) ? 0 : d.getSeconds();
	}

	static WEEKDAY(date: unknown): number {
		if (AirtableRuntime._isBlank(date)) return 0;
		const d = new Date(AirtableRuntime._toStr(date));
		return isNaN(d.getTime()) ? 0 : d.getDay();
	}

	static WEEKNUM(date: unknown, startDay?: unknown): number {
		if (AirtableRuntime._isBlank(date)) return 0;
		const d = new Date(AirtableRuntime._toStr(date));
		if (isNaN(d.getTime())) return 0;
		const dayNames: Record<string, number> = {
			sunday: 0,
			monday: 1,
			tuesday: 2,
			wednesday: 3,
			thursday: 4,
			friday: 5,
			saturday: 6,
		};
		const startDow = AirtableRuntime._isBlank(startDay)
			? 0
			: (dayNames[AirtableRuntime._toStr(startDay).toLowerCase()] ?? 0);
		const startOfYear = new Date(d.getFullYear(), 0, 1);
		const startDayOfWeek = startOfYear.getDay();
		const dayOfYear = Math.floor((d.getTime() - startOfYear.getTime()) / 86400000);
		const adjusted = dayOfYear + ((startDayOfWeek - startDow + 7) % 7);
		return Math.ceil((adjusted + 1) / 7);
	}

	static DATESTR(date: unknown): string {
		if (AirtableRuntime._isBlank(date)) return "";
		const d = new Date(AirtableRuntime._toStr(date));
		if (isNaN(d.getTime())) return "";
		return d.toISOString().slice(0, 10);
	}

	static TIMESTR(date: unknown): string {
		if (AirtableRuntime._isBlank(date)) return "";
		const d = new Date(AirtableRuntime._toStr(date));
		if (isNaN(d.getTime())) return "";
		return d.toISOString().slice(11, 19);
	}

	static TONOW(date: unknown, unit?: unknown): number {
		return AirtableRuntime.DATETIME_DIFF(new Date().toISOString(), date, unit || "days");
	}

	static FROMNOW(date: unknown, unit?: unknown): number {
		return AirtableRuntime.DATETIME_DIFF(date, new Date().toISOString(), unit || "days");
	}

	static IS_SAME(date1: unknown, date2: unknown, unit?: unknown): boolean {
		return AirtableRuntime.DATETIME_DIFF(date1, date2, unit || "days") === 0;
	}

	static IS_BEFORE(date1: unknown, date2: unknown, unit?: unknown): boolean {
		return AirtableRuntime.DATETIME_DIFF(date1, date2, unit || "days") < 0;
	}

	static IS_AFTER(date1: unknown, date2: unknown, unit?: unknown): boolean {
		return AirtableRuntime.DATETIME_DIFF(date1, date2, unit || "days") > 0;
	}

	static WORKDAY(startDate: unknown, numDays: unknown): string | null {
		if (AirtableRuntime._isBlank(startDate)) return null;
		const d = new Date(AirtableRuntime._toStr(startDate));
		if (isNaN(d.getTime())) return null;
		let remaining = AirtableRuntime._toNum(numDays);
		const direction = remaining > 0 ? 1 : -1;
		remaining = Math.abs(remaining);
		while (remaining > 0) {
			d.setDate(d.getDate() + direction);
			const dow = d.getDay();
			if (dow !== 0 && dow !== 6) remaining--;
		}
		return d.toISOString();
	}

	static WORKDAY_DIFF(startDate: unknown, endDate: unknown): number {
		if (AirtableRuntime._isBlank(startDate) || AirtableRuntime._isBlank(endDate)) return 0;
		const d1 = new Date(AirtableRuntime._toStr(startDate));
		const d2 = new Date(AirtableRuntime._toStr(endDate));
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
	static ARRAYJOIN(arr: unknown, separator?: unknown): string {
		if (!Array.isArray(arr)) return AirtableRuntime._toStr(arr);
		const sep = AirtableRuntime._isBlank(separator) ? ", " : AirtableRuntime._toStr(separator);
		return arr.map((v) => AirtableRuntime._toStr(v)).join(sep);
	}

	static ARRAYUNIQUE(arr: unknown): unknown[] {
		if (!Array.isArray(arr)) return [arr];
		return [...new Set(arr)];
	}

	static ARRAYCOMPACT(arr: unknown): unknown[] {
		if (!Array.isArray(arr)) return AirtableRuntime._isBlank(arr) ? [] : [arr];
		return arr.filter((v) => !AirtableRuntime._isBlank(v) && v !== "");
	}

	static ARRAYFLATTEN(arr: unknown): unknown[] {
		if (!Array.isArray(arr)) return [arr];
		return arr.flat(Infinity);
	}
	// endregion

	// region Record/Special functions
	static RECORD_ID(): string {
		// This is handled specially in the emitter (returns this.id)
		return "";
	}

	static CREATED_TIME(): string | null {
		return null;
	}

	static LAST_MODIFIED_TIME(): string | null {
		return null;
	}

	static ERROR(message?: unknown): never {
		throw new Error(AirtableRuntime._toStr(message || "Error"));
	}

	static ISERROR(value: unknown): boolean {
		try {
			// If the value was computed without error, it's not an error
			return value instanceof Error || (typeof value === "number" && isNaN(value));
		} catch {
			return true;
		}
	}
	// endregion
}

/**
 * Typed error hierarchy for the MyAirtable runtime. Mirrors the C#/Rust/Go/Java/Kotlin/Swift
 * targets: a single base `AirtableError extends Error` with 7 concrete subclasses. Catch
 * `AirtableError` for everything, or narrow with `instanceof` for targeted handling.
 *
 * Each subclass sets `this.name` and calls `Object.setPrototypeOf(this, X.prototype)` so that
 * `instanceof` keeps working even when consumers transpile to an older target (where `extends
 * Error` otherwise breaks the prototype chain).
 */

/** Base class for all errors raised by the generated client. */
export class AirtableError extends Error {
	constructor(message: string, options?: { cause?: unknown }) {
		super(message, options as ErrorOptions);
		this.name = "AirtableError";
		Object.setPrototypeOf(this, AirtableError.prototype);
	}
}

/** Structured Airtable API error envelope (`{"error":{"type":...,"message":...}}` or `{"error":"CODE"}`). */
export class ApiError extends AirtableError {
	readonly code: string;
	readonly statusCode: number;
	readonly apiMessage: string;

	constructor(code: string, statusCode: number, apiMessage: string) {
		super(`AirtableError.ApiError(${code}) [${statusCode}]: ${apiMessage}`);
		this.name = "ApiError";
		this.code = code;
		this.statusCode = statusCode;
		this.apiMessage = apiMessage;
		Object.setPrototypeOf(this, ApiError.prototype);
	}
}

/** HTTP 429. `retryAfter` (seconds) is parsed from the Retry-After header when present. */
export class RateLimitedError extends AirtableError {
	readonly retryAfter?: number;
	readonly statusCode = 429;

	constructor(retryAfter?: number) {
		super(
			retryAfter !== undefined
				? `AirtableError.RateLimitedError(retryAfter=${retryAfter}s)`
				: "AirtableError.RateLimitedError",
		);
		this.name = "RateLimitedError";
		this.retryAfter = retryAfter;
		Object.setPrototypeOf(this, RateLimitedError.prototype);
	}
}

/** Non-2xx HTTP response without a parseable Airtable error code. `body` is the raw response body. */
export class HttpError extends AirtableError {
	readonly statusCode: number;
	readonly body?: string;

	constructor(statusCode: number, body?: string) {
		super(body ? `AirtableError.HttpError(${statusCode}): ${body}` : `AirtableError.HttpError(${statusCode})`);
		this.name = "HttpError";
		this.statusCode = statusCode;
		this.body = body;
		Object.setPrototypeOf(this, HttpError.prototype);
	}
}

/** JSON (de)serialization failure; wraps the underlying cause. */
export class DecodingError extends AirtableError {
	constructor(message: string, cause?: unknown) {
		super(`AirtableError.DecodingError: ${message}`, { cause });
		this.name = "DecodingError";
		Object.setPrototypeOf(this, DecodingError.prototype);
	}
}

/** A request URL could not be constructed. */
export class InvalidUrlError extends AirtableError {
	constructor(message: string) {
		super(`AirtableError.InvalidUrlError: ${message}`);
		this.name = "InvalidUrlError";
		Object.setPrototypeOf(this, InvalidUrlError.prototype);
	}
}

/** Missing API key or base ID. */
export class MissingCredentialsError extends AirtableError {
	constructor(message: string) {
		super(`AirtableError.MissingCredentialsError: ${message}`);
		this.name = "MissingCredentialsError";
		Object.setPrototypeOf(this, MissingCredentialsError.prototype);
	}
}

/** Transport-level failure that is NOT a 429 (DNS, connection reset, timeout, ...). */
export class NetworkError extends AirtableError {
	constructor(message: string, cause?: unknown) {
		super(`AirtableError.NetworkError: ${message}`, { cause });
		this.name = "NetworkError";
		Object.setPrototypeOf(this, NetworkError.prototype);
	}
}

/**
 * Extract the Airtable error code from either envelope shape: the legacy bare-string
 * `{"error":"NOT_FOUND"}` or the structured `{"error":{"type":...,"message":...}}`.
 * Returns "" on parse failure or absence. (Mirrors Rust `parse_api_error_code`.)
 */
export function parseApiErrorCode(body: string): string {
	try {
		const parsed = JSON.parse(body) as unknown;
		const err = (parsed as { error?: unknown })?.error;
		if (typeof err === "string") return err;
		if (err && typeof err === "object") {
			const type = (err as { type?: unknown }).type;
			if (typeof type === "string") return type;
		}
	} catch {
		// fall through
	}
	return "";
}

/**
 * Extract the human-readable message from the structured envelope
 * `{"error":{"type":...,"message":...}}`. Returns undefined on parse failure or absence.
 */
export function parseApiErrorMessage(body: string): string | undefined {
	try {
		const parsed = JSON.parse(body) as unknown;
		const err = (parsed as { error?: unknown })?.error;
		if (err && typeof err === "object") {
			const message = (err as { message?: unknown }).message;
			if (typeof message === "string") return message;
		}
	} catch {
		// fall through
	}
	return undefined;
}

/**
 * Classify an error thrown by airtable.js (shaped `{ error: <code>, message, statusCode }`) into a
 * typed `AirtableError`. Idempotent: an already-typed `AirtableError` is returned unchanged.
 */
export function classifyAirtableJsError(error: unknown): AirtableError {
	if (error instanceof AirtableError) return error;
	const e = error as { error?: string; message?: string; statusCode?: number };
	const status = typeof e?.statusCode === "number" ? e.statusCode : undefined;
	const message = e?.message ?? String(error);
	if (status === 429) return new RateLimitedError(undefined); // airtable.js carries no Retry-After
	if (status !== undefined) {
		return e.error ? new ApiError(e.error, status, message) : new HttpError(status, message);
	}
	return new NetworkError(message, error); // no status -> transport/unknown
}

/**
 * Classify a non-success HTTP response (raw-fetch PATCH path) from its status + body. `retryAfter`
 * (seconds) is optional and only used for the 429 case (parsed from the Retry-After header).
 */
export function classifyHttpResponse(status: number, body: string, retryAfter?: number): AirtableError {
	if (status === 429) return new RateLimitedError(retryAfter);
	const code = parseApiErrorCode(body);
	return code ? new ApiError(code, status, parseApiErrorMessage(body) ?? body) : new HttpError(status, body);
}

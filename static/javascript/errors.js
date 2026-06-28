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
class AirtableError extends Error {
	constructor(message, options) {
		super(message, options);
		this.name = "AirtableError";
		Object.setPrototypeOf(this, AirtableError.prototype);
	}
}

/** Structured Airtable API error envelope (`{"error":{"type":...,"message":...}}` or `{"error":"CODE"}`). */
class ApiError extends AirtableError {
	constructor(code, statusCode, apiMessage) {
		super(`AirtableError.ApiError(${code}) [${statusCode}]: ${apiMessage}`);
		this.name = "ApiError";
		this.code = code;
		this.statusCode = statusCode;
		this.apiMessage = apiMessage;
		Object.setPrototypeOf(this, ApiError.prototype);
	}
}

/** HTTP 429. `retryAfter` (seconds) is parsed from the Retry-After header when present. */
class RateLimitedError extends AirtableError {
	constructor(retryAfter) {
		super(
			retryAfter !== undefined
				? `AirtableError.RateLimitedError(retryAfter=${retryAfter}s)`
				: "AirtableError.RateLimitedError",
		);
		this.name = "RateLimitedError";
		this.retryAfter = retryAfter;
		this.statusCode = 429;
		Object.setPrototypeOf(this, RateLimitedError.prototype);
	}
}

/** Non-2xx HTTP response without a parseable Airtable error code. `body` is the raw response body. */
class HttpError extends AirtableError {
	constructor(statusCode, body) {
		super(body ? `AirtableError.HttpError(${statusCode}): ${body}` : `AirtableError.HttpError(${statusCode})`);
		this.name = "HttpError";
		this.statusCode = statusCode;
		this.body = body;
		Object.setPrototypeOf(this, HttpError.prototype);
	}
}

/** JSON (de)serialization failure; wraps the underlying cause. */
class DecodingError extends AirtableError {
	constructor(message, cause) {
		super(`AirtableError.DecodingError: ${message}`, { cause });
		this.name = "DecodingError";
		Object.setPrototypeOf(this, DecodingError.prototype);
	}
}

/** A request URL could not be constructed. */
class InvalidUrlError extends AirtableError {
	constructor(message) {
		super(`AirtableError.InvalidUrlError: ${message}`);
		this.name = "InvalidUrlError";
		Object.setPrototypeOf(this, InvalidUrlError.prototype);
	}
}

/** Missing API key or base ID. */
class MissingCredentialsError extends AirtableError {
	constructor(message) {
		super(`AirtableError.MissingCredentialsError: ${message}`);
		this.name = "MissingCredentialsError";
		Object.setPrototypeOf(this, MissingCredentialsError.prototype);
	}
}

/** Transport-level failure that is NOT a 429 (DNS, connection reset, timeout, ...). */
class NetworkError extends AirtableError {
	constructor(message, cause) {
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
function parseApiErrorCode(body) {
	try {
		const parsed = JSON.parse(body);
		const err = parsed?.error;
		if (typeof err === "string") return err;
		if (err && typeof err === "object" && typeof err.type === "string") return err.type;
	} catch {
		// fall through
	}
	return "";
}

/**
 * Extract the human-readable message from the structured envelope
 * `{"error":{"type":...,"message":...}}`. Returns undefined on parse failure or absence.
 */
function parseApiErrorMessage(body) {
	try {
		const parsed = JSON.parse(body);
		const err = parsed?.error;
		if (err && typeof err === "object" && typeof err.message === "string") return err.message;
	} catch {
		// fall through
	}
	return undefined;
}

/**
 * Classify an error thrown by airtable.js (shaped `{ error: <code>, message, statusCode }`) into a
 * typed `AirtableError`. Idempotent: an already-typed `AirtableError` is returned unchanged.
 */
function classifyAirtableJsError(error) {
	if (error instanceof AirtableError) return error;
	const e = error;
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
function classifyHttpResponse(status, body, retryAfter) {
	if (status === 429) return new RateLimitedError(retryAfter);
	const code = parseApiErrorCode(body);
	return code ? new ApiError(code, status, parseApiErrorMessage(body) ?? body) : new HttpError(status, body);
}

module.exports = {
	AirtableError,
	ApiError,
	RateLimitedError,
	HttpError,
	DecodingError,
	InvalidUrlError,
	MissingCredentialsError,
	NetworkError,
	parseApiErrorCode,
	parseApiErrorMessage,
	classifyAirtableJsError,
	classifyHttpResponse,
};

import { AirtableOptions } from "airtable";
import process from "node:process";

export function getApiKey(): string {
	const apiKey = process.env.AIRTABLE_API_KEY;
	if (!apiKey) {
		throw new Error("Airtable API key is not set");
	}
	return apiKey;
}

export function getBaseId(): string {
	const baseId = process.env.AIRTABLE_BASE_ID;
	if (!baseId) {
		throw new Error("Airtable Base ID is not set");
	}
	return baseId;
}

export function getEndpointUrl(): string | undefined {
	return process.env.AIRTABLE_ENDPOINT_URL;
}

export function getApiVersion(): string | undefined {
	return process.env.AIRTABLE_API_VERSION;
}

export function getNoRetryIfRateLimited(): boolean | undefined {
	const value = process.env.AIRTABLE_NO_RETRY_IF_RATE_LIMITED;
	if (value === undefined) {
		return undefined;
	}
	return value.toLowerCase() === "true";
}

export function getRequestTimeout(): number | undefined {
	const value = process.env.AIRTABLE_REQUEST_TIMEOUT;
	if (value === undefined) {
		return undefined;
	}
	const parsed = parseInt(value, 10);
	if (isNaN(parsed)) {
		throw new Error("Airtable request timeout is not a valid number");
	}
	return parsed;
}

export function getCustomHeaders(): { [x: string]: string | number | boolean; } | undefined {
	const headersEnv = process.env.AIRTABLE_CUSTOM_HEADERS;
	if (!headersEnv) {
		return undefined;
	}
	try {
		const headers = JSON.parse(headersEnv);
		if (typeof headers === "object" && headers !== null) {
			return headers as { [x: string]: string | number | boolean; };
		} else {
			throw new Error("Airtable custom headers is not a valid object");
		}
	} catch {
		throw new Error("Airtable custom headers is not a valid JSON string");
	}
}

export function getOptions(): AirtableOptions {
	return {
		apiKey: getApiKey(),
		apiVersion: getApiVersion(),
		endpointUrl: getEndpointUrl(),
		requestTimeout: getRequestTimeout(),
		noRetryIfRateLimited: getNoRetryIfRateLimited(),
		customHeaders: getCustomHeaders(),
	};
}

export function validateKey<T extends string>(name: T, names: readonly T[] | T[]): void {
	if (!names.includes(name)) {
		throw new Error(`Invalid field name: ${name}.`);
	}
}

import { AirtableOptions } from "airtable";
import process from "node:process";

// Config registry keyed by baseId
const _configRegistry: Map<string, AirtableOptions> = new Map();
let _defaultBaseId: string | undefined;

export function setAirtableConfig(baseId: string, options: AirtableOptions): void {
	_configRegistry.set(baseId, options);
	_defaultBaseId = baseId; // Last registered becomes default
}

export function getConfigForBase(baseId: string): AirtableOptions | undefined {
	return _configRegistry.get(baseId);
}

export function getApiKey(baseId?: string): string {
	// If baseId provided, look up in registry
	if (baseId) {
		const config = _configRegistry.get(baseId);
		if (config?.apiKey) return config.apiKey;
	}
	// Fall back to default baseId's config
	if (_defaultBaseId) {
		const config = _configRegistry.get(_defaultBaseId);
		if (config?.apiKey) return config.apiKey;
	}
	// Fall back to env var
	const apiKey = process.env.AIRTABLE_API_KEY;
	if (!apiKey) {
		throw new Error("Airtable API key is not set");
	}
	return apiKey;
}

export function getBaseId(): string {
	if (_defaultBaseId) return _defaultBaseId;
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

export function getCustomHeaders(): { [x: string]: string | number | boolean } | undefined {
	const headersEnv = process.env.AIRTABLE_CUSTOM_HEADERS;
	if (!headersEnv) {
		return undefined;
	}
	try {
		const headers = JSON.parse(headersEnv);
		if (typeof headers === "object" && headers !== null) {
			return headers as { [x: string]: string | number | boolean };
		} else {
			throw new Error("Airtable custom headers is not a valid object");
		}
	} catch {
		throw new Error("Airtable custom headers is not a valid JSON string");
	}
}

export function getOptions(baseId?: string): AirtableOptions {
	const config = baseId
		? _configRegistry.get(baseId)
		: _defaultBaseId
			? _configRegistry.get(_defaultBaseId)
			: undefined;
	return {
		apiKey: getApiKey(baseId),
		apiVersion: config?.apiVersion ?? getApiVersion(),
		endpointUrl: config?.endpointUrl ?? getEndpointUrl(),
		requestTimeout: config?.requestTimeout ?? getRequestTimeout(),
		noRetryIfRateLimited: config?.noRetryIfRateLimited ?? getNoRetryIfRateLimited(),
		customHeaders: config?.customHeaders ?? getCustomHeaders(),
	};
}

export function validateKey<T extends string>(name: T, names: readonly T[] | T[]): void {
	if (!names.includes(name)) {
		throw new Error(`Invalid field name: ${name}.`);
	}
}

const baseUrl: string = "https://airtable.com";

export function buildUrl(
	baseId: string = "",
	tableId: string = "",
	viewId: string = "",
	recordId: string = "",
): string {
	if (!baseId) {
		return baseId;
	} else if (!tableId) {
		return `${baseUrl}/${baseId}`;
	} else if (!viewId && !recordId) {
		return `${baseUrl}/${baseId}/${tableId}`;
	} else if (viewId && !recordId) {
		return `${baseUrl}/${baseId}/${tableId}/${viewId}`;
	} else if (recordId && !viewId) {
		return `${baseUrl}/${baseId}/${tableId}/${recordId}`;
	} else {
		return `${baseUrl}/${baseId}/${tableId}/${viewId}/${recordId}`;
	}
}

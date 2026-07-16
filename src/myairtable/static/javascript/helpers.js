// Config registry keyed by baseId
const _configRegistry = new Map();
let _defaultBaseId = undefined;

function setAirtableConfig(baseId, options) {
	_configRegistry.set(baseId, options);
	_defaultBaseId = baseId; // Last registered becomes default
}

function getConfigForBase(baseId) {
	return _configRegistry.get(baseId);
}

function getApiKey(baseId) {
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

function getBaseId() {
	if (_defaultBaseId) return _defaultBaseId;
	const baseId = process.env.AIRTABLE_BASE_ID;
	if (!baseId) {
		throw new Error("Airtable Base ID is not set");
	}
	return baseId;
}

function getEndpointUrl() {
	return process.env.AIRTABLE_ENDPOINT_URL;
}

function getApiVersion() {
	return process.env.AIRTABLE_API_VERSION;
}

function getNoRetryIfRateLimited() {
	const value = process.env.AIRTABLE_NO_RETRY_IF_RATE_LIMITED;
	if (value === undefined) {
		return undefined;
	}
	return value.toLowerCase() === "true";
}

function getRequestTimeout() {
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

function getCustomHeaders() {
	const headersEnv = process.env.AIRTABLE_CUSTOM_HEADERS;
	if (!headersEnv) {
		return undefined;
	}
	try {
		const headers = JSON.parse(headersEnv);
		if (typeof headers === "object" && headers !== null) {
			return headers;
		} else {
			throw new Error("Airtable custom headers is not a valid object");
		}
	} catch {
		throw new Error("Airtable custom headers is not a valid JSON string");
	}
}

function getOptions(baseId) {
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

function validateKey(name, names) {
	if (!names.includes(name)) {
		throw new Error(`Invalid field name: ${name}.`);
	}
}

const baseUrl = "https://airtable.com";

function buildUrl(baseId = "", tableId = "", viewId = "", recordId = "") {
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

module.exports = {
	setAirtableConfig,
	getConfigForBase,
	getApiKey,
	getBaseId,
	getEndpointUrl,
	getApiVersion,
	getNoRetryIfRateLimited,
	getRequestTimeout,
	getCustomHeaders,
	getOptions,
	validateKey,
	buildUrl,
};

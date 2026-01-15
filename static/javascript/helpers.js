function getApiKey() {
	const apiKey = process.env.AIRTABLE_API_KEY;
	if (!apiKey) {
		throw new Error("Airtable API key is not set");
	}
	return apiKey;
}

function getBaseId() {
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

function getOptions() {
	return {
		apiKey: getApiKey(),
		apiVersion: getApiVersion(),
		endpointUrl: getEndpointUrl(),
		requestTimeout: getRequestTimeout(),
		noRetryIfRateLimited: getNoRetryIfRateLimited(),
		customHeaders: getCustomHeaders(),
	};
}

function validateKey(name, names) {
	if (!names.includes(name)) {
		throw new Error(`Invalid field name: ${name}.`);
	}
}

module.exports = {
	getApiKey,
	getBaseId,
	getEndpointUrl,
	getApiVersion,
	getNoRetryIfRateLimited,
	getRequestTimeout,
	getCustomHeaders,
	getOptions,
	validateKey,
};

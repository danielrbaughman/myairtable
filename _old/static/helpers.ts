import process from "node:process";

export function getApiKey(): string {
	const apiKey = process.env.AIRTABLE_API_KEY;
	if (!apiKey) {
		throw new Error("Airtable API key is not set");
	}
	return apiKey;
}

export function validateKey<T extends string>(name: T, names: readonly T[] | T[]): void {
	if (!names.includes(name)) {
		throw new Error(`Invalid field name: ${name}.`);
	}
}

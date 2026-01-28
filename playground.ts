#!/usr/bin/env node
import { Airtable } from "./output";

async function main() {
	console.log("Hello World (TypeScript)");

	const airtable = new Airtable();
}

main().catch((err) => {
	console.error("Error in main:", err);
	process.exit(1);
});

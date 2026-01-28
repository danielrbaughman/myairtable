#!/usr/bin/env node

const { Airtable } = require("./output");

async function main() {
	console.log("Hello World (JavaScript)");

	const airtable = new Airtable();
	const job = await airtable.table("Jobs").get("recHKg9mlUN0jiwOu");
	console.log(job.name);
}

main().catch((err) => {
	console.error("Error in main:", err);
	process.exit(1);
});

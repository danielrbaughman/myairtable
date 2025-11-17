#!/usr/bin/env node
import process from "node:process";
import { Command } from "commander";
import { Airtable } from "./output";

const program = new Command();
program.action(async () => {
	const job = await new Airtable().jobs.get("recj337mJ7HEkbJ1R");
	console.log(job.name);
});

program.parse(process.argv);

#!/usr/bin/env node
import process from "node:process";
import { Command } from "commander";
import { Airtable, JobsModel } from "./output";

const program = new Command();
program.action(async () => {
	console.log("Hello World (TypeScript)");
	console.log(JobsModel.f.name.equals("Bob"));
});

program.parse(process.argv);

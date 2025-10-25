#!/usr/bin/env node
import process from "node:process";
import { Command } from "commander";
import { Airtable } from "./output"

const program = new Command();
program.action(async () => {
  const companies = await new Airtable().companies.get();
	console.log(companies.length);
});

program.parse(process.argv);

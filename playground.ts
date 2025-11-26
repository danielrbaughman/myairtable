#!/usr/bin/env node
import process from "node:process";
import { Command } from "commander";

const program = new Command();
program.action(async () => {
	console.log("hello world")
});

program.parse(process.argv);

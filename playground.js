#!/usr/bin/env node
const process = require("node:process");
const { Command } = require("commander");

const program = new Command();
program.action(async () => {
	console.log("Hello World (JavaScript)");
});

program.parse(process.argv);

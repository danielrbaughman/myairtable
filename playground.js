#!/usr/bin/env node
const process = require("node:process");
const { Command } = require("commander");

const program = new Command();
program.action(async () => {
	console.log("hello world js");
});

program.parse(process.argv);

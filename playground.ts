#!/usr/bin/env node
import process from "node:process";
import { Command } from "commander";
import { Airtable, JobsModel, JobsFormulas, AND } from "./output";

const program = new Command();
program.action(async () => {
	const j = JobsFormulas;
	// const job = await new Airtable().jobs.get("recj337mJ7HEkbJ1R");
	console.log(j.dueDate.on().daysAgo(1));
	j.dueDate.after().yearsAgo(2);
	j.dueDate.before().monthsAgo(3);
	const formula = AND(
		j.dueDate.on().daysAgo(1),
		j.dueDate.empty(),
		j.activeQLookup.true(),
		j.dueDate.after().yearsAgo(2),
		j.dueDate.before().monthsAgo(3),
		j.dueDate.on(new Date("2023-01-01")),
		j.name.containsAll(["Important", "Urgent"]),
		j.name.equals("Project Alpha"),
		j.acresEq.between(10, 20),
		j.acres25Eq.greaterThan(5),
	);
	console.log(formula);
});

program.parse(process.argv);

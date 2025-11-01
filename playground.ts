#!/usr/bin/env node
import process from "node:process";
import { Command } from "commander";
// import { Airtable } from "./output";
import { AirtableTs, Table } from "airtable-ts";
import * as z from "zod";

const program = new Command();
program.action(async () => {
	const apiKey = process.env.AIRTABLE_API_KEY;

	const db = new AirtableTs({
		apiKey: apiKey,
	});

	const teamsZod = z.object({
		id: z.string(),
		name: z.string().optional(),
		email: z.email().or(z.literal("")).optional(),
	});

	type TeamsRecord = z.infer<typeof teamsZod>;

	const teamFieldNames = { name: "string", email: "string" } as const;
	const teamFieldIds = { name: "flddlHwEkZPUc18zB", email: "fld0FDjwBjaSaFAn5" } as const;

	const team: Table<TeamsRecord> = {
		name: "Team",
		baseId: process.env.AIRTABLE_BASE_ID || "",
		tableId: "tbltyutRGeqeflNU5",
		schema: teamFieldNames,
		mappings: teamFieldIds,
	};

	class Model {
		id: string;

		constructor(id: string) {
			this.id = id;
		}
	}

	class TeamsModel extends Model {
		private _name?: string;
		private _email?: string;

		constructor(data: TeamsRecord) {
			super(data.id);
			this._name = data.name;
			this._name = data.name;
			this._email = data.email;
			this.validate(); // Validate on construction
		}

		get name(): string | undefined {
			return this._name;
		}

		set name(value: string | undefined) {
			this._name = value;
			this.validate();
		}

		get email(): string | undefined {
			return this._email;
		}

		set email(value: string | undefined) {
			this._email = value;
			this.validate();
		}

		toRecord(): TeamsRecord {
			return {
				id: this.id,
				name: this._name,
				email: this._email,
			};
		}

		validate(): boolean {
			const parsed = teamsZod.safeParse(this.toRecord());
			if (!parsed.success) {
				throw new Error("Validation error: " + parsed.error.message);
			}
			return parsed.success;
		}
	}

	const teamMembers: TeamsRecord[] = await db.scan(team);
	console.log("Team Members:", teamMembers.length);

	const parsedTeamMembers: TeamsModel[] = await Promise.all(
		teamMembers.map(async (member) => {
			const parsed = teamsZod.safeParse(member);
			if (!parsed.success) {
				// console.error("Validation error:", member, parsed.error);
				return null;
			}
			return new TeamsModel(parsed.data);
		}),
	).then((results) => results.filter((member): member is TeamsModel => member !== null));

	// console.log("Parsed Team Members:", parsedTeamMembers);
	console.log("Parsed Team Members:", parsedTeamMembers.length);
	const t = parsedTeamMembers[0];
	t.email = "hello@hello.com";
	// t.validate();
	console.log(t.email);
});

program.parse(process.argv);

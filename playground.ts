#!/usr/bin/env node
import process from "node:process";
import { Command } from "commander";
import { TeamPayTypeOption, TeamZodType, TeamRecord, TeamFieldPropertyIdMapping, TeamZodSchema } from "./output";
import { TeamFieldPropertyTypeMapping } from "./output/dynamic/types/team";
import { AirtableTs, Table } from "airtable-ts";


const program = new Command();
program.action(async () => {
	// console.log("TeamFieldPropertyIdMapping", TeamFieldPropertyIdMapping);
	const team: Table<TeamRecord> = {
		name: "Team",
		baseId: process.env.AIRTABLE_BASE_ID || "",
		tableId: "tbltyutRGeqeflNU5",
		schema: TeamFieldPropertyTypeMapping,
		mappings: TeamFieldPropertyIdMapping,
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
		private _payType?: TeamPayTypeOption;

		constructor(data: TeamZodType) {
			super(data.id);
			this._name = data.name;
			this._email = data.email;
			this._payType = data.payType;
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

		get payType(): TeamPayTypeOption | undefined {
			return this._payType;
		}

		set payType(value: TeamPayTypeOption | undefined) {
			this._payType = value;
			this.validate();
		}

		toRecord(): TeamZodType {
			return {
				id: this.id,
				name: this._name,
				email: this._email,
				payType: this._payType,
			};
		}

		validate(): boolean {
			const parsed = TeamZodSchema.safeParse(this.toRecord());
			if (!parsed.success) {
				throw new Error("Validation error: " + parsed.error.message);
			}
			return parsed.success;
		}
	}

	const apiKey = process.env.AIRTABLE_API_KEY;

	const db = new AirtableTs({
		apiKey: apiKey,
	});

	const teamMembers: TeamRecord = await db.get<TeamRecord>(team, "rec01prAYWAOwsALi");
	console.log("Team Members:", teamMembers);

	// const parsedTeamMembers: TeamsModel[] = await Promise.all(
	// 	teamMembers.map(async (member) => {
	// 		const parsed = TeamZodSchema.safeParse(member);
	// 		if (!parsed.success) {
	// 			console.error("Validation error:", member, parsed.error);
	// 			return null;
	// 		}
	// 		return new TeamsModel(parsed.data);
	// 	}),
	// ).then((results) => results.filter((member): member is TeamsModel => member !== null));

	// // console.log("Parsed Team Members:", parsedTeamMembers);
	// console.log("Parsed Team Members:", parsedTeamMembers.length);
	// const t = parsedTeamMembers[0];
	// t.email = "hello@hello.com";
	// // t.validate();
	// console.log(t.email);
});

program.parse(process.argv);

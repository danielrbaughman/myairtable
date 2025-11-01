#!/usr/bin/env node
import process from "node:process";
import { Command } from "commander";
import { TeamPayTypeOption, TeamZodType, TeamRecord, TeamFieldPropertyIdMapping, TeamZodSchema } from "./output";
import { TeamFieldPropertyTypeMapping, TeamPayTypeOptions } from "./output/dynamic/types/team";
import { AirtableTs, Table } from "airtable-ts";
import * as z from "zod";


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
		constructor(data: TeamZodType) {
			super(data.id);
			this._name = this._nameSchema.parse(data.name);
			this._email = this._emailSchema.parse(data.email);
			this._payType = this._payTypeSchema.parse(data.payType);
		}
		
		private _name: string | null;
		private _nameSchema = z.string().nullable();
		public get name(): string | null { return this._name; }
		public set name(value: string | null) { this._name = this._nameSchema.parse(value); }
		
		private _email: string | null;
		private _emailSchema = z.email().nullable();
		public get email(): string | null { return this._email; }
		public set email(value: string | null) { this._email = this._emailSchema.parse(value); }
		
		private _payType: TeamPayTypeOption | null;
		private _payTypeSchema = z.enum(TeamPayTypeOptions).nullable();
		public get payType(): TeamPayTypeOption | null { return this._payType; }
		public set payType(value: TeamPayTypeOption | null) { this._payType = this._payTypeSchema.parse(value); }

		toJSON(): Partial<TeamRecord> {
			return {
				id: this.id,
				name: this.name,
				email: this.email,
				payType: this.payType,
			};
		}
	}

	const apiKey = process.env.AIRTABLE_API_KEY;

	const db = new AirtableTs({
		apiKey: apiKey,
	});

	const teamMember = await db.get(team, "rec01prAYWAOwsALi");
	// console.log("Team Members:", teamMember);
	// const parsedTeamMember = TeamZodSchema.parse(teamMember);

	const parsed = TeamZodSchema.safeParse(teamMember);
	if (!parsed.success) {
		console.error("Validation error:", teamMember, parsed.error);
		throw new Error("Validation failed");
	}
	const teamMemberModel = new TeamsModel(parsed.data);
	console.log("Parsed Team Member Model:", teamMemberModel.toJSON());
	teamMemberModel.email = "hello"
	// const parsedTeamMembers: TeamsModel[] = await Promise.all(
	// 	teamMember.map(async (member) => {
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

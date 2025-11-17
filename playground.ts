#!/usr/bin/env node
import process from "node:process";
import { Command } from "commander";
import { JobsTable, JobsModel } from "./output";
import { AirtableTs } from "airtable-ts";


const program = new Command();
program.action(async () => {

	// class TeamsModel extends AirtableModel {
	// 	constructor(data: TeamRecord) {
	// 		super(data.id);
	// 		this._name = data.name;
	// 		this._email = data.email;
	// 		this._payType = data.payType;
	// 	}
		
	// 	private _name: string | null;
	// 	private _nameSchema = z.string().nullable();
	// 	public get name(): string | null { return this._name; }
	// 	public set name(value: string | null) { this._name = this._nameSchema.parse(value); }
		
	// 	private _email: string | null;
	// 	private _emailSchema = z.string().nullable();
	// 	public get email(): string | null { return this._email; }
	// 	public set email(value: string | null) { this._email = this._emailSchema.parse(value); }
		
	// 	private _payType: TeamPayTypeOption | null;
	// 	private _payTypeSchema = z.enum(TeamPayTypeOptions).nullable();
	// 	public get payType(): TeamPayTypeOption | null { return this._payType; }
	// 	public set payType(value: TeamPayTypeOption | null) { this._payType = this._payTypeSchema.parse(value); }

	// 	toJSON(): Partial<TeamRecord> {
	// 		return {
	// 			id: this.id,
	// 			name: this.name,
	// 			email: this.email,
	// 			payType: this.payType,
	// 		};
	// 	}
	// }

	const apiKey = process.env.AIRTABLE_API_KEY;

	const db = new AirtableTs({
		apiKey: apiKey,
		readValidation: "warning" // special types, like "infinity" fail their validation
	});

	const job = await db.get(JobsTable, "recj337mJ7HEkbJ1R");
	// console.log("Team Members:", teamMember);
	// const parsedTeamMember = TeamZodSchema.parse(teamMember);

	// const parsed = TeamZodSchema.safeParse(teamMember);
	// if (!parsed.success) {
	// 	console.error("Validation error:", teamMember, parsed.error);
	// 	throw new Error("Validation failed");
	// }
	const jobModel = new JobsModel(job);
	console.log(jobModel.toJSON());
	// console.log("Parsed Team Member Model:", teamMemberModel.toJSON());
	// teamMemberModel.email = "hello"
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

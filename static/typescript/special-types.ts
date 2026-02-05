import { AirtableOptions, FieldSet } from "airtable";
import * as z from "zod";

export type { AirtableOptions, FieldSet, Record, RecordData, Attachment, Collaborator } from "airtable";

export const baseIdSchema = z.string().regex(/\bapp[a-zA-Z0-9]{14}\b/, "Invalid Airtable Base ID");
export const recordIdSchema = z.string().regex(/\brec[a-zA-Z0-9]{14}\b/, "Invalid Airtable Record ID");
export function validateRecordIds(idOrIds: string | string[]): void {
	if (Array.isArray(idOrIds)) {
		idOrIds.forEach((id) => recordIdSchema.parse(id));
	} else {
		recordIdSchema.parse(idOrIds);
	}
}
export const StringSchema = z.string("Value must be a string");
export const NumberSchema = z.number("Value must be a number");
export const BooleanSchema = z.boolean("Value must be a boolean");
export const SpecialNumberSchema = z.object({ specialValue: z.string() });
export const ErrorValueSchema = z.object({ error: z.string() });

export interface ExtendedAirtableOptions extends AirtableOptions {
	baseId?: string;
}

export const AirtableThumbnailSchema = z.object({
	url: z.string().optional(),
	width: z.number().optional(),
	height: z.number().optional(),
});

export type AirtableThumbnail = z.infer<typeof AirtableThumbnailSchema>;

export const AirtableThumbnailsSchema = z.object({
	small: AirtableThumbnailSchema.optional(),
	large: AirtableThumbnailSchema.optional(),
	full: AirtableThumbnailSchema.optional(),
});

export type AirtableThumbnails = z.infer<typeof AirtableThumbnailsSchema>;

export const AirtableAttachmentSchema = z.object({
	id: z.string().optional(),
	url: z.string().optional(),
	filename: z.string().optional(),
	size: z.number().optional(),
	type: z.string().optional(),
	thumbnails: AirtableThumbnailsSchema.optional(),
});

export type AirtableAttachment = z.infer<typeof AirtableAttachmentSchema>;

export const AirtableCollaboratorSchema = z.object({
	id: z.string().optional(),
	email: z.email().optional(),
	name: z.string().optional(),
});

export type AirtableCollaborator = z.infer<typeof AirtableCollaboratorSchema>;

export const AirtableButtonSchema = z.object({
	label: z.string().optional(),
	url: z.string().optional(),
});

export type AirtableButton = z.infer<typeof AirtableButtonSchema>;

export type RecordId = string;

/** A variant of `RecordData`, without the ID */
export interface CreateRecordData<T extends FieldSet> {
	fields: T;
}

/** Simplified representation of an Airtable record */
export interface IRecord<FldSt extends FieldSet> {
	/** The ID of the record */
	id: string;
	/** The fields of the record */
	fields: FldSt;
}

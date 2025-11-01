import { FieldSet } from "airtable";
import * as z from "zod";

export const AirtableThumbnailSchema = z.object({
	url: z.url().optional(),
	width: z.number().optional(),
	height: z.number().optional(),
});

export type AirtableThumbnail = z.infer<typeof AirtableThumbnailSchema>;

// export interface AirtableThumbnail {
// 	url?: string;
// 	width?: number;
// 	height?: number;
// }

export const AirtableThumbnailsSchema = z.object({
	small: AirtableThumbnailSchema.optional(),
	large: AirtableThumbnailSchema.optional(),
	full: AirtableThumbnailSchema.optional(),
});

export type AirtableThumbnails = z.infer<typeof AirtableThumbnailsSchema>;

// export interface AirtableThumbnails {
// 	small?: AirtableThumbnail;
// 	large?: AirtableThumbnail;
// 	full?: AirtableThumbnail;
// }

export const AirtableAttachmentSchema = z.object({
	id: z.string().optional(),
	url: z.url().optional(),
	filename: z.string().optional(),
	size: z.number().optional(),
	type: z.string().optional(),
	thumbnails: AirtableThumbnailsSchema.optional(),
});

export type AirtableAttachment = z.infer<typeof AirtableAttachmentSchema>;

// export interface AirtableAttachment {
// 	id?: string;
// 	url?: string;
// 	filename?: string;
// 	size?: number;
// 	type?: string;
// 	thumbnails?: AirtableThumbnails;
// }

export const AirtableCollaboratorSchema = z.object({
	id: z.string().optional(),
	email: z.email().optional(),
	name: z.string().optional(),
});

export type AirtableCollaborator = z.infer<typeof AirtableCollaboratorSchema>;

// export interface AirtableCollaborator {
// 	id?: string;
// 	email?: string;
// 	name?: string;
// }

export const AirtableButtonSchema = z.object({
	label: z.string().optional(),
	url: z.url().optional(),
});

export type AirtableButton = z.infer<typeof AirtableButtonSchema>;

// export interface AirtableButton {
// 	label?: string;
// 	url?: string;
// }

export const RecordIdSchema = z.string();

export type RecordId = z.infer<typeof RecordIdSchema>;

export interface CreateRecordData<T extends FieldSet> {
	fields: T;
}

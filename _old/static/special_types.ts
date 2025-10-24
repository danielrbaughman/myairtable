import { FieldSet } from "airtable";

export interface AirtableThumbnail {
	url?: string;
	width?: number;
	height?: number;
}

export interface AirtableThumbnails {
	small?: AirtableThumbnail;
	large?: AirtableThumbnail;
	full?: AirtableThumbnail;
}

export interface AirtableAttachment {
	id?: string;
	url?: string;
	filename?: string;
	size?: number;
	type?: string;
	thumbnails?: AirtableThumbnails;
}

export interface AirtableCollaborator {
	id?: string;
	email?: string;
	name?: string;
}

export interface AirtableButton {
	label?: string;
	url?: string;
}

export type RecordId = string;

export interface CreateRecordData<T extends FieldSet> {
	fields: T;
}

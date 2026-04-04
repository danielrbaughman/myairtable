export type FieldTypeSchema =
	| "singleLineText"
	| "multilineText"
	| "number"
	| "singleSelect"
	| "multipleSelects"
	| "multipleRecordLinks"
	| "multipleLookupValues"
	| "multipleAttachments"
	| "checkbox"
	| "date"
	| "dateTime"
	| "createdTime"
	| "lastModifiedTime"
	| "formula"
	| "count"
	| "rollup"
	| "lookup"
	| "singleCollaborator"
	| "multipleCollaborators"
	| "autoNumber"
	| "barcode"
	| "phoneNumber"
	| "email"
	| "url"
	| "percent"
	| "rating"
	| "duration"
	| "richText"
	| "currency"
	| "createdBy"
	| "button"
	| "lastModifiedBy";

export interface FieldOptionSchema {
	id: string;
	name: string;
	color: string;
}

export interface ViewSchema {
	id: string;
	name: string;
	type: string;
}

export interface FieldSchema {
	id: string;
	name: string;
	type: FieldTypeSchema;
	description?: string;
	options?: Record<string, any>;
}

export interface TableSchema {
	id: string;
	name: string;
	description?: string;
	primaryFieldId: string;
	fields: FieldSchema[];
	views: ViewSchema[];
}

export interface BaseSchema {
	tables: TableSchema[];
}

/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable no-unused-vars */
import { Record as ATRecord, Attachment, FieldSet, RecordData } from "airtable";
import * as z from "zod";
import { CreateRecordData, recordIdSchema } from "./special-types";

export abstract class AirtableModel<T extends FieldSet, U> {
	[key: string]: unknown;

	/** Zod schema for validation - must be defined by subclasses */
	protected static schema: z.ZodTypeAny;

	protected record?: ATRecord<T>;
	public id: string;

	constructor(id: string) {
		this.id = id ? recordIdSchema.parse(id) : id;
	}

	/**
	 * Validates the current model state against its Zod schema.
	 * No-op if schema is not defined (when generated with --no-zod).
	 * @throws {z.ZodError} if validation fails
	 */
	public validate(): void {
		const schema = (this.constructor as typeof AirtableModel).schema;
		if (!schema) return; // No-op when schema not defined
		schema.parse(this.toJson());
	}

	/**
	 * Converts the model to a plain object.
	 * Must be implemented by subclasses to return all field values.
	 */
	public abstract toJson(): U;

	protected writableFields(useFieldIds: boolean = false): Partial<T> {
		return {};
		// To be overridden by subclasses
	}

	/** The attachment we get from Airtable has extra properties that its own API doesn't accept when saving, so we sanitize it before saving */
	protected sanitizeAttachment(fieldName: string): Attachment[] {
		const attachments = this[fieldName] as Attachment[] | undefined;
		const writableAttachments: Attachment[] = [];
		if (attachments && Array.isArray(attachments)) {
			for (const attachment of attachments) {
				const writableAttachment: Attachment = {
					id: attachment.id,
					url: attachment.url,
					filename: attachment.filename,
					size: attachment.size,
					type: attachment.type,
				};
				writableAttachments.push(writableAttachment);
			}
		}

		return writableAttachments;
	}

	protected updateModel(record: ATRecord<T>): void {
		this.record = record;
		// To be overridden by subclasses
	}

	protected updateRecord(): void {
		// To be overridden by subclasses
	}

	public toRecord(): ATRecord<T> {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		return this.record;
	}

	public toRecordData(): RecordData<T> {
		return {
			id: this.id,
			fields: this.toRecord().fields,
		};
	}

	public toCreateRecordData(useFieldIds: boolean = true): CreateRecordData<Partial<T>> {
		return {
			fields: this.writableFields(useFieldIds),
		};
	}

	public toUpdateRecordData(useFieldIds: boolean = false): RecordData<Partial<T>> {
		return {
			id: this.id,
			fields: this.writableFields(useFieldIds),
		};
	}

	/**
	 * Saves the current Airtable record to the server.
	 * @throws {z.ZodError} if validation fails before save
	 */
	public async save(): Promise<void> {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.validate();
		this.updateRecord();
		// @ts-ignore
		this.record.fields = this.writableFields();
		this.record = await this.record.save();
		this.updateModel(this.record);
	}

	/**
	 * Fetches the latest data for the current Airtable record from the server, overwriting any unsaved local changes.
	 */
	public async fetch(): Promise<void> {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		this.record = await this.record.fetch();
		this.updateModel(this.record);
	}

	/**
	 * Deletes the current Airtable record to the server.
	 */
	public async delete(): Promise<void> {
		if (!this.record)
			throw new Error("Cannot destroy record: _record is undefined. Please use fromRecord to initialize the instance.");
		await this.record.destroy();
		this.record = undefined;
		this.id = "";
	}
}

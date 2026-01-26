/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable no-unused-vars */
import { AirtableOptions, Record as ATRecord, Attachment, FieldSet, RecordData } from "airtable";
import * as z from "zod";
import { CreateRecordData, recordIdSchema } from "./special-types";
import { getBaseId, getOptions } from "./helpers";

export abstract class AirtableModel<T extends FieldSet, U> {
	[key: string]: unknown;

	/** Zod schema for validation - must be defined by subclasses */
	protected static schema: z.ZodTypeAny;

	protected record?: ATRecord<T>;
	public id: string;

	// Change tracking
	protected _dirtyFields: Set<string> = new Set();
	protected _isNew: boolean = true;

	// Per-instance config (using __ prefix to avoid conflicts with field names)
	protected __configBaseId?: string;
	protected __configOptions?: AirtableOptions;

	constructor(id: string) {
		this.id = id ? recordIdSchema.parse(id) : id;
	}

	/** Sets the config for this model instance (called by factory methods) */
	protected setConfig(baseId: string, options: AirtableOptions): void {
		this.__configBaseId = baseId;
		this.__configOptions = options;
	}

	/** Gets the options for this instance, falling back to registry/env vars */
	protected getInstanceOptions(): AirtableOptions {
		if (this.__configOptions) return this.__configOptions;
		return getOptions(this.__configBaseId);
	}

	/** Gets the baseId for this instance, falling back to registry/env vars */
	protected getInstanceBaseId(): string {
		return this.__configBaseId ?? getBaseId();
	}

	/** Marks a field as dirty (modified) */
	protected markDirty(fieldName: string): void {
		this._dirtyFields.add(fieldName);
	}

	/** Checks if a field has been modified */
	protected isDirty(fieldName: string): boolean {
		return this._dirtyFields.has(fieldName);
	}

	/** Returns true if any fields have been modified */
	public hasChanges(): boolean {
		return this._dirtyFields.size > 0;
	}

	/** Returns an array of field names that have been modified */
	public getChangedFields(): string[] {
		return Array.from(this._dirtyFields);
	}

	/** Clears all dirty flags and marks the model as not new */
	protected clearDirtyFlags(): void {
		this._dirtyFields.clear();
		this._isNew = false;
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

	protected writableFields(useFieldIds: boolean = true): Partial<T> {
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

	public toUpdateRecordData(useFieldIds: boolean = true): RecordData<Partial<T>> {
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

		const updateData = this.toUpdateRecordData();

		try {
			const updatedRecords = await this.record._table.update([updateData]);
			this.record = updatedRecords[0] as ATRecord<T>;
		} catch (error) {
			// I am aware of how stupid this looks,
			// but without it, errors from Airtable's API don't surface properly;
			// you get a generic "UnhandledPromiseRejectionWarning" instead.
			throw new Error(String(error));
		}
		this.updateModel(this.record);
		this.clearDirtyFlags();
	}

	/**
	 * Fetches the latest data for the current Airtable record from the server, overwriting any unsaved local changes.
	 */
	public async fetch(): Promise<void> {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		try {
			this.record = await this.record.fetch();
		} catch (error) {
			// I am aware of how stupid this looks,
			// but without it, errors from Airtable's API don't surface properly;
			// you get a generic "UnhandledPromiseRejectionWarning" instead.
			throw new Error(String(error));
		}
		this.updateModel(this.record);
		this.clearDirtyFlags();
	}

	/**
	 * Deletes the current Airtable record to the server.
	 */
	public async delete(): Promise<void> {
		if (!this.record)
			throw new Error("Cannot destroy record: _record is undefined. Please use fromRecord to initialize the instance.");
		try {
			await this.record.destroy();
		} catch (error) {
			// I am aware of how stupid this looks,
			// but without it, errors from Airtable's API don't surface properly;
			// you get a generic "UnhandledPromiseRejectionWarning" instead.
			throw new Error(String(error));
		}
		this.record = undefined;
		this.id = "";
	}
}

/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable no-unused-vars */
import { AirtableOptions, Record as ATRecord, Attachment, FieldSet, RecordData } from "airtable";
import * as z from "zod";
import { CreateRecordData, recordIdSchema } from "./special-types";
import { getBaseId, getOptions } from "./helpers";

export abstract class AirtableModel<FldSt extends FieldSet, MdlInterface, Fld> {
	// Base properties
	protected record?: ATRecord<FldSt>;
	public id: string;
	[key: string]: unknown;

	// Mappings - must be defined by subclasses
	protected nameToIdMap: Record<string, string> = {};
	protected idToNameMap: Record<string, string> = {};
	protected nameToPropertyMap: Record<string, string> = {};

	/** Zod schema for validation - must be defined by subclasses */
	protected static schema: z.ZodTypeAny;

	// Change tracking
	protected _dirtyFields: Set<string> = new Set();
	protected _isNew: boolean = true;

	// Per-instance config (using __ prefix to avoid conflicts with field names)
	protected __configBaseId?: string;
	protected __configOptions?: AirtableOptions;

	constructor(id: string = "") {
		this.id = id ? recordIdSchema.parse(id) : id;
	}

	//#region PUBLIC
	public get(key: Fld): any | undefined {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		if (!this.nameToPropertyMap[key as string]) throw new Error(`Field name "${key}" does not exist on this model.`);
		return this[this.nameToPropertyMap[key as string]];
	}

	public set(key: Fld, value: any): void {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		if (!this.nameToPropertyMap[key as string]) throw new Error(`Field name "${key}" does not exist on this model.`);
		this[this.nameToPropertyMap[key as string]] = value;
	}

	/** Returns true if any fields have been modified */
	public hasChanges(): boolean {
		return this._dirtyFields.size > 0;
	}

	/** Returns an array of field names that have been modified */
	public getChangedFields(): string[] {
		return Array.from(this._dirtyFields);
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
	public abstract toJson(): MdlInterface;

	public toRecord(useFieldIds: boolean = true): ATRecord<FldSt> {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		const r = { ...this.record } as ATRecord<FldSt>;
		if (!useFieldIds) {
			r.fields = Object.fromEntries(
				Object.entries(r.fields).map(([key, value]) => {
					const name = this.idToNameMap[key] || key;
					return [name, value];
				}),
			) as FldSt;
		}
		return r;
	}

	public toCreateRecordData(useFieldIds: boolean = true): CreateRecordData<Partial<FldSt>> {
		return {
			fields: this.writableFields(useFieldIds),
		};
	}

	public toUpdateRecordData(useFieldIds: boolean = true): RecordData<Partial<FldSt>> {
		if (!this.id) throw new Error("Cannot create update record data: id is undefined.");
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
			this.record = updatedRecords[0] as ATRecord<FldSt>;
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

	//#endregion

	//#region PRIVATE

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

	/** Clears all dirty flags and marks the model as not new */
	protected clearDirtyFlags(): void {
		this._dirtyFields.clear();
		this._isNew = false;
	}

	protected writableFields(useFieldIds: boolean = true): Partial<FldSt> {
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

	protected updateModel(record: ATRecord<FldSt>): void {
		this.record = record;
		// To be overridden by subclasses
	}

	protected updateRecord(): void {
		// To be overridden by subclasses
	}

	//#endregion
}

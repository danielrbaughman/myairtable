/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable no-unused-vars */
import { AirtableOptions, Record as ATRecord, Attachment, FieldSet, RecordData } from "airtable";
import * as z from "zod";
import { CreateRecordData, IRecord, RecordId, recordIdSchema } from "./special-types";
import { getBaseId, getOptions } from "./helpers";
import { LinkedRecord, LinkedRecords, wrapLinkedRecordProxy } from "./linked-record";

export type FieldType = "generic" | "linkedRecord" | "linkedRecords" | "attachment";

export interface FieldDescriptor {
	propertyName: string;
	fieldId: string;
	fieldName: string;
	isComputed: boolean;
	fieldType: FieldType;
	linkedModelFromId?: (id: any, config?: AirtableOptions & { baseId: string }) => any;
	linkedModelClass?: any;
}

export abstract class AirtableModel<FldSt extends FieldSet, MdlInterface, Fld> {
	// Base properties
	protected record?: ATRecord<FldSt>;
	public id: string;
	public evaluateFormulasAtRuntime: boolean = false;
	[key: string]: unknown;

	// Mappings - must be defined by subclasses
	protected static nameToIdMap: Record<string, string> = {};
	protected static idToNameMap: Record<string, string> = {};
	protected static nameToPropertyMap: Record<string, string> = {};

	/** Zod schema for validation - must be defined by subclasses */
	protected static schema: z.ZodTypeAny;

	/** Field descriptors - must be defined by subclasses */
	protected static fieldDescriptors: FieldDescriptor[] = [];

	public static getFieldDescriptor(propertyName: string): FieldDescriptor | undefined {
		return this.fieldDescriptors.find((d) => d.propertyName === propertyName);
	}

	// Field storage
	protected _fields: Record<string, unknown> = {};

	// Change tracking
	protected _dirtyFields: Set<string> = new Set();
	protected _isNew: boolean = true;

	// Per-instance config (using __ prefix to avoid conflicts with field names)
	protected __configBaseId?: string;
	protected __configOptions?: AirtableOptions;

	constructor(id: string = "") {
		this.id = id ? recordIdSchema.parse(id) : id;
	}

	protected getFieldDescriptors(): FieldDescriptor[] {
		return (this.constructor as typeof AirtableModel).fieldDescriptors;
	}

	//#region PUBLIC
	/** Get a value by Airtable field name */
	public get(key: Fld): any | undefined {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		if (!(this.constructor as typeof AirtableModel).nameToPropertyMap[key as string])
			throw new Error(`Field name "${key}" does not exist on this model.`);
		return this[(this.constructor as typeof AirtableModel).nameToPropertyMap[key as string]];
	}

	/** Set a value by Airtable field name */
	public set(key: Fld, value: any): void {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		if (!(this.constructor as typeof AirtableModel).nameToPropertyMap[key as string])
			throw new Error(`Field name "${key}" does not exist on this model.`);
		this[(this.constructor as typeof AirtableModel).nameToPropertyMap[key as string]] = value;
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
	 * @throws {z.ZodError} if validation fails
	 */
	public validate(): void {
		const schema = (this.constructor as typeof AirtableModel).schema;
		if (!schema) return; // No-op when schema not defined
		schema.parse(this.toJson());
	}

	/** Converts the model to a plain object. */
	public toJson(): MdlInterface {
		const result: Record<string, unknown> = {};
		result.id = this.id || undefined;
		for (const desc of this.getFieldDescriptors()) {
			if (desc.fieldType === "linkedRecord" && !desc.isComputed) {
				result[desc.propertyName] = (this._fields[desc.propertyName] as any)?.id;
			} else if (desc.fieldType === "linkedRecords" && !desc.isComputed) {
				result[desc.propertyName] = (this._fields[desc.propertyName] as any)?.ids;
			} else {
				result[desc.propertyName] = this._fields[desc.propertyName];
			}
		}
		return result as MdlInterface;
	}

	/** Returns the model as a simple interface, equivalent to the original Airtable JSON payload. */
	public toIRecord(useFieldIds: boolean = false): IRecord<FldSt> {
		const r = this.toRecord(useFieldIds);
		return {
			id: r.id,
			fields: r.fields,
		};
	}

	/**
	 * Returns the model as Airtable.js's `Record<FieldSet>` class
	 *
	 * @param useFieldIds - Default: `false`.
	 */
	public toRecord(useFieldIds: boolean = false): ATRecord<FldSt> {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		const r = { ...this.record } as ATRecord<FldSt>;
		if (!useFieldIds) {
			r.fields = Object.fromEntries(
				Object.entries(r.fields).map(([key, value]) => {
					const name = (this.constructor as typeof AirtableModel).idToNameMap[key] || key;
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

	/** Saves the current Airtable record to the server. */
	public async save(): Promise<void> {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.validate();

		try {
			if (this.id) {
				const updatedRecords = await this.record._table.update([this.toUpdateRecordData(true)]);
				this.record = updatedRecords[0] as ATRecord<FldSt>;
			} else {
				const createdRecords = await this.record._table.create([this.toCreateRecordData(true)]);
				this.record = createdRecords[0] as ATRecord<FldSt>;
			}
		} catch (error) {
			// I am aware of how stupid this looks,
			// but without it, errors from Airtable's API don't surface properly;
			// you get a generic "UnhandledPromiseRejectionWarning" instead.
			throw new Error(String(error));
		}
		this.updateModel(this.record);
		this.clearDirtyFlags();
	}

	/** Fetches the latest data for the current Airtable record from the server, overwriting any unsaved local changes. */
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

	/** Deletes the current Airtable record from the server. */
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

	/**
	 * Initializes a model instance from an Airtable.js `Record<FieldSet>`.
	 * @param record - The Airtable record to initialize from.
	 * @param config - Optional config object. By default, config values (e.g. BaseID and APIKey)
	 * are picked up from environment variables. But if you are passing those values directly
	 * into the main class, you need to pass them here as well if you want to use functions
	 * like save() or fetch().
	 */
	public static fromRecord<T extends AirtableModel<any, any, any>>(
		this: new (...args: any[]) => T,
		record: ATRecord<any>,
		config?: AirtableOptions & { baseId: string },
		validate: boolean = true,
	): T {
		const instance = new this({ id: record.id });
		if (config) {
			const { baseId, ...options } = config;
			instance.setConfig(baseId, options);
		}
		instance.updateModel(record, validate);
		instance.clearDirtyFlags();
		return instance;
	}

	/**
	 * Creates a model instance from a record ID without fetching data.
	 * @param id - The Airtable record ID.
	 * @param config - Optional config object. By default, config values (e.g. BaseID and APIKey)
	 * are picked up from environment variables. But if you are passing those values directly
	 * into the main class, you need to pass them here as well if you want to use functions
	 * like save() or fetch().
	 */
	public static fromId<T extends AirtableModel<any, any, any>>(
		this: new (...args: any[]) => T,
		id: RecordId,
		config?: AirtableOptions & { baseId: string },
	): T {
		const instance = new this({ id });
		if (config) {
			const { baseId, ...options } = config;
			instance.setConfig(baseId, options);
		}
		return instance;
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
		const fields: Partial<FldSt> = {};
		for (const desc of this.getFieldDescriptors()) {
			if (desc.isComputed) continue;
			if (!this._isNew && !this.isDirty(desc.propertyName)) continue;
			const key = useFieldIds ? desc.fieldId : desc.fieldName;
			switch (desc.fieldType) {
				case "linkedRecord": {
					const rid = (this._fields[desc.propertyName] as any)?.id;
					(fields as any)[key] = rid ? [rid] : undefined;
					break;
				}
				case "linkedRecords":
					(fields as any)[key] = (this._fields[desc.propertyName] as any)?.ids;
					break;
				case "attachment":
					(fields as any)[key] = this.sanitizeAttachment(desc.propertyName);
					break;
				default:
					(fields as any)[key] = this._fields[desc.propertyName];
					break;
			}
		}
		return fields;
	}

	/** The attachment we get from Airtable has extra properties that its own API doesn't accept when saving, so we sanitize it before saving */
	protected sanitizeAttachment(fieldName: string): Attachment[] {
		const attachments = this._fields[fieldName] as Attachment[] | undefined;
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

	private _createLinkedField(desc: FieldDescriptor, value: unknown): LinkedRecord<any> | LinkedRecords<any> {
		if (desc.fieldType === "linkedRecord") {
			// Airtable API always returns arrays for link fields; unwrap to single ID
			const singleId = Array.isArray(value) ? value[0] : value;
			const lr = new LinkedRecord(
				singleId as RecordId,
				desc.linkedModelFromId!,
				() => this.markDirty(desc.propertyName),
				this.__configBaseId,
				this.__configOptions,
				desc.linkedModelClass,
			);
			return wrapLinkedRecordProxy(lr);
		} else {
			return new LinkedRecords(
				value as RecordId[],
				desc.linkedModelFromId!,
				() => this.markDirty(desc.propertyName),
				this.__configBaseId,
				this.__configOptions,
			);
		}
	}

	protected _setLinkedField(propertyName: string, value: unknown): void {
		const desc = this.getFieldDescriptors().find((d) => d.propertyName === propertyName);
		if (!desc) return;

		if (value instanceof LinkedRecord) {
			this._fields[propertyName] = value;
		} else if (value instanceof AirtableModel) {
			const lr = this._createLinkedField(desc, value.id);
			(lr as LinkedRecord<any>)._assign(value);
			this._fields[propertyName] = lr;
		} else if (typeof value === "string") {
			this._fields[propertyName] = this._createLinkedField(desc, value);
		} else if (value === undefined || value === null) {
			this._fields[propertyName] = this._createLinkedField(desc, undefined);
		} else {
			this._fields[propertyName] = value;
		}
		this.markDirty(propertyName);
	}

	protected _setLinkedRecordsField(propertyName: string, value: unknown): void {
		const desc = this.getFieldDescriptors().find((d) => d.propertyName === propertyName);
		if (!desc) return;

		if (value instanceof LinkedRecords) {
			this._fields[propertyName] = value;
		} else if (Array.isArray(value)) {
			if (value.length === 0) {
				this._fields[propertyName] = this._createLinkedField(desc, []);
			} else if (value[0] instanceof AirtableModel) {
				const ids = value.map((v: AirtableModel<any, any, any>) => v.id);
				const lr = this._createLinkedField(desc, ids) as LinkedRecords<any>;
				lr._assign(value);
				this._fields[propertyName] = lr;
			} else {
				this._fields[propertyName] = this._createLinkedField(desc, value);
			}
		} else if (value === undefined || value === null) {
			this._fields[propertyName] = this._createLinkedField(desc, undefined);
		} else {
			this._fields[propertyName] = value;
		}
		this.markDirty(propertyName);
	}

	protected initializeFields(data: Record<string, unknown>): void {
		for (const desc of this.getFieldDescriptors()) {
			const value = (data as any)[desc.propertyName];
			if ((desc.fieldType === "linkedRecord" || desc.fieldType === "linkedRecords") && !desc.isComputed) {
				this._fields[desc.propertyName] = this._createLinkedField(desc, value);
			} else {
				this._fields[desc.propertyName] = value;
			}
		}
	}

	protected updateModel(record: ATRecord<FldSt>, validate: boolean = true): void {
		this.record = record;
		this.id = record.id;
		for (const desc of this.getFieldDescriptors()) {
			const value = record.get(desc.fieldId as keyof FldSt) ?? record.get(desc.fieldName as keyof FldSt);
			if ((desc.fieldType === "linkedRecord" || desc.fieldType === "linkedRecords") && !desc.isComputed) {
				this._fields[desc.propertyName] = this._createLinkedField(desc, value);
			} else {
				this._fields[desc.propertyName] = value;
			}
		}
		if (validate) this.validate();
	}

	protected updateRecord(): void {
		if (!this.record)
			throw new Error(
				"Cannot convert to record: record is undefined. Please use fromRecord to initialize the instance.",
			);
		for (const desc of this.getFieldDescriptors()) {
			if ((desc.fieldType === "linkedRecord" || desc.fieldType === "linkedRecords") && !desc.isComputed) {
				if (desc.fieldType === "linkedRecord") {
					const rid = (this._fields[desc.propertyName] as any)?.id;
					//@ts-ignore
					this.record.set(desc.fieldId, rid ? [rid] : undefined);
				} else {
					//@ts-ignore
					this.record.set(desc.fieldId, (this._fields[desc.propertyName] as any)?.ids);
				}
			} else {
				//@ts-ignore
				this.record.set(desc.fieldId, this._fields[desc.propertyName]);
			}
		}
	}

	//#endregion
}

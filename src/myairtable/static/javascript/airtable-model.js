const { recordIdSchema } = require("./special-types");
const { getBaseId, getOptions } = require("./helpers");
const { LinkedRecord, LinkedRecords, wrapLinkedRecordProxy } = require("./linked-record");

class AirtableModel {
	// Base properties
	record;
	id;
	evaluateFormulasAtRuntime = false;

	// Mappings - must be defined by subclasses
	static nameToIdMap = {};
	static idToNameMap = {};
	static nameToPropertyMap = {};

	/** Zod schema for validation - must be defined by subclasses */
	static schema;

	/** Field descriptors - must be defined by subclasses */
	static fieldDescriptors = [];

	static getFieldDescriptor(propertyName) {
		return this.fieldDescriptors.find((d) => d.propertyName === propertyName);
	}

	// Field storage
	_fields = {};

	// Change tracking
	_dirtyFields = new Set();
	_isNew = true;

	// Per-instance config (using __ prefix to avoid conflicts with field names)
	__configBaseId;
	__configOptions;

	constructor(id) {
		this.id = id ? recordIdSchema.parse(id) : id;
	}

	getFieldDescriptors() {
		return this.constructor.fieldDescriptors;
	}

	//#region PUBLIC
	/** Get a value by Airtable field name */
	get(key) {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		if (!this.constructor.nameToPropertyMap[key]) throw new Error(`Field name "${key}" does not exist on this model.`);
		return this[this.constructor.nameToPropertyMap[key]];
	}

	/** Set a value by Airtable field name */
	set(key, value) {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		if (!this.constructor.nameToPropertyMap[key]) throw new Error(`Field name "${key}" does not exist on this model.`);
		this[this.constructor.nameToPropertyMap[key]] = value;
	}

	/** Returns true if any fields have been modified */
	hasChanges() {
		return this._dirtyFields.size > 0;
	}

	/** Returns an array of field names that have been modified */
	getChangedFields() {
		return Array.from(this._dirtyFields);
	}

	/**
	 * Validates the current model state against its Zod schema.
	 * @throws {z.ZodError} if validation fails
	 */
	validate() {
		const schema = this.constructor.schema;
		if (!schema) return; // No-op when schema not defined
		schema.parse(this.toJson());
	}

	/** Converts the model to a plain object. */
	toJson() {
		const result = {};
		result.id = this.id || undefined;
		for (const desc of this.getFieldDescriptors()) {
			if (desc.fieldType === "linkedRecord" && !desc.isComputed) {
				result[desc.propertyName] = this._fields[desc.propertyName]?.id;
			} else if (desc.fieldType === "linkedRecords" && !desc.isComputed) {
				result[desc.propertyName] = this._fields[desc.propertyName]?.ids;
			} else {
				result[desc.propertyName] = this._fields[desc.propertyName];
			}
		}
		return result;
	}

	/** Returns the model as a simple object, equivalent to the original Airtable JSON payload. */
	toIRecord(useFieldIds = false) {
		const r = this.toRecord(useFieldIds);
		return {
			id: r.id,
			fields: r.fields,
		};
	}

	/**
	 * Returns the model as Airtable.js's Record class
	 *
	 * @param useFieldIds - Default: `false`.
	 */
	toRecord(useFieldIds = false) {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		const r = { ...this.record };
		if (!useFieldIds) {
			r.fields = Object.fromEntries(
				Object.entries(r.fields).map(([key, value]) => {
					const name = this.constructor.idToNameMap[key] || key;
					return [name, value];
				}),
			);
		}
		return r;
	}

	toCreateRecordData(useFieldIds = true, asInsert = false) {
		return {
			fields: this.writableFields(useFieldIds, asInsert),
		};
	}

	toUpdateRecordData(useFieldIds = true) {
		if (!this.id) throw new Error("Cannot create update record data: id is undefined.");
		return {
			id: this.id,
			fields: this.writableFields(useFieldIds),
		};
	}

	/** Saves the current Airtable record to the server. */
	async save() {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.validate();

		try {
			if (this.id) {
				const updatedRecords = await this.record._table.update([this.toUpdateRecordData(true)]);
				this.record = updatedRecords[0];
			} else {
				const createdRecords = await this.record._table.create([this.toCreateRecordData(true)]);
				this.record = createdRecords[0];
			}
		} catch (error) {
			// I am aware of how stupid this looks,
			// but without it, errors from Airtable's API don't surface properly;
			// you get a generic "UnhandledPromiseRejectionWarning" instead.
			throw new Error(error);
		}
		this.updateModel(this.record);
		this.clearDirtyFlags();
	}

	/** Fetches the latest data for the current Airtable record from the server, overwriting any unsaved local changes. */
	async fetch() {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		try {
			this.record = await this.record.fetch();
		} catch (error) {
			// I am aware of how stupid this looks,
			// but without it, errors from Airtable's API don't surface properly;
			// you get a generic "UnhandledPromiseRejectionWarning" instead.
			throw new Error(error);
		}
		this.updateModel(this.record);
		this.clearDirtyFlags();
	}

	/** Deletes the current Airtable record from the server. */
	async delete() {
		if (!this.record)
			throw new Error("Cannot destroy record: _record is undefined. Please use fromRecord to initialize the instance.");
		try {
			await this.record.destroy();
		} catch (error) {
			// I am aware of how stupid this looks,
			// but without it, errors from Airtable's API don't surface properly;
			// you get a generic "UnhandledPromiseRejectionWarning" instead.
			throw new Error(error);
		}
		this.record = undefined;
		this.id = "";
	}

	/**
	 * Initializes a model instance from an Airtable.js Record.
	 * @param record - The Airtable record to initialize from.
	 * @param config - Optional config object. By default, config values (e.g. BaseID and APIKey)
	 * are picked up from environment variables. But if you are passing those values directly
	 * into the main class, you need to pass them here as well if you want to use functions
	 * like save() or fetch().
	 */
	static fromRecord(record, config, validate = true) {
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
	static fromId(id, config) {
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
	setConfig(baseId, options) {
		this.__configBaseId = baseId;
		this.__configOptions = options;
	}

	/** Gets the options for this instance, falling back to registry/env vars */
	getInstanceOptions() {
		if (this.__configOptions) return this.__configOptions;
		return getOptions(this.__configBaseId);
	}

	/** Gets the baseId for this instance, falling back to registry/env vars */
	getInstanceBaseId() {
		return this.__configBaseId ?? getBaseId();
	}

	/** Marks a field as dirty (modified) */
	markDirty(fieldName) {
		this._dirtyFields.add(fieldName);
	}

	/** Checks if a field has been modified */
	isDirty(fieldName) {
		return this._dirtyFields.has(fieldName);
	}

	/** Clears all dirty flags and marks the model as not new */
	clearDirtyFlags() {
		this._dirtyFields.clear();
		this._isNew = false;
	}

	writableFields(useFieldIds = true, asInsert = false) {
		const isInsert = this._isNew || asInsert;
		const fields = {};
		for (const desc of this.getFieldDescriptors()) {
			if (desc.isComputed) continue;
			if (!isInsert && !this.isDirty(desc.propertyName)) continue;
			const key = useFieldIds ? desc.fieldId : desc.fieldName;
			switch (desc.fieldType) {
				case "linkedRecord": {
					const rid = this._fields[desc.propertyName]?.id;
					fields[key] = rid ? [rid] : undefined;
					break;
				}
				case "linkedRecords":
					fields[key] = this._fields[desc.propertyName]?.ids;
					break;
				case "attachment":
					fields[key] = this.sanitizeAttachment(desc.propertyName, isInsert);
					break;
				default:
					fields[key] = this._fields[desc.propertyName];
					break;
			}
			// On update, an included field is dirty; a nullish value is an explicit clear and must
			// serialize as JSON null (undefined keys are dropped by JSON.stringify, leaving the cell
			// unchanged). On create, undefined is left to be dropped (sparse write).
			if (!isInsert && fields[key] == null) fields[key] = null;
		}
		return fields;
	}

	/**
	 * Airtable returns attachments with read-only metadata (`size`, `type`, `width`, `height`,
	 * `thumbnails`) that its own API rejects on write, and create and update do NOT accept the
	 * same shapes — verified against the live API:
	 *
	 * - **create** is a strict whitelist: only `{url}` / `{url, filename}` is accepted. Sending
	 *   `id` — alone, echoed back with `url`, or as `{id,url,filename,size,type}` — fails with
	 *   `INVALID_ATTACHMENT_OBJECT`. Airtable re-ingests the file and mints a fresh attachment id.
	 * - **update** accepts `id`, and it means *retain this attachment*. Re-sending `{url}` on an
	 *   update would instead re-download the file and replace the id, so `id` must be preserved
	 *   here or existing attachments churn on every save.
	 *
	 * Hence `forCreate`: project to `{url, filename}` when inserting, keep `{id}` when updating an
	 * attachment that already has one.
	 * @param {string} fieldName
	 * @param {boolean} forCreate
	 */
	sanitizeAttachment(fieldName, forCreate) {
		const attachments = this._fields[fieldName];
		if (!attachments || !Array.isArray(attachments)) return [];
		return attachments.map((attachment) => {
			// Retain an existing attachment on update; Airtable rejects `id` on create.
			if (!forCreate && attachment.id) return { id: attachment.id };
			const writable = { url: attachment.url };
			if (attachment.filename) writable.filename = attachment.filename;
			return writable;
		});
	}

	_createLinkedField(desc, value) {
		if (desc.fieldType === "linkedRecord") {
			// Airtable API always returns arrays for link fields; unwrap to single ID
			const singleId = Array.isArray(value) ? value[0] : value;
			const lr = new LinkedRecord(
				singleId,
				desc.linkedModelFromId,
				() => this.markDirty(desc.propertyName),
				this.__configBaseId,
				this.__configOptions,
				desc.linkedModelClass,
			);
			return wrapLinkedRecordProxy(lr);
		} else {
			return new LinkedRecords(
				value,
				desc.linkedModelFromId,
				() => this.markDirty(desc.propertyName),
				this.__configBaseId,
				this.__configOptions,
			);
		}
	}

	_setLinkedField(propertyName, value) {
		const desc = this.getFieldDescriptors().find((d) => d.propertyName === propertyName);
		if (!desc) return;

		if (value instanceof LinkedRecord) {
			this._fields[propertyName] = value;
		} else if (value instanceof AirtableModel) {
			const lr = this._createLinkedField(desc, value.id);
			lr._assign(value);
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

	_setLinkedRecordsField(propertyName, value) {
		const desc = this.getFieldDescriptors().find((d) => d.propertyName === propertyName);
		if (!desc) return;

		if (value instanceof LinkedRecords) {
			this._fields[propertyName] = value;
		} else if (Array.isArray(value)) {
			if (value.length === 0) {
				this._fields[propertyName] = this._createLinkedField(desc, []);
			} else if (value[0] instanceof AirtableModel) {
				const ids = value.map((v) => v.id);
				const lr = this._createLinkedField(desc, ids);
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

	initializeFields(data) {
		for (const desc of this.getFieldDescriptors()) {
			const value = data[desc.propertyName];
			if ((desc.fieldType === "linkedRecord" || desc.fieldType === "linkedRecords") && !desc.isComputed) {
				this._fields[desc.propertyName] = this._createLinkedField(desc, value);
			} else {
				this._fields[desc.propertyName] = value;
			}
		}
	}

	updateModel(record, validate = true) {
		this.record = record;
		this.id = record.id;
		for (const desc of this.getFieldDescriptors()) {
			const value = record.get(desc.fieldId) ?? record.get(desc.fieldName);
			if ((desc.fieldType === "linkedRecord" || desc.fieldType === "linkedRecords") && !desc.isComputed) {
				this._fields[desc.propertyName] = this._createLinkedField(desc, value);
			} else {
				this._fields[desc.propertyName] = value;
			}
		}
		if (validate) this.validate();
	}

	updateRecord() {
		if (!this.record)
			throw new Error(
				"Cannot convert to record: record is undefined. Please use fromRecord to initialize the instance.",
			);
		for (const desc of this.getFieldDescriptors()) {
			if ((desc.fieldType === "linkedRecord" || desc.fieldType === "linkedRecords") && !desc.isComputed) {
				if (desc.fieldType === "linkedRecord") {
					const rid = this._fields[desc.propertyName]?.id;
					this.record.set(desc.fieldId, rid ? [rid] : undefined);
				} else {
					this.record.set(desc.fieldId, this._fields[desc.propertyName]?.ids);
				}
			} else {
				this.record.set(desc.fieldId, this._fields[desc.propertyName]);
			}
		}
	}

	//#endregion
}

module.exports = { AirtableModel };

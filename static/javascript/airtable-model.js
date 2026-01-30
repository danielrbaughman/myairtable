const { recordIdSchema } = require("./special-types");
const { getBaseId, getOptions } = require("./helpers");

class AirtableModel {
	// Base properties
	record;
	id;

	// Mappings - must be defined by subclasses
	nameToIdMap = {};
	idToNameMap = {};
	nameToPropertyMap = {};

	/** Zod schema for validation - must be defined by subclasses */
	static schema;

	// Change tracking
	_dirtyFields = new Set();
	_isNew = true;

	// Per-instance config (using __ prefix to avoid conflicts with field names)
	__configBaseId;
	__configOptions;

	constructor(id) {
		this.id = id ? recordIdSchema.parse(id) : id;
	}

	//#region PUBLIC
	/** Get a value by Airtable field name */
	get(key) {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		if (!this.nameToPropertyMap[key]) throw new Error(`Field name "${key}" does not exist on this model.`);
		return this[this.nameToPropertyMap[key]];
	}

	/** Set a value by Airtable field name */
	set(key, value) {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		if (!this.nameToPropertyMap[key]) throw new Error(`Field name "${key}" does not exist on this model.`);
		this[this.nameToPropertyMap[key]] = value;
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
		throw new Error("toJson must be implemented by subclass");
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
					const name = this.idToNameMap[key] || key;
					return [name, value];
				}),
			);
		}
		return r;
	}

	toCreateRecordData(useFieldIds = true) {
		return {
			fields: this.writableFields(useFieldIds),
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

	writableFields(useFieldIds = true) {
		return {};
		// To be overridden by subclasses
	}

	/** The attachment we get from Airtable has extra properties that its own API doesn't accept when saving, so we sanitize it before saving */
	sanitizeAttachment(fieldName) {
		const attachments = this[fieldName];
		const writableAttachments = [];
		if (attachments && Array.isArray(attachments)) {
			for (const attachment of attachments) {
				const writableAttachment = {
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

	updateModel(record) {
		this.record = record;
		// To be overridden by subclasses
	}

	updateRecord() {
		// To be overridden by subclasses
	}

	//#endregion
}

module.exports = { AirtableModel };

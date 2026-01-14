const { recordIdSchema } = require("./special-types");

class AirtableModel {
	/** Zod schema for validation - must be defined by subclasses */
	static schema;

	record;
	id;

	constructor(id) {
		this.id = id ? recordIdSchema.parse(id) : id;
	}

	/**
	 * Validates the current model state against its Zod schema.
	 * No-op if schema is not defined (when generated with --no-zod).
	 * @throws {z.ZodError} if validation fails
	 */
	validate() {
		const schema = this.constructor.schema;
		if (!schema) return; // No-op when schema not defined
		schema.parse(this.toJson());
	}

	/**
	 * Converts the model to a plain object.
	 * Must be implemented by subclasses to return all field values.
	 */
	toJson() {
		throw new Error("toJson must be implemented by subclass");
	}

	writableFields(useFieldIds = false) {
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

	toRecord() {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		return this.record;
	}

	toRecordData() {
		return {
			id: this.id,
			fields: this.toRecord().fields,
		};
	}

	toCreateRecordData(useFieldIds = true) {
		return {
			fields: this.writableFields(useFieldIds),
		};
	}

	toUpdateRecordData(useFieldIds = false) {
		return {
			id: this.id,
			fields: this.writableFields(useFieldIds),
		};
	}

	/**
	 * Saves the current Airtable record to the server.
	 * @throws {z.ZodError} if validation fails before save
	 */
	async save() {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.validate();
		this.updateRecord();
		this.record.fields = this.writableFields();
		this.record = await this.record.save();
		this.updateModel(this.record);
	}

	/**
	 * Fetches the latest data for the current Airtable record from the server, overwriting any unsaved local changes.
	 */
	async fetch() {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		this.record = await this.record.fetch();
		this.updateModel(this.record);
	}

	/**
	 * Deletes the current Airtable record to the server.
	 */
	async delete() {
		if (!this.record)
			throw new Error("Cannot destroy record: _record is undefined. Please use fromRecord to initialize the instance.");
		await this.record.destroy();
		this.record = undefined;
		this.id = "";
	}
}

module.exports = { AirtableModel };

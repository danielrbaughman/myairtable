const { recordIdSchema } = require("./special-types");

/**
 * A reference to a linked Airtable record, providing methods to get and set the linked record.
 */
class LinkedRecord {
	/** The ID of the linked record. This is the value Airtable actually stores in the linked record field. */
	id;
	record;
	modelCtor;

	constructor(recordId, modelCtor) {
		this.id = recordIdSchema.optional().parse(recordId);
		this.modelCtor = modelCtor;
	}

	/**
	 * Retrieves the linked record. Caches the result for future calls.
	 *
	 * @param fetch - If `true`, forces a fetch of the record data even if it is already loaded. Defaults to `false`.
	 */
	async get(fetch = false) {
		if (this.record === undefined || fetch) {
			this.record = this.modelCtor(this.id);
			await this.record.fetch();
		}
		return this.record;
	}

	/**
	 * Sets the linked record value and updates the associated ID.
	 *
	 * @param value - The new record to link. If `undefined` or falsy, clears the current record and ID.
	 */
	set(value) {
		if (!value) {
			this.record = undefined;
			this.id = undefined;
		} else {
			this.record = value;
			this.id = value.id;
		}
	}
}

/**
 * A reference to linked Airtable records, providing methods to get and set the linked records.
 */
class LinkedRecords {
	/** The IDs of the linked records. These are the values Airtable actually stores in the linked record field. */
	ids;
	records;
	modelCtor;

	constructor(recordIds, modelCtor) {
		this.ids = recordIds?.map((id) => recordIdSchema.parse(id));
		this.modelCtor = modelCtor;
	}

	/**
	 * Retrieves the linked records. Caches the result for future calls.
	 *
	 * @param fetch - If `true`, forces a fresh fetch of the records even if they are already loaded. Defaults to `false`.
	 */
	async get(fetch = false) {
		if (this.records === undefined || fetch) {
			this.records = this.ids?.map((id) => this.modelCtor(id)) ?? [];
			await Promise.all(this.records.map((record) => record.fetch()));
		}
		return this.records;
	}

	/**
	 * Sets the linked record values and updates the associated IDs.
	 *
	 * @param values - The new records to link. If `undefined` or falsy, clears the current records and IDs.
	 */
	set(values) {
		if (!values || values.length === 0) {
			this.records = undefined;
			this.ids = undefined;
		} else {
			this.records = values;
			this.ids = values.map((value) => value.id);
		}
	}
}

module.exports = { LinkedRecord, LinkedRecords };

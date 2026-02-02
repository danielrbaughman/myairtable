const { recordIdSchema } = require("./special-types");

/**
 * A reference to a linked Airtable record, providing methods to get and set the linked record.
 */
class LinkedRecord {
	/** The ID of the linked record. This is the value Airtable actually stores in the linked record field. */
	_id;
	record;
	modelCtor;
	onDirty;
	__configBaseId;
	__configOptions;

	constructor(recordId, modelCtor, onDirty, baseId, options) {
		this._id = recordIdSchema.optional().parse(recordId);
		this.modelCtor = modelCtor;
		this.onDirty = onDirty;
		this.__configBaseId = baseId;
		this.__configOptions = options;
	}

	get id() {
		return this._id;
	}
	set id(value) {
		this._id = value;
		this.onDirty?.();
	}

	/**
	 * Retrieves the linked record. Caches the result for future calls.
	 *
	 * @param fetch - If `true`, forces a fetch of the record data even if it is already loaded. Defaults to `false`.
	 */
	async get(fetch = false) {
		if (this.record === undefined || fetch) {
			const config = this.__configBaseId ? { baseId: this.__configBaseId, ...this.__configOptions } : undefined;
			this.record = this.modelCtor(this._id, config);
			await this.record.fetch();
		}
		return this.record;
	}

	/**
	 * Sets the linked record value and updates the associated ID.
	 *
	 * @param value - The new record to link.
	 */
	set(value) {
		if (!value) {
			this.record = undefined;
			this._id = undefined;
		} else {
			this.record = value;
			this._id = value.id;
		}
		this.onDirty?.();
	}
}

/**
 * A reference to linked Airtable records, providing methods to get and set the linked records.
 */
class LinkedRecords {
	/** The IDs of the linked records. These are the values Airtable actually stores in the linked record field. */
	_ids;
	records;
	modelCtor;
	onDirty;
	__configBaseId;
	__configOptions;

	constructor(recordIds, modelCtor, onDirty, baseId, options) {
		this._ids = recordIds?.map((id) => recordIdSchema.parse(id));
		this.modelCtor = modelCtor;
		this.onDirty = onDirty;
		this.__configBaseId = baseId;
		this.__configOptions = options;
	}

	get ids() {
		return this._ids;
	}
	set ids(value) {
		this._ids = value;
		this.onDirty?.();
	}

	/**
	 * Retrieves the linked records. Caches the result for future calls.
	 *
	 * @param fetch - If `true`, forces a fresh fetch of the records even if they are already loaded. Defaults to `false`.
	 */
	async get(fetch = false) {
		if (this.records === undefined || fetch) {
			const config = this.__configBaseId ? { baseId: this.__configBaseId, ...this.__configOptions } : undefined;
			this.records = this._ids?.map((id) => this.modelCtor(id, config)) ?? [];
			await Promise.all(this.records.map((record) => record.fetch()));
		}
		return this.records;
	}

	/**
	 * Sets the linked record values and updates the associated IDs.
	 *
	 * @param values - The new records to link.
	 */
	set(values) {
		if (!values || values.length === 0) {
			this.records = undefined;
			this._ids = undefined;
		} else {
			this.records = values;
			this._ids = values.map((value) => value.id);
		}
		this.onDirty?.();
	}

	/**
	 * Adds a linked record value and updates the associated ID.
	 *
	 * @param value - The new record to link.
	 */
	add(value) {
		if (!this.records) this.records = [];
		if (!this._ids) this._ids = [];
		this.records.push(value);
		this._ids.push(value.id);
		this.onDirty?.();
	}
}

module.exports = { LinkedRecord, LinkedRecords };

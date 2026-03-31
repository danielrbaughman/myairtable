const { recordIdSchema } = require("./special-types");

// Properties that should pass through the Proxy without interception
const PASSTHROUGH_PROPS = new Set([
	"id",
	"get",
	"set",
	"then",
	"_id",
	"record",
	"modelCtor",
	"onDirty",
	"__configBaseId",
	"__configOptions",
	"linkedModelClass",
	"constructor",
	"prototype",
	"toJSON",
	"valueOf",
	"toString",
]);

/**
 * A reference to a linked Airtable record, providing methods to get and set the linked record.
 * Supports implicit thenable syntax: `await job.deal` fetches the linked record.
 * Supports chaining: `await job.deal.companies` fetches the deal, then its companies.
 */
class LinkedRecord {
	/** The ID of the linked record. This is the value Airtable actually stores in the linked record field. */
	_id;
	record;
	modelCtor;
	onDirty;
	__configBaseId;
	__configOptions;
	linkedModelClass;

	constructor(recordId, modelCtor, onDirty, baseId, options, linkedModelClass) {
		this._id = recordIdSchema.optional().parse(recordId);
		this.modelCtor = modelCtor;
		this.onDirty = onDirty;
		this.__configBaseId = baseId;
		this.__configOptions = options;
		this.linkedModelClass = linkedModelClass;
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
		if (!this._id) return undefined;
		if (this.record === undefined || fetch) {
			const config = this.__configBaseId ? { baseId: this.__configBaseId, ...this.__configOptions } : undefined;
			this.record = this.modelCtor(this._id, config);
			await this.record.fetch();
		}
		return this.record;
	}

	/**
	 * Makes LinkedRecord thenable: `await linkedRecord` calls `.get()`.
	 */
	then(onfulfilled, onrejected) {
		return this.get().then(onfulfilled, onrejected);
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
 * Supports implicit thenable syntax: `await linkedRecords` calls `.get()`.
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
	 * Makes LinkedRecords thenable: `await linkedRecords` calls `.get()`.
	 */
	then(onfulfilled, onrejected) {
		return this.get().then(onfulfilled, onrejected);
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

/**
 * Wraps a LinkedRecord in a Proxy that intercepts property access for chaining.
 */
function wrapLinkedRecordProxy(lr) {
	const modelClass = lr.linkedModelClass;
	if (!modelClass) return lr;

	return new Proxy(lr, {
		get(target, prop, receiver) {
			if (typeof prop === "symbol" || PASSTHROUGH_PROPS.has(prop)) {
				return Reflect.get(target, prop, receiver);
			}

			const desc = modelClass.getFieldDescriptor?.(prop);
			if (desc && (desc.fieldType === "linkedRecord" || desc.fieldType === "linkedRecords")) {
				return createChainLink(() => target.get(), prop, desc);
			}

			return Reflect.get(target, prop, receiver);
		},
	});
}

/**
 * Creates a thenable chain link that resolves the parent, accesses a field, and resolves that too.
 */
function createChainLink(parentResolver, fieldName, desc) {
	const resolution = parentResolver().then(async (parentModel) => {
		if (!parentModel) {
			return desc.fieldType === "linkedRecords" ? [] : undefined;
		}
		const field = parentModel[fieldName];
		if (!field) {
			return desc.fieldType === "linkedRecords" ? [] : undefined;
		}
		if (field instanceof LinkedRecord || field instanceof LinkedRecords) {
			return field.get();
		}
		return field;
	});

	if (desc.fieldType === "linkedRecord" && desc.linkedModelClass) {
		return createChainablePromise(resolution, desc.linkedModelClass);
	}
	return resolution;
}

/**
 * Wraps a Promise in a Proxy that allows further chaining through linked fields.
 */
function createChainablePromise(promise, modelClass) {
	return new Proxy(promise, {
		get(target, prop, receiver) {
			if (prop === "then" || prop === "catch" || prop === "finally" || typeof prop === "symbol") {
				return Reflect.get(target, prop, receiver);
			}

			const desc = modelClass.getFieldDescriptor?.(prop);
			if (desc && (desc.fieldType === "linkedRecord" || desc.fieldType === "linkedRecords")) {
				const nextPromise = target.then(async (model) => {
					if (!model) {
						return desc.fieldType === "linkedRecords" ? [] : undefined;
					}
					const field = model[prop];
					if (!field) {
						return desc.fieldType === "linkedRecords" ? [] : undefined;
					}
					if (field instanceof LinkedRecord || field instanceof LinkedRecords) {
						return field.get();
					}
					return field;
				});

				if (desc.fieldType === "linkedRecord" && desc.linkedModelClass) {
					return createChainablePromise(nextPromise, desc.linkedModelClass);
				}
				return nextPromise;
			}

			return Reflect.get(target, prop, receiver);
		},
	});
}

module.exports = { LinkedRecord, LinkedRecords, wrapLinkedRecordProxy };

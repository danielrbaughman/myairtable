const Airtable = require("airtable");
const { AirtableModel } = require("./airtable-model");
const { ID } = require("./formula");
const { baseIdSchema, validateRecordIds } = require("./special-types");
const { buildUrl } = require("./helpers");

class AirtableTable {
	/** Underlying Airtable.js Table instance */
	_table;
	id;
	/** Base ID */
	baseId;
	_options = {};
	cacheSeconds = 0;
	_cache = new Map();

	recordCtor;
	viewNameToIdMap = {};
	fieldNameToIdMap = {};
	fieldIdToNameMap = {};
	writableFieldIds = [];

	constructor(
		baseId,
		tableNameOrId,
		viewNameToIdMap,
		fieldNameToIdMap,
		fieldIdToNameMap,
		writableFieldIds,
		recordCtor,
		options = {},
	) {
		this.baseId = baseIdSchema.parse(baseId);
		this._options = options;
		this._table = new Airtable(options).base(this.baseId).table(tableNameOrId);
		this.id = tableNameOrId;
		this.recordCtor = recordCtor;
		this.viewNameToIdMap = viewNameToIdMap;
		this.fieldNameToIdMap = fieldNameToIdMap;
		this.fieldIdToNameMap = fieldIdToNameMap;
		this.writableFieldIds = writableFieldIds;
		this.cacheSeconds = options?.cacheSeconds ?? 0;
	}

	/** Get view ID by name */
	getViewId(viewName) {
		return this.viewNameToIdMap[viewName] || viewName;
	}

	/** Gets the Airtable web URL for this table, optionally for a specific view. */
	url(view) {
		if (view) {
			return buildUrl(this.baseId, this.id, this.getViewId(view));
		} else {
			return buildUrl(this.baseId, this.id);
		}
	}

	//#region GET

	/**
	 * Get record(s) by ID, IDs, or query options.
	 * @param {string|string[]|object} recordIdOrIdsOrOptions - Single ID, array of IDs, or query options
	 * @param options - Query options
	 *
	 * Options:
	 *   - `fields` — Restrict which fields are returned (by name).
	 *   - `useFieldIds` — When true, field keys are IDs (`fldXXX`) instead of names. Defaults to true when returning models; false otherwise.
	 *   - `returnAs` — Determines the return format: `model`, `record`, or `interface`. Default: `model`.
	 *   - `pageSize` — Records per API page (1–100, default 100).
	 *   - `maxRecords` — Cap the total number of records returned.
	 *   - `onlyWritableFields` — Return only writable fields from the API. Intended for use in making Airtable.js's `.save()` method work correctly.
	 */
	async get(recordIdOrIdsOrOptions, options) {
		// Cache check
		const cacheKey = this.cacheSeconds > 0 ? JSON.stringify([recordIdOrIdsOrOptions, options]) : "";
		if (this.cacheSeconds > 0) {
			const hit = this._cache.get(cacheKey);
			if (hit && Date.now() < hit.expiresAt) return hit.value;
		}

		let result;

		// Single record by ID
		if (typeof recordIdOrIdsOrOptions === "string") {
			validateRecordIds(recordIdOrIdsOrOptions);
			const returnAs = options?.returnAs ?? "model";
			const selectOptions = {
				filterByFormula: new ID().equals(recordIdOrIdsOrOptions),
			};
			if (options?.fields) {
				selectOptions.fields = options.fields;
			} else if (options?.onlyWritableFields && returnAs !== "model") {
				selectOptions.fields = this.writableFieldIds;
			}
			if (options?.pageSize) selectOptions.pageSize = options.pageSize;
			if (options?.offset) selectOptions.offset = options.offset;
			if (options?.timeZone) selectOptions.timeZone = options.timeZone;
			if (options?.userLocale) selectOptions.userLocale = options.userLocale;
			selectOptions.returnFieldsByFieldId = options?.useFieldIds ?? returnAs === "model";

			try {
				const records = await this._table.select(selectOptions).all();
				if (records.length === 0) {
					throw new Error(`Record ${recordIdOrIdsOrOptions} not found`);
				}
				result = this.convertGetResult(records[0], returnAs);
			} catch (error) {
				throw new Error(String(error));
			}
		}

		// Multiple records by IDs
		else if (Array.isArray(recordIdOrIdsOrOptions)) {
			validateRecordIds(recordIdOrIdsOrOptions);
			if (recordIdOrIdsOrOptions.length === 0) {
				return [];
			}
			const returnAs = options?.returnAs ?? "model";
			const selectOptions = {
				filterByFormula: new ID().inList(recordIdOrIdsOrOptions),
			};
			if (options?.fields) {
				selectOptions.fields = options.fields;
			} else if (options?.onlyWritableFields && returnAs !== "model") {
				selectOptions.fields = this.writableFieldIds;
			}
			if (options?.sort) selectOptions.sort = options.sort;
			if (options?.pageSize) selectOptions.pageSize = options.pageSize;
			if (options?.maxRecords) selectOptions.maxRecords = options.maxRecords;
			if (options?.offset) selectOptions.offset = options.offset;
			if (options?.timeZone) selectOptions.timeZone = options.timeZone;
			if (options?.userLocale) selectOptions.userLocale = options.userLocale;
			selectOptions.returnFieldsByFieldId = options?.useFieldIds ?? returnAs === "model";

			try {
				const records = await this._table.select(selectOptions).all();
				result = this.convertGetResults([...records], returnAs);
			} catch (error) {
				throw new Error(String(error));
			}
		}

		// Query with options (first parameter is options object)
		else {
			const queryOptions = recordIdOrIdsOrOptions || {};
			const returnAs = queryOptions.returnAs ?? "model";
			const selectOptions = {};
			if (queryOptions.fields) {
				selectOptions.fields = queryOptions.fields;
			} else if (queryOptions.onlyWritableFields && returnAs !== "model") {
				selectOptions.fields = this.writableFieldIds;
			}
			if (queryOptions.view) selectOptions.view = this.getViewId(queryOptions.view);
			if (queryOptions.formula) selectOptions.filterByFormula = queryOptions.formula;
			if (queryOptions.sort) selectOptions.sort = queryOptions.sort;
			if (queryOptions.pageSize) selectOptions.pageSize = queryOptions.pageSize;
			if (queryOptions.maxRecords) selectOptions.maxRecords = queryOptions.maxRecords;
			if (queryOptions.offset) selectOptions.offset = queryOptions.offset;
			if (queryOptions.timeZone) selectOptions.timeZone = queryOptions.timeZone;
			if (queryOptions.userLocale) selectOptions.userLocale = queryOptions.userLocale;
			selectOptions.returnFieldsByFieldId = queryOptions.useFieldIds ?? returnAs === "model";

			try {
				const records = await this._table.select(selectOptions).all();
				result = this.convertGetResults([...records], returnAs);
			} catch (error) {
				throw new Error(String(error));
			}
		}

		// Cache store
		if (this.cacheSeconds > 0) {
			this._cache.set(cacheKey, { value: result, expiresAt: Date.now() + this.cacheSeconds * 1000 });
		}
		return result;
	}

	//#endregion

	//#region CREATE

	/**
	 * Create record(s).
	 * @param {object|object[]} recordOrRecords - Single record or array of records
	 */
	async create(recordOrRecords) {
		this.invalidateCache();
		const isArray = Array.isArray(recordOrRecords);
		if (isArray && recordOrRecords.length === 0) return [];
		const firstItem = isArray ? recordOrRecords[0] : recordOrRecords;
		const inputType = this.detectInputType(firstItem);

		if (isArray) {
			const items = recordOrRecords;
			const createdRecords = [];

			if (inputType === "model") {
				const payloads = items.map((r) => r.toCreateRecordData());
				for (let i = 0; i < payloads.length; i += 10) {
					const batch = payloads.slice(i, i + 10);
					try {
						const batchCreated = await this._table.create(batch);
						createdRecords.push(...batchCreated);
					} catch (error) {
						// I am aware of how stupid this looks,
						// but without it, errors from Airtable's API don't surface properly;
						// you get a generic "UnhandledPromiseRejectionWarning" instead.
						throw new Error(String(error));
					}
				}
				return createdRecords.map((r) => this.recordCtor(r));
			} else {
				const records = this.mapToIds(items);
				const isUsingFieldNames = this.isUsingFieldNames(records);
				for (let i = 0; i < records.length; i += 10) {
					const batch = records.slice(i, i + 10);
					try {
						const batchCreated = await this._table.create(batch.map((r) => this.toWritableRecord(r)));
						createdRecords.push(...batchCreated);
					} catch (error) {
						// I am aware of how stupid this looks,
						// but without it, errors from Airtable's API don't surface properly;
						// you get a generic "UnhandledPromiseRejectionWarning" instead.
						throw new Error(String(error));
					}
				}
				if (isUsingFieldNames) this.mapToNames(createdRecords);
				return inputType === "interface" ? createdRecords.map((r) => this.toInterface(r)) : createdRecords;
			}
		} else {
			if (inputType === "model") {
				const payload = recordOrRecords.toCreateRecordData();
				try {
					const createdRecords = await this._table.create([payload]);
					return this.recordCtor(createdRecords[0]);
				} catch (error) {
					// I am aware of how stupid this looks,
					// but without it, errors from Airtable's API don't surface properly;
					// you get a generic "UnhandledPromiseRejectionWarning" instead.
					throw new Error(String(error));
				}
			} else {
				const record = this.mapToIds([recordOrRecords])[0];
				const isUsingFieldNames = this.isUsingFieldNames([record]);
				try {
					const createdRecords = await this._table.create([this.toWritableRecord(record)]);
					if (isUsingFieldNames) this.mapToNames(createdRecords);
					const created = createdRecords[0];
					return inputType === "interface" ? this.toInterface(created) : created;
				} catch (error) {
					// I am aware of how stupid this looks,
					// but without it, errors from Airtable's API don't surface properly;
					// you get a generic "UnhandledPromiseRejectionWarning" instead.
					throw new Error(String(error));
				}
			}
		}
	}

	//#endregion

	//#region UPDATE

	/**
	 * Update record(s).
	 * @param {object|object[]} recordOrRecords - Single record or array of records
	 */
	async update(recordOrRecords) {
		this.invalidateCache();
		const isArray = Array.isArray(recordOrRecords);
		if (isArray && recordOrRecords.length === 0) return [];
		const firstItem = isArray ? recordOrRecords[0] : recordOrRecords;
		const inputType = this.detectInputType(firstItem);

		if (isArray) {
			const items = recordOrRecords;
			const updatedRecords = [];

			if (inputType === "model") {
				const payloads = items.map((r) => r.toUpdateRecordData());
				for (let i = 0; i < payloads.length; i += 10) {
					const batch = payloads.slice(i, i + 10);
					try {
						const batchUpdated = await this._table.update(batch);
						updatedRecords.push(...batchUpdated);
					} catch (error) {
						// I am aware of how stupid this looks,
						// but without it, errors from Airtable's API don't surface properly;
						// you get a generic "UnhandledPromiseRejectionWarning" instead.
						throw new Error(String(error));
					}
				}
				return updatedRecords.map((r) => this.recordCtor(r));
			} else {
				const records = this.mapToIds(items);
				const isUsingFieldNames = this.isUsingFieldNames(records);
				for (let i = 0; i < records.length; i += 10) {
					const batch = records.slice(i, i + 10);
					try {
						const batchUpdated = await this._table.update(batch.map((r) => this.toWritableRecord(r)));
						updatedRecords.push(...batchUpdated);
					} catch (error) {
						// I am aware of how stupid this looks,
						// but without it, errors from Airtable's API don't surface properly;
						// you get a generic "UnhandledPromiseRejectionWarning" instead.
						throw new Error(String(error));
					}
				}
				if (isUsingFieldNames) this.mapToNames(updatedRecords);
				return inputType === "interface" ? updatedRecords.map((r) => this.toInterface(r)) : updatedRecords;
			}
		} else {
			if (inputType === "model") {
				const payload = recordOrRecords.toUpdateRecordData();
				try {
					const updatedRecords = await this._table.update([payload]);
					return this.recordCtor(updatedRecords[0]);
				} catch (error) {
					// I am aware of how stupid this looks,
					// but without it, errors from Airtable's API don't surface properly;
					// you get a generic "UnhandledPromiseRejectionWarning" instead.
					throw new Error(String(error));
				}
			} else {
				const record = this.mapToIds([recordOrRecords])[0];
				const isUsingFieldNames = this.isUsingFieldNames([record]);
				try {
					const updatedRecords = await this._table.update([this.toWritableRecord(record)]);
					if (isUsingFieldNames) this.mapToNames(updatedRecords);
					const updated = updatedRecords[0];
					return inputType === "interface" ? this.toInterface(updated) : updated;
				} catch (error) {
					// I am aware of how stupid this looks,
					// but without it, errors from Airtable's API don't surface properly;
					// you get a generic "UnhandledPromiseRejectionWarning" instead.
					throw new Error(String(error));
				}
			}
		}
	}

	//#endregion

	//#region UPSERT

	/**
	 * Upsert record(s) - creates if doesn't exist, updates if exists.
	 * @param {object|object[]} recordOrRecords - Single record or array of records
	 */
	async upsert(recordOrRecords) {
		this.invalidateCache();
		const isArray = Array.isArray(recordOrRecords);
		if (isArray && recordOrRecords.length === 0) return [];
		const firstItem = isArray ? recordOrRecords[0] : recordOrRecords;
		const inputType = this.detectInputType(firstItem);
		const records = isArray ? recordOrRecords : [recordOrRecords];

		// Batch fetch all records to check which exist
		const recordIds = records.map((r) => r.id).filter((id) => !!id);
		const existingRecords = recordIds.length > 0 ? await this.get(recordIds) : [];
		const existingIds = new Set(existingRecords.map((r) => r.id));

		// Separate into updates and creates
		const toUpdate = [];
		const toCreate = [];
		for (const record of records) {
			if (record.id && existingIds.has(record.id)) {
				toUpdate.push(record);
			} else {
				toCreate.push(record);
			}
		}

		// Batch update and create
		const [updatedRecords, createdRecords] = await Promise.all([
			toUpdate.length > 0 ? this.update(toUpdate) : Promise.resolve([]),
			toCreate.length > 0 ? this.create(toCreate) : Promise.resolve([]),
		]);
		const upsertedRecords = [
			...(Array.isArray(updatedRecords) ? updatedRecords : [updatedRecords]),
			...(Array.isArray(createdRecords) ? createdRecords : [createdRecords]),
		];

		if (inputType === "interface") {
			const asInterfaces = upsertedRecords.map((r) => (this.isATRecord(r) ? this.toInterface(r) : r));
			return isArray ? asInterfaces : asInterfaces[0];
		}
		return isArray ? upsertedRecords : upsertedRecords[0];
	}

	//#endregion

	//#region DELETE

	/**
	 * Delete record(s) by ID.
	 * @param {string|string[]} recordIdOrIds - Single ID or array of IDs
	 */
	async delete(recordIdOrIds) {
		this.invalidateCache();
		if (Array.isArray(recordIdOrIds)) {
			validateRecordIds(recordIdOrIds);
			// Delete in batches of 10 (Airtable API limit)
			for (let i = 0; i < recordIdOrIds.length; i += 10) {
				const batch = recordIdOrIds.slice(i, i + 10);
				try {
					await this._table.destroy(batch);
				} catch (error) {
					// I am aware of how stupid this looks,
					// but without it, errors from Airtable's API don't surface properly;
					// you get a generic "UnhandledPromiseRejectionWarning" instead.
					throw new Error(String(error));
				}
			}
		} else {
			validateRecordIds(recordIdOrIds);
			try {
				await this._table.destroy([recordIdOrIds]);
			} catch (error) {
				// I am aware of how stupid this looks,
				// but without it, errors from Airtable's API don't surface properly;
				// you get a generic "UnhandledPromiseRejectionWarning" instead.
				throw new Error(String(error));
			}
		}
	}

	//#endregion

	//#region HELPERS

	/** Clears the cache for this table. */
	invalidateCache() {
		this._cache.clear();
	}

	/** Convert a single get result based on returnAs */
	convertGetResult(record, returnAs) {
		switch (returnAs) {
			case "model":
				return this.recordCtor(record);
			case "record":
				return record;
			case "interface":
				return this.toInterface(record);
		}
	}

	/** Convert multiple get results based on returnAs */
	convertGetResults(records, returnAs) {
		switch (returnAs) {
			case "model":
				return records.map((r) => this.recordCtor(r));
			case "record":
				return records;
			case "interface":
				return records.map((r) => this.toInterface(r));
		}
	}

	/** Detect the input type of a record */
	detectInputType(record) {
		if (record instanceof AirtableModel) return "model";
		if (this.isATRecord(record)) return "record";
		return "interface";
	}

	/** Convert into a form the Airtable API will accept */
	toWritableRecord(record) {
		const writableFields = {};
		for (const fieldId of this.writableFieldIds) {
			if (fieldId in record.fields) {
				writableFields[fieldId] = record.fields[fieldId];
			}
		}
		return {
			id: record.id,
			fields: writableFields,
		};
	}

	/** Check if a record is an Airtable.js Record instance (vs a plain object) */
	isATRecord(record) {
		return typeof record.save === "function";
	}

	/** Convert to a simple interface object */
	toInterface(record) {
		return {
			id: record.id,
			fields: record.fields,
		};
	}

	isUsingFieldNames(records) {
		for (const record of records) {
			for (const field in record.fields) {
				if (this.fieldNameToIdMap[field]) {
					return true;
				}
			}
		}
		return false;
	}

	mapToIds(records) {
		if (this.isUsingFieldNames(records)) {
			for (const record of records) {
				for (const field in record.fields) {
					if (this.fieldNameToIdMap[field]) {
						const value = record.fields[field];
						delete record.fields[field];
						record.fields[this.fieldNameToIdMap[field]] = value;
					}
				}
			}
		}
		return records;
	}

	mapToNames(records) {
		for (const record of records) {
			for (const field in record.fields) {
				if (this.fieldIdToNameMap[field]) {
					const value = record.fields[field];
					delete record.fields[field];
					record.fields[this.fieldIdToNameMap[field]] = value;
				}
			}
		}
		return records;
	}

	//#endregion
}

module.exports = { AirtableTable };

const Airtable = require("airtable");
const { ID } = require("./formula");
const { baseIdSchema, validateRecordIds } = require("./special-types");

class AirtableTable {
	_table;
	recordCtor;
	viewNameToIdMap = {};

	constructor(baseId, tableNameOrId, viewNameToIdMap, recordCtor, options = {}) {
		this._table = new Airtable(options).base(baseIdSchema.parse(baseId)).table(tableNameOrId);
		this.recordCtor = recordCtor;
		this.viewNameToIdMap = viewNameToIdMap;
	}

	getViewId(viewName) {
		return this.viewNameToIdMap[viewName] || viewName;
	}

	/**
	 * Get record(s) by ID, IDs, or query options.
	 * @param {string|string[]|object} recordIdOrIdsOrOptions - Single ID, array of IDs, or query options
	 * @param {object} options - Additional options when fetching by ID
	 */
	async get(recordIdOrIdsOrOptions, options) {
		// Single record by ID
		if (typeof recordIdOrIdsOrOptions === "string") {
			validateRecordIds(recordIdOrIdsOrOptions);
			const selectOptions = {
				filterByFormula: new ID().equals(recordIdOrIdsOrOptions),
			};
			if (options?.pageSize) selectOptions.pageSize = options.pageSize;
			if (options?.fields) selectOptions.fields = options.fields;
			selectOptions.returnFieldsByFieldId = options?.useFieldIds || false;

			const records = await this._table.select(selectOptions).all();
			const mappedRecords = records.map((record) => this.recordCtor(record));
			return mappedRecords.length === 0 ? {} : mappedRecords[0];
		}

		// Multiple records by IDs
		if (Array.isArray(recordIdOrIdsOrOptions)) {
			validateRecordIds(recordIdOrIdsOrOptions);
			if (recordIdOrIdsOrOptions.length === 0) {
				return [];
			}

			const selectOptions = {
				filterByFormula: new ID().inList(recordIdOrIdsOrOptions),
			};
			if (options?.pageSize) selectOptions.pageSize = options.pageSize;
			if (options?.fields) selectOptions.fields = options.fields;
			if (options?.maxRecords) selectOptions.maxRecords = options.maxRecords;
			selectOptions.returnFieldsByFieldId = options?.useFieldIds || false;

			const records = await this._table.select(selectOptions).all();
			return records.map((record) => this.recordCtor(record));
		}

		// Query with options (first parameter is options object)
		const queryOptions = recordIdOrIdsOrOptions || {};
		const selectOptions = {};
		if (queryOptions.view) selectOptions.view = this.getViewId(queryOptions.view);
		if (queryOptions.formula) selectOptions.filterByFormula = queryOptions.formula;
		if (queryOptions.pageSize) selectOptions.pageSize = queryOptions.pageSize;
		if (queryOptions.fields) selectOptions.fields = queryOptions.fields;
		if (queryOptions.maxRecords) selectOptions.maxRecords = queryOptions.maxRecords;

		const records = await this._table.select(selectOptions).all();
		return records.map((record) => this.recordCtor(record));
	}

	/**
	 * Create record(s).
	 * @param {object|object[]} recordOrRecords - Single record or array of records
	 */
	async create(recordOrRecords) {
		if (Array.isArray(recordOrRecords)) {
			const records = recordOrRecords.map((record) => record.toCreateRecordData());
			const createdRecords = [];
			// Create in batches of 10 (Airtable API limit)
			for (let i = 0; i < records.length; i += 10) {
				const batch = records.slice(i, i + 10);
				const batchCreated = await this._table.create(batch);
				createdRecords.push(...batchCreated);
			}
			return createdRecords.map((record) => this.recordCtor(record));
		} else {
			const record = recordOrRecords.toCreateRecordData();
			const createdRecords = await this._table.create([record]);
			return this.recordCtor(createdRecords[0]);
		}
	}

	/**
	 * Update record(s).
	 * @param {object|object[]} recordOrRecords - Single record or array of records
	 */
	async update(recordOrRecords) {
		if (Array.isArray(recordOrRecords)) {
			const records = recordOrRecords.map((record) => record.toUpdateRecordData());
			const updatedRecords = [];
			// Update in batches of 10 (Airtable API limit)
			for (let i = 0; i < records.length; i += 10) {
				const batch = records.slice(i, i + 10);
				const batchUpdated = await this._table.update(batch);
				updatedRecords.push(...batchUpdated);
			}
			return updatedRecords.map((record) => this.recordCtor(record));
		} else {
			const record = recordOrRecords.toUpdateRecordData();
			const updatedRecords = await this._table.update([record]);
			return this.recordCtor(updatedRecords[0]);
		}
	}

	/**
	 * Upsert record(s) - creates if doesn't exist, updates if exists.
	 * @param {object|object[]} recordOrRecords - Single record or array of records
	 */
	async upsert(recordOrRecords) {
		const records = Array.isArray(recordOrRecords) ? recordOrRecords : [recordOrRecords];

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
			toUpdate.length > 0 ? await this.update(toUpdate) : Promise.resolve([]),
			toCreate.length > 0 ? await this.create(toCreate) : Promise.resolve([]),
		]);
		const upsertedRecords = [...updatedRecords, ...createdRecords];

		return Array.isArray(recordOrRecords) ? upsertedRecords : upsertedRecords[0];
	}

	/**
	 * Delete record(s) by ID.
	 * @param {string|string[]} recordIdOrIds - Single ID or array of IDs
	 */
	async delete(recordIdOrIds) {
		if (Array.isArray(recordIdOrIds)) {
			validateRecordIds(recordIdOrIds);
			// Delete in batches of 10 (Airtable API limit)
			for (let i = 0; i < recordIdOrIds.length; i += 10) {
				const batch = recordIdOrIds.slice(i, i + 10);
				await this._table.destroy(batch);
			}
		} else {
			validateRecordIds(recordIdOrIds);
			await this._table.destroy([recordIdOrIds]);
		}
	}
}

module.exports = { AirtableTable };

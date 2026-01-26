/* eslint-disable no-unused-vars */
import Airtable, { Record as ATRecord, FieldSet, Table, AirtableOptions } from "airtable";
import { AirtableModel } from "./airtable-model";
import { QueryParams } from "airtable/lib/query_params";
import { ID } from "./formula";
import { baseIdSchema, validateRecordIds } from "./special-types";

interface Options<T> {
	pageSize?: number;
	fields?: T[];
	useFieldIds?: boolean;
	maxRecords?: number;
}
interface QueryOptions<V, T> extends Options<T> {
	view?: V;
	formula?: string;
}

export class AirtableTable<
	T extends FieldSet,
	U extends AirtableModel<T, unknown>,
	V extends string,
	W extends string,
> {
	public _table: Table<T>;
	public readonly baseId: string;
	public readonly options: AirtableOptions;
	private recordCtor: (record: ATRecord<T>) => U;
	private viewNameToIdMap: Record<V, string> = {} as Record<V, string>;

	constructor(
		baseId: string,
		tableNameOrId: string,
		viewNameToIdMap: Record<V, string>,
		recordCtor: (record: ATRecord<T>) => U,
		options: AirtableOptions = {},
	) {
		this.baseId = baseIdSchema.parse(baseId);
		this.options = options;
		this._table = new Airtable(options).base(this.baseId).table(tableNameOrId);
		this.recordCtor = recordCtor;
		this.viewNameToIdMap = viewNameToIdMap;
	}

	public getViewId(viewName: V): string {
		return this.viewNameToIdMap[viewName] || viewName;
	}

	/** Get a single record by ID */
	public async get(recordId: string, options?: Options<W>): Promise<U>;
	/** Get multiple records by IDs */
	public async get(recordIds: string[], options?: Options<W>): Promise<U[]>;
	/** Get multiple records with query options */
	public async get(options?: QueryOptions<V, W>): Promise<U[]>;
	public async get(
		recordIdOrIdsOrOptions?: string | string[] | QueryOptions<V, W>,
		options?: Options<W>,
	): Promise<U | U[]> {
		// Single record by ID
		if (typeof recordIdOrIdsOrOptions === "string") {
			validateRecordIds(recordIdOrIdsOrOptions);
			const selectOptions: QueryParams<T> = {
				filterByFormula: new ID().equals(recordIdOrIdsOrOptions),
			};
			if (options?.pageSize) selectOptions.pageSize = options.pageSize;
			if (options?.fields) selectOptions.fields = options.fields as string[];
			selectOptions.returnFieldsByFieldId = options?.useFieldIds ?? true;

			try {
				const records = await this._table.select(selectOptions).all();
				const mappedRecords = records.map((record) => this.recordCtor(record));
				return mappedRecords.length === 0 ? ({} as U) : mappedRecords[0];
			} catch (error) {
				// I am aware of how stupid this looks,
				// but without it, errors from Airtable's API don't surface properly;
				// you get a generic "UnhandledPromiseRejectionWarning" instead.
				throw new Error(String(error));
			}
		}

		// Multiple records by IDs
		if (Array.isArray(recordIdOrIdsOrOptions)) {
			validateRecordIds(recordIdOrIdsOrOptions);
			if (recordIdOrIdsOrOptions.length === 0) {
				return [];
			}

			const selectOptions: QueryParams<T> = {
				filterByFormula: new ID().inList(recordIdOrIdsOrOptions),
			};
			if (options?.pageSize) selectOptions.pageSize = options.pageSize;
			if (options?.fields) selectOptions.fields = options.fields as string[];
			if (options?.maxRecords) selectOptions.maxRecords = options.maxRecords;
			selectOptions.returnFieldsByFieldId = options?.useFieldIds ?? true;

			try {
				const records = await this._table.select(selectOptions).all();
				return records.map((record) => this.recordCtor(record));
			} catch (error) {
				// I am aware of how stupid this looks,
				// but without it, errors from Airtable's API don't surface properly;
				// you get a generic "UnhandledPromiseRejectionWarning" instead.
				throw new Error(String(error));
			}
		}

		// Query with options (first parameter is options object)
		const queryOptions = recordIdOrIdsOrOptions || {};
		const selectOptions: QueryParams<T> = {};
		if (queryOptions.view) selectOptions.view = this.getViewId(queryOptions.view);
		if (queryOptions.formula) selectOptions.filterByFormula = queryOptions.formula;
		if (queryOptions.pageSize) selectOptions.pageSize = queryOptions.pageSize;
		if (queryOptions.fields) selectOptions.fields = queryOptions.fields as string[];
		if (queryOptions.maxRecords) selectOptions.maxRecords = queryOptions.maxRecords;
		selectOptions.returnFieldsByFieldId = queryOptions.useFieldIds ?? true;

		try {
			const records = await this._table.select(selectOptions).all();
			return records.map((record) => this.recordCtor(record));
		} catch (error) {
			// I am aware of how stupid this looks,
			// but without it, errors from Airtable's API don't surface properly;
			// you get a generic "UnhandledPromiseRejectionWarning" instead.
			throw new Error(String(error));
		}
	}

	/** Create a single record */
	public async create(record: U): Promise<U>;
	/** Create multiple records */
	public async create(records: U[]): Promise<U[]>;
	public async create(recordOrRecords: U | U[]): Promise<U | U[]> {
		if (Array.isArray(recordOrRecords)) {
			const records = recordOrRecords.map((record) => record.toCreateRecordData());
			const createdRecords: ATRecord<T>[] = [];
			// Create in batches of 10 (Airtable API limit)
			for (let i = 0; i < records.length; i += 10) {
				const batch = records.slice(i, i + 10);
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
			return createdRecords.map((record) => this.recordCtor(record));
		} else {
			const record = recordOrRecords.toCreateRecordData();
			try {
				const createdRecords = await this._table.create([record]);
				return this.recordCtor(createdRecords[0]);
			} catch (error) {
				// I am aware of how stupid this looks,
				// but without it, errors from Airtable's API don't surface properly;
				// you get a generic "UnhandledPromiseRejectionWarning" instead.
				throw new Error(String(error));
			}
		}
	}

	/** Update a single record */
	public async update(record: U): Promise<U>;
	/** Update multiple records */
	public async update(records: U[]): Promise<U[]>;
	public async update(recordOrRecords: U | U[]): Promise<U | U[]> {
		if (Array.isArray(recordOrRecords)) {
			const records = recordOrRecords.map((record) => record.toUpdateRecordData());
			const updatedRecords: ATRecord<T>[] = [];
			// Update in batches of 10 (Airtable API limit)
			for (let i = 0; i < records.length; i += 10) {
				const batch = records.slice(i, i + 10);
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
			return updatedRecords.map((record) => this.recordCtor(record));
		} else {
			const record = recordOrRecords.toUpdateRecordData();
			try {
				const updatedRecords = await this._table.update([record]);
				return this.recordCtor(updatedRecords[0]);
			} catch (error) {
				// I am aware of how stupid this looks,
				// but without it, errors from Airtable's API don't surface properly;
				// you get a generic "UnhandledPromiseRejectionWarning" instead.
				throw new Error(String(error));
			}
		}
	}

	/** Upsert a single record */
	public async upsert(record: U): Promise<U>;
	/** Upsert multiple records */
	public async upsert(records: U[]): Promise<U[]>;
	public async upsert(recordOrRecords: U | U[]): Promise<U | U[]> {
		const records: U[] = Array.isArray(recordOrRecords) ? recordOrRecords : [recordOrRecords];

		// Batch fetch all records to check which exist
		const recordIds = records.map((r) => r.id).filter((id) => !!id);
		const existingRecords = recordIds.length > 0 ? await this.get(recordIds) : [];
		const existingIds = new Set(existingRecords.map((r) => r.id));

		// Separate into updates and creates
		const toUpdate: U[] = [];
		const toCreate: U[] = [];
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

	/** Delete a single record */
	public async delete(recordId: string): Promise<void>;
	/** Delete multiple records */
	public async delete(recordIds: string[]): Promise<void>;
	public async delete(recordIdOrIds: string | string[]): Promise<void> {
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
}

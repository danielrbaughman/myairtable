/* eslint-disable no-unused-vars */
import Airtable, { Record as ATRecord, FieldSet, Table, AirtableOptions } from "airtable";
import { AirtableModel } from "./airtable-model";
import { QueryParams } from "airtable/lib/query_params";
import { ID } from "./formula";
import { baseIdSchema, validateRecordIds } from "./special-types";

export interface Options<Fld> {
	/** Number of records to return per page (Airtable API default is 100) */
	pageSize?: number;
	/** Specific fields to return */
	fields?: Fld[];
	/** Whether to use field IDs instead of names */
	useFieldIds?: boolean;
	/** Maximum number of records to return */
	maxRecords?: number;
}
export interface QueryOptions<Vw, Fld> extends Options<Fld> {
	/** View name or ID to filter records */
	view?: Vw;
	/** Formula string to filter records */
	formula?: string;
}

/** Abstraction of Airtable's `Table` class, for use with myAirtable's `AirtableModel` class */
export class ModelTable<
	FldSt extends FieldSet,
	Mdl extends AirtableModel<FldSt, unknown, keyof FldSt>,
	Vw extends string,
	Fld extends string,
> {
	/** Underlying Airtable.js Table instance */
	public _table: Table<FldSt>;
	/** Base ID */
	public readonly baseId: string;
	private recordCtor: (record: ATRecord<FldSt>) => Mdl;
	public _options: AirtableOptions = {};

	// Mappings
	private viewNameToIdMap: Record<Vw, string>;

	constructor(
		baseId: string,
		tableNameOrId: string,
		viewNameToIdMap: Record<Vw, string>,
		recordCtor: (record: ATRecord<FldSt>) => Mdl,
		options: AirtableOptions = {},
	) {
		this.baseId = baseIdSchema.parse(baseId);
		this._options = options;
		this._table = new Airtable(options).base(this.baseId).table(tableNameOrId);
		this.recordCtor = recordCtor;
		this.viewNameToIdMap = viewNameToIdMap;
	}

	public getViewId(viewName: Vw): string {
		return this.viewNameToIdMap[viewName] || viewName;
	}

	/** Get a single record by ID */
	public async get(recordId: string, options?: Options<Fld>): Promise<Mdl>;
	/** Get multiple records by IDs */
	public async get(recordIds: string[], options?: Options<Fld>): Promise<Mdl[]>;
	/** Get multiple records with query options */
	public async get(options?: QueryOptions<Vw, Fld>): Promise<Mdl[]>;
	public async get(
		recordIdOrIdsOrOptions?: string | string[] | QueryOptions<Vw, Fld>,
		options?: Options<Fld>,
	): Promise<Mdl | Mdl[]> {
		// Single record by ID
		if (typeof recordIdOrIdsOrOptions === "string") {
			validateRecordIds(recordIdOrIdsOrOptions);
			const selectOptions: QueryParams<FldSt> = {
				filterByFormula: new ID().equals(recordIdOrIdsOrOptions),
			};
			if (options?.pageSize) selectOptions.pageSize = options.pageSize;
			if (options?.fields) selectOptions.fields = options.fields as string[];
			selectOptions.returnFieldsByFieldId = options?.useFieldIds ?? true;

			try {
				const records = await this._table.select(selectOptions).all();
				const mappedRecords = records.map((record) => this.recordCtor(record));
				return mappedRecords.length === 0 ? ({} as Mdl) : mappedRecords[0];
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

			const selectOptions: QueryParams<FldSt> = {
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
		const selectOptions: QueryParams<FldSt> = {};
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
	public async create(record: Mdl): Promise<Mdl>;
	/** Create multiple records */
	public async create(records: Mdl[]): Promise<Mdl[]>;
	public async create(recordOrRecords: Mdl | Mdl[]): Promise<Mdl | Mdl[]> {
		if (Array.isArray(recordOrRecords)) {
			const records = recordOrRecords.map((record) => record.toCreateRecordData());
			const createdRecords: ATRecord<FldSt>[] = [];
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
	public async update(record: Mdl): Promise<Mdl>;
	/** Update multiple records */
	public async update(records: Mdl[]): Promise<Mdl[]>;
	public async update(recordOrRecords: Mdl | Mdl[]): Promise<Mdl | Mdl[]> {
		if (Array.isArray(recordOrRecords)) {
			const records = recordOrRecords.map((record) => record.toUpdateRecordData());
			const updatedRecords: ATRecord<FldSt>[] = [];
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
	public async upsert(record: Mdl): Promise<Mdl>;
	/** Upsert multiple records */
	public async upsert(records: Mdl[]): Promise<Mdl[]>;
	public async upsert(recordOrRecords: Mdl | Mdl[]): Promise<Mdl | Mdl[]> {
		const records: Mdl[] = Array.isArray(recordOrRecords) ? recordOrRecords : [recordOrRecords];

		// Batch fetch all records to check which exist
		const recordIds = records.map((r) => r.id).filter((id) => !!id);
		const existingRecords = recordIds.length > 0 ? await this.get(recordIds) : [];
		const existingIds = new Set(existingRecords.map((r) => r.id));

		// Separate into updates and creates
		const toUpdate: Mdl[] = [];
		const toCreate: Mdl[] = [];
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

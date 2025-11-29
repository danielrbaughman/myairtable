/* eslint-disable no-unused-vars */
import Airtable, { Record as ATRecord, FieldSet, Table } from "airtable";
import { AirtableModel } from "./airtable-model";
import { QueryParams } from "airtable/lib/query_params";
import { ID } from "./formula";

interface Options<T> {
	pageSize?: number;
	fields?: T[];
	useFieldIds?: boolean;
}
interface QueryOptions<V, T> extends Options<T> {
	view?: V;
	formula?: string;
}

export class AirtableTable<T extends FieldSet, U extends AirtableModel<T>, V extends string, W extends string> {
	public _table: Table<T>;
	private recordCtor: (record: ATRecord<T>) => U;
	private viewNameToIdMap: Record<V, string> = {} as Record<V, string>;

	constructor(
		apiKey: string,
		baseId: string,
		tableName: string,
		viewNameToIdMap: Record<V, string>,
		recordCtor: (record: ATRecord<T>) => U,
	) {
		this._table = new Airtable({ apiKey, noRetryIfRateLimited: false }).base(baseId).table(tableName);
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
			const selectOptions: QueryParams<T> = {
				filterByFormula: new ID().equals(recordIdOrIdsOrOptions),
			};
			if (options?.pageSize) selectOptions.pageSize = options.pageSize;
			if (options?.fields) selectOptions.fields = options.fields as string[];
			selectOptions.returnFieldsByFieldId = options?.useFieldIds || false;

			const records = await this._table.select(selectOptions).all();
			const mappedRecords = records.map((record) => this.recordCtor(record));
			return mappedRecords.length === 0 ? ({} as U) : mappedRecords[0];
		}

		// Multiple records by IDs
		if (Array.isArray(recordIdOrIdsOrOptions)) {
			if (recordIdOrIdsOrOptions.length === 0) {
				return [];
			}

			const selectOptions: QueryParams<T> = {
				filterByFormula: new ID().inList(recordIdOrIdsOrOptions),
			};
			if (options?.pageSize) selectOptions.pageSize = options.pageSize;
			if (options?.fields) selectOptions.fields = options.fields as string[];
			selectOptions.returnFieldsByFieldId = options?.useFieldIds || false;

			const records = await this._table.select(selectOptions).all();
			return records.map((record) => this.recordCtor(record));
		}

		// Query with options (first parameter is options object)
		const queryOptions = recordIdOrIdsOrOptions || {};
		const selectOptions: QueryParams<T> = {};
		if (queryOptions.view) selectOptions.view = this.getViewId(queryOptions.view);
		if (queryOptions.formula) selectOptions.filterByFormula = queryOptions.formula;
		if (queryOptions.pageSize) selectOptions.pageSize = queryOptions.pageSize;
		if (queryOptions.fields) selectOptions.fields = queryOptions.fields as string[];

		const records = await this._table.select(selectOptions).all();
		return records.map((record) => this.recordCtor(record));
	}

	/** Create a single record */
	public async create(record: U): Promise<U>;
	/** Create multiple records */
	public async create(records: U[]): Promise<U[]>;
	public async create(recordOrRecords: U | U[]): Promise<U | U[]> {
		if (Array.isArray(recordOrRecords)) {
			const records = recordOrRecords.map((record) => record.toCreateRecordData());
			const createdRecords = await this._table.create(records);
			return createdRecords.map((record) => this.recordCtor(record));
		} else {
			const record = recordOrRecords.toCreateRecordData();
			const createdRecords = await this._table.create([record]);
			return this.recordCtor(createdRecords[0]);
		}
	}

	/** Update a single record */
	public async update(record: U): Promise<U>;
	/** Update multiple records */
	public async update(records: U[]): Promise<U[]>;
	public async update(recordOrRecords: U | U[]): Promise<U | U[]> {
		if (Array.isArray(recordOrRecords)) {
			const records = recordOrRecords.map((record) => record.toUpdateRecordData());
			const updatedRecords = await this._table.update(records);
			return updatedRecords.map((record) => this.recordCtor(record));
		} else {
			const record = recordOrRecords.toUpdateRecordData();
			const updatedRecords = await this._table.update([record]);
			return this.recordCtor(updatedRecords[0]);
		}
	}

	/** Delete a single record */
	public async delete(recordId: string): Promise<void>;
	/** Delete multiple records */
	public async delete(recordIds: string[]): Promise<void>;
	public async delete(recordIdOrIds: string | string[]): Promise<void> {
		if (Array.isArray(recordIdOrIds)) {
			await this._table.destroy(recordIdOrIds);
		} else {
			await this._table.destroy([recordIdOrIds]);
		}
	}
}

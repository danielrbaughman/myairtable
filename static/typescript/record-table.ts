/* eslint-disable no-unused-vars */
import Airtable, { Record as ATRecord, FieldSet, Table, AirtableOptions } from "airtable";
import { QueryParams } from "airtable/lib/query_params";
import { ID } from "./formula";
import { baseIdSchema, validateRecordIds } from "./special-types";
import { Options, QueryOptions } from "./model-table";

export interface RecordOptions<Fld> extends Options<Fld> {
	/** Return only writable fields from the API. Allows `.save()` to work properly. */
	onlyWritableFields?: boolean;
	/** Return the data as a simple interface, rather than Airtable.js's `Record<FieldSet>` class */
	returnAsInterface?: boolean;
}

export interface RecordQueryOptions<Vw, Fld> extends QueryOptions<Vw, Fld> {
	/** Return only writable fields from the API. Allows `.save()` to work properly. */
	onlyWritableFields?: boolean;
	/** Return the data as a simple interface, rather than Airtable.js's `Record<FieldSet>` class */
	returnAsInterface?: boolean;
}

/** Simplified representation of an Airtable record */
export interface IRecord<FldSt extends FieldSet> {
	/** The ID of the record */
	id: string;
	/** The fields of the record */
	fields: FldSt;
}

/** Abstraction of Airtable's `Table` class, for use with Airtable.js's `Record<FieldSet>` class */
export class RecordTable<FldSt extends FieldSet, Vw extends string, Fld extends string> {
	/** Underlying Airtable.js Table instance */
	public _table: Table<FldSt>;
	/** Base ID */
	public readonly baseId: string;
	public _options: AirtableOptions = {};

	// Mappings
	private viewNameToIdMap: Record<Vw, string>;
	private fieldNameToIdMap: Record<string, string>;
	private fieldIdToNameMap: Record<string, string>;
	private writableFieldIds: string[];

	constructor(
		baseId: string,
		tableNameOrId: string,
		viewNameToIdMap: Record<Vw, string>,
		fieldNameToIdMap: Record<string, string>,
		fieldIdToNameMap: Record<string, string>,
		writableFieldIds: string[],
		options: AirtableOptions = {},
	) {
		this.baseId = baseIdSchema.parse(baseId);
		this._options = options;
		this._table = new Airtable(options).base(this.baseId).table(tableNameOrId);
		this.viewNameToIdMap = viewNameToIdMap;
		this.fieldNameToIdMap = fieldNameToIdMap;
		this.fieldIdToNameMap = fieldIdToNameMap;
		this.writableFieldIds = writableFieldIds;
	}

	public getViewId(viewName: Vw): string {
		return this.viewNameToIdMap[viewName] || viewName;
	}

	/** Get a single record by ID, as a simple interface */
	public async get(
		recordId: string,
		options: RecordOptions<Fld> & { returnAsInterface: true },
	): Promise<IRecord<FldSt>>;
	/** Get multiple records by IDs, as simple interfaces */
	public async get(
		recordIds: string[],
		options: RecordOptions<Fld> & { returnAsInterface: true },
	): Promise<IRecord<FldSt>[]>;
	/** Get multiple records with query options, as simple interfaces */
	public async get(options: RecordQueryOptions<Vw, Fld> & { returnAsInterface: true }): Promise<IRecord<FldSt>[]>;
	/** Get a single record by ID */
	public async get(recordId: string, options?: RecordOptions<Fld>): Promise<ATRecord<FldSt>>;
	/** Get multiple records by IDs */
	public async get(recordIds: string[], options?: RecordOptions<Fld>): Promise<ATRecord<FldSt>[]>;
	/** Get multiple records with query options */
	public async get(options?: RecordQueryOptions<Vw, Fld>): Promise<ATRecord<FldSt>[]>;
	public async get(
		recordIdOrIdsOrOptions?: string | string[] | RecordQueryOptions<Vw, Fld>,
		options?: RecordOptions<Fld>,
	): Promise<IRecord<FldSt> | IRecord<FldSt>[] | ATRecord<FldSt> | ATRecord<FldSt>[]> {
		// Single record by ID
		if (typeof recordIdOrIdsOrOptions === "string") {
			validateRecordIds(recordIdOrIdsOrOptions);
			const selectOptions: QueryParams<FldSt> = {
				filterByFormula: new ID().equals(recordIdOrIdsOrOptions),
			};
			if (options?.pageSize) selectOptions.pageSize = options.pageSize;
			if (options?.fields) {
				selectOptions.fields = options.fields as string[];
			} else if (options?.onlyWritableFields) {
				selectOptions.fields = this.writableFieldIds;
			}
			selectOptions.returnFieldsByFieldId = options?.useFieldIds ?? false; // Opposite of ModelTable default

			try {
				const records = await this._table.select(selectOptions).all();
				const record = records.length === 0 ? ({} as ATRecord<FldSt>) : records[0];
				return options?.returnAsInterface ? this.toInterface(record) : record;
			} catch (error) {
				// I am aware of how stupid this looks,
				// but without it, errors from Airtable's API don't surface properly;
				// you get a generic "UnhandledPromiseRejectionWarning" instead.
				throw new Error(String(error));
			}
		}

		// Multiple records by IDs
		else if (Array.isArray(recordIdOrIdsOrOptions)) {
			validateRecordIds(recordIdOrIdsOrOptions);
			if (recordIdOrIdsOrOptions.length === 0) {
				return [];
			}

			const selectOptions: QueryParams<FldSt> = {
				filterByFormula: new ID().inList(recordIdOrIdsOrOptions),
			};
			if (options?.pageSize) selectOptions.pageSize = options.pageSize;
			if (options?.fields) {
				selectOptions.fields = options.fields as string[];
			} else if (options?.onlyWritableFields) {
				selectOptions.fields = this.writableFieldIds;
			}
			if (options?.maxRecords) selectOptions.maxRecords = options.maxRecords;
			selectOptions.returnFieldsByFieldId = options?.useFieldIds ?? false; // Opposite of ModelTable default

			try {
				const records = await this._table.select(selectOptions).all();
				return options?.returnAsInterface ? records.map((r) => this.toInterface(r)) : (records as ATRecord<FldSt>[]);
			} catch (error) {
				// I am aware of how stupid this looks,
				// but without it, errors from Airtable's API don't surface properly;
				// you get a generic "UnhandledPromiseRejectionWarning" instead.
				throw new Error(String(error));
			}
		}

		// Query with options (first parameter is options object)
		else {
			const queryOptions = recordIdOrIdsOrOptions || {};
			const selectOptions: QueryParams<FldSt> = {};
			if (queryOptions.view) selectOptions.view = this.getViewId(queryOptions.view);
			if (queryOptions.formula) selectOptions.filterByFormula = queryOptions.formula;
			if (queryOptions.pageSize) selectOptions.pageSize = queryOptions.pageSize;
			if (queryOptions.fields) selectOptions.fields = queryOptions.fields as string[];
			if (queryOptions.maxRecords) selectOptions.maxRecords = queryOptions.maxRecords;
			selectOptions.returnFieldsByFieldId = queryOptions.useFieldIds ?? false; // Opposite of ModelTable default

			try {
				const records = await this._table.select(selectOptions).all();
				return queryOptions.returnAsInterface
					? records.map((r) => this.toInterface(r))
					: (records as ATRecord<FldSt>[]);
			} catch (error) {
				// I am aware of how stupid this looks,
				// but without it, errors from Airtable's API don't surface properly;
				// you get a generic "UnhandledPromiseRejectionWarning" instead.
				throw new Error(String(error));
			}
		}
	}

	/** Create a single record */
	public async create(record: ATRecord<FldSt>): Promise<ATRecord<FldSt>>;
	/** Create multiple records */
	public async create(records: ATRecord<FldSt>[]): Promise<ATRecord<FldSt>[]>;
	/** Create a single record from a simple interface */
	public async create(record: IRecord<FldSt>): Promise<IRecord<FldSt>>;
	/** Create multiple records from simple interfaces */
	public async create(records: IRecord<FldSt>[]): Promise<IRecord<FldSt>[]>;
	public async create(
		recordOrRecords: ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[],
	): Promise<ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[]> {
		const inputIsIRecord = Array.isArray(recordOrRecords)
			? recordOrRecords.length > 0 && !this.isATRecord(recordOrRecords[0])
			: !this.isATRecord(recordOrRecords);

		if (Array.isArray(recordOrRecords)) {
			const records = this.mapToIds(recordOrRecords);
			const isUsingFieldNames = this.isUsingFieldNames(records);
			const createdRecords: ATRecord<FldSt>[] = [];
			// Create in batches of 10 (Airtable API limit)
			for (let i = 0; i < records.length; i += 10) {
				const batch = records.slice(i, i + 10);
				try {
					const batchCreated = await this._table.create(batch.map((r) => this.toWritableRecord(r)) as any);
					createdRecords.push(...batchCreated);
				} catch (error) {
					// I am aware of how stupid this looks,
					// but without it, errors from Airtable's API don't surface properly;
					// you get a generic "UnhandledPromiseRejectionWarning" instead.
					throw new Error(String(error));
				}
			}
			if (isUsingFieldNames) this.mapToNames(createdRecords);
			return inputIsIRecord ? createdRecords.map((r) => this.toInterface(r)) : (createdRecords as ATRecord<FldSt>[]);
		} else {
			const record = this.mapToIds([recordOrRecords])[0];
			const isUsingFieldNames = this.isUsingFieldNames([record]);
			try {
				const createdRecords = await this._table.create([this.toWritableRecord(record)] as any);
				if (isUsingFieldNames) this.mapToNames(createdRecords as ATRecord<FldSt>[]);
				const created = createdRecords[0] as ATRecord<FldSt>;
				return inputIsIRecord ? this.toInterface(created) : created;
			} catch (error) {
				// I am aware of how stupid this looks,
				// but without it, errors from Airtable's API don't surface properly;
				// you get a generic "UnhandledPromiseRejectionWarning" instead.
				throw new Error(String(error));
			}
		}
	}

	/** Update a single record */
	public async update(record: ATRecord<FldSt>): Promise<ATRecord<FldSt>>;
	/** Update multiple records */
	public async update(records: ATRecord<FldSt>[]): Promise<ATRecord<FldSt>[]>;
	/** Update a single record from a simple interface */
	public async update(record: IRecord<FldSt>): Promise<IRecord<FldSt>>;
	/** Update multiple records from simple interfaces */
	public async update(records: IRecord<FldSt>[]): Promise<IRecord<FldSt>[]>;
	public async update(
		recordOrRecords: ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[],
	): Promise<ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[]> {
		const inputIsIRecord = Array.isArray(recordOrRecords)
			? recordOrRecords.length > 0 && !this.isATRecord(recordOrRecords[0])
			: !this.isATRecord(recordOrRecords);

		if (Array.isArray(recordOrRecords)) {
			const records = this.mapToIds(recordOrRecords);
			const isUsingFieldNames = this.isUsingFieldNames(records);
			const updatedRecords: ATRecord<FldSt>[] = [];
			// Update in batches of 10 (Airtable API limit)
			for (let i = 0; i < records.length; i += 10) {
				const batch = records.slice(i, i + 10);
				try {
					const batchUpdated = await this._table.update(batch.map((r) => this.toWritableRecord(r)) as any);
					updatedRecords.push(...batchUpdated);
				} catch (error) {
					// I am aware of how stupid this looks,
					// but without it, errors from Airtable's API don't surface properly;
					// you get a generic "UnhandledPromiseRejectionWarning" instead.
					throw new Error(String(error));
				}
			}
			if (isUsingFieldNames) this.mapToNames(updatedRecords);
			return inputIsIRecord ? updatedRecords.map((r) => this.toInterface(r)) : (updatedRecords as ATRecord<FldSt>[]);
		} else {
			const record = this.mapToIds([recordOrRecords])[0];
			const isUsingFieldNames = this.isUsingFieldNames([record]);
			try {
				const updatedRecords = await this._table.update([this.toWritableRecord(record)] as any);
				if (isUsingFieldNames) this.mapToNames(updatedRecords as ATRecord<FldSt>[]);
				const updated = updatedRecords[0] as ATRecord<FldSt>;
				return inputIsIRecord ? this.toInterface(updated) : updated;
			} catch (error) {
				// I am aware of how stupid this looks,
				// but without it, errors from Airtable's API don't surface properly;
				// you get a generic "UnhandledPromiseRejectionWarning" instead.
				throw new Error(String(error));
			}
		}
	}

	/** Upsert a single record */
	public async upsert(record: ATRecord<FldSt>): Promise<ATRecord<FldSt>>;
	/** Upsert multiple records */
	public async upsert(records: ATRecord<FldSt>[]): Promise<ATRecord<FldSt>[]>;
	/** Upsert a single record from a simple interface */
	public async upsert(record: IRecord<FldSt>): Promise<IRecord<FldSt>>;
	/** Upsert multiple records from simple interfaces */
	public async upsert(records: IRecord<FldSt>[]): Promise<IRecord<FldSt>[]>;
	public async upsert(
		recordOrRecords: ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[],
	): Promise<ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[]> {
		const inputIsIRecord = Array.isArray(recordOrRecords)
			? recordOrRecords.length > 0 && !this.isATRecord(recordOrRecords[0])
			: !this.isATRecord(recordOrRecords);

		const records = Array.isArray(recordOrRecords) ? recordOrRecords : [recordOrRecords];
		// Batch fetch all records to check which exist
		const recordIds = records.map((r) => r.id).filter((id) => !!id);
		const existingRecords = recordIds.length > 0 ? await this.get(recordIds) : [];
		const existingIds = new Set(existingRecords.map((r) => r.id));

		// Separate into updates and creates
		const toUpdate: (ATRecord<FldSt> | IRecord<FldSt>)[] = [];
		const toCreate: (ATRecord<FldSt> | IRecord<FldSt>)[] = [];
		for (const record of records) {
			if (record.id && existingIds.has(record.id)) {
				toUpdate.push(record);
			} else {
				toCreate.push(record);
			}
		}

		// Batch update and create
		type RecordList = (ATRecord<FldSt> | IRecord<FldSt>)[];
		const [updatedRecords, createdRecords] = await Promise.all([
			toUpdate.length > 0
				? this.update(toUpdate as any).then((r) => r as unknown as RecordList)
				: Promise.resolve([] as RecordList),
			toCreate.length > 0
				? this.create(toCreate as any).then((r) => r as unknown as RecordList)
				: Promise.resolve([] as RecordList),
		]);
		const upsertedRecords = [...updatedRecords, ...createdRecords];

		if (inputIsIRecord) {
			const asInterfaces = upsertedRecords.map((r) =>
				this.isATRecord(r) ? this.toInterface(r) : (r as IRecord<FldSt>),
			);
			return Array.isArray(recordOrRecords) ? asInterfaces : asInterfaces[0];
		}
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

	/** Convert into a form the Airtable API will accept */
	private toWritableRecord(record: ATRecord<FldSt> | IRecord<FldSt>): IRecord<FldSt> {
		const writableFields: Partial<FldSt> = {};
		for (const fieldId of this.writableFieldIds) {
			if (fieldId in record.fields) {
				writableFields[fieldId as keyof FldSt] = record.fields[fieldId as keyof FldSt];
			}
		}
		return {
			id: record.id,
			fields: writableFields as FldSt,
		};
	}

	/** Check if a record is an Airtable.js Record instance (vs a plain IRecord) */
	private isATRecord(record: ATRecord<FldSt> | IRecord<FldSt>): record is ATRecord<FldSt> {
		return typeof (record as any).save === "function";
	}

	/** Convert to a simple interface */
	private toInterface(record: ATRecord<FldSt>): IRecord<FldSt> {
		return {
			id: record.id,
			fields: record.fields,
		};
	}

	private isUsingFieldNames(records: Airtable.Record<FldSt>[] | IRecord<FldSt>[]) {
		for (const record of records) {
			for (const field in record.fields) {
				if (this.fieldNameToIdMap[field]) {
					return true;
				}
			}
		}
		return false;
	}

	private mapToIds(records: Airtable.Record<FldSt>[] | IRecord<FldSt>[]): Airtable.Record<FldSt>[] | IRecord<FldSt>[] {
		if (this.isUsingFieldNames(records)) {
			for (const record of records) {
				for (const field in record.fields) {
					if (this.fieldNameToIdMap[field]) {
						const value = record.fields[field];
						delete record.fields[field];
						record.fields[this.fieldNameToIdMap[field] as keyof FldSt] = value;
					}
				}
			}
		}
		return records;
	}

	private mapToNames(
		records: Airtable.Record<FldSt>[] | IRecord<FldSt>[],
	): Airtable.Record<FldSt>[] | IRecord<FldSt>[] {
		if (!this.isUsingFieldNames(records)) {
			for (const record of records) {
				for (const field in record.fields) {
					if (this.fieldIdToNameMap[field]) {
						const value = record.fields[field];
						delete record.fields[field];
						record.fields[this.fieldIdToNameMap[field] as keyof FldSt] = value;
					}
				}
			}
		}
		return records;
	}
}

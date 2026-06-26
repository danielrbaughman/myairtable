import Airtable, { Record as ATRecord, FieldSet, Table, AirtableOptions } from "airtable";
import { AirtableModel } from "./airtable-model";
import { QueryParams, SortParameter } from "airtable/lib/query_params";
import { ID } from "./formula";
import { baseIdSchema, IRecord, validateRecordIds } from "./special-types";
import { buildUrl } from "./helpers";

/** Options for `upsert()` */
export interface UpsertOptions {
	/**
	 * Field IDs (or names) Airtable matches existing records on, via server-side performUpsert.
	 * When omitted, upsert falls back to matching by record `id` (create when absent, update when present).
	 */
	fieldsToMergeOn?: string[];
}

/** Options for fetching records via `get()` */
export interface FetchOptions<Fld> {
	/** Number of records to return per page (Airtable API default is 100) */
	pageSize?: number;
	/** Specific fields to return */
	fields?: Fld[];
	/** Sort records by given field(s) */
	sort?: SortOption<Fld>[];
	/** Whether to use field IDs instead of names */
	useFieldIds?: boolean;
	/** Maximum number of records to return */
	maxRecords?: number;
	/** What format to return the data in. Default: "model" */
	returnAs?: "model" | "record" | "interface";
	/** Return only writable fields from the API. Intended for use in making Airtable.js's `.save()` method work correctly. */
	onlyWritableFields?: boolean;
	offset?: number;
	timeZone?: string;
	userLocale?: string;
}

/** Options for querying records via `get()` */
export interface QueryOptions<Vw, Fld> extends FetchOptions<Fld> {
	/** View name or ID to filter records */
	view?: Vw;
	/** Formula string to filter records */
	formula?: string;
}

/** Sort records by given field */
export interface SortOption<Fld> {
	/** Field to sort by */
	field: Fld;
	/** Direction to sort */
	direction?: "asc" | "desc";
}

/** Conditional return type for `get()` based on the `returnAs` option */
type GetResult<FldSt extends FieldSet, Mdl, R> = R extends "interface"
	? IRecord<FldSt>
	: R extends "record"
		? ATRecord<FldSt>
		: Mdl;

/** Unified Airtable table class supporting model, record, and interface return types */
export class AirtableTable<
	FldSt extends FieldSet,
	Mdl extends AirtableModel<FldSt, unknown, keyof FldSt>,
	Vw extends string,
	Fld extends string,
> {
	/** Underlying Airtable.js Table instance */
	public _table: Table<FldSt>;
	public id: string;
	/** Base ID */
	public readonly baseId: string;
	public _options: AirtableOptions = {};

	private recordCtor: (record: ATRecord<FldSt>) => Mdl;
	private viewNameToIdMap: Record<Vw, string>;
	private fieldNameToIdMap: Record<string, string>;
	private fieldIdToNameMap: Record<string, string>;
	private writableFieldIds: string[];
	private cacheSeconds: number;
	private _cache: Map<string, { value: any; expiresAt: number }> = new Map();

	constructor(
		baseId: string,
		tableNameOrId: string,
		viewNameToIdMap: Record<Vw, string>,
		fieldNameToIdMap: Record<string, string>,
		fieldIdToNameMap: Record<string, string>,
		writableFieldIds: string[],
		recordCtor: (record: ATRecord<FldSt>) => Mdl,
		options: AirtableOptions = {},
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
		this.cacheSeconds = (options as any).cacheSeconds ?? 0;
	}

	/** Gets the view ID for a given view name. */
	public getViewId(viewName: Vw): string {
		return this.viewNameToIdMap[viewName] || viewName;
	}

	/** Gets the Airtable web URL for this table, optionally for a specific view. */
	public url(view?: Vw): string {
		if (view) {
			return buildUrl(this.baseId, this.id, this.getViewId(view));
		} else {
			return buildUrl(this.baseId, this.id);
		}
	}

	//#region GET

	/**
	 * Fetches a single record by ID.
	 *
	 * @param recordId - The Airtable record ID.
	 * @param options - See also {@link FetchOptions}:
	 *   - `fields` — Restrict which fields are returned (by name).
	 *   - `useFieldIds` — When true, field keys are IDs (`fldXXX`) instead of names. Defaults to true when returning models; false otherwise.
	 *   - `returnAs` — Determines the return format: `model`, `record`, or `interface`. Default: `model`.
	 *   - `pageSize` — Records per API page (1–100, default 100).
	 *   - `maxRecords` — Cap the total number of records returned.
	 *   - `onlyWritableFields` — Return only writable fields from the API. Intended for use in making Airtable.js's `.save()` method work correctly.
	 */
	public async get<R extends "model" | "record" | "interface">(
		recordId: string,
		options: FetchOptions<Fld> & { returnAs: R },
	): Promise<GetResult<FldSt, Mdl, R>>;
	/**
	 * Fetches multiple records by their IDs, returning them in the format specified by `options.returnAs`.
	 *
	 * @param recordIds - Array of Airtable record IDs.
	 * @param options - See also {@link FetchOptions}:
	 *   - `fields` — Restrict which fields are returned (by name).
	 *   - `useFieldIds` — When true, field keys are IDs (`fldXXX`) instead of names. Defaults to true when returning models; false otherwise.
	 *   - `returnAs` — Determines the return format: `model`, `record`, or `interface`. Default: `model`.
	 *   - `pageSize` — Records per API page (1–100, default 100).
	 *   - `maxRecords` — Cap the total number of records returned.
	 *   - `onlyWritableFields` — Return only writable fields from the API. Intended for use in making Airtable.js's `.save()` method work correctly.
	 */
	public async get<R extends "model" | "record" | "interface">(
		recordIds: string[],
		options: FetchOptions<Fld> & { returnAs: R },
	): Promise<GetResult<FldSt, Mdl, R>[]>;
	/**
	 * Fetches records matching query options, returning them in the format specified by `options.returnAs`.
	 *
	 * @param options - See also {@link FetchOptions}:
	 *   - `view` — View name or ID to filter records.
	 *   - `formula` — Formula string to filter records.
	 *   - `sort` — Sort records by given field(s).
	 *   - `fields` — Restrict which fields are returned (by name).
	 *   - `useFieldIds` — When true, field keys are IDs (`fldXXX`) instead of names. Defaults to true when returning models; false otherwise.
	 *   - `returnAs` — Determines the return format: `model`, `record`, or `interface`. Default: `model`.
	 *   - `pageSize` — Records per API page (1–100, default 100).
	 *   - `maxRecords` — Cap the total number of records returned.
	 *   - `onlyWritableFields` — Return only writable fields from the API. Intended for use in making Airtable.js's `.save()` method work correctly.
	 */
	public async get<R extends "model" | "record" | "interface">(
		options: QueryOptions<Vw, Fld> & { returnAs: R },
	): Promise<GetResult<FldSt, Mdl, R>[]>;
	/**
	 * Fetches a single record by ID.
	 *
	 * @param recordId - The Airtable record ID.
	 * @param options - See also {@link FetchOptions}:
	 *   - `returnAs` — Determines the return format: `model`, `record`, or `interface`. Default: `model`.
	 *   - `pageSize` — Records per API page (1–100, default 100).
	 *   - `fields` — Restrict which fields are returned (by name).
	 *   - `useFieldIds` — When true, field keys are IDs (`fldXXX`) instead of names. Defaults to true when returning models; false otherwise.
	 *   - `maxRecords` — Cap the total number of records returned.
	 *   - `onlyWritableFields` — Return only writable fields from the API. Intended for use in making Airtable.js's `.save()` method work correctly.
	 */
	public async get(recordId: string, options?: FetchOptions<Fld>): Promise<Mdl>;
	/**
	 * Fetches multiple records by their IDs, returning them in the format specified by `options.returnAs`.
	 *
	 * @param recordIds - Array of Airtable record IDs.
	 * @param options - See also {@link FetchOptions}:
	 *   - `fields` — Restrict which fields are returned (by name).
	 *   - `useFieldIds` — When true, field keys are IDs (`fldXXX`) instead of names. Defaults to true when returning models; false otherwise.
	 *   - `returnAs` — Determines the return format: `model`, `record`, or `interface`. Default: `model`.
	 *   - `pageSize` — Records per API page (1–100, default 100).
	 *   - `maxRecords` — Cap the total number of records returned.
	 *   - `onlyWritableFields` — Return only writable fields from the API. Intended for use in making Airtable.js's `.save()` method work correctly.
	 */
	public async get(recordIds: string[], options?: FetchOptions<Fld>): Promise<Mdl[]>;
	/**
	 * Fetches records matching query options, returning them in the format specified by `options.returnAs`.
	 *
	 * @param options - See also {@link FetchOptions}:
	 *   - `view` — View name or ID to filter records.
	 *   - `formula` — Formula string to filter records.
	 *   - `sort` — Sort records by given field(s).
	 *   - `fields` — Restrict which fields are returned (by name).
	 *   - `useFieldIds` — When true, field keys are IDs (`fldXXX`) instead of names. Defaults to true when returning models; false otherwise.
	 *   - `returnAs` — Determines the return format: `model`, `record`, or `interface`. Default: `model`.
	 *   - `pageSize` — Records per API page (1–100, default 100).
	 *   - `maxRecords` — Cap the total number of records returned.
	 *   - `onlyWritableFields` — Return only writable fields from the API. Intended for use in making Airtable.js's `.save()` method work correctly.
	 */
	public async get(options?: QueryOptions<Vw, Fld>): Promise<Mdl[]>;
	public async get(
		recordIdOrIdsOrOptions?: string | string[] | QueryOptions<Vw, Fld>,
		options?: FetchOptions<Fld>,
	): Promise<any> {
		// Cache check
		const cacheKey = this.cacheSeconds > 0 ? JSON.stringify([recordIdOrIdsOrOptions, options]) : "";
		if (this.cacheSeconds > 0) {
			const hit = this._cache.get(cacheKey);
			if (hit && Date.now() < hit.expiresAt) return hit.value;
		}

		let result: any;

		// Single record by ID
		if (typeof recordIdOrIdsOrOptions === "string") {
			validateRecordIds(recordIdOrIdsOrOptions);
			const returnAs = options?.returnAs ?? "model";
			const selectOptions: QueryParams<FldSt> = {
				filterByFormula: new ID().equals(recordIdOrIdsOrOptions),
			};
			if (options?.fields) {
				selectOptions.fields = options.fields as string[];
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
			const selectOptions: QueryParams<FldSt> = {
				filterByFormula: new ID().inList(recordIdOrIdsOrOptions),
			};
			if (options?.fields) {
				selectOptions.fields = options.fields as string[];
			} else if (options?.onlyWritableFields && returnAs !== "model") {
				selectOptions.fields = this.writableFieldIds;
			}
			if (options?.sort) selectOptions.sort = options.sort as SortParameter<FldSt>[];
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
			const selectOptions: QueryParams<FldSt> = {};
			if (queryOptions.fields) {
				selectOptions.fields = queryOptions.fields as string[];
			} else if (queryOptions.onlyWritableFields && returnAs !== "model") {
				selectOptions.fields = this.writableFieldIds;
			}
			if (queryOptions.view) selectOptions.view = this.getViewId(queryOptions.view);
			if (queryOptions.formula) selectOptions.filterByFormula = queryOptions.formula;
			if (queryOptions.sort) selectOptions.sort = queryOptions.sort as SortParameter<FldSt>[];
			if (queryOptions.pageSize) selectOptions.pageSize = queryOptions.pageSize;
			if (queryOptions.maxRecords) selectOptions.maxRecords = queryOptions.maxRecords;
			if (queryOptions?.offset) selectOptions.offset = queryOptions.offset;
			if (queryOptions?.timeZone) selectOptions.timeZone = queryOptions.timeZone;
			if (queryOptions?.userLocale) selectOptions.userLocale = queryOptions.userLocale;
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

	/** Create a single record */
	public async create(record: Mdl): Promise<Mdl>;
	/** Create multiple records */
	public async create(records: Mdl[]): Promise<Mdl[]>;
	/** Create a single record from an Airtable.js Record */
	public async create(record: ATRecord<FldSt>): Promise<ATRecord<FldSt>>;
	/** Create multiple records from Airtable.js Records */
	public async create(records: ATRecord<FldSt>[]): Promise<ATRecord<FldSt>[]>;
	/** Create a single record from a simple interface */
	public async create(record: IRecord<FldSt>): Promise<IRecord<FldSt>>;
	/** Create multiple records from simple interfaces */
	public async create(records: IRecord<FldSt>[]): Promise<IRecord<FldSt>[]>;
	public async create(
		recordOrRecords: Mdl | Mdl[] | ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[],
	): Promise<Mdl | Mdl[] | ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[]> {
		this.invalidateCache();
		const isArray = Array.isArray(recordOrRecords);
		if (isArray && (recordOrRecords as any[]).length === 0) return [] as any;
		const firstItem = isArray ? (recordOrRecords as any[])[0] : recordOrRecords;
		const inputType = this.detectInputType(firstItem);

		if (isArray) {
			const items = recordOrRecords as any[];
			const createdRecords: ATRecord<FldSt>[] = [];

			if (inputType === "model") {
				const payloads = items.map((r: Mdl) => r.toCreateRecordData());
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
				return inputType === "interface"
					? createdRecords.map((r) => this.toInterface(r))
					: (createdRecords as ATRecord<FldSt>[]);
			}
		} else {
			if (inputType === "model") {
				const payload = (recordOrRecords as Mdl).toCreateRecordData();
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
				const record = this.mapToIds([recordOrRecords as any])[0];
				const isUsingFieldNames = this.isUsingFieldNames([record]);
				try {
					const createdRecords = await this._table.create([this.toWritableRecord(record)] as any);
					if (isUsingFieldNames) this.mapToNames(createdRecords as ATRecord<FldSt>[]);
					const created = createdRecords[0] as ATRecord<FldSt>;
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

	/** Update a single record */
	public async update(record: Mdl): Promise<Mdl>;
	/** Update multiple records */
	public async update(records: Mdl[]): Promise<Mdl[]>;
	/** Update a single record from an Airtable.js Record */
	public async update(record: ATRecord<FldSt>): Promise<ATRecord<FldSt>>;
	/** Update multiple records from Airtable.js Records */
	public async update(records: ATRecord<FldSt>[]): Promise<ATRecord<FldSt>[]>;
	/** Update a single record from a simple interface */
	public async update(record: IRecord<FldSt>): Promise<IRecord<FldSt>>;
	/** Update multiple records from simple interfaces */
	public async update(records: IRecord<FldSt>[]): Promise<IRecord<FldSt>[]>;
	public async update(
		recordOrRecords: Mdl | Mdl[] | ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[],
	): Promise<Mdl | Mdl[] | ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[]> {
		this.invalidateCache();
		const isArray = Array.isArray(recordOrRecords);
		if (isArray && (recordOrRecords as any[]).length === 0) return [] as any;
		const firstItem = isArray ? (recordOrRecords as any[])[0] : recordOrRecords;
		const inputType = this.detectInputType(firstItem);

		if (isArray) {
			const items = recordOrRecords as any[];
			const updatedRecords: ATRecord<FldSt>[] = [];

			if (inputType === "model") {
				const payloads = items.map((r: Mdl) => r.toUpdateRecordData());
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
				return inputType === "interface"
					? updatedRecords.map((r) => this.toInterface(r))
					: (updatedRecords as ATRecord<FldSt>[]);
			}
		} else {
			if (inputType === "model") {
				const payload = (recordOrRecords as Mdl).toUpdateRecordData();
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
				const record = this.mapToIds([recordOrRecords as any])[0];
				const isUsingFieldNames = this.isUsingFieldNames([record]);
				try {
					const updatedRecords = await this._table.update([this.toWritableRecord(record)] as any);
					if (isUsingFieldNames) this.mapToNames(updatedRecords as ATRecord<FldSt>[]);
					const updated = updatedRecords[0] as ATRecord<FldSt>;
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

	/** Upsert a single record */
	public async upsert(record: Mdl, options?: UpsertOptions): Promise<Mdl>;
	/** Upsert multiple records */
	public async upsert(records: Mdl[], options?: UpsertOptions): Promise<Mdl[]>;
	/** Upsert a single record from an Airtable.js Record */
	public async upsert(record: ATRecord<FldSt>, options?: UpsertOptions): Promise<ATRecord<FldSt>>;
	/** Upsert multiple records from Airtable.js Records */
	public async upsert(records: ATRecord<FldSt>[], options?: UpsertOptions): Promise<ATRecord<FldSt>[]>;
	/** Upsert a single record from a simple interface */
	public async upsert(record: IRecord<FldSt>, options?: UpsertOptions): Promise<IRecord<FldSt>>;
	/** Upsert multiple records from simple interfaces */
	public async upsert(records: IRecord<FldSt>[], options?: UpsertOptions): Promise<IRecord<FldSt>[]>;
	public async upsert(
		recordOrRecords: Mdl | Mdl[] | ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[],
		options?: UpsertOptions,
	): Promise<Mdl | Mdl[] | ATRecord<FldSt> | ATRecord<FldSt>[] | IRecord<FldSt> | IRecord<FldSt>[]> {
		this.invalidateCache();
		const isArray = Array.isArray(recordOrRecords);
		if (isArray && (recordOrRecords as any[]).length === 0) return [] as any;
		const firstItem = isArray ? (recordOrRecords as any[])[0] : recordOrRecords;
		const inputType = this.detectInputType(firstItem);
		const records = isArray ? (recordOrRecords as any[]) : [recordOrRecords];

		// Merge-field upsert: Airtable matches each record against existing ones by the given field
		// IDs/names (server-side performUpsert). airtable.js doesn't expose this, so issue the PATCH
		// directly, then rehydrate the upserted records (returned in input order) via get().
		if (options?.fieldsToMergeOn && options.fieldsToMergeOn.length > 0) {
			const orderedIds = await this.performMergeUpsert(records, inputType, options.fieldsToMergeOn);
			const fetched = (await this.get(orderedIds, { returnAs: inputType } as any)) as any[];
			const byId = new Map<string, any>();
			for (const item of fetched) byId.set((item as any).id, item);
			const ordered = orderedIds.map((id) => byId.get(id));
			return isArray ? ordered : ordered[0];
		}

		// Batch fetch all records to check which exist
		const recordIds = records.map((r) => r.id).filter((id: string) => !!id);
		const existingRecords = recordIds.length > 0 ? await this.get(recordIds) : [];
		const existingIds = new Set(existingRecords.map((r) => r.id));

		// Separate into updates and creates
		const toUpdate: any[] = [];
		const toCreate: any[] = [];
		for (const record of records) {
			if (record.id && existingIds.has(record.id)) {
				toUpdate.push(record);
			} else {
				toCreate.push(record);
			}
		}

		// Batch update and create
		const [updatedRecords, createdRecords] = await Promise.all([
			toUpdate.length > 0 ? this.update(toUpdate as any) : Promise.resolve([]),
			toCreate.length > 0 ? this.create(toCreate as any) : Promise.resolve([]),
		]);
		const upsertedRecords = [
			...(Array.isArray(updatedRecords) ? updatedRecords : [updatedRecords]),
			...(Array.isArray(createdRecords) ? createdRecords : [createdRecords]),
		];

		if (inputType === "interface") {
			const asInterfaces = upsertedRecords.map((r) =>
				this.isATRecord(r as any) ? this.toInterface(r as ATRecord<FldSt>) : (r as IRecord<FldSt>),
			);
			return isArray ? asInterfaces : asInterfaces[0];
		}
		return isArray ? upsertedRecords : upsertedRecords[0];
	}

	/**
	 * Issue a server-side performUpsert PATCH for the given records, matching by `fieldsToMergeOn`,
	 * in batches of 10. Returns the upserted record IDs in input order. Records carrying an `id` are
	 * matched by id; the rest by the merge fields (one match updates, none inserts, many → 422).
	 */
	private async performMergeUpsert(
		records: any[],
		inputType: "model" | "record" | "interface",
		fieldsToMergeOn: string[],
	): Promise<string[]> {
		const payloads: { id?: string; fields: any }[] =
			inputType === "model"
				? records.map((r: Mdl) => ({ id: r.id, fields: r.toCreateRecordData(true).fields }))
				: this.mapToIds(records).map((r) => ({ id: r.id, fields: this.toWritableRecord(r).fields }));

		const apiKey = (this._options as any).apiKey ?? process.env.AIRTABLE_API_KEY;
		const endpoint = (this._options as any).endpointUrl ?? "https://api.airtable.com";
		const url = `${endpoint}/v0/${this.baseId}/${encodeURIComponent(this.id)}`;

		const ids: string[] = [];
		for (let i = 0; i < payloads.length; i += 10) {
			const batch = payloads.slice(i, i + 10);
			const body = {
				performUpsert: { fieldsToMergeOn },
				records: batch.map((p) => (p.id ? { id: p.id, fields: p.fields } : { fields: p.fields })),
				returnFieldsByFieldId: true,
				typecast: false,
			};
			let response: Response;
			try {
				response = await fetch(url, {
					method: "PATCH",
					headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
					body: JSON.stringify(body),
				});
			} catch (error) {
				throw new Error(String(error));
			}
			if (!response.ok) {
				const text = await response.text().catch(() => "");
				throw new Error(`Airtable upsert failed (${response.status}): ${text}`);
			}
			const json = (await response.json()) as { records: { id: string }[] };
			for (const rec of json.records) ids.push(rec.id);
		}
		return ids;
	}

	//#endregion

	//#region DELETE

	/** Delete a single record */
	public async delete(recordId: string): Promise<void>;
	/** Delete multiple records */
	public async delete(recordIds: string[]): Promise<void>;
	public async delete(recordIdOrIds: string | string[]): Promise<void> {
		this.invalidateCache();
		if (Array.isArray(recordIdOrIds)) {
			validateRecordIds(recordIdOrIds);
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
	public invalidateCache(): void {
		this._cache.clear();
	}

	/** Convert a single get result based on returnAs */
	private convertGetResult(
		record: ATRecord<FldSt>,
		returnAs: "model" | "record" | "interface",
	): Mdl | ATRecord<FldSt> | IRecord<FldSt> {
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
	private convertGetResults(
		records: ATRecord<FldSt>[],
		returnAs: "model" | "record" | "interface",
	): Mdl[] | ATRecord<FldSt>[] | IRecord<FldSt>[] {
		switch (returnAs) {
			case "model":
				return records.map((r) => this.recordCtor(r));
			case "record":
				return records as ATRecord<FldSt>[];
			case "interface":
				return records.map((r) => this.toInterface(r));
		}
	}

	/** Detect the input type of a record */
	private detectInputType(record: unknown): "model" | "record" | "interface" {
		if (record instanceof AirtableModel) return "model";
		if (this.isATRecord(record as any)) return "record";
		return "interface";
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

	private isUsingFieldNames(records: (ATRecord<FldSt> | IRecord<FldSt>)[]): boolean {
		for (const record of records) {
			for (const field in record.fields) {
				if (this.fieldNameToIdMap[field]) {
					return true;
				}
			}
		}
		return false;
	}

	private mapToIds(records: (ATRecord<FldSt> | IRecord<FldSt>)[]): (ATRecord<FldSt> | IRecord<FldSt>)[] {
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

	private mapToNames(records: (ATRecord<FldSt> | IRecord<FldSt>)[]): (ATRecord<FldSt> | IRecord<FldSt>)[] {
		for (const record of records) {
			for (const field in record.fields) {
				if (this.fieldIdToNameMap[field]) {
					const value = record.fields[field];
					delete record.fields[field];
					record.fields[this.fieldIdToNameMap[field] as keyof FldSt] = value;
				}
			}
		}
		return records;
	}

	//#endregion
}

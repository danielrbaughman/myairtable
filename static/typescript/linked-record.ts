import { AirtableOptions, FieldSet } from "airtable";
import { AirtableModel } from "./airtable-model";
import { RecordId, recordIdSchema } from "./special-types";

/**
 * A reference to a linked Airtable record, providing methods to get and set the linked record.
 */
export class LinkedRecord<Mdl extends AirtableModel<FieldSet, unknown, keyof FieldSet>> {
	/** The ID of the linked record. This is the value Airtable actually stores in the linked record field. */
	private _id?: RecordId;
	private record?: Mdl;
	// eslint-disable-next-line no-unused-vars
	private modelCtor?: (id: RecordId, config?: AirtableOptions & { baseId: string }) => Mdl;
	// eslint-disable-next-line no-unused-vars
	private onDirty?: () => void;
	private __configBaseId?: string;
	private __configOptions?: AirtableOptions;

	// eslint-disable-next-line no-unused-vars
	constructor(
		recordId?: RecordId,
		modelCtor?: (id: RecordId, config?: AirtableOptions & { baseId: string }) => Mdl,
		onDirty?: () => void,
		baseId?: string,
		options?: AirtableOptions,
	) {
		this._id = recordIdSchema.optional().parse(recordId);
		this.modelCtor = modelCtor;
		this.onDirty = onDirty;
		this.__configBaseId = baseId;
		this.__configOptions = options;
	}

	public get id(): RecordId | undefined {
		return this._id;
	}
	public set id(value: RecordId | undefined) {
		this._id = value;
		this.onDirty?.();
	}

	/**
	 * Retrieves the linked record. Caches the result for future calls.
	 *
	 * @param fetch - If `true`, forces a fetch of the record data even if it is already loaded. Defaults to `false`.
	 */
	public async get(fetch: boolean = false): Promise<Mdl | undefined> {
		if (this.record === undefined || fetch) {
			const config = this.__configBaseId ? { baseId: this.__configBaseId, ...this.__configOptions } : undefined;
			this.record = this.modelCtor!(this.id!, config);
			await this.record.fetch();
		}
		return this.record;
	}

	/**
	 * Sets the linked record value and updates the associated ID.
	 *
	 * @param value - The new record to link.
	 */
	public set(value: Mdl): void {
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
export class LinkedRecords<Mdl extends AirtableModel<FieldSet, unknown, keyof FieldSet>> {
	/** The IDs of the linked records. These are the values Airtable actually stores in the linked record field. */
	private _ids?: RecordId[];
	private records?: Mdl[];
	// eslint-disable-next-line no-unused-vars
	private modelCtor?: (id: RecordId, config?: AirtableOptions & { baseId: string }) => Mdl;
	// eslint-disable-next-line no-unused-vars
	private onDirty?: () => void;
	private __configBaseId?: string;
	private __configOptions?: AirtableOptions;

	// eslint-disable-next-line no-unused-vars
	constructor(
		recordIds?: RecordId[],
		modelCtor?: (id: RecordId, config?: AirtableOptions & { baseId: string }) => Mdl,
		onDirty?: () => void,
		baseId?: string,
		options?: AirtableOptions,
	) {
		this._ids = recordIds?.map((id) => recordIdSchema.parse(id));
		this.modelCtor = modelCtor;
		this.onDirty = onDirty;
		this.__configBaseId = baseId;
		this.__configOptions = options;
	}

	public get ids(): RecordId[] | undefined {
		return this._ids;
	}
	public set ids(value: RecordId[] | undefined) {
		this._ids = value;
		this.onDirty?.();
	}

	/**
	 * Retrieves the linked records. Caches the result for future calls.
	 *
	 * @param fetch - If `true`, forces a fresh fetch of the records even if they are already loaded. Defaults to `false`.
	 */
	public async get(fetch: boolean = false): Promise<Mdl[]> {
		if (this.records === undefined || fetch) {
			const config = this.__configBaseId ? { baseId: this.__configBaseId, ...this.__configOptions } : undefined;
			this.records = this.ids?.map((id) => this.modelCtor!(id, config)) ?? [];
			await Promise.all(this.records.map((record) => record.fetch()));
		}
		return this.records;
	}

	/**
	 * Sets the linked record values and updates the associated IDs.
	 *
	 * @param values - The new records to link.
	 */
	public set(values: Mdl[]): void {
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
	public add(value: Mdl): void {
		if (!this.records) this.records = [];
		if (!this._ids) this._ids = [];
		this.records.push(value);
		this._ids.push(value.id);
		this.onDirty?.();
	}
}

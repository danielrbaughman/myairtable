import { AirtableOptions, FieldSet } from "airtable";
import { AirtableModel, FieldDescriptor } from "./airtable-model";
import { RecordId, recordIdSchema } from "./special-types";

// Properties that should pass through the Proxy without interception
const PASSTHROUGH_PROPS = new Set<string | symbol>([
	"id",
	"_resolve",
	"_assign",
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
 * A reference to a linked Airtable record.
 * Supports implicit thenable syntax: `await child.parent` fetches the linked record.
 * Supports chaining: `await child.parent.grandparent` fetches the parent, then its grandparent.
 */
export class LinkedRecord<Mdl extends AirtableModel<FieldSet, unknown, keyof FieldSet>> {
	/** The ID of the linked record. This is the value Airtable actually stores in the linked record field. */
	private _id?: RecordId;
	private record?: Mdl;
	private modelCtor?: (id: RecordId, config?: AirtableOptions & { baseId: string }) => Mdl;
	private onDirty?: () => void;
	private __configBaseId?: string;
	private __configOptions?: AirtableOptions;
	private linkedModelClass?: any;

	constructor(
		recordId?: RecordId,
		modelCtor?: (id: RecordId, config?: AirtableOptions & { baseId: string }) => Mdl,
		onDirty?: () => void,
		baseId?: string,
		options?: AirtableOptions,
		linkedModelClass?: any,
	) {
		this._id = recordIdSchema.optional().parse(recordId);
		this.modelCtor = modelCtor;
		this.onDirty = onDirty;
		this.__configBaseId = baseId;
		this.__configOptions = options;
		this.linkedModelClass = linkedModelClass;
	}

	public get id(): RecordId | undefined {
		return this._id;
	}
	public set id(value: RecordId | undefined) {
		this._id = value;
		this.onDirty?.();
	}

	/** @internal Retrieves the linked record. Caches the result for future calls. */
	public async _resolve(fetch: boolean = false): Promise<Mdl | undefined> {
		if (!this._id) return undefined;
		if (this.record === undefined || fetch) {
			const config = this.__configBaseId ? { baseId: this.__configBaseId, ...this.__configOptions } : undefined;
			this.record = this.modelCtor!(this.id!, config);
			await this.record.fetch();
		}
		return this.record;
	}

	/** Makes LinkedRecord thenable: `await linkedRecord` resolves the linked record. */
	public then<TResult1 = Mdl | undefined, TResult2 = never>(
		onfulfilled?: ((value: Mdl | undefined) => TResult1 | PromiseLike<TResult1>) | null,
		onrejected?: ((reason: any) => TResult2 | PromiseLike<TResult2>) | null,
	): PromiseLike<TResult1 | TResult2> {
		return this._resolve().then(onfulfilled, onrejected);
	}

	/** @internal Sets the linked record value and updates the associated ID. */
	public _assign(value: Mdl): void {
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
 * A reference to linked Airtable records.
 * Supports implicit thenable syntax: `await linkedRecords` resolves the linked records.
 */
export class LinkedRecords<Mdl extends AirtableModel<FieldSet, unknown, keyof FieldSet>> {
	/** The IDs of the linked records. These are the values Airtable actually stores in the linked record field. */
	private _ids?: RecordId[];
	private records?: Mdl[];
	private modelCtor?: (id: RecordId, config?: AirtableOptions & { baseId: string }) => Mdl;
	private onDirty?: () => void;
	private __configBaseId?: string;
	private __configOptions?: AirtableOptions;

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

	/** @internal Retrieves the linked records. Caches the result for future calls. */
	public async _resolve(fetch: boolean = false): Promise<Mdl[]> {
		if (this.records === undefined || fetch) {
			const config = this.__configBaseId ? { baseId: this.__configBaseId, ...this.__configOptions } : undefined;
			this.records = this.ids?.map((id) => this.modelCtor!(id, config)) ?? [];
			await Promise.all(this.records.map((record) => record.fetch()));
		}
		return this.records;
	}

	/** Makes LinkedRecords thenable: `await linkedRecords` resolves the linked records. */
	public then<TResult1 = Mdl[], TResult2 = never>(
		onfulfilled?: ((value: Mdl[]) => TResult1 | PromiseLike<TResult1>) | null,
		onrejected?: ((reason: any) => TResult2 | PromiseLike<TResult2>) | null,
	): PromiseLike<TResult1 | TResult2> {
		return this._resolve().then(onfulfilled, onrejected);
	}

	/** @internal Sets the linked record values and updates the associated IDs. */
	public _assign(values: Mdl[]): void {
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

/**
 * Wraps a LinkedRecord in a Proxy that intercepts property access for chaining.
 * Accessing a linked field name on the proxy returns a chainable, thenable promise.
 */
export function wrapLinkedRecordProxy<Mdl extends AirtableModel<FieldSet, unknown, keyof FieldSet>>(
	lr: LinkedRecord<Mdl>,
): LinkedRecord<Mdl> {
	const modelClass = (lr as any).linkedModelClass;
	if (!modelClass) return lr;

	return new Proxy(lr, {
		get(target, prop, receiver) {
			if (typeof prop === "symbol" || PASSTHROUGH_PROPS.has(prop)) {
				return Reflect.get(target, prop, receiver);
			}

			const desc: FieldDescriptor | undefined = modelClass.getFieldDescriptor?.(prop as string);
			if (desc && (desc.fieldType === "linkedRecord" || desc.fieldType === "linkedRecords")) {
				return createChainLink(() => target._resolve(), prop as string, desc);
			}

			return Reflect.get(target, prop, receiver);
		},
	});
}

/**
 * Creates a thenable chain link that resolves the parent, accesses a field, and resolves that too.
 * For single linked fields, the result is further chainable via Proxy.
 */
function createChainLink(parentResolver: () => Promise<any>, fieldName: string, desc: FieldDescriptor): any {
	const resolution = parentResolver().then(async (parentModel: any) => {
		if (!parentModel) {
			return desc.fieldType === "linkedRecords" ? [] : undefined;
		}
		const field = parentModel[fieldName];
		if (!field) {
			return desc.fieldType === "linkedRecords" ? [] : undefined;
		}
		if (field instanceof LinkedRecord || field instanceof LinkedRecords) {
			return field._resolve();
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
 * `await chainablePromise.someField` resolves the promise, then accesses someField.
 */
function createChainablePromise(promise: Promise<any>, modelClass: any): any {
	return new Proxy(promise, {
		get(target, prop, receiver) {
			if (prop === "then" || prop === "catch" || prop === "finally" || typeof prop === "symbol") {
				return Reflect.get(target, prop, receiver);
			}

			const desc: FieldDescriptor | undefined = modelClass.getFieldDescriptor?.(prop as string);
			if (desc && (desc.fieldType === "linkedRecord" || desc.fieldType === "linkedRecords")) {
				const nextPromise = target.then(async (model: any) => {
					if (!model) {
						return desc.fieldType === "linkedRecords" ? [] : undefined;
					}
					const field = model[prop];
					if (!field) {
						return desc.fieldType === "linkedRecords" ? [] : undefined;
					}
					if (field instanceof LinkedRecord || field instanceof LinkedRecords) {
						return field._resolve();
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

// ============================================================
// Type utilities for chainable linked records
// ============================================================

type AnyModel = AirtableModel<FieldSet, unknown, keyof FieldSet>;

/**
 * Extracts linked fields from a model and maps them to chainable thenables.
 * Depth-limited to 4 levels to prevent TS2589 on circular schemas.
 */
export type ChainableFields<Mdl, Depth extends unknown[] = []> = Depth["length"] extends 4
	? Record<string, never>
	: {
			[K in keyof Mdl as Mdl[K] extends LinkedRecord<any>
				? K
				: Mdl[K] extends LinkedRecords<any>
					? K
					: never]: Mdl[K] extends LinkedRecord<infer R>
				? PromiseLike<R | undefined> & ChainableFields<R, [...Depth, unknown]>
				: Mdl[K] extends LinkedRecords<infer R>
					? PromiseLike<R[]>
					: never;
		};

/**
 * A LinkedRecord that also exposes linked fields of the target model
 * as chainable, thenable properties for deep traversal.
 */
export type ChainableLinkedRecord<Mdl extends AnyModel> = LinkedRecord<Mdl> & ChainableFields<Mdl>;

/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable no-unused-vars */
import { Record as ATRecord, FieldSet, RecordData } from "airtable";
import { CreateRecordData } from "./special_types";

export class AirtableModel<T extends FieldSet> {
	protected record?: ATRecord<T>;
	public id: string;

	constructor(id: string) {
		this.id = id;
	}

	protected writableFields(useFieldIds: boolean = false): Partial<T> {
		return {};
		// To be overridden by subclasses
	}

	protected updateModel(record: ATRecord<T>): void {
		this.record = record;
		// To be overridden by subclasses
	}

	protected updateRecord(): void {
		// To be overridden by subclasses
	}

	public toRecord(): ATRecord<T> {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		return this.record;
	}

	public toRecordData(): RecordData<T> {
		return {
			id: this.id,
			fields: this.toRecord().fields,
		};
	}

	public toCreateRecordData(useFieldIds: boolean = true): CreateRecordData<Partial<T>> {
		return {
			fields: this.writableFields(useFieldIds),
		};
	}

	public toUpdateRecordData(useFieldIds: boolean = false): RecordData<Partial<T>> {
		return {
			id: this.id,
			fields: this.writableFields(useFieldIds),
		};
	}

	/**
	 * Saves the current Airtable record to the server.
	 */
	public async save(): Promise<void> {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		// @ts-ignore
		this.record.fields = this.writableFields();
		this.record = await this.record.save();
		this.updateModel(this.record);
	}

	/**
	 * Fetches the latest data for the current Airtable record from the server, overwriting any unsaved local changes.
	 */
	public async fetch(): Promise<void> {
		if (!this.record) throw new Error("_record is undefined. This means the object was not properly initialized.");
		this.updateRecord();
		this.record = await this.record.fetch();
		this.updateModel(this.record);
	}

	/**
	 * Deletes the current Airtable record to the server.
	 */
	public async delete(): Promise<void> {
		if (!this.record)
			throw new Error("Cannot destroy record: _record is undefined. Please use fromRecord to initialize the instance.");
		await this.record.destroy();
		this.record = undefined;
		this.id = "";
	}
}

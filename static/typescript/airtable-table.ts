/* eslint-disable no-unused-vars */
import { Record as ATRecord, FieldSet, AirtableOptions } from "airtable";
import { AirtableModel } from "./airtable-model";
import { ModelTable } from "./model-table";
import { RecordTable } from "./record-table";

export class AirtableTable<
	FldSt extends FieldSet,
	Mdl extends AirtableModel<FldSt, unknown, keyof FldSt>,
	Vw extends string,
	Fld extends string,
> extends ModelTable<FldSt, Mdl, Vw, Fld> {
	/** A separate instance for dealing with Airtable.js's `Record<FieldSet>` class */
	public record: RecordTable<FldSt, Vw, Fld>;

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
		super(baseId, tableNameOrId, viewNameToIdMap, recordCtor, options);
		this.record = new RecordTable<FldSt, Vw, Fld>(
			baseId,
			tableNameOrId,
			viewNameToIdMap,
			fieldNameToIdMap,
			fieldIdToNameMap,
			writableFieldIds,
			options,
		);
	}
}

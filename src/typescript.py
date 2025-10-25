from pathlib import Path

from src.airtable_meta_types import FIELD_TYPE, AirTableFieldMetadata, AirtableMetadata
from src.helpers import (
    WriteToTypeScriptFile,
    camel_case,
    copy_static_files,
    get_referenced_field,
    get_result_type,
    get_select_options,
    involves_lookup_field,
    involves_rollup_field,
    is_calculated_field,
    is_computed_field,
    is_valid_field,
    options_name,
    property_name,
    sanitize_string,
    upper_case,
    warn_unhandled_airtable_type,
)

all_fields: dict[str, AirTableFieldMetadata] = {}
select_options: dict[str, str] = {}
table_id_name_map: dict[str, str] = {}


def gen_typescript(metadata: AirtableMetadata, base_id: str, verbose: bool, folder: Path):
    for table in metadata["tables"]:
        table_id_name_map[table["id"]] = table["name"]
        for field in table["fields"]:
            all_fields[field["id"]] = field
            options = get_select_options(field)
            if len(options) > 0:
                select_options[field["id"]] = f"{options_name(camel_case(table['name']), camel_case(field['name']))}"

    copy_static_files(folder, "typescript")
    write_types(metadata, verbose, folder)
    write_models(metadata, base_id, verbose, folder)
    write_tables(metadata, verbose, folder)
    write_main_class(metadata, base_id, verbose, folder)
    write_formula_helpers(metadata, verbose, folder)
    write_index(metadata, verbose, folder)


def write_types(metadata: AirtableMetadata, verbose: bool, folder: Path):
    with WriteToTypeScriptFile(path=folder / "dynamic" / "types.ts") as write:
        # Imports
        write.region("IMPORTS")
        write.line('import { Attachment, Collaborator, FieldSet } from "airtable";')
        write.line('import { RecordId } from "../static/special_types";')
        write.endregion()
        write.line_empty()

        # Field Options
        write.region("FIELD OPTIONS")
        for table in metadata["tables"]:
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    write.types(
                        options_name(camel_case(table["name"]), camel_case(sanitize_string(field["name"]))),
                        options,
                        f"Select options for `{sanitize_string(field['name'])}`",
                    )
        write.endregion()

        # Table Types
        for table in metadata["tables"]:
            field_names = [sanitize_string(field["name"]) for field in table["fields"]]
            field_ids = [field["id"] for field in table["fields"]]
            property_names = [property_name(field, folder) for field in table["fields"]]

            write.region(upper_case(table["name"]))

            write.types(f"{camel_case(table['name'])}Field", field_names, f"Field names for `{table['name']}`")
            write.types(f"{camel_case(table['name'])}FieldId", field_ids, f"Field IDs for `{table['name']}`")
            write.types(f"{camel_case(table['name'])}FieldProperty", property_names, f"Property names for `{table['name']}`")

            write.docstring(f"Calculated fields for `{table['name']}`")
            write.str_list(
                f"{camel_case(table['name'])}CalculatedFields",
                [sanitize_string(field["name"]) for field in table["fields"] if is_computed_field(field)],
            )
            write.docstring(f"Calculated fields for `{table['name']}`")
            write.str_list(
                f"{camel_case(table['name'])}CalculatedFieldIds",
                [field["id"] for field in table["fields"] if is_computed_field(field)],
            )
            write.line_empty()

            write.dict_class(
                f"{camel_case(table['name'])}FieldNameIdMapping",
                [(sanitize_string(field["name"]), field["id"]) for field in table["fields"]],
                first_type=f"{camel_case(table['name'])}Field",
                second_type=f"{camel_case(table['name'])}FieldId",
                is_value_string=True,
            )
            write.dict_class(
                f"{camel_case(table['name'])}FieldIdNameMapping",
                [(field["id"], sanitize_string(field["name"])) for field in table["fields"]],
                first_type=f"{camel_case(table['name'])}FieldId",
                second_type=f"{camel_case(table['name'])}Field",
                is_value_string=True,
            )
            write.dict_class(
                f"{camel_case(table['name'])}FieldIdPropertyMapping",
                [(field["id"], property_name(field, folder)) for field in table["fields"]],
                first_type=f"{camel_case(table['name'])}FieldId",
                second_type=f"{camel_case(table['name'])}FieldProperty",
                is_value_string=True,
            )
            write.dict_class(
                f"{camel_case(table['name'])}FieldPropertyIdMapping",
                [(property_name(field, folder), field["id"]) for field in table["fields"]],
                first_type=f"{camel_case(table['name'])}FieldProperty",
                second_type=f"{camel_case(table['name'])}FieldId",
                is_value_string=True,
            )

            write.line(f"export interface {camel_case(table['name'])}FieldSetIds extends FieldSet {{")
            for field in table["fields"]:
                write.property_row(field["id"], typescript_type(field, warn=True, verbose=verbose), optional=True)
            write.line("}")
            write.line_empty()
            write.line(f"export interface {camel_case(table['name'])}FieldSet extends FieldSet {{")
            for field in table["fields"]:
                write.property_row(
                    sanitize_string(field["name"]), typescript_type(field, warn=True, verbose=verbose), is_name_string=True, optional=True
                )
            write.line("}")
            write.line_empty()
            write.line_empty()

            views = table["views"]
            view_names: list[str] = [sanitize_string(view["name"]) for view in views]
            view_ids: list[str] = [view["id"] for view in views]
            write.types(f"{camel_case(table['name'])}View", view_names, f"View names for `{table['name']}`")
            write.types(f"{camel_case(table['name'])}ViewId", view_ids, f"View IDs for `{table['name']}`")
            write.dict_class(
                f"{camel_case(table['name'])}ViewNameIdMapping",
                [(sanitize_string(view["name"]), view["id"]) for view in table["views"]],
                first_type=f"{camel_case(table['name'])}View",
                second_type=f"{camel_case(table['name'])}ViewId",
                is_value_string=True,
            )
            write.dict_class(
                f"{camel_case(table['name'])}ViewIdNameMapping",
                [(view["id"], sanitize_string(view["name"])) for view in table["views"]],
                first_type=f"{camel_case(table['name'])}ViewId",
                second_type=f"{camel_case(table['name'])}View",
                is_value_string=True,
            )

            write.endregion()

        # Table Lists
        table_names = []
        table_ids = []
        for table in metadata["tables"]:
            table_names.append(table["name"])
            table_ids.append(table["id"])

        write.region("TABLES")
        write.types("TableName", table_names)
        write.types("TableId", table_ids)
        write.dict_class(
            "TableNameIdMapping",
            [(table["name"], table["id"]) for table in metadata["tables"]],
            first_type="TableName",
            second_type="TableId",
            is_value_string=True,
        )
        write.dict_class(
            "TableIdNameMapping",
            [(table["id"], table["name"]) for table in metadata["tables"]],
            first_type="TableId",
            second_type="TableName",
            is_value_string=True,
        )
        write.dict_class(
            "TableIdToFieldNameIdMapping",
            [(table["id"], f"{camel_case(table['name'])}FieldNameIdMapping") for table in metadata["tables"]],
            first_type="TableId",
            second_type="Record<string, string>",
        )
        write.endregion()


def write_models(metadata: AirtableMetadata, base_id: str, verbose: bool, folder: Path):
    with WriteToTypeScriptFile(path=folder / "dynamic" / "models.ts") as write:
        # Imports
        write.region("IMPORTS")
        write.line('import { Attachment, Collaborator, FieldSet, Record } from "airtable";')
        write.line('import { AirtableRecord } from "../static/airtable-record";')
        write.line('import { RecordId } from "../static/special_types";')
        write.line('import { getApiKey } from "../static/helpers";')
        write.line("import {")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}FieldSet,")
        for table in metadata["tables"]:
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    write.line_indented(f"{options_name(camel_case(table['name']), camel_case(field['name']))},")
        write.line('} from "./types";')
        write.line("import {")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Table,")
        write.line('} from "./tables";')
        write.endregion()
        write.line_empty()

        # Table Types
        for table in metadata["tables"]:
            write.region(upper_case(table["name"]))

            write.line(f"export class {camel_case(table['name'])}Record extends AirtableRecord<{camel_case(table['name'])}FieldSet> {{")
            for field in table["fields"]:
                write.line_indented(f"public {property_name(field, folder)}?: {typescript_type(field, warn=True, verbose=verbose)};", 1)
            write.line_empty()
            write.line_indented("constructor({")
            write.line_indented("id,", 2)
            for field in table["fields"]:
                write.line_indented(f"{property_name(field, folder)},", 2)
            write.line_indented("}: {", 1)
            write.line_indented("id?: string,", 2)
            for field in table["fields"]:
                write.line_indented(f"{property_name(field, folder)}?: {typescript_type(field, warn=True, verbose=verbose)},", 2)
            write.line_indented("}) {")
            write.line_indented("super(id ?? '');", 2)
            for field in table["fields"]:
                write.line_indented(f"this.{property_name(field, folder)} = {property_name(field, folder)};", 2)
            write.line_indented(
                f"this.record = new Record<{camel_case(table['name'])}FieldSet>(new {camel_case(table['name'])}Table(getApiKey(), '{base_id}')._table, this.id, {{}});",
                2,
            )
            write.line_indented("this.updateRecord();", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(
                f"public static fromRecord(record: Record<{camel_case(table['name'])}FieldSet>): {camel_case(table['name'])}Record {{"
            )
            write.line_indented(f"const instance = new {camel_case(table['name'])}Record(", 2)
            write.line_indented("{ id: record.id },", 3)
            write.line_indented(");", 2)
            write.line_indented("instance.updateModel(record);", 2)
            write.line_indented("return instance;", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"protected writableFields(useFieldIds: boolean = false): Partial<{camel_case(table['name'])}FieldSet> {{")
            write.line_indented(f"const fields: Partial<{camel_case(table['name'])}FieldSet> = {{}};", 2)
            for field in table["fields"]:
                if not is_computed_field(field):
                    write.line_indented(
                        f'fields[useFieldIds ? "{field["id"]}" : "{sanitize_string(field["name"])}"] = this.{property_name(field, folder)};', 2
                    )
            write.line_indented("return fields;", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"protected updateModel(record: Record<{camel_case(table['name'])}FieldSet>) {{")
            write.line_indented("this.record = record;", 2)
            for field in table["fields"]:
                write.line_indented(f'this.{property_name(field, folder)} = record.get("{sanitize_string(field["name"])}");', 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented("protected updateRecord() {")
            write.line_indented("if (!this.record) ", 2)
            write.line_indented(
                'throw new Error("Cannot convert to record: record is undefined. Please use fromRecord to initialize the instance.");', 3
            )
            for field in table["fields"]:
                write.line_indented(f'this.record.set("{sanitize_string(field["name"])}", this.{property_name(field, folder)});', 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line("}")
            write.endregion()


def write_tables(metadata: AirtableMetadata, verbose: bool, folder: Path):
    with WriteToTypeScriptFile(path=folder / "dynamic" / "tables.ts") as write:
        # Imports
        write.region("IMPORTS")
        write.line('import { AirtableTable } from "../static/airtable-table";')
        write.line("import {")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}FieldSet,")
            write.line_indented(f"{camel_case(table['name'])}Field,")
            write.line_indented(f"{camel_case(table['name'])}View,")
            write.line_indented(f"{camel_case(table['name'])}ViewNameIdMapping,")
        write.line('} from "./types";')
        write.line("import {")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Record,")
        write.line('} from "./models";')
        write.endregion()
        write.line_empty()

        # Table Types
        for table in metadata["tables"]:
            write.region(upper_case(table["name"]))

            write.line(
                f"export class {camel_case(table['name'])}Table extends AirtableTable<{camel_case(table['name'])}FieldSet, {camel_case(table['name'])}Record, {camel_case(table['name'])}View, {camel_case(table['name'])}Field> {{"
            )
            write.line_indented("constructor(apiKey: string, baseId: string) {")
            write.line_indented(
                f'super(apiKey, baseId, "{table["name"]}", {camel_case(table["name"])}ViewNameIdMapping, {camel_case(table["name"])}Record.fromRecord);',
                2,
            )
            write.line_indented("}")
            write.line("}")

            write.endregion()


def write_main_class(metadata: AirtableMetadata, base_id: str, verbose: bool, folder: Path):
    with WriteToTypeScriptFile(path=folder / "dynamic" / "airtable-main.ts") as write:
        # Imports
        write.line('import { getApiKey } from "../static/helpers";')
        write.line("import {")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Table,")
        write.line('} from "./tables";')
        write.line_empty()

        write.line("export class Airtable {")
        for table in metadata["tables"]:
            write.line_indented(f"public {property_name(table, folder, use_custom=False)}: {camel_case(table['name'])}Table;")
        write.line_empty()
        write.line_indented("constructor() {")
        write.line_indented("const apiKey = getApiKey();", 2)
        write.line_indented(f"const baseId = '{base_id}';", 2)
        for table in metadata["tables"]:
            write.line_indented(f"this.{property_name(table, folder, use_custom=False)} = new {camel_case(table['name'])}Table(apiKey, baseId);", 2)
        write.line_indented("}")
        write.line("}")


def write_formula_helpers(metadata: AirtableMetadata, verbose: bool, folder: Path):
    with WriteToTypeScriptFile(path=folder / "dynamic" / "formula.ts") as write:
        # Imports
        write.region("IMPORTS")
        write.line("import {")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Field,")
            write.line_indented(f"{camel_case(table['name'])}Fields,")
            write.line_indented(f"{camel_case(table['name'])}FieldNameIdMapping,")
        write.line("} from './types';")
        write.line("import { validateKey } from '../static/helpers';")
        write.line("import { AttachmentsField, BooleanField, DateField, NumberField, TextField } from '../static/formula';")
        write.line_empty()

        # Class
        for table in metadata["tables"]:
            write.region(upper_case(table["name"]))

            def write_formula(type: str):
                write.line(f"export class {camel_case(table['name'])}{type} extends {type} {{")
                write.line_indented(f"constructor(name: {camel_case(table['name'])}Field) {{")
                write.line_indented(f"validateKey(name, {camel_case(table['name'])}Fields);", 2)
                write.line_indented(f"super(name, {camel_case(table['name'])}FieldNameIdMapping);", 2)
                write.line_indented("}", 1)
                write.line("}")
                write.line_empty()
                write.line_empty()

            write_formula("AttachmentsField")
            write_formula("BooleanField")
            write_formula("DateField")
            write_formula("NumberField")
            write_formula("TextField")

            write.endregion()


def write_index(metadata: AirtableMetadata, verbose: bool, folder: Path):
    with WriteToTypeScriptFile(path=folder / "dynamic" / "index.ts") as write:
        write.line('export * from "./airtable-main";')
        write.line('export * from "./tables";')
        write.line('export * from "./types";')
        write.line('export * from "./models";')
        write.line("")

    with WriteToTypeScriptFile(path=folder / "index.ts") as write:
        write.line('export * from "./dynamic";')
        write.line('export * from "./static/formula";')
        write.line("")


def typescript_type(field: AirTableFieldMetadata, verbose: bool = False, warn: bool = False) -> str:
    """Returns the appropriate Python type for a given Airtable field."""

    airtable_type: FIELD_TYPE = field["type"]
    ts_type: str = "Any"

    # With calculated fields, we want to know the type of the result
    if is_calculated_field(field):
        airtable_type = get_result_type(field)

    match airtable_type:
        case "singleLineText" | "multilineText" | "url" | "richText" | "email" | "phoneNumber" | "barcode":
            ts_type = "string"
        case "checkbox":
            ts_type = "boolean"
        case "date" | "dateTime" | "createdTime" | "lastModifiedTime":
            ts_type = "string"
        case "count" | "autoNumber" | "percent" | "currency" | "number":
            ts_type = "number"
        case "duration":
            ts_type = "number"
        case "multipleRecordLinks":
            ts_type = "RecordId[]"
        case "multipleAttachments":
            ts_type = "Attachment[]"
        case "singleCollaborator" | "lastModifiedBy" | "createdBy":
            ts_type = "Collaborator"
        case "singleSelect":
            referenced_field = get_referenced_field(field, all_fields)
            if field["id"] in select_options:
                ts_type = select_options[field["id"]]
            elif referenced_field and referenced_field["type"] == "singleSelect" and referenced_field["id"] in select_options:
                ts_type = select_options[referenced_field["id"]]
            else:
                if warn:
                    warn_unhandled_airtable_type(field, airtable_type, verbose)
                ts_type = "any"
        case "multipleSelects":
            if field["id"] in select_options:
                ts_type = f"{select_options[field['id']]}[]"
            else:
                if warn:
                    warn_unhandled_airtable_type(field, airtable_type, verbose)
                ts_type = "any"
        case "button":
            ts_type = "string"  # Unsupported by Airtable's JS library
        case _:
            if not is_valid_field(field):
                if warn:
                    warn_unhandled_airtable_type(field, airtable_type, verbose)
                ts_type = "any"

    # TODO: In the case of some calculated fields, sometimes the result is just too unpredictable.
    # Although the type prediction is basically right, I haven't figured out how to predict if
    # it's a list or not, and sometimes the result is a list with a single null value.
    # I don't love this, but it works. Pydantic throws validation errors without it.
    # - this might have something to do with select fields... Those can be null
    if not ts_type.endswith("[]") and ts_type not in ("number", "boolean"):  # TODO - why is this not allowed in Airtable JS library?
        if involves_lookup_field(field, all_fields) or involves_rollup_field(field, all_fields):
            ts_type = f"{ts_type}[]"

    return ts_type

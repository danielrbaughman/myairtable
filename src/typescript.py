import shutil
from pathlib import Path

from .helpers import (
    WriteToTypeScriptFile,
    copy_static_files,
    detect_duplicate_property_names,
    get_referenced_field,
    get_result_type,
    get_select_options,
    involves_lookup_field,
    involves_rollup_field,
    is_calculated_field,
    is_computed_field,
    is_valid_field,
    options_name,
    property_name_camel,
    sanitize_string,
    upper_case,
    warn_unhandled_airtable_type,
)
from .meta_types import BaseMetadata, FieldMetadata, FieldType

all_fields: dict[str, FieldMetadata] = {}
select_options: dict[str, str] = {}
table_id_name_map: dict[str, str] = {}


def gen_typescript(metadata: BaseMetadata, base_id: str, folder: Path):
    for table in metadata["tables"]:
        table_id_name_map[table["id"]] = table["name"]
        for field in table["fields"]:
            all_fields[field["id"]] = field
            options = get_select_options(field)
            if len(options) > 0:
                select_options[field["id"]] = f"{options_name(property_name_camel(table, folder), property_name_camel(field, folder))}"
        detect_duplicate_property_names(table, folder)

    dynamic_folder = folder / "dynamic"
    if dynamic_folder.exists():
        shutil.rmtree(dynamic_folder)
        dynamic_folder.mkdir(parents=True, exist_ok=True)

    static_folder = folder / "static"
    if static_folder.exists():
        shutil.rmtree(static_folder)
        static_folder.mkdir(parents=True, exist_ok=True)

    copy_static_files(folder, "typescript")
    write_types(metadata, folder)
    write_models(metadata, base_id, folder)
    write_tables(metadata, folder)
    write_main_class(metadata, base_id, folder)
    write_formula_helpers(metadata, folder)
    write_index(metadata, folder)


def write_types(metadata: BaseMetadata, folder: Path):
    # Create types directory
    types_dir = folder / "dynamic" / "types"
    types_dir.mkdir(parents=True, exist_ok=True)

    # Write individual table type files
    for table in metadata["tables"]:
        with WriteToTypeScriptFile(path=types_dir / f"{property_name_camel(table, folder)}.ts") as write:
            # Imports
            write.region("IMPORTS")
            write.line('import { Attachment, Collaborator, FieldSet } from "airtable";')
            write.line('import { RecordId } from "../../static/special_types";')
            write.endregion()
            write.line_empty()

            # Field Options
            write.region("FIELD OPTIONS")
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    write.types(
                        options_name(property_name_camel(table, folder), property_name_camel(field, folder)),
                        options,
                        f"Select options for `{sanitize_string(field['name'])}`",
                    )
            write.endregion()

            # Table Type
            field_names = [sanitize_string(field["name"]) for field in table["fields"]]
            field_ids = [field["id"] for field in table["fields"]]
            property_names = [property_name_camel(field, folder) for field in table["fields"]]

            write.region(upper_case(table["name"]))

            write.types(f"{property_name_camel(table, folder)}Field", field_names, f"Field names for `{table['name']}`")
            write.types(f"{property_name_camel(table, folder)}FieldId", field_ids, f"Field IDs for `{table['name']}`")
            write.types(f"{property_name_camel(table, folder)}FieldProperty", property_names, f"Property names for `{table['name']}`")

            write.docstring(f"Calculated fields for `{table['name']}`")
            write.str_list(
                f"{property_name_camel(table, folder)}CalculatedFields",
                [sanitize_string(field["name"]) for field in table["fields"] if is_computed_field(field)],
            )
            write.docstring(f"Calculated fields for `{table['name']}`")
            write.str_list(
                f"{property_name_camel(table, folder)}CalculatedFieldIds",
                [field["id"] for field in table["fields"] if is_computed_field(field)],
            )
            write.line_empty()

            write.dict_class(
                f"{property_name_camel(table, folder)}FieldNameIdMapping",
                [(sanitize_string(field["name"]), field["id"]) for field in table["fields"]],
                first_type=f"{property_name_camel(table, folder)}Field",
                second_type=f"{property_name_camel(table, folder)}FieldId",
                is_value_string=True,
            )
            write.dict_class(
                f"{property_name_camel(table, folder)}FieldIdNameMapping",
                [(field["id"], sanitize_string(field["name"])) for field in table["fields"]],
                first_type=f"{property_name_camel(table, folder)}FieldId",
                second_type=f"{property_name_camel(table, folder)}Field",
                is_value_string=True,
            )
            write.dict_class(
                f"{property_name_camel(table, folder)}FieldIdPropertyMapping",
                [(field["id"], property_name_camel(field, folder)) for field in table["fields"]],
                first_type=f"{property_name_camel(table, folder)}FieldId",
                second_type=f"{property_name_camel(table, folder)}FieldProperty",
                is_value_string=True,
            )
            write.dict_class(
                f"{property_name_camel(table, folder)}FieldPropertyIdMapping",
                [(property_name_camel(field, folder), field["id"]) for field in table["fields"]],
                first_type=f"{property_name_camel(table, folder)}FieldProperty",
                second_type=f"{property_name_camel(table, folder)}FieldId",
                is_value_string=True,
            )

            write.line(f"export interface {property_name_camel(table, folder)}FieldSetIds extends FieldSet {{")
            for field in table["fields"]:
                write.property_row(field["id"], typescript_type(table["name"], field, warn=True), optional=True)
            write.line("}")
            write.line_empty()
            write.line(f"export interface {property_name_camel(table, folder)}FieldSet extends FieldSet {{")
            for field in table["fields"]:
                write.property_row(
                    sanitize_string(field["name"]), typescript_type(table["name"], field, warn=True), is_name_string=True, optional=True
                )
            write.line("}")
            write.line_empty()
            write.line_empty()

            views = table["views"]
            view_names: list[str] = [sanitize_string(view["name"]) for view in views]
            view_ids: list[str] = [view["id"] for view in views]
            write.types(f"{property_name_camel(table, folder)}View", view_names, f"View names for `{table['name']}`")
            write.types(f"{property_name_camel(table, folder)}ViewId", view_ids, f"View IDs for `{table['name']}`")
            write.dict_class(
                f"{property_name_camel(table, folder)}ViewNameIdMapping",
                [(sanitize_string(view["name"]), view["id"]) for view in table["views"]],
                first_type=f"{property_name_camel(table, folder)}View",
                second_type=f"{property_name_camel(table, folder)}ViewId",
                is_value_string=True,
            )
            write.dict_class(
                f"{property_name_camel(table, folder)}ViewIdNameMapping",
                [(view["id"], sanitize_string(view["name"])) for view in table["views"]],
                first_type=f"{property_name_camel(table, folder)}ViewId",
                second_type=f"{property_name_camel(table, folder)}View",
                is_value_string=True,
            )

            write.endregion()

    # Write global tables file
    with WriteToTypeScriptFile(path=types_dir / "_tables.ts") as write:
        # Import field name ID mappings from individual table files
        write.region("IMPORTS")
        for table in metadata["tables"]:
            write.line(f"import {{ {property_name_camel(table, folder)}FieldNameIdMapping }} from './{property_name_camel(table, folder)}';")
        write.endregion()
        write.line_empty()

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
            [(table["id"], f"{property_name_camel(table, folder)}FieldNameIdMapping") for table in metadata["tables"]],
            first_type="TableId",
            second_type="Record<string, string>",
        )
        write.endregion()

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=types_dir / "index.ts") as write:
        for table in metadata["tables"]:
            write.line(f"export * from './{property_name_camel(table, folder)}';")
        write.line("export * from './_tables';")
        write.line("")


def write_models(metadata: BaseMetadata, base_id: str, folder: Path):
    # Create models directory
    models_dir = folder / "dynamic" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    # Write individual table model files
    for table in metadata["tables"]:
        with WriteToTypeScriptFile(path=models_dir / f"{property_name_camel(table, folder)}.ts") as write:
            # Imports
            write.region("IMPORTS")
            write.line('import { Attachment, Collaborator, FieldSet, Record } from "airtable";')
            write.line('import { AirtableRecord } from "../../static/airtable-record";')
            write.line('import { RecordId } from "../../static/special_types";')
            write.line('import { getApiKey } from "../../static/helpers";')

            # Import types for this table
            write.line("import {")
            write.line_indented(f"{property_name_camel(table, folder)}FieldSet,")
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    write.line_indented(f"{options_name(property_name_camel(table, folder), property_name_camel(field, folder))},")
            write.line('} from "../types";')

            # Import table class for this table
            write.line(f"import {{ {property_name_camel(table, folder)}Table }} from '../tables/{property_name_camel(table, folder)}';")
            write.endregion()
            write.line_empty()

            # Table Model
            write.region(upper_case(table["name"]))

            write.line(
                f"export class {property_name_camel(table, folder)}Record extends AirtableRecord<{property_name_camel(table, folder)}FieldSet> {{"
            )
            for field in table["fields"]:
                write.line_indented(f"public {property_name_camel(field, folder)}?: {typescript_type(table['name'], field, warn=True)};", 1)
            write.line_empty()
            write.line_indented("constructor({")
            write.line_indented("id,", 2)
            for field in table["fields"]:
                write.line_indented(f"{property_name_camel(field, folder)},", 2)
            write.line_indented("}: {", 1)
            write.line_indented("id?: string,", 2)
            for field in table["fields"]:
                write.line_indented(f"{property_name_camel(field, folder)}?: {typescript_type(table['name'], field, warn=True)},", 2)
            write.line_indented("}) {")
            write.line_indented("super(id ?? '');", 2)
            for field in table["fields"]:
                write.line_indented(f"this.{property_name_camel(field, folder)} = {property_name_camel(field, folder)};", 2)
            write.line_indented(
                f"this.record = new Record<{property_name_camel(table, folder)}FieldSet>(new {property_name_camel(table, folder)}Table(getApiKey(), '{base_id}')._table, this.id, {{}});",
                2,
            )
            write.line_indented("this.updateRecord();", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(
                f"public static fromRecord(record: Record<{property_name_camel(table, folder)}FieldSet>): {property_name_camel(table, folder)}Record {{"
            )
            write.line_indented(f"const instance = new {property_name_camel(table, folder)}Record(", 2)
            write.line_indented("{ id: record.id },", 3)
            write.line_indented(");", 2)
            write.line_indented("instance.updateModel(record);", 2)
            write.line_indented("return instance;", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"protected writableFields(useFieldIds: boolean = false): Partial<{property_name_camel(table, folder)}FieldSet> {{")
            write.line_indented(f"const fields: Partial<{property_name_camel(table, folder)}FieldSet> = {{}};", 2)
            for field in table["fields"]:
                if not is_computed_field(field):
                    write.line_indented(
                        f'fields[useFieldIds ? "{field["id"]}" : "{sanitize_string(field["name"])}"] = this.{property_name_camel(field, folder)};', 2
                    )
            write.line_indented("return fields;", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"protected updateModel(record: Record<{property_name_camel(table, folder)}FieldSet>) {{")
            write.line_indented("this.record = record;", 2)
            for field in table["fields"]:
                write.line_indented(f'this.{property_name_camel(field, folder)} = record.get("{sanitize_string(field["name"])}");', 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented("protected updateRecord() {")
            write.line_indented("if (!this.record) ", 2)
            write.line_indented(
                'throw new Error("Cannot convert to record: record is undefined. Please use fromRecord to initialize the instance.");', 3
            )
            for field in table["fields"]:
                write.line_indented(f'this.record.set("{sanitize_string(field["name"])}", this.{property_name_camel(field, folder)});', 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line("}")
            write.endregion()

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=models_dir / "index.ts") as write:
        for table in metadata["tables"]:
            write.line(f"export * from './{property_name_camel(table, folder)}';")
        write.line("")


def write_tables(metadata: BaseMetadata, folder: Path):
    # Create tables directory
    tables_dir = folder / "dynamic" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    # Write individual table files
    for table in metadata["tables"]:
        with WriteToTypeScriptFile(path=tables_dir / f"{property_name_camel(table, folder)}.ts") as write:
            # Imports
            write.region("IMPORTS")
            write.line('import { AirtableTable } from "../../static/airtable-table";')
            write.line("import {")
            write.line_indented(f"{property_name_camel(table, folder)}FieldSet,")
            write.line_indented(f"{property_name_camel(table, folder)}Field,")
            write.line_indented(f"{property_name_camel(table, folder)}View,")
            write.line_indented(f"{property_name_camel(table, folder)}ViewNameIdMapping,")
            write.line('} from "../types";')
            write.line(f"import {{ {property_name_camel(table, folder)}Record }} from '../models/{property_name_camel(table, folder)}';")
            write.endregion()
            write.line_empty()

            # Table Class
            write.region(upper_case(table["name"]))

            write.line(
                f"export class {property_name_camel(table, folder)}Table extends AirtableTable<{property_name_camel(table, folder)}FieldSet, {property_name_camel(table, folder)}Record, {property_name_camel(table, folder)}View, {property_name_camel(table, folder)}Field> {{"
            )
            write.line_indented("constructor(apiKey: string, baseId: string) {")
            write.line_indented(
                f'super(apiKey, baseId, "{table["name"]}", {property_name_camel(table, folder)}ViewNameIdMapping, {property_name_camel(table, folder)}Record.fromRecord);',
                2,
            )
            write.line_indented("}")
            write.line("}")

            write.endregion()

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=tables_dir / "index.ts") as write:
        for table in metadata["tables"]:
            write.line(f"export * from './{property_name_camel(table, folder)}';")
        write.line("")


def write_main_class(metadata: BaseMetadata, base_id: str, folder: Path):
    with WriteToTypeScriptFile(path=folder / "dynamic" / "airtable-main.ts") as write:
        # Imports
        write.line('import { getApiKey } from "../static/helpers";')
        write.line("import {")
        for table in metadata["tables"]:
            write.line_indented(f"{property_name_camel(table, folder)}Table,")
        write.line('} from "./tables";')
        write.line_empty()

        write.line("export class Airtable {")
        for table in metadata["tables"]:
            write.line_indented(f"public {property_name_camel(table, folder, use_custom=False)}: {property_name_camel(table, folder)}Table;")
        write.line_empty()
        write.line_indented("constructor() {")
        write.line_indented("const apiKey = getApiKey();", 2)
        write.line_indented(f"const baseId = '{base_id}';", 2)
        for table in metadata["tables"]:
            write.line_indented(
                f"this.{property_name_camel(table, folder, use_custom=False)} = new {property_name_camel(table, folder)}Table(apiKey, baseId);", 2
            )
        write.line_indented("}")
        write.line("}")


def write_formula_helpers(metadata: BaseMetadata, folder: Path):
    # Create formulas directory
    formulas_dir = folder / "dynamic" / "formulas"
    formulas_dir.mkdir(parents=True, exist_ok=True)

    # Write individual formula helper files
    for table in metadata["tables"]:
        with WriteToTypeScriptFile(path=formulas_dir / f"{property_name_camel(table, folder)}.ts") as write:
            # Imports
            write.region("IMPORTS")
            write.line("import {")
            write.line_indented(f"{property_name_camel(table, folder)}Field,")
            write.line_indented(f"{property_name_camel(table, folder)}Fields,")
            write.line_indented(f"{property_name_camel(table, folder)}FieldNameIdMapping,")
            write.line('} from "../types";')
            write.line('import { validateKey } from "../../static/helpers";')
            write.line('import { AttachmentsField, BooleanField, DateField, NumberField, TextField } from "../../static/formula";')
            write.endregion()
            write.line_empty()

            # Formula Classes
            write.region(upper_case(table["name"]))

            def write_formula(type: str):
                write.line(f"export class {property_name_camel(table, folder)}{type} extends {type} {{")
                write.line_indented(f"constructor(name: {property_name_camel(table, folder)}Field) {{")
                write.line_indented(f"validateKey(name, {property_name_camel(table, folder)}Fields);", 2)
                write.line_indented(f"super(name, {property_name_camel(table, folder)}FieldNameIdMapping);", 2)
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

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=formulas_dir / "index.ts") as write:
        for table in metadata["tables"]:
            write.line(f"export * from './{property_name_camel(table, folder)}';")
        write.line("")


def write_index(metadata: BaseMetadata, folder: Path):
    with WriteToTypeScriptFile(path=folder / "dynamic" / "index.ts") as write:
        write.line('export * from "./airtable-main";')
        write.line('export * from "./tables";')
        write.line('export * from "./types";')
        write.line('export * from "./models";')
        write.line('export * from "./formulas";')
        write.line("")

    with WriteToTypeScriptFile(path=folder / "index.ts") as write:
        write.line('export * from "./dynamic";')
        write.line('export * from "./static/formula";')
        write.line("")


def typescript_type(table_name: str, field: FieldMetadata, warn: bool = False) -> str:
    """Returns the appropriate Python type for a given Airtable field."""

    airtable_type: FieldType = field["type"]
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
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = "any"
        case "multipleSelects":
            if field["id"] in select_options:
                ts_type = f"{select_options[field['id']]}[]"
            else:
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = "any"
        case "button":
            ts_type = "string"  # Unsupported by Airtable's JS library
        case _:
            if not is_valid_field(field):
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = "any"

    # TODO: In the case of some calculated fields, sometimes the result is just too unpredictable.
    # Although the type prediction is basically right, I haven't figured out how to predict if
    # it's a list or not, and sometimes the result is a list with a single null value.
    if not ts_type.endswith("[]") and ts_type not in ("number", "boolean"):  # TODO - why is this not allowed in Airtable JS library?
        if involves_lookup_field(field, all_fields) or involves_rollup_field(field, all_fields):
            ts_type = f"{ts_type}[]"

    return ts_type

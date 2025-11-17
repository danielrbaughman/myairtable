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
    property_name_pascal,
    sanitize_string,
    # upper_case,
    warn_unhandled_airtable_type,
)
from .meta_types import BaseMetadata, FieldMetadata, FieldType

all_fields: dict[str, FieldMetadata] = {}
select_options_types: dict[str, str] = {}
select_options_lists: dict[str, str] = {}
table_id_name_map: dict[str, str] = {}


def gen_typescript(metadata: BaseMetadata, base_id: str, folder: Path):
    for table in metadata["tables"]:
        table_id_name_map[table["id"]] = table["name"]
        for field in table["fields"]:
            all_fields[field["id"]] = field
            options = get_select_options(field)
            if len(options) > 0:
                table_name = property_name_pascal(table, folder)
                field_name = property_name_pascal(field, folder)
                select_options_types[field["id"]] = options_name(table_name, field_name)
                select_options_lists[field["id"]] = f"{options_name(table_name, field_name)}s"
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
    write_interfaces(metadata, base_id, folder)
    write_zod_schemas(metadata, base_id, folder)
    write_tables(metadata, folder)
    # write_main_class(metadata, base_id, folder)
    write_formula_helpers(metadata, folder)
    write_index(metadata, folder)


def write_types(metadata: BaseMetadata, folder: Path):
    with WriteToTypeScriptFile(path=folder / "dynamic" / "types" / "_tables.ts") as write:
        table_names = [table["name"] for table in metadata["tables"]]
        table_ids = [table["id"] for table in metadata["tables"]]

        write.region("TABLES")
        write.types("TableName", table_names)
        write.types("TableId", table_ids)
        write.dict_class(
            "TableNameIdMapping",
            [(table["name"], table["id"]) for table in metadata["tables"]],
            first_type="TableName",
            second_type="TableId",
            is_key_string=True,
            is_value_string=True,
        )
        write.dict_class(
            "TableIdNameMapping",
            [(table["id"], table["name"]) for table in metadata["tables"]],
            first_type="TableId",
            second_type="TableName",
            is_value_string=True,
        )
        # write.dict_class(
        #     "TableIdToFieldNameIdMapping",
        #     [(table["id"], f"{property_name_camel(table, folder)}FieldNameIdMapping") for table in metadata["tables"]],
        #     first_type="TableId",
        #     second_type="Record<string, string>",
        # )
        write.endregion()

    for table in metadata["tables"]:
        table_filename = property_name_camel(table, folder)
        table_name = property_name_pascal(table, folder)

        with WriteToTypeScriptFile(path=folder / "dynamic" / "types" / f"{table_filename}.ts") as write:
            # Imports
            write.region("IMPORTS")
            write.line('import { Attachment, Collaborator, FieldSet } from "airtable";')
            write.line('import { RecordId } from "../../static/special-types";')
            write.endregion()
            write.line_empty()

            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    write.types(
                        options_name(property_name_pascal(table, folder), property_name_pascal(field, folder)),
                        options,
                        f"Select options for `{sanitize_string(field['name'])}`",
                    )
            write.line_empty()

            field_names = [sanitize_string(field["name"]) for field in table["fields"]]
            field_ids = [field["id"] for field in table["fields"]]
            property_names = [property_name_camel(field, folder) for field in table["fields"]]

            write.types(f"{table_name}Field", field_names, f"Field names for `{table['name']}`")
            write.types(f"{table_name}FieldId", field_ids, f"Field IDs for `{table['name']}`")
            write.types(f"{table_name}FieldProperty", property_names, f"Property names for `{table['name']}`")

            write.docstring(f"Calculated fields for `{table['name']}`")
            write.str_list(
                f"{table_name}CalculatedFields",
                [sanitize_string(field["name"]) for field in table["fields"] if is_computed_field(field)],
            )
            write.docstring(f"Calculated fields for `{table['name']}`")
            write.str_list(
                f"{table_name}CalculatedFieldIds",
                [field["id"] for field in table["fields"] if is_computed_field(field)],
            )
            write.line_empty()

            write.dict_class(
                f"{table_name}FieldNameIdMapping",
                [(sanitize_string(field["name"]), field["id"]) for field in table["fields"]],
                first_type=f"{table_name}Field",
                second_type=f"{table_name}FieldId",
                is_value_string=True,
                is_key_string=True,
            )
            write.dict_class(
                f"{table_name}FieldIdNameMapping",
                [(field["id"], sanitize_string(field["name"])) for field in table["fields"]],
                first_type=f"{table_name}FieldId",
                second_type=f"{table_name}Field",
                is_value_string=True,
            )
            write.dict_class(
                f"{table_name}FieldIdPropertyMapping",
                [(field["id"], property_name_camel(field, folder)) for field in table["fields"]],
                first_type=f"{table_name}FieldId",
                second_type=f"{table_name}FieldProperty",
                is_value_string=True,
            )
            write.dict_class(
                f"{table_name}FieldPropertyIdMapping",
                [(property_name_camel(field, folder), field["id"]) for field in table["fields"]],
                first_type=f"{table_name}FieldProperty",
                second_type=f"{table_name}FieldId",
                is_value_string=True,
            )
            write.line(f"export const {table_name}FieldPropertyTypeMapping = {{")
            for field in table["fields"]:
                write.line_indented(
                    f"{property_name_camel(field, folder)}: {airtable_ts_type(table['name'], field, warn=True)},",
                )
            write.line("} as const;")
            write.line_empty()

            write.line(f"export interface {table_name}FieldSetIds extends FieldSet {{")
            for field in table["fields"]:
                ts_type = typescript_type(table["name"], field)
                write.property_row(field["id"], ts_type, optional=True)
            write.line("}")
            write.line_empty()
            write.line(f"export interface {table_name}FieldSet extends FieldSet {{")
            for field in table["fields"]:
                ts_type = typescript_type(table["name"], field)
                name = sanitize_string(field["name"])
                write.property_row(name, ts_type, is_name_string=True, optional=True)
            write.line("}")
            write.line_empty()
            write.line_empty()

            views = table["views"]
            view_names: list[str] = [sanitize_string(view["name"]) for view in views]
            view_ids: list[str] = [view["id"] for view in views]
            write.types(f"{table_name}View", view_names, f"View names for `{table['name']}`")
            write.types(f"{table_name}ViewId", view_ids, f"View IDs for `{table['name']}`")
            write.dict_class(
                f"{table_name}ViewNameIdMapping",
                [(sanitize_string(view["name"]), view["id"]) for view in table["views"]],
                first_type=f"{table_name}View",
                second_type=f"{table_name}ViewId",
                is_value_string=True,
                is_key_string=True,
            )
            write.dict_class(
                f"{table_name}ViewIdNameMapping",
                [(view["id"], sanitize_string(view["name"])) for view in table["views"]],
                first_type=f"{table_name}ViewId",
                second_type=f"{table_name}View",
                is_value_string=True,
            )

    with WriteToTypeScriptFile(path=folder / "dynamic" / "types" / "index.ts") as write:
        write.line('export * from "./_tables";')
        for table in metadata["tables"]:
            table_filename = property_name_camel(table, folder)
            write.line(f'export * from "./{table_filename}";')


def write_interfaces(metadata: BaseMetadata, base_id: str, folder: Path):
    for table in metadata["tables"]:
        table_filename = property_name_camel(table, folder)

        with WriteToTypeScriptFile(path=folder / "dynamic" / "interfaces" / f"{table_filename}.ts") as write:
            write.line("import {")
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    table_name = property_name_pascal(table, folder)
                    field_name = property_name_pascal(field, folder)
                    write.line_indented(f"{options_name(table_name, field_name)},")
            write.line(f'}} from "../types/{table_filename}";')
            write.line('import { RecordId } from "../../../static/typescript/special-types";')
            write.line('import { Attachment, Collaborator } from "airtable";')
            write.line_empty()

            table_name = property_name_pascal(table, folder)
            write.line(f"export interface {table_name}Record {{")
            write.line_indented("id: string;")
            for field in table["fields"]:
                field_name = property_name_camel(field, folder)
                ts_type = typescript_type(table["name"], field, include_null=True)
                write.docstring(f"`{sanitize_string(field['name'])}` ({field['id']})", 1)
                write.property_row(field_name, ts_type, optional=False)
            write.line("}")
            write.line_empty()

    with WriteToTypeScriptFile(path=folder / "dynamic" / "interfaces" / "index.ts") as write:
        for table in metadata["tables"]:
            table_filename = property_name_camel(table, folder)
            write.line(f'export * from "./{table_filename}";')


def write_zod_schemas(metadata: BaseMetadata, base_id: str, folder: Path):
    for table in metadata["tables"]:
        table_filename = property_name_camel(table, folder)
        table_name = property_name_pascal(table, folder)

        with WriteToTypeScriptFile(path=folder / "dynamic" / "zod" / f"{table_filename}.ts") as write:
            # Imports
            write.line('import * as z from "zod";')
            write.line('import { AirtableAttachmentSchema, AirtableCollaboratorSchema, RecordIdSchema } from "../../static/special-types";')
            write.line("import {")
            write.line_indented(f"{property_name_pascal(table, folder)}FieldSet,")
            # Import select option types
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    table_name = property_name_pascal(table, folder)
                    field_name = property_name_pascal(field, folder)
                    write.line_indented(f"{options_name(table_name, field_name)}s,")
            write.line(f'}} from "../types/{table_filename}";')
            write.line_empty()

            # Schema
            write.line(f"export const {property_name_pascal(table, folder)}ZodSchema = z.object({{")
            write.line_indented("id: z.string(),")
            for field in table["fields"]:
                z_type = zod_type(table["name"], field)
                field_name = property_name_camel(field, folder)
                write.line_indented(f"{field_name}: {z_type},", 1)  # TODO: Replace with actual type
            write.line("});")
            write.line_empty()
            write.line(f"export type {table_name}ZodType = z.infer<typeof {table_name}ZodSchema>;")
            write.line_empty()

    with WriteToTypeScriptFile(path=folder / "dynamic" / "zod" / "index.ts") as write:
        for table in metadata["tables"]:
            table_filename = property_name_camel(table, folder)
            write.line(f'export * from "./{table_filename}";')


def write_tables(metadata: BaseMetadata, folder: Path):
    # Step 6: Generate per-table table files
    for table in metadata["tables"]:
        table_filename = property_name_camel(table, folder)

        with WriteToTypeScriptFile(path=folder / "dynamic" / "tables" / f"{table_filename}.ts") as write:
            # Imports
            write.line('import { Table } from "airtable-ts";')

            write.line("import {")
            write.line_indented(f"{property_name_pascal(table, folder)}FieldPropertyTypeMapping,")
            write.line_indented(f"{property_name_pascal(table, folder)}FieldPropertyIdMapping,")
            write.line(f'}} from "../types/{table_filename}";')
            write.line(f'import type {{ {property_name_pascal(table, folder)}Record }} from "../interfaces/{table_filename}";')
            write.line_empty()

            # Table class
            write.line(f"export const {property_name_pascal(table, folder)}Table: Table<{property_name_pascal(table, folder)}Record> = {{")
            write.line_indented(f"name: '{sanitize_string(table['name'])}',")
            write.line_indented(
                "baseId: process.env.AIRTABLE_BASE_ID || '',",
            )
            write.line_indented(f"tableId: '{table['id']}',")
            write.line_indented(f"schema: {property_name_pascal(table, folder)}FieldPropertyTypeMapping,")
            write.line_indented(f"mappings: {property_name_pascal(table, folder)}FieldPropertyIdMapping,")
            write.line("}")

    # Step 7: Generate index.ts to re-export all tables
    with WriteToTypeScriptFile(path=folder / "dynamic" / "tables" / "index.ts") as write:
        for table in metadata["tables"]:
            table_filename = property_name_camel(table, folder)
            write.line(f'export * from "./{table_filename}";')


# def write_main_class(metadata: BaseMetadata, base_id: str, folder: Path):
#     with WriteToTypeScriptFile(path=folder / "dynamic" / "airtable-main.ts") as write:
#         # Imports
#         write.line('import { getApiKey } from "../static/helpers";')
#         write.line("import {")
#         for table in metadata["tables"]:
#             write.line_indented(f"{property_name_camel(table, folder)}Table,")
#         write.line('} from "./tables";')
#         write.line_empty()

#         write.line("export class Airtable {")
#         for table in metadata["tables"]:
#             write.line_indented(f"public {property_name_camel(table, folder, use_custom=False)}: {property_name_camel(table, folder)}Table;")
#         write.line_empty()
#         write.line_indented("constructor() {")
#         write.line_indented("const apiKey = getApiKey();", 2)
#         write.line_indented(f"const baseId = '{base_id}';", 2)
#         for table in metadata["tables"]:
#             write.line_indented(
#                 f"this.{property_name_camel(table, folder, use_custom=False)} = new {property_name_camel(table, folder)}Table(apiKey, baseId);", 2
#             )
#         write.line_indented("}")
#         write.line("}")


def write_formula_helpers(metadata: BaseMetadata, folder: Path):
    # Step 8: Generate per-table formula files
    for table in metadata["tables"]:
        table_filename = property_name_camel(table, folder)

        with WriteToTypeScriptFile(path=folder / "dynamic" / "formulas" / f"{table_filename}.ts") as write:
            # Imports
            write.line(f'import type {{ {property_name_pascal(table, folder)}Field }} from "../types/{table_filename}";')
            write.line(
                f'import {{ {property_name_pascal(table, folder)}Fields, {property_name_pascal(table, folder)}FieldNameIdMapping }} from "../types/{table_filename}";'
            )
            write.line('import { validateKey } from "../../static/helpers";')
            write.line('import { AttachmentsField, BooleanField, DateField, NumberField, TextField } from "../../static/formula";')
            write.line_empty()

            # Formula helper classes
            def write_formula(type: str):
                write.line(f"export class {property_name_pascal(table, folder)}{type} extends {type} {{")
                write.line_indented(f"constructor(name: {property_name_pascal(table, folder)}Field) {{")
                write.line_indented(f"validateKey(name, {property_name_pascal(table, folder)}Fields);", 2)
                write.line_indented(f"super(name, {property_name_pascal(table, folder)}FieldNameIdMapping);", 2)
                write.line_indented("}", 1)
                write.line("}")
                write.line_empty()
                write.line_empty()

            write_formula("AttachmentsField")
            write_formula("BooleanField")
            write_formula("DateField")
            write_formula("NumberField")
            write_formula("TextField")

    # Step 9: Generate index.ts to re-export all formulas
    with WriteToTypeScriptFile(path=folder / "dynamic" / "formulas" / "index.ts") as write:
        for table in metadata["tables"]:
            table_filename = property_name_camel(table, folder)
            write.line(f'export * from "./{table_filename}";')


def write_index(metadata: BaseMetadata, folder: Path):
    with WriteToTypeScriptFile(path=folder / "dynamic" / "index.ts") as write:
        # write.line('export * from "./airtable-main";')
        write.line('export * from "./tables";')
        write.line('export * from "./types";')
        write.line('export * from "./zod";')
        write.line('export * from "./interfaces";')
        # write.line('export * from "./models";')
        write.line('export * from "./formulas";')
        write.line("")

    with WriteToTypeScriptFile(path=folder / "index.ts") as write:
        write.line('export * from "./dynamic";')
        write.line('export * from "./static/formula";')
        write.line("")


def typescript_type(table_name: str, field: FieldMetadata, warn: bool = False, include_null: bool = False) -> str:
    """Returns the appropriate Python type for a given Airtable field."""

    airtable_type: FieldType = field["type"]
    generic = "string"
    # ts_type: str = "Any"
    ts_type: str = generic  # AirtableTS doesn't like "Any"

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
            # ts_type = "Attachment[]"
            ts_type = "string"
        case "singleCollaborator" | "lastModifiedBy" | "createdBy":
            # ts_type = "Collaborator"
            ts_type = "string"
        case "singleSelect":
            referenced_field = get_referenced_field(field, all_fields)
            if field["id"] in select_options_types:
                ts_type = select_options_types[field["id"]]
            elif referenced_field and referenced_field["type"] == "singleSelect" and referenced_field["id"] in select_options_types:
                ts_type = select_options_types[referenced_field["id"]]
            else:
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = generic
        case "multipleSelects":
            if field["id"] in select_options_types:
                ts_type = f"{select_options_types[field['id']]}[]"
            else:
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = generic
        case "button":
            ts_type = "string"  # Unsupported by Airtable's JS library
        case _:
            if not is_valid_field(field):
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = generic

    # TODO: In the case of some calculated fields, sometimes the result is just too unpredictable.
    # Although the type prediction is basically right, I haven't figured out how to predict if
    # it's a list or not, and sometimes the result is a list with a single null value.
    if not ts_type.endswith("[]") and ts_type not in ("number", "boolean"):  # TODO - why is this not allowed in Airtable JS library?
        if involves_lookup_field(field, all_fields):
            ts_type = f"{ts_type}[]"
        elif involves_rollup_field(field, all_fields):
            if ts_type == "number" or ts_type == "string":  # TODO - a limitation of Airtable-TS: "[airtable-ts] Unknown airtable type..."
                ts_type = ts_type
            else:
                ts_type = f"{ts_type}[]"

    if include_null:
        return ts_type + " | null"
    else:
        return ts_type


def airtable_ts_type(table_name: str, field: FieldMetadata, warn: bool = False) -> str:
    """Returns the appropriate Airtable-TS type for a given Airtable field."""

    airtable_type: FieldType = field["type"]
    generic = "string"
    ts_type: str = generic  # AirtableTS doesn't like "Any"

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
            ts_type = "string[]"
        case "multipleAttachments":
            # ts_type = "Attachment[]"  # TODO
            ts_type = "string"  # TODO
        case "singleCollaborator" | "lastModifiedBy" | "createdBy":
            # ts_type = "Collaborator"  # TODO
            ts_type = "string"  # TODO
        case "singleSelect":
            referenced_field = get_referenced_field(field, all_fields)
            if field["id"] in select_options_types:
                ts_type = "string"
                # ts_type = select_options_types[field["id"]]
            elif referenced_field and referenced_field["type"] == "singleSelect" and referenced_field["id"] in select_options_types:
                ts_type = "string"
                # ts_type = select_options_types[referenced_field["id"]]
            else:
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = generic
        case "multipleSelects":
            if field["id"] in select_options_types:
                ts_type = "string[]"
                # ts_type = f"{select_options_types[field['id']]}[]"
            else:
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = generic
        case "button":
            ts_type = "string"  # Unsupported by Airtable's JS library
        case _:
            if not is_valid_field(field):
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = generic

    # TODO: In the case of some calculated fields, sometimes the result is just too unpredictable.
    # Although the type prediction is basically right, I haven't figured out how to predict if
    # it's a list or not, and sometimes the result is a list with a single null value.
    if not ts_type.endswith("[]") and ts_type not in ("number", "boolean"):  # TODO - why is this not allowed in Airtable JS library?
        if involves_lookup_field(field, all_fields):
            ts_type = f"{ts_type}[]"
        elif involves_rollup_field(field, all_fields):
            if ts_type == "number" or ts_type == "string":  # TODO - a limitation of Airtable-TS: "[airtable-ts] Unknown airtable type..."
                ts_type = ts_type
            else:
                ts_type = f"{ts_type}[]"

    return f"'{ts_type} | null'"


def zod_type(table_name: str, field: FieldMetadata, warn: bool = False) -> str:
    """Returns the appropriate Zod schema type for a given Airtable field."""

    airtable_type: FieldType = field["type"]
    ts_type: str = "z.any()"

    # With calculated fields, we want to know the type of the result
    if is_calculated_field(field):
        airtable_type = get_result_type(field)

    match airtable_type:
        case "singleLineText" | "multilineText" | "richText" | "barcode":
            ts_type = "z.string()"
        case "phoneNumber":
            ts_type = "z.string()"  # TODO - zod doesn't have built-in phone validation, but it supports custom validation
        case "url":
            ts_type = "z.url().or(z.literal(''))"
        case "email":
            ts_type = "z.email().or(z.literal(''))"
        case "checkbox":
            ts_type = "z.boolean()"
        case "date" | "dateTime" | "createdTime" | "lastModifiedTime":
            ts_type = "z.string()"  # TODO
        case "count" | "autoNumber" | "percent" | "currency" | "duration":
            ts_type = "z.number()"
        case "number":
            if "options" in field and "precision" in field["options"]:  # type: ignore
                if field["options"]["precision"] == 0:  # type: ignore
                    ts_type = "z.int()"
                else:
                    ts_type = "z.number()"
            else:
                ts_type = "z.number()"
        case "multipleRecordLinks":
            ts_type = "z.array(RecordIdSchema)"
        case "multipleAttachments":
            ts_type = "z.array(AirtableAttachmentSchema)"
        case "singleCollaborator" | "lastModifiedBy" | "createdBy":
            ts_type = "AirtableCollaboratorSchema"
        case "singleSelect":
            referenced_field = get_referenced_field(field, all_fields)
            if field["id"] in select_options_lists:
                ts_type = f"z.enum({select_options_lists[field['id']]})"
            elif referenced_field and referenced_field["type"] == "singleSelect" and referenced_field["id"] in select_options_types:
                ts_type = f"z.enum({select_options_lists[referenced_field['id']]})"
            else:
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = "z.any()"
        case "multipleSelects":
            if field["id"] in select_options_lists:
                ts_type = f"z.array(z.enum({select_options_lists[field['id']]}))"
            else:
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = "z.any()"
        case "button":
            ts_type = "z.string()"  # TODO
        case _:
            if not is_valid_field(field):
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                ts_type = "z.any()"

    # TODO: In the case of some calculated fields, sometimes the result is just too unpredictable.
    # Although the type prediction is basically right, I haven't figured out how to predict if
    # it's a list or not, and sometimes the result is a list with a single null value.
    if not ts_type.endswith("[]") and ts_type not in ("number", "boolean"):  # TODO - why is this not allowed in Airtable JS library?
        if involves_lookup_field(field, all_fields) or involves_rollup_field(field, all_fields):
            ts_type = f"{ts_type}.or(z.array({ts_type}))"  # TODO - not sure if this is correct

    return ts_type + ".nullable()"

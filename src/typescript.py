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
    property_name_model,
    property_name_pascal,
    sanitize_string,
    upper_case,
    warn_unhandled_airtable_type,
)
from .meta_types import BaseMetadata, FieldMetadata, FieldType
from .python import formula_type

all_fields: dict[str, FieldMetadata] = {}
select_options: dict[str, str] = {}
table_id_name_map: dict[str, str] = {}


def gen_typescript(metadata: BaseMetadata, base_id: str, output_folder: Path, csv_folder: Path):
    for table in metadata["tables"]:
        table_id_name_map[table["id"]] = table["name"]
        for field in table["fields"]:
            all_fields[field["id"]] = field
            options = get_select_options(field)
            if len(options) > 0:
                _table_name = property_name_pascal(table, csv_folder)
                field_name = property_name_pascal(field, csv_folder)
                select_options[field["id"]] = f"{options_name(_table_name, field_name)}"
        detect_duplicate_property_names(table, csv_folder)

    dynamic_folder = output_folder / "dynamic"
    if dynamic_folder.exists():
        shutil.rmtree(dynamic_folder)
        dynamic_folder.mkdir(parents=True, exist_ok=True)

    static_folder = output_folder / "static"
    if static_folder.exists():
        shutil.rmtree(static_folder)
        static_folder.mkdir(parents=True, exist_ok=True)

    copy_static_files(output_folder, "typescript")
    write_types(metadata, output_folder, csv_folder)
    write_models(metadata, base_id, output_folder, csv_folder)
    write_tables(metadata, output_folder, csv_folder)
    write_main_class(metadata, base_id, output_folder, csv_folder)
    write_formula_helpers(metadata, output_folder, csv_folder)
    write_index(metadata, output_folder)


def write_types(metadata: BaseMetadata, output_folder: Path, csv_folder: Path):
    # Create types directory
    types_dir = output_folder / "dynamic" / "types"
    types_dir.mkdir(parents=True, exist_ok=True)

    # Write individual table type files
    for table in metadata["tables"]:
        table_name = property_name_pascal(table, csv_folder)
        table_name_camel = property_name_camel(table, csv_folder)
        with WriteToTypeScriptFile(path=types_dir / f"{table_name_camel}.ts") as write:
            # Imports
            write.region("IMPORTS")
            write.line('import { Attachment, Collaborator, FieldSet } from "airtable";')
            write.line('import { RecordId } from "../../static/special-types";')
            write.endregion()
            write.line_empty()

            # Field Options
            write.region("FIELD OPTIONS")
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    _table_name = property_name_pascal(table, csv_folder)
                    field_name = property_name_pascal(field, csv_folder)
                    write.types(
                        options_name(_table_name, field_name),
                        options,
                        f"Select options for `{sanitize_string(field['name'])}`",
                    )
            write.endregion()

            # Table Type
            field_names = [sanitize_string(field["name"]) for field in table["fields"]]
            field_ids = [field["id"] for field in table["fields"]]
            property_names = [property_name_camel(field, csv_folder) for field in table["fields"]]

            write.region(upper_case(table["name"]))

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
                [(field["id"], property_name_camel(field, csv_folder)) for field in table["fields"]],
                first_type=f"{table_name}FieldId",
                second_type=f"{table_name}FieldProperty",
                is_value_string=True,
            )
            write.dict_class(
                f"{table_name}FieldPropertyIdMapping",
                [(property_name_camel(field, csv_folder), field["id"]) for field in table["fields"]],
                first_type=f"{table_name}FieldProperty",
                second_type=f"{table_name}FieldId",
                is_value_string=True,
            )
            write.dict_class(
                f"{property_name_pascal(table, csv_folder)}FieldNamePropertyMapping",
                [(field["name"], property_name_camel(field, csv_folder)) for field in table["fields"]],
                first_type=f"{property_name_pascal(table, csv_folder)}Field",
                second_type=f"{property_name_pascal(table, csv_folder)}FieldProperty",
                is_value_string=True,
            )
            write.dict_class(
                f"{property_name_pascal(table, csv_folder)}FieldPropertyNameMapping",
                [(property_name_camel(field, csv_folder), field["name"]) for field in table["fields"]],
                first_type=f"{property_name_pascal(table, csv_folder)}FieldProperty",
                second_type=f"{property_name_pascal(table, csv_folder)}Field",
                is_value_string=True,
            )

            write.line(f"export interface {table_name}FieldSetIds extends FieldSet {{")
            for field in table["fields"]:
                write.line_indented("//@ts-ignore")
                write.property_row(field["id"], typescript_type(table["name"], field, warn=True), optional=True)
            write.line("}")
            write.line_empty()
            write.line(f"export interface {table_name}FieldSet extends FieldSet {{")
            for field in table["fields"]:
                write.line_indented("//@ts-ignore")
                write.property_row(sanitize_string(field["name"]), typescript_type(table["name"], field), is_name_string=True, optional=True)
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
            )
            write.dict_class(
                f"{table_name}ViewIdNameMapping",
                [(view["id"], sanitize_string(view["name"])) for view in table["views"]],
                first_type=f"{table_name}ViewId",
                second_type=f"{table_name}View",
                is_value_string=True,
            )

            write.endregion()

    # Write global tables file
    with WriteToTypeScriptFile(path=types_dir / "_tables.ts") as write:
        # Import field name ID mappings from individual table files
        write.region("IMPORTS")
        for table in metadata["tables"]:
            table_name = property_name_pascal(table, csv_folder)
            table_name_camel = property_name_camel(table, csv_folder)
            write.line(f"import {{ {table_name}FieldNameIdMapping }} from './{table_name_camel}';")
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
            [(table["id"], f"{property_name_pascal(table, csv_folder)}FieldNameIdMapping") for table in metadata["tables"]],
            first_type="TableId",
            second_type="Record<string, string>",
        )
        write.endregion()

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=types_dir / "index.ts") as write:
        for table in metadata["tables"]:
            write.line(f"export * from './{property_name_camel(table, csv_folder)}';")
        write.line("export * from './_tables';")
        write.line("")


def write_models(metadata: BaseMetadata, base_id: str, output_folder: Path, csv_folder: Path):
    # Create models directory
    models_dir = output_folder / "dynamic" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    # Write individual table model files
    for table in metadata["tables"]:
        table_name = property_name_pascal(table, csv_folder)
        table_name_camel = property_name_camel(table, csv_folder)
        model_name = property_name_model(table, csv_folder)
        with WriteToTypeScriptFile(path=models_dir / f"{table_name_camel}.ts") as write:
            # Imports
            write.region("IMPORTS")
            write.line('import { AirtableOptions, Attachment, Collaborator, FieldSet, Record } from "airtable";')
            write.line('import { AirtableModel } from "../../static/airtable-model";')
            write.line('import { RecordId } from "../../static/special-types";')
            write.line('import { LinkedRecord, LinkedRecords } from "../../static/linked-record";')
            write.line('import { getOptions, getBaseId } from "../../static/helpers";')

            # Import types for this table
            write.line("import {")
            write.line_indented(f"{table_name}FieldSet,")
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    field_name = property_name_pascal(field, csv_folder)
                    write.line_indented(f"{options_name(table_name, field_name)},")
            write.line(f'}} from "../types/{table_name_camel}";')
            write.line(f"import {{ {table_name}Formulas }} from '../formulas/{table_name_camel}';")

            write.line("import {")
            for _table in metadata["tables"]:
                if _table["id"] == table["id"]:
                    continue
                _model_name = property_name_model(_table, csv_folder)
                write.line_indented(f"{_model_name},")
            write.line('} from "../models";')

            # Import table class for this table
            write.line(f"import {{ {table_name}Table }} from '../tables/{table_name_camel}';")
            write.endregion()
            write.line_empty()

            # Table Model
            write.region(upper_case(table["name"]))

            write.docstring(f"Model for `{table['name']}` ({table['id']})", 0)
            write.line(f"export class {model_name} extends AirtableModel<{table_name}FieldSet> {{")
            write.line_indented(f"public static f = {table_name}Formulas")
            write.line_empty()
            for field in table["fields"]:
                field_name = property_name_camel(field, csv_folder)
                field_type = typescript_type(table["name"], field)
                write.docstring(f"`{field['name']}` ({field['id']})")
                if (field_type == "RecordId" or field_type == "RecordId[]") and not is_computed_field(field):
                    linked_record_type: str = ""
                    if "options" in field and "linkedTableId" in field["options"]:  # type: ignore
                        table_id = field["options"]["linkedTableId"]  # type: ignore
                        tables = metadata["tables"]
                        for _table in tables:
                            if _table["id"] == table_id:
                                linked_record_type = property_name_model(_table, csv_folder)
                                break

                    if field_type == "RecordId":
                        write.line_indented(f"public {field_name}: LinkedRecord<{linked_record_type}>;", 1)
                    elif field_type == "RecordId[]":
                        write.line_indented(f"public {field_name}: LinkedRecords<{linked_record_type}>;", 1)
                else:
                    write.line_indented(f"public {field_name}?: {field_type};", 1)
            write.line_empty()
            write.line_indented("constructor({")
            write.line_indented("id,", 2)
            for field in table["fields"]:
                field_name = property_name_camel(field, csv_folder)
                write.line_indented(f"{field_name},", 2)
            write.line_indented("}: {", 1)
            write.line_indented("id?: string,", 2)
            for field in table["fields"]:
                field_name = property_name_camel(field, csv_folder)
                field_type = typescript_type(table["name"], field)
                write.line_indented(f"{field_name}?: {field_type},", 2)
            write.line_indented("}) {")
            write.line_indented("super(id ?? '');", 2)
            for field in table["fields"]:
                field_name = property_name_camel(field, csv_folder)
                field_type = typescript_type(table["name"], field)
                if (field_type == "RecordId" or field_type == "RecordId[]") and not is_computed_field(field):
                    linked_record_type: str = ""
                    if "options" in field and "linkedTableId" in field["options"]:  # type: ignore
                        table_id = field["options"]["linkedTableId"]  # type: ignore
                        tables = metadata["tables"]
                        for _table in tables:
                            if _table["id"] == table_id:
                                linked_record_type = property_name_model(_table, csv_folder)
                                break

                    if field_type == "RecordId":
                        write.line_indented(
                            f"this.{field_name} = new LinkedRecord<{linked_record_type}>({field_name}, {linked_record_type}.fromId);", 2
                        )
                    elif field_type == "RecordId[]":
                        write.line_indented(
                            f"this.{field_name} = new LinkedRecords<{linked_record_type}>({field_name}, {linked_record_type}.fromId);", 2
                        )
                else:
                    write.line_indented(f"this.{field_name} = {field_name};", 2)
            write.line_indented(
                f"this.record = new Record<{table_name}FieldSet>(new {table_name}Table(getBaseId(), getOptions())._table, this.id, {{}});",
                2,
            )
            write.line_indented("this.updateRecord();", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"public static fromRecord(record: Record<{table_name}FieldSet>): {model_name} {{")
            write.line_indented(f"const instance = new {model_name}(", 2)
            write.line_indented("{ id: record.id },", 3)
            write.line_indented(");", 2)
            write.line_indented("instance.updateModel(record);", 2)
            write.line_indented("return instance;", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"public static fromId(id: RecordId): {model_name} {{")
            write.line_indented(f"return new {model_name}({{ id }});", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"protected writableFields(useFieldIds: boolean = false): Partial<{table_name}FieldSet> {{")
            write.line_indented(f"const fields: Partial<{table_name}FieldSet> = {{}};", 2)
            for field in table["fields"]:
                field_name = property_name_camel(field, csv_folder)
                if not is_computed_field(field):
                    field_type = typescript_type(table["name"], field)
                    if field_type == "RecordId" or field_type == "RecordId[]":
                        if field_type == "RecordId":
                            write.line_indented(
                                f'fields[useFieldIds ? "{field["id"]}" : "{sanitize_string(field["name"])}"] = this.{field_name}?.id;', 2
                            )
                        elif field_type == "RecordId[]":
                            write.line_indented(
                                f'fields[useFieldIds ? "{field["id"]}" : "{sanitize_string(field["name"])}"] = this.{field_name}?.ids;', 2
                            )
                    elif field_type == "Attachment[]":
                        write.line_indented(
                            f'fields[useFieldIds ? "{field["id"]}" : "{sanitize_string(field["name"])}"] = this.sanitizeAttachment("{field_name}");',
                            2,
                        )
                    else:
                        write.line_indented(f'fields[useFieldIds ? "{field["id"]}" : "{sanitize_string(field["name"])}"] = this.{field_name};', 2)
            write.line_indented("return fields;", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"protected updateModel(record: Record<{table_name}FieldSet>) {{")
            write.line_indented("this.record = record;", 2)
            for field in table["fields"]:
                field_name = property_name_camel(field, csv_folder)
                field_type = typescript_type(table["name"], field)
                if (field_type == "RecordId" or field_type == "RecordId[]") and not is_computed_field(field):
                    linked_record_type: str = ""
                    if "options" in field and "linkedTableId" in field["options"]:  # type: ignore
                        table_id = field["options"]["linkedTableId"]  # type: ignore
                        tables = metadata["tables"]
                        for _table in tables:
                            if _table["id"] == table_id:
                                linked_record_type = property_name_model(_table, csv_folder)
                                break

                    if field_type == "RecordId":
                        write.line_indented(
                            f'this.{field_name} = new LinkedRecord<{linked_record_type}>(record.get("{sanitize_string(field["name"])}"), {linked_record_type}.fromId);',
                            2,
                        )
                    elif field_type == "RecordId[]":
                        write.line_indented(
                            f'this.{field_name} = new LinkedRecords<{linked_record_type}>(record.get("{sanitize_string(field["name"])}"), {linked_record_type}.fromId);',
                            2,
                        )
                else:
                    write.line_indented(f'this.{field_name} = record.get("{sanitize_string(field["name"])}");', 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented("protected updateRecord() {")
            write.line_indented("if (!this.record) ", 2)
            write.line_indented(
                'throw new Error("Cannot convert to record: record is undefined. Please use fromRecord to initialize the instance.");', 3
            )
            for field in table["fields"]:
                field_name = property_name_camel(field, csv_folder)
                field_type = typescript_type(table["name"], field)
                if (field_type == "RecordId" or field_type == "RecordId[]") and not is_computed_field(field):
                    if field_type == "RecordId":
                        write.line_indented(f'this.record.set("{sanitize_string(field["name"])}", this.{field_name}?.id);', 2)
                    elif field_type == "RecordId[]":
                        write.line_indented(f'this.record.set("{sanitize_string(field["name"])}", this.{field_name}?.ids);', 2)
                else:
                    write.line_indented(f'this.record.set("{sanitize_string(field["name"])}", this.{field_name});', 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line("}")
            write.endregion()

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=models_dir / "index.ts") as write:
        for table in metadata["tables"]:
            write.line(f"export * from './{property_name_camel(table, csv_folder)}';")
        write.line("")


def write_tables(metadata: BaseMetadata, output_folder: Path, csv_folder: Path):
    # Create tables directory
    tables_dir = output_folder / "dynamic" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    # Write individual table files
    for table in metadata["tables"]:
        table_name = property_name_pascal(table, csv_folder)
        table_name_camel = property_name_camel(table, csv_folder)
        model_name = property_name_model(table, csv_folder)
        with WriteToTypeScriptFile(path=tables_dir / f"{table_name_camel}.ts") as write:
            # Imports
            write.region("IMPORTS")
            write.line('import { AirtableTable } from "../../static/airtable-table";')
            write.line("import {")
            write.line_indented(f"{table_name}FieldSet,")
            write.line_indented(f"{table_name}Field,")
            write.line_indented(f"{table_name}View,")
            write.line_indented(f"{table_name}ViewNameIdMapping,")
            write.line(f'}} from "../types/{table_name_camel}";')
            write.line(f"import {{ {model_name} }} from '../models/{table_name_camel}';")
            write.line('import { AirtableOptions } from "airtable";')
            write.endregion()
            write.line_empty()

            write.line(
                f"export class {table_name}Table extends AirtableTable<{table_name}FieldSet, {model_name}, {table_name}View, {table_name}Field> {{"
            )
            write.line_indented("constructor(baseId: string, options: AirtableOptions) {")
            write.line_indented(
                f'super(baseId, "{table["id"]}", {table_name}ViewNameIdMapping, {model_name}.fromRecord, options);',
                2,
            )
            write.line_indented("}")
            write.line("}")

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=tables_dir / "index.ts") as write:
        for table in metadata["tables"]:
            write.line(f"export * from './{property_name_camel(table, csv_folder)}';")
        write.line("")


def write_main_class(metadata: BaseMetadata, base_id: str, output_folder: Path, csv_folder: Path):
    with WriteToTypeScriptFile(path=output_folder / "dynamic" / "airtable-main.ts") as write:
        # Imports
        write.line('import { ExtendedAirtableOptions } from "../static/special-types";')
        write.line('import { getApiKey, getBaseId } from "../static/helpers";')
        write.line("import {")
        for table in metadata["tables"]:
            table_name_pascal = property_name_pascal(table, csv_folder)
            write.line_indented(f"{table_name_pascal}Table,")
        write.line('} from "./tables";')
        write.line_empty()

        write.line("export class Airtable {")
        for table in metadata["tables"]:
            table_name_camel = property_name_camel(table, csv_folder)
            table_name_pascal = property_name_pascal(table, csv_folder)
            write.line_indented(f"public {table_name_camel}: {table_name_pascal}Table;")
        write.line_empty()
        write.line_indented("constructor(options?: ExtendedAirtableOptions) {")
        write.line_indented("const _baseId = options?.baseId || getBaseId();", 2)
        write.line_indented("const _options = {", 2)
        write.line_indented("  apiKey: options?.apiKey ?? getApiKey(),", 3)
        write.line_indented("  apiVersion: options?.apiVersion,", 3)
        write.line_indented("  customHeaders: options?.customHeaders,", 3)
        write.line_indented("  endpointUrl: options?.endpointUrl,", 3)
        write.line_indented("  noRetryIfRateLimited: options?.noRetryIfRateLimited ?? false,", 3)
        write.line_indented("  requestTimeout: options?.requestTimeout,", 3)
        write.line_indented("};", 2)
        for table in metadata["tables"]:
            table_name_camel = property_name_camel(table, csv_folder)
            table_name_pascal = property_name_pascal(table, csv_folder)
            write.line_indented(f"this.{table_name_camel} = new {table_name_pascal}Table(_baseId, _options);", 2)
        write.line_indented("}")
        write.line("}")


def write_formula_helpers(metadata: BaseMetadata, output_folder: Path, csv_folder: Path):
    # Create formulas directory
    formulas_dir = output_folder / "dynamic" / "formulas"
    formulas_dir.mkdir(parents=True, exist_ok=True)

    for table in metadata["tables"]:
        table_name = property_name_pascal(table, csv_folder)
        table_name_camel = property_name_camel(table, csv_folder)
        with WriteToTypeScriptFile(path=formulas_dir / f"{table_name_camel}.ts") as write:
            # Imports
            write.line(
                'import { ID, AttachmentsField, BooleanField, DateField, NumberField, TextField, SingleSelectField, MultiSelectField } from "../../static/formula";'
            )
            has_options: bool = False
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    has_options = True
                    break

            if has_options:
                write.line("import {")
                for field in table["fields"]:
                    options = get_select_options(field)
                    if len(options) > 0:
                        field_name = property_name_pascal(field, csv_folder)
                        write.line_indented(f"{options_name(table_name, field_name)},")
                write.line(f'}} from "../types/{table_name_camel}";')

            write.line_empty()

            # Properties
            write.line(f"export namespace {table_name}Formulas {{")
            write.line_indented("export const id: ID = new ID();")
            for field in table["fields"]:
                property_name = property_name_camel(field, csv_folder)
                formula_class = formula_type(table["name"], field)
                if formula_class == "SingleSelectField" or formula_class == "MultiSelectField":
                    write.line_indented(
                        f"export const {property_name}: {formula_class}<{options_name(property_name_pascal(table, csv_folder), property_name_pascal(field, csv_folder))}> = new {formula_class}('{field['id']}');"
                    )
                else:
                    write.line_indented(f"export const {property_name}: {formula_class} = new {formula_class}('{field['id']}');")
            write.line("}")
            write.line_empty()

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=formulas_dir / "index.ts") as write:
        for table in metadata["tables"]:
            write.line(f"export * from './{property_name_camel(table, csv_folder)}';")
        write.line("")


def write_index(metadata: BaseMetadata, output_folder: Path):
    with WriteToTypeScriptFile(path=output_folder / "dynamic" / "index.ts") as write:
        write.line('export * from "./airtable-main";')
        write.line('export * from "./tables";')
        write.line('export * from "./types";')
        write.line('export * from "./models";')
        write.line('export * from "./formulas";')
        write.line("")

    with WriteToTypeScriptFile(path=output_folder / "index.ts") as write:
        write.line('export * from "./dynamic";')
        write.line('export * from "./static/formula";')
        write.line('export * from "./static/airtable-model";')
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
    if not ts_type.endswith("[]"):
        if involves_lookup_field(field, all_fields) or involves_rollup_field(field, all_fields):
            ts_type = f"{ts_type} | {ts_type}[]"

    return ts_type

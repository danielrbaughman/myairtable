import shutil
from pathlib import Path

from .helpers import (
    copy_static_files,
    options_name,
    sanitize_string,
    upper_case,
)
from .meta import Base, Field, FieldType
from .python import formula_type
from .write_to_file import WriteToTypeScriptFile

all_fields: dict[str, Field] = {}
select_options: dict[str, str] = {}
table_id_name_map: dict[str, str] = {}


def gen_typescript(base: Base, output_folder: Path):
    for table in base.tables:
        table_id_name_map[table.id] = table.name
        for field in table.fields:
            all_fields[field.id] = field
            options = field.get_select_options()
            if len(options) > 0:
                _table_name = table.name_pascal()
                field_name = field.name_pascal()
                select_options[field.id] = f"{options_name(_table_name, field_name)}"
        table.detect_duplicate_property_names()

    dynamic_folder = output_folder / "dynamic"
    if dynamic_folder.exists():
        shutil.rmtree(dynamic_folder)
        dynamic_folder.mkdir(parents=True, exist_ok=True)

    static_folder = output_folder / "static"
    if static_folder.exists():
        shutil.rmtree(static_folder)
        static_folder.mkdir(parents=True, exist_ok=True)

    copy_static_files(output_folder, "typescript")
    write_types(base, output_folder)
    write_models(base, output_folder)
    write_tables(base, output_folder)
    write_main_class(base, output_folder)
    write_formula_helpers(base, output_folder)
    write_index(output_folder)


def write_types(base: Base, output_folder: Path):
    # Create types directory
    types_dir = output_folder / "dynamic" / "types"
    types_dir.mkdir(parents=True, exist_ok=True)

    # Write individual table type files
    for table in base.tables:
        table_name = table.name_pascal()
        table_name_camel = table.name_camel()
        with WriteToTypeScriptFile(path=types_dir / f"{table_name_camel}.ts") as write:
            # Imports
            write.region("IMPORTS")
            write.line('import { Attachment, Collaborator, FieldSet } from "airtable";')
            write.line('import { RecordId } from "../../static/special-types";')
            write.endregion()
            write.line_empty()

            # Field Options
            write.region("FIELD OPTIONS")
            for field in table.fields:
                options = field.get_select_options()
                if len(options) > 0:
                    _table_name = table.name_pascal()
                    field_name = field.name_pascal()
                    write.types(
                        options_name(_table_name, field_name),
                        options,
                        f"Select options for `{sanitize_string(field.name)}`",
                    )
            write.endregion()

            # Table Type
            field_names = [sanitize_string(field.name) for field in table.fields]
            field_ids = [field.id for field in table.fields]
            property_names = [field.name_camel() for field in table.fields]

            write.region(upper_case(table.name))
            write.types(f"{table_name}Field", field_names, f"Field names for `{table.name}`")
            write.types(f"{table_name}FieldId", field_ids, f"Field IDs for `{table.name}`")
            write.types(f"{table_name}FieldProperty", property_names, f"Property names for `{table.name}`")

            write.docstring(f"Calculated fields for `{table.name}`")
            write.str_list(
                f"{table_name}CalculatedFields",
                [sanitize_string(field.name) for field in table.fields if field.is_computed()],
            )
            write.docstring(f"Calculated fields for `{table.name}`")
            write.str_list(
                f"{table_name}CalculatedFieldIds",
                [field.id for field in table.fields if field.is_computed()],
            )
            write.line_empty()

            write.dict_class(
                f"{table_name}FieldNameIdMapping",
                [(sanitize_string(field.name), field.id) for field in table.fields],
                first_type=f"{table_name}Field",
                second_type=f"{table_name}FieldId",
                is_value_string=True,
            )
            write.dict_class(
                f"{table_name}FieldIdNameMapping",
                [(field.id, sanitize_string(field.name)) for field in table.fields],
                first_type=f"{table_name}FieldId",
                second_type=f"{table_name}Field",
                is_value_string=True,
            )
            write.dict_class(
                f"{table_name}FieldIdPropertyMapping",
                [(field.id, field.name_camel()) for field in table.fields],
                first_type=f"{table_name}FieldId",
                second_type=f"{table_name}FieldProperty",
                is_value_string=True,
            )
            write.dict_class(
                f"{table_name}FieldPropertyIdMapping",
                [(field.name_camel(), field.id) for field in table.fields],
                first_type=f"{table_name}FieldProperty",
                second_type=f"{table_name}FieldId",
                is_value_string=True,
            )
            write.dict_class(
                f"{table_name}FieldNamePropertyMapping",
                [(field.name, field.name_camel()) for field in table.fields],
                first_type=f"{table_name}Field",
                second_type=f"{table_name}FieldProperty",
                is_value_string=True,
            )
            write.dict_class(
                f"{table_name}FieldPropertyNameMapping",
                [(field.name_camel(), field.name) for field in table.fields],
                first_type=f"{table_name}FieldProperty",
                second_type=f"{table_name}Field",
                is_value_string=True,
            )

            write.line(f"export interface {table_name}FieldSetIds extends FieldSet {{")
            for field in table.fields:
                write.line_indented("//@ts-ignore")
                write.property_row(field.id, typescript_type(table.name, field, warn=True), optional=True)
            write.line("}")
            write.line_empty()
            write.line(f"export interface {table_name}FieldSet extends FieldSet {{")
            for field in table.fields:
                write.line_indented("//@ts-ignore")
                write.property_row(sanitize_string(field.name), typescript_type(table.name, field), is_name_string=True, optional=True)
            write.line("}")
            write.line_empty()
            write.line_empty()

            views = table.views
            view_names: list[str] = [sanitize_string(view.name) for view in views]
            view_ids: list[str] = [view.id for view in views]
            write.types(f"{table_name}View", view_names, f"View names for `{table.name}`")
            write.types(f"{table_name}ViewId", view_ids, f"View IDs for `{table.name}`")
            write.dict_class(
                f"{table_name}ViewNameIdMapping",
                [(sanitize_string(view.name), view.id) for view in table.views],
                first_type=f"{table_name}View",
                second_type=f"{table_name}ViewId",
                is_value_string=True,
            )
            write.dict_class(
                f"{table_name}ViewIdNameMapping",
                [(view.id, sanitize_string(view.name)) for view in table.views],
                first_type=f"{table_name}ViewId",
                second_type=f"{table_name}View",
                is_value_string=True,
            )

            write.endregion()

    # Write global tables file
    with WriteToTypeScriptFile(path=types_dir / "_tables.ts") as write:
        # Import field name ID mappings from individual table files
        write.region("IMPORTS")
        for table in base.tables:
            table_name = table.name_pascal()
            table_name_camel = table.name_camel()
            write.line(f"import {{ {table_name}FieldNameIdMapping }} from './{table_name_camel}';")
        write.endregion()
        write.line_empty()

        # Table Lists
        table_names = []
        table_ids = []
        for table in base.tables:
            table_names.append(table.name)
            table_ids.append(table.id)

        write.region("TABLES")
        write.types("TableName", table_names)
        write.types("TableId", table_ids)
        write.dict_class(
            "TableNameIdMapping",
            [(table.name, table.id) for table in base.tables],
            first_type="TableName",
            second_type="TableId",
            is_value_string=True,
        )
        write.dict_class(
            "TableIdNameMapping",
            [(table.id, table.name) for table in base.tables],
            first_type="TableId",
            second_type="TableName",
            is_value_string=True,
        )

        write.dict_class(
            "TableIdToFieldNameIdMapping",
            [(table.id, f"{table.name_pascal()}FieldNameIdMapping") for table in base.tables],
            first_type="TableId",
            second_type="Record<string, string>",
        )
        write.endregion()

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=types_dir / "index.ts") as write:
        for table in base.tables:
            write.line(f"export * from './{table.name_camel()}';")
        write.line("export * from './_tables';")
        write.line("")


def write_models(base: Base, output_folder: Path):
    # Create models directory
    models_dir = output_folder / "dynamic" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    # Write individual table model files
    for table in base.tables:
        table_name = table.name_pascal()
        table_name_camel = table.name_camel()
        model_name = table.name_model()
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
            for field in table.fields:
                options = field.get_select_options()
                if len(options) > 0:
                    field_name = field.name_pascal()
                    write.line_indented(f"{options_name(table_name, field_name)},")
            write.line(f'}} from "../types/{table_name_camel}";')
            write.line(f"import {{ {table_name}Formulas }} from '../formulas/{table_name_camel}';")

            write.line("import {")
            for _table in base.tables:
                if _table.id == table.id:
                    continue
                _model_name = _table.name_model()
                write.line_indented(f"{_model_name},")
            write.line('} from "../models";')

            # Import table class for this table
            write.line(f"import {{ {table_name}Table }} from '../tables/{table_name_camel}';")
            write.endregion()
            write.line_empty()

            # Table Model
            write.region(upper_case(table.name))

            write.docstring(f"Model for `{table.name}` ({table.id})", 0)
            write.line(f"export class {model_name} extends AirtableModel<{table_name}FieldSet> {{")
            write.line_indented(f"public static f = {table_name}Formulas")
            write.line_empty()
            for field in table.fields:
                field_name = field.name_camel()
                field_type = typescript_type(table.name, field)
                write.docstring(f"`{field.name}` ({field.id})")
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type: str = ""
                    if field.options and field.options.linked_table_id:
                        table_id = field.options.linked_table_id
                        tables = base.tables
                        for _table in tables:
                            if _table.id == table_id:
                                linked_record_type = _table.name_model()
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
            for field in table.fields:
                field_name = field.name_camel()
                write.line_indented(f"{field_name},", 2)
            write.line_indented("}: {", 1)
            write.line_indented("id?: string,", 2)
            for field in table.fields:
                field_name = field.name_camel()
                field_type = typescript_type(table.name, field)
                write.line_indented(f"{field_name}?: {field_type},", 2)
            write.line_indented("}) {")
            write.line_indented("super(id ?? '');", 2)
            for field in table.fields:
                field_name = field.name_camel()
                field_type = typescript_type(table.name, field)
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type: str = ""
                    if field.options and field.options.linked_table_id:
                        table_id = field.options.linked_table_id
                        tables = base.tables
                        for _table in tables:
                            if _table.id == table_id:
                                linked_record_type = _table.name_model()
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
            for field in table.fields:
                field_name = field.name_camel()
                if not field.is_computed():
                    field_type = typescript_type(table.name, field)
                    if field_type == "RecordId" or field_type == "RecordId[]":
                        if field_type == "RecordId":
                            write.line_indented(f'fields[useFieldIds ? "{field.id}" : "{sanitize_string(field.name)}"] = this.{field_name}?.id;', 2)
                        elif field_type == "RecordId[]":
                            write.line_indented(f'fields[useFieldIds ? "{field.id}" : "{sanitize_string(field.name)}"] = this.{field_name}?.ids;', 2)
                    elif field_type == "Attachment[]":
                        write.line_indented(
                            f'fields[useFieldIds ? "{field.id}" : "{sanitize_string(field.name)}"] = this.sanitizeAttachment("{field_name}");',
                            2,
                        )
                    else:
                        write.line_indented(f'fields[useFieldIds ? "{field.id}" : "{sanitize_string(field.name)}"] = this.{field_name};', 2)
            write.line_indented("return fields;", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"protected updateModel(record: Record<{table_name}FieldSet>) {{")
            write.line_indented("this.record = record;", 2)
            for field in table.fields:
                field_name = field.name_camel()
                field_type = typescript_type(table.name, field)
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type: str = ""
                    if field.options and field.options.linked_table_id:
                        table_id = field.options.linked_table_id
                        tables = base.tables
                        for _table in tables:
                            if _table.id == table_id:
                                linked_record_type = _table.name_model()
                                break

                    if field_type == "RecordId":
                        write.line_indented(
                            f'this.{field_name} = new LinkedRecord<{linked_record_type}>(record.get("{sanitize_string(field.name)}"), {linked_record_type}.fromId);',
                            2,
                        )
                    elif field_type == "RecordId[]":
                        write.line_indented(
                            f'this.{field_name} = new LinkedRecords<{linked_record_type}>(record.get("{sanitize_string(field.name)}"), {linked_record_type}.fromId);',
                            2,
                        )
                else:
                    write.line_indented(f'this.{field_name} = record.get("{sanitize_string(field.name)}");', 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented("protected updateRecord() {")
            write.line_indented("if (!this.record) ", 2)
            write.line_indented(
                'throw new Error("Cannot convert to record: record is undefined. Please use fromRecord to initialize the instance.");', 3
            )
            for field in table.fields:
                field_name = field.name_camel()
                field_type = typescript_type(table.name, field)
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    if field_type == "RecordId":
                        write.line_indented(f'this.record.set("{sanitize_string(field.name)}", this.{field_name}?.id);', 2)
                    elif field_type == "RecordId[]":
                        write.line_indented(f'this.record.set("{sanitize_string(field.name)}", this.{field_name}?.ids);', 2)
                else:
                    write.line_indented(f'this.record.set("{sanitize_string(field.name)}", this.{field_name});', 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line("}")
            write.endregion()

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=models_dir / "index.ts") as write:
        for table in base.tables:
            write.line(f"export * from './{table.name_camel()}';")
        write.line("")


def write_tables(base: Base, output_folder: Path):
    # Create tables directory
    tables_dir = output_folder / "dynamic" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    # Write individual table files
    for table in base.tables:
        table_name = table.name_pascal()
        table_name_camel = table.name_camel()
        model_name = table.name_model()
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
                f'super(baseId, "{table.id}", {table_name}ViewNameIdMapping, {model_name}.fromRecord, options);',
                2,
            )
            write.line_indented("}")
            write.line("}")

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=tables_dir / "index.ts") as write:
        for table in base.tables:
            write.line(f"export * from './{table.name_camel()}';")
        write.line("")


def write_main_class(base: Base, output_folder: Path):
    with WriteToTypeScriptFile(path=output_folder / "dynamic" / "airtable-main.ts") as write:
        # Imports
        write.line('import { ExtendedAirtableOptions } from "../static/special-types";')
        write.line('import { getApiKey, getBaseId } from "../static/helpers";')
        write.line("import {")
        for table in base.tables:
            table_name_pascal = table.name_pascal()
            write.line_indented(f"{table_name_pascal}Table,")
        write.line('} from "./tables";')
        write.line_empty()

        write.line("export class Airtable {")
        for table in base.tables:
            table_name_camel = table.name_camel()
            table_name_pascal = table.name_pascal()
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
        for table in base.tables:
            table_name_camel = table.name_camel()
            table_name_pascal = table.name_pascal()
            write.line_indented(f"this.{table_name_camel} = new {table_name_pascal}Table(_baseId, _options);", 2)
        write.line_indented("}")
        write.line("}")


def write_formula_helpers(base: Base, output_folder: Path):
    # Create formulas directory
    formulas_dir = output_folder / "dynamic" / "formulas"
    formulas_dir.mkdir(parents=True, exist_ok=True)

    for table in base.tables:
        table_name = table.name_pascal()
        table_name_camel = table.name_camel()
        with WriteToTypeScriptFile(path=formulas_dir / f"{table_name_camel}.ts") as write:
            # Imports
            write.line(
                'import { ID, AttachmentsField, BooleanField, DateField, NumberField, TextField, SingleSelectField, MultiSelectField } from "../../static/formula";'
            )
            has_options: bool = False
            for field in table.fields:
                options = field.get_select_options()
                if len(options) > 0:
                    has_options = True
                    break

            if has_options:
                write.line("import {")
                for field in table.fields:
                    options = field.get_select_options()
                    if len(options) > 0:
                        field_name = field.name_pascal()
                        write.line_indented(f"{options_name(table_name, field_name)},")
                write.line(f'}} from "../types/{table_name_camel}";')

            write.line_empty()

            # Properties
            write.line(f"export namespace {table_name}Formulas {{")
            write.line_indented("export const id: ID = new ID();")
            for field in table.fields:
                property_name = field.name_camel()
                formula_class = formula_type(field)
                if formula_class == "SingleSelectField" or formula_class == "MultiSelectField":
                    write.line_indented(
                        f"export const {property_name}: {formula_class}<{options_name(table_name, field.name_pascal())}> = new {formula_class}('{field.id}');"
                    )
                else:
                    write.line_indented(f"export const {property_name}: {formula_class} = new {formula_class}('{field.id}');")
            write.line("}")
            write.line_empty()

    # Write barrel export index.ts
    with WriteToTypeScriptFile(path=formulas_dir / "index.ts") as write:
        for table in base.tables:
            write.line(f"export * from './{table.name_camel()}';")
        write.line("")


def write_index(output_folder: Path):
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


def typescript_type(table_name: str, field: Field, warn: bool = False) -> str:
    """Returns the appropriate Python type for a given Airtable field."""

    airtable_type: FieldType = field.type
    ts_type: str = "Any"

    # With calculated fields, we want to know the type of the result
    if field.is_calculated():
        airtable_type = field.get_result_type()

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
            referenced_field = field.get_referenced_field(all_fields)
            if field.id in select_options:
                ts_type = select_options[field.id]
            elif referenced_field and referenced_field["type"] == "singleSelect" and referenced_field["id"] in select_options:
                ts_type = select_options[referenced_field["id"]]
            else:
                if warn:
                    field.warn_unhandled_airtable_type(table_name)
                ts_type = "any"
        case "multipleSelects":
            if field.id in select_options:
                ts_type = f"{select_options[field.id]}[]"
            else:
                if warn:
                    field.warn_unhandled_airtable_type(table_name)
                ts_type = "any"
        case "button":
            ts_type = "string"  # Unsupported by Airtable's JS library
        case _:
            if not field.is_valid():
                if warn:
                    field.warn_unhandled_airtable_type(table_name)
                ts_type = "any"

    # TODO: In the case of some calculated fields, sometimes the result is just too unpredictable.
    # Although the type prediction is basically right, I haven't figured out how to predict if
    # it's a list or not, and sometimes the result is a list with a single null value.
    if not ts_type.endswith("[]"):
        if field.involves_lookup(all_fields) or field.involves_rollup(all_fields):
            ts_type = f"{ts_type} | {ts_type}[]"

    return ts_type

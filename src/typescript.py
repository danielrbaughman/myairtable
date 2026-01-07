from pathlib import Path

from .helpers import (
    Paths,
    copy_static_files,
    create_dynamic_subdir,
    reset_folder,
    sanitize_string,
)
from .meta import Base, Field, FieldType
from .progress import progress_spinner
from .write_to_file import WriteToTypeScriptFile


# region MAIN
def generate_typescript(base: Base, output_folder: Path) -> None:
    with progress_spinner(message="Copying static files...", transient=False) as spinner:
        for table in base.tables:
            table.detect_duplicate_property_names()

        reset_folder(output_folder / Paths.DYNAMIC)
        reset_folder(output_folder / Paths.STATIC)

        copy_static_files(output_folder, "typescript")
        spinner.update(description="Generating types...")
        write_types(base, output_folder)

        spinner.update(description="Generating models...")
        write_models(base, output_folder)

        spinner.update(description="Generating formula helpers...")
        write_formula_helpers(base, output_folder)

        spinner.update(description="Generating tables...")
        write_tables(base, output_folder)

        spinner.update(description="Generating main class...")
        write_main_class(base, output_folder)

        spinner.update(description="Generating index...")
        write_index(output_folder)

        spinner.update(description="TypeScript Generation complete!")


def write_barrel_export(base: Base, directory: Path, extra_exports: list[str] | None = None) -> None:
    """Generate index.ts barrel export for a directory."""
    with WriteToTypeScriptFile(path=directory / "index.ts") as write:
        for table in base.tables:
            write.line(f"export * from './{table.name_camel()}';")
        if extra_exports:
            for export in extra_exports:
                write.line(export)
        write.line("")


# endregion


# region TYPES
def write_types(base: Base, output_folder: Path) -> None:
    types_dir = create_dynamic_subdir(output_folder, Paths.TYPES)

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
                options = field.select_options()
                if len(options) > 0:
                    _table_name = table.name_pascal()
                    write.types(
                        field.options_name(),
                        options,
                        f"Select options for `{sanitize_string(field.name)}`",
                    )
            write.endregion()

            # Table Type
            field_names = [sanitize_string(field.name) for field in table.fields]
            field_ids = [field.id for field in table.fields]
            property_names = [field.name_camel() for field in table.fields]

            write.region(table.name_upper())
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

            # Configuration for field mapping dict classes: (suffix, key_attr, value_attr, key_type_suffix, value_type_suffix)
            field_mappings = [
                ("FieldNameIdMapping", "name_sanitized", "id", "Field", "FieldId"),
                ("FieldIdNameMapping", "id", "name_sanitized", "FieldId", "Field"),
                ("FieldIdPropertyMapping", "id", "name_camel", "FieldId", "FieldProperty"),
                ("FieldPropertyIdMapping", "name_camel", "id", "FieldProperty", "FieldId"),
                ("FieldNamePropertyMapping", "name", "name_camel", "Field", "FieldProperty"),
                ("FieldPropertyNameMapping", "name_camel", "name", "FieldProperty", "Field"),
            ]

            def _get(field: Field, attr: str) -> str:
                """Get a field attribute value by name."""
                match attr:
                    case "id":
                        return field.id
                    case "name":
                        return field.name
                    case "name_sanitized":
                        return sanitize_string(field.name)
                    case "name_camel":
                        return field.name_camel()
                    case _:
                        raise ValueError(f"Unknown field attribute: {attr}")

            for suffix, get_1, get_2, type_1, type_2 in field_mappings:
                write.dict_class(
                    f"{table_name}{suffix}",
                    [(_get(field, get_1), _get(field, get_2)) for field in table.fields],
                    first_type=f"{table_name}{type_1}",
                    second_type=f"{table_name}{type_2}",
                    is_value_string=True,
                )

            write.line(f"export interface {table_name}FieldSetIds extends FieldSet {{")
            for field in table.fields:
                write.line_indented("//@ts-ignore")
                write.property_row(field.id, typescript_type(field), optional=True)
            write.line("}")
            write.line_empty()
            write.line(f"export interface {table_name}FieldSet extends FieldSet {{")
            for field in table.fields:
                write.line_indented("//@ts-ignore")
                write.property_row(sanitize_string(field.name), typescript_type(field), is_name_string=True, optional=True)
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
    write_barrel_export(base, types_dir, extra_exports=["export * from './_tables';"])


# endregion


# region MODELS
def write_models(base: Base, output_folder: Path) -> None:
    models_dir = create_dynamic_subdir(output_folder, Paths.MODELS)

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
                options = field.select_options()
                if len(options) > 0:
                    write.line_indented(f"{field.options_name()},")
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
            write.region(table.name_upper())

            write.docstring(f"Model for `{table.name}` ({table.id})", 0)
            write.line(f"export class {model_name} extends AirtableModel<{table_name}FieldSet> {{")
            write.line_indented(f"public static f = {table_name}Formulas")
            write.line_empty()
            for field in table.fields:
                field_name = field.name_camel()
                field_type = typescript_type(field)
                write.docstring(f"`{field.name}` ({field.id})")
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type = field.get_linked_model_name()
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
                field_type = typescript_type(field)
                write.line_indented(f"{field_name}?: {field_type},", 2)
            write.line_indented("}) {")
            write.line_indented("super(id ?? '');", 2)
            for field in table.fields:
                field_name = field.name_camel()
                field_type = typescript_type(field)
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type = field.get_linked_model_name()
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
                    field_type = typescript_type(field)
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
                field_type = typescript_type(field)
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type = field.get_linked_model_name()
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
                field_type = typescript_type(field)
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
    write_barrel_export(base, models_dir)


# endregion


# region TABLES
def write_tables(base: Base, output_folder: Path) -> None:
    tables_dir = create_dynamic_subdir(output_folder, Paths.TABLES)

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
    write_barrel_export(base, tables_dir)


# endregion


# region FORMULA
def write_formula_helpers(base: Base, output_folder: Path) -> None:
    formulas_dir = create_dynamic_subdir(output_folder, Paths.FORMULAS)

    for table in base.tables:
        table_name = table.name_pascal()
        table_name_camel = table.name_camel()
        with WriteToTypeScriptFile(path=formulas_dir / f"{table_name_camel}.ts") as write:
            # Imports
            write.line(
                'import { ID, AttachmentsField, BooleanField, DateField, NumberField, TextField, SingleSelectField, MultiSelectField } from "../../static/formula";'
            )
            write.select_options_import(table, f"../types/{table_name_camel}")
            write.line_empty()

            # Properties
            write.line(f"export namespace {table_name}Formulas {{")
            write.line_indented("export const id: ID = new ID();")
            for field in table.fields:
                property_name = field.name_camel()
                formula_class = field.formula_class()
                if formula_class == "SingleSelectField" or formula_class == "MultiSelectField":
                    write.line_indented(f"export const {property_name}: {formula_class}<{field.options_name()}> = new {formula_class}('{field.id}');")
                else:
                    write.line_indented(f"export const {property_name}: {formula_class} = new {formula_class}('{field.id}');")
            write.line("}")
            write.line_empty()

    # Write barrel export index.ts
    write_barrel_export(base, formulas_dir)


# endregion


# region MAIN CLASS
def write_main_class(base: Base, output_folder: Path) -> None:
    with WriteToTypeScriptFile(path=output_folder / Paths.DYNAMIC / "airtable-main.ts") as write:
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


# endregion


# region INDEX
def write_index(output_folder: Path) -> None:
    with WriteToTypeScriptFile(path=output_folder / Paths.DYNAMIC / "index.ts") as write:
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


# endregion

# region TYPE MAPPING
# Simple Airtable type → TypeScript type mappings
SIMPLE_TS_TYPES: dict[str, str] = {
    "singleLineText": "string",
    "multilineText": "string",
    "url": "string",
    "richText": "string",
    "email": "string",
    "phoneNumber": "string",
    "barcode": "string",
    "checkbox": "boolean",
    "date": "string",
    "dateTime": "string",
    "createdTime": "string",
    "lastModifiedTime": "string",
    "count": "number",
    "autoNumber": "number",
    "percent": "number",
    "currency": "number",
    "number": "number",
    "duration": "number",
    "multipleRecordLinks": "RecordId[]",
    "multipleAttachments": "Attachment[]",
    "singleCollaborator": "Collaborator",
    "lastModifiedBy": "Collaborator",
    "createdBy": "Collaborator",
    "button": "string",
}


def typescript_type(field: Field) -> str:
    """Returns the appropriate TypeScript type for a given Airtable field."""
    airtable_type: FieldType = field.type
    ts_type: str = "any"

    # With calculated fields, we want to know the type of the result
    if field.is_calculated():
        airtable_type = field.result_type()

    # Handle simple type mappings via lookup
    if airtable_type in SIMPLE_TS_TYPES:
        ts_type = SIMPLE_TS_TYPES[airtable_type]

    # Handle complex types with special logic
    elif airtable_type == "singleSelect":
        referenced_field = field.referenced_field()
        select_fields_ids = field.base.select_fields_ids()
        if field.id in select_fields_ids:
            ts_type = field.options_name()
        elif referenced_field and referenced_field.type == "singleSelect" and referenced_field.id in select_fields_ids:
            ts_type = referenced_field.options_name()
        else:
            ts_type = "any"
    elif airtable_type == "multipleSelects":
        select_fields_ids = field.base.select_fields_ids()
        if field.id in select_fields_ids:
            ts_type = f"{field.options_name()}[]"
        else:
            ts_type = "any"
    elif not field.is_valid():
        ts_type = "any"

    # TODO: In the case of some calculated fields, sometimes the result is just too unpredictable.
    # Although the type prediction is basically right, I haven't figured out how to predict if
    # it's a list or not, and sometimes the result is a list with a single null value.
    if not ts_type.endswith("[]"):
        if field.involves_lookup() or field.involves_rollup():
            ts_type = f"{ts_type} | {ts_type}[]"

    return ts_type


# endregion

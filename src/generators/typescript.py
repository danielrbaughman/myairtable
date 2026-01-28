from pathlib import Path

from rich import print

from ..meta import Base, Field, Table
from ..utils import timer
from ..utils.helpers import (
    Paths,
    copy_static_files,
    create_dynamic_subdir,
    reset_folder,
    sanitize_string,
)
from ..utils.verbose import verbose
from ..utils.write_to_file import WriteToFile


class WriteToTypeScriptFile(WriteToFile):
    def __init__(self, path: Path):
        super().__init__(path=path, language="typescript")

    def region(self, text: str):
        self.lines.append(f"// #region {text}")

    def endregion(self):
        self.lines.append("// #endregion")
        self.line_empty()

    def literal(self, name: str, list: list[str]):
        self.line(f"export type {name} = ")
        for item in list:
            if item != list[-1]:
                self.line_indented(f'"{item}" |')
            else:
                self.line_indented(f'"{item}"')

    def str_list(self, name: str, list: list[str], type: str = "string"):
        self.line(f"export const {name}: {type}[] = [")
        for item in list:
            self.line_indented(f'"{item}",')
        self.line("]")

    def docstring(self, text: str, indent: int = 1):
        self.line_indented(f"/** {text} */", indent=indent)

    def types(self, name: str, list: list[str], docstring: str = ""):
        literal_name = f"{name}"
        if docstring:
            self.docstring(docstring)
        self.literal(literal_name, list)
        if docstring:
            self.docstring(docstring)
        self.str_list(f"{name}s", list, type=literal_name)
        self.line_empty()

    def dict_class(
        self, name: str, pairs: list[tuple[str, str]], first_type: str = "string", second_type: str = "string", is_value_string: bool = False
    ):
        self.line(f"export const {name}: Record<{first_type}, {second_type}> = {{")
        for k, v in pairs:
            self.dict_row(k, v, is_value_string)
        self.line("}")
        self.line_empty()

    def dict_row(self, key: str, value: str, is_value_string: bool = False, optional: bool = False):
        if is_value_string:
            self.line_indented(f'"{key}"{"?" if optional else ""}: "{value}",')
        else:
            self.line_indented(f'"{key}"{"?" if optional else ""}: {value},')

    def property_row(self, name: str, type: str, is_name_string: bool = False, optional: bool = False):
        if is_name_string:
            self.line_indented(f'"{name}"{"?" if optional else ""}: {type},')
        else:
            self.line_indented(f"{name}{'?' if optional else ''}: {type}")

    def select_options_import(self, table: Table, from_path: str) -> None:
        """Import select field option types if the table has any select fields."""
        select_fields = table.select_fields()
        if len(select_fields) > 0:
            self.line("import {")
            for field in select_fields:
                self.line_indented(f"{field.options_name()},")
            self.line(f'}} from "{from_path}";')


# region MAIN
def generate_typescript(base: Base, output_folder: Path, formulas: bool = True, wrappers: bool = True, zod: bool = True) -> None:
    print("Generating TypeScript code")
    for table in base.tables:
        table.detect_duplicate_property_names()

    reset_folder(output_folder / Paths.DYNAMIC)
    reset_folder(output_folder / Paths.STATIC)

    with timer.timer("TypeScript: copy_static_files"):
        copy_static_files(output_folder, "typescript")
        if verbose:
            print("[dim] - TypeScript static files copied.[/]")

    with timer.timer("TypeScript: write_types"):
        write_types(base, output_folder)
        if verbose:
            print("[dim] - TypeScript types generated.[/]")

    if formulas:
        with timer.timer("TypeScript: write_formula_helpers"):
            write_formula_helpers(base, output_folder)
            if verbose:
                print("[dim] - TypeScript formula helpers generated.[/]")

    if zod:
        with timer.timer("TypeScript: write_zod_schemas"):
            write_zod_schemas(base, output_folder)
            if verbose:
                print("[dim] - TypeScript Zod schemas generated.[/]")

    if wrappers:
        with timer.timer("TypeScript: write_models"):
            write_models(base, output_folder, formulas=formulas, zod=zod)
            if verbose:
                print("[dim] - TypeScript models generated.[/]")

        with timer.timer("TypeScript: write_tables"):
            write_tables(base, output_folder)
            if verbose:
                print("[dim] - TypeScript tables generated.[/]")

        with timer.timer("TypeScript: write_main_class"):
            write_main_class(base, output_folder)
            if verbose:
                print("[dim] - TypeScript main class generated.[/]")

    with timer.timer("TypeScript: write_index"):
        write_index(output_folder, formulas=formulas, wrappers=wrappers)

    if verbose:
        print("[green] - TypeScript code generation complete.[/]")
        print("")


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
                write.property_row(field.id, field.typescript_type(), optional=True)
            write.line("}")
            write.line_empty()
            write.line(f"export interface {table_name}FieldSet extends FieldSet {{")
            for field in table.fields:
                write.line_indented("//@ts-ignore")
                write.property_row(sanitize_string(field.name), field.typescript_type(), is_name_string=True, optional=True)
            write.line("}")
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

# region ZOD


def write_zod_schemas(base: Base, output_folder: Path) -> None:
    zod_dir = create_dynamic_subdir(output_folder, Paths.ZOD)

    for table in base.tables:
        with WriteToTypeScriptFile(path=zod_dir / f"{table.name_camel()}.ts") as write:
            write.line('import * as z from "zod";')
            write.line(
                'import { recordIdSchema, AirtableAttachmentSchema, AirtableCollaboratorSchema, AirtableButtonSchema, SpecialNumberSchema, ErrorValueSchema } from "../../static/special-types";'
            )

            # Import select option constants from types
            select_fields = table.select_fields()
            if len(select_fields) > 0:
                write.line("import {")
                for field in select_fields:
                    write.line_indented(f"{field.options_name()}s,")
                write.line(f'}} from "../types/{table.name_camel()}";')
            write.line_empty()

            table_name = table.name_pascal()
            write.region(table.name_upper())
            write.line(f"export const {table_name}Schema = z.object({{")
            for field in table.fields:
                field_type = field.zod_type()
                write.line_indented(f"{field.name_camel()}: {field_type},")
            write.line("});")
            write.line_empty()

            # Inferred type from schema
            write.line(f"export type I{table_name} = z.infer<typeof {table_name}Schema>;")
            write.line_empty()
            write.endregion()

    write_barrel_export(base, zod_dir)


# endregion


# region MODELS
def write_models(base: Base, output_folder: Path, formulas: bool = True, zod: bool = True) -> None:
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
            write.line('import { RecordId, AirtableButton } from "../../static/special-types";')
            write.line('import { LinkedRecord, LinkedRecords } from "../../static/linked-record";')
            write.line('import { getOptions, getBaseId } from "../../static/helpers";')

            # Import types for this table
            write.line("import {")
            write.line_indented(f"{table_name}FieldSet,")
            write.line_indented(f"{table_name}Field,")
            write.line_indented(f"{table_name}FieldNameIdMapping,")
            write.line_indented(f"{table_name}FieldIdNameMapping,")
            write.line_indented(f"{table_name}FieldNamePropertyMapping,")
            for field in table.fields:
                options = field.select_options()
                if len(options) > 0:
                    write.line_indented(f"{field.options_name()},")
            write.line(f'}} from "../types/{table_name_camel}";')
            if formulas:
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
            if zod:
                write.line(f"import {{ {table_name}Schema, I{table_name} }} from '../zod/{table_name_camel}';")
            write.endregion()
            write.line_empty()

            # Table Model
            write.region(table.name_upper())

            write.docstring(f"Model for `{table.name}` ({table.id})", 0)
            if zod:
                write.line(f"export class {model_name} extends AirtableModel<{table_name}FieldSet, I{table_name}, {table_name}Field> {{")
                write.line_indented(f"protected static schema = {table_name}Schema;")
            else:
                write.line(f"export class {model_name} extends AirtableModel<{table_name}FieldSet, unknown, {table_name}Field> {{")
            if formulas:
                write.line_indented(f"public static f = {table_name}Formulas")
            write.line_indented(f"protected nameToIdMap = {table_name}FieldNameIdMapping;", 1)
            write.line_indented(f"protected idToNameMap = {table_name}FieldIdNameMapping;", 1)
            write.line_indented(f"protected nameToPropertyMap = {table_name}FieldNamePropertyMapping;", 1)
            write.line_empty()
            for field in table.fields:
                field_name = field.name_camel()
                field_type = field.typescript_type()
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type = field.get_linked_model_name()
                    if field_type == "RecordId":
                        write.line_indented(f"private _{field_name}!: LinkedRecord<{linked_record_type}>;", 1)
                        write.docstring(f"`{field.name}` ({field.id})")
                        write.line_indented(f"public get {field_name}(): LinkedRecord<{linked_record_type}> {{ return this._{field_name}; }}", 1)
                        write.line_indented(
                            f"public set {field_name}(value: LinkedRecord<{linked_record_type}> | undefined) {{ this._{field_name} = value!; this.markDirty('{field_name}'); }}",
                            1,
                        )
                    elif field_type == "RecordId[]":
                        write.line_indented(f"private _{field_name}!: LinkedRecords<{linked_record_type}>;", 1)
                        write.docstring(f"`{field.name}` ({field.id})")
                        write.line_indented(f"public get {field_name}(): LinkedRecords<{linked_record_type}> {{ return this._{field_name}; }}", 1)
                        write.line_indented(
                            f"public set {field_name}(value: LinkedRecords<{linked_record_type}> | undefined) {{ this._{field_name} = value!; this.markDirty('{field_name}'); }}",
                            1,
                        )
                else:
                    write.line_indented(f"private _{field_name}?: {field_type};", 1)
                    write.docstring(f"`{field.name}` ({field.id})")
                    write.line_indented(f"public get {field_name}(): {field_type} | undefined {{ return this._{field_name}; }}", 1)
                    write.line_indented(
                        f"public set {field_name}(value: {field_type} | undefined) {{ this._{field_name} = value; this.markDirty('{field_name}'); }}",
                        1,
                    )
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
                field_type = field.typescript_type()
                write.line_indented(f"{field_name}?: {field_type},", 2)
            write.line_indented("} = {}) {")
            write.line_indented("super(id ?? '');", 2)
            for field in table.fields:
                field_name = field.name_camel()
                field_type = field.typescript_type()
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type = field.get_linked_model_name()
                    if field_type == "RecordId":
                        write.line_indented(
                            f"this._{field_name} = new LinkedRecord<{linked_record_type}>({field_name}, {linked_record_type}.fromId, () => this.markDirty('{field_name}'), this.__configBaseId, this.__configOptions);",
                            2,
                        )
                    elif field_type == "RecordId[]":
                        write.line_indented(
                            f"this._{field_name} = new LinkedRecords<{linked_record_type}>({field_name}, {linked_record_type}.fromId, () => this.markDirty('{field_name}'), this.__configBaseId, this.__configOptions);",
                            2,
                        )
                else:
                    write.line_indented(f"this._{field_name} = {field_name};", 2)
            write.line_indented(
                f"this.record = new Record<{table_name}FieldSet>(new {table_name}Table(this.getInstanceBaseId(), this.getInstanceOptions())._table, this.id, {{}});",
                2,
            )
            write.line_indented("this.updateRecord();", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"public static fromRecord(record: Record<{table_name}FieldSet>, table?: {table_name}Table): {model_name} {{")
            write.line_indented(f"const instance = new {model_name}({{ id: record.id }});", 2)
            write.line_indented("if (table) instance.setConfig(table.baseId, table.options);", 2)
            write.line_indented("instance.updateModel(record);", 2)
            write.line_indented("instance.clearDirtyFlags();", 2)
            write.line_indented("return instance;", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"public static fromId(id: RecordId, baseId?: string, options?: AirtableOptions): {model_name} {{")
            write.line_indented(f"const instance = new {model_name}({{ id }});", 2)
            write.line_indented("if (baseId && options) instance.setConfig(baseId, options);", 2)
            write.line_indented("return instance;", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"protected writableFields(useFieldIds: boolean = true): Partial<{table_name}FieldSet> {{")
            write.line_indented(f"const fields: Partial<{table_name}FieldSet> = {{}};", 2)
            for field in table.fields:
                field_name = field.name_camel()
                if not field.is_computed():
                    field_type = field.typescript_type()
                    write.line_indented(f"if (this._isNew || this.isDirty('{field_name}')) {{", 2)
                    if field_type == "RecordId" or field_type == "RecordId[]":
                        if field_type == "RecordId":
                            write.line_indented(f'fields[useFieldIds ? "{field.id}" : "{sanitize_string(field.name)}"] = this._{field_name}?.id;', 3)
                        elif field_type == "RecordId[]":
                            write.line_indented(f'fields[useFieldIds ? "{field.id}" : "{sanitize_string(field.name)}"] = this._{field_name}?.ids;', 3)
                    elif field_type == "Attachment[]":
                        write.line_indented(
                            f'fields[useFieldIds ? "{field.id}" : "{sanitize_string(field.name)}"] = this.sanitizeAttachment("_{field_name}");',
                            3,
                        )
                    else:
                        write.line_indented(f'fields[useFieldIds ? "{field.id}" : "{sanitize_string(field.name)}"] = this._{field_name};', 3)
                    write.line_indented("}", 2)
            write.line_indented("return fields;", 2)
            write.line_indented("}", 1)
            write.line_empty()

            if zod:
                write.line_indented(f"public toJson(): I{table_name} {{")
            else:
                write.line_indented("public toJson(): { [key: string]: unknown } {")
            write.line_indented("return {", 2)
            for field in table.fields:
                field_name = field.name_camel()
                field_type = field.typescript_type()
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    if field_type == "RecordId":
                        write.line_indented(f"{field_name}: this._{field_name}?.id,", 3)
                    else:
                        write.line_indented(f"{field_name}: this._{field_name}?.ids,", 3)
                else:
                    write.line_indented(f"{field_name}: this._{field_name},", 3)
            write.line_indented("};", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented(f"protected updateModel(record: Record<{table_name}FieldSet>) {{")
            write.line_indented("this.record = record;", 2)
            for field in table.fields:
                field_name = field.name_camel()
                field_type = field.typescript_type()
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type = field.get_linked_model_name()
                    if field_type == "RecordId":
                        write.line_indented(
                            f'this._{field_name} = new LinkedRecord<{linked_record_type}>((record.get("{field.id}") ?? record.get("{sanitize_string(field.name)}")) as {field_type}, {linked_record_type}.fromId, () => this.markDirty(\'{field_name}\'), this.__configBaseId, this.__configOptions);',
                            2,
                        )
                    elif field_type == "RecordId[]":
                        write.line_indented(
                            f'this._{field_name} = new LinkedRecords<{linked_record_type}>((record.get("{field.id}") ?? record.get("{sanitize_string(field.name)}")) as {field_type}, {linked_record_type}.fromId, () => this.markDirty(\'{field_name}\'), this.__configBaseId, this.__configOptions);',
                            2,
                        )
                else:
                    write.line_indented(
                        f'this._{field_name} = (record.get("{field.id}") ?? record.get("{sanitize_string(field.name)}")) as {field_type};', 2
                    )
            write.line_indented("this.validate();", 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line_indented("protected updateRecord() {")
            write.line_indented("if (!this.record) ", 2)
            write.line_indented(
                'throw new Error("Cannot convert to record: record is undefined. Please use fromRecord to initialize the instance.");', 3
            )
            for field in table.fields:
                field_name = field.name_camel()
                field_type = field.typescript_type()
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    if field_type == "RecordId":
                        write.line_indented("//@ts-ignore", 2)
                        write.line_indented(f'this.record.set("{field.id}", this._{field_name}?.id);', 2)
                    elif field_type == "RecordId[]":
                        write.line_indented("//@ts-ignore", 2)
                        write.line_indented(f'this.record.set("{field.id}", this._{field_name}?.ids);', 2)
                else:
                    write.line_indented("//@ts-ignore", 2)
                    write.line_indented(f'this.record.set("{field.id}", this._{field_name});', 2)
            write.line_indented("}", 1)
            write.line_empty()

            write.line("}")
            write.endregion()

    with WriteToTypeScriptFile(path=models_dir / "_models.ts") as write:
        write.line("import {")
        for table in base.tables:
            model_name = table.name_model()
            write.line_indented(f"{model_name},")
        write.line('} from ".";')
        write.line_empty()

        model_names = [table.name_model() for table in base.tables]
        write.line(f"export type ModelUnion = {' | '.join(model_names)};")
        write.line_empty()

    # Write barrel export index.ts
    write_barrel_export(base, models_dir, extra_exports=["export * from './_models';"])


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
                f'super(baseId, "{table.id}", {table_name}ViewNameIdMapping, (record) => {model_name}.fromRecord(record, this), options);',
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
        write.line('import { getApiKey, getBaseId, setAirtableConfig } from "../static/helpers";')
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
        write.line_indented("setAirtableConfig(_baseId, _options);", 2)
        for table in base.tables:
            table_name_camel = table.name_camel()
            table_name_pascal = table.name_pascal()
            write.line_indented(f"this.{table_name_camel} = new {table_name_pascal}Table(_baseId, _options);", 2)
        write.line_indented("}")
        write.line("}")


# endregion


# region INDEX
def write_index(output_folder: Path, formulas: bool = True, wrappers: bool = True) -> None:
    with WriteToTypeScriptFile(path=output_folder / Paths.DYNAMIC / "index.ts") as write:
        if wrappers:
            write.line('export * from "./airtable-main";')
            write.line('export * from "./tables";')
            write.line('export * from "./models";')
        write.line('export * from "./types";')
        if formulas:
            write.line('export * from "./formulas";')
        write.line("")

    with WriteToTypeScriptFile(path=output_folder / "index.ts") as write:
        write.line('export * from "./dynamic";')
        if formulas:
            write.line('export * from "./static/formula";')
        if wrappers:
            write.line('export * from "./static/airtable-model";')
        write.line("")


# endregion

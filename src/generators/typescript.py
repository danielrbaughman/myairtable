import json
from pathlib import Path

from rich import print

from ..formulas.formula_flattener import flatten_formula_for_transpilation
from ..formulas.formula_transpiler import transpile_table_formulas
from ..meta import Base, Field, Table
from ..utils import timer
from ..utils.helpers import (
    Paths,
    copy_static_files,
    create_dynamic_subdir,
    deduplicate_names,
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

    def docstring(self, text: str | list[str], indent: int = 1):
        if isinstance(text, list):
            self.line_indented("/**", indent=indent)
            for line in text:
                self.line_indented(f" * {line}", indent=indent)
            self.line_indented(" */", indent=indent)
        else:
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
def generate_typescript(
    base: Base, output_folder: Path, formulas: bool = True, wrappers: bool = True, runtime: bool = True, flatten: bool = False, zod: bool = True
) -> None:
    print("Generating TypeScript code")
    for table in base.tables:
        table.detect_duplicate_property_names()

    reset_folder(output_folder / Paths.DYNAMIC)
    reset_folder(output_folder / Paths.STATIC)

    with timer.timer("TypeScript: copy_static_files"):
        exclude = ["airtable-runtime.ts"] if not runtime else None
        copy_static_files(output_folder, "typescript", exclude=exclude)
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

    with timer.timer("TypeScript: write_options"):
        write_options(base, output_folder)
        if verbose:
            print("[dim] - TypeScript options generated.[/]")

    if zod:
        with timer.timer("TypeScript: write_zod_schemas"):
            write_zod_schemas(base, output_folder)
            if verbose:
                print("[dim] - TypeScript Zod schemas generated.[/]")

    if wrappers:
        with timer.timer("TypeScript: write_models"):
            write_models(base, output_folder, formulas=formulas, runtime=runtime, flatten=flatten, zod=zod)
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
            write.docstring(f"Writable fields for `{table.name}`")
            write.str_list(
                f"{table_name}WritableFields",
                [sanitize_string(field.name) for field in table.fields if not field.is_computed()],
            )
            write.docstring(f"Writable fields for `{table.name}`")
            write.str_list(
                f"{table_name}WritableFieldIds",
                [field.id for field in table.fields if not field.is_computed()],
            )

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
                ts_type = field.typescript_type()
                # Airtable API always uses arrays for link fields, even single-link ones
                if ts_type == "RecordId":
                    ts_type = "RecordId[]"
                # Airtable's Attachment type has all fields required, but the API only needs { url } for writes
                if ts_type == "Attachment[]":
                    ts_type = "Partial<Attachment>[]"
                write.property_row(field.id, ts_type, optional=True)
            write.line("}")
            write.line_empty()
            write.line(f"export interface {table_name}FieldSet extends FieldSet {{")
            for field in table.fields:
                write.line_indented("//@ts-ignore")
                ts_type = field.typescript_type()
                if ts_type == "RecordId":
                    ts_type = "RecordId[]"
                if ts_type == "Attachment[]":
                    ts_type = "Partial<Attachment>[]"
                write.property_row(sanitize_string(field.name), ts_type, is_name_string=True, optional=True)
            write.line("}")
            write.line_empty()

            views = table.views
            view_names: list[str] = deduplicate_names([sanitize_string(view.name) for view in views])
            view_ids: list[str] = [view.id for view in views]
            write.types(f"{table_name}View", view_names, f"View names for `{table.name}`")
            write.types(f"{table_name}ViewId", view_ids, f"View IDs for `{table.name}`")
            write.dict_class(
                f"{table_name}ViewNameIdMapping",
                list(zip(view_names, view_ids)),
                first_type=f"{table_name}View",
                second_type=f"{table_name}ViewId",
                is_value_string=True,
            )
            write.dict_class(
                f"{table_name}ViewIdNameMapping",
                list(zip(view_ids, view_names)),
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
        write.types("TablePropertyName", [table.name_camel() for table in base.tables])
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
            "TableNamePropertyMapping",
            [(table.name, table.name_camel()) for table in base.tables],
            first_type="TableName",
            second_type="string",
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

            write.line_empty()

            table_name = table.name_pascal()
            write.region(table.name_upper())
            write.line(f"export const {table_name}Schema = z.object({{")
            write.line_indented("id: recordIdSchema.optional(),")
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
def write_models(base: Base, output_folder: Path, formulas: bool = True, runtime: bool = True, flatten: bool = False, zod: bool = True) -> None:
    models_dir = create_dynamic_subdir(output_folder, Paths.MODELS)

    # Write individual table model files
    for table in base.tables:
        table_name = table.name_pascal()
        table_name_camel = table.name_camel()
        model_name = table.name_model()
        with WriteToTypeScriptFile(path=models_dir / f"{table_name_camel}.ts") as write:
            # Imports
            write.line('import { AirtableOptions, Attachment, Collaborator, FieldSet, Record } from "airtable";')
            write.line('import { AirtableModel, FieldDescriptor } from "../../static/airtable-model";')
            write.line('import { RecordId, AirtableButton } from "../../static/special-types";')
            write.line('import { LinkedRecord, LinkedRecords, ChainableLinkedRecord } from "../../static/linked-record";')
            write.line('import { buildUrl } from "../../static/helpers";')

            # Import types for this table
            write.line("import {")
            write.line_indented(f"{table_name}FieldSet,")
            write.line_indented(f"{table_name}Field,")
            write.line_indented(f"{table_name}View,")
            write.line_indented(f"{table_name}ViewNameIdMapping,")
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
            if len(table.select_fields()) > 0:
                write.line(f"import {{ {table_name}Options }} from '../options/{table_name_camel}';")

            linked_tables = table.linked_tables()
            if linked_tables:
                write.line("import {")
                for _table in linked_tables:
                    write.line_indented(f"{_table.name_model()},")
                write.line('} from "../models";')

            # Import table class for this table
            write.line(f"import {{ {table_name}Table }} from '../tables/{table_name_camel}';")
            if zod:
                write.line(f"import {{ {table_name}Schema, I{table_name} }} from '../zod/{table_name_camel}';")

            # Pre-transpile formula fields and add AirtableRuntime import if any succeed
            formula_field_ids = table.formula_field_ids()
            if runtime:
                linked_record_field_ids = table.linked_record_field_ids()
                single_linked_record_field_ids = table.single_linked_record_field_ids()
                field_name_map = {f.id: f.name_camel() for f in table.fields}
                raw_formulas = {f.id: f.options.formula for f in table.fields if f.is_formula() and f.options and f.options.formula}
                if flatten and raw_formulas:
                    formula_map_tuple = table.base.get_formula_field_map_tuple()
                    raw_formulas = {fid: flatten_formula_for_transpilation(f, fid, formula_map_tuple) for fid, f in raw_formulas.items()}
                transpiled_formulas = transpile_table_formulas(
                    raw_formulas, "typescript", field_name_map, formula_field_ids, linked_record_field_ids, single_linked_record_field_ids
                )
                has_any_formula = any(f.is_formula() for f in table.fields)
                if has_any_formula:
                    write.line('import { AirtableRuntime as F } from "../../static/airtable-runtime";')
            else:
                transpiled_formulas = {}
            write.line_empty()

            # Table Model
            write.docstring(f"Model for `{table.name}` ({table.id})", 0)
            if zod:
                write.line(f"export class {model_name} extends AirtableModel<{table_name}FieldSet, I{table_name}, {table_name}Field> {{")
                write.line_indented(f"protected static schema = {table_name}Schema;")
            else:
                write.line(f"export class {model_name} extends AirtableModel<{table_name}FieldSet, unknown, {table_name}Field> {{")
            if formulas:
                write.line_indented(f"public static f = {table_name}Formulas")
            if len(table.select_fields()) > 0:
                write.line_indented(f"public static o = {table_name}Options")
            write.line_indented(f"protected static nameToIdMap = {table_name}FieldNameIdMapping;", 1)
            write.line_indented(f"protected static idToNameMap = {table_name}FieldIdNameMapping;", 1)
            write.line_indented(f"protected static nameToPropertyMap = {table_name}FieldNamePropertyMapping;", 1)
            write.line_empty()
            write.docstring(f"Table name ({table.name})", 1)
            write.line_indented(f"public static tableName: string = '{table.name}';", 1)
            write.docstring(f"Table name ({table.name})", 1)
            write.line_indented(f"public get tableName(): string {{ return {model_name}.tableName; }}", 1)
            write.line_empty()
            write.docstring(f"Table ID ({table.id})", 1)
            write.line_indented(f"public static tableId: string = '{table.id}';", 1)
            write.docstring(f"Table ID ({table.id})", 1)
            write.line_indented(f"public get tableId(): string {{ return {model_name}.tableId; }}", 1)
            write.line_empty()

            # Field descriptors
            write.line_indented("protected static fieldDescriptors: FieldDescriptor[] = [", 1)
            for field in table.fields:
                field_name = field.name_camel()
                field_type = field.typescript_type()
                is_computed = "true" if field.is_computed() else "false"
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type = field.get_linked_model_name()
                    field_kind = "linkedRecord" if field_type == "RecordId" else "linkedRecords"
                    write.line_indented(
                        f'{{ propertyName: "{field_name}", fieldId: "{field.id}", fieldName: "{sanitize_string(field.name)}", isComputed: {is_computed}, fieldType: "{field_kind}", linkedModelFromId: (id, config) => {linked_record_type}.fromId(id, config), linkedModelClass: {linked_record_type} as any }},',
                        2,
                    )
                elif field_type == "Attachment[]":
                    write.line_indented(
                        f'{{ propertyName: "{field_name}", fieldId: "{field.id}", fieldName: "{sanitize_string(field.name)}", isComputed: {is_computed}, fieldType: "attachment" }},',
                        2,
                    )
                else:
                    write.line_indented(
                        f'{{ propertyName: "{field_name}", fieldId: "{field.id}", fieldName: "{sanitize_string(field.name)}", isComputed: {is_computed}, fieldType: "generic" }},',
                        2,
                    )
            write.line_indented("];", 1)
            write.line_empty()

            for field in table.fields:
                field_name = field.name_camel()
                field_type = field.typescript_type()
                docstring: str | list[str]
                if field.formula(sanitized=True, condense=True):
                    docstring: list[str] = [
                        f"`{field.name}` ({field.id})",
                        "",
                        "```",
                        *[line for line in field.formula(sanitized=True, format=True).splitlines()],
                        "```",
                    ]
                else:
                    docstring: str = f"`{field.name}` ({field.id})"

                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type = field.get_linked_model_name()
                    if field_type == "RecordId":
                        write.docstring(docstring)
                        write.line_indented(
                            f'public get {field_name}(): ChainableLinkedRecord<{linked_record_type}> {{ return this._fields["{field_name}"] as ChainableLinkedRecord<{linked_record_type}>; }}',
                            1,
                        )
                        write.line_indented(
                            f"public set {field_name}(value: {linked_record_type} | LinkedRecord<{linked_record_type}> | RecordId | undefined) {{ this._setLinkedField('{field_name}', value); }}",
                            1,
                        )
                    elif field_type == "RecordId[]":
                        write.docstring(docstring)
                        write.line_indented(
                            f'public get {field_name}(): LinkedRecords<{linked_record_type}> {{ return this._fields["{field_name}"] as LinkedRecords<{linked_record_type}>; }}',
                            1,
                        )
                        write.line_indented(
                            f"public set {field_name}(value: {linked_record_type}[] | LinkedRecords<{linked_record_type}> | RecordId[] | undefined) {{ this._setLinkedRecordsField('{field_name}', value); }}",
                            1,
                        )
                elif field.is_formula() and runtime:
                    # Formula field -> computed property that checks evaluateFormulasAtRuntime
                    write.docstring(docstring)
                    write.line_indented(f"public get {field_name}(): {field_type} | undefined {{", 1)
                    if field.id in transpiled_formulas:
                        formula_code = transpiled_formulas[field.id]
                        write.line_indented(f'if (this.evaluateFormulasAtRuntime) this._fields["{field_name}"] = {formula_code};', 2)
                    write.line_indented(f'return this._fields["{field_name}"] as {field_type};', 2)
                    write.line_indented("}", 1)
                elif field.is_computed():
                    # Computed: getter only (TypeScript enforces read-only at compile time)
                    write.docstring(docstring)
                    write.line_indented(
                        f'public get {field_name}(): {field_type} | undefined {{ return this._fields["{field_name}"] as {field_type}; }}', 1
                    )
                else:
                    # Writable: getter + setter
                    write.docstring(docstring)
                    write.line_indented(
                        f'public get {field_name}(): {field_type} | undefined {{ return this._fields["{field_name}"] as {field_type}; }}', 1
                    )
                    write.line_indented(
                        f"public set {field_name}(value: {field_type} | undefined) {{ this._fields[\"{field_name}\"] = value; this.markDirty('{field_name}'); }}",
                        1,
                    )
            write.line_empty()
            if zod:
                write.line_indented(f"constructor(data: I{table_name} = {{}}) {{")
            else:
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
            prefix = "data." if zod else ""
            write.line_indented(f"super({prefix}id ?? '');", 2)
            if zod:
                write.line_indented("this.initializeFields(data);", 2)
            else:
                # Build data object from destructured params and use initializeFields
                field_names = [field.name_camel() for field in table.fields]
                fields_obj = ", ".join(field_names)
                write.line_indented(f"this.initializeFields({{ {fields_obj} }});", 2)
            write.line_indented(
                f"this.record = new Record<{table_name}FieldSet>(new {table_name}Table(this.getInstanceBaseId(), this.getInstanceOptions())._table, this.id, {{}});",
                2,
            )
            write.line_indented("this.updateRecord();", 2)
            write.line_indented("}", 1)
            write.line_empty()

            # url
            has_field_called_url: bool = any(field.name_camel() == "url" for field in table.fields)
            url_method_name: str = "URL" if has_field_called_url else "url"
            write.docstring("Get the URL for this record in Airtable, with optional view.", 1)
            write.line_indented(f"public {url_method_name}(view?: {table_name}View): string {{")
            write.line_indented("if (view) {", 2)
            write.line_indented(f"return buildUrl(this.getInstanceBaseId(), '{table.id}', this.id, {table_name}ViewNameIdMapping[view]);", 3)
            write.line_indented("} else {", 2)
            write.line_indented(f"return buildUrl(this.getInstanceBaseId(), '{table.id}', this.id);", 3)
            write.line_indented("}", 2)
            write.line_indented("}")
            write.line_empty()

            write.line("}")

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
            write.line_indented(f"{table_name}FieldNameIdMapping,")
            write.line_indented(f"{table_name}FieldIdNameMapping,")
            write.line_indented(f"{table_name}WritableFieldIds,")
            write.line(f'}} from "../types/{table_name_camel}";')
            write.line(f"import {{ {model_name} }} from '../models/{table_name_camel}';")
            write.line('import { AirtableOptions } from "airtable";')
            write.endregion()
            write.line_empty()

            write.line(
                f"export class {table_name}Table extends AirtableTable<{table_name}FieldSet, {model_name}, {table_name}View, {table_name}Field> {{"
            )
            write.docstring(f"Table name ({table.name})", 1)
            write.line_indented(f'public static tableName: string = "{table.name}";')
            write.docstring(f"Table name ({table.name})", 1)
            write.line_indented(f"public get tableName(): string {{ return {table_name}Table.tableName; }}")
            write.line_empty()
            write.docstring(f"Table ID ({table.id})", 1)
            write.line_indented(f'public static tableId: string = "{table.id}";')
            write.docstring(f"Table ID ({table.id})", 1)
            write.line_indented(f"public get tableId(): string {{ return {table_name}Table.tableId; }}")
            write.line_empty()
            write.line_indented("constructor(baseId: string, options: AirtableOptions) {")
            write.line_indented(
                f'super(baseId, "{table.id}", {table_name}ViewNameIdMapping, {table_name}FieldNameIdMapping, {table_name}FieldIdNameMapping, {table_name}WritableFieldIds, (record) => {model_name}.fromRecord(record, {{ baseId: this.baseId, ...this._options }}, false), options);',
                2,
            )
            write.line_indented("}")
            write.line("}")

    with WriteToTypeScriptFile(path=tables_dir / "_tables.ts") as write:
        write.line("import {")
        for table in base.tables:
            table_name = table.name_pascal() + "Table"
            write.line_indented(f"{table_name},")
        write.line('} from ".";')
        write.line_empty()

        table_names = [table.name_pascal() + "Table" for table in base.tables]
        write.line(f"export type TableUnion = {' | '.join(table_names)};")
        write.line_empty()

        # Add TableNameToTableType mapping interface for type-safe dynamic table lookup
        write.line("export interface TableNameToTableType {")
        for table in base.tables:
            table_name_pascal = table.name_pascal()
            write.line_indented(f'"{table.name}": {table_name_pascal}Table;')
        write.line("}")
        write.line_empty()

    # Write barrel export index.ts
    write_barrel_export(base, tables_dir, extra_exports=["export * from './_tables';"])


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
                'import { ID, AttachmentsField, BooleanField, DateField, LookupField, NumberField, TextField, SingleSelectField, MultiSelectField } from "../../static/formula";'
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


def write_options(base: Base, output_folder: Path) -> None:
    options_dir = create_dynamic_subdir(output_folder, Paths.OPTIONS)

    for table in base.tables:
        table_name = table.name_pascal()
        table_name_camel = table.name_camel()
        select_fields = table.select_fields()
        with WriteToTypeScriptFile(path=options_dir / f"{table_name_camel}.ts") as write:
            if len(select_fields) > 0:
                # Import the const arrays from types
                write.line("import {")
                for field in select_fields:
                    write.line_indented(f"{field.options_name()}s,")
                write.line(f'}} from "../types/{table_name_camel}";')
                write.line_empty()

            # Namespace with property per select field
            write.line(f"export namespace {table_name}Options {{")
            for field in select_fields:
                write.line_indented(f"export const {field.name_camel()} = {field.options_name()}s;")
            write.line("}")
            write.line_empty()

    # Write barrel export index.ts
    write_barrel_export(base, options_dir)


# endregion


# region MAIN CLASS
def write_main_class(base: Base, output_folder: Path) -> None:
    with WriteToTypeScriptFile(path=output_folder / Paths.DYNAMIC / "airtable-main.ts") as write:
        # Imports
        write.line('import { ExtendedAirtableOptions } from "../static/special-types";')
        write.line('import { BaseSchema } from "../static/schema-types";')
        write.line('import { getApiKey, getBaseId, setAirtableConfig, buildUrl } from "../static/helpers";')
        write.line("import {")
        for table in base.tables:
            table_name_pascal = table.name_pascal()
            write.line_indented(f"{table_name_pascal}Table,")
        write.line_indented("TableNameToTableType,")
        write.line('} from "./tables";')
        write.line('import { TableName, TableNamePropertyMapping } from "./types";')
        write.line_empty()

        write.docstring("Airtable base wrapper")
        write.line("export class Airtable {")
        schema_json = json.dumps(base.to_dict())
        write.line_indented("public baseId: string;")
        write.line_indented(f"public static schema: BaseSchema = {schema_json};")
        write.line_empty()
        for table in base.tables:
            table_name_camel = table.name_camel()
            table_name_pascal = table.name_pascal()
            write.docstring(f"`{table.name}` ({table.id})", 1)
            write.line_indented(f"public {table_name_camel}: {table_name_pascal}Table;")
        write.line_empty()
        write.line_indented("constructor(options?: ExtendedAirtableOptions) {")
        write.line_indented("this.baseId = options?.baseId || getBaseId();", 2)
        write.line_indented("const _options = {", 2)
        write.line_indented("  apiKey: options?.apiKey ?? getApiKey(),", 3)
        write.line_indented("  apiVersion: options?.apiVersion,", 3)
        write.line_indented("  customHeaders: options?.customHeaders,", 3)
        write.line_indented("  endpointUrl: options?.endpointUrl,", 3)
        write.line_indented("  noRetryIfRateLimited: options?.noRetryIfRateLimited ?? false,", 3)
        write.line_indented("  requestTimeout: options?.requestTimeout,", 3)
        write.line_indented("  cacheSeconds: options?.cacheSeconds,", 3)
        write.line_indented("};", 2)
        write.line_indented("setAirtableConfig(this.baseId, _options);", 2)
        for table in base.tables:
            table_name_camel = table.name_camel()
            table_name_pascal = table.name_pascal()
            write.line_indented(f"this.{table_name_camel} = new {table_name_pascal}Table(this.baseId, _options);", 2)
        write.line_indented("}")
        write.line_empty()
        write.line_empty()
        write.docstring("Get a table by its Airtable name.", 1)
        write.line_indented("public table<T extends TableName>(tableName: T): TableNameToTableType[T] {")
        write.line_indented("return this[TableNamePropertyMapping[tableName] as keyof this] as TableNameToTableType[T];", 2)
        write.line_indented("}")
        write.line_empty()
        write.docstring("Get the URL for the Airtable base.", 1)
        write.line_indented("public url(): string {")
        write.line_indented("return buildUrl(this.baseId);", 2)
        write.line_indented("}")
        write.line_empty()
        write.docstring("Fetch a live version of the schema from Airtable's metadata API.", 1)
        write.line_indented("public async getSchema(): Promise<BaseSchema> {")
        write.line_indented("const url = `https://api.airtable.com/v0/meta/bases/${this.baseId}/tables`;", 2)
        write.line_indented("const response = await fetch(url, {", 2)
        write.line_indented("headers: { Authorization: `Bearer ${getApiKey(this.baseId)}` },", 3)
        write.line_indented("});", 2)
        write.line_indented("if (!response.ok) {", 2)
        write.line_indented("throw new Error(`Failed to fetch schema: ${response.status} ${response.statusText}`);", 3)
        write.line_indented("}", 2)
        write.line_indented("return response.json();", 2)
        write.line_indented("}")
        write.line_empty()
        write.docstring("Invalidates the cache for all tables.", 1)
        write.line_indented("public invalidateCache(): void {")
        for table in base.tables:
            write.line_indented(f"this.{table.name_camel()}.invalidateCache();", 2)
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
        write.line('export * from "./options";')
        write.line("")

    with WriteToTypeScriptFile(path=output_folder / "index.ts") as write:
        write.line('export * from "./dynamic";')
        if formulas:
            write.line('export * from "./static/formula";')
        if wrappers:
            write.line('export * from "./static/airtable-model";')
        write.line('export * from "./static/special-types";')
        write.line("")


# endregion

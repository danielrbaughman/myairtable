import json
from pathlib import Path

from rich import print

from ..formulas.formula_flattener import flatten_formula_for_transpilation
from ..formulas.formula_transpiler import transpile_table_formulas
from ..meta import Base, Field, Table
from ..utils.helpers import (
    Paths,
    copy_static_files,
    create_dynamic_subdir,
    deduplicate_names,
    escape_for_double_quoted_string,
    reset_folder,
    sanitize_string,
)
from ..utils.verbose import verbose
from ..utils.write_to_file import ImportGroup, ImportSymbol, WriteToFile


class WriteToJavaScriptFile(WriteToFile):
    def __init__(self, path: Path):
        super().__init__(path=path, language="javascript")

    def region(self, text: str):
        self.lines.append(f"// #region {text}")

    def endregion(self):
        self.lines.append("// #endregion")
        self.line_empty()

    def const_array(self, name: str, items: list[str], docstring: str = ""):
        """Generate a const array: const Name = ["a", "b"];"""
        if docstring:
            self.docstring(docstring, indent=0)
        self.line(f"const {name} = [")
        for item in items:
            self.line_indented(f'"{escape_for_double_quoted_string(item)}",')
        self.line("];")
        self.line_empty()

    def const_object(self, name: str, pairs: list[tuple[str, str]], is_value_string: bool = True, docstring: str = ""):
        """Generate a const object: const Name = { key: "value" };"""
        if docstring:
            self.docstring(docstring, indent=0)
        self.line(f"const {name} = {{")
        for k, v in pairs:
            escaped_key = escape_for_double_quoted_string(k)
            if is_value_string:
                self.line_indented(f'"{escaped_key}": "{escape_for_double_quoted_string(v)}",')
            else:
                self.line_indented(f'"{escaped_key}": {v},')
        self.line("};")
        self.line_empty()

    def docstring(self, text: str | list[str], indent: int = 1):
        if isinstance(text, list):
            self.line_indented("/**", indent=indent)
            for line in text:
                self.line_indented(f" * {line}", indent=indent)
            self.line_indented(" */", indent=indent)
        else:
            self.line_indented(f"/** {text} */", indent=indent)

    def require_statement(self, names: list[str], path: str):
        """Generate: const { X, Y } = require("path");"""
        if len(names) == 1:
            self.line(f'const {{ {names[0]} }} = require("{path}");')
        else:
            self.line("const {")
            for name in names:
                self.line_indented(f"{name},")
            self.line(f'}} = require("{path}");')

    def module_exports(self, names: list[str]):
        """Generate: module.exports = { X, Y };"""
        if len(names) <= 3:
            self.line(f"module.exports = {{ {', '.join(names)} }};")
        else:
            self.line("module.exports = {")
            for name in names:
                self.line_indented(f"{name},")
            self.line("};")

    def select_options_require(self, table: Table, from_path: str) -> list[str]:
        """Register select field option arrays (resolved against usage). Returns the candidate names."""
        names: list[str] = []
        if len(table.select_fields()) > 0:
            for field in table.select_fields():
                names.append(f"{field.options_name()}s")
            self.add_import(from_path, list(names))
        return names

    def _render_import_group(self, group: ImportGroup, used: list[ImportSymbol]) -> list[str]:
        names = [sym.name for sym in used]
        if len(names) == 1:
            return [f'const {{ {names[0]} }} = require("{group.module}");']
        lines = ["const {"]
        lines += [f"    {name}," for name in names]
        lines.append(f'}} = require("{group.module}");')
        return lines


# region MAIN
def generate_javascript(
    base: Base, output_folder: Path, formulas: bool = True, wrappers: bool = True, runtime: bool = True, flatten: bool = False, zod: bool = True
) -> None:
    print("Generating JavaScript code")
    for table in base.tables:
        table.detect_duplicate_property_names()

    reset_folder(output_folder / Paths.DYNAMIC)
    reset_folder(output_folder / Paths.STATIC)

    exclude = ["airtable-runtime.js"] if not runtime else None
    copy_static_files(output_folder, "javascript", exclude=exclude)
    if verbose:
        print("[dim] - JavaScript static files copied.[/]")

    write_types(base, output_folder)
    if verbose:
        print("[dim] - JavaScript types generated.[/]")

    if formulas:
        write_formula_helpers(base, output_folder)
        if verbose:
            print("[dim] - JavaScript formula helpers generated.[/]")

    write_options(base, output_folder)
    if verbose:
        print("[dim] - JavaScript options generated.[/]")

    if zod:
        write_zod_schemas(base, output_folder)
        if verbose:
            print("[dim] - JavaScript Zod schemas generated.[/]")

    if wrappers:
        write_models(base, output_folder, formulas=formulas, runtime=runtime, flatten=flatten, zod=zod)
        if verbose:
            print("[dim] - JavaScript models generated.[/]")

        write_tables(base, output_folder)
        if verbose:
            print("[dim] - JavaScript tables generated.[/]")

        write_main_class(base, output_folder)
        if verbose:
            print("[dim] - JavaScript main class generated.[/]")

    write_index(output_folder, formulas=formulas, wrappers=wrappers)

    if verbose:
        print("[green] - JavaScript code generation complete.[/]")
        print("")


def write_barrel_export(base: Base, directory: Path, extra_exports: list[str] | None = None) -> None:
    """Generate index.js barrel export for a directory using CommonJS spread syntax."""
    with WriteToJavaScriptFile(path=directory / "index.js") as write:
        write.line("module.exports = {")
        for table in base.tables:
            write.line_indented(f"...require('./{table.name_camel()}'),")
        if extra_exports:
            for export in extra_exports:
                write.line_indented(export)
        write.line("};")
        write.line("")


# endregion


# region TYPES
def write_types(base: Base, output_folder: Path) -> None:
    types_dir = create_dynamic_subdir(output_folder, Paths.TYPES)

    for table in base.tables:
        # Track all exports for this file
        exports: list[str] = []

        with WriteToJavaScriptFile(path=types_dir / f"{table.name_camel()}.js") as write:
            # Field Options
            write.region("FIELD OPTIONS")
            for field in table.fields:
                options = field.select_options()
                if len(options) > 0:
                    option_name = f"{field.options_name()}s"
                    write.const_array(option_name, options, f"Select options for `{sanitize_string(field.name)}`")
                    exports.append(option_name)

                # For singleSelect / multipleSelects, also emit name<->id maps so
                # callers can (de)serialize using the stable Airtable option id
                # instead of the option name. Renaming an option then doesn't
                # break stored data.
                choices = field.select_option_choices()
                if choices:
                    option_type = field.options_name()
                    name_id_mapping = f"{option_type}NameIdMapping"
                    id_name_mapping = f"{option_type}IdNameMapping"
                    write.const_object(name_id_mapping, choices, is_value_string=True)
                    exports.append(name_id_mapping)
                    write.const_object(id_name_mapping, [(id_, name) for (name, id_) in choices], is_value_string=True)
                    exports.append(id_name_mapping)
            write.endregion()

            # Table Types
            field_names = [sanitize_string(field.name) for field in table.fields]
            field_ids = [field.id for field in table.fields]
            property_names = [field.name_camel() for field in table.fields]

            write.region(table.name_upper())

            # Field arrays
            write.const_array(f"{table.name_pascal()}Fields", field_names, f"Field names for `{table.name}`")
            exports.append(f"{table.name_pascal()}Fields")

            write.const_array(f"{table.name_pascal()}FieldIds", field_ids, f"Field IDs for `{table.name}`")
            exports.append(f"{table.name_pascal()}FieldIds")

            write.const_array(f"{table.name_pascal()}FieldProperties", property_names, f"Property names for `{table.name}`")
            exports.append(f"{table.name_pascal()}FieldProperties")

            write.const_array(
                f"{table.name_pascal()}CalculatedFields",
                [sanitize_string(field.name) for field in table.fields if field.is_computed()],
                f"Calculated fields for `{table.name}`",
            )
            exports.append(f"{table.name_pascal()}CalculatedFields")

            write.const_array(
                f"{table.name_pascal()}CalculatedFieldIds",
                [field.id for field in table.fields if field.is_computed()],
                f"Calculated field IDs for `{table.name}`",
            )
            exports.append(f"{table.name_pascal()}CalculatedFieldIds")

            write.const_array(
                f"{table.name_pascal()}WritableFields",
                [sanitize_string(field.name) for field in table.fields if not field.is_computed()],
                f"Writable fields for `{table.name}`",
            )
            exports.append(f"{table.name_pascal()}WritableFields")

            write.const_array(
                f"{table.name_pascal()}WritableFieldIds",
                [field.id for field in table.fields if not field.is_computed()],
                f"Writable field IDs for `{table.name}`",
            )
            exports.append(f"{table.name_pascal()}WritableFieldIds")

            # Field mapping dictionaries
            field_mappings = [
                ("FieldNameIdMapping", "name_sanitized", "id"),
                ("FieldIdNameMapping", "id", "name_sanitized"),
                ("FieldIdPropertyMapping", "id", "name_camel"),
                ("FieldPropertyIdMapping", "name_camel", "id"),
                ("FieldNamePropertyMapping", "name", "name_camel"),
                ("FieldPropertyNameMapping", "name_camel", "name"),
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

            for suffix, get_1, get_2 in field_mappings:
                mapping_name = f"{table.name_pascal()}{suffix}"
                write.const_object(
                    mapping_name,
                    [(_get(field, get_1), _get(field, get_2)) for field in table.fields],
                    is_value_string=True,
                )
                exports.append(mapping_name)

            # Views
            view_names: list[str] = deduplicate_names([sanitize_string(view.name) for view in table.views])
            view_ids: list[str] = [view.id for view in table.views]

            write.const_array(f"{table.name_pascal()}Views", view_names, f"View names for `{table.name}`")
            exports.append(f"{table.name_pascal()}Views")

            write.const_array(f"{table.name_pascal()}ViewIds", view_ids, f"View IDs for `{table.name}`")
            exports.append(f"{table.name_pascal()}ViewIds")

            write.const_object(
                f"{table.name_pascal()}ViewNameIdMapping",
                list(zip(view_names, view_ids)),
                is_value_string=True,
            )
            exports.append(f"{table.name_pascal()}ViewNameIdMapping")

            write.const_object(
                f"{table.name_pascal()}ViewIdNameMapping",
                list(zip(view_ids, view_names)),
                is_value_string=True,
            )
            exports.append(f"{table.name_pascal()}ViewIdNameMapping")

            write.endregion()

            # Module exports
            write.module_exports(exports)

    # Write global tables file
    with WriteToJavaScriptFile(path=types_dir / "_tables.js") as write:
        # Require field name ID mappings from individual table files
        write.region("REQUIRES")
        for table in base.tables:
            write.require_statement([f"{table.name_pascal()}FieldNameIdMapping"], f"./{table.name_camel()}")
        write.endregion()
        write.line_empty()

        # Table Lists
        table_names = [table.name for table in base.tables]
        table_ids = [table.id for table in base.tables]

        exports = []
        write.region("TABLES")
        write.const_array("TableNames", table_names)
        exports.append("TableNames")

        write.const_array("TableIds", table_ids)
        exports.append("TableIds")

        write.const_object(
            "TableNameIdMapping",
            [(table.name, table.id) for table in base.tables],
            is_value_string=True,
        )
        exports.append("TableNameIdMapping")

        write.const_object(
            "TableIdNameMapping",
            [(table.id, table.name) for table in base.tables],
            is_value_string=True,
        )
        exports.append("TableIdNameMapping")

        write.const_object(
            "TableIdToFieldNameIdMapping",
            [(table.id, f"{table.name_pascal()}FieldNameIdMapping") for table in base.tables],
            is_value_string=False,
        )
        exports.append("TableIdToFieldNameIdMapping")

        write.const_object(
            "TableNamePropertyMapping",
            [(table.name, table.name_camel()) for table in base.tables],
            is_value_string=True,
        )
        exports.append("TableNamePropertyMapping")
        write.endregion()

        write.module_exports(exports)

    # Write barrel export index.js
    write_barrel_export(base, types_dir, extra_exports=["...require('./_tables'),"])


# endregion

# region ZOD


def write_zod_schemas(base: Base, output_folder: Path) -> None:
    zod_dir = create_dynamic_subdir(output_folder, Paths.ZOD)

    for table in base.tables:
        with WriteToJavaScriptFile(path=zod_dir / f"{table.name_camel()}.js") as write:
            write.line('const z = require("zod");')
            write.mark_imports()
            write.add_import("../../static/special-types", ["recordIdSchema"], always=True)
            write.add_import(
                "../../static/special-types",
                ["AirtableAttachmentSchema", "AirtableCollaboratorSchema", "AirtableButtonSchema", "SpecialNumberSchema", "ErrorValueSchema"],
            )

            # Register select option constants from types (resolved against usage)
            if len(table.select_fields()) > 0:
                names = [f"{field.options_name()}s" for field in table.select_fields()]
                write.add_import(f"../types/{table.name_camel()}", list(names))
            write.line_empty()

            write.region(table.name_upper())
            write.line(f"const {table.name_pascal()}Schema = z.object({{")
            write.line_indented("id: recordIdSchema.optional(),")
            for field in table.fields:
                write.line_indented(f"{field.name_camel()}: {field.zod_type()},")
            write.line("});")
            write.line_empty()
            write.endregion()

            write.module_exports([f"{table.name_pascal()}Schema"])

    write_barrel_export(base, zod_dir)


# endregion


# region MODELS
def write_models(base: Base, output_folder: Path, formulas: bool = True, runtime: bool = True, flatten: bool = False, zod: bool = True) -> None:
    models_dir = create_dynamic_subdir(output_folder, Paths.MODELS)

    # Write individual table model files
    for table in base.tables:
        with WriteToJavaScriptFile(path=models_dir / f"{table.name_camel()}.js") as write:
            # Requires (registered as candidates; only symbols used in the body are emitted)
            write.region("REQUIRES")
            write.mark_imports()
            write.add_import("../../static/airtable-model", ["AirtableModel"], always=True)
            write.add_import("../../static/linked-record", ["LinkedRecord", "LinkedRecords", "wrapLinkedRecordProxy"])
            write.add_import("../../static/helpers", ["getOptions", "getBaseId", "buildUrl"])

            # Require field mappings + select options from types
            type_imports: list[str | tuple[str, str]] = [
                f"{table.name_pascal()}FieldNameIdMapping",
                f"{table.name_pascal()}FieldIdNameMapping",
                f"{table.name_pascal()}FieldNamePropertyMapping",
                f"{table.name_pascal()}ViewNameIdMapping",
            ]
            for field in table.select_fields():
                type_imports.append(f"{field.options_name()}s")
            write.add_import(f"../types/{table.name_camel()}", type_imports)

            if formulas:
                write.add_import(f"../formulas/{table.name_camel()}", [f"{table.name_pascal()}Formulas"])
            if len(table.select_fields()) > 0:
                write.add_import(f"../options/{table.name_camel()}", [f"{table.name_pascal()}Options"])

            # Note: Other models are loaded lazily to avoid circular dependencies

            # Require table class for this table
            write.add_import(f"../tables/{table.name_camel()}", [f"{table.name_pascal()}Table"])
            if zod:
                write.add_import(f"../zod/{table.name_camel()}", [f"{table.name_pascal()}Schema"])

            # Register the formula runtime require unconditionally; resolve_imports drops it when no
            # transpiled formula references `F`.
            write.add_import("../../static/airtable-runtime", [("AirtableRuntime: F", "F")])

            # Pre-transpile formula fields
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
                    raw_formulas, "javascript", field_name_map, formula_field_ids, linked_record_field_ids, single_linked_record_field_ids
                )
            else:
                transpiled_formulas = {}
            write.endregion()
            write.line_empty()

            # Table Model
            write.region(table.name_upper())

            write.docstring(f"Model for `{table.name}` ({table.id})", 0)
            write.line(f"class {table.name_model()} extends AirtableModel {{")
            if zod:
                write.line_indented(f"static schema = {table.name_pascal()}Schema;")
            if formulas:
                write.line_indented(f"static f = {table.name_pascal()}Formulas;")
            if len(table.select_fields()) > 0:
                write.line_indented(f"static o = {table.name_pascal()}Options;")
            write.line_indented(f"static nameToIdMap = {table.name_pascal()}FieldNameIdMapping;")
            write.line_indented(f"static idToNameMap = {table.name_pascal()}FieldIdNameMapping;")
            write.line_indented(f"static nameToPropertyMap = {table.name_pascal()}FieldNamePropertyMapping;")
            write.docstring(f"Table name ({table.name})", 1)
            write.line_indented(f"static tableName = '{table.name}';", 1)
            write.docstring(f"Table name ({table.name})", 1)
            write.line_indented(f"get tableName() {{ return {table.name_model()}.tableName; }}", 1)
            write.line_empty()
            write.docstring(f"Table ID ({table.id})", 1)
            write.line_indented(f"static tableId = '{table.id}';", 1)
            write.docstring(f"Table ID ({table.id})", 1)
            write.line_indented(f"get tableId() {{ return {table.name_model()}.tableId; }}", 1)
            write.line_empty()

            # Field descriptors
            write.line_indented("static fieldDescriptors = [", 1)
            for field in table.fields:
                field_name = field.name_camel()
                field_type = field.typescript_type()
                is_computed = "true" if field.is_computed() else "false"
                if (field_type == "RecordId" or field_type == "RecordId[]") and not field.is_computed():
                    linked_record_type = field.get_linked_model_name()
                    linked_table_id = field.options.linked_table_id if field.options else None
                    linked_table = base.table_by_id(linked_table_id) if linked_table_id else None
                    linked_file = linked_table.name_camel() if linked_table else ""
                    field_kind = "linkedRecord" if field_type == "RecordId" else "linkedRecords"
                    write.line_indented(
                        f'{{ propertyName: "{field_name}", fieldId: "{field.id}", fieldName: "{sanitize_string(field.name)}", isComputed: {is_computed}, fieldType: "{field_kind}", linkedModelFromId: (id, config) => require("./{linked_file}").{linked_record_type}.fromId(id, config), linkedModelClass: require("./{linked_file}").{linked_record_type} }},',
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

            # Field properties with JSDoc
            for field in table.fields:
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

                if field.is_formula() and runtime:
                    # Formula field -> computed property that checks evaluateFormulasAtRuntime
                    write.docstring(docstring)
                    write.line_indented(f"get {field.name_camel()}() {{")
                    if field.id in transpiled_formulas:
                        formula_code = transpiled_formulas[field.id]
                        write.line_indented(f'if (this.evaluateFormulasAtRuntime) this._fields["{field.name_camel()}"] = {formula_code};', 2)
                    write.line_indented(f'return this._fields["{field.name_camel()}"];', 2)
                    write.line_indented("}")
                else:
                    field_type = field.typescript_type()
                    write.docstring(docstring)
                    write.line_indented(f'get {field.name_camel()}() {{ return this._fields["{field.name_camel()}"]; }}')
                    if not field.is_computed():
                        if field_type == "RecordId" and not field.is_computed():
                            write.line_indented(f"set {field.name_camel()}(value) {{ this._setLinkedField('{field.name_camel()}', value); }}")
                        elif field_type == "RecordId[]" and not field.is_computed():
                            write.line_indented(f"set {field.name_camel()}(value) {{ this._setLinkedRecordsField('{field.name_camel()}', value); }}")
                        else:
                            write.line_indented(
                                f"set {field.name_camel()}(value) {{ this._fields[\"{field.name_camel()}\"] = value; this.markDirty('{field.name_camel()}'); }}"
                            )
            write.line_empty()

            # Constructor
            write.line_indented("constructor(data = {}) {")
            write.line_indented("super(data.id ?? '');", 2)
            write.line_indented("this.initializeFields(data);", 2)
            write.line_indented(
                f"this.record = new (require('airtable').Record)(new {table.name_pascal()}Table(this.getInstanceBaseId(), this.getInstanceOptions())._table, this.id, {{}});",
                2,
            )
            write.line_indented("this.updateRecord();", 2)
            write.line_indented("}")
            write.line_empty()

            # url
            has_field_called_url: bool = any(field.name_camel() == "url" for field in table.fields)
            url_method_name: str = "URL" if has_field_called_url else "url"
            write.docstring("Get the URL for this record in Airtable, with optional view.")
            write.line_indented(f"{url_method_name}(view) {{")
            write.line_indented("if (view) {", 2)
            write.line_indented(f"return buildUrl(this.getInstanceBaseId(), '{table.id}', this.id, {table.name_pascal()}ViewNameIdMapping[view]);", 3)
            write.line_indented("} else {", 2)
            write.line_indented(f"return buildUrl(this.getInstanceBaseId(), '{table.id}', this.id);", 3)
            write.line_indented("}", 2)
            write.line_indented("}")
            write.line_empty()

            write.line("}")
            write.endregion()

            write.module_exports([table.name_model()])

    # Write barrel export index.js
    write_barrel_export(base, models_dir)


# endregion


# region TABLES
def write_tables(base: Base, output_folder: Path) -> None:
    tables_dir = create_dynamic_subdir(output_folder, Paths.TABLES)

    for table in base.tables:
        with WriteToJavaScriptFile(path=tables_dir / f"{table.name_camel()}.js") as write:
            # Requires
            write.region("REQUIRES")
            write.mark_imports()
            write.add_import("../../static/airtable-table", ["AirtableTable"])
            write.add_import(
                f"../types/{table.name_camel()}",
                [
                    f"{table.name_pascal()}ViewNameIdMapping",
                    f"{table.name_pascal()}FieldNameIdMapping",
                    f"{table.name_pascal()}FieldIdNameMapping",
                    f"{table.name_pascal()}WritableFieldIds",
                ],
            )
            # Note: Model is loaded lazily to avoid circular dependencies
            write.endregion()
            write.line_empty()

            write.line(f"class {table.name_pascal()}Table extends AirtableTable {{")
            write.docstring(f"Table name ({table.name})")
            write.line_indented(f'static tableName = "{table.name}";')
            write.docstring(f"Table name ({table.name})")
            write.line_indented(f"get tableName() {{ return {table.name_pascal()}Table.tableName; }}")
            write.line_empty()
            write.docstring(f"Table ID ({table.id})")
            write.line_indented(f'static tableId = "{table.id}";')
            write.docstring(f"Table ID ({table.id})")
            write.line_indented(f"get tableId() {{ return {table.name_pascal()}Table.tableId; }}")
            write.line_empty()
            write.line_indented("constructor(baseId, options) {")
            write.line_indented(
                f'super(baseId, "{table.id}", {table.name_pascal()}ViewNameIdMapping, {table.name_pascal()}FieldNameIdMapping, {table.name_pascal()}FieldIdNameMapping, {table.name_pascal()}WritableFieldIds, (record) => require("../models/{table.name_camel()}").{table.name_model()}.fromRecord(record, {{ baseId: this.baseId, ...this._options }}, false), options);',
                2,
            )
            write.line_indented("}")
            write.line("}")
            write.line_empty()

            write.module_exports([f"{table.name_pascal()}Table"])

    # Write barrel export index.js
    write_barrel_export(base, tables_dir)


# endregion


# region FORMULA
def write_formula_helpers(base: Base, output_folder: Path) -> None:
    formulas_dir = create_dynamic_subdir(output_folder, Paths.FORMULAS)

    for table in base.tables:
        with WriteToJavaScriptFile(path=formulas_dir / f"{table.name_camel()}.js") as write:
            # Requires (only the formula classes actually instantiated are emitted)
            write.mark_imports()
            write.add_import(
                "../../static/formula",
                [
                    "ID",
                    "AttachmentsField",
                    "BooleanField",
                    "DateField",
                    "LookupField",
                    "NumberField",
                    "TextField",
                    "SingleSelectField",
                    "MultiSelectField",
                ],
            )
            write.select_options_require(table, f"../types/{table.name_camel()}")
            write.line_empty()

            # Properties as object (instead of TypeScript namespace)
            write.line(f"const {table.name_pascal()}Formulas = {{")
            write.line_indented("id: new ID(),")
            for field in table.fields:
                property_name = field.name_camel()
                formula_class = field.formula_class()
                write.line_indented(f"{property_name}: new {formula_class}('{field.id}'),")
            write.line("};")
            write.line_empty()

            write.module_exports([f"{table.name_pascal()}Formulas"])

    # Write barrel export index.js
    write_barrel_export(base, formulas_dir)


def write_options(base: Base, output_folder: Path) -> None:
    options_dir = create_dynamic_subdir(output_folder, Paths.OPTIONS)

    for table in base.tables:
        select_fields = table.select_fields()
        with WriteToJavaScriptFile(path=options_dir / f"{table.name_camel()}.js") as write:
            if len(select_fields) > 0:
                # Register the const arrays from types (resolved against usage)
                write.mark_imports()
                option_names = [f"{field.options_name()}s" for field in select_fields]
                write.add_import(f"../types/{table.name_camel()}", list(option_names))
                write.line_empty()

            # Object with property per select field
            write.line(f"const {table.name_pascal()}Options = {{")
            for field in select_fields:
                write.line_indented(f"{field.name_camel()}: {field.options_name()}s,")
            write.line("};")
            write.line_empty()

            write.module_exports([f"{table.name_pascal()}Options"])

    # Write barrel export index.js
    write_barrel_export(base, options_dir)


# endregion


# region MAIN CLASS
def write_main_class(base: Base, output_folder: Path) -> None:
    with WriteToJavaScriptFile(path=output_folder / Paths.DYNAMIC / "airtable-main.js") as write:
        # Requires
        write.mark_imports()
        write.add_import("../static/helpers", ["getApiKey", "getBaseId", "setAirtableConfig", "buildUrl"])
        table_classes = [f"{table.name_pascal()}Table" for table in base.tables]
        write.add_import("./tables", list(table_classes))
        write.add_import("./types", ["TableNamePropertyMapping"])
        write.line_empty()

        write.docstring("Airtable base wrapper", 0)
        write.line("class Airtable {")
        schema_json = json.dumps(base.to_dict())
        write.line_indented("baseId;")
        write.line_indented(f"static schema = {schema_json};")
        write.line_empty()
        for table in base.tables:
            write.docstring(f"`{table.name}` ({table.id})", 1)
            write.line_indented(f"{table.name_camel()};")
        write.line_empty()
        # Constructor
        write.line_indented("constructor(options = {}) {")
        write.line_indented("this.baseId = options.baseId || getBaseId();", 2)
        write.line_indented("const _options = {", 2)
        write.line_indented("apiKey: options.apiKey ?? getApiKey(),", 3)
        write.line_indented("apiVersion: options.apiVersion,", 3)
        write.line_indented("customHeaders: options.customHeaders,", 3)
        write.line_indented("endpointUrl: options.endpointUrl,", 3)
        write.line_indented("noRetryIfRateLimited: options.noRetryIfRateLimited ?? false,", 3)
        write.line_indented("requestTimeout: options.requestTimeout,", 3)
        write.line_indented("cacheSeconds: options.cacheSeconds,", 3)
        write.line_indented("};", 2)
        write.line_indented("setAirtableConfig(this.baseId, _options);", 2)
        for table in base.tables:
            write.line_indented(f"this.{table.name_camel()} = new {table.name_pascal()}Table(this.baseId, _options);", 2)
        write.line_indented("}")
        write.line_empty()
        write.docstring("Get a table by its Airtable name.", 1)
        write.line_indented("table(tableName) {")
        write.line_indented("return this[TableNamePropertyMapping[tableName]];", 2)
        write.line_indented("}")
        write.line_empty()
        write.docstring("Get the URL for the Airtable base.", 1)
        write.line_indented("url() {")
        write.line_indented("return buildUrl(this.baseId);", 2)
        write.line_indented("}")
        write.line_empty()
        write.docstring("Fetch a live version of the schema from Airtable's metadata API.", 1)
        write.line_indented("async getSchema() {")
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
        write.line_indented("invalidateCache() {")
        for table in base.tables:
            write.line_indented(f"this.{table.name_camel()}.invalidateCache();", 2)
        write.line_indented("}")
        write.line("}")
        write.line_empty()

        write.module_exports(["Airtable"])


# endregion


# region INDEX
def write_index(output_folder: Path, formulas: bool = True, wrappers: bool = True) -> None:
    with WriteToJavaScriptFile(path=output_folder / Paths.DYNAMIC / "index.js") as write:
        write.line("module.exports = {")
        if wrappers:
            write.line_indented('...require("./airtable-main"),')
            write.line_indented('...require("./tables"),')
            write.line_indented('...require("./models"),')
        write.line_indented('...require("./types"),')
        if formulas:
            write.line_indented('...require("./formulas"),')
        write.line_indented('...require("./options"),')
        write.line("};")
        write.line("")

    with WriteToJavaScriptFile(path=output_folder / "index.js") as write:
        write.line("module.exports = {")
        write.line_indented('...require("./dynamic"),')
        if formulas:
            write.line_indented('...require("./static/formula"),')
        if wrappers:
            write.line_indented('...require("./static/airtable-model"),')
        write.line_indented('...require("./static/errors"),')
        write.line("};")
        write.line("")


# endregion

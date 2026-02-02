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
            self.line_indented(f'"{item}",')
        self.line("];")
        self.line_empty()

    def const_object(self, name: str, pairs: list[tuple[str, str]], is_value_string: bool = True, docstring: str = ""):
        """Generate a const object: const Name = { key: "value" };"""
        if docstring:
            self.docstring(docstring, indent=0)
        self.line(f"const {name} = {{")
        for k, v in pairs:
            if is_value_string:
                self.line_indented(f'"{k}": "{v}",')
            else:
                self.line_indented(f'"{k}": {v},')
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
        """Require select field option arrays if the table has any select fields. Returns list of imported names."""
        names: list[str] = []
        if len(table.select_fields()) > 0:
            for field in table.select_fields():
                names.append(f"{field.options_name()}s")
            self.require_statement(names, from_path)
        return names


# region MAIN
def generate_javascript(base: Base, output_folder: Path, formulas: bool = True, wrappers: bool = True, zod: bool = True) -> None:
    print("Generating JavaScript code")
    for table in base.tables:
        table.detect_duplicate_property_names()

    reset_folder(output_folder / Paths.DYNAMIC)
    reset_folder(output_folder / Paths.STATIC)

    with timer.timer("JavaScript: copy_static_files"):
        copy_static_files(output_folder, "javascript")
        if verbose:
            print("[dim] - JavaScript static files copied.[/]")

    with timer.timer("JavaScript: write_types"):
        write_types(base, output_folder)
        if verbose:
            print("[dim] - JavaScript types generated.[/]")

    if formulas:
        with timer.timer("JavaScript: write_formula_helpers"):
            write_formula_helpers(base, output_folder)
            if verbose:
                print("[dim] - JavaScript formula helpers generated.[/]")

    if zod:
        with timer.timer("JavaScript: write_zod_schemas"):
            write_zod_schemas(base, output_folder)
            if verbose:
                print("[dim] - JavaScript Zod schemas generated.[/]")

    if wrappers:
        with timer.timer("JavaScript: write_models"):
            write_models(base, output_folder, formulas=formulas, zod=zod)
            if verbose:
                print("[dim] - JavaScript models generated.[/]")

        with timer.timer("JavaScript: write_tables"):
            write_tables(base, output_folder)
            if verbose:
                print("[dim] - JavaScript tables generated.[/]")

        with timer.timer("JavaScript: write_main_class"):
            write_main_class(base, output_folder)
            if verbose:
                print("[dim] - JavaScript main class generated.[/]")

    with timer.timer("JavaScript: write_index"):
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
            view_names: list[str] = [sanitize_string(view.name) for view in table.views]
            view_ids: list[str] = [view.id for view in table.views]

            write.const_array(f"{table.name_pascal()}Views", view_names, f"View names for `{table.name}`")
            exports.append(f"{table.name_pascal()}Views")

            write.const_array(f"{table.name_pascal()}ViewIds", view_ids, f"View IDs for `{table.name}`")
            exports.append(f"{table.name_pascal()}ViewIds")

            write.const_object(
                f"{table.name_pascal()}ViewNameIdMapping",
                [(sanitize_string(view.name), view.id) for view in table.views],
                is_value_string=True,
            )
            exports.append(f"{table.name_pascal()}ViewNameIdMapping")

            write.const_object(
                f"{table.name_pascal()}ViewIdNameMapping",
                [(view.id, sanitize_string(view.name)) for view in table.views],
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
            write.require_statement(
                [
                    "recordIdSchema",
                    "AirtableAttachmentSchema",
                    "AirtableCollaboratorSchema",
                    "AirtableButtonSchema",
                    "SpecialNumberSchema",
                    "ErrorValueSchema",
                ],
                "../../static/special-types",
            )

            # Require select option constants from types
            if len(table.select_fields()) > 0:
                names = [f"{field.options_name()}s" for field in table.select_fields()]
                write.require_statement(names, f"../types/{table.name_camel()}")
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
def write_models(base: Base, output_folder: Path, formulas: bool = True, zod: bool = True) -> None:
    models_dir = create_dynamic_subdir(output_folder, Paths.MODELS)

    # Write individual table model files
    for table in base.tables:
        with WriteToJavaScriptFile(path=models_dir / f"{table.name_camel()}.js") as write:
            # Requires
            write.region("REQUIRES")
            write.require_statement(["AirtableModel"], "../../static/airtable-model")
            write.require_statement(["LinkedRecord", "LinkedRecords"], "../../static/linked-record")
            write.require_statement(["getOptions", "getBaseId"], "../../static/helpers")

            # Require field mappings from types
            write.require_statement(
                [
                    f"{table.name_pascal()}FieldNameIdMapping",
                    f"{table.name_pascal()}FieldIdNameMapping",
                    f"{table.name_pascal()}FieldNamePropertyMapping",
                ],
                f"../types/{table.name_camel()}",
            )

            # Require select options from types
            select_fields = table.select_fields()
            if len(select_fields) > 0:
                type_imports = [f"{field.options_name()}s" for field in select_fields]
                write.require_statement(type_imports, f"../types/{table.name_camel()}")

            if formulas:
                write.require_statement([f"{table.name_pascal()}Formulas"], f"../formulas/{table.name_camel()}")

            # Note: Other models are loaded lazily to avoid circular dependencies

            # Require table class for this table
            write.require_statement([f"{table.name_pascal()}Table"], f"../tables/{table.name_camel()}")
            if zod:
                write.require_statement([f"{table.name_pascal()}Schema"], f"../zod/{table.name_camel()}")
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
                        f'{{ propertyName: "{field_name}", fieldId: "{field.id}", fieldName: "{sanitize_string(field.name)}", isComputed: {is_computed}, fieldType: "{field_kind}", linkedModelFromId: (id, config) => require("./{linked_file}").{linked_record_type}.fromId(id, config) }},',
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

                write.docstring(docstring)
                write.line_indented(f'get {field.name_camel()}() {{ return this._fields["{field.name_camel()}"]; }}')
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
            write.require_statement(["AirtableTable"], "../../static/airtable-table")
            write.require_statement(
                [
                    f"{table.name_pascal()}ViewNameIdMapping",
                    f"{table.name_pascal()}FieldNameIdMapping",
                    f"{table.name_pascal()}FieldIdNameMapping",
                    f"{table.name_pascal()}WritableFieldIds",
                ],
                f"../types/{table.name_camel()}",
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
                f'super(baseId, "{table.id}", {table.name_pascal()}ViewNameIdMapping, {table.name_pascal()}FieldNameIdMapping, {table.name_pascal()}FieldIdNameMapping, {table.name_pascal()}WritableFieldIds, (record) => require("../models/{table.name_camel()}").{table.name_model()}.fromRecord(record, {{ baseId: this.baseId, ...this._options }}), options);',
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
            # Requires
            write.require_statement(
                ["ID", "AttachmentsField", "BooleanField", "DateField", "NumberField", "TextField", "SingleSelectField", "MultiSelectField"],
                "../../static/formula",
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


# endregion


# region MAIN CLASS
def write_main_class(base: Base, output_folder: Path) -> None:
    with WriteToJavaScriptFile(path=output_folder / Paths.DYNAMIC / "airtable-main.js") as write:
        # Requires
        write.require_statement(["getApiKey", "getBaseId", "setAirtableConfig"], "../static/helpers")
        table_classes = [f"{table.name_pascal()}Table" for table in base.tables]
        write.require_statement(table_classes, "./tables")
        write.require_statement(["TableNamePropertyMapping"], "./types")
        write.line_empty()

        write.docstring("Airtable base wrapper", 0)
        write.line("class Airtable {")
        for table in base.tables:
            write.docstring(f"`{table.name}` ({table.id})", 1)
            write.line_indented(f"{table.name_camel()};")
        write.line_empty()
        # Constructor
        write.line_indented("constructor(options = {}) {")
        write.line_indented("const _baseId = options.baseId || getBaseId();", 2)
        write.line_indented("const _options = {", 2)
        write.line_indented("apiKey: options.apiKey ?? getApiKey(),", 3)
        write.line_indented("apiVersion: options.apiVersion,", 3)
        write.line_indented("customHeaders: options.customHeaders,", 3)
        write.line_indented("endpointUrl: options.endpointUrl,", 3)
        write.line_indented("noRetryIfRateLimited: options.noRetryIfRateLimited ?? false,", 3)
        write.line_indented("requestTimeout: options.requestTimeout,", 3)
        write.line_indented("};", 2)
        write.line_indented("setAirtableConfig(_baseId, _options);", 2)
        for table in base.tables:
            write.line_indented(f"this.{table.name_camel()} = new {table.name_pascal()}Table(_baseId, _options);", 2)
        write.line_indented("}")
        write.line_empty()
        write.docstring("Get a table by its Airtable name.", 1)
        write.line_indented("table(tableName) {")
        write.line_indented("return this[TableNamePropertyMapping[tableName]];", 2)
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
        write.line("};")
        write.line("")

    with WriteToJavaScriptFile(path=output_folder / "index.js") as write:
        write.line("module.exports = {")
        write.line_indented('...require("./dynamic"),')
        if formulas:
            write.line_indented('...require("./static/formula"),')
        if wrappers:
            write.line_indented('...require("./static/airtable-model"),')
        write.line("};")
        write.line("")


# endregion

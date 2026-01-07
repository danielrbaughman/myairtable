from pathlib import Path

from rich import print

from .helpers import (
    Paths,
    copy_static_files,
    create_dynamic_subdir,
    reset_folder,
    sanitize_string,
)
from .meta import Base, Field, FieldType, Table
from .write_to_file import WriteToFile


class WriteToPythonFile(WriteToFile):
    def __init__(self, path: Path):
        super().__init__(path=path, language="python")

    def types(self, name: str, list: list[str], docstring: str = ""):
        literal_name = f"{name}"
        self.literal(literal_name, list)
        if docstring:
            self.line(f'"""{docstring}"""')
        self.str_list(f"{name}s", list, type=literal_name)
        if docstring:
            self.line(f'"""{docstring}"""')
        self.line_empty()

    def property_docstring(self, field: Field, table: Table):
        if field.id == table.primary_field_id:
            if field.is_computed():
                self.line_indented(f'"""{sanitize_string(field.name)} `{field.id}` - `Primary Key` - `Read-Only Field`"""')
            else:
                self.line_indented(f'"""{sanitize_string(field.name)} `{field.id}` - `Primary Key`"""')
        elif field.is_computed():
            self.line_indented(f'"""{sanitize_string(field.name)} `{field.id}` - `Read-Only Field`"""')
        else:
            self.line_indented(f'"""{sanitize_string(field.name)} `{field.id}`"""')

    def dict_class(self, name: str, pairs: list[tuple[str, str]], first_type: str = "str", second_type: str = "str", value_is_string: bool = True):
        self.line(f"{name}: dict[{first_type}, {second_type}] = {{")
        for k, v in pairs:
            self.dict_row(k, v, value_is_string=value_is_string)
        self.line("}")
        self.line_empty()

    def literal(self, name: str, list: list[str]):
        self.line(f"{name} = Literal[")
        for item in list:
            self.line_indented(f'"{item}",')
        self.line("]")

    def str_list(self, name: str, list: list[str], type: str = "str"):
        self.line(f"{name}: list[{type}] = [")
        for item in list:
            self.line_indented(f'"{item}",')
        self.line("]")

    def dict_row(self, key: str, value: str, value_is_string: bool = True):
        if value_is_string:
            self.line_indented(f'"{key}": "{value}",')
        else:
            self.line_indented(f'"{key}": {value},')

    def property_row(self, name: str, type: str):
        self.line_indented(f"{name}: {type}")

    def region(self, text: str):
        self.lines.append(f"# region {text}")

    def endregion(self):
        self.lines.append("# endregion")
        self.line_empty()

    def multiline_import(self, module: str, items: list[str]) -> None:
        """Write a multi-line import statement."""
        self.line(f"from {module} import (")
        for item in items:
            self.line_indented(f"{item},")
        self.line(")")

    def select_options_import(self, table: Table) -> None:
        """Import select field option types if the table has any select fields."""
        select_fields = table.select_fields()
        if len(select_fields) > 0:
            self.multiline_import("..types", [field.options_name() for field in select_fields])


# region MAIN
def generate_python(base: Base, output_folder: Path, formulas: bool, wrappers: bool, package_prefix: str) -> None:
    print("Generating Python code")
    for table in base.tables:
        table.detect_duplicate_property_names()

    reset_folder(output_folder / Paths.DYNAMIC)
    reset_folder(output_folder / Paths.STATIC)

    copy_static_files(output_folder, "python")
    print("[dim] - Python static files copied.[/]")
    write_types(base, output_folder)
    print("[dim] - Python types generated.[/]")
    write_dicts(base, output_folder)
    print("[dim] - Python dicts generated.[/]")
    write_models(base, output_folder, formulas=formulas, package_prefix=package_prefix)
    print("[dim] - Python models generated.[/]")
    if formulas:
        write_formula_helpers(base, output_folder)
        print("[dim] - Python formula helpers generated.[/]")
    if wrappers:
        write_tables(base, output_folder)
        print("[dim] - Python tables generated.[/]")
        write_main_class(base, output_folder)
        print("[dim] - Python main class generated.[/]")
    write_init(output_folder, formulas, wrappers)
    print("[green] - Python code generation complete.[/]")
    print("")


def write_module_init(base: Base, output_folder: Path, subdir: str, extra_imports: list[str] | None = None) -> None:
    """Generate __init__.py that re-exports all table modules."""
    with WriteToPythonFile(path=output_folder / Paths.DYNAMIC / subdir / "__init__.py") as write:
        if extra_imports:
            for line in extra_imports:
                write.line(line)
        for table in base.tables:
            write.line(f"from .{table.name_snake()} import *  # noqa: F403")


# endregion


# region TYPES
def write_types(base: Base, output_folder: Path) -> None:
    types_dir = create_dynamic_subdir(output_folder, Paths.TYPES)

    # Table Types
    for table in base.tables:
        with WriteToPythonFile(path=types_dir / f"{table.name_snake()}.py") as write:
            # Imports
            write.region("IMPORTS")
            write.line("from datetime import datetime, timedelta")
            write.line("from typing import Any, Literal, TypedDict")
            write.line_empty()
            write.line("from ...static.special_types import AirtableAttachment, AirtableButton, AirtableCollaborator, RecordId")
            write.endregion()
            write.line_empty()

            write.region("OPTIONS")
            for field in table.fields:
                options = field.select_options()
                if len(options) > 0:
                    write.types(
                        field.options_name(),
                        options,
                        f"Select options for `{sanitize_string(field.name)}`",
                    )
            write.endregion()

            field_names = [sanitize_string(field.name) for field in table.fields]
            field_ids = [field.id for field in table.fields]
            property_names = [field.name_snake() for field in table.fields]

            write.region(table.name_upper())

            write.types(f"{table.name_pascal()}Field", field_names, f"Field names for `{table.name}`")
            write.types(f"{table.name_pascal()}FieldId", field_ids, f"Field IDs for `{table.name}`")
            write.types(f"{table.name_pascal()}FieldProperty", property_names, f"Property names for `{table.name}`")

            write.str_list(
                f"{table.name_pascal()}CalculatedFields",
                [sanitize_string(field.name) for field in table.fields if field.is_computed()],
            )
            write.line(f'"""Calculated fields for `{table.name}`"""')
            write.str_list(
                f"{table.name_pascal()}CalculatedFieldIds",
                [field.id for field in table.fields if field.is_computed()],
            )
            write.line(f'"""Calculated fields for `{table.name}`"""')
            write.line_empty()

            field_mappings: list[tuple[str, str, str, str, str]] = [
                ("FieldNameIdMapping", "name_sanitized", "id", "Field", "FieldId"),
                ("FieldIdNameMapping", "id", "name_sanitized", "FieldId", "Field"),
                ("FieldIdPropertyMapping", "id", "name_snake", "FieldId", "FieldProperty"),
                ("FieldPropertyIdMapping", "name_snake", "id", "FieldProperty", "FieldId"),
                ("FieldNamePropertyMapping", "name", "name_snake", "Field", "FieldProperty"),
                ("FieldPropertyNameMapping", "name_snake", "name", "FieldProperty", "Field"),
            ]

            def _get(field: Field, getter: str) -> str:
                """Get a field value based on the getter name."""
                if getter == "id":
                    return field.id
                elif getter == "name":
                    return field.name
                elif getter == "name_snake":
                    return field.name_snake()
                elif getter == "name_sanitized":
                    return sanitize_string(field.name)
                raise ValueError(f"Unknown getter: {getter}")

            for suffix, get_1, get_2, type_1, type_2 in field_mappings:
                write.dict_class(
                    f"{table.name_pascal()}{suffix}",
                    [(_get(field, get_1), _get(field, get_2)) for field in table.fields],
                    first_type=f"{table.name_pascal()}{type_1}",
                    second_type=f"{table.name_pascal()}{type_2}",
                )

            write.line(f"class {table.name_pascal()}FieldsDict(TypedDict, total=False):")
            for field in table.fields:
                write.property_row(field.id, python_type(field))
            write.line_empty()
            write.line_empty()

            views = table.views
            view_names: list[str] = [sanitize_string(view.name) for view in views]
            view_ids: list[str] = [view.id for view in views]
            write.types(f"{table.name_pascal()}View", view_names, f"View names for `{table.name}`")
            write.types(f"{table.name_pascal()}ViewId", view_ids, f"View IDs for `{table.name}`")
            write.dict_class(
                f"{table.name_pascal()}ViewNameIdMapping",
                [(sanitize_string(view.name), view.id) for view in table.views],
                first_type=f"{table.name_pascal()}View",
                second_type=f"{table.name_pascal()}ViewId",
            )
            write.dict_class(
                f"{table.name_pascal()}ViewIdNameMapping",
                [(view.id, sanitize_string(view.name)) for view in table.views],
                first_type=f"{table.name_pascal()}ViewId",
                second_type=f"{table.name_pascal()}View",
            )

            write.endregion()

    with WriteToPythonFile(path=types_dir / "_tables.py") as write:
        write.line("from typing import Literal")
        for table in base.tables:
            snake = table.name_snake()
            pascal = table.name_pascal()
            write.line(f"from .{snake} import {pascal}Field, {pascal}Fields, {pascal}FieldNameIdMapping")
        write.line_empty()

        # Table Lists
        table_names = []
        table_ids = []
        for table in base.tables:
            table_names.append(table.name)
            table_ids.append(table.id)

        write.types("TableName", table_names)
        write.types("TableId", table_ids)
        write.dict_class(
            "TableNameIdMapping",
            [(table.name, table.id) for table in base.tables],
            first_type="TableName",
            second_type="TableId",
        )
        write.dict_class(
            "TableIdNameMapping",
            [(table.id, table.name) for table in base.tables],
            first_type="TableId",
            second_type="TableName",
        )
        write.dict_class(
            "TableIdToFieldNameIdMapping",
            [(table.id, f"{table.name_pascal()}FieldNameIdMapping") for table in base.tables],
            first_type="TableId",
            second_type="dict[str, str]",
            value_is_string=False,
        )
        write.dict_class(
            "TableIdToFieldNamesTypeMapping",
            [(table.id, f"{table.name_pascal()}Field") for table in base.tables],
            first_type="TableId",
            second_type="str",
            value_is_string=False,
        )
        write.dict_class(
            "TableIdToFieldNamesListMapping",
            [(table.id, f"{table.name_pascal()}Fields") for table in base.tables],
            first_type="TableId",
            second_type="list[str]",
            value_is_string=False,
        )
        write.dict_class(
            "TableIdToFieldNameToFieldIdMapping",
            [(table.id, f"{table.name_pascal()}FieldNameIdMapping") for table in base.tables],
            first_type="TableId",
            second_type="dict[str, str]",
            value_is_string=False,
        )

    write_module_init(base, output_folder, Paths.TYPES, extra_imports=["from ._tables import *  # noqa: F403"])


# endregion


# region DICTS
def write_dicts(base: Base, output_folder: Path) -> None:
    dicts_dir = create_dynamic_subdir(output_folder, Paths.DICTS)

    for table in base.tables:
        with WriteToPythonFile(path=dicts_dir / f"{table.name_snake()}.py") as write:
            # Imports
            write.line("from typing import Any")
            write.line_empty()
            write.line("from pyairtable.api.types import CreateRecordDict, RecordDict, UpdateRecordDict")
            write.line_empty()
            write.multiline_import(
                "..types",
                [
                    f"{table.name_pascal()}FieldsDict",
                    f"{table.name_pascal()}Field",
                ],
            )
            write.line_empty()

            # (class_suffix, parent_class, has_id, has_created_time, use_field_ids)
            dict_classes: list[tuple[str, str, bool, bool, bool]] = [
                ("CreateRecordDict", "CreateRecordDict", False, False, False),
                ("IdsCreateRecordDict", "CreateRecordDict", False, False, True),
                ("UpdateRecordDict", "UpdateRecordDict", True, False, False),
                ("IdsUpdateRecordDict", "UpdateRecordDict", True, False, True),
                ("RecordDict", "RecordDict", True, True, False),
                ("IdsRecordDict", "RecordDict", True, False, True),
            ]
            for suffix, parent, has_id, has_created_time, use_field_ids in dict_classes:
                write.line(f"class {table.name_pascal()}{suffix}({parent}):")
                write.line_indented(record_doc_string(table.name, id=has_id, created_time=has_created_time, use_field_ids=use_field_ids))
                if use_field_ids:
                    write.line_indented(f"fields: {table.name_pascal()}FieldsDict")
                else:
                    write.line_indented(f"fields: dict[{table.name_pascal()}Field, Any]")
                write.line_empty()
                write.line_empty()

    write_module_init(base, output_folder, Paths.DICTS)


# endregion

# region MODELS
# PyAirtable ORM field types used in model generation
PYAIRTABLE_FIELD_TYPES: tuple[str, ...] = (
    "SingleLineTextField",
    "MultilineTextField",
    "PhoneNumberField",
    "EmailField",
    "LinkField",
    "SingleLinkField",
    "UrlField",
    "DateField",
    "CreatedTimeField",
    "LastModifiedTimeField",
    "NumberField",
    "SelectField",
    "MultipleSelectField",
    "CheckboxField",
    "RichTextField",
    "CurrencyField",
    "PercentField",
    "LookupField",
    "AttachmentsField",
    "CreatedByField",
    "ButtonField",
    "CountField",
    "DatetimeField",
    "DurationField",
    "LastModifiedByField",
    "AutoNumberField",
    "CollaboratorField",
)


def write_models(base: Base, output_folder: Path, formulas: bool, package_prefix: str) -> None:
    models_dir = create_dynamic_subdir(output_folder, Paths.MODELS)

    for table in base.tables:
        with WriteToPythonFile(path=models_dir / f"{table.name_snake()}.py") as write:
            # Imports
            write.line("from datetime import datetime")
            write.line("from typing import Any, TYPE_CHECKING")
            write.line_empty()
            write.line("from pyairtable.orm import Model")
            write.line(f"from pyairtable.orm.fields import {', '.join(PYAIRTABLE_FIELD_TYPES)}")
            write.line_empty()
            write.line("from ...static.helpers import get_api_key, get_base_id")
            write.line("from ...static.special_types import AirtableAttachment, RecordId")
            write.select_options_import(table)
            write.line(f"from ..dicts import {table.name_pascal()}RecordDict")
            write.line(f"from ..formulas import {table.name_pascal()}Formulas")
            linked_tables = table.linked_tables()
            if len(linked_tables) > 0:
                write.line("if TYPE_CHECKING:")
            for linked_table in linked_tables:
                write.line_indented(f"from .{linked_table.name_snake()} import {linked_table.name_model()}")
            write.line_empty()
            write.line_empty()

            # definition
            write.line(f"class {table.name_model()}(Model):")
            write.line_indented(orm_model_doc_string(table.name))
            write.line_indented("class Meta:")
            write.line_indented("@staticmethod", 2)
            write.line_indented("def api_key() -> str:", 2)
            write.line_indented("return get_api_key()", 3)
            write.line_indented("@staticmethod", 2)
            write.line_indented("def base_id() -> str:", 2)
            write.line_indented("return get_base_id()", 3)
            write.line_indented(f'table_name = "{table.name}"', 2)
            write.line_indented("use_field_ids = True", 2)
            write.line_indented("memoize = True", 2)
            write.line_empty()

            # to_record_dict
            write.line_indented(f"def to_record_dict(self) -> {table.name_pascal()}RecordDict:")
            write.line_indented("return self.to_record()", 2)
            write.line_empty()

            if formulas:
                write.line_indented(f"f: {table.name_pascal()}Formulas = {table.name_pascal()}Formulas()")
                write.line_empty()

            # properties
            for field in table.fields:
                field_name = field.name_snake()
                pyairtable_type = pyairtable_orm_type(field, base, output_folder, package_prefix=package_prefix)
                write.line_indented(f"{field_name}: {pyairtable_type}")
                write.property_docstring(field, table)
            write.line_empty()

    write_module_init(base, output_folder, Paths.MODELS)


# endregion


# region TABLES
def write_tables(base: Base, output_folder: Path) -> None:
    tables_dir = create_dynamic_subdir(output_folder, Paths.TABLES)

    for table in base.tables:
        with WriteToPythonFile(path=tables_dir / f"{table.name_snake()}.py") as write:
            # Imports
            write.region("IMPORTS")
            write.line("from pyairtable import Table")
            write.line_empty()
            write.line("from ...static.airtable_table import AirtableTable")
            write.multiline_import(
                "..types",
                [
                    f"{table.name_pascal()}Field",
                    f"{table.name_pascal()}CalculatedFields",
                    f"{table.name_pascal()}CalculatedFieldIds",
                    f"{table.name_pascal()}View",
                    f"{table.name_pascal()}ViewNameIdMapping",
                    f"{table.name_pascal()}Fields",
                ],
            )
            write.multiline_import(
                "..dicts",
                [
                    f"{table.name_pascal()}RecordDict",
                    f"{table.name_pascal()}CreateRecordDict",
                    f"{table.name_pascal()}UpdateRecordDict",
                ],
            )
            write.line(f"from ..models import {table.name_model()}")
            write.endregion()
            write.line_empty()
            write.line_empty()

            # Tables
            write.region(table.name_upper())
            class_name = table.name_pascal()
            model_name = table.name_model()
            write.line(
                f"class {class_name}Table(AirtableTable[{class_name}RecordDict, {class_name}CreateRecordDict, {class_name}UpdateRecordDict, {model_name}, {class_name}View, {class_name}Field]):"
            )
            write.line_indented(table_doc_string(table))
            write.line_indented("@classmethod")
            write.line_indented("def from_table(cls, table: Table):")
            write.line_indented("cls = super().from_table(", 2)
            write.line_indented("table,", 3)
            write.line_indented(f"{table.name_pascal()}RecordDict,", 3)
            write.line_indented(f"{table.name_pascal()}CreateRecordDict,", 3)
            write.line_indented(f"{table.name_pascal()}UpdateRecordDict,", 3)
            write.line_indented(f"{table.name_model()},", 3)
            write.line_indented(f"{table.name_pascal()}CalculatedFields,", 3)
            write.line_indented(f"{table.name_pascal()}CalculatedFieldIds,", 3)
            write.line_indented(f"{table.name_pascal()}ViewNameIdMapping,", 3)
            write.line_indented(f"{table.name_pascal()}Fields,", 3)
            write.line_indented(")", 2)
            write.line_indented("return cls", 2)
            write.endregion()
            write.line_empty()

    write_module_init(base, output_folder, Paths.TABLES)


# endregion


# region FORMULA
def write_formula_helpers(base: Base, output_folder: Path) -> None:
    formulas_dir = create_dynamic_subdir(output_folder, Paths.FORMULAS)

    for table in base.tables:
        with WriteToPythonFile(path=formulas_dir / f"{table.name_snake()}.py") as write:
            # Imports
            write.line(
                "from ...static.formula import AttachmentsField, BooleanField, DateField, NumberField, TextField, SingleSelectField, MultiSelectField, ID"
            )
            write.select_options_import(table)
            write.line_empty()

            # Properties
            write.region("PROPERTIES")
            write.line(f"class {table.name_pascal()}Formulas:")
            write.line_indented("id: ID = ID()")
            for field in table.fields:
                property_name = field.name_snake()
                formula_class = field.formula_class()
                if formula_class == "SingleSelectField" or formula_class == "MultiSelectField":
                    write.line_indented(f"{property_name}: {formula_class}[{field.options_name()}] = {formula_class}('{field.id}')")
                else:
                    write.line_indented(f"{property_name}: {formula_class} = {formula_class}('{field.id}')")
                write.property_docstring(field, table)
            write.line_empty()
            write.endregion()

    write_module_init(base, output_folder, Paths.FORMULAS)


# endregion


# region MAIN CLASS
def write_main_class(base: Base, output_folder: Path) -> None:
    with WriteToPythonFile(path=output_folder / Paths.DYNAMIC / "airtable_main.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("from pyairtable import Api")
        write.line_empty()
        write.line("from .types import TableName")
        write.line("from ..static.airtable_table import TableType")
        write.line("from ..static.helpers import get_api_key, get_base_id")
        write.multiline_import(".tables", [f"{table.name_pascal()}Table" for table in base.tables])
        write.endregion()
        write.line_empty()
        write.line_empty()

        # Class
        write.region("MAIN CLASS")
        write.line("class Airtable:")
        write.line_indented(main_doc_string())
        write.line_empty()
        write.line_indented("_api: Api")
        write.line_indented("_base_id: str")
        write.line_indented("_tables: dict[TableName, TableType] = {}")
        write.line_empty()
        write.line_indented(
            'def __init__(self, api_key: str | None = None, base_id: str | None = None, endpoint_url: str = "https://api.airtable.com"):'
        )
        write.line_indented("self._base_id: str = base_id or get_base_id()", 2)
        write.line_indented("if not self._base_id:", 2)
        write.line_indented('raise ValueError("Base ID must be provided.")', 3)
        write.line_indented("api_key: str = api_key or get_api_key()", 2)
        write.line_indented("if not api_key:", 2)
        write.line_indented('raise ValueError("API key must be provided.")', 3)
        write.line_indented("self._api = Api(api_key=api_key, endpoint_url=endpoint_url)", 2)
        write.line_empty()
        for table in base.tables:
            write.line_indented("@property")
            write.line_indented(f"def {table.name_snake()}(self) -> {table.name_pascal()}Table:")
            write.line_indented(f"if '{table.name}' not in self._tables:", 2)
            write.line_indented(
                f'self._tables["{table.name}"] = {table.name_pascal()}Table.from_table(self._api.table(self._base_id, "{table.name}"))', 3
            )
            write.line_indented(f'return self._tables["{table.name}"]', 2)
            write.line_empty()
        write.endregion()


# endregion


# region INIT
def write_init(output_folder: Path, formulas: bool, wrappers: bool) -> None:
    with WriteToPythonFile(path=output_folder / Paths.DYNAMIC / "__init__.py") as write:
        # Imports
        write.line("from .types import *  # noqa: F403")
        write.line("from .dicts import *  # noqa: F403")
        write.line("from .models import *  # noqa: F403")
        if wrappers:
            write.line("from .tables import *  # noqa: F403")
            write.line("from .airtable_main import *  # noqa: F403")
        if formulas:
            write.line("from .formulas import *  # noqa: F403")

    with WriteToPythonFile(path=output_folder / "__init__.py") as write:
        # Imports
        write.line("from .dynamic import *  # noqa: F403")
        if formulas:
            write.line("from .static.formula import *  # noqa: F403")


# endregion


# region DOCSTRINGS
def record_doc_string(table_name: str, id: bool, created_time: bool, use_field_ids: bool = False) -> str:
    """Generate docstring for record TypedDict classes."""
    field_desc: str = "field ids" if use_field_ids else "field names"
    example_fields: str = (
        '"fld75gvKPpwKmG58B": "Alice",\n            "fldrEdQBTxp1Y8kKL": "Engineering"'
        if use_field_ids
        else '"Name": "Alice",\n            "Department": "Engineering"'
    )
    return f'''"""
    TypedDict representation for Airtable records from the `{table_name}` table.

    A type-hinted version of the pyairtable `RecordDict` class.

    `fields` are all Airtable {field_desc}

    ```
    {{
        {'"id": "recAdw9EjV90xbW",\n' if id else ""}{'"createdTime": "2023-05-22T21:24:15.333134Z",\n' if created_time else ""}\t\t\t"fields": {{
            {example_fields}
        }}
    }}
    ```
    """'''


def orm_model_doc_string(table_name: str) -> str:
    return f'''"""
    ORM model for Airtable records from the `{table_name}` table.

    Property names do not necessarily match field names in Airtable.
    """'''


def table_doc_string(table: Table) -> str:
    return f'''"""
    An abstraction of pyAirtable's `Api.table` for the `{table.name}` table, and an interface for working with custom-typed versions of the models/dicts created by the type generator.

    ```python
    record = Airtable().{table.name_snake()}.get("rec1234567890")
    ```

    You can also access the RecordDicts via `.dict`.
    
    ```python
    record = Airtable().{table.name_snake()}.dict.get("rec1234567890")
    ```

    You can also use the ORM Models directly. See https://pyairtable.readthedocs.io/en/stable/orm.html#
    """'''


def main_doc_string() -> str:
    return '''"""
    A collection of tables abstracting pyAirtable's `Api.table`. Represents the whole Airtable base.
    
    Provides an interface for working with custom-typed versions of the models/dicts created by the type generator, for each of the tables in the Airtable base.

    ```python
    record = Airtable().tablename.get("rec1234567890")
    ```

    You can also access the RecordDicts via `.dict`.
    
    ```python
    record = Airtable().tablename.dict.get("rec1234567890")
    ```

    You can also use the ORM Models directly. See https://pyairtable.readthedocs.io/en/stable/orm.html#
    """'''


# endregion

# region TYPE MAPPING

# Simple Airtable type → Python type mappings
SIMPLE_PYTHON_TYPES: dict[str, str] = {
    "singleLineText": "str",
    "multilineText": "str",
    "url": "str",
    "richText": "str",
    "email": "str",
    "phoneNumber": "str",
    "barcode": "str",
    "checkbox": "bool",
    "date": "datetime",
    "dateTime": "datetime",
    "createdTime": "datetime",
    "lastModifiedTime": "datetime",
    "count": "int",
    "autoNumber": "int",
    "percent": "float",
    "currency": "float",
    "duration": "timedelta",
    "multipleRecordLinks": "list[RecordId]",
    "multipleAttachments": "list[AirtableAttachment]",
    "singleCollaborator": "AirtableCollaborator",
    "lastModifiedBy": "AirtableCollaborator",
    "createdBy": "AirtableCollaborator",
    "button": "AirtableButton",
}


def python_type(field: Field) -> str:
    """Returns the appropriate Python type for a given Airtable field. Cached after first call."""
    # Return cached result if available
    if field._python_type_cache is not None:
        return field._python_type_cache

    airtable_type: FieldType = field.type

    # With calculated fields, we want to know the type of the result
    if field.is_calculated():
        airtable_type = field.result_type()

    # Handle simple type mappings via lookup
    if airtable_type in SIMPLE_PYTHON_TYPES:
        py_type = SIMPLE_PYTHON_TYPES[airtable_type]

    # Handle complex types with special logic
    elif airtable_type == "number":
        if field.options and field.options.precision is not None and field.options.precision == 0:
            py_type = "int"
        else:
            py_type = "float"
    elif airtable_type == "singleSelect":
        referenced_field = field.referenced_field()
        select_fields_ids = field.base.select_fields_ids()
        if field.id in select_fields_ids:
            py_type = field.options_name()
        elif referenced_field and referenced_field.type == "singleSelect" and referenced_field.id in select_fields_ids:
            py_type = referenced_field.options_name()
        else:
            py_type = "Any"
    elif airtable_type == "multipleSelects":
        select_fields_ids = field.base.select_fields_ids()
        if field.id in select_fields_ids:
            py_type = f"list[{field.options_name()}]"
        else:
            py_type = "Any"
    else:
        py_type = "Any"

    # TODO: In the case of some calculated fields, sometimes the result is just too unpredictable.
    # Although the type prediction is basically right, I haven't figured out how to predict if
    # it's a list or not, and sometimes the result is a list with a single null value.
    if "list" not in py_type:
        if field.involves_lookup() or field.involves_rollup():
            py_type = f"list[{py_type} | None] | {py_type}"

    field._python_type_cache = py_type
    return py_type


# Simple Airtable type → PyAirtable ORM field class mappings
SIMPLE_ORM_TYPES: dict[str, str] = {
    "singleLineText": "SingleLineTextField",
    "multilineText": "MultilineTextField",
    "url": "UrlField",
    "richText": "RichTextField",
    "email": "EmailField",
    "phoneNumber": "PhoneNumberField",
    "barcode": "BarcodeField",
    "lastModifiedBy": "LastModifiedByField",
    "createdBy": "CreatedByField",
    "checkbox": "CheckboxField",
    "date": "DateField",
    "dateTime": "DatetimeField",
    "createdTime": "CreatedTimeField",
    "lastModifiedTime": "LastModifiedTimeField",
    "count": "CountField",
    "autoNumber": "AutoNumberField",
    "percent": "PercentField",
    "duration": "DurationField",
    "currency": "CurrencyField",
    "number": "NumberField",
    "multipleAttachments": "AttachmentsField",
    "singleCollaborator": "CollaboratorField",
    "button": "ButtonField",
}


def pyairtable_orm_type(field: Field, base: Base, output_folder: Path, package_prefix: str) -> str:
    """Returns the appropriate PyAirtable ORM type for a given Airtable field."""
    airtable_type = field.type
    original_id = field.id
    is_read_only: bool = field.is_computed()

    # With formula/rollup fields, we want to know the type of the result
    if field.type in ["formula", "rollup"]:
        airtable_type = field.result_type()

    params = f'field_name="{original_id}"' + (", readonly=True" if is_read_only else "")

    # Handle simple type mappings via lookup
    if airtable_type in SIMPLE_ORM_TYPES:
        orm_class = SIMPLE_ORM_TYPES[airtable_type]
        return f"{orm_class} = {orm_class}({params})"

    # Handle complex types with special logic
    match airtable_type:
        case "singleSelect":
            if field.id in field.base.select_fields_ids():
                return f"{field.options_name()} = SelectField({params})"
            return f"SelectField = SelectField({params})"
        case "multipleSelects":
            if field.id in field.base.select_fields_ids():
                return f"list[{field.options_name()}] = MultipleSelectField({params}) # type: ignore"
            return f"MultipleSelectField = MultipleSelectField({params})"
        case "lookup" | "multipleLookupValues":
            return f"LookupField = LookupField[{python_type(field)}]({params})"
        case "multipleRecordLinks":
            if field.options and field.options.linked_table_id:
                table_id: str = field.options.linked_table_id
                for table in base.tables:
                    if table.id == table_id:
                        linked_orm_class = table.name_model()
                        break
                prefix = f"{package_prefix}.{output_folder.stem}.dynamic.models" if package_prefix else f"{output_folder.stem}.dynamic.models"
                if field.options.prefers_single_record_link:
                    return f'"{linked_orm_class}" = SingleLinkField["{linked_orm_class}"]({params}, model="{prefix}.{table.name_snake()}.{linked_orm_class}") # type: ignore'
                return f'list["{linked_orm_class}"] = LinkField["{linked_orm_class}"]({params}, model="{prefix}.{table.name_snake()}.{linked_orm_class}") # type: ignore'
            print(field.table.name, original_id, sanitize_string(field.name), "[yellow]does not have a linkedTableId[/]")
        case _:
            pass

    return "Any"


# endregion

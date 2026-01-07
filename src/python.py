import shutil
from pathlib import Path

from rich import print

from .helpers import (
    copy_static_files,
    sanitize_string,
)
from .meta import Base, Field, FieldType, Table
from .progress import progress_spinner
from .write_to_file import WriteToPythonFile


def gen_python(base: Base, output_folder: Path, csv_folder: Path, formulas: bool, wrappers: bool, package_prefix: str):
    with progress_spinner(message="Copying static files...", transient=False) as spinner:
        for table in base.tables:
            table.detect_duplicate_property_names()

        reset_folder(output_folder / "dynamic")
        reset_folder(output_folder / "static")

        copy_static_files(output_folder, "python")
        spinner.update(description="Generating types...")
        write_types(base, output_folder)

        spinner.update(description="Generating dicts...")
        write_dicts(base, output_folder)

        spinner.update(description="Generating models...")
        write_models(base, output_folder, formulas=formulas, package_prefix=package_prefix)

        if formulas:
            spinner.update(description="Generating formula helpers...")
            write_formula_helpers(base, output_folder)

        if wrappers:
            spinner.update(description="Generating tables...")
            write_tables(base, output_folder, csv_folder)

            spinner.update(description="Generating main class...")
            write_main_class(base, output_folder)

        spinner.update(description="Generating init...")
        write_init(output_folder, formulas, wrappers)

        spinner.update(description="Python Generation complete!")


def reset_folder(folder: Path) -> None:
    """Remove and recreate a folder if it exists."""
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)


def write_module_init(base: Base, output_folder: Path, subdir: str, extra_imports: list[str] | None = None) -> None:
    """Generate __init__.py that re-exports all table modules."""
    with WriteToPythonFile(path=output_folder / "dynamic" / subdir / "__init__.py") as write:
        if extra_imports:
            for line in extra_imports:
                write.line(line)
        for table in base.tables:
            write.line(f"from .{table.name_snake()} import *  # noqa: F403")


# region TYPES
def write_types(base: Base, output_folder: Path):
    # Table Types
    for table in base.tables:
        with WriteToPythonFile(path=output_folder / "dynamic" / "types" / f"{table.name_snake()}.py") as write:
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

    with WriteToPythonFile(path=output_folder / "dynamic" / "types" / "_tables.py") as write:
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

    write_module_init(base, output_folder, "types", extra_imports=["from ._tables import *  # noqa: F403"])


# endregion


# region DICTS
def write_dicts(base: Base, output_folder: Path):
    for table in base.tables:
        with WriteToPythonFile(path=output_folder / "dynamic" / "dicts" / f"{table.name_snake()}.py") as write:
            # Imports
            write.line("from typing import Any")
            write.line_empty()
            write.line("from pyairtable.api.types import CreateRecordDict, RecordDict, UpdateRecordDict")
            write.line_empty()
            write.line("from ..types import (")
            write.line_indented(f"{table.name_pascal()}FieldsDict,")
            write.line_indented(f"{table.name_pascal()}Field,")
            write.line(")")
            write.line_empty()

            write.line(f"class {table.name_pascal()}CreateRecordDict(CreateRecordDict):")
            write.line_indented(record_doc_string(table.name, id=False, created_time=False))
            write.line_indented(f"fields: dict[{f'{table.name_pascal()}Field'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {table.name_pascal()}IdsCreateRecordDict(CreateRecordDict):")
            write.line_indented(record_doc_string(table.name, id=False, created_time=False, use_field_ids=True))
            write.line_indented(f"fields: {table.name_pascal()}FieldsDict")
            write.line_empty()
            write.line_empty()

            write.line(f"class {table.name_pascal()}UpdateRecordDict(UpdateRecordDict):")
            write.line_indented(record_doc_string(table.name, id=True, created_time=False))
            write.line_indented(f"fields: dict[{f'{table.name_pascal()}Field'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {table.name_pascal()}IdsUpdateRecordDict(UpdateRecordDict):")
            write.line_indented(record_doc_string(table.name, id=True, created_time=False, use_field_ids=True))
            write.line_indented(f"fields: {table.name_pascal()}FieldsDict")
            write.line_empty()
            write.line_empty()

            write.line(f"class {table.name_pascal()}RecordDict(RecordDict):")
            write.line_indented(record_doc_string(table.name, id=True, created_time=True))
            write.line_indented(f"fields: dict[{f'{table.name_pascal()}Field'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {table.name_pascal()}IdsRecordDict(RecordDict):")
            write.line_indented(record_doc_string(table.name, id=True, created_time=False, use_field_ids=True))
            write.line_indented(f"fields: {table.name_pascal()}FieldsDict")
            write.line_empty()
            write.line_empty()

    write_module_init(base, output_folder, "dicts")


# endregion


# region MODELS
def write_models(base: Base, output_folder: Path, formulas: bool, package_prefix: str):
    for table in base.tables:
        with WriteToPythonFile(path=output_folder / "dynamic" / "models" / f"{table.name_snake()}.py") as write:
            # Imports
            write.line("from datetime import datetime")
            write.line("from typing import Any, TYPE_CHECKING")
            write.line_empty()
            write.line("from pyairtable.orm import Model")
            pyairtable_field_types: list[str] = [
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
            ]
            write.line(f"from pyairtable.orm.fields import {', '.join(pyairtable_field_types)}")
            write.line_empty()
            write.line("from ...static.helpers import get_api_key, get_base_id")
            write.line("from ...static.special_types import AirtableAttachment, RecordId")
            if len(table.select_fields()) > 0:
                write.line("from ..types import (")
                for field in table.select_fields():
                    write.line_indented(f"{field.options_name()},")
                write.line(")")
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

    write_module_init(base, output_folder, "models")


# endregion


# region TABLES
def write_tables(base: Base, output_folder: Path, csv_folder: Path):
    for table in base.tables:
        with WriteToPythonFile(path=output_folder / "dynamic" / "tables" / f"{table.name_snake()}.py") as write:
            # Imports
            write.region("IMPORTS")
            write.line("from pyairtable import Table")
            write.line_empty()
            write.line("from ...static.airtable_table import AirtableTable")
            write.line("from ..types import (")
            write.line_indented(f"{table.name_pascal()}Field,")
            write.line_indented(f"{table.name_pascal()}CalculatedFields,")
            write.line_indented(f"{table.name_pascal()}CalculatedFieldIds,")
            write.line_indented(f"{table.name_pascal()}View,")
            write.line_indented(f"{table.name_pascal()}ViewNameIdMapping,")
            write.line_indented(f"{table.name_pascal()}Fields,")
            write.line(")")
            write.line("from ..dicts import (")
            write.line_indented(f"{table.name_pascal()}RecordDict,")
            write.line_indented(f"{table.name_pascal()}CreateRecordDict,")
            write.line_indented(f"{table.name_pascal()}UpdateRecordDict,")
            write.line(")")
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
            write.line_indented(table_doc_string(table, csv_folder))
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

    write_module_init(base, output_folder, "tables")


# endregion


# region FORMULA


def write_formula_helpers(base: Base, output_folder: Path):
    for table in base.tables:
        with WriteToPythonFile(path=output_folder / "dynamic" / "formulas" / f"{table.name_snake()}.py") as write:
            # Imports
            write.line(
                "from ...static.formula import AttachmentsField, BooleanField, DateField, NumberField, TextField, SingleSelectField, MultiSelectField, ID"
            )
            if len(table.select_fields()) > 0:
                write.line("from ..types import (")
                for field in table.select_fields():
                    write.line_indented(f"{field.options_name()},")
                write.line(")")
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

    write_module_init(base, output_folder, "formulas")


# endregion


# region MAIN


def write_main_class(base: Base, output_folder: Path):
    with WriteToPythonFile(path=output_folder / "dynamic" / "airtable_main.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("from pyairtable import Api")
        write.line_empty()
        write.line("from .types import TableName")
        write.line("from ..static.airtable_table import TableType")
        write.line("from ..static.helpers import get_api_key, get_base_id")
        write.line("from .tables import (")
        for table in base.tables:
            write.line_indented(f"{table.name_pascal()}Table,")
        write.line(")")
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


def write_init(output_folder: Path, formulas: bool, wrappers: bool):
    with WriteToPythonFile(path=output_folder / "dynamic" / "__init__.py") as write:
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


def table_doc_string(table: Table, csv_folder: Path) -> str:
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


# region TYPE PARSING
def python_type(field: Field) -> str:
    """Returns the appropriate Python type for a given Airtable field."""

    airtable_type: FieldType = field.type
    py_type: str = "Any"

    # With calculated fields, we want to know the type of the result
    if field.is_calculated():
        airtable_type = field.result_type()

    match airtable_type:
        case "singleLineText" | "multilineText" | "url" | "richText" | "email" | "phoneNumber" | "barcode":
            py_type = "str"
        case "checkbox":
            py_type = "bool"
        case "date" | "dateTime" | "createdTime" | "lastModifiedTime":
            py_type = "datetime"
        case "count" | "autoNumber":
            py_type = "int"
        case "percent" | "currency":
            py_type = "float"
        case "duration":
            py_type = "timedelta"
        case "number":
            if field.options and field.options.precision is not None:
                if field.options.precision == 0:
                    py_type = "int"
                else:
                    py_type = "float"
            else:
                py_type = "float"
        case "multipleRecordLinks":
            py_type = "list[RecordId]"
        case "multipleAttachments":
            py_type = "list[AirtableAttachment]"
        case "singleCollaborator" | "lastModifiedBy" | "createdBy":
            py_type = "AirtableCollaborator"
        case "singleSelect":
            referenced_field = field.referenced_field()
            select_fields_ids = field.base.select_fields_ids()
            if field.id in select_fields_ids:
                py_type = field.options_name()
            elif referenced_field and referenced_field.type == "singleSelect" and referenced_field.id in select_fields_ids:
                py_type = referenced_field.options_name()
            else:
                py_type = "Any"
        case "multipleSelects":
            select_fields_ids = field.base.select_fields_ids()
            if field.id in select_fields_ids:
                py_type = f"list[{field.options_name()}]"
            else:
                py_type = "Any"
        case "button":
            py_type = "AirtableButton"
        case _:
            if not field.is_valid():
                py_type = "Any"

    # TODO: In the case of some calculated fields, sometimes the result is just too unpredictable.
    # Although the type prediction is basically right, I haven't figured out how to predict if
    # it's a list or not, and sometimes the result is a list with a single null value.
    if "list" not in py_type:
        if field.involves_lookup() or field.involves_rollup():
            py_type = f"list[{py_type} | None] | {py_type}"

    return py_type


def pyairtable_orm_type(field: Field, base: Base, output_folder: Path, package_prefix: str) -> str:
    """Returns the appropriate PyAirtable ORM type for a given Airtable field."""

    airtable_type = field.type
    original_id = field.id

    is_read_only: bool = field.is_computed()

    # With formula/rollup fields, we want to know the type of the result
    if field.type in ["formula", "rollup"]:
        airtable_type = field.result_type()

    params = f'field_name="{original_id}"' + (", readonly=True" if is_read_only else "")

    orm_type: str = "Any"

    match airtable_type:
        case "singleLineText":
            orm_type = f"SingleLineTextField = SingleLineTextField({params})"
        case "multilineText":
            orm_type = f"MultilineTextField = MultilineTextField({params})"
        case "url":
            orm_type = f"UrlField = UrlField({params})"
        case "richText":
            orm_type = f"RichTextField = RichTextField({params})"
        case "email":
            orm_type = f"EmailField = EmailField({params})"
        case "phoneNumber":
            orm_type = f"PhoneNumberField = PhoneNumberField({params})"
        case "barcode":
            orm_type = f"BarcodeField = BarcodeField({params})"
        case "lastModifiedBy":
            orm_type = f"LastModifiedByField = LastModifiedByField({params})"
        case "createdBy":
            orm_type = f"CreatedByField = CreatedByField({params})"
        case "checkbox":
            orm_type = f"CheckboxField = CheckboxField({params})"
        case "date":
            orm_type = f"DateField = DateField({params})"
        case "dateTime":
            orm_type = f"DatetimeField = DatetimeField({params})"
        case "createdTime":
            orm_type = f"CreatedTimeField = CreatedTimeField({params})"
        case "lastModifiedTime":
            orm_type = f"LastModifiedTimeField = LastModifiedTimeField({params})"
        case "count":
            orm_type = f"CountField = CountField({params})"
        case "autoNumber":
            orm_type = f"AutoNumberField = AutoNumberField({params})"
        case "percent":
            orm_type = f"PercentField = PercentField({params})"
        case "duration":
            orm_type = f"DurationField = DurationField({params})"
        case "currency":
            orm_type = f"CurrencyField = CurrencyField({params})"
        case "number":
            orm_type = f"NumberField = NumberField({params})"
        case "multipleAttachments":
            orm_type = f"AttachmentsField = AttachmentsField({params})"
        case "singleCollaborator":
            orm_type = f"CollaboratorField = CollaboratorField({params})"
        case "singleSelect":
            if field.id in field.base.select_fields_ids():
                orm_type = f"{field.options_name()} = SelectField({params})"
            else:
                orm_type = f"SelectField = SelectField({params})"
        case "multipleSelects":
            if field.id in field.base.select_fields_ids():
                orm_type = f"list[{field.options_name()}] = MultipleSelectField({params}) # type: ignore"
            else:
                orm_type = f"MultipleSelectField = MultipleSelectField({params})"
        case "button":
            orm_type = f"ButtonField = ButtonField({params})"
        case "lookup" | "multipleLookupValues":
            orm_type = f"LookupField = LookupField[{python_type(field)}]({params})"
        case "multipleRecordLinks":
            if field.options and field.options.linked_table_id:
                table_id = field.options.linked_table_id
                tables = base.tables
                for table in tables:
                    if table.id == table_id:
                        linked_orm_class = table.name_model()
                        break
                prefix = f"{package_prefix}.{output_folder.stem}.dynamic.models" if package_prefix else f"{output_folder.stem}.dynamic.models"
                if field.options.prefers_single_record_link:
                    orm_type = f'"{linked_orm_class}" = SingleLinkField["{linked_orm_class}"]({params}, model="{prefix}.{table.name_snake()}.{linked_orm_class}") # type: ignore'
                else:
                    orm_type = f'list["{linked_orm_class}"] = LinkField["{linked_orm_class}"]({params}, model="{prefix}.{table.name_snake()}.{linked_orm_class}") # type: ignore'
            else:
                print(field.table.name, original_id, sanitize_string(field.name), "[yellow]does not have a linkedTableId[/]")
        case _:
            if not field.is_valid():
                orm_type = "Any"

    return orm_type


# endregion

import shutil
from pathlib import Path

from pydantic import BaseModel
from rich import print

from .helpers import (
    WriteToPythonFile,
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
    property_name_snake,
    sanitize_string,
    upper_case,
    warn_unhandled_airtable_type,
)
from .meta_types import BaseMetadata, FieldMetadata, FieldType, TableMetadata

all_fields: dict[str, FieldMetadata] = {}
select_options: dict[str, str] = {}
table_id_name_map: dict[str, str] = {}


def gen_python(metadata: BaseMetadata, base_id: str, folder: Path, formulas: bool, wrappers: bool):
    for table in metadata["tables"]:
        table_id_name_map[table["id"]] = table["name"]
        for field in table["fields"]:
            all_fields[field["id"]] = field
            options = get_select_options(field)
            if len(options) > 0:
                select_options[field["id"]] = f"{options_name(property_name_pascal(table, folder), property_name_pascal(field, folder))}"
        detect_duplicate_property_names(table, folder)

    dynamic_folder = folder / "dynamic"
    if dynamic_folder.exists():
        shutil.rmtree(dynamic_folder)
        dynamic_folder.mkdir(parents=True, exist_ok=True)

    static_folder = folder / "static"
    if static_folder.exists():
        shutil.rmtree(static_folder)
        static_folder.mkdir(parents=True, exist_ok=True)

    copy_static_files(folder, "python")
    write_types(metadata, folder)
    write_dicts(metadata, folder)
    write_models(metadata, base_id, folder, formulas)
    # write_pydantic_models(metadata, folder)
    if formulas:
        write_formula_helpers(metadata, folder)
    if wrappers:
        write_tables(metadata, folder)
        write_main_class(metadata, base_id, folder)
    write_init(metadata, folder, formulas, wrappers)


# region TYPES
def write_types(metadata: BaseMetadata, folder: Path):
    # Table Types
    for table in metadata["tables"]:
        with WriteToPythonFile(path=folder / "dynamic" / "types" / f"{property_name_snake(table, folder)}.py") as write:
            # Imports
            write.region("IMPORTS")
            write.line("from datetime import datetime, timedelta")
            write.line("from typing import Any, Literal, TypedDict")
            write.line_empty()
            write.line("from ...static.special_types import AirtableAttachment, AirtableButton, AirtableCollaborator, RecordId")
            write.endregion()
            write.line_empty()

            write.region("OPTIONS")
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    write.types(
                        options_name(property_name_pascal(table, folder), property_name_pascal(field, folder)),
                        options,
                        f"Select options for `{sanitize_string(field['name'])}`",
                    )
            write.endregion()

            field_names = [sanitize_string(field["name"]) for field in table["fields"]]
            field_ids = [field["id"] for field in table["fields"]]
            property_names = [property_name_snake(field, folder) for field in table["fields"]]

            write.region(upper_case(table["name"]))

            write.types(f"{property_name_pascal(table, folder)}Field", field_names, f"Field names for `{table['name']}`")
            write.types(f"{property_name_pascal(table, folder)}FieldId", field_ids, f"Field IDs for `{table['name']}`")
            write.types(f"{property_name_pascal(table, folder)}FieldProperty", property_names, f"Property names for `{table['name']}`")

            write.str_list(
                f"{property_name_pascal(table, folder)}CalculatedFields",
                [sanitize_string(field["name"]) for field in table["fields"] if is_computed_field(field)],
            )
            write.line(f'"""Calculated fields for `{table["name"]}`"""')
            write.str_list(
                f"{property_name_pascal(table, folder)}CalculatedFieldIds",
                [field["id"] for field in table["fields"] if is_computed_field(field)],
            )
            write.line(f'"""Calculated fields for `{table["name"]}`"""')
            write.line_empty()

            write.dict_class(
                f"{property_name_pascal(table, folder)}FieldNameIdMapping",
                [(sanitize_string(field["name"]), field["id"]) for field in table["fields"]],
                first_type=f"{property_name_pascal(table, folder)}Field",
                second_type=f"{property_name_pascal(table, folder)}FieldId",
            )
            write.dict_class(
                f"{property_name_pascal(table, folder)}FieldIdNameMapping",
                [(field["id"], sanitize_string(field["name"])) for field in table["fields"]],
                first_type=f"{property_name_pascal(table, folder)}FieldId",
                second_type=f"{property_name_pascal(table, folder)}Field",
            )
            write.dict_class(
                f"{property_name_pascal(table, folder)}FieldIdPropertyMapping",
                [(field["id"], property_name_snake(field, folder)) for field in table["fields"]],
                first_type=f"{property_name_pascal(table, folder)}FieldId",
                second_type=f"{property_name_pascal(table, folder)}FieldProperty",
            )
            write.dict_class(
                f"{property_name_pascal(table, folder)}FieldPropertyIdMapping",
                [(property_name_snake(field, folder), field["id"]) for field in table["fields"]],
                first_type=f"{property_name_pascal(table, folder)}FieldProperty",
                second_type=f"{property_name_pascal(table, folder)}FieldId",
            )

            write.line(f"class {property_name_pascal(table, folder)}FieldsDict(TypedDict, total=False):")
            for field in table["fields"]:
                write.property_row(field["id"], python_type(table["name"], field, warn=True))
            write.line_empty()
            write.line_empty()

            views = table["views"]
            view_names: list[str] = [sanitize_string(view["name"]) for view in views]
            view_ids: list[str] = [view["id"] for view in views]
            write.types(f"{property_name_pascal(table, folder)}View", view_names, f"View names for `{table['name']}`")
            write.types(f"{property_name_pascal(table, folder)}ViewId", view_ids, f"View IDs for `{table['name']}`")
            write.dict_class(
                f"{property_name_pascal(table, folder)}ViewNameIdMapping",
                [(sanitize_string(view["name"]), view["id"]) for view in table["views"]],
                first_type=f"{property_name_pascal(table, folder)}View",
                second_type=f"{property_name_pascal(table, folder)}ViewId",
            )
            write.dict_class(
                f"{property_name_pascal(table, folder)}ViewIdNameMapping",
                [(view["id"], sanitize_string(view["name"])) for view in table["views"]],
                first_type=f"{property_name_pascal(table, folder)}ViewId",
                second_type=f"{property_name_pascal(table, folder)}View",
            )

            write.endregion()

    with WriteToPythonFile(path=folder / "dynamic" / "types" / "_tables.py") as write:
        write.line("from typing import Literal")
        write.line_empty()

        # Table Lists
        table_names = []
        table_ids = []
        for table in metadata["tables"]:
            table_names.append(table["name"])
            table_ids.append(table["id"])

        write.types("TableName", table_names)
        write.types("TableId", table_ids)
        write.dict_class(
            "TableNameIdMapping",
            [(table["name"], table["id"]) for table in metadata["tables"]],
            first_type="TableName",
            second_type="TableId",
        )
        write.dict_class(
            "TableIdNameMapping",
            [(table["id"], table["name"]) for table in metadata["tables"]],
            first_type="TableId",
            second_type="TableName",
        )
        write.dict_class(
            "TableIdToFieldNameIdMapping",
            [(table["id"], f"{property_name_camel(table, folder)}FieldNameIdMapping") for table in metadata["tables"]],
            first_type="TableId",
            second_type="dict[str, str]",
        )
        write.dict_class(
            "TableIdToFieldNamesTypeMapping",
            [(table["id"], f"{property_name_camel(table, folder)}FieldName") for table in metadata["tables"]],
            first_type="TableId",
        )
        write.dict_class(
            "TableIdToFieldNamesListMapping",
            [(table["id"], f"{property_name_camel(table, folder)}FieldNames") for table in metadata["tables"]],
            first_type="TableId",
        )

    with WriteToPythonFile(path=folder / "dynamic" / "types" / "__init__.py") as write:
        write.line("from ._tables import *  # noqa: F403")
        for table in metadata["tables"]:
            write.line(f"from .{property_name_snake(table, folder)} import *  # noqa: F403")


# endregion


# region DICTS
def write_dicts(metadata: BaseMetadata, folder: Path):
    for table in metadata["tables"]:
        with WriteToPythonFile(path=folder / "dynamic" / "dicts" / f"{property_name_snake(table, folder)}.py") as write:
            # Imports
            write.line("from typing import Any")
            write.line_empty()
            write.line("from pyairtable.api.types import CreateRecordDict, RecordDict, UpdateRecordDict")
            write.line_empty()
            write.line("from ..types import (")
            write.line_indented(f"{property_name_pascal(table, folder)}FieldsDict,")
            write.line_indented(f"{property_name_pascal(table, folder)}Field,")
            write.line(")")
            write.line_empty()

            write.line(f"class {property_name_pascal(table, folder)}CreateRecordDict(CreateRecordDict):")
            write.line_indented(name_record_doc_string(table["name"], id=False, created_time=False))
            write.line_indented(f"fields: dict[{f'{property_name_pascal(table, folder)}Field'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {property_name_pascal(table, folder)}IdsCreateRecordDict(CreateRecordDict):")
            write.line_indented(id_record_doc_string(table["name"], id=False, created_time=False))
            write.line_indented(f"fields: {property_name_pascal(table, folder)}FieldsDict")
            write.line_empty()
            write.line_empty()

            write.line(f"class {property_name_pascal(table, folder)}UpdateRecordDict(UpdateRecordDict):")
            write.line_indented(name_record_doc_string(table["name"], id=True, created_time=False))
            write.line_indented(f"fields: dict[{f'{property_name_pascal(table, folder)}Field'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {property_name_pascal(table, folder)}IdsUpdateRecordDict(UpdateRecordDict):")
            write.line_indented(id_record_doc_string(table["name"], id=True, created_time=False))
            write.line_indented(f"fields: {property_name_pascal(table, folder)}FieldsDict")
            write.line_empty()
            write.line_empty()

            write.line(f"class {property_name_pascal(table, folder)}RecordDict(RecordDict):")
            write.line_indented(name_record_doc_string(table["name"], id=True, created_time=True))
            write.line_indented(f"fields: dict[{f'{property_name_pascal(table, folder)}Field'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {property_name_pascal(table, folder)}IdsRecordDict(RecordDict):")
            write.line_indented(id_record_doc_string(table["name"], id=True, created_time=False))
            write.line_indented(f"fields: {property_name_pascal(table, folder)}FieldsDict")
            write.line_empty()
            write.line_empty()

    with WriteToPythonFile(path=folder / "dynamic" / "dicts" / "__init__.py") as write:
        for table in metadata["tables"]:
            write.line(f"from .{property_name_snake(table, folder)} import *  # noqa: F403")


# endregion


# region MODELS
def write_models(metadata: BaseMetadata, base_id: str, folder: Path, formulas: bool):
    for table in metadata["tables"]:
        with WriteToPythonFile(path=folder / "dynamic" / "models" / f"{property_name_snake(table, folder)}.py") as write:
            # Imports
            write.line("from datetime import datetime")
            write.line("from typing import Any")
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
            write.line("from ...static.helpers import get_api_key")
            write.line("from ...static.special_types import AirtableAttachment, RecordId")
            all_options: list[str] = []
            for field in table["fields"]:
                options = get_select_options(field)
                all_options.extend(options)
            if len(all_options) > 0:
                write.line("from ..types import (")
                for field in table["fields"]:
                    options = get_select_options(field)
                    if len(options) > 0:
                        write.line_indented(f"{options_name(property_name_pascal(table, folder), property_name_pascal(field, folder))},")
                write.line(")")
            write.line(f"from ..dicts import {property_name_pascal(table, folder)}RecordDict")
            write.line(f"from ..formulas import {property_name_pascal(table, folder)}Formulas")
            write.line_empty()
            write.line_empty()

            # definition
            write.line(f"class {property_name_model(table, folder)}(Model):")
            write.line_indented(orm_model_doc_string(table["name"]))
            write.line_indented("class Meta:")
            write.line_indented("@staticmethod", 2)
            write.line_indented("def api_key() -> str:", 2)
            write.line_indented("return get_api_key()", 3)
            write.line_indented(f'base_id = "{base_id}"', 2)
            write.line_indented(f'table_name = "{table["name"]}"', 2)
            write.line_indented("use_field_ids = True", 2)
            write.line_indented("memoize = True", 2)
            write.line_empty()

            # to_record_dict
            write.line_indented(f"def to_record_dict(self) -> {property_name_pascal(table, folder)}RecordDict:")
            write.line_indented("return self.to_record()", 2)
            write.line_empty()

            if formulas:
                write.line_indented(f"f: {property_name_pascal(table, folder)}Formulas = {property_name_pascal(table, folder)}Formulas()")
                write.line_empty()

            # properties
            for field in table["fields"]:
                write.line_indented(f"{property_name_snake(field, folder)}: {pyairtable_orm_type(table['name'], field, metadata, folder)}")
                write.property_docstring(field, table)
            write.line_empty()

    with WriteToPythonFile(path=folder / "dynamic" / "models" / "__init__.py") as write:
        for table in metadata["tables"]:
            write.line(f"from .{property_name_snake(table, folder)} import *  # noqa: F403")


# endregion


# region TABLES
def write_tables(metadata: BaseMetadata, folder: Path):
    for table in metadata["tables"]:
        with WriteToPythonFile(path=folder / "dynamic" / "tables" / f"{property_name_snake(table, folder)}.py") as write:
            # Imports
            write.region("IMPORTS")
            write.line("from pyairtable import Table")
            write.line_empty()
            write.line("from ...static.airtable_table import AirtableTable")
            write.line("from ..types import (")
            write.line_indented(f"{property_name_pascal(table, folder)}Field,")
            write.line_indented(f"{property_name_pascal(table, folder)}CalculatedFields,")
            write.line_indented(f"{property_name_pascal(table, folder)}CalculatedFieldIds,")
            write.line_indented(f"{property_name_pascal(table, folder)}View,")
            write.line_indented(f"{property_name_pascal(table, folder)}ViewNameIdMapping,")
            write.line_indented(f"{property_name_pascal(table, folder)}Fields,")
            write.line(")")
            write.line("from ..dicts import (")
            write.line_indented(f"{property_name_pascal(table, folder)}RecordDict,")
            write.line_indented(f"{property_name_pascal(table, folder)}CreateRecordDict,")
            write.line_indented(f"{property_name_pascal(table, folder)}UpdateRecordDict,")
            write.line(")")
            write.line(f"from ..models import {property_name_model(table, folder)}")
            write.endregion()
            write.line_empty()
            write.line_empty()

            # Tables
            write.region(upper_case(table["name"]))
            class_name = property_name_pascal(table, folder)
            model_name = property_name_model(table, folder)
            write.line(
                f"class {class_name}Table(AirtableTable[{class_name}RecordDict, {class_name}CreateRecordDict, {class_name}UpdateRecordDict, {model_name}, {class_name}View, {class_name}Field]):"
            )
            write.line_indented(table_doc_string(table, folder))
            write.line_indented("@classmethod")
            write.line_indented("def from_table(cls, table: Table):")
            write.line_indented("cls = super().from_table(", 2)
            write.line_indented("table,", 3)
            write.line_indented(f"{property_name_pascal(table, folder)}RecordDict,", 3)
            write.line_indented(f"{property_name_pascal(table, folder)}CreateRecordDict,", 3)
            write.line_indented(f"{property_name_pascal(table, folder)}UpdateRecordDict,", 3)
            write.line_indented(f"{property_name_model(table, folder)},", 3)
            write.line_indented(f"{property_name_pascal(table, folder)}CalculatedFields,", 3)
            write.line_indented(f"{property_name_pascal(table, folder)}CalculatedFieldIds,", 3)
            write.line_indented(f"{property_name_pascal(table, folder)}ViewNameIdMapping,", 3)
            write.line_indented(f"{property_name_pascal(table, folder)}Fields,", 3)
            write.line_indented(")", 2)
            write.line_indented("return cls", 2)
            write.endregion()
            write.line_empty()

    with WriteToPythonFile(path=folder / "dynamic" / "tables" / "__init__.py") as write:
        for table in metadata["tables"]:
            write.line(f"from .{property_name_snake(table, folder)} import *  # noqa: F403")


# endregion


# region FORMULA


def write_formula_helpers(metadata: BaseMetadata, folder: Path):
    for table in metadata["tables"]:
        with WriteToPythonFile(path=folder / "dynamic" / "formulas" / f"{property_name_snake(table, folder)}.py") as write:
            # Imports
            write.line("from ...static.formula import AttachmentsField, BooleanField, DateField, NumberField, TextField, ID")
            write.line_empty()

            # Properties
            write.region("PROPERTIES")
            write.line(f"class {property_name_pascal(table, folder)}Formulas:")
            write.line_indented("id: ID = ID()")
            for field in table["fields"]:
                property_name = property_name_snake(field, folder)
                formula_class = formula_type(table["name"], field)
                write.line_indented(f"{property_name}: {formula_class} = {formula_class}('{field['id']}')")
                write.property_docstring(field, table)
            write.line_empty()
            write.endregion()

    with WriteToPythonFile(path=folder / "dynamic" / "formulas" / "__init__.py") as write:
        for table in metadata["tables"]:
            write.line(f"from .{property_name_snake(table, folder)} import *  # noqa: F403")


# endregion


# region MAIN


def write_main_class(metadata: BaseMetadata, base_id: str, folder: Path):
    with WriteToPythonFile(path=folder / "dynamic" / "airtable_main.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("from pyairtable import Api")
        write.line_empty()
        write.line("from .types import TableName")
        write.line("from ..static.airtable_table import TableType")
        write.line("from ..static.helpers import get_api_key")
        write.line("from .tables import (")
        for table in metadata["tables"]:
            write.line_indented(f"{property_name_pascal(table, folder)}Table,")
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
        write.line_indented(f"_base_id: str = '{base_id}'")
        write.line_indented("_tables: dict[TableName, TableType] = {}")
        write.line_empty()
        write.line_indented("def __init__(self):")
        write.line_indented("api_key: str = get_api_key()", 2)
        write.line_indented("if not api_key:", 2)
        write.line_indented('raise ValueError("API key must be provided.")', 3)
        write.line_indented("self._api = Api(api_key=api_key)", 2)
        write.line_empty()
        for table in metadata["tables"]:
            write.line_indented("@property")
            write.line_indented(f"def {property_name_snake(table, folder, use_custom=False)}(self) -> {property_name_pascal(table, folder)}Table:")
            write.line_indented(f"if '{table['name']}' not in self._tables:", 2)
            write.line_indented(
                f'self._tables["{table["name"]}"] = {property_name_pascal(table, folder)}Table.from_table(self._api.table(self._base_id, "{table["name"]}"))',
                3,
            )
            write.line_indented(f'return self._tables["{table["name"]}"]', 2)
            write.line_empty()
        write.endregion()


def write_init(metadata: BaseMetadata, folder: Path, formulas: bool, wrappers: bool):
    with WriteToPythonFile(path=folder / "dynamic" / "__init__.py") as write:
        # Imports
        write.line("from .types import *  # noqa: F403")
        write.line("from .dicts import *  # noqa: F403")
        write.line("from .models import *  # noqa: F403")
        if wrappers:
            write.line("from .tables import *  # noqa: F403")
            write.line("from .airtable_main import *  # noqa: F403")
        if formulas:
            write.line("from .formulas import *  # noqa: F403")

    with WriteToPythonFile(path=folder / "__init__.py") as write:
        # Imports
        write.line("from .dynamic import *  # noqa: F403")
        if formulas:
            write.line("from .static.formula import *  # noqa: F403")


# endregion


# region DOCSTRINGS
def id_record_doc_string(table_name: str, id: bool, created_time: bool) -> str:
    return f'''"""
    TypedDict representation for Airtable records from the `{table_name}` table.

    A type-hinted version of the pyairtable `RecordDict` class.

    `fields` are all Airtable field ids

    ```
    {{
        {'"id": "recAdw9EjV90xbW",\n' if id else ""}{'"createdTime": "2023-05-22T21:24:15.333134Z",\n' if created_time else ""}\t\t\t"fields": {{
            "fld75gvKPpwKmG58B": "Alice",
            "fldrEdQBTxp1Y8kKL": "Engineering"
        }}
    }}
    ```
    """'''


def name_record_doc_string(table_name: str, id: bool, created_time: bool) -> str:
    return f'''"""
    TypedDict representation for Airtable records from the `{table_name}` table.

    A type-hinted version of the pyairtable `RecordDict` class.
    
    `fields` are all Airtable field names

    ```
    {{
        {'"id": "recAdw9EjV90xbW",\n' if id else ""}{'"createdTime": "2023-05-22T21:24:15.333134Z",\n' if created_time else ""}\t\t\t"fields": {{
            "Name": "Alice",
            "Department": "Engineering"
        }}
    }}
    ```
    """'''


def orm_model_doc_string(table_name: str) -> str:
    return f'''"""
    ORM model for Airtable records from the `{table_name}` table.

    Property names do not necessarily match field names in Airtable.
    """'''


def table_doc_string(table: TableMetadata, folder: Path) -> str:
    return f'''"""
    An abstraction of pyAirtable's `Api.table` for the `{table["name"]}` table, and an interface for working with custom-typed versions of the models/dicts created by the type generator.

    ```python
    record = Airtable().{property_name_snake(table, folder, use_custom=False)}.get("rec1234567890")
    ```

    You can also access the RecordDicts via `.dict`.
    
    ```python
    record = Airtable().{property_name_snake(table, folder, use_custom=False)}.dict.get("rec1234567890")
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


# region NAMES


# endregion


# region TYPE PARSING
def python_type(table_name: str, field: FieldMetadata, warn: bool = False) -> str:
    """Returns the appropriate Python type for a given Airtable field."""

    airtable_type: FieldType = field["type"]
    py_type: str = "Any"

    # With calculated fields, we want to know the type of the result
    if is_calculated_field(field):
        airtable_type = get_result_type(field)

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
            if "options" in field and "precision" in field["options"]:  # type: ignore
                if field["options"]["precision"] == 0:  # type: ignore
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
            referenced_field = get_referenced_field(field, all_fields)
            if field["id"] in select_options:
                py_type = select_options[field["id"]]
            elif referenced_field and referenced_field["type"] == "singleSelect" and referenced_field["id"] in select_options:
                py_type = select_options[referenced_field["id"]]
            else:
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                py_type = "Any"
        case "multipleSelects":
            if field["id"] in select_options:
                py_type = f"list[{select_options[field['id']]}]"
            else:
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                py_type = "Any"
        case "button":
            py_type = "AirtableButton"
        case _:
            if not is_valid_field(field):
                if warn:
                    warn_unhandled_airtable_type(table_name, field)
                py_type = "Any"

    # TODO: In the case of some calculated fields, sometimes the result is just too unpredictable.
    # Although the type prediction is basically right, I haven't figured out how to predict if
    # it's a list or not, and sometimes the result is a list with a single null value.
    if "list" not in py_type:
        if involves_lookup_field(field, all_fields) or involves_rollup_field(field, all_fields):
            py_type = f"list[{py_type} | None] | {py_type}"

    return py_type


def formula_type(table_name: str, field: FieldMetadata) -> str:
    """Returns the appropriate myAirtable formula type for a given Airtable field."""

    airtable_type: FieldType = field["type"]
    formula_type: str = "TextField"

    # With calculated fields, we want to know the type of the result
    if is_calculated_field(field):
        airtable_type = get_result_type(field)

    match airtable_type:
        case "singleLineText" | "multilineText" | "url" | "richText" | "email" | "phoneNumber" | "barcode":
            formula_type = "TextField"
        case "checkbox":
            formula_type = "BooleanField"
        case "date" | "dateTime" | "createdTime" | "lastModifiedTime":
            formula_type = "DateField"
        case "count" | "autoNumber" | "percent" | "currency" | "duration" | "number":
            formula_type = "NumberField"
        case "multipleAttachments":
            formula_type = "AttachmentsField"
        case _:
            formula_type = "TextField"

    return formula_type


def pyairtable_orm_type(table_name: str, field: FieldMetadata, metadata: BaseMetadata, folder: Path) -> str:
    """Returns the appropriate PyAirtable ORM type for a given Airtable field."""

    airtable_type = field["type"]
    original_id = field["id"]

    is_read_only: bool = is_computed_field(field)

    # With formula/rollup fields, we want to know the type of the result
    if field["type"] in ["formula", "rollup"]:
        airtable_type = get_result_type(field)

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
            if field["id"] in select_options:
                options_const = select_options[field["id"]]
                orm_type = f"{options_const} = SelectField({params})"
            else:
                orm_type = f"SelectField = SelectField({params})"
        case "multipleSelects":
            if field["id"] in select_options:
                options_const = select_options[field["id"]]
                orm_type = f"list[{options_const}] = MultipleSelectField({params}) # type: ignore"
            else:
                orm_type = f"MultipleSelectField = MultipleSelectField({params})"
        case "button":
            orm_type = f"ButtonField = ButtonField({params})"
        case "lookup" | "multipleLookupValues":
            orm_type = f"LookupField = LookupField[{python_type(table_name, field)}]({params})"
        case "multipleRecordLinks":
            if "options" in field and "linkedTableId" in field["options"]:  # type: ignore
                table_id = field["options"]["linkedTableId"]  # type: ignore
                tables = metadata["tables"]
                for table in tables:
                    if table["id"] == table_id:
                        linked_orm_class = property_name_model(table, folder)
                        break
                if field["options"]["prefersSingleRecordLink"]:  # type: ignore
                    orm_type = f'"{linked_orm_class}" = SingleLinkField["{linked_orm_class}"]({params}, model="{linked_orm_class}") # type: ignore'
                else:
                    orm_type = f'list["{linked_orm_class}"] = LinkField["{linked_orm_class}"]({params}, model="{linked_orm_class}") # type: ignore'
            else:
                print(table_name, original_id, sanitize_string(field["name"]), "[yellow]does not have a linkedTableId[/]")
        case _:
            if not is_valid_field(field):
                orm_type = "Any"

    return orm_type


class TypeAndReferencedField(BaseModel):
    type: FieldType
    field: FieldMetadata | None
    types: list[FieldType] = []


def get_calculated_type(field: FieldMetadata, airtable_type: FieldType) -> TypeAndReferencedField:
    """Get the resulting type of a calculated field"""

    result: TypeAndReferencedField = TypeAndReferencedField(type=airtable_type, field=None)

    match airtable_type:
        case "formula":
            if is_formula_that_references_field_type(field, "formula"):
                result.type = "formula"
                result.field = get_referenced_field_from_formula(field, "formula")
            elif is_formula_that_references_field_type(field, "rollup"):
                result.type = "rollup"
                result.field = get_referenced_field_from_formula(field, "rollup")
            elif is_formula_that_references_field_type(field, "lookup"):
                result.type = "lookup"
                result.field = get_referenced_field_from_formula(field, "lookup")
            elif is_formula_that_references_field_type(field, "multipleLookupValues"):
                result.type = "multipleLookupValues"
                result.field = get_referenced_field_from_formula(field, "multipleLookupValues")
            elif is_formula_that_references_field_type(field, "multipleRecordLinks"):
                result.type = "multipleRecordLinks"
                result.field = get_referenced_field_from_formula(field, "multipleRecordLinks")
            else:
                result.type = get_result_type(field, airtable_type)
        case "rollup":
            if is_rollup_that_references_field_type(field, "formula"):
                result.type = "formula"
                result.field = get_referenced_field(field, all_fields)
            elif is_rollup_that_references_field_type(field, "rollup"):
                result.type = "rollup"
                result.field = get_referenced_field(field, all_fields)
            elif is_rollup_that_references_field_type(field, "lookup"):
                result.type = "lookup"
                result.field = get_referenced_field(field, all_fields)
            elif is_rollup_that_references_field_type(field, "multipleLookupValues"):
                result.type = "multipleLookupValues"
                result.field = get_referenced_field(field, all_fields)
            elif is_rollup_that_references_field_type(field, "multipleRecordLinks"):
                result.type = "multipleRecordLinks"
                result.field = get_referenced_field(field, all_fields)
            else:
                result.type = get_result_type(field, airtable_type)
        case "lookup" | "multipleLookupValues":
            if is_lookup_that_references_field_type(field, "formula"):
                result.type = "formula"
                result.field = get_referenced_field(field, all_fields)
            elif is_lookup_that_references_field_type(field, "rollup"):
                result.type = "rollup"
                result.field = get_referenced_field(field, all_fields)
            elif is_lookup_that_references_field_type(field, "lookup"):
                result.type = "lookup"
                result.field = get_referenced_field(field, all_fields)
            elif is_lookup_that_references_field_type(field, "multipleLookupValues"):
                result.type = "multipleLookupValues"
                result.field = get_referenced_field(field, all_fields)
            elif is_lookup_that_references_field_type(field, "multipleRecordLinks"):
                result.type = "multipleRecordLinks"
                result.field = get_referenced_field(field, all_fields)
            else:
                result.type = get_result_type(field, airtable_type)

    result.types.append(result.type)

    return result


def get_referenced_field_from_formula(field: FieldMetadata, type: FieldType) -> FieldMetadata | None:
    """Check if a formula field references a field of the given type"""

    if field["type"] == "formula":
        if "options" in field and "referencedFieldIds" in field["options"]:
            field_ids = field["options"]["referencedFieldIds"]
            for field_id in field_ids:
                if all_fields[field_id]["type"] == type:
                    return all_fields[field_id]

    return None


def is_lookup_that_references_field_type(field: FieldMetadata, target_type: FieldType) -> bool:
    """Check if a lookup field references a field of the given type."""

    if field["type"] == "lookup" or field["type"] == "multipleLookupValues":
        options = field.get("options", {})
        referenced_field_id = options.get("fieldIdInLinkedTable")
        if referenced_field_id and referenced_field_id in all_fields:
            return all_fields[referenced_field_id]["type"] == target_type

    return False


def is_rollup_that_references_field_type(field: FieldMetadata, target_type: FieldType) -> bool:
    """Check if a rollup field references a field of the given type."""

    if field["type"] == "rollup":
        options = field.get("options", {})
        referenced_field_id = options.get("fieldIdInLinkedTable")
        if referenced_field_id and referenced_field_id in all_fields:
            return all_fields[referenced_field_id]["type"] == target_type

    return False


def is_formula_that_references_field_type(field: FieldMetadata, type: FieldType) -> bool:
    """Check if a formula field references a field of the given type"""

    if field["type"] == "formula":
        if "options" in field and "referencedFieldIds" in field["options"]:
            field_ids = field["options"]["referencedFieldIds"]
            for field_id in field_ids:
                if all_fields[field_id]["type"] == type:
                    return True

    return False


# endregion


# region HELPERS


# endregion

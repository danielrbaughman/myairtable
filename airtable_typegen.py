import os
from pathlib import Path
from typing import Optional

import pandas as pd
from pydantic import BaseModel
from rich import print
from rich.console import Console
from rich.table import Table

from meta import get_base_meta_data
from meta_types import FIELD_TYPE, AirTableFieldMetadata, AirtableMetadata, TableMetadata

OUTPUT_PATH = Path("./output")
TABLES_CSV_PATH = Path("./tables.csv")
FIELDS_CSV_PATH = Path("./fields.csv")


all_fields: dict[str, AirTableFieldMetadata] = {}
select_options: dict[str, str] = {}
table_id_name_map: dict[str, str] = {}


def python_gen(verbose: bool = False):
    """`WIP` Generate Python types and models for Airtable"""

    metadata = get_base_meta_data()

    for table in metadata["tables"]:
        table_id_name_map[table["id"]] = table["name"]
        for field in table["fields"]:
            all_fields[field["id"]] = field
            options = get_select_options(field)
            if len(options) > 0:
                select_options[field["id"]] = f"{options_const(upper_case(table['name']), upper_case(field['name']))}_TYPE"

    write_types(metadata, verbose)
    write_dicts(metadata, verbose)
    write_orm_models(metadata, verbose)
    write_pydantic_models(metadata, verbose)
    write_tables(metadata, verbose)
    write_main_class(metadata, verbose)
    write_init(metadata, verbose)


# region WRITE
class WriteToFile(BaseModel):
    """Abstracts file writing operations."""

    path: Path
    file: Optional[object] = None
    lines: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            if self.path.exists():
                os.remove(self.path)
            os.makedirs(self.path.parent, exist_ok=True)
            self.file = open(self.path, "a")
            for line in self.lines:
                self.file.write(line + "\n")
            self.file.close()

    def line(self, text: str):
        self.lines.append(text)

    def line_empty(self):
        self.lines.append("")

    def region(self, text: str):
        self.lines.append(f"# region {text}")

    def endregion(self):
        self.lines.append("# endregion")
        self.line_empty()

    def line_indented(self, text: str, indent: int = 1):
        self.lines.append("    " * indent + text)

    def dict_row(self, key: str, value: str):
        self.line_indented(f'"{key}": "{value}",')

    def property_row(self, name: str, type: str):
        self.line_indented(f"{name}: {type}")

    def dict_class(self, name: str, pairs: list[tuple[str, str]], first_type: str = "str", second_type: str = "str"):
        self.line(f"{name}: dict[{first_type}, {second_type}] = {{")
        for k, v in pairs:
            self.dict_row(k, v)
        self.line("}")
        self.line_empty()

    def literal(self, name: str, list: list[str]):
        self.line(f"{name} = Literal[{', '.join(f'"{item}"' for item in list)}]")

    def str_list(self, name: str, list: list[str], type: str = "str"):
        self.line(f"{name}: list[{type}] = [{', '.join(f'"{item}"' for item in list)}]")

    def types(self, name: str, list: list[str], docstring: str = ""):
        literal_name = f"{name}_TYPE"
        self.literal(literal_name, list)
        if docstring:
            self.line(f'"""{docstring}"""')
        self.str_list(f"{name}_LIST", list, type=literal_name)
        if docstring:
            self.line(f'"""{docstring}"""')
        self.line_empty()

    def property_docstring(self, field: AirTableFieldMetadata, table: TableMetadata):
        if field["id"] == table["primaryFieldId"]:
            if is_computed_field(field):
                self.line_indented(f'"""{field["name"]} `{field["id"]}` - `Primary Key` - `Read-Only Field`"""')
            else:
                self.line_indented(f'"""{field["name"]} `{field["id"]}` - `Primary Key`"""')
        elif is_computed_field(field):
            self.line_indented(f'"""{field["name"]} `{field["id"]}` - `Read-Only Field`"""')
        else:
            self.line_indented(f'"""{field["name"]} `{field["id"]}`"""')


# endregion


# region TYPES
def write_types(metadata: AirtableMetadata, verbose: bool):
    with WriteToFile(path=OUTPUT_PATH / "types.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("from datetime import datetime, timedelta")
        write.line("from typing import Any, Literal, TypedDict")
        write.line_empty()
        write.line("from ..static.special_types import AirtableAttachment, AirtableButton, AirtableCollaborator, RecordId")
        write.endregion()
        write.line_empty()

        # Field Options
        write.region("FIELD OPTIONS")
        for table in metadata["tables"]:
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    write.types(options_const(upper_case(table["name"]), upper_case(field["name"])), options, f"Select options for `{field['name']}`")
        write.endregion()

        # Table Types
        for table in metadata["tables"]:
            field_names = [field["name"] for field in table["fields"]]
            field_ids = [field["id"] for field in table["fields"]]
            property_names = [property_name(field) for field in table["fields"]]

            write.region(upper_case(table["name"]))

            write.types(f"{upper_case(table['name'])}_FIELD_NAMES", field_names, f"Field names for `{table['name']}`")
            write.types(f"{upper_case(table['name'])}_FIELD_IDS", field_ids, f"Field IDs for `{table['name']}`")
            write.types(f"{upper_case(table['name'])}_FIELD_PROPERTIES", property_names, f"Property names for `{table['name']}`")

            write.str_list(
                f"{upper_case(table['name'])}_CALCULATED_FIELD_NAMES_LIST",
                [field["name"] for field in table["fields"] if is_computed_field(field)],
            )
            write.line(f'"""Calculated fields for `{table["name"]}`"""')
            write.str_list(
                f"{upper_case(table['name'])}_CALCULATED_FIELD_IDS_LIST",
                [field["id"] for field in table["fields"] if is_computed_field(field)],
            )
            write.line(f'"""Calculated fields for `{table["name"]}`"""')
            write.line_empty()

            write.dict_class(
                f"{upper_case(table['name'])}_FIELD_NAME_ID_MAPPING",
                [(field["name"], field["id"]) for field in table["fields"]],
                first_type=f"{upper_case(table['name'])}_FIELD_NAMES_TYPE",
                second_type=f"{upper_case(table['name'])}_FIELD_IDS_TYPE",
            )
            write.dict_class(
                f"{upper_case(table['name'])}_FIELD_ID_NAME_MAPPING",
                [(field["id"], field["name"]) for field in table["fields"]],
                first_type=f"{upper_case(table['name'])}_FIELD_IDS_TYPE",
                second_type=f"{upper_case(table['name'])}_FIELD_NAMES_TYPE",
            )
            write.dict_class(
                f"{upper_case(table['name'])}_FIELD_ID_PROPERTY_MAPPING",
                [(field["id"], property_name(field)) for field in table["fields"]],
                first_type=f"{upper_case(table['name'])}_FIELD_IDS_TYPE",
                second_type=f"{upper_case(table['name'])}_FIELD_PROPERTIES_TYPE",
            )
            write.dict_class(
                f"{upper_case(table['name'])}_FIELD_PROPERTY_ID_MAPPING",
                [(property_name(field), field["id"]) for field in table["fields"]],
                first_type=f"{upper_case(table['name'])}_FIELD_PROPERTIES_TYPE",
                second_type=f"{upper_case(table['name'])}_FIELD_IDS_TYPE",
            )

            write.line(f"class {camel_case(table['name'])}Fields(TypedDict, total=False):")
            for field in table["fields"]:
                write.property_row(field["id"], python_type(field, warn=True, verbose=verbose))
            write.line_empty()
            write.line_empty()

            write.endregion()

        # Table Lists
        table_names_const = []
        table_ids = []
        for table in metadata["tables"]:
            table_names_const.append(upper_case(table["name"]))
            table_ids.append(table["id"])

        write.region("TABLES")
        write.types("TABLE_NAMES", table_names_const)
        write.types("TABLE_IDS", table_ids)
        write.dict_class(
            "TABLE_NAME_ID_MAPPING",
            [(table["name"], table["id"]) for table in metadata["tables"]],
            first_type="TABLE_NAMES_TYPE",
            second_type="TABLE_IDS_TYPE",
        )
        write.dict_class(
            "TABLE_ID_NAME_MAPPING",
            [(table["id"], table["name"]) for table in metadata["tables"]],
            first_type="TABLE_IDS_TYPE",
            second_type="TABLE_NAMES_TYPE",
        )
        write.dict_class(
            "TABLE_ID_TO_FIELD_NAME_ID_MAPPING",
            [(table["id"], f"{upper_case(table['name'])}_FIELD_NAME_ID_MAPPING") for table in metadata["tables"]],
            first_type="TABLE_IDS_TYPE",
            second_type="dict[str, str]",
        )
        write.dict_class(
            "TABLE_ID_TO_FIELD_NAMES_TYPE_MAPPING",
            [(table["id"], f"{upper_case(table['name'])}_FIELD_NAMES_TYPE") for table in metadata["tables"]],
            first_type="TABLE_IDS_TYPE",
        )
        write.dict_class(
            "TABLE_ID_TO_FIELD_NAMES_LIST_MAPPING",
            [(table["id"], f"{upper_case(table['name'])}_FIELD_NAMES_LIST") for table in metadata["tables"]],
            first_type="TABLE_IDS_TYPE",
        )
        write.endregion()


# endregion


# region TYPES
def write_dicts(metadata: AirtableMetadata, verbose: bool):
    with WriteToFile(path=OUTPUT_PATH / "dicts.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("from typing import Any")
        write.line_empty()
        write.line("from pyairtable.api.types import CreateRecordDict, RecordDict, UpdateRecordDict")
        write.line_empty()
        write.line("from .types import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Fields,")
        for table in metadata["tables"]:
            write.line_indented(f"{upper_case(table['name'])}_FIELD_NAMES_TYPE,")
        write.line(")")
        write.endregion()
        write.line_empty()

        # Dicts
        for table in metadata["tables"]:
            write.region(upper_case(table["name"]))
            write.line(f"class {camel_case(table['name'])}CreateRecordDict(CreateRecordDict):")
            write.line_indented(name_record_doc_string(table["name"], id=False, created_time=False))
            write.line_indented(f"fields: dict[{f'{upper_case(table["name"])}_FIELD_NAMES_TYPE'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {camel_case(table['name'])}IdsCreateRecordDict(CreateRecordDict):")
            write.line_indented(id_record_doc_string(table["name"], id=False, created_time=False))
            write.line_indented(f"fields: {camel_case(table['name'])}Fields")
            write.line_empty()
            write.line_empty()

            write.line(f"class {camel_case(table['name'])}UpdateRecordDict(UpdateRecordDict):")
            write.line_indented(name_record_doc_string(table["name"], id=True, created_time=False))
            write.line_indented(f"fields: dict[{f'{upper_case(table["name"])}_FIELD_NAMES_TYPE'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {camel_case(table['name'])}IdsUpdateRecordDict(UpdateRecordDict):")
            write.line_indented(id_record_doc_string(table["name"], id=True, created_time=False))
            write.line_indented(f"fields: {camel_case(table['name'])}Fields")
            write.line_empty()
            write.line_empty()

            write.line(f"class {camel_case(table['name'])}RecordDict(RecordDict):")
            write.line_indented(name_record_doc_string(table["name"], id=True, created_time=True))
            write.line_indented(f"fields: dict[{f'{upper_case(table["name"])}_FIELD_NAMES_TYPE'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {camel_case(table['name'])}IdsRecordDict(RecordDict):")
            write.line_indented(id_record_doc_string(table["name"], id=True, created_time=False))
            write.line_indented(f"fields: {camel_case(table['name'])}Fields")
            write.line_empty()
            write.line_empty()

            write.endregion()


# endregion


# region ORM
def write_orm_models(metadata: AirtableMetadata, verbose: bool):
    with WriteToFile(path=OUTPUT_PATH / "orm_models.py") as write:
        # Imports
        write.region("IMPORTS")
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
        write.line("from ..static.constants import get_api_key, get_base_id")
        write.line("from ..static.special_types import AirtableAttachment, RecordId")
        write.line("from .types import (")
        for table in metadata["tables"]:
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    write.line_indented(f"{options_const(upper_case(table['name']), upper_case(field['name']))}_TYPE,")
        write.line(")")
        write.line("from .models import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Model,")
        write.line(")")
        write.endregion()
        write.line_empty()
        write.line_empty()

        # Models
        for table in metadata["tables"]:
            write.region(upper_case(table["name"]))

            # definition
            write.line(f"class {camel_case(table['name'])}ORM(Model):")
            write.line_indented(orm_model_doc_string(table["name"]))
            write.line_indented("class Meta:")
            write.line_indented("@staticmethod", 2)
            write.line_indented("def api_key() -> str:", 2)
            write.line_indented("return get_api_key()", 3)
            write.line_indented("@staticmethod", 2)
            write.line_indented("def base_id() -> str:", 2)
            write.line_indented("return get_base_id()", 3)
            write.line_indented(f'table_name = "{table["name"]}"', 2)
            write.line_indented("use_field_ids = True", 2)
            write.line_indented("memoize = True", 2)
            write.line_empty()

            # properties
            for field in table["fields"]:
                write.line_indented(f"{property_name(field)}: {pyairtable_orm_type(table['name'], field, verbose)}")
                write.property_docstring(field, table)
            write.line_empty()

            # to_model
            write.line_indented(f"def to_model(self) -> {camel_case(table['name'])}Model:")
            write.line_indented(f"return {camel_case(table['name'])}Model.model_validate(self)", 2)
            write.line_empty()

            write.endregion()


# endregion


# region MODELS
def write_pydantic_models(metadata: AirtableMetadata, verbose: bool):
    with WriteToFile(path=OUTPUT_PATH / "models.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("from datetime import datetime, timedelta")
        write.line("from typing import Any, Optional, overload")
        write.line_empty()
        write.line("from ..static.special_types import AirtableAttachment, AirtableButton, AirtableCollaborator, RecordId")
        write.line("from ..static.pydantic_model import AirtableBaseModel")
        write.line("from .types import (")
        for table in metadata["tables"]:
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    write.line_indented(f"{options_const(upper_case(table['name']), upper_case(field['name']))}_TYPE,")
        write.line(")")
        write.line("from .dicts import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}RecordDict,")
            write.line_indented(f"{camel_case(table['name'])}IdsRecordDict,")
            write.line_indented(f"{camel_case(table['name'])}CreateRecordDict,")
            write.line_indented(f"{camel_case(table['name'])}IdsCreateRecordDict,")
            write.line_indented(f"{camel_case(table['name'])}UpdateRecordDict,")
            write.line_indented(f"{camel_case(table['name'])}IdsUpdateRecordDict,")
        write.line(")")
        write.endregion()
        write.line_empty()
        write.line_empty()

        for table in metadata["tables"]:
            select_options: dict[str, str] = {}
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    select_options[field["id"]] = f"{options_const(upper_case(table['name']), upper_case(field['name']))}_TYPE"

            write.region(upper_case(table["name"]))

            # Properties
            write.line(f"class {camel_case(table['name'])}Model(AirtableBaseModel):")
            for field in table["fields"]:
                write.line_indented(f"{property_name(field)}: {pydantic_type(field)}")
                write.property_docstring(field, table)
            write.line_empty()

            # _to_fields
            write.line_indented("def _to_fields(self, use_field_ids: bool) -> dict:")
            write.line_indented("fields: dict = {}", 2)
            write.line_indented("if use_field_ids:", 2)
            for field in table["fields"]:
                write.line_indented(f"if self.{property_name(field)} is not None:", 3)
                write.line_indented(f'fields["{field["id"]}"] = self.{property_name(field)}', 4)
            write.line_indented("else:", 2)
            for field in table["fields"]:
                write.line_indented(f"if self.{property_name(field)} is not None:", 3)
                write.line_indented(f'fields["{field["name"]}"] = self.{property_name(field)}', 4)
            write.line_indented("return fields", 2)
            write.line_empty()

            # to_record_dict
            def _to_record_dict(method: str, record_type: str):
                write.line_indented("@overload")
                write.line_indented(f"def {method}(self) -> {camel_case(table['name'])}{record_type}: ...")
                write.line_indented("@overload")
                write.line_indented(f"def {method}(self, use_field_ids: bool) -> {camel_case(table['name'])}Ids{record_type}: ...")
                write.line_indented(
                    f"def {method}(self, use_field_ids: bool = False) -> {camel_case(table['name'])}{record_type} | {camel_case(table['name'])}Ids{record_type}:"
                )
                write.line_indented(f"record = super().{method}()", 2)
                write.line_indented("record['fields'] = self._to_fields(use_field_ids)", 2)
                write.line_indented("return record", 2)
                write.line_empty()

            _to_record_dict("to_create_record_dict", "CreateRecordDict")
            _to_record_dict("to_update_record_dict", "UpdateRecordDict")
            _to_record_dict("to_record_dict", "RecordDict")

            write.endregion()


# endregion


# region TABLES
def write_tables(metadata: AirtableMetadata, verbose: bool):
    with WriteToFile(path=OUTPUT_PATH / "tables.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("from pyairtable import Table")
        write.line_empty()
        write.line("from ..static.airtable_table import AirtableTable")
        write.line("from .types import (")
        for table in metadata["tables"]:
            write.line_indented(f"{upper_case(table['name'])}_CALCULATED_FIELD_NAMES_LIST,")
            write.line_indented(f"{upper_case(table['name'])}_CALCULATED_FIELD_IDS_LIST,")
        write.line(")")
        write.line("from .dicts import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}RecordDict,")
            write.line_indented(f"{camel_case(table['name'])}CreateRecordDict,")
            write.line_indented(f"{camel_case(table['name'])}UpdateRecordDict,")
        write.line(")")
        write.line("from .orm_models import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}ORM,")
        write.line(")")
        write.line("from .models import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Model,")
        write.line(")")
        write.endregion()
        write.line_empty()
        write.line_empty()

        # Tables
        for table in metadata["tables"]:
            write.region(upper_case(table["name"]))
            write.line(
                f"class {camel_case(table['name'])}Table(AirtableTable[{camel_case(table['name'])}RecordDict, {camel_case(table['name'])}CreateRecordDict, {camel_case(table['name'])}UpdateRecordDict, {camel_case(table['name'])}ORM, {camel_case(table['name'])}Model]):"
            )
            write.line_indented(table_doc_string(table))
            write.line_indented("@classmethod")
            write.line_indented("def from_table(cls, table: Table):")
            write.line_indented("cls = super().from_table(", 2)
            write.line_indented("table,", 3)
            write.line_indented(f"{camel_case(table['name'])}RecordDict,", 3)
            write.line_indented(f"{camel_case(table['name'])}CreateRecordDict,", 3)
            write.line_indented(f"{camel_case(table['name'])}UpdateRecordDict,", 3)
            write.line_indented(f"{camel_case(table['name'])}ORM,", 3)
            write.line_indented(f"{camel_case(table['name'])}Model,", 3)
            write.line_indented(f"{upper_case(table['name'])}_CALCULATED_FIELD_NAMES_LIST,", 3)
            write.line_indented(f"{upper_case(table['name'])}_CALCULATED_FIELD_IDS_LIST,", 3)
            write.line_indented(")", 2)
            write.line_indented("return cls", 2)
            write.endregion()
            write.line_empty()


# endregion


# region MAIN


def write_main_class(metadata: AirtableMetadata, verbose: bool):
    with WriteToFile(path=OUTPUT_PATH / "airtable_main.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("import os")
        write.line_empty()
        write.line("from pyairtable import Api")
        write.line_empty()
        # write.line("from ..static.constants import API_KEY, BASE_ID")
        write.line("from .tables import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Table,")
        write.line(")")
        write.endregion()
        write.line_empty()
        write.line_empty()

        # Class
        write.region("MAIN CLASS")
        write.line("class Airtable:")
        write.line_indented(main_doc_string())
        for table in metadata["tables"]:
            write.line_indented(f"{property_name(table, use_custom=False).lower()}: {camel_case(table['name'])}Table")
        write.line_empty()
        write.line_indented("def __init__(self, api_key: str = '', base_id: str = ''):")
        write.line_indented("if not api_key:", 2)
        write.line_indented("api_key = os.getenv('AIRTABLE_API_KEY') or ''", 3)
        write.line_indented("if not base_id:", 2)
        write.line_indented("base_id = os.getenv('AIRTABLE_BASE_ID') or ''", 3)
        write.line_indented("if not api_key or not base_id:", 2)
        write.line_indented('raise ValueError("API key and Base ID must be provided.")', 3)
        write.line_indented("api = Api(api_key=api_key)", 2)
        for table in metadata["tables"]:
            write.line_indented(
                f'self.{property_name(table, use_custom=False).lower()} = {camel_case(table["name"])}Table.from_table(api.table(base_id, "{table["name"]}"))',
                2,
            )
        write.endregion()


def write_init(metadata: AirtableMetadata, verbose: bool):
    with WriteToFile(path=OUTPUT_PATH / "__init__.py") as write:
        # Imports
        write.line("from .types import *  # noqa: F403")
        write.line("from .dicts import *  # noqa: F403")
        write.line("from .orm_models import *  # noqa: F403")
        write.line("from .models import *  # noqa: F403")
        write.line("from .tables import *  # noqa: F403")
        write.line("from .airtable_main import *  # noqa: F403")


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


def table_doc_string(table: TableMetadata) -> str:
    return f'''"""
    An abstraction of pyAirtable's `Api.table` for the `{table["name"]}` table, and an interface for working with custom-typed versions of the models/dicts created by the type generator.

    Has tables for RecordDicts under `.dict`, pyAirtable ORM models under `.orm`, and Pydantic models under `.model`.

    ```python
    record = Airtable().{property_name(table, use_custom=False)}.dict.get("rec1234567890")
    record = Airtable().{property_name(table, use_custom=False)}.orm.get("rec1234567890")
    record = Airtable().{property_name(table, use_custom=False)}.model.get("rec1234567890")
    ```

    You can also access the ORM tables without `.orm`.

    ```python
    record = Airtable().{property_name(table, use_custom=False)}.get("rec1234567890")
    ```

    You can also use the ORM Models directly. See https://pyairtable.readthedocs.io/en/stable/orm.html#
    """'''


def main_doc_string() -> str:
    return '''"""
    A collection of tables abstracting pyAirtable's `Api.table`. Represents the whole Airtable base.
    
    Provides an interface for working with custom-typed versions of the models/dicts created by the type generator, for each of the tables in the Airtable base.

    Has tables for RecordDicts under `.dict`, pyAirtable ORM models under `.orm`, and Pydantic models under `.model`.

    ```python
    record = Airtable().tablename.dict.get("rec1234567890")
    record = Airtable().tablename.orm.get("rec1234567890")
    record = Airtable().tablename.model.get("rec1234567890")
    ```

    You can also access the ORM tables without `.orm`.

    ```python
    record = Airtable().tablename.get("rec1234567890")
    ```

    You can also use the ORM Models directly. See https://pyairtable.readthedocs.io/en/stable/orm.html#
    """'''


# endregion


# region NAMES
def options_const(table_name_const: str, field_name: str) -> str:
    return f"{table_name_const}_{field_name.upper()}_OPTIONS"


def upper_case(text: str) -> str:
    """Formats as UPPERCASE"""

    def alpha_only(text: str) -> str:
        return "".join(c for c in text if c.isalpha())

    return alpha_only(text).upper()


def camel_case(text: str) -> str:
    """Formats as CamelCase"""

    def non_alpha_to_space(text: str) -> str:
        return "".join(c if c.isalpha() else " " for c in text)

    def capitalize_words(text: str) -> list[str]:
        return [word.capitalize() for word in text.split()]

    text = non_alpha_to_space(text)
    return "".join(capitalize_words(text))


fields_dataframe: pd.DataFrame = None  # type: ignore
tables_dataframe: pd.DataFrame = None  # type: ignore


def get_custom_property_name(field_or_table: AirTableFieldMetadata | TableMetadata) -> str | None:
    """Gets the custom property name for a field or table, if it exists."""

    global fields_dataframe
    if fields_dataframe is None:
        fields_dataframe = pd.read_csv(FIELDS_CSV_PATH)

    global tables_dataframe
    if tables_dataframe is None:
        tables_dataframe = pd.read_csv(TABLES_CSV_PATH)

    id = "Table ID" if "primaryFieldId" in field_or_table else "Field ID"
    match = fields_dataframe[fields_dataframe[id] == field_or_table["id"]]
    if not match.empty:
        if "Property Name" in match.columns:
            custom_property_name = match.iloc[0]["Property Name"]
            if isinstance(custom_property_name, str) and custom_property_name.strip():
                name = snake_case(custom_property_name.strip())
                if name:
                    return name

    return None


def property_name(field_or_table: AirTableFieldMetadata | TableMetadata, use_custom: bool = True) -> str:
    """Formats as snake_case, and sanitizes the name to remove any characters that are not allowed in property names"""

    if use_custom:
        text = get_custom_property_name(field_or_table)
        if text:
            return text

    text = field_or_table["name"]

    text = sanitize_property_name(text)
    text = snake_case(text)
    text = sanitize_leading_trailing_characters(text)
    text = sanitize_reserved_names(text)

    return text


def sanitize_property_name(text: str) -> str:
    """Sanitizes the property name to remove any characters that are not allowed in property names"""

    if text.endswith("?"):
        text = text[:-1]
        text = "is_" + text
    if text.endswith(" #"):
        text = text[:-1]
        text = text + "number"

    text = text.replace("+", " and ")
    text = text.replace("&", " and ")
    text = text.replace("=", " is ")
    text = text.replace("%", " percent ")
    text = text.replace("<", " less than ")
    text = text.replace(">", " greater than ")
    text = text.replace("$/", " dollars per ")
    text = text.replace("$ ", "dollar ")
    text = text.replace("w/", " with ")
    text = text.replace("# ", " number ")

    text = text.replace("(", "").replace(")", "")
    text = text.replace("?", "").replace("$", "")
    text = text.replace("#", "").replace("'", "")

    text = text.replace("/", "_")
    text = text.replace("\\", "_")
    text = text.replace("-", "_")
    text = text.replace(".", "_")
    text = text.replace(":", "_")

    return text


def snake_case(text: str) -> str:
    """Formats as snake_case"""

    text = text.replace(" ", "_")
    text = text.replace("__", "_").replace("__", "_").replace("__", "_").replace("__", "_").replace("__", "_")
    text = text.lower()

    return text


def sanitize_leading_trailing_characters(text: str) -> str:
    """Sanitizes leading and trailing characters, to deal with characters that are not allowed and/or desired in property names"""

    if text.startswith("_"):
        text = text[1:]
    if text.endswith("_"):
        text = text[:-1]
    if text and text[0].isdigit():
        text = f"n_{text}"

    return text


def sanitize_reserved_names(text: str) -> str:
    """Some names are reserved by the pyairtable library and cannot be used as property names."""

    if text == "id":
        text = "identifier"
    if text == "created_time":
        text = "created_at"

    return text


# endregion


# region TYPE PARSING
def python_type(field: AirTableFieldMetadata, verbose: bool = False, warn: bool = False) -> str:
    """Returns the appropriate Python type for a given Airtable field."""

    airtable_type: FIELD_TYPE = field["type"]
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
            # if "options" in field and "precision" in field["options"]:
            #     if field["options"]["precision"] == 0:
            #         py_type = "int"
            #     else:
            #         py_type = "float"
            # else:

            # You'd think that precision == 0 would mean int, but that's not always the case
            # TODO ??? - found issue in Deals table - fldHHgC24A8Wf4lGo
            py_type = "float"
        case "multipleRecordLinks":
            py_type = "list[RecordId]"
        case "multipleAttachments":
            py_type = "list[AirtableAttachment]"
        case "singleCollaborator" | "lastModifiedBy" | "createdBy":
            py_type = "AirtableCollaborator"
        case "singleSelect":
            referenced_field = get_referenced_field(field)
            if field["id"] in select_options:
                py_type = select_options[field["id"]]
            elif referenced_field and referenced_field["type"] == "singleSelect" and referenced_field["id"] in select_options:
                py_type = select_options[referenced_field["id"]]
            else:
                if warn:
                    warn_unhandled_airtable_type(field, airtable_type, verbose)
                py_type = "Any"
        case "multipleSelects":
            if field["id"] in select_options:
                py_type = f"list[{select_options[field['id']]}]"
            else:
                if warn:
                    warn_unhandled_airtable_type(field, airtable_type, verbose)
                py_type = "Any"
        case "button":
            py_type = "AirtableButton"
        case _:
            if not is_valid_field(field):
                if warn:
                    warn_unhandled_airtable_type(field, airtable_type, verbose)
                py_type = "Any"

    # TODO: In the case of some calculated fields, sometimes the result is just too unpredictable.
    # Although the type prediction is basically right, I haven't figured out how to predict if
    # it's a list or not, and sometimes the result is a list with a single null value.
    # I don't love this, but it works. Pydantic throws validation errors without it.
    # - this might have something to do with select fields... Those can be null
    if "list" not in py_type:
        if involves_lookup_field(field) or involves_rollup_field(field):
            py_type = f"list[{py_type} | None] | {py_type}"

    return py_type


def pydantic_type(field: AirTableFieldMetadata) -> str:
    """Returns the appropriate Python type as Optional"""

    return f"Optional[{python_type(field)}] = None"


def pyairtable_orm_type(table_name: str, field: AirTableFieldMetadata, verbose: bool, warn: bool = True) -> str:
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
            orm_type = f"SelectField = SelectField({params})"
        case "multipleSelects":
            orm_type = f"MultipleSelectField = MultipleSelectField({params})"
        case "button":
            orm_type = f"ButtonField = ButtonField({params})"
        case "lookup" | "multipleLookupValues":
            orm_type = f"LookupField = LookupField[{python_type(field)}]({params})"
        case "multipleRecordLinks":
            if "options" in field and "linkedTableId" in field["options"]:
                linked_table_name = table_id_name_map.get(field["options"]["linkedTableId"], field["options"]["linkedTableId"])
                linked_orm_class = f"{camel_case(linked_table_name)}ORM"
                if field["options"]["prefersSingleRecordLink"]:
                    orm_type = f'"{linked_orm_class}" = SingleLinkField["{linked_orm_class}"]({params}, model="{linked_orm_class}") # type: ignore'
                else:
                    orm_type = f'list["{linked_orm_class}"] = LinkField["{linked_orm_class}"]({params}, model="{linked_orm_class}") # type: ignore'
            else:
                print(table_name, original_id, field["name"], "[yellow]does not have a linkedTableId[/]")
        case _:
            if not is_valid_field(field):
                orm_type = "Any"

    if orm_type == "Any" and warn:
        warn_unhandled_airtable_type(field, airtable_type, verbose)

    return orm_type


def involves_lookup_field(field: AirTableFieldMetadata) -> bool:
    """Check if a field involves multipleLookupValues, either directly or through any referenced fields."""
    if field["type"] == "multipleLookupValues" or field["type"] == "lookup":
        return True

    # Check if field has referencedFieldIds and recursively check each one
    options = field.get("options", {})
    referenced_field_ids = options.get("referencedFieldIds", [])

    if referenced_field_ids:
        for referenced_field_id in referenced_field_ids:
            if referenced_field_id in all_fields:
                referenced_field = all_fields[referenced_field_id]
                if involves_lookup_field(referenced_field):
                    return True
    return False


def involves_rollup_field(field: AirTableFieldMetadata) -> bool:
    """Check if a field involves rollup, either directly or through any referenced fields."""
    if field["type"] == "rollup":
        return True

    # Check if field has referencedFieldIds and recursively check each one
    options = field.get("options", {})
    referenced_field_ids = options.get("referencedFieldIds", [])

    if referenced_field_ids:
        for referenced_field_id in referenced_field_ids:
            if referenced_field_id in all_fields:
                referenced_field = all_fields[referenced_field_id]
                if involves_rollup_field(referenced_field):
                    return True
    return False


class TypeAndReferencedField(BaseModel):
    type: FIELD_TYPE
    field: AirTableFieldMetadata | None
    types: list[FIELD_TYPE] = []


def get_calculated_type(field: AirTableFieldMetadata, airtable_type: FIELD_TYPE) -> TypeAndReferencedField:
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
                result.field = get_referenced_field(field)
            elif is_rollup_that_references_field_type(field, "rollup"):
                result.type = "rollup"
                result.field = get_referenced_field(field)
            elif is_rollup_that_references_field_type(field, "lookup"):
                result.type = "lookup"
                result.field = get_referenced_field(field)
            elif is_rollup_that_references_field_type(field, "multipleLookupValues"):
                result.type = "multipleLookupValues"
                result.field = get_referenced_field(field)
            elif is_rollup_that_references_field_type(field, "multipleRecordLinks"):
                result.type = "multipleRecordLinks"
                result.field = get_referenced_field(field)
            else:
                result.type = get_result_type(field, airtable_type)
        case "lookup" | "multipleLookupValues":
            if is_lookup_that_references_field_type(field, "formula"):
                result.type = "formula"
                result.field = get_referenced_field(field)
            elif is_lookup_that_references_field_type(field, "rollup"):
                result.type = "rollup"
                result.field = get_referenced_field(field)
            elif is_lookup_that_references_field_type(field, "lookup"):
                result.type = "lookup"
                result.field = get_referenced_field(field)
            elif is_lookup_that_references_field_type(field, "multipleLookupValues"):
                result.type = "multipleLookupValues"
                result.field = get_referenced_field(field)
            elif is_lookup_that_references_field_type(field, "multipleRecordLinks"):
                result.type = "multipleRecordLinks"
                result.field = get_referenced_field(field)
            else:
                result.type = get_result_type(field, airtable_type)

    result.types.append(result.type)

    return result


def get_result_type(field: AirTableFieldMetadata, airtable_type: FIELD_TYPE = "") -> FIELD_TYPE:
    if "options" in field and field["options"]:
        if "result" in field["options"] and field["options"]["result"]:
            if "type" in field["options"]["result"]:
                airtable_type = field["options"]["result"]["type"]

    return airtable_type


def warn_unhandled_airtable_type(field: AirTableFieldMetadata, airtable_type: FIELD_TYPE, verbose: bool):
    if is_valid_field(field):
        print(
            "[yellow]Unhandled Airtable type. This results in generic types in the output.[/]",
            "use --verbose for more details" if not verbose else "",
        )
    else:
        print(
            "[yellow]Invalid Airtable field[/]",
            field["id"],
            "[yellow]This results in generic types in the output.[/]",
            "use --verbose for more details" if not verbose else "",
        )
    if verbose:
        table = Table()
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("ID", str(field["id"]))
        table.add_row("Name", str(field["name"]))
        table.add_row("Type", str(field["type"]))
        table.add_row("Interpreted Type", str(airtable_type))
        is_valid = is_valid_field(field)
        color = "green" if is_valid else "red"
        table.add_row("Is Valid", f"[{color}]{is_valid}[/{color}]")
        console = Console()
        console.print(table)
        print("")


def get_referenced_field(field: AirTableFieldMetadata) -> AirTableFieldMetadata | None:
    options = field.get("options", {})
    referenced_field_id = options.get("fieldIdInLinkedTable")
    if referenced_field_id and referenced_field_id in all_fields:
        return all_fields[referenced_field_id]

    return None


def get_referenced_field_from_formula(field: AirTableFieldMetadata, type: FIELD_TYPE) -> AirTableFieldMetadata | None:
    """Check if a formula field references a field of the given type"""

    if field["type"] == "formula":
        if "options" in field and "referencedFieldIds" in field["options"]:
            field_ids = field["options"]["referencedFieldIds"]
            for field_id in field_ids:
                if all_fields[field_id]["type"] == type:
                    return all_fields[field_id]

    return None


def is_lookup_that_references_field_type(field: AirTableFieldMetadata, target_type: FIELD_TYPE) -> bool:
    """Check if a lookup field references a field of the given type."""

    if field["type"] == "lookup" or field["type"] == "multipleLookupValues":
        options = field.get("options", {})
        referenced_field_id = options.get("fieldIdInLinkedTable")
        if referenced_field_id and referenced_field_id in all_fields:
            return all_fields[referenced_field_id]["type"] == target_type

    return False


def is_rollup_that_references_field_type(field: AirTableFieldMetadata, target_type: FIELD_TYPE) -> bool:
    """Check if a rollup field references a field of the given type."""

    if field["type"] == "rollup":
        options = field.get("options", {})
        referenced_field_id = options.get("fieldIdInLinkedTable")
        if referenced_field_id and referenced_field_id in all_fields:
            return all_fields[referenced_field_id]["type"] == target_type

    return False


def is_formula_that_references_field_type(field: AirTableFieldMetadata, type: FIELD_TYPE) -> bool:
    """Check if a formula field references a field of the given type"""

    if field["type"] == "formula":
        if "options" in field and "referencedFieldIds" in field["options"]:
            field_ids = field["options"]["referencedFieldIds"]
            for field_id in field_ids:
                if all_fields[field_id]["type"] == type:
                    return True

    return False


def is_valid_field(field: AirTableFieldMetadata) -> bool:
    """Check if the field is `valid` according to Airtable."""
    if "options" in field and "isValid" in field["options"]:
        return bool(field["options"]["isValid"])
    return True


def is_calculated_field(field: AirTableFieldMetadata) -> bool:
    return field["type"] == "formula" or field["type"] == "rollup" or field["type"] == "lookup" or field["type"] == "multipleLookupValues"


def is_computed_field(field: AirTableFieldMetadata) -> bool:
    return (
        is_calculated_field(field)
        or field["type"] == "createdTime"
        or field["type"] == "lastModifiedTime"
        or field["type"] == "createdBy"
        or field["type"] == "count"
    )


# endregion


# region HELPERS
def get_select_options(field: AirTableFieldMetadata) -> list[str]:
    """Get the options of a select field"""

    airtable_type = field["type"]

    if (
        airtable_type == "singleSelect"
        or airtable_type == "multipleSelects"
        or airtable_type == "singleCollaborator"
        or airtable_type == "multipleLookupValues"
        or airtable_type == "formula"
    ):
        if "options" in field and field["options"]:
            if "choices" in field["options"] and field["options"]["choices"]:
                return [choice["name"] for choice in field["options"]["choices"]]
            elif "result" in field["options"] and field["options"]["result"]:
                if "options" in field["options"]["result"] and field["options"]["result"]["options"]:
                    if "choices" in field["options"]["result"]["options"]:
                        return [choice["name"] for choice in field["options"]["result"]["options"]["choices"]]

    return []


# endregion

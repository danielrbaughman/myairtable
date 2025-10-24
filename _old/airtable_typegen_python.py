from pydantic import BaseModel
from rich import print
from typer import Typer

from src.airtable_meta_types import FIELD_TYPE, AirTableFieldMetadata, AirtableMetadata, TableMetadata

from .airtable_typegen_helpers import (
    DYNAMIC_PATH,
    WriteToPythonFile,
    camel_case,
    get_referenced_field,
    get_result_type,
    get_select_options,
    involves_lookup_field,
    involves_rollup_field,
    is_calculated_field,
    is_computed_field,
    is_valid_field,
    options_name,
    python_property_name,
    sanitize_string,
    upper_case,
    warn_unhandled_airtable_type,
)

cli = Typer()


all_fields: dict[str, AirTableFieldMetadata] = {}
select_options: dict[str, str] = {}
table_id_name_map: dict[str, str] = {}


def gen_python(metadata: AirtableMetadata, base_id: str, verbose: bool = False):
    for table in metadata["tables"]:
        table_id_name_map[table["id"]] = table["name"]
        for field in table["fields"]:
            all_fields[field["id"]] = field
            options = get_select_options(field)
            if len(options) > 0:
                select_options[field["id"]] = f"{options_name(camel_case(table['name']), camel_case(field['name']))}"

    write_types(metadata, verbose)
    write_dicts(metadata, verbose)
    write_orm_models(metadata, base_id, verbose)
    write_pydantic_models(metadata, verbose)
    write_tables(metadata, verbose)
    write_formula_helpers(metadata, verbose)
    write_main_class(metadata, base_id, verbose)
    write_init(metadata, verbose)


# region TYPES
def write_types(metadata: AirtableMetadata, verbose: bool):
    with WriteToPythonFile(path=DYNAMIC_PATH / "types.py") as write:
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
                    write.types(
                        options_name(camel_case(table["name"]), camel_case(sanitize_string(field["name"]))),
                        options,
                        f"Select options for `{sanitize_string(field['name'])}`",
                    )
        write.endregion()

        # Table Types
        for table in metadata["tables"]:
            field_names = [sanitize_string(field["name"]) for field in table["fields"]]
            field_ids = [field["id"] for field in table["fields"]]
            property_names = [python_property_name(field) for field in table["fields"]]

            write.region(upper_case(table["name"]))

            write.types(f"{camel_case(table['name'])}Field", field_names, f"Field names for `{table['name']}`")
            write.types(f"{camel_case(table['name'])}FieldId", field_ids, f"Field IDs for `{table['name']}`")
            write.types(f"{camel_case(table['name'])}FieldProperty", property_names, f"Property names for `{table['name']}`")

            write.str_list(
                f"{camel_case(table['name'])}CalculatedFields",
                [sanitize_string(field["name"]) for field in table["fields"] if is_computed_field(field)],
            )
            write.line(f'"""Calculated fields for `{table["name"]}`"""')
            write.str_list(
                f"{camel_case(table['name'])}CalculatedFieldIds",
                [field["id"] for field in table["fields"] if is_computed_field(field)],
            )
            write.line(f'"""Calculated fields for `{table["name"]}`"""')
            write.line_empty()

            write.dict_class(
                f"{camel_case(table['name'])}FieldNameIdMapping",
                [(sanitize_string(field["name"]), field["id"]) for field in table["fields"]],
                first_type=f"{camel_case(table['name'])}Field",
                second_type=f"{camel_case(table['name'])}FieldId",
            )
            write.dict_class(
                f"{camel_case(table['name'])}FieldIdNameMapping",
                [(field["id"], sanitize_string(field["name"])) for field in table["fields"]],
                first_type=f"{camel_case(table['name'])}FieldId",
                second_type=f"{camel_case(table['name'])}Field",
            )
            write.dict_class(
                f"{camel_case(table['name'])}FieldIdPropertyMapping",
                [(field["id"], python_property_name(field)) for field in table["fields"]],
                first_type=f"{camel_case(table['name'])}FieldId",
                second_type=f"{camel_case(table['name'])}FieldProperty",
            )
            write.dict_class(
                f"{camel_case(table['name'])}FieldPropertyIdMapping",
                [(python_property_name(field), field["id"]) for field in table["fields"]],
                first_type=f"{camel_case(table['name'])}FieldProperty",
                second_type=f"{camel_case(table['name'])}FieldId",
            )

            write.line(f"class {camel_case(table['name'])}FieldsDict(TypedDict, total=False):")
            for field in table["fields"]:
                write.property_row(field["id"], python_type(field, warn=True, verbose=verbose))
            write.line_empty()
            write.line_empty()

            views = table["views"]
            view_names: list[str] = [sanitize_string(view["name"]) for view in views]
            view_ids: list[str] = [view["id"] for view in views]
            write.types(f"{camel_case(table['name'])}View", view_names, f"View names for `{table['name']}`")
            write.types(f"{camel_case(table['name'])}ViewId", view_ids, f"View IDs for `{table['name']}`")
            write.dict_class(
                f"{camel_case(table['name'])}ViewNameIdMapping",
                [(sanitize_string(view["name"]), view["id"]) for view in table["views"]],
                first_type=f"{camel_case(table['name'])}View",
                second_type=f"{camel_case(table['name'])}ViewId",
            )
            write.dict_class(
                f"{camel_case(table['name'])}ViewIdNameMapping",
                [(view["id"], sanitize_string(view["name"])) for view in table["views"]],
                first_type=f"{camel_case(table['name'])}ViewId",
                second_type=f"{camel_case(table['name'])}View",
            )

            write.endregion()

        # Table Lists
        table_names = []
        table_ids = []
        for table in metadata["tables"]:
            table_names.append(table["name"])
            table_ids.append(table["id"])

        write.region("TABLES")
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
            [(table["id"], f"{camel_case(table['name'])}FieldNameIdMapping") for table in metadata["tables"]],
            first_type="TableId",
            second_type="dict[str, str]",
        )
        write.dict_class(
            "TableIdToFieldNamesTypeMapping",
            [(table["id"], f"{camel_case(table['name'])}FieldName") for table in metadata["tables"]],
            first_type="TableId",
        )
        write.dict_class(
            "TableIdToFieldNamesListMapping",
            [(table["id"], f"{camel_case(table['name'])}FieldNames") for table in metadata["tables"]],
            first_type="TableId",
        )
        write.endregion()


# endregion


# region DICTS
def write_dicts(metadata: AirtableMetadata, verbose: bool):
    with WriteToPythonFile(path=DYNAMIC_PATH / "dicts.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("from typing import Any")
        write.line_empty()
        write.line("from pyairtable.api.types import CreateRecordDict, RecordDict, UpdateRecordDict")
        write.line_empty()
        write.line("from .types import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}FieldsDict,")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Field,")
        write.line(")")
        write.endregion()
        write.line_empty()

        # Dicts
        for table in metadata["tables"]:
            write.region(upper_case(table["name"]))
            write.line(f"class {camel_case(table['name'])}CreateRecordDict(CreateRecordDict):")
            write.line_indented(name_record_doc_string(table["name"], id=False, created_time=False))
            write.line_indented(f"fields: dict[{f'{camel_case(table["name"])}Field'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {camel_case(table['name'])}IdsCreateRecordDict(CreateRecordDict):")
            write.line_indented(id_record_doc_string(table["name"], id=False, created_time=False))
            write.line_indented(f"fields: {camel_case(table['name'])}FieldsDict")
            write.line_empty()
            write.line_empty()

            write.line(f"class {camel_case(table['name'])}UpdateRecordDict(UpdateRecordDict):")
            write.line_indented(name_record_doc_string(table["name"], id=True, created_time=False))
            write.line_indented(f"fields: dict[{f'{camel_case(table["name"])}Field'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {camel_case(table['name'])}IdsUpdateRecordDict(UpdateRecordDict):")
            write.line_indented(id_record_doc_string(table["name"], id=True, created_time=False))
            write.line_indented(f"fields: {camel_case(table['name'])}FieldsDict")
            write.line_empty()
            write.line_empty()

            write.line(f"class {camel_case(table['name'])}RecordDict(RecordDict):")
            write.line_indented(name_record_doc_string(table["name"], id=True, created_time=True))
            write.line_indented(f"fields: dict[{f'{camel_case(table["name"])}Field'}, Any]")
            write.line_empty()
            write.line_empty()

            write.line(f"class {camel_case(table['name'])}IdsRecordDict(RecordDict):")
            write.line_indented(id_record_doc_string(table["name"], id=True, created_time=False))
            write.line_indented(f"fields: {camel_case(table['name'])}FieldsDict")
            write.line_empty()
            write.line_empty()

            write.endregion()


# endregion


# region ORM
def write_orm_models(metadata: AirtableMetadata, base_id: str, verbose: bool):
    with WriteToPythonFile(path=DYNAMIC_PATH / "orm_models.py") as write:
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
        write.line("from ..static.helpers import get_api_key")
        write.line("from ..static.special_types import AirtableAttachment, RecordId")
        write.line("from .types import (")
        for table in metadata["tables"]:
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    write.line_indented(f"{options_name(camel_case(table['name']), camel_case(field['name']))},")
        write.line(")")
        write.line("from .dicts import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}RecordDict,")
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
            write.line_indented(f'base_id = "{base_id}"', 2)
            write.line_indented(f'table_name = "{table["name"]}"', 2)
            write.line_indented("use_field_ids = True", 2)
            write.line_indented("memoize = True", 2)
            write.line_empty()

            # to_record_dict
            write.line_indented(f"def to_record_dict(self) -> {camel_case(table['name'])}RecordDict:")
            write.line_indented("return self.to_record()", 2)
            write.line_empty()

            # to_model
            write.line_indented(f"def to_model(self) -> {camel_case(table['name'])}Model:")
            write.line_indented("record_dict = self.to_record()", 2)
            write.line_indented(f"return {camel_case(table['name'])}Model.from_record_dict(record_dict)", 2)
            write.line_empty()

            # _validate
            write.line_indented("def _validate(self) -> None:")
            write.line_indented("self.to_model()", 2)
            write.line_empty()

            # __setattr__
            write.line_indented("def __setattr__(self, name: str, value: Any) -> None:")
            write.line_indented("super().__setattr__(name, value)", 2)
            write.line_indented("if name != 'id':", 2)
            write.line_indented("self._validate()", 3)
            write.line_empty()

            # properties
            for field in table["fields"]:
                write.line_indented(f"{python_property_name(field)}: {pyairtable_orm_type(table['name'], field, verbose)}")
                write.property_docstring(field, table)
            write.line_empty()

            write.endregion()


# endregion


# region MODELS
def write_pydantic_models(metadata: AirtableMetadata, verbose: bool):
    with WriteToPythonFile(path=DYNAMIC_PATH / "models.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("from datetime import datetime, timedelta")
        write.line("from typing import Any, Optional, overload")
        write.line_empty()
        write.line("from ..static.special_types import AirtableAttachment, AirtableButton, AirtableCollaborator, RecordId")
        write.line("from ..static.airtable_base_model import AirtableBaseModel")
        write.line("from .types import (")
        for table in metadata["tables"]:
            for field in table["fields"]:
                options = get_select_options(field)
                if len(options) > 0:
                    write.line_indented(f"{options_name(camel_case(table['name']), camel_case(field['name']))},")
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
                    select_options[field["id"]] = f"{options_name(camel_case(table['name']), camel_case(field['name']))}"

            write.region(upper_case(table["name"]))

            # Properties
            write.line(f"class {camel_case(table['name'])}Model(AirtableBaseModel):")
            for field in table["fields"]:
                write.line_indented(f"{python_property_name(field)}: {pydantic_type(field)}")
                write.property_docstring(field, table)
            write.line_empty()

            # _to_fields
            write.line_indented("def _to_fields(self, use_field_ids: bool) -> dict:")
            write.line_indented("fields: dict = {}", 2)
            write.line_indented("if use_field_ids:", 2)
            for field in table["fields"]:
                write.line_indented(f"if self.{python_property_name(field)} is not None:", 3)
                write.line_indented(f'fields["{field["id"]}"] = self.{python_property_name(field)}', 4)
            write.line_indented("else:", 2)
            for field in table["fields"]:
                write.line_indented(f"if self.{python_property_name(field)} is not None:", 3)
                write.line_indented(f'fields["{sanitize_string(field["name"])}"] = self.{python_property_name(field)}', 4)
            write.line_indented("return fields", 2)
            write.line_empty()

            # _update_from_record_dict
            write.line_indented(
                f"def _update_from_record_dict(self, record: {camel_case(table['name'])}RecordDict | {camel_case(table['name'])}IdsRecordDict):"
            )
            write.line_indented("fields = record.get('fields', {})", 2)
            for field in table["fields"]:
                write.line_indented(
                    f"self.{python_property_name(field)} = fields.get('{field['id']}', None) or fields.get(\"{sanitize_string(field['name'])}\", None)",
                    2,
                )
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

            # from_record_dict
            write.line_indented("@classmethod")
            write.line_indented(f'def from_record_dict(cls, record: {camel_case(table["name"])}RecordDict) -> "{camel_case(table["name"])}Model":')
            write.line_indented("instance = super().from_record_dict(record)", 2)
            write.line_indented("instance._update_from_record_dict(record)", 2)
            write.line_indented("return instance", 2)
            write.line_empty()

            write.endregion()


# endregion


# region TABLES
def write_tables(metadata: AirtableMetadata, verbose: bool):
    with WriteToPythonFile(path=DYNAMIC_PATH / "tables.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("from pyairtable import Table")
        write.line_empty()
        write.line("from ..static.airtable_table import AirtableTable")
        write.line("from .types import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Field,")
            write.line_indented(f"{camel_case(table['name'])}CalculatedFields,")
            write.line_indented(f"{camel_case(table['name'])}CalculatedFieldIds,")
            write.line_indented(f"{camel_case(table['name'])}View,")
            write.line_indented(f"{camel_case(table['name'])}ViewNameIdMapping,")
            write.line_indented(f"{camel_case(table['name'])}Fields,")
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
                f"class {camel_case(table['name'])}Table(AirtableTable[{camel_case(table['name'])}RecordDict, {camel_case(table['name'])}CreateRecordDict, {camel_case(table['name'])}UpdateRecordDict, {camel_case(table['name'])}ORM, {camel_case(table['name'])}Model, {camel_case(table['name'])}View, {camel_case(table['name'])}Field]):"
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
            write.line_indented(f"{camel_case(table['name'])}CalculatedFields,", 3)
            write.line_indented(f"{camel_case(table['name'])}CalculatedFieldIds,", 3)
            write.line_indented(f"{camel_case(table['name'])}ViewNameIdMapping,", 3)
            write.line_indented(f"{camel_case(table['name'])}Fields,", 3)
            write.line_indented(")", 2)
            write.line_indented("return cls", 2)
            write.endregion()
            write.line_empty()


# endregion


# region FORMULA


def write_formula_helpers(metadata: AirtableMetadata, verbose: bool):
    with WriteToPythonFile(path=DYNAMIC_PATH / "formula.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("from .types import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Field,")
            write.line_indented(f"{camel_case(table['name'])}Fields,")
            write.line_indented(f"{camel_case(table['name'])}FieldNameIdMapping,")
        write.line(")")
        write.line("from ..static.helpers import validate_key")
        write.line("from ..static.formula import AttachmentsField, BooleanField, DateField, NumberField, TextField")
        write.line_empty()

        # Class
        for table in metadata["tables"]:
            write.region(upper_case(table["name"]))

            def write_formula(type: str):
                write.line(f"class {camel_case(table['name'])}{type}({type}):")
                write.line_indented(f"def __init__(self, name: {camel_case(table['name'])}Field):")
                write.line_indented(f"validate_key(name, {camel_case(table['name'])}Fields)", 2)
                write.line_indented(f"super().__init__(name=name, name_to_id_map={camel_case(table['name'])}FieldNameIdMapping)", 2)
                write.line_empty()
                write.line_empty()

            write_formula("AttachmentsField")
            write_formula("BooleanField")
            write_formula("DateField")
            write_formula("NumberField")
            write_formula("TextField")

            write.endregion()


# endregion


# region MAIN


def write_main_class(metadata: AirtableMetadata, base_id: str, verbose: bool):
    with WriteToPythonFile(path=DYNAMIC_PATH / "airtable_main.py") as write:
        # Imports
        write.region("IMPORTS")
        write.line("import os")
        write.line_empty()
        write.line("from pyairtable import Api")
        write.line_empty()
        write.line("from .tables import (")
        for table in metadata["tables"]:
            write.line_indented(f"{camel_case(table['name'])}Table,")
        write.line(")")
        write.line("from ..static.helpers import get_api_key")
        write.endregion()
        write.line_empty()
        write.line_empty()

        # Class
        write.region("MAIN CLASS")
        write.line("class Airtable:")
        write.line_indented(main_doc_string())
        for table in metadata["tables"]:
            write.line_indented(f"{python_property_name(table, use_custom=False).lower()}: {camel_case(table['name'])}Table")
        write.line_empty()
        write.line_indented("def __init__(self):")
        write.line_indented("api_key = get_api_key()", 2)
        write.line_indented(f'base_id = "{base_id}"', 2)
        write.line_indented("if not api_key or not base_id:", 2)
        write.line_indented('raise ValueError("API key and Base ID must be provided.")', 3)
        write.line_indented("api = Api(api_key=api_key)", 2)
        for table in metadata["tables"]:
            write.line_indented(
                f'self.{python_property_name(table, use_custom=False).lower()} = {camel_case(table["name"])}Table.from_table(api.table(base_id, "{table["name"]}"))',
                2,
            )
        write.endregion()


def write_init(metadata: AirtableMetadata, verbose: bool):
    with WriteToPythonFile(path=DYNAMIC_PATH / "__init__.py") as write:
        # Imports
        write.line("from .types import *  # noqa: F403")
        write.line("from .dicts import *  # noqa: F403")
        write.line("from .orm_models import *  # noqa: F403")
        write.line("from .models import *  # noqa: F403")
        write.line("from .tables import *  # noqa: F403")
        write.line("from .airtable_main import *  # noqa: F403")
        write.line("from .formula import *  # noqa: F403")


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
    record = Airtable().{python_property_name(table, use_custom=False)}.dict.get("rec1234567890")
    record = Airtable().{python_property_name(table, use_custom=False)}.orm.get("rec1234567890")
    record = Airtable().{python_property_name(table, use_custom=False)}.model.get("rec1234567890")
    ```

    You can also access the ORM tables without `.orm`.

    ```python
    record = Airtable().{python_property_name(table, use_custom=False)}.get("rec1234567890")
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
            referenced_field = get_referenced_field(field, all_fields)
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
        if involves_lookup_field(field, all_fields) or involves_rollup_field(field, all_fields):
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
                print(table_name, original_id, sanitize_string(field["name"]), "[yellow]does not have a linkedTableId[/]")
        case _:
            if not is_valid_field(field):
                orm_type = "Any"

    if orm_type == "Any" and warn:
        warn_unhandled_airtable_type(field, airtable_type, verbose)

    return orm_type


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


# endregion


# region HELPERS


# endregion

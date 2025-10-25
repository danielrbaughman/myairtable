from datetime import datetime
from typing import Any, TypeVar

from pyairtable.api.types import CreateRecordDict, RecordDict, UpdateRecordDict
from pyairtable.orm import Model

from .airtable_base_model import AirtableBaseModel

DictType = TypeVar("DictType", bound=RecordDict)
UpdateDictType = TypeVar("UpdateDictType", bound=UpdateRecordDict)
CreateDictType = TypeVar("CreateDictType", bound=CreateRecordDict)
ORMType = TypeVar("ORMType", bound=Model)
PydanticType = TypeVar("PydanticType", bound=AirtableBaseModel)
ViewType = TypeVar("ViewType", bound=str)
FieldType = TypeVar("FieldType", bound=str)


def sanitize_record_dict(record: DictType) -> DictType:
    """Handle `specialValue` and `error responses."""

    def _sanitize(record: DictType, field_key: str, field_value: Any):
        if "specialValue" in field_value:
            special_value = field_value["specialValue"]
            if special_value in ["NaN", "Infinity"]:
                special_value = None
            record["fields"][field_key] = special_value
        elif "error" in field_value:
            error_value = field_value["error"]
            if error_value in ["#ERROR!", "#ERROR"]:
                error_value = None
            record["fields"][field_key] = error_value

    for field_key in record["fields"]:
        field_value = record["fields"][field_key]
        if isinstance(field_value, dict):
            _sanitize(record, field_key, field_value)
        if isinstance(field_value, list) and len(field_value) > 0 and isinstance(field_value[0], dict):
            for value in field_value:
                _sanitize(record, field_key, value)
    return record


def remove_calculated_fields(fields: dict, calculated_fields: list[str]) -> dict:
    """Remove calculated fields. Needed for creating/updating records."""
    return {k: v for k, v in fields.items() if k not in calculated_fields}


def convert_datetime_fields_to_str(fields: dict) -> dict:
    """Convert datetime fields to string representation. pyAirtable doesn't like datetime objects."""
    return {k: v.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if isinstance(v, datetime) else v for k, v in fields.items()}


def prepare_fields_for_save(fields: dict, calculated_fields: list[str]) -> dict:
    """Prepare fields for sending to Airtable."""
    fields = remove_calculated_fields(fields, calculated_fields)
    fields = convert_datetime_fields_to_str(fields)
    return fields

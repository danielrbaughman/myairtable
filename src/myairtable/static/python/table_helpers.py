from collections.abc import Sequence
from datetime import datetime
from typing import Any, Generic, Literal, Optional, TypedDict, TypeVar

from pyairtable.api.types import CreateRecordDict, RecordDict, UpdateRecordDict
from pyairtable.orm import Model

DictType = TypeVar("DictType", bound=RecordDict)
UpdateDictType = TypeVar("UpdateDictType", bound=UpdateRecordDict)
CreateDictType = TypeVar("CreateDictType", bound=CreateRecordDict)
ORMType = TypeVar("ORMType", bound=Model)
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


def remove_calculated_fields(fields: dict, calculated_fields: Sequence[str]) -> dict:
    """Remove calculated fields. Needed for creating/updating records."""
    return {k: v for k, v in fields.items() if k not in calculated_fields}


def convert_datetime_fields_to_str(fields: dict) -> dict:
    """Convert datetime fields to string representation. pyAirtable doesn't like datetime objects."""
    return {k: v.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if isinstance(v, datetime) else v for k, v in fields.items()}


def project_attachments_for_create(fields: dict) -> dict:
    """Reduce attachment cells to the only shape Airtable accepts when inserting.

    Airtable returns attachments carrying read-only metadata (``id``, ``size``, ``type``,
    ``width``, ``height``, ``thumbnails``). On **create** it accepts only ``{"url": ...}``
    (optionally with ``"filename"``) — sending an ``id``, alone or echoed alongside ``url``,
    fails with ``INVALID_ATTACHMENT_OBJECT``. Airtable re-ingests the file and mints a fresh
    attachment id, which is what makes a duplicated record's attachment independent of its
    source rather than an alias.

    Create-only: on **update** an ``id`` is legal and means "retain this attachment", so this
    must not be applied to the update path or existing attachments churn on every save.

    Attachment cells are recognised by shape rather than by field id, because the raw dict
    layer may be keyed by either field id or field name depending on ``use_field_ids``. The
    shape is unambiguous: no other Airtable cell type is a list of mappings carrying a ``url``
    alongside an ``att``-prefixed id. A cell the caller already built as ``{"url": ...}`` has
    no id and is passed through unchanged, which is exactly the shape create wants anyway.

    Returns a new dict; the caller's fields are never mutated.
    """

    def _is_attachment_cell(value: Any) -> bool:
        return (
            isinstance(value, list)
            and bool(value)
            and all(isinstance(v, dict) and "url" in v and str(v.get("id", "")).startswith("att") for v in value)
        )

    projected_fields = dict(fields)
    for field_key, value in fields.items():
        if not _is_attachment_cell(value):
            continue
        projected: list[dict] = []
        for attachment in value:
            item: dict[str, Any] = {"url": attachment["url"]}
            if attachment.get("filename"):
                item["filename"] = attachment["filename"]
            projected.append(item)
        projected_fields[field_key] = projected
    return projected_fields


def prepare_fields_for_save(fields: dict, calculated_fields: Sequence[str]) -> dict:
    """Prepare fields for sending to Airtable."""
    fields = remove_calculated_fields(fields, calculated_fields)
    fields = convert_datetime_fields_to_str(fields)
    return fields


class SortOption(TypedDict, Generic[FieldType]):
    field: FieldType
    direction: Optional[Literal["asc", "desc"]]


def convert_sort_options(sort: "list[SortOption] | None") -> list[str]:
    """Convert SortOption dicts to pyairtable's expected string format."""
    if sort is None:
        return []
    result = []
    for option in sort:
        field = option["field"]
        direction = option.get("direction")
        if direction == "desc":
            result.append(f"-{field}")
        else:
            result.append(field)
    return result

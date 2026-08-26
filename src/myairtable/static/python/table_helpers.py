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


# Attributes the generator emits onto a model that a copy should inherit when -- and only
# when -- the source set them per instance. `evaluate_formulas_at_runtime` is currently the
# only one; it is a behaviour toggle, so a copy that ignored it would not read like its source.
_GENERATED_INSTANCE_ATTRS = ("evaluate_formulas_at_runtime",)


def _detach_containers(value: Any) -> Any:
    """Rebuild every list/dict so a copy shares no mutable state with its source.

    Deliberately not ``copy.deepcopy``: a list read off a model is a
    ``ChangeTrackingList``, which holds a ``_model`` back-reference to the record it
    came from (pyairtable ``orm/lists.py``). Deep-copying one would drag the entire
    source model in with it; aliasing one is worse still, because its ``_on_change``
    writes to ``self._model._changed`` — so mutating the *copy's* list would mark the
    *source* dirty. Rebuilding as plain containers drops the binding entirely; the
    descriptor re-wraps them against the new instance on first read.

    Scalars are returned as-is: everything reaching here has been through
    ``to_record()``, so the leaves are immutable (str/int/float/bool/None).
    """
    if isinstance(value, dict):
        return {key: _detach_containers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_detach_containers(item) for item in value]
    return value


def copy_model(record: ORMType) -> ORMType:
    """Return a detached, unsaved deep copy of an ORM record.

    The copy carries every field value — computed ones included, so it reads like its
    source — but none of the record's identity, so ``create()`` inserts it as a new
    record instead of updating the original. Mutate it and hand it to ``create()``.

    Performs no I/O. That is the whole difference from ``duplicate()``, which re-reads
    the source from Airtable first; a copy is therefore only as fresh as the model in
    hand, which matters most for attachments (their signed URLs expire).

    Detaching is what makes this safe, and pyairtable's class defaults do most of it:
    a bare ``type(record)()`` starts with ``id = ""``, ``created_time = None``,
    ``_deleted = False``, ``_fetched = False`` and a fresh ``_changed`` dict. The id is
    the load-bearing one — ``Model.save()`` branches on it (``if not self.id:``), so a
    copy that kept the source's id would PATCH the source rather than insert. Building
    the instance directly also keeps it out of the memoization cache, which
    ``from_record()`` would otherwise populate (generated models set ``memoize = True``).

    Values round-trip through ``to_record()`` rather than being read off the
    descriptors: descriptor reads on a link field call ``populate()``, which hits the
    network, whereas ``to_record()`` walks ``_fields`` directly and resolves links to
    plain record ids.

    Attachments are projected to ``{url, filename}`` because Airtable rejects
    server-returned attachment objects on create, and copying by URL is what makes the
    created record own an independent attachment rather than aliasing the source's.
    Only writable cells are projected — a computed lookup can hold the same shape, and
    stripping metadata from a read-only cell would lose fidelity for no benefit, since
    it is never written back.
    """
    model_cls = type(record)
    descriptors = model_cls._field_name_descriptor_map()

    fields = _detach_containers(record.to_record()["fields"])
    writable = {key: value for key, value in fields.items() if key in descriptors and not descriptors[key].readonly}
    fields.update(project_attachments_for_create(writable))

    copied = model_cls()
    # Assign _fields directly: the public descriptors refuse to set a read-only field,
    # which is exactly what carrying computed values requires. from_record() does the
    # same thing for the same reason.
    copied._fields = {
        key: (descriptors[key].to_internal_value(value) if value is not None else None) for key, value in fields.items() if key in descriptors
    }

    # Carry generated per-instance attributes, but only where the source actually set one
    # on the instance: reading it off the class would pin the class default onto the copy
    # as an instance attribute, which then stops tracking later changes to the class.
    # Copied through __dict__ because these are emitted onto the concrete generated model,
    # not declared on pyairtable's Model base, so ORMType does not know about them.
    for attr in _GENERATED_INSTANCE_ATTRS:
        if attr in record.__dict__:
            copied.__dict__[attr] = record.__dict__[attr]

    return copied


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

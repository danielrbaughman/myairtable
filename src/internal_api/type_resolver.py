"""Resolve computed-field result types from the internal application/read schema.

The public meta API often reports a formula/lookup/rollup result type as
`singleLineText` or leaves it ambiguous; the internal schema carries an
authoritative `typeOptions.resultType` for ~98% of computed fields (100% of the
public-ambiguous population — see docs/airtable-internal-api.md, "computed-field
type resolution"). This module normalizes that internal info into the public
`FieldType` vocabulary so the generators can emit precise types.

Output is a map {field_id -> {result_type, is_array, source}}, persisted to a
type-map file (myairtable-v9v5) so CI codegen stays PAT-only.

Findings baked in here:
- Lookups are internally typed "lookup" (NOT the public "multipleLookupValues").
- resultType vocabulary is coarse (text/number/date/checkbox) + resultIsArray;
  typeOptions refinements recover currency/percent (format) and dateTime
  (isDateTime), so no regression vs finer public inference.
- The validator fallback (getUnsavedColumnConfigResultType) is a POST needing
  the deferred write transport — not used here; schema coverage is enough.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.meta_types import FieldType

from .errors import InternalApiError
from .tools import raw_application_read

# Persisted type-map file (lives alongside the codegen CSVs). Generated locally
# with an internal session; consumed by CI codegen, which stays PAT-only.
TYPE_MAP_FILENAME = "type_map.json"

# Internal container types that carry a resolved typeOptions.resultType.
_COMPUTED_CONTAINERS = {"formula", "rollup", "count", "lookup"}

# Internal resultType -> public FieldType. The internal vocabulary uses its own
# names (phone/select/foreignKey/...) distinct from the public FieldType names.
# `number` and `date` are handled specially (format / isDateTime). Verified
# live; add entries as new resultType values are observed.
_RESULT_TYPE_MAP: dict[str, FieldType] = {
    "text": "singleLineText",  # internal "text" doesn't split single/multi-line; both map to str
    "multilineText": "multilineText",
    "richText": "richText",
    "checkbox": "checkbox",
    "select": "singleSelect",
    "multiSelect": "multipleSelects",
    "phone": "phoneNumber",
    "email": "email",
    "url": "url",
    "rating": "rating",
    "barcode": "barcode",
    "foreignKey": "multipleRecordLinks",  # a lookup returning linked records
    "multipleAttachment": "multipleAttachments",
}

# typeOptions.format -> public FieldType (only for resultType "number").
_NUMBER_FORMATS: dict[str, FieldType] = {
    "currency": "currency",
    "percentV2": "percent",
    "percent": "percent",
    "duration": "duration",
}


def normalize_result_type(type_options: dict[str, Any]) -> tuple[FieldType, bool] | None:
    """Map a computed column's typeOptions to (public FieldType, is_array).

    Returns None when there is no resolved resultType, or when the internal
    resultType isn't recognized — in that case the field keeps its existing
    public-API inference (no regression, no invalid type emitted).
    """
    result_type = type_options.get("resultType")
    if not result_type:
        return None
    is_array = bool(type_options.get("resultIsArray"))

    resolved: FieldType
    if result_type == "number":
        resolved = _NUMBER_FORMATS.get(type_options.get("format", ""), "number")
    elif result_type == "date":
        resolved = "dateTime" if type_options.get("isDateTime") else "date"
    elif result_type in _RESULT_TYPE_MAP:
        resolved = _RESULT_TYPE_MAP[result_type]
    else:
        return None  # unrecognized internal type — fall back to existing inference
    return resolved, is_array


def resolve_field_types() -> dict[str, dict[str, Any]]:
    """{field_id -> {result_type, is_array, source}} for every computed field
    the internal schema resolves. Requires an internal session."""
    payload = raw_application_read()
    table_schemas = (payload.get("data") or {}).get("tableSchemas")
    if not isinstance(table_schemas, list):
        raise InternalApiError("application/read response has no data.tableSchemas list.")

    resolved: dict[str, dict[str, Any]] = {}
    for table in table_schemas:
        for column in table.get("columns", []):
            if column.get("type") not in _COMPUTED_CONTAINERS:
                continue
            norm = normalize_result_type(column.get("typeOptions") or {})
            if norm is None:
                continue
            result_type, is_array = norm
            resolved[column["id"]] = {"result_type": result_type, "is_array": is_array, "source": "internal_schema"}
    return resolved


def write_type_map(folder: Path) -> Path:
    """Resolve computed-field types and persist a type-map JSON into `folder`.

    Local-only (needs an internal session). Returns the written file path.
    """
    from src.meta import get_base_id

    payload = {
        "base_id": get_base_id(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fields": resolve_field_types(),
    }
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / TYPE_MAP_FILENAME
    dest.write_text(json.dumps(payload, indent=2))
    return dest


def load_type_map(folder_or_file: Path) -> dict[str, dict[str, Any]]:
    """Load the persisted {field_id -> resolved-type} map; {} if absent.

    Accepts the codegen folder or a direct path to the JSON file. PAT-only —
    reads the file, no internal session.
    """
    path = folder_or_file / TYPE_MAP_FILENAME if folder_or_file.is_dir() else folder_or_file
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    fields = data.get("fields")
    return fields if isinstance(fields, dict) else {}

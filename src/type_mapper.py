"""
Unified type mapping module for Python and TypeScript code generation.

This module is the single source of truth for all type mapping logic,
including disambiguation of calculated field types via Airtable API.
"""

import os
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

import pyairtable
from rich import print
from rich.progress import track

from .meta import Base, Field
from .meta_types import FieldType


# =============================================================================
# region GENERIC TYPES
# =============================================================================
class GenericType(Enum):
    """Language-independent type representation for Airtable field types."""

    # Primitive types
    STRING = auto()
    INTEGER = auto()
    FLOAT = auto()
    BOOLEAN = auto()

    # Date/Time types
    DATETIME = auto()
    DURATION = auto()

    # Airtable-specific types
    RECORD_ID = auto()
    ATTACHMENT = auto()
    COLLABORATOR = auto()
    BUTTON = auto()

    # Container types
    LIST_OF_RECORD_IDS = auto()
    LIST_OF_ATTACHMENTS = auto()

    # Select types (require options_name metadata)
    SINGLE_SELECT = auto()
    MULTIPLE_SELECT = auto()

    # Fallback
    ANY = auto()


@dataclass
class ResolvedType:
    """A resolved type with optional metadata for select fields and list wrapping."""

    generic_type: GenericType
    options_name: str | None = None  # For select fields
    is_list: bool = False  # For analyzed list values


# endregion

# =============================================================================
# region MAPS
# =============================================================================

# Canonical mapping from Airtable types to GenericType (single source of truth)
AIRTABLE_TO_GENERIC: dict[str, GenericType] = {
    # Text types -> STRING
    "singleLineText": GenericType.STRING,
    "multilineText": GenericType.STRING,
    "url": GenericType.STRING,
    "richText": GenericType.STRING,
    "email": GenericType.STRING,
    "phoneNumber": GenericType.STRING,
    "barcode": GenericType.STRING,
    # Boolean
    "checkbox": GenericType.BOOLEAN,
    # Date/Time
    "date": GenericType.DATETIME,
    "dateTime": GenericType.DATETIME,
    "createdTime": GenericType.DATETIME,
    "lastModifiedTime": GenericType.DATETIME,
    # Integer types
    "count": GenericType.INTEGER,
    "autoNumber": GenericType.INTEGER,
    # Float types
    "percent": GenericType.FLOAT,
    "currency": GenericType.FLOAT,
    # Duration (special: timedelta in Python, number in TS)
    "duration": GenericType.DURATION,
    # Airtable complex types
    "multipleRecordLinks": GenericType.LIST_OF_RECORD_IDS,
    "multipleAttachments": GenericType.LIST_OF_ATTACHMENTS,
    "singleCollaborator": GenericType.COLLABORATOR,
    "lastModifiedBy": GenericType.COLLABORATOR,
    "createdBy": GenericType.COLLABORATOR,
    "button": GenericType.BUTTON,
}

# Python type renderer
GENERIC_TO_PYTHON: dict[GenericType, str] = {
    GenericType.STRING: "str",
    GenericType.INTEGER: "int",
    GenericType.FLOAT: "float",
    GenericType.BOOLEAN: "bool",
    GenericType.DATETIME: "datetime",
    GenericType.DURATION: "timedelta",
    GenericType.RECORD_ID: "RecordId",
    GenericType.ATTACHMENT: "AirtableAttachment",
    GenericType.COLLABORATOR: "AirtableCollaborator",
    GenericType.BUTTON: "AirtableButton",
    GenericType.LIST_OF_RECORD_IDS: "list[RecordId]",
    GenericType.LIST_OF_ATTACHMENTS: "list[AirtableAttachment]",
    GenericType.ANY: "Any",
}

# TypeScript type renderer
GENERIC_TO_TYPESCRIPT: dict[GenericType, str] = {
    GenericType.STRING: "string",
    GenericType.INTEGER: "number",
    GenericType.FLOAT: "number",
    GenericType.BOOLEAN: "boolean",
    GenericType.DATETIME: "string",  # ISO date strings
    GenericType.DURATION: "number",  # Milliseconds
    GenericType.RECORD_ID: "RecordId",
    GenericType.ATTACHMENT: "Attachment",
    GenericType.COLLABORATOR: "Collaborator",
    GenericType.BUTTON: "string",
    GenericType.LIST_OF_RECORD_IDS: "RecordId[]",
    GenericType.LIST_OF_ATTACHMENTS: "Attachment[]",
    GenericType.ANY: "any",
}

# endregion


def python_type_matches_generic(saved: str, generic_type: GenericType | None) -> bool:
    """Check if a saved Python type string matches the expected generic type."""
    if generic_type is None:
        return False

    # Extract base type from saved (strip list[...] wrapper if present)
    if saved.startswith("list[") and saved.endswith("]"):
        saved_base = saved[5:-1]
    else:
        saved_base = saved

    # Get expected base type from generic type
    expected_base = GENERIC_TO_PYTHON.get(generic_type, "Any")

    return saved_base == expected_base


# =============================================================================
# region PRE-CALC
# =============================================================================


def calculate_types(base: Base) -> None:
    """Calculate and store Python and TypeScript types for all fields. Idempotent."""
    print("Determining field types")

    if base.tables and base.tables[0].fields:
        first_field = base.tables[0].fields[0]
        if first_field._python_type is not None and first_field._typescript_type is not None:
            return  # Already calculated

    # First pass: calculate all types and identify fields needing disambiguation
    fields_to_disambiguate: list[Field] = []
    for table in base.tables:
        for field in table.fields:
            # Calculate generic type once
            resolved = calculate_generic_type(field)

            # Render both types from the same generic type
            py_type = render_python_type(resolved, field)
            ts_type = render_typescript_type(resolved, field)

            field._python_type = py_type
            field._typescript_type = ts_type

            # Handle disambiguation for union types (list vs single value)
            if "|" in py_type and field.is_valid():
                csv_python_type = field.csv_python_type()
                if csv_python_type and python_type_matches_generic(csv_python_type, field._generic_type):
                    # CSV has valid disambiguated type - use it directly
                    is_list = csv_python_type.startswith("list[")
                    field._python_type = render_disambiguated_type(field._generic_type, is_list, "python")
                    field._typescript_type = render_disambiguated_type(field._generic_type, is_list, "typescript")
                else:
                    # Need to disambiguate via API (no saved type, or base type changed)
                    fields_to_disambiguate.append(field)
    print("[dim] - Determined types[/]")

    # Second pass: disambiguate fields that need it (handles both languages)
    if fields_to_disambiguate:
        disambiguate_fields_batch(fields_to_disambiguate)
        print("[dim] - Disambiguated calculated field types[/]")

    print("")


# endregion

# =============================================================================
# region TYPE CALC
# =============================================================================


def calculate_generic_type(field: Field) -> ResolvedType:
    """Calculate the generic type for a field (language-independent). Caches result on field._generic_type."""
    # Use cached generic type if available
    if field._generic_type is not None:
        # Reconstruct ResolvedType from cached GenericType
        if field._generic_type in (GenericType.SINGLE_SELECT, GenericType.MULTIPLE_SELECT):
            options_name = get_select_options_name(field)
            return ResolvedType(generic_type=field._generic_type, options_name=options_name)
        return ResolvedType(generic_type=field._generic_type)

    airtable_type: FieldType = field.type

    # For calculated fields, use the result type
    if field.is_calculated():
        airtable_type = field.result_type()

    # Simple type lookup
    if airtable_type in AIRTABLE_TO_GENERIC:
        resolved = ResolvedType(generic_type=AIRTABLE_TO_GENERIC[airtable_type])
        field._generic_type = resolved.generic_type
        return resolved

    # Handle number field (int vs float based on precision)
    if airtable_type == "number":
        if field.options and field.options.precision is not None and field.options.precision == 0:
            resolved = ResolvedType(generic_type=GenericType.INTEGER)
        else:
            resolved = ResolvedType(generic_type=GenericType.FLOAT)
        field._generic_type = resolved.generic_type
        return resolved

    # Handle select fields (shared logic for single and multiple)
    if airtable_type == "singleSelect":
        options_name = get_select_options_name(field)
        if options_name:
            resolved = ResolvedType(generic_type=GenericType.SINGLE_SELECT, options_name=options_name)
        else:
            resolved = ResolvedType(generic_type=GenericType.ANY)
        field._generic_type = resolved.generic_type
        return resolved

    if airtable_type == "multipleSelects":
        options_name = get_select_options_name(field)
        if options_name:
            resolved = ResolvedType(generic_type=GenericType.MULTIPLE_SELECT, options_name=options_name)
        else:
            resolved = ResolvedType(generic_type=GenericType.ANY)
        field._generic_type = resolved.generic_type
        return resolved

    resolved = ResolvedType(generic_type=GenericType.ANY)
    field._generic_type = resolved.generic_type
    return resolved


def get_select_options_name(field: Field) -> str | None:
    """Extract the options name for a select field (shared logic for single/multiple)."""
    select_fields_ids = field.base.select_fields_ids()

    # Direct select field
    if field.id in select_fields_ids:
        return field.options_name()

    # Check if referencing a select field in linked table
    referenced_field = field.field_in_linked_table()
    if referenced_field and referenced_field.type == "singleSelect":
        if referenced_field.id in select_fields_ids:
            return referenced_field.options_name()

    return None


def render_python_type(resolved: ResolvedType, field: Field) -> str:
    """Render a ResolvedType to Python syntax."""
    # Handle select types with their options_name
    if resolved.generic_type == GenericType.SINGLE_SELECT:
        base_type = resolved.options_name or "Any"
    elif resolved.generic_type == GenericType.MULTIPLE_SELECT:
        base_type = f"list[{resolved.options_name}]" if resolved.options_name else "Any"
    else:
        base_type = GENERIC_TO_PYTHON.get(resolved.generic_type, "Any")

    # Apply lookup/rollup wrapper if needed (only for non-list types)
    if "list" not in base_type:
        if field.involves_lookup() or field.involves_rollup():
            return f"list[{base_type} | None] | {base_type}"

    return base_type


def render_typescript_type(resolved: ResolvedType, field: Field) -> str:
    """Render a ResolvedType to TypeScript syntax."""
    # Handle select types with their options_name
    if resolved.generic_type == GenericType.SINGLE_SELECT:
        base_type = resolved.options_name or "any"
    elif resolved.generic_type == GenericType.MULTIPLE_SELECT:
        base_type = f"{resolved.options_name}[]" if resolved.options_name else "any"
    else:
        base_type = GENERIC_TO_TYPESCRIPT.get(resolved.generic_type, "any")

    # Apply lookup/rollup wrapper if needed (only for non-array types)
    if not base_type.endswith("[]"):
        if field.involves_lookup() or field.involves_rollup():
            return f"{base_type} | {base_type}[]"

    return base_type


def calculate_python_type(field: Field) -> str:
    """Calculate the raw Python type for a field (without disambiguation)."""
    # Return cached result if available
    if field._python_type_cache is not None:
        return field._python_type_cache

    resolved = calculate_generic_type(field)
    py_type = render_python_type(resolved, field)

    field._python_type_cache = py_type
    return py_type


def calculate_typescript_type(field: Field) -> str:
    """Calculate the raw TypeScript type for a field (without disambiguation)."""
    # Return cached result if available
    if field._typescript_type_cache is not None:
        return field._typescript_type_cache

    resolved = calculate_generic_type(field)
    ts_type = render_typescript_type(resolved, field)

    # Handle invalid fields
    if not field.is_valid() and ts_type == "any":
        pass  # Already "any", no change needed

    field._typescript_type_cache = ts_type
    return ts_type


# endregion

# =============================================================================
# region DISAMBIGUATION
# =============================================================================


def disambiguate_fields_batch(fields: list[Field]) -> None:
    """Disambiguate multiple fields efficiently by batching API calls per table."""
    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        return

    # Group fields by table
    fields_by_table: dict[str, list[Field]] = {}
    for field in fields:
        table_id = field.table.id
        if table_id not in fields_by_table:
            fields_by_table[table_id] = []
        fields_by_table[table_id].append(field)

    # Process each table
    for table_id, table_fields in track(fields_by_table.items(), description="Disambiguating calculated field types...", transient=True):
        disambiguate_table_fields(api_key, table_fields)


def disambiguate_table_fields(api_key: str, fields: list[Field]) -> None:
    """Disambiguate all fields from a single table with minimal API calls."""
    if not fields:
        return

    # All fields are from the same table
    sample_field = fields[0]
    base_id = sample_field.base.id
    table_id = sample_field.table.id
    field_ids = [f.id for f in fields]

    try:
        table = pyairtable.Table(api_key, base_id, table_id)

        # Fetch multiple records to increase chance of finding non-blank values
        records = table.all(fields=field_ids, max_records=20, use_field_ids=True)

        if not records:
            return

        # For each field, find the first non-blank value across all records
        for field in fields:
            value = find_non_blank_value(records, field.id)
            if value is not None:
                # Only determine if it's a list - preserve the original generic type
                is_list = isinstance(value, list)

                # Render disambiguated types using the original generic type
                field._python_type = render_disambiguated_type(field._generic_type, is_list, "python")
                field._typescript_type = render_disambiguated_type(field._generic_type, is_list, "typescript")

    except Exception:
        print(f"[red] - Error disambiguating fields for table {table_id}.[/]")


def find_non_blank_value(records: list[dict], field_id: str) -> Any:
    """Find the first non-blank value for a field across multiple records."""
    for record in records:
        value = record.get("fields", {}).get(field_id)
        if value is not None:
            # For lists, ensure it's not empty and not all None
            if isinstance(value, list):
                if value and any(v is not None for v in value):
                    return value
            else:
                return value
    return None


def render_disambiguated_type(generic_type: GenericType | None, is_list: bool, language: str) -> str:
    """Render a disambiguated type (with known is_list) to the target language."""
    if generic_type is None:
        return "Any" if language == "python" else "any"

    match language:
        case "python":
            renderer = GENERIC_TO_PYTHON
            fallback = "Any"
        case "typescript":
            renderer = GENERIC_TO_TYPESCRIPT
            fallback = "any"
        case _:
            return "Any" if language == "python" else "any"

    base_type = renderer.get(generic_type, fallback)

    if is_list:
        if language == "python":
            return f"list[{base_type}]"
        else:
            return f"{base_type}[]"

    return base_type

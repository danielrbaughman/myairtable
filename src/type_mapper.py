"""
Unified type mapping module for Python and TypeScript code generation.

This module is the single source of truth for all type mapping logic,
including disambiguation of calculated field types via Airtable API.
"""

import os
from pathlib import Path
from typing import Any

import pyairtable
from rich import print
from rich.progress import track

from .helpers import sanitize_string
from .meta import Base, Field, FieldType

# =============================================================================
# TYPE MAPPING DICTIONARIES
# =============================================================================

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

SIMPLE_TYPESCRIPT_TYPES: dict[str, str] = {
    "singleLineText": "string",
    "multilineText": "string",
    "url": "string",
    "richText": "string",
    "email": "string",
    "phoneNumber": "string",
    "barcode": "string",
    "checkbox": "boolean",
    "date": "string",
    "dateTime": "string",
    "createdTime": "string",
    "lastModifiedTime": "string",
    "count": "number",
    "autoNumber": "number",
    "percent": "number",
    "currency": "number",
    "number": "number",
    "duration": "number",
    "multipleRecordLinks": "RecordId[]",
    "multipleAttachments": "Attachment[]",
    "singleCollaborator": "Collaborator",
    "lastModifiedBy": "Collaborator",
    "createdBy": "Collaborator",
    "button": "string",
}

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


# =============================================================================
# MAIN API FUNCTIONS
# =============================================================================


def python_type(field: Field) -> str:
    """Returns the Python type for a field. Must call calculate_all_python_types() first."""
    if field._python_type:
        return field._python_type
    # Fallback for fields not pre-calculated
    return _calculate_python_type(field)


def typescript_type(field: Field) -> str:
    """Returns the TypeScript type for a field. Must call calculate_all_typescript_types() first."""
    if field._typescript_type:
        return field._typescript_type
    # Fallback for fields not pre-calculated
    return _calculate_typescript_type(field)


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


# =============================================================================
# PRE-CALCULATION FUNCTIONS
# =============================================================================


def calculate_all_python_types(base: Base) -> None:
    """Calculate and store Python types for all fields upfront."""
    # First pass: calculate all types and identify fields needing disambiguation
    fields_to_disambiguate: list[Field] = []
    for table in base.tables:
        for field in table.fields:
            py_type = _calculate_python_type(field)
            field._python_type = py_type

            # Check if disambiguation is needed
            if "|" in py_type and field.is_valid():
                if field.saved_python_type() not in py_type or "|" in field.saved_python_type():
                    fields_to_disambiguate.append(field)

    # Second pass: disambiguate fields that need it
    if fields_to_disambiguate:
        _disambiguate_fields_batch(fields_to_disambiguate, language="python")


def calculate_all_typescript_types(base: Base) -> None:
    """Calculate and store TypeScript types for all fields upfront."""
    # First pass: calculate all types and identify fields needing disambiguation
    fields_to_disambiguate: list[Field] = []
    for table in base.tables:
        for field in table.fields:
            ts_type = _calculate_typescript_type(field)
            field._typescript_type = ts_type

            # Check if disambiguation is needed (contains | but not [])
            if "|" in ts_type and field.is_valid():
                if field.saved_typescript_type() not in ts_type or "|" in field.saved_typescript_type():
                    fields_to_disambiguate.append(field)

    # Second pass: disambiguate fields that need it
    if fields_to_disambiguate:
        _disambiguate_fields_batch(fields_to_disambiguate, language="typescript")


# =============================================================================
# INTERNAL CALCULATION FUNCTIONS
# =============================================================================


def _calculate_python_type(field: Field) -> str:
    """Calculate the raw Python type for a field (without disambiguation)."""
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
        referenced_field = field.field_in_linked_table()
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

    # In the case of some calculated fields, sometimes the result is just too unpredictable.
    # We'll need to disambiguate these later with real data.
    if "list" not in py_type:
        if field.involves_lookup() or field.involves_rollup():
            py_type = f"list[{py_type} | None] | {py_type}"

    field._python_type_cache = py_type

    return py_type


def _calculate_typescript_type(field: Field) -> str:
    """Calculate the raw TypeScript type for a field (without disambiguation)."""
    # Return cached result if available
    if field._typescript_type_cache is not None:
        return field._typescript_type_cache

    airtable_type: FieldType = field.type
    ts_type: str = "any"

    # With calculated fields, we want to know the type of the result
    if field.is_calculated():
        airtable_type = field.result_type()

    # Handle simple type mappings via lookup
    if airtable_type in SIMPLE_TYPESCRIPT_TYPES:
        ts_type = SIMPLE_TYPESCRIPT_TYPES[airtable_type]

    # Handle complex types with special logic
    elif airtable_type == "singleSelect":
        referenced_field = field.field_in_linked_table()
        select_fields_ids = field.base.select_fields_ids()
        if field.id in select_fields_ids:
            ts_type = field.options_name()
        elif referenced_field and referenced_field.type == "singleSelect" and referenced_field.id in select_fields_ids:
            ts_type = referenced_field.options_name()
        else:
            ts_type = "any"
    elif airtable_type == "multipleSelects":
        select_fields_ids = field.base.select_fields_ids()
        if field.id in select_fields_ids:
            ts_type = f"{field.options_name()}[]"
        else:
            ts_type = "any"
    elif not field.is_valid():
        ts_type = "any"

    # In the case of some calculated fields, sometimes the result is just too unpredictable.
    # We'll need to disambiguate these later with real data.
    if not ts_type.endswith("[]"):
        if field.involves_lookup() or field.involves_rollup():
            ts_type = f"{ts_type} | {ts_type}[]"

    field._typescript_type_cache = ts_type
    return ts_type


# =============================================================================
# DISAMBIGUATION FUNCTIONS
# =============================================================================


def _disambiguate_fields_batch(fields: list[Field], language: str) -> None:
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
        _disambiguate_table_fields(api_key, table_fields, language)


def _disambiguate_table_fields(api_key: str, fields: list[Field], language: str) -> None:
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
            value = _find_non_blank_value(records, field.id)
            if value is not None:
                if language == "python":
                    new_type = _analyze_python_type(value, field)
                    if new_type:
                        field._python_type = new_type
                elif language == "typescript":
                    new_type = _analyze_typescript_type(value, field)
                    if new_type:
                        field._typescript_type = new_type

    except Exception:
        print(f"[red] - Error disambiguating fields for table {table_id}.[/]")


def _find_non_blank_value(records: list[dict], field_id: str) -> Any:
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


# =============================================================================
# TYPE ANALYSIS FUNCTIONS (for disambiguation)
# =============================================================================


def _analyze_python_type(value: Any, field: Field) -> str:
    """Analyze a Python value and return the appropriate Python type string."""
    if isinstance(value, list):
        if not value:
            print(f"[red] - Field {field.id} value is an empty list.[/]")
            return ""

        element = next((v for v in value if v is not None), None)
        if element is None:
            print(f"[red] - Field {field.id} list contains only None values.[/]")
            return ""

        element_type = _get_python_element_type(element, field)
        if element_type:
            return f"list[{element_type}]"
        print(f"[red] - Could not determine type for field {field.id}.[/]")
        return ""
    else:
        element_type = _get_python_element_type(value, field)
        if element_type:
            return element_type
        print(f"[red] - Could not determine type for field {field.id}.[/]")
        return ""


def _analyze_typescript_type(value: Any, field: Field) -> str:
    """Analyze a value and return the appropriate TypeScript type string."""
    if isinstance(value, list):
        if not value:
            print(f"[red] - Field {field.id} value is an empty list.[/]")
            return ""

        element = next((v for v in value if v is not None), None)
        if element is None:
            print(f"[red] - Field {field.id} list contains only None values.[/]")
            return ""

        element_type = _get_typescript_element_type(element, field)
        if element_type:
            return f"{element_type}[]"
        print(f"[red] - Could not determine type for field {field.id}.[/]")
        return ""
    else:
        element_type = _get_typescript_element_type(value, field)
        if element_type:
            return element_type
        print(f"[red] - Could not determine type for field {field.id}.[/]")
        return ""


def _get_python_element_type(value: Any, field: Field) -> str:
    """Map a Python value to its Python type string."""
    if isinstance(value, bool):
        return "bool"
    elif isinstance(value, str):
        if value.startswith("rec"):
            return "RecordId"
        return "str"
    elif isinstance(value, int):
        return "int"
    elif isinstance(value, float):
        return "float"
    elif isinstance(value, dict):
        if "url" in value and "filename" in value:
            return "AirtableAttachment"
        elif "id" in value and "email" in value:
            return "AirtableCollaborator"
        elif "specialValue" in value:
            if value["specialValue"] == "Infinity" or value["specialValue"] == "NaN":
                return "float"
        elif "error" in value:
            print(f"[red] - Field {field.id} value returns an error.[/]")
            return ""
        print(f"[red] - Unrecognized dict structure for field {field.id}.[/]", value)
        return ""
    print(f"[red] - Unrecognized value type for field {field.id}.[/]")
    return ""


def _get_typescript_element_type(value: Any, field: Field) -> str:
    """Map a value to its TypeScript type string."""
    if isinstance(value, bool):
        return "boolean"
    elif isinstance(value, str):
        if value.startswith("rec"):
            return "RecordId"
        return "string"
    elif isinstance(value, int) or isinstance(value, float):
        return "number"
    elif isinstance(value, dict):
        if "url" in value and "filename" in value:
            return "Attachment"
        elif "id" in value and "email" in value:
            return "Collaborator"
        elif "specialValue" in value:
            if value["specialValue"] == "Infinity" or value["specialValue"] == "NaN":
                return "number"
        elif "error" in value:
            print(f"[red] - Field {field.id} value returns an error.[/]")
            return ""
        print(f"[red] - Unrecognized dict structure for field {field.id}.[/]", value)
        return ""
    print(f"[red] - Unrecognized value type for field {field.id}.[/]")
    return ""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Literal

import pyairtable
from rich import print

from ..meta import AirtableCredentials, Base, Field
from ..meta_types import FieldType, GenericType, ResolvedType
from . import timer
from .verbose import verbose

# =============================================================================
# region MAPS
# =============================================================================

AIRTABLE_TO_GENERIC: dict[str, GenericType] = {
    # Text
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
    # Integer
    "count": GenericType.INTEGER,
    "autoNumber": GenericType.INTEGER,
    # Float
    "percent": GenericType.FLOAT,
    "currency": GenericType.FLOAT,
    # Duration
    "duration": GenericType.DURATION,
    # Airtable special types
    "multipleRecordLinks": GenericType.LIST_OF_RECORD_IDS,
    "multipleAttachments": GenericType.LIST_OF_ATTACHMENTS,
    "multipleCollaborators": GenericType.LIST_OF_COLLABORATORS,
    "singleCollaborator": GenericType.COLLABORATOR,
    "lastModifiedBy": GenericType.COLLABORATOR,
    "createdBy": GenericType.COLLABORATOR,
    "button": GenericType.BUTTON,
}

GENERIC_TO_PYTHON: dict[GenericType, str] = {
    GenericType.STRING: "str",
    GenericType.INTEGER: "int",
    GenericType.FLOAT: "float",
    GenericType.BOOLEAN: "bool",
    GenericType.DATETIME: "datetime",  # pyAirtable converts to datetime.datetime
    GenericType.DURATION: "timedelta",  # pyAirtable converts to datetime.timedelta
    GenericType.RECORD_ID: "RecordId",  # custom type alias for str
    GenericType.ATTACHMENT: "AirtableAttachment",
    GenericType.COLLABORATOR: "AirtableCollaborator",
    GenericType.BUTTON: "AirtableButton",
    GenericType.LIST_OF_RECORD_IDS: "list[RecordId]",
    GenericType.LIST_OF_ATTACHMENTS: "list[AirtableAttachment]",
    GenericType.LIST_OF_COLLABORATORS: "list[AirtableCollaborator]",
    GenericType.UNKNOWN: "Any",
}

GENERIC_TO_TYPESCRIPT: dict[GenericType, str] = {
    GenericType.STRING: "string",
    GenericType.INTEGER: "number",
    GenericType.FLOAT: "number",
    GenericType.BOOLEAN: "boolean",
    GenericType.DATETIME: "string",  # ISO date strings
    GenericType.DURATION: "number",  # Milliseconds
    GenericType.RECORD_ID: "RecordId",  # custom type alias for string
    GenericType.ATTACHMENT: "Attachment",
    GenericType.COLLABORATOR: "Collaborator",
    GenericType.BUTTON: "AirtableButton",
    GenericType.LIST_OF_RECORD_IDS: "RecordId[]",
    GenericType.LIST_OF_ATTACHMENTS: "Attachment[]",
    GenericType.LIST_OF_COLLABORATORS: "Collaborator[]",
    GenericType.UNKNOWN: "any",
}

GENERIC_TO_ZOD: dict[GenericType, str] = {
    GenericType.SINGLE_SELECT: "z.string()",
    GenericType.MULTIPLE_SELECT: "z.string()",  # list wrapping handled in render_type
    GenericType.STRING: "z.string()",
    GenericType.INTEGER: "z.number()",  # No .int() - JS doesn't distinguish, and computed fields can produce floats
    GenericType.FLOAT: "z.number()",
    GenericType.BOOLEAN: "z.boolean()",
    GenericType.DATETIME: "z.string()",  # ISO date strings
    GenericType.DURATION: "z.number()",  # Milliseconds
    GenericType.RECORD_ID: "recordIdSchema",
    GenericType.ATTACHMENT: "AirtableAttachmentSchema",
    GenericType.COLLABORATOR: "AirtableCollaboratorSchema",
    GenericType.BUTTON: "AirtableButtonSchema",
    GenericType.LIST_OF_RECORD_IDS: "z.array(recordIdSchema)",
    GenericType.LIST_OF_ATTACHMENTS: "z.array(AirtableAttachmentSchema)",
    GenericType.LIST_OF_COLLABORATORS: "z.array(AirtableCollaboratorSchema)",
    GenericType.UNKNOWN: "z.any()",
}

GENERIC_TO_RUST: dict[GenericType, str] = {
    GenericType.STRING: "String",
    GenericType.INTEGER: "i64",
    GenericType.FLOAT: "f64",
    GenericType.BOOLEAN: "bool",
    GenericType.DATETIME: "String",  # ISO 8601 strings
    GenericType.DURATION: "i64",  # Milliseconds
    GenericType.RECORD_ID: "Vec<RecordId>",  # API always returns arrays, even for single-link fields
    GenericType.ATTACHMENT: "Attachment",
    GenericType.COLLABORATOR: "Collaborator",
    GenericType.BUTTON: "AirtableButton",
    GenericType.LIST_OF_RECORD_IDS: "Vec<RecordId>",
    GenericType.LIST_OF_ATTACHMENTS: "Vec<Attachment>",
    GenericType.LIST_OF_COLLABORATORS: "Vec<Collaborator>",
    GenericType.UNKNOWN: "serde_json::Value",
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


@timer.timed("map_types")
def map_types(base: Base) -> None:
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
            resolved = map_type(field)

            # Render all types from the same generic type
            is_computed = field.is_computed()
            py_type = render_type(field, "python", resolved=resolved)
            ts_type = render_type(field, "typescript", resolved=resolved)
            rust_type = render_type(field, "rust", resolved=resolved, is_computed=is_computed)
            rust_type = apply_rust_computed_wrapping(rust_type, field, resolved)

            field._python_type = py_type
            field._typescript_type = ts_type
            field._rust_type = rust_type

            # Handle disambiguation for union types (list vs single value)
            if "|" in py_type and field.is_valid():
                csv_python_type = field.csv_python_type()
                if csv_python_type and python_type_matches_generic(csv_python_type, field._generic_type):
                    # CSV has valid disambiguated type - use it directly
                    is_list = csv_python_type.startswith("list[")
                    field._python_type = render_type(field, "python", is_list=is_list)
                    field._typescript_type = render_type(field, "typescript", is_list=is_list)
                    rust_type = render_type(field, "rust", is_list=is_list, is_computed=is_computed)
                    field._rust_type = apply_rust_computed_wrapping(rust_type, field, resolved)
                else:
                    # Need to disambiguate via API (no saved type, or base type changed)
                    fields_to_disambiguate.append(field)

    if verbose:
        print("[dim] - Mapped unambiguous types[/]")

    # Second pass: disambiguate fields that need it (handles both languages)
    if fields_to_disambiguate:
        disambiguate_fields(fields_to_disambiguate)
        if verbose:
            print("[dim] - Mapped ambiguous field types[/]")

    if verbose:
        print("")


# endregion

# =============================================================================
# region TYPE CALC
# =============================================================================


@timer.timed("map_type")
def map_type(field: Field) -> ResolvedType:
    """Calculate the generic type for a field."""

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

    if airtable_type in AIRTABLE_TO_GENERIC:
        generic = AIRTABLE_TO_GENERIC[airtable_type]
        # Airtable uses multipleRecordLinks for both single and multiple link fields.
        # The prefersSingleRecordLink option distinguishes them.
        if generic == GenericType.LIST_OF_RECORD_IDS and field.options and field.options.prefers_single_record_link:
            generic = GenericType.RECORD_ID
        resolved = ResolvedType(generic_type=generic)
        field._generic_type = resolved.generic_type
        return resolved

    if airtable_type == "number":
        if field.options and field.options.precision is not None and field.options.precision == 0:
            resolved = ResolvedType(generic_type=GenericType.INTEGER)
        else:
            resolved = ResolvedType(generic_type=GenericType.FLOAT)
        field._generic_type = resolved.generic_type
        return resolved

    if airtable_type == "singleSelect":
        options_name = get_select_options_name(field)
        if options_name:
            resolved = ResolvedType(generic_type=GenericType.SINGLE_SELECT, options_name=options_name)
        else:
            resolved = ResolvedType(generic_type=GenericType.UNKNOWN)
        field._generic_type = resolved.generic_type
        return resolved

    if airtable_type == "multipleSelects":
        options_name = get_select_options_name(field)
        if options_name:
            resolved = ResolvedType(generic_type=GenericType.MULTIPLE_SELECT, options_name=options_name)
        else:
            resolved = ResolvedType(generic_type=GenericType.UNKNOWN)
        field._generic_type = resolved.generic_type
        return resolved

    resolved = ResolvedType(generic_type=GenericType.UNKNOWN)
    field._generic_type = resolved.generic_type
    return resolved


@timer.timed("get_select_options_name")
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


Language = Literal["python", "typescript", "zod", "rust"]


@dataclass(frozen=True)
class LanguageConfig:
    """Language-specific type configuration."""

    type_map: dict[GenericType, str]
    unknown: str
    list_fmt: str
    union_fmt: str
    enum_fmt: str = "{0}"
    computed_union_fmt: str = ""  # For computed fields where array items can be errors


LANGUAGE_CONFIGS: dict[Language, LanguageConfig] = {
    "python": LanguageConfig(
        type_map=GENERIC_TO_PYTHON,
        unknown="Any",
        list_fmt="list[{0}]",
        union_fmt="list[{0} | None] | {0}",
    ),
    "typescript": LanguageConfig(
        type_map=GENERIC_TO_TYPESCRIPT,
        unknown="any",
        list_fmt="{0}[]",
        union_fmt="{0} | {0}[]",
    ),
    "zod": LanguageConfig(
        type_map=GENERIC_TO_ZOD,
        unknown="z.any()",
        list_fmt="z.array({0})",
        union_fmt="z.union([{0}, z.array({0}.nullable())])",
        enum_fmt="z.enum({0}s)",
        computed_union_fmt="z.union([{0}, SpecialNumberSchema, ErrorValueSchema, z.array(z.union([{0}, SpecialNumberSchema, ErrorValueSchema]).nullable())])",
    ),
    "rust": LanguageConfig(
        type_map=GENERIC_TO_RUST,
        unknown="serde_json::Value",
        list_fmt="Vec<{0}>",
        union_fmt="VecOrValue<{0}>",
        enum_fmt="{0}",
        computed_union_fmt="VecOrValue<MaybeSpecialOrError<{0}>>",
    ),
}


def is_already_list(base_type: str, language: Language) -> bool:
    match language:
        case "python":
            return "list" in base_type
        case "typescript":
            return base_type.endswith("[]")
        case "zod":
            return base_type.startswith("z.array(")
        case "rust":
            return base_type.startswith("Vec<")
        case _:
            return False


@timer.timed("render_type")
def render_type(
    field: Field,
    language: Language,
    resolved: ResolvedType | None = None,
    is_list: bool | None = None,
    is_computed: bool = False,
) -> str:
    config: LanguageConfig = LANGUAGE_CONFIGS[language]

    # Get the generic type
    generic_type = resolved.generic_type if resolved else field._generic_type
    if generic_type is None:
        return config.unknown

    # Compute base type
    if generic_type == GenericType.SINGLE_SELECT:
        # If the type_map has an entry (e.g. Zod uses z.string()), use it directly
        if generic_type in config.type_map:
            base_type = config.type_map[generic_type]
        else:
            options_name = resolved.options_name if resolved else field.options_name()
            if options_name:
                base_type = config.enum_fmt.format(options_name)
            else:
                base_type = config.unknown
    elif generic_type == GenericType.MULTIPLE_SELECT:
        # If the type_map has an entry (e.g. Zod uses z.string()), use it directly
        if generic_type in config.type_map:
            return config.list_fmt.format(config.type_map[generic_type])  # Always a list
        else:
            options_name = resolved.options_name if resolved else field.options_name()
            if options_name:
                enum_type = config.enum_fmt.format(options_name)
                return config.list_fmt.format(enum_type)  # Always a list
            return config.unknown
    else:
        base_type = config.type_map.get(generic_type, config.unknown)

    if is_list is None:
        # Apply lookup/rollup wrapper. It's impossible to tell based on Airtable's metadata is it's a list or not.
        if not is_already_list(base_type, language):
            if field.involves_lookup() or field.involves_rollup():
                # Use computed_union_fmt for computed fields (array items can be errors)
                if is_computed and config.computed_union_fmt:
                    return config.computed_union_fmt.format(base_type)
                return config.union_fmt.format(base_type)
    elif is_list:
        return config.list_fmt.format(base_type)

    return base_type


@timer.timed("map_python_type")
def map_python_type(field: Field) -> str:
    """Calculate the raw Python type for a field (without disambiguation)."""

    if field._python_type_csv is not None:
        return field._python_type_csv

    resolved: ResolvedType = map_type(field)
    py_type: str = render_type(field, "python", resolved=resolved)

    field._python_type = py_type
    return py_type


@timer.timed("map_typescript_type")
def map_typescript_type(field: Field) -> str:
    """Calculate the raw TypeScript type for a field (without disambiguation)."""

    if field._typescript_type_csv is not None:
        return field._typescript_type_csv

    resolved: ResolvedType = map_type(field)
    ts_type: str = render_type(field, "typescript", resolved=resolved)

    field._typescript_type = ts_type
    return ts_type


@timer.timed("map_zod_type")
def map_zod_type(field: Field) -> str:
    """Calculate the Zod schema for a field."""

    if field._zod_type is not None:
        return field._zod_type

    resolved: ResolvedType = map_type(field)
    is_computed = field.is_computed()
    zod_type: str = render_type(field, "zod", resolved=resolved, is_computed=is_computed)

    # Add error/special value handling for computed/formula fields
    # Skip if field involves lookup/rollup - already handled by computed_union_fmt in render_type
    if is_computed and not (field.involves_lookup() or field.involves_rollup()):
        generic_type = resolved.generic_type if resolved else field._generic_type
        # Number types can have special values (NaN, Infinity) and errors
        if generic_type in (GenericType.INTEGER, GenericType.FLOAT, GenericType.DURATION):
            zod_type = f"z.union([{zod_type}, SpecialNumberSchema, ErrorValueSchema])"
        else:
            # All other formula fields can have errors
            zod_type = f"z.union([{zod_type}, ErrorValueSchema])"

    # All Airtable fields are optional (can be blank/missing)
    zod_type = f"{zod_type}.optional()"

    field._zod_type = zod_type
    return zod_type


def apply_rust_computed_wrapping(rust_type: str, field: Field, resolved: ResolvedType | None = None) -> str:
    """Wrap a computed field's Rust type to model Airtable special/error values.

    Numeric computed → `MaybeSpecialOrError<T>`; other computed → `MaybeError<T>`.
    No-op when the type was already wrapped by `computed_union_fmt` in `render_type`.

    For disambiguated list types (`Vec<T>`), wraps inner items as `Vec<Option<W<T>>>`
    (items can be null or per-item errors) and the whole Vec in `MaybeError<..>`
    because Airtable can return a top-level `{"error":"..."}` instead of the list
    when the rollup/lookup formula itself fails.
    """
    if not field.is_computed():
        return rust_type

    if "MaybeSpecialOrError<" in rust_type or "MaybeError<" in rust_type:
        return rust_type

    generic_type = resolved.generic_type if resolved else field._generic_type
    wrapper = "MaybeSpecialOrError" if generic_type in (GenericType.INTEGER, GenericType.FLOAT, GenericType.DURATION) else "MaybeError"

    if rust_type.startswith("Vec<") and rust_type.endswith(">"):
        inner = rust_type[len("Vec<") : -1]
        return f"MaybeError<Vec<Option<{wrapper}<{inner}>>>>"

    return f"{wrapper}<{rust_type}>"


@timer.timed("map_rust_type")
def map_rust_type(field: Field) -> str:
    """Calculate the Rust type for a field."""

    if field._rust_type is not None:
        return field._rust_type

    resolved: ResolvedType = map_type(field)
    rust_type: str = render_type(field, "rust", resolved=resolved, is_computed=field.is_computed())
    rust_type = apply_rust_computed_wrapping(rust_type, field, resolved)

    field._rust_type = rust_type
    return rust_type


# endregion

# =============================================================================
# region DISAMBIGUATION
# =============================================================================


@timer.timed("disambiguate_fields")
def disambiguate_fields(fields: list[Field]) -> None:
    """Disambiguate multiple fields efficiently by batching API calls per table."""

    try:
        api_key = AirtableCredentials.get_instance().get_api_key()
    except Exception:
        return

    # Group fields by table
    fields_by_table: dict[str, list[Field]] = {}
    for field in fields:
        table_id = field.table.id
        if table_id not in fields_by_table:
            fields_by_table[table_id] = []
        fields_by_table[table_id].append(field)

    # Process tables concurrently for better performance
    failures: list[Field] = []
    num_tables = len(fields_by_table)

    if num_tables == 1:
        # Single table: no concurrency overhead needed
        sys.stdout.write("Disambiguating calculated field types (1 table)...")
        sys.stdout.flush()
        table_fields = next(iter(fields_by_table.values()))
        failures.extend(disambiguate_fields_per_table(api_key, table_fields))
        sys.stdout.write(" done\n")
        sys.stdout.flush()
    else:
        # Multiple tables: process concurrently
        max_workers = min(num_tables, 5)  # Cap at 5 to avoid API rate limits
        completed = 0

        # Print initial status
        sys.stdout.write(f"Disambiguating calculated field types (0/{num_tables} tables)...")
        sys.stdout.flush()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_table = {
                executor.submit(disambiguate_fields_per_table, api_key, table_fields): table_id for table_id, table_fields in fields_by_table.items()
            }
            for future in as_completed(future_to_table):
                try:
                    failures.extend(future.result())
                except Exception as e:
                    table_id = future_to_table[future]
                    sys.stdout.write(f"\n[red] - Error processing table {table_id}: {e}[/]\n")
                completed += 1
                # Use \r to return to start, then clear line with ANSI escape, then write new status
                sys.stdout.write(f"\rDisambiguating calculated field types ({completed}/{num_tables} tables)...\033[K")
                sys.stdout.flush()
        sys.stdout.write(" done\n")
        sys.stdout.flush()

    if failures:
        print(f"[yellow] - Failed to disambiguate {len(failures)} fields. No records have values for these fields. Use `--verbose` for details.[/]")
        if verbose:
            for field in failures:
                print(f"[dim]    - Table '{field.table.name}' Field '{field.name}' (ID: {field.id})[/]")


@timer.timed("disambiguate_fields_per_table")
def disambiguate_fields_per_table(api_key: str, fields: list[Field]) -> list[Field]:
    """Disambiguate all fields from a single table with minimal API calls."""

    if not fields:
        return []

    sample_field: Field = fields[0]
    base_id: str = sample_field.base.id
    table_id: str = sample_field.table.id
    field_ids: list[str] = [f.id for f in fields]

    try:
        table = pyairtable.Table(api_key, base_id, table_id)
        remaining = list(fields)

        # Phase 1: shotgun fetch
        records = table.all(fields=field_ids, max_records=20, use_field_ids=True)
        remaining = process_records_and_get_remaining(remaining, records)
        if not remaining:
            return []

        # Phase 2: narrow it down
        remaining = disambiguate_with_or_formula(table, remaining)
        if not remaining:
            return []

        # Phase 3: per-field fallback for any still remaining
        failures: list[Field] = []
        for field in remaining:
            if failure := disambiguate_single_field(table, field):
                failures.append(failure)

        return failures

    except Exception as e:
        print(f"[red] - API Error disambiguating fields for table {table_id}.[/]", e)
        return fields  # Return all as failures


@timer.timed("process_records_and_get_remaining")
def process_records_and_get_remaining(fields: list[Field], records: list[dict]) -> list[Field]:
    """Process records and return fields that still need disambiguation."""
    remaining: list[Field] = []
    for field in fields:
        value = find_non_blank_value(records, field.id)
        if value is not None:
            apply_disambiguated_type(field, isinstance(value, list))
        else:
            remaining.append(field)
    return remaining


@timer.timed("disambiguate_with_or_formula")
def disambiguate_with_or_formula(table: pyairtable.Table, fields: list[Field]) -> list[Field]:
    """Iteratively fetch records where ANY field is non-blank until no progress."""
    remaining = list(fields)

    while len(remaining) > 1:
        field_ids = [f.id for f in remaining]
        formula = any_not_blank(field_ids)

        records = table.all(formula=formula, fields=field_ids, max_records=50, use_field_ids=True)
        if not records:
            break  # No records found, go to per-field fallback

        new_remaining: list[Field] = process_records_and_get_remaining(remaining, records)
        if len(new_remaining) == len(remaining):
            break  # No progress made, go to per-field fallback

        remaining = new_remaining

    return remaining


def not_blank(field_id: str) -> str:
    """Build NOT({field_id}=BLANK()) formula."""
    return f"NOT({{{field_id}}}=BLANK())"


def any_not_blank(field_ids: list[str]) -> str:
    """Build OR(NOT({f1}=BLANK()), NOT({f2}=BLANK()), ...) formula."""
    conditions = [not_blank(fid) for fid in field_ids]
    if len(conditions) == 1:
        return conditions[0]
    return f"OR({', '.join(conditions)})"


@timer.timed("disambiguate_single_field")
def disambiguate_single_field(table: pyairtable.Table, field: Field) -> Field | None:
    """Fetch a single record where the field is not blank."""
    record = table.first(
        formula=not_blank(field.id),
        fields=[field.id],
        use_field_ids=True,
    )
    if record:
        if value := record.get("fields", {}).get(field.id):
            apply_disambiguated_type(field, isinstance(value, list))
            return None
    return field  # Still could not disambiguate


def apply_disambiguated_type(field: Field, is_list: bool) -> None:
    """Apply disambiguated types to a field."""
    field._python_type = render_type(field, "python", is_list=is_list)
    field._typescript_type = render_type(field, "typescript", is_list=is_list)
    rust_type = render_type(field, "rust", is_list=is_list, is_computed=field.is_computed())
    field._rust_type = apply_rust_computed_wrapping(rust_type, field)


def find_non_blank_value(records: list[dict], field_id: str) -> Any:
    """Find the first non-blank value for a field across multiple records."""
    for record in records:
        value = record.get("fields", {}).get(field_id)
        if value is not None:
            if isinstance(value, list):
                if value and any(v is not None for v in value):
                    return value
            else:
                return value
    return None

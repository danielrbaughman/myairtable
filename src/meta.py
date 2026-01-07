import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import pandas as pd
from pydantic import BaseModel
from pydantic.alias_generators import to_camel, to_pascal
from rich import print

from src.helpers import remove_extra_spaces, sanitize_leading_trailing_characters, sanitize_property_name, sanitize_reserved_names
from src.meta_types import BaseMetadata, FieldType

PROPERTY_NAME = "Property Name (snake_case)"
MODEL_NAME = "Model Name (snake_case)"


def get_base_meta_data() -> BaseMetadata:
    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise Exception("AIRTABLE_API_KEY not found in environment")

    base_id = get_base_id()

    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    try:
        response = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.ReadTimeout:
        print("Request timed out, retrying in 5 seconds...")
        time.sleep(5)
        response = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"})
    data: BaseMetadata = response.json()
    data["tables"].sort(key=lambda t: t["name"].lower())
    for table in data["tables"]:
        table["fields"].sort(key=lambda f: f["name"].lower())
    return data


def get_base_id() -> str:
    """Get the Airtable Base ID from environment variable."""
    base_id = os.getenv("AIRTABLE_BASE_ID")
    if not base_id:
        raise Exception("AIRTABLE_BASE_ID not found in environment")
    return base_id


def generate_meta(metadata: BaseMetadata, folder: Path):
    """Fetch Airtable metadata into a json file."""

    p = folder / "meta.json"
    with open(p, "w") as f:
        f.write(json.dumps(metadata, indent=4))
    print(f"Base metadata written to '{p.as_posix()}'")


class Choice(BaseModel):
    id: str
    name: str
    color: str | None = None


class DateFormat(BaseModel):
    name: str
    format: str


class Result(BaseModel):
    type: FieldType
    options: Optional["Options"] = None


class Options(BaseModel):
    formula: str | None = None
    view_id_for_record_selection: str | None = None
    is_reversed: bool | None = None
    precision: int | None = None
    choices: list[Choice] | None = None
    linked_table_id: str | None = None
    prefers_single_record_link: bool | None = None
    inverse_link_field_id: str | None = None
    icon: str | None = None
    color: str | None = None
    is_valid: bool | None = None
    date_format: DateFormat | None = None
    duration_format: str | None = None
    record_link_field_id: str | None = None
    field_id_in_linked_table: str | None = None
    referenced_field_ids: list[str] | None = None
    result: Result | None = None
    field_id: str | None = None


class CsvCache:
    """Cache for CSV lookups - provides O(1) access by ID."""

    def __init__(self, csv_folder: Path | None = None):
        self.fields: dict[str, dict[str, str]] = {}  # field_id -> {column: value}
        self.tables: dict[str, dict[str, str]] = {}  # table_id -> {column: value}

        if csv_folder:
            self._load_fields(csv_folder / "fields.csv")
            self._load_tables(csv_folder / "tables.csv")

    def _load_fields(self, path: Path) -> None:
        if not path.exists():
            return
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            field_id = row.get("Field ID")
            if field_id:
                self.fields[field_id] = row.to_dict()

    def _load_tables(self, path: Path) -> None:
        if not path.exists():
            return
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            table_id = row.get("Table ID")
            if table_id:
                self.tables[table_id] = row.to_dict()

    def get_field_value(self, field_id: str, key: str) -> str | None:
        """Get a value for a field by ID and column key. O(1) lookup."""
        row = self.fields.get(field_id)
        if row and key in row:
            value = row[key]
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def get_table_value(self, table_id: str, key: str) -> str | None:
        """Get a value for a table by ID and column key. O(1) lookup."""
        row = self.tables.get(table_id)
        if row and key in row:
            value = row[key]
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None


class TableOrField(BaseModel):
    id: str
    name: str

    def is_table(self) -> bool:
        return hasattr(self, "primary_field_id")

    def _property_name(self, use_custom: bool = True, custom_key: str = PROPERTY_NAME) -> str:
        """Converts the field or table name to a sanitized property name in snake_case."""
        if use_custom and hasattr(self, "base") and self.base and self.base._csv_cache:
            text = self._custom_property_name(key=custom_key)
            if text:
                text = text.replace(" ", "_")
                return text

        text = self.name

        text = sanitize_property_name(text)
        text = remove_extra_spaces(text)
        text = text.replace(" ", "_")
        text = text.lower()
        text = sanitize_leading_trailing_characters(text)
        text = sanitize_reserved_names(text)

        return text

    def _custom_property_name(self, key: str = "Property Name (snake_case)") -> str | None:
        """Gets the custom property name for a field or table, if it exists."""
        # Access cache from base (both Field and Table have base attribute)
        if not hasattr(self, "base") or self.base is None:
            return None

        cache = self.base._csv_cache
        if cache is None:
            return None

        if self.is_table():
            value = cache.get_table_value(self.id, key)
        else:
            value = cache.get_field_value(self.id, key)

        if value:
            return remove_extra_spaces(value)
        return None

    def name_snake(self, use_custom: bool = True) -> str:
        """Get the property name in snake_case."""
        return self._property_name(use_custom=use_custom)

    def name_camel(self, use_custom: bool = True) -> str:
        """Get the property name in camelCase."""
        text = self._property_name(use_custom=use_custom)
        return to_camel(text)

    def name_pascal(self, use_custom: bool = True) -> str:
        """Get the property name in PascalCase."""
        text = self._property_name(use_custom=use_custom)
        return to_pascal(text)

    def name_model(self, use_custom: bool = True) -> str:
        """Get the model name (PascalCase with 'Model' suffix)."""
        if use_custom and hasattr(self, "base") and self.base and self.base._csv_cache:
            text = self._custom_property_name(key=MODEL_NAME)
            if text:
                text = text.replace(" ", "_")
                return to_pascal(text)

        name = self.name_pascal(use_custom=use_custom) + "Model"
        return name

    def name_upper(self) -> str:
        """Get the name with only alphabetic characters in UPPERCASE."""

        def alpha_only(text: str) -> str:
            return "".join(c for c in text if c.isalpha())

        return alpha_only(self.name).upper()


class Field(TableOrField):
    id: str
    name: str
    type: FieldType
    description: str | None = None
    options: Options | None = None
    table: "Table"
    base: "Base"

    def is_valid(self) -> bool:
        """Check if the field is `valid` according to Airtable."""
        if self.options and hasattr(self.options, "is_valid"):
            return bool(self.options.is_valid)
        return True

    def is_calculated(self) -> bool:
        """A field whose value is dependent on other fields."""
        calculated_types: list[FieldType] = [
            "formula",
            "rollup",
            "lookup",
            "multipleLookupValues",
        ]
        return self.type in calculated_types

    def is_computed(self) -> bool:
        """A field whose value is calculated by Airtable, and thus read-only."""
        computed_types: list[FieldType] = [
            "formula",
            "rollup",
            "lookup",
            "multipleLookupValues",
            "createdTime",
            "lastModifiedTime",
            "lastModifiedBy",
            "createdBy",
            "count",
            "button",
        ]
        return self.type in computed_types

    def result_type(self) -> FieldType:
        if self.options:
            if self.options.result:
                if self.options.result.type:
                    return self.options.result.type
        return self.type

    def referenced_field(self) -> "Field | None":
        if self.options is None:
            return None
        referenced_field_id = self.options.field_id_in_linked_table
        if referenced_field_id and referenced_field_id in self.base.field_ids():
            return self.base.field_by_id(referenced_field_id)

        return None

    def get_linked_model_name(self) -> str:
        """Get the model name for a linked record field."""
        if self.options and self.options.linked_table_id:
            for table in self.base.tables:
                if table.id == self.options.linked_table_id:
                    return table.name_model()
        return ""

    def involves_lookup(self) -> bool:
        """Check if a field involves multipleLookupValues, either directly or through any referenced fields."""
        # Check memoization cache first
        if self.id in self.base._involves_lookup_cache:
            return self.base._involves_lookup_cache[self.id]

        # Compute result
        if self.type == "multipleLookupValues" or self.type == "lookup":
            result = True
        elif self.options is None:
            result = False
        else:
            result = False
            # Check if field has referencedFieldIds and recursively check each one
            referenced_field_ids = self.options.referenced_field_ids or []
            for referenced_field_id in referenced_field_ids:
                if referenced_field_id in self.base.field_ids():
                    referenced_field = self.base.field_by_id(referenced_field_id)
                    if referenced_field and referenced_field.involves_lookup():
                        result = True
                        break

        # Cache and return result
        self.base._involves_lookup_cache[self.id] = result
        return result

    def involves_rollup(self) -> bool:
        """Check if a field involves rollup, either directly or through any referenced fields."""
        # Check memoization cache first
        if self.id in self.base._involves_rollup_cache:
            return self.base._involves_rollup_cache[self.id]

        # Compute result
        if self.type == "rollup":
            result = True
        elif self.options is None:
            result = False
        else:
            result = False
            # Check if field has referencedFieldIds and recursively check each one
            referenced_field_ids = self.options.referenced_field_ids or []
            for referenced_field_id in referenced_field_ids:
                if referenced_field_id in self.base.field_ids():
                    referenced_field = self.base.field_by_id(referenced_field_id)
                    if referenced_field and referenced_field.involves_rollup():
                        result = True
                        break

        # Cache and return result
        self.base._involves_rollup_cache[self.id] = result
        return result

    def select_options(self) -> list[str]:
        """Get the options of a select field"""

        airtable_type = self.type

        if (
            airtable_type == "singleSelect"
            or airtable_type == "multipleSelects"
            or airtable_type == "singleCollaborator"
            or airtable_type == "multipleLookupValues"
            or airtable_type == "formula"
        ):
            if self.options:
                if self.options.choices:
                    options = [choice.name for choice in self.options.choices]
                    options.sort()
                    return options
                elif self.options.result:
                    if self.options.result.options:
                        if self.options.result.options.choices:
                            options = [choice.name for choice in self.options.result.options.choices]
                            options.sort()
                            return options

        return []

    def options_name(self) -> str:
        return f"{self.table.name_pascal()}{self.name_pascal()}Option"

    def formula_class(self) -> str:
        """Returns the appropriate myAirtable formula type for a given Airtable field."""

        airtable_type: FieldType = self.type
        formula_type: str = "TextField"

        # With calculated fields, we want to know the type of the result
        if self.is_calculated():
            airtable_type = self.result_type()

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
            case "multipleSelects":
                formula_type = "MultiSelectField"
            case "singleSelect":
                formula_type = "SingleSelectField"
            case _:
                formula_type = "TextField"

        return formula_type


class View(BaseModel):
    id: str
    name: str
    type: str
    table_id: str


class Table(TableOrField):
    id: str
    name: str
    primary_field_id: str
    fields: list[Field]
    views: list[View]
    base: "Base"

    def field_ids(self) -> list[str]:
        return [field.id for field in self.fields]

    def field_names(self) -> list[str]:
        return [field.name for field in self.fields]

    def field_by_id(self, field_id: str) -> Field | None:
        for field in self.fields:
            if field.id == field_id:
                return field
        return None

    def detect_duplicate_property_names(self) -> None:
        """Detect duplicate property names in a table's fields."""
        from collections import Counter

        property_names = [field.name_snake() for field in self.fields]
        counts = Counter(property_names)

        for name, count in counts.items():
            if count > 1:
                print(f"[red]Warning: Duplicate property name detected:[/] '{name}' in table '{self.name}'")

    def select_fields(self) -> list[Field]:
        select_fields: list[Field] = []
        for field in self.fields:
            options = field.select_options()
            if len(options) > 0:
                select_fields.append(field)
        return select_fields

    def linked_tables(self) -> list["Table"]:
        """Get the list of linked models for a given table"""

        linked_tables: list[Table] = []

        for field in self.fields:
            if field.type == "multipleRecordLinks":
                if field.options and field.options.linked_table_id:
                    table_id = field.options.linked_table_id
                    tables = self.base.tables
                    for linked_table in tables:
                        if linked_table.id == table_id:
                            linked_tables.append(linked_table)
                            break

        # Remove duplicates while preserving order
        seen = set()
        unique_linked_tables = []
        for linked_table in linked_tables:
            if linked_table.id not in seen and linked_table.id != self.id:
                seen.add(linked_table.id)
                unique_linked_tables.append(linked_table)

        linked_tables = unique_linked_tables
        return linked_tables


class Base(BaseModel):
    id: str
    tables: list[Table]
    _original_metadata: BaseMetadata
    _csv_cache: CsvCache | None = None
    # Memoization caches for recursive field analysis (prevents exponential traversal)
    _involves_lookup_cache: dict[str, bool] = {}
    _involves_rollup_cache: dict[str, bool] = {}

    @classmethod
    def new(cls, csv_folder: Path | None = None) -> "Base":
        meta = get_base_meta_data()
        base: Base = cls(
            id=get_base_id(),
            tables=[],
        )
        base._original_metadata = meta
        base._csv_cache = CsvCache(csv_folder) if csv_folder else None
        # Initialize fresh caches for this base instance
        base._involves_lookup_cache = {}
        base._involves_rollup_cache = {}
        for table_meta in meta["tables"]:
            table = Table(
                id=table_meta["id"],
                name=table_meta["name"],
                primary_field_id=table_meta["primaryFieldId"],
                fields=[],
                views=[],
                base=base,
            )
            for field_meta in table_meta["fields"]:
                options: dict[str, Any] = field_meta.get("options", {})
                field = Field(
                    id=field_meta["id"],
                    name=field_meta["name"],
                    type=field_meta["type"],
                    description=field_meta.get("description"),
                    table=table,
                    base=base,
                    options=Options(
                        field_id=field_meta["id"],
                        formula=options.get("formula"),
                        view_id_for_record_selection=options.get("viewIdForRecordSelection"),
                        is_reversed=options.get("isReversed"),
                        precision=options.get("precision"),
                        linked_table_id=options.get("linkedTableId"),
                        prefers_single_record_link=options.get("prefersSingleRecordLink"),
                        inverse_link_field_id=options.get("inverseLinkFieldId"),
                        icon=options.get("icon"),
                        color=options.get("color"),
                        is_valid=options.get("isValid", True),
                        duration_format=options.get("durationFormat"),
                        record_link_field_id=options.get("recordLinkFieldId"),
                        field_id_in_linked_table=options.get("fieldIdInLinkedTable"),
                        referenced_field_ids=options.get("referencedFieldIds"),
                        date_format=DateFormat.model_validate(options.get("dateFormat")) if options.get("dateFormat") else None,
                        result=Result.model_validate(options.get("result")) if options.get("result") else None,
                        choices=[Choice.model_validate(choice) for choice in options.get("choices", [])] if options.get("choices") else None,
                    ),
                )
                table.fields.append(field)
            for view_meta in table_meta.get("views", []):
                view = View(
                    id=view_meta["id"],
                    name=view_meta["name"],
                    type=view_meta["type"],
                    table_id=table_meta["id"],
                )
                table.views.append(view)
            base.tables.append(table)
        return base

    def to_dict(self) -> BaseMetadata:
        return self._original_metadata

    def fields(self) -> list[Field]:
        fields = []
        for table in self.tables:
            fields.extend(table.fields)
        return fields

    def field_ids(self) -> list[str]:
        ids: list[str] = []
        for table in self.tables:
            ids.extend(table.field_ids())
        return ids

    def field_names(self) -> list[str]:
        names: list[str] = []
        for table in self.tables:
            names.extend(table.field_names())
        return names

    def table_by_id(self, table_id: str) -> Table | None:
        for table in self.tables:
            if table.id == table_id:
                return table
        return None

    def field_by_id(self, field_id: str) -> Field | None:
        for table in self.tables:
            field = table.field_by_id(field_id)
            if field:
                return field
        return None

    def select_fields(self) -> list[Field]:
        select_fields: list[Field] = []
        for field in self.fields():
            options = field.select_options()
            if len(options) > 0:
                select_fields.append(field)
        return select_fields

    def select_fields_ids(self) -> list[str]:
        select_field_ids: list[str] = []
        for field in self.fields():
            options = field.select_options()
            if len(options) > 0:
                select_field_ids.append(field.id)
        return select_field_ids

    def select_field_by_id(self, field_id: str) -> Field | None:
        field = self.field_by_id(field_id)
        if field:
            options = field.select_options()
            if len(options) > 0:
                return field
        return None

import json
import os
import time
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from pydantic import BaseModel, PrivateAttr

from src.meta_types import BaseMetadata


def get_base_meta_data(base_id: str) -> BaseMetadata:
    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise Exception("AIRTABLE_API_KEY not found in environment")

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


def gen_meta(metadata: BaseMetadata, folder: Path):
    """Fetch Airtable metadata into a json file."""

    p = folder / "meta.json"
    with open(p, "w") as f:
        f.write(json.dumps(metadata, indent=4))
    print(f"Base metadata written to {p.as_posix()}")


FieldType = Literal[
    "singleLineText",
    "multilineText",
    "number",
    "singleSelect",
    "multipleSelects",
    "multipleRecordLinks",
    "multipleLookupValues",
    "multipleAttachments",
    "checkbox",
    "date",
    "dateTime",
    "createdTime",
    "lastModifiedTime",
    "formula",
    "count",
    "rollup",
    "lookup",
    "singleCollaborator",
    "autoNumber",
    "barcode",
    "phoneNumber",
    "email",
    "url",
    "percent",
    "rating",
    "duration",
    "richText",
    "currency",
    "createdBy",
    "button",
    "lastModifiedBy",
]


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


class Field(BaseModel):
    id: str
    name: str
    type: FieldType
    description: str | None = None
    options: Options | None = None
    table_id: str


class View(BaseModel):
    id: str
    name: str
    type: str
    table_id: str


class Table(BaseModel):
    id: str
    name: str
    primary_field_id: str
    fields: list[Field]
    views: list[View]
    base_id: str

    def get_all_field_ids(self) -> list[str]:
        return [field.id for field in self.fields]

    def get_all_field_names(self) -> list[str]:
        return [field.name for field in self.fields]

    def get_field_by_id(self, field_id: str) -> Field | None:
        for field in self.fields:
            if field.id == field_id:
                return field
        return None


class Base(BaseModel):
    id: str
    tables: list[Table]
    _original_metadata: BaseMetadata = PrivateAttr()

    @classmethod
    def from_dict(cls, meta: BaseMetadata | dict, base_id: str) -> "Base":
        base: Base = cls(
            id=base_id,
            tables=[],
        )
        base._original_metadata = (meta,)
        for table_meta in meta["tables"]:
            table = Table(
                id=table_meta["id"],
                name=table_meta["name"],
                primary_field_id=table_meta["primaryFieldId"],
                fields=[],
                views=[],
                base_id=base_id,
            )
            for field_meta in table_meta["fields"]:
                options: dict[str, Any] = field_meta.get("options", {})
                field = Field(
                    id=field_meta["id"],
                    name=field_meta["name"],
                    type=field_meta["type"],
                    description=field_meta.get("description"),
                    table_id=table_meta["id"],
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
                        is_valid=options.get("isValid"),
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

    def get_all_field_ids(self) -> list[str]:
        ids = []
        for table in self.tables:
            ids.extend(table.get_all_field_ids())
        return ids

    def get_all_field_names(self) -> list[str]:
        names = []
        for table in self.tables:
            names.extend(table.get_all_field_names())
        return names

    def get_table_by_id(self, table_id: str) -> Table | None:
        for table in self.tables:
            if table.id == table_id:
                return table
        return None

    def get_field_by_id(self, field_id: str) -> Field | None:
        for table in self.tables:
            field = table.get_field_by_id(field_id)
            if field:
                return field
        return None

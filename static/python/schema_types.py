from typing import Any, Literal, NotRequired, TypedDict

FieldTypeSchema = Literal[
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
    "multipleCollaborators",
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


class FieldOptionSchema(TypedDict):
    id: str
    name: str
    color: str


class ViewSchema(TypedDict):
    id: str
    name: str
    type: str


class FieldSchema(TypedDict, total=False):
    id: str
    name: str
    type: FieldTypeSchema
    description: str | None
    options: dict[str, Any] | None


class TableSchema(TypedDict):
    id: str
    name: str
    description: NotRequired[str | None]
    primaryFieldId: str
    fields: list[FieldSchema]
    views: list[ViewSchema]


class BaseSchema(TypedDict):
    tables: list[TableSchema]

from typing import Any, Literal, Optional, TypedDict

from typer import Typer

cli = Typer()


class OptionMetadata(TypedDict):
    id: str
    name: str
    color: str


FieldType = Literal[
    "singleLineText",
    "multilineText",
    "number",
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
]


class OptionsBase(TypedDict):
    pass


class ResultMetadata(TypedDict):
    type: FieldType
    options: dict[str, Any]


class FormulaFieldOptions(OptionsBase):
    isValid: bool
    formula: str
    referencedFieldIds: list[str]
    result: ResultMetadata


class NamedFieldMetadata(TypedDict):
    id: str
    name: str
    type: FieldType
    description: Optional[str]
    strong_links: list[str]
    weak_links: list[str]
    table: str


class MultipleRecordLinksOptions(OptionsBase):
    linkedTableId: str
    isReversed: bool
    prefersSingleRecordLink: bool
    inverseLinkFieldId: str
    viewIdForRecordSelection: Optional[str]


class MultipleRecordLinksField(NamedFieldMetadata):
    type: Literal["multipleRecordLinks"]
    options: MultipleRecordLinksOptions


class MultipleLookupValuesOptions(OptionsBase):
    isValid: bool
    recordLinkFieldId: str
    fieldIdInLinkedTable: str
    result: ResultMetadata


class MultipleLookupValues(NamedFieldMetadata):
    type: Literal["multipleLookupValues"]
    options: MultipleLookupValuesOptions


class SingleLineTextField(NamedFieldMetadata):
    type: Literal["singleLineText"]


class MultipleAttachmentsOptions(OptionsBase):
    isReversed: bool


class MultipleAttachmentsField(NamedFieldMetadata):
    type: Literal["multipleAttachments"]
    options: MultipleAttachmentsOptions


class NumberFieldOptions(OptionsBase):
    type: Literal["number"]
    precision: int


class NumberField(NamedFieldMetadata):
    type: Literal["number"]
    options: NumberFieldOptions


class MultipleSelectsOptions(OptionsBase):
    choices: list[OptionMetadata]


class MultipleSelectsField(NamedFieldMetadata):
    type: Literal["multipleSelects"]
    options: MultipleSelectsOptions


class SingleSelectField(NamedFieldMetadata):
    type: Literal["singleSelect"]
    options: MultipleSelectsOptions


class MultipleLookupValuesOptions(OptionsBase):
    linkedTableId: str
    prefersSingleRecordLink: bool
    inverseLinkFieldId: str


class FormulaField(NamedFieldMetadata):
    type: Literal["formula"]
    options: FormulaFieldOptions


class CheckboxOptions(OptionsBase):
    icon: str
    color: str


class CheckboxField(NamedFieldMetadata):
    type: Literal["checkbox"]
    options: CheckboxOptions


class DateFormat(TypedDict):
    name: str
    format: str


class DateFieldOptions(OptionsBase):
    dateFormat: DateFormat


class DateField(NamedFieldMetadata):
    type: Literal["date"]
    options: DateFieldOptions


class CreatedTimeFieldOptions(OptionsBase):
    result: ResultMetadata


class CreatedTimeField(NamedFieldMetadata):
    type: Literal["createdTime"]
    options: CreatedTimeFieldOptions


class LastModifiedTimeFieldOptions(OptionsBase):
    isValid: bool
    referencedFieldIds: list[str]
    result: ResultMetadata


class LastModifiedTimeField(NamedFieldMetadata):
    type: Literal["lastModifiedTime"]
    options: LastModifiedTimeFieldOptions


class CountFieldOptions(OptionsBase):
    isValid: bool
    recordLinkFieldId: str


class CountField(NamedFieldMetadata):
    type: Literal["count"]
    options: CountFieldOptions


class RollupFieldOptions(OptionsBase):
    isValid: bool
    recordLinkFieldId: str
    fieldIdInLinkedTable: Optional[str]
    referencedFieldIds: list[str]
    result: ResultMetadata


class RollupField(NamedFieldMetadata):
    type: Literal["rollup"]
    options: RollupFieldOptions


class CollaboratorField(NamedFieldMetadata):
    type: Literal["collaborator"]


class AutoNumberField(NamedFieldMetadata):
    type: Literal["autoNumber"]


class BarcodeField(NamedFieldMetadata):
    type: Literal["barcode"]
    options: dict[str, Any]


class PhoneNumberField(NamedFieldMetadata):
    type: Literal["phoneNumber"]


class EmailField(NamedFieldMetadata):
    type: Literal["email"]


class UrlField(NamedFieldMetadata):
    type: Literal["url"]


class PercentField(NamedFieldMetadata):
    type: Literal["percent"]
    options: NumberFieldOptions


class RatingField(NamedFieldMetadata):
    type: Literal["rating"]
    options: dict[str, Any]


class DurationFieldOptions(OptionsBase):
    durationFormat: str


class DurationField(NamedFieldMetadata):
    type: Literal["duration"]
    options: DurationFieldOptions


class RichTextField(NamedFieldMetadata):
    type: Literal["richText"]


class ButtonField(NamedFieldMetadata):
    type: Literal["button"]


type FieldMetadata = (
    SingleLineTextField
    | FormulaField
    | MultipleSelectsField
    | CheckboxField
    | DateField
    | CreatedTimeField
    | LastModifiedTimeField
    | CountField
    | RollupField
    | CollaboratorField
    | AutoNumberField
    | BarcodeField
    | PhoneNumberField
    | EmailField
    | UrlField
    | PercentField
    | RatingField
    | DurationField
    | RichTextField
    | MultipleRecordLinksField
    | MultipleLookupValues
    | SingleSelectField
    | MultipleAttachmentsField
    | ButtonField
)


class ViewMetadata(TypedDict):
    id: str
    name: str
    type: str


class TableMetadata(TypedDict):
    id: str
    name: str
    primaryFieldId: str
    fields: list[FieldMetadata]
    views: list[ViewMetadata]


class BaseMetadata(TypedDict):
    tables: list[TableMetadata]
    table_lookup: dict[str, TableMetadata]

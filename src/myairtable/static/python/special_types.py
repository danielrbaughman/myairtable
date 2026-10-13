from typing import Optional, TypedDict


class AirtableThumbnail(TypedDict, total=False):
    url: str
    width: int
    height: int


class AirtableThumbnails(TypedDict, total=False):
    small: AirtableThumbnail
    large: AirtableThumbnail
    full: AirtableThumbnail


class AirtableAttachment(TypedDict, total=False):
    id: str
    url: str
    filename: str
    size: int
    type: str
    thumbnails: Optional[AirtableThumbnails]


class AirtableCollaborator(TypedDict, total=False):
    id: str
    email: str
    name: str


class AirtableButton(TypedDict, total=False):
    label: str
    url: Optional[str]


class AirtableAiText(TypedDict, total=False):
    state: str  # "empty", "loading", "generated" or "error"
    isStale: bool
    value: Optional[str]
    errorType: str  # only when state is "error"


RecordId = str

"""Pydantic models for internal v0.3 API responses.

Modeled from shapes OBSERVED in the 2026-06-10 spike (not just the reference
doc) — see docs/airtable-internal-api.md "Spike findings". Key divergences
from the original reference baked in here:

- `lastSortsApplied` is an object `{sortSet, shouldAutoSort, appliedTime}`,
  not a bare array.
- `rowHeight` / `metadata` are absent when a view uses defaults — optional.
- `view/{viwId}/readData` returns the view definition directly under `data`
  (no `viewDatas[]` wrapper) and does NOT include the view's name — names are
  resolved from the base schema.

These models are intentionally separate from the public-API models in
src/meta.py. Unknown keys are ignored (Airtable adds fields constantly);
parse failures surface as EndpointShapeChangedError, not ValidationError.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.alias_generators import to_camel

from .errors import EndpointShapeChangedError


class _InternalModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class ViewFilter(_InternalModel):
    """A filter leaf or a nested filter group (`type: "nested"`)."""

    id: str
    # leaf fields
    column_id: str | None = None
    operator: str | None = None
    value: Any = None
    # nested-group fields (max nesting depth 2)
    type: str | None = None
    conjunction: str | None = None
    filter_set: list["ViewFilter"] | None = None

    @property
    def is_nested(self) -> bool:
        return self.type == "nested"


class FilterConfig(_InternalModel):
    filter_set: list[ViewFilter] = []
    conjunction: str = "and"


class SortSpec(_InternalModel):
    id: str
    column_id: str
    ascending: bool = True


class SortConfig(_InternalModel):
    """Observed shape: object with sortSet — NOT the bare array the original reference described."""

    sort_set: list[SortSpec] = []
    should_auto_sort: bool = True
    applied_time: str | None = None


class GroupLevel(_InternalModel):
    id: str
    column_id: str
    order: str = "ascending"  # "ascending" | "descending"
    empty_group_state: str | None = None  # "hidden" | "visible"


class ColumnOrderEntry(_InternalModel):
    column_id: str
    visibility: bool = True
    width: int | None = None


class ViewDefinition(_InternalModel):
    """Full live definition of a view, from GET /v0.3/view/{viwId}/readData.

    `name` is not part of the readData response — it is attached after
    resolving the view against the base schema.
    """

    id: str
    type: str
    name: str | None = None
    description: str | None = None
    created_by_user_id: str | None = None
    filters: FilterConfig | None = None
    last_sorts_applied: SortConfig | None = None
    group_levels: list[GroupLevel] | None = None
    column_order: list[ColumnOrderEntry] = []
    frozen_column_count: int | None = None
    color_config: dict[str, Any] | None = None
    row_height: str | None = None  # absent when default


class ViewInfo(_InternalModel):
    """Static view metadata from the base schema (application/read)."""

    id: str
    name: str
    type: str
    description: str | None = None
    personal_for_user_id: str | None = None
    created_by_user_id: str | None = None


class ViewSection(_InternalModel):
    """A sidebar view section (vsc...). Section membership lives in `view_order`."""

    id: str
    name: str
    view_order: list[str] = []
    pinned_for_user_id: str | None = None
    created_by_user_id: str | None = None


class TableViews(_InternalModel):
    """The view-related slice of a tableSchema from application/read.

    `view_order` interleaves viw... and vsc... IDs in sidebar display order.
    """

    id: str
    name: str
    views: list[ViewInfo] = []
    view_order: list[str] = []
    view_sections_by_id: dict[str, ViewSection] = {}


def parse_view_definition(data: dict[str, Any]) -> ViewDefinition:
    try:
        return ViewDefinition.model_validate(data)
    except ValidationError as e:
        raise EndpointShapeChangedError("view/{viwId}/readData", str(e)) from e


def parse_table_views(table_schema: dict[str, Any]) -> TableViews:
    try:
        return TableViews.model_validate(table_schema)
    except ValidationError as e:
        raise EndpointShapeChangedError("application/{appId}/read", str(e)) from e

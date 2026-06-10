"""Tests for src/internal_api/ — models, name resolution, section assembly, IDs.

Fixtures are synthetic but mirror the response shapes observed in the
2026-06-10 spike (docs/airtable-internal-api.md, "Spike findings"). No
network, no playwright — the transport is monkeypatched.
"""

import pytest

from src.internal_api import tools
from src.internal_api.errors import EndpointShapeChangedError, InternalApiError
from src.internal_api.ids import generate_id, generate_request_id, validate_airtable_id
from src.internal_api.models import (
    TableViews,
    parse_table_views,
    parse_view_definition,
)

# --- fixtures (spike-observed shapes) --------------------------------------

VIEW_READDATA = {
    "id": "viwAAAAAAAAAAAAAA",
    "type": "grid",
    "filters": {
        "filterSet": [
            {"id": "fltAAAAAAAAAAAAAA", "columnId": "fldAAAAAAAAAAAAAA", "operator": "contains", "value": "x"},
            {
                "id": "fltBBBBBBBBBBBBBB",
                "type": "nested",
                "conjunction": "or",
                "filterSet": [
                    {"id": "fltCCCCCCCCCCCCCC", "columnId": "fldBBBBBBBBBBBBBB", "operator": "=", "value": 1},
                ],
            },
        ],
        "conjunction": "and",
    },
    # observed: an OBJECT with sortSet, not a bare array
    "lastSortsApplied": {
        "sortSet": [{"id": "srtAAAAAAAAAAAAAA", "columnId": "fldAAAAAAAAAAAAAA", "ascending": True}],
        "shouldAutoSort": True,
        "appliedTime": "2025-09-23T23:37:56.338Z",
    },
    "groupLevels": None,
    "columnOrder": [
        {"columnId": "fldAAAAAAAAAAAAAA", "visibility": True},
        {"columnId": "fldBBBBBBBBBBBBBB", "visibility": False, "width": 264},
    ],
    "frozenColumnCount": 2,
    "colorConfig": None,
    "description": None,
    # observed extras we ignore
    "rowOrder": [{"rowId": "recAAAAAAAAAAAAAA"}],
    "sharesById": {},
    "applicationTransactionNumber": 1234,
}

TABLE_SCHEMA = {
    "id": "tblAAAAAAAAAAAAAA",
    "name": "Contacts",
    "views": [
        {"id": "viwAAAAAAAAAAAAAA", "name": "Grid A", "type": "grid", "description": "main", "personalForUserId": None},
        {"id": "viwBBBBBBBBBBBBBB", "name": "Grid B", "type": "grid"},
        {"id": "viwCCCCCCCCCCCCCC", "name": "Cal", "type": "calendar"},
    ],
    "viewOrder": ["vscAAAAAAAAAAAAAA", "viwCCCCCCCCCCCCCC"],
    "viewSectionsById": {
        "vscAAAAAAAAAAAAAA": {
            "id": "vscAAAAAAAAAAAAAA",
            "name": "Daily",
            "viewOrder": ["viwAAAAAAAAAAAAAA", "viwBBBBBBBBBBBBBB"],
            "pinnedForUserId": None,
        }
    },
    "columns": [
        {"id": "fldAAAAAAAAAAAAAA", "name": "Name", "type": "text"},
        {"id": "fldBBBBBBBBBBBBBB", "name": "Status", "type": "select", "description": "stage"},
    ],
    "primaryColumnId": "fldAAAAAAAAAAAAAA",
    # observed extras we ignore
    "meaningfulColumnOrder": [],
}


# --- models -----------------------------------------------------------------


def test_parse_view_definition_observed_shape():
    d = parse_view_definition(VIEW_READDATA)
    assert d.id == "viwAAAAAAAAAAAAAA"
    assert d.type == "grid"
    assert d.frozen_column_count == 2
    assert d.filters is not None
    assert d.filters.conjunction == "and"
    assert len(d.filters.filter_set) == 2
    leaf, nested = d.filters.filter_set
    assert not leaf.is_nested and leaf.operator == "contains"
    assert nested.is_nested and nested.conjunction == "or"
    assert nested.filter_set is not None and nested.filter_set[0].value == 1
    assert d.last_sorts_applied is not None
    assert d.last_sorts_applied.should_auto_sort is True
    assert d.last_sorts_applied.sort_set[0].column_id == "fldAAAAAAAAAAAAAA"
    assert d.group_levels is None
    assert [c.visibility for c in d.column_order] == [True, False]
    assert d.column_order[1].width == 264
    assert d.row_height is None  # absent when default


def test_parse_view_definition_dump_excludes_observed_extras():
    dumped = parse_view_definition(VIEW_READDATA).model_dump(mode="json")
    assert "rowOrder" not in dumped and "row_order" not in dumped
    assert "sharesById" not in dumped and "shares_by_id" not in dumped


def test_row_count_captured_from_row_order():
    d = parse_view_definition(VIEW_READDATA)
    assert d.row_count == 1  # one entry in fixture rowOrder

    visible_mix = {
        **VIEW_READDATA,
        "rowOrder": [
            {"rowId": "recAAAAAAAAAAAAAA", "visibility": True},
            {"rowId": "recBBBBBBBBBBBBBB", "visibility": False},
            {"rowId": "recCCCCCCCCCCCCCC", "visibility": True},
        ],
    }
    assert parse_view_definition(visible_mix).row_count == 2

    no_row_order = {k: v for k, v in VIEW_READDATA.items() if k != "rowOrder"}
    assert parse_view_definition(no_row_order).row_count is None


def test_parse_view_definition_shape_change_raises():
    with pytest.raises(EndpointShapeChangedError):
        parse_view_definition({"filters": "not-a-view"})


def test_parse_table_views():
    t = parse_table_views(TABLE_SCHEMA)
    assert t.name == "Contacts"
    assert [v.name for v in t.views] == ["Grid A", "Grid B", "Cal"]
    assert t.view_sections_by_id["vscAAAAAAAAAAAAAA"].view_order == ["viwAAAAAAAAAAAAAA", "viwBBBBBBBBBBBBBB"]
    assert [(c.id, c.name, c.type) for c in t.columns] == [
        ("fldAAAAAAAAAAAAAA", "Name", "text"),
        ("fldBBBBBBBBBBBBBB", "Status", "select"),
    ]
    assert t.primary_column_id == "fldAAAAAAAAAAAAAA"


# --- tools (transport monkeypatched) ----------------------------------------


@pytest.fixture
def fake_schema(monkeypatch):
    tables = [TableViews.model_validate(TABLE_SCHEMA)]
    monkeypatch.setattr(tools, "_read_table_views", lambda force_refresh=False: tables)
    monkeypatch.setattr("src.internal_api.tools.get_base_id", lambda: "appAAAAAAAAAAAAAA")
    return tables


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, path, object_params=None, app_id=None):
        self.calls.append(path)
        return self.response


def test_get_view_resolves_names_and_attaches_table_info(fake_schema, monkeypatch):
    fake = FakeTransport({"data": VIEW_READDATA})
    monkeypatch.setattr(tools, "_get_transport", lambda: fake)

    result = tools.get_view("contacts", "grid a")  # case-insensitive names
    assert fake.calls == ["/v0.3/view/viwAAAAAAAAAAAAAA/readData"]
    assert result["name"] == "Grid A"
    assert result["description"] == "main"  # backfilled from schema
    assert result["table_id"] == "tblAAAAAAAAAAAAAA"
    assert result["table_name"] == "Contacts"
    assert result["filters"]["conjunction"] == "and"


def test_get_view_by_ids(fake_schema, monkeypatch):
    fake = FakeTransport({"data": VIEW_READDATA})
    monkeypatch.setattr(tools, "_get_transport", lambda: fake)
    result = tools.get_view("tblAAAAAAAAAAAAAA", "viwAAAAAAAAAAAAAA")
    assert result["id"] == "viwAAAAAAAAAAAAAA"


def test_get_view_unknown_table_lists_available(fake_schema):
    with pytest.raises(InternalApiError, match="Available tables: Contacts"):
        tools.get_view("Nope", "Grid A")


def test_get_view_unknown_view_lists_available(fake_schema):
    with pytest.raises(InternalApiError, match="Available views: Grid A, Grid B, Cal"):
        tools.get_view("Contacts", "Nope")


def test_get_all_view_definitions_collects_errors(fake_schema, monkeypatch):
    """One view 403s -> scan still returns the other definitions plus the error."""

    class PartialTransport:
        def get(self, path, object_params=None, app_id=None):
            if "viwBBBBBBBBBBBBBB" in path:
                raise InternalApiError("simulated failure")
            return {"data": {**VIEW_READDATA, "id": path.split("/")[3]}}

    monkeypatch.setattr(tools, "_get_transport", lambda: PartialTransport())
    monkeypatch.setattr(tools, "_view_cache", {})

    [table] = fake_schema
    definitions, errors = tools.get_all_view_definitions(table)
    assert set(definitions) == {"viwAAAAAAAAAAAAAA", "viwCCCCCCCCCCCCCC"}
    assert definitions["viwAAAAAAAAAAAAAA"].name == "Grid A"  # name attached from schema
    assert list(errors) == ["viwBBBBBBBBBBBBBB"]
    assert "simulated failure" in errors["viwBBBBBBBBBBBBBB"]


def test_fetch_view_definition_uses_cache(fake_schema, monkeypatch):
    calls = []

    class CountingTransport:
        def get(self, path, object_params=None, app_id=None):
            calls.append(path)
            return {"data": VIEW_READDATA}

    monkeypatch.setattr(tools, "_get_transport", lambda: CountingTransport())
    monkeypatch.setattr(tools, "_view_cache", {})

    [table] = fake_schema
    tools._fetch_view_definition(table, "viwAAAAAAAAAAAAAA")
    tools._fetch_view_definition(table, "viwAAAAAAAAAAAAAA")
    assert len(calls) == 1  # second call served from cache


def test_get_view_sections_assembly(fake_schema):
    [result] = tools.get_view_sections("Contacts")
    assert result["table_name"] == "Contacts"
    [section] = result["sections"]
    assert section["name"] == "Daily"
    assert [v["name"] for v in section["views"]] == ["Grid A", "Grid B"]
    # Cal is in viewOrder but not in any section
    assert [v["name"] for v in result["ungrouped_views"]] == ["Cal"]


# --- ids ---------------------------------------------------------------------


def test_generate_ids():
    assert generate_request_id().startswith("req")
    assert len(generate_request_id()) == 17
    assert len(generate_id("pgl", 13)) == 16


def test_validate_airtable_id():
    assert validate_airtable_id("tblAAAAAAAAAAAAAA") == "tblAAAAAAAAAAAAAA"
    with pytest.raises(ValueError):
        validate_airtable_id("../etc/passwd")
    with pytest.raises(ValueError):
        validate_airtable_id("tbl/evil")

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
    # shares ARE modeled (for audit_shares) but excluded from get_view output —
    # see test_get_view_output_excludes_shares


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


def test_find_views_using_field(fake_schema, monkeypatch):
    """Field used in: Grid A filter (top-level + nested), Grid A sort; hidden in Grid B."""

    grid_a = {
        **VIEW_READDATA,
        "id": "viwAAAAAAAAAAAAAA",
    }
    grid_b = {
        "id": "viwBBBBBBBBBBBBBB",
        "type": "grid",
        "filters": None,
        "lastSortsApplied": {"sortSet": [], "shouldAutoSort": True},
        "groupLevels": [{"id": "glvAAAAAAAAAAAAAA", "columnId": "fldBBBBBBBBBBBBBB", "order": "descending"}],
        "columnOrder": [{"columnId": "fldAAAAAAAAAAAAAA", "visibility": False}],
        "rowOrder": [],
    }
    cal = {
        "id": "viwCCCCCCCCCCCCCC",
        "type": "calendar",
        "filters": None,
        "columnOrder": [],
        "rowOrder": [],
    }
    responses = {"viwAAAAAAAAAAAAAA": grid_a, "viwBBBBBBBBBBBBBB": grid_b, "viwCCCCCCCCCCCCCC": cal}

    class MappedTransport:
        def get(self, path, object_params=None, app_id=None):
            return {"data": responses[path.split("/")[3]]}

    monkeypatch.setattr(tools, "_get_transport", lambda: MappedTransport())
    monkeypatch.setattr(tools, "_view_cache", {})

    # fldAAA: filter (leaf 'contains') + sort in Grid A; hidden in Grid B
    result = tools.find_views_using_field("Contacts", "Name")
    assert result["field"] == {"id": "fldAAAAAAAAAAAAAA", "name": "Name", "type": "text"}
    assert result["summary"]["views_scanned"] == 3
    assert result["summary"]["views_using_field"] == 1
    assert result["summary"]["by_kind"] == {"filter": 1, "sort": 1}
    assert result["summary"]["visible_in"] == 1  # Grid A
    assert result["summary"]["hidden_in"] == 1  # Grid B
    [usage_view] = result["views"]
    assert usage_view["name"] == "Grid A"
    kinds = {u["kind"] for u in usage_view["usage"]}
    assert kinds == {"filter", "sort"}

    # fldBBB: nested filter in Grid A + group in Grid B
    monkeypatch.setattr(tools, "_view_cache", {})
    result = tools.find_views_using_field("Contacts", "fldBBBBBBBBBBBBBB")
    assert result["summary"]["by_kind"] == {"filter": 1, "group": 1}
    names = [v["name"] for v in result["views"]]
    assert names == ["Grid A", "Grid B"]
    grid_a_usage = next(v for v in result["views"] if v["name"] == "Grid A")
    assert grid_a_usage["usage"] == [{"kind": "filter", "operators": ["="]}]  # found inside nested group


def test_find_views_using_field_unknown_field(fake_schema):
    with pytest.raises(InternalApiError, match="Available fields: Name, Status"):
        tools.find_views_using_field("Contacts", "Nope")


def _counting_responses():
    """Grid A: filtered, 2 rows. Grid B: unfiltered, 5 rows. Cal: unfiltered, 3 rows."""
    return {
        "viwAAAAAAAAAAAAAA": {
            **VIEW_READDATA,
            "rowOrder": [{"rowId": "rec1", "visibility": True}, {"rowId": "rec2", "visibility": True}],
        },
        "viwBBBBBBBBBBBBBB": {
            "id": "viwBBBBBBBBBBBBBB",
            "type": "grid",
            "filters": {"filterSet": [], "conjunction": "and"},
            "columnOrder": [],
            "rowOrder": [{"rowId": f"rec{i}", "visibility": True} for i in range(5)],
        },
        "viwCCCCCCCCCCCCCC": {
            "id": "viwCCCCCCCCCCCCCC",
            "type": "calendar",
            "filters": None,
            "columnOrder": [],
            "rowOrder": [{"rowId": f"rec{i}", "visibility": True} for i in range(3)],
        },
    }


def test_count_records_all_views(fake_schema, monkeypatch):
    responses = _counting_responses()

    class MappedTransport:
        def get(self, path, object_params=None, app_id=None):
            return {"data": responses[path.split("/")[3]]}

    monkeypatch.setattr(tools, "_get_transport", lambda: MappedTransport())
    monkeypatch.setattr(tools, "_view_cache", {})

    result = tools.count_records("Contacts")
    assert result["total_records"] == 5  # max over unfiltered views (Grid B)
    assert result["total_is_exact"] is True
    by_name = {v["name"]: v for v in result["views"]}
    assert by_name["Grid A"]["row_count"] == 2 and by_name["Grid A"]["is_filtered"] is True
    assert by_name["Grid B"]["row_count"] == 5 and by_name["Grid B"]["is_filtered"] is False


def test_count_records_single_view(fake_schema, monkeypatch):
    responses = _counting_responses()

    class MappedTransport:
        def get(self, path, object_params=None, app_id=None):
            return {"data": responses[path.split("/")[3]]}

    monkeypatch.setattr(tools, "_get_transport", lambda: MappedTransport())
    monkeypatch.setattr(tools, "_view_cache", {})

    result = tools.count_records("Contacts", "grid a")
    assert result["row_count"] == 2
    assert result["is_filtered"] is True
    assert result["view"]["name"] == "Grid A"


def test_count_records_total_lower_bound_when_all_filtered(fake_schema, monkeypatch):
    responses = _counting_responses()
    # make every view filtered
    for r in responses.values():
        r["filters"] = {
            "filterSet": [{"id": "fltZZZZZZZZZZZZZZ", "columnId": "fldAAAAAAAAAAAAAA", "operator": "=", "value": 1}],
            "conjunction": "and",
        }

    class MappedTransport:
        def get(self, path, object_params=None, app_id=None):
            return {"data": responses[path.split("/")[3]]}

    monkeypatch.setattr(tools, "_get_transport", lambda: MappedTransport())
    monkeypatch.setattr(tools, "_view_cache", {})

    result = tools.count_records("Contacts")
    assert result["total_records"] == 5
    assert result["total_is_exact"] is False


AUDIT_TABLE_SCHEMA = {
    "id": "tblAAAAAAAAAAAAAA",
    "name": "Contacts",
    "views": [
        {"id": "viwAAAAAAAAAAAAAA", "name": "Main Grid", "type": "grid"},  # default — never unfiltered-flagged
        {"id": "viwBBBBBBBBBBBBBB", "name": "Pipeline copy", "type": "grid", "personalForUserId": "usrXXXXXXXXXXXXXX"},
        {"id": "viwCCCCCCCCCCCCCC", "name": "Quarterly Review", "type": "grid"},
    ],
    "viewOrder": ["viwAAAAAAAAAAAAAA", "viwBBBBBBBBBBBBBB", "viwCCCCCCCCCCCCCC"],
    "viewSectionsById": {},
    "columns": [{"id": "fldAAAAAAAAAAAAAA", "name": "Name", "type": "text"}],
}


def test_audit_views(monkeypatch):
    tables = [TableViews.model_validate(AUDIT_TABLE_SCHEMA)]
    monkeypatch.setattr(tools, "_read_table_views", lambda force_refresh=False: tables)
    monkeypatch.setattr("src.internal_api.tools.get_base_id", lambda: "appAAAAAAAAAAAAAA")

    responses = {
        # default grid: unfiltered but exempt; stale sort from 2020
        "viwAAAAAAAAAAAAAA": {
            "id": "viwAAAAAAAAAAAAAA",
            "type": "grid",
            "filters": None,
            "lastSortsApplied": {
                "sortSet": [{"id": "srtAAAAAAAAAAAAAA", "columnId": "fldAAAAAAAAAAAAAA", "ascending": True}],
                "shouldAutoSort": True,
                "appliedTime": "2020-01-01T00:00:00.000Z",
            },
            "columnOrder": [],
            "rowOrder": [{"rowId": "rec1", "visibility": True}],
        },
        # personal + 'copy' name + unfiltered + empty
        "viwBBBBBBBBBBBBBB": {
            "id": "viwBBBBBBBBBBBBBB",
            "type": "grid",
            "filters": {"filterSet": [], "conjunction": "and"},
            "columnOrder": [],
            "rowOrder": [],
        },
        # clean filtered view: no flags
        "viwCCCCCCCCCCCCCC": {
            "id": "viwCCCCCCCCCCCCCC",
            "type": "grid",
            "filters": {
                "filterSet": [{"id": "fltAAAAAAAAAAAAAA", "columnId": "fldAAAAAAAAAAAAAA", "operator": "=", "value": 1}],
                "conjunction": "and",
            },
            "columnOrder": [],
            "rowOrder": [{"rowId": "rec1", "visibility": True}],
        },
    }

    class MappedTransport:
        def get(self, path, object_params=None, app_id=None):
            return {"data": responses[path.split("/")[3]]}

    monkeypatch.setattr(tools, "_get_transport", lambda: MappedTransport())
    monkeypatch.setattr(tools, "_view_cache", {})

    result = tools.audit_views()
    assert result["summary"]["views_scanned"] == 3
    assert result["summary"]["views_flagged"] == 2

    [report] = result["tables"]
    by_name = {v["name"]: v for v in report["views_flagged"]}

    main_kinds = [f["kind"] for f in by_name["Main Grid"]["flags"]]
    assert main_kinds == ["stale_sort"]  # default grid exempt from unfiltered_grid

    copy_kinds = sorted(f["kind"] for f in by_name["Pipeline copy"]["flags"])
    assert copy_kinds == ["empty", "personal", "suspicious_name", "unfiltered_grid"]

    assert "Quarterly Review" not in by_name
    assert result["summary"]["by_kind"]["personal"] == 1


def test_suspicious_name_patterns():
    assert tools._suspicious_name("Pipeline copy") == "copy"
    assert tools._suspicious_name("Copy of Main") == "copy"
    assert tools._suspicious_name("test view") == "test"
    assert tools._suspicious_name("Grid (2)") == "numbered duplicate"
    assert tools._suspicious_name("Quarterly Review") is None
    assert tools._suspicious_name("Latest deals") is None  # 'test' inside a word doesn't match


class _FakePublicField:
    def __init__(self, id, name, type="singleLineText", referenced_ids=None, formula_refs=None):
        self.id = id
        self.name = name
        self.type = type

        class _Opts:
            referenced_field_ids = referenced_ids or []
            field_id_in_linked_table = None
            record_link_field_id = None

        self.options = _Opts()
        self._formula_refs = formula_refs or []

    def is_computed(self):
        return self.type in ("formula", "rollup", "multipleLookupValues", "count")

    def is_formula(self):
        return self.type == "formula"

    def get_field_ids_from_formula(self):
        return self._formula_refs


class _FakePublicBase:
    def __init__(self, tables):
        self.tables = tables

    def fields(self):
        return [f for t in self.tables for f in t.fields]


class _FakePublicTable:
    def __init__(self, id, fields):
        self.id = id
        self.fields = fields


def test_find_unused_fields(fake_schema, monkeypatch):
    fields = [
        _FakePublicField("fldAAAAAAAAAAAAAA", "Name"),  # primary -> skipped
        _FakePublicField("fldBBBBBBBBBBBBBB", "Status"),  # hidden everywhere + unreferenced; used in a nested filter
        _FakePublicField("fldDDDDDDDDDDDDDD", "Notes"),  # absent from views entirely + unreferenced
        _FakePublicField("fldEEEEEEEEEEEEEE", "Amount"),  # referenced by a formula -> only 1 signal
        _FakePublicField("fldFFFFFFFFFFFFFF", "Calc", type="formula", formula_refs=["fldEEEEEEEEEEEEEE"]),  # computed -> skipped
    ]
    fake_base = _FakePublicBase([_FakePublicTable("tblAAAAAAAAAAAAAA", fields)])
    monkeypatch.setattr("src.meta.Base", lambda: fake_base)

    fake = FakeTransport({"data": VIEW_READDATA})
    monkeypatch.setattr(tools, "_get_transport", lambda: fake)
    monkeypatch.setattr(tools, "_view_cache", {})

    result = tools.find_unused_fields("Contacts")
    assert result["summary"]["fields_scanned"] == 3  # primary + computed excluded
    by_name = {f["name"]: f for f in result["fields"]}

    # Status: hidden in the view, no formula refs, but IS in a nested filter
    # (the fake transport serves the same viewData for all 3 views -> 3 uses)
    assert sorted(by_name["Status"]["signals"]) == ["hidden_in_all_views", "no_formula_references"]
    assert by_name["Status"]["evidence"]["view_config_uses"] == 3

    # Notes: unreferenced + in no view config (not present in any columnOrder)
    assert sorted(by_name["Notes"]["signals"]) == ["no_formula_references", "not_in_view_config"]

    # Amount: referenced by the Calc formula -> 1 signal only, below min_signals=2
    assert "Amount" not in by_name
    assert result["caveats"]


def test_find_unused_fields_min_signals_one(fake_schema, monkeypatch):
    fields = [_FakePublicField("fldEEEEEEEEEEEEEE", "Amount", referenced_ids=[])]
    fake_base = _FakePublicBase([_FakePublicTable("tblAAAAAAAAAAAAAA", fields)])
    monkeypatch.setattr("src.meta.Base", lambda: fake_base)
    monkeypatch.setattr(tools, "_get_transport", lambda: FakeTransport({"data": VIEW_READDATA}))
    monkeypatch.setattr(tools, "_view_cache", {})

    result = tools.find_unused_fields("Contacts", min_signals=1)
    [field] = result["fields"]
    assert field["name"] == "Amount"


BASE_SHARE = {
    "id": "shrBASEAAAAAAAAAA",
    "modelId": "appAAAAAAAAAAAAAA",
    "createdByUserId": "usrXXXXXXXXXXXXXX",
    "canBeCloned": False,
    "canBeExported": False,
    "includeHiddenColumns": False,
    "includeBlocks": False,
    "emailDomain": None,
    "hasPassword": True,
}

VIEW_SHARE = {
    "id": "shrVIEWAAAAAAAAAA",
    "modelId": "viwAAAAAAAAAAAAAA",
    "createdByUserId": "usrXXXXXXXXXXXXXX",
    "canBeCloned": False,
    "canBeExported": True,
    "includeHiddenColumns": False,
    "includeBlocks": False,
    "emailDomain": "rogoag.com",
    "hasPassword": False,
}


def test_audit_shares(monkeypatch):
    from src.internal_api.models import ShareInfo

    tables = [TableViews.model_validate(TABLE_SCHEMA)]
    base_shares = [ShareInfo.model_validate(BASE_SHARE)]
    monkeypatch.setattr(tools, "_read_application_data", lambda force_refresh=False: tools.ApplicationData(tables, base_shares, []))
    monkeypatch.setattr("src.internal_api.tools.get_base_id", lambda: "appAAAAAAAAAAAAAA")

    responses = {
        "viwAAAAAAAAAAAAAA": {**VIEW_READDATA, "sharesById": {"shrVIEWAAAAAAAAAA": VIEW_SHARE}},
        "viwBBBBBBBBBBBBBB": {"id": "viwBBBBBBBBBBBBBB", "type": "grid", "columnOrder": [], "rowOrder": []},
        "viwCCCCCCCCCCCCCC": {"id": "viwCCCCCCCCCCCCCC", "type": "calendar", "columnOrder": [], "rowOrder": []},
    }

    class MappedTransport:
        def get(self, path, object_params=None, app_id=None):
            return {"data": responses[path.split("/")[3]]}

    monkeypatch.setattr(tools, "_get_transport", lambda: MappedTransport())
    monkeypatch.setattr(tools, "_view_cache", {})

    result = tools.audit_shares()
    assert result["summary"] == {
        "total_shares": 2,
        "base_shares": 1,
        "view_shares": 1,
        "exportable": 1,
        "password_protected": 1,
        "domain_restricted": 1,
        "views_scanned": 3,
    }
    by_scope = {s["scope"]: s for s in result["shares"]}
    assert by_scope["base"]["url"] == "https://airtable.com/shrBASEAAAAAAAAAA"
    assert by_scope["base"]["has_password"] is True
    view_share = by_scope["view"]
    assert view_share["url"] == "https://airtable.com/shrVIEWAAAAAAAAAA"
    assert view_share["table_name"] == "Contacts"
    assert view_share["view_name"] == "Grid A"
    assert view_share["can_be_exported"] is True
    assert view_share["email_domain"] == "rogoag.com"


def test_audit_shares_table_scope_excludes_base_shares(monkeypatch):
    from src.internal_api.models import ShareInfo

    tables = [TableViews.model_validate(TABLE_SCHEMA)]
    base_shares = [ShareInfo.model_validate(BASE_SHARE)]
    monkeypatch.setattr(tools, "_read_application_data", lambda force_refresh=False: tools.ApplicationData(tables, base_shares, []))
    monkeypatch.setattr(tools, "_read_table_views", lambda force_refresh=False: tables)
    monkeypatch.setattr("src.internal_api.tools.get_base_id", lambda: "appAAAAAAAAAAAAAA")
    monkeypatch.setattr(tools, "_get_transport", lambda: FakeTransport({"data": VIEW_READDATA}))
    monkeypatch.setattr(tools, "_view_cache", {})

    result = tools.audit_shares("Contacts")
    assert result["summary"]["base_shares"] == 0


def test_get_view_output_excludes_shares(fake_schema, monkeypatch):
    response = {**VIEW_READDATA, "sharesById": {"shrVIEWAAAAAAAAAA": VIEW_SHARE}}
    monkeypatch.setattr(tools, "_get_transport", lambda: FakeTransport({"data": response}))
    monkeypatch.setattr(tools, "_view_cache", {})

    result = tools.get_view("Contacts", "Grid A")
    assert "shares_by_id" not in result and "sharesById" not in result


PAGE_BUNDLE = {
    "id": "pbdAAAAAAAAAAAAAA",
    "name": "Lab Issue Mgmt",
    "description": None,
    "color": "green",
    "icon": "beaker",
    "firstPagePublishedTime": "2023-01-12T02:02:51.000Z",
    "lastPublishedTime": "2023-01-12T02:02:51.000Z",
    "pages": [
        {
            "id": "pagAAAAAAAAAAAAAA",
            "metadata": {"type": "entry", "name": "Issues", "description": None},
            "isPublished": True,
            "lastPublishedRevisionChangeTime": "2023-01-12T02:02:51.000Z",
            "lastWorkingDraftModifiedTime": "2023-01-12T01:58:54.000Z",
        },
        {
            "id": "pagBBBBBBBBBBBBBB",
            "metadata": {"type": "entry", "name": None},
            "isPublished": False,
        },
    ],
}


def test_list_interfaces(monkeypatch):
    from src.internal_api.models import InterfaceBundle

    interfaces = [InterfaceBundle.model_validate(PAGE_BUNDLE)]
    monkeypatch.setattr(tools, "_read_application_data", lambda force_refresh=False: tools.ApplicationData([], [], interfaces))
    monkeypatch.setattr("src.internal_api.tools.get_base_id", lambda: "appAAAAAAAAAAAAAA")

    result = tools.list_interfaces()
    assert result["summary"] == {"interfaces": 1, "published": 1, "pages": 2}
    [iface] = result["interfaces"]
    assert iface["name"] == "Lab Issue Mgmt"
    assert iface["url"] == "https://airtable.com/appAAAAAAAAAAAAAA/pbdAAAAAAAAAAAAAA"
    assert iface["is_published"] is True
    assert [p["name"] for p in iface["pages"]] == ["Issues", "Untitled"]
    assert iface["pages"][1]["is_published"] is False


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

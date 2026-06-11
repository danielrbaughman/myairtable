"""Tests for src/internal_api/type_resolver.py — normalization + schema extraction.

Fixtures mirror the typeOptions shapes observed in the 2026-06-10 spike
(docs/airtable-internal-api.md, "computed-field type resolution").
"""

from src.internal_api import type_resolver


def test_normalize_text():
    assert type_resolver.normalize_result_type({"resultType": "text", "resultIsArray": False}) == ("singleLineText", False)


def test_normalize_number_plain_and_formats():
    assert type_resolver.normalize_result_type({"resultType": "number"}) == ("number", False)
    assert type_resolver.normalize_result_type({"resultType": "number", "format": "currency", "symbol": "$"}) == ("currency", False)
    assert type_resolver.normalize_result_type({"resultType": "number", "format": "percentV2"}) == ("percent", False)
    assert type_resolver.normalize_result_type({"resultType": "number", "format": "duration"}) == ("duration", False)


def test_normalize_date_vs_datetime():
    assert type_resolver.normalize_result_type({"resultType": "date", "isDateTime": False}) == ("date", False)
    assert type_resolver.normalize_result_type({"resultType": "date", "isDateTime": True}) == ("dateTime", False)


def test_normalize_checkbox_and_array():
    assert type_resolver.normalize_result_type({"resultType": "checkbox"}) == ("checkbox", False)
    # multi-value lookup of a text field
    assert type_resolver.normalize_result_type({"resultType": "text", "resultIsArray": True}) == ("singleLineText", True)


def test_normalize_missing_result_type():
    assert type_resolver.normalize_result_type({}) is None
    assert type_resolver.normalize_result_type({"resultType": None}) is None


def test_normalize_internal_vocabulary():
    # internal names differ from public FieldType names
    assert type_resolver.normalize_result_type({"resultType": "phone"}) == ("phoneNumber", False)
    assert type_resolver.normalize_result_type({"resultType": "select"}) == ("singleSelect", False)
    assert type_resolver.normalize_result_type({"resultType": "multiSelect"}) == ("multipleSelects", False)
    assert type_resolver.normalize_result_type({"resultType": "foreignKey"}) == ("multipleRecordLinks", False)
    assert type_resolver.normalize_result_type({"resultType": "multipleAttachment", "resultIsArray": True}) == ("multipleAttachments", True)
    assert type_resolver.normalize_result_type({"resultType": "multilineText"}) == ("multilineText", False)


def test_normalize_unknown_skips():
    # unrecognized internal type -> None (fall back to existing inference, no invalid type)
    assert type_resolver.normalize_result_type({"resultType": "futuristicType"}) is None


_FAKE_SCHEMA = {
    "data": {
        "tableSchemas": [
            {
                "id": "tbl1",
                "columns": [
                    {"id": "fldPlain", "type": "singleLineText"},  # not computed -> skipped
                    {"id": "fldFormula", "type": "formula", "typeOptions": {"resultType": "text", "resultIsArray": False}},
                    {"id": "fldRollup", "type": "rollup", "typeOptions": {"resultType": "number", "resultIsArray": False}},
                    {"id": "fldCount", "type": "count", "typeOptions": {"resultType": "number"}},
                    # lookups are internal type "lookup", carrying currency format + array
                    {"id": "fldLookup", "type": "lookup", "typeOptions": {"resultType": "number", "format": "currency", "resultIsArray": True}},
                    {"id": "fldNoResult", "type": "formula", "typeOptions": {}},  # no resultType -> skipped
                ],
            }
        ]
    }
}


def test_resolve_field_types(monkeypatch):
    monkeypatch.setattr(type_resolver, "raw_application_read", lambda: _FAKE_SCHEMA)

    resolved = type_resolver.resolve_field_types()
    assert set(resolved) == {"fldFormula", "fldRollup", "fldCount", "fldLookup"}
    assert resolved["fldFormula"] == {"result_type": "singleLineText", "is_array": False, "source": "internal_schema"}
    assert resolved["fldRollup"]["result_type"] == "number"
    assert resolved["fldLookup"] == {"result_type": "currency", "is_array": True, "source": "internal_schema"}
    assert "fldPlain" not in resolved  # non-computed excluded
    assert "fldNoResult" not in resolved  # no resultType excluded


def test_write_and_load_type_map(monkeypatch, tmp_path):
    monkeypatch.setattr(type_resolver, "raw_application_read", lambda: _FAKE_SCHEMA)
    monkeypatch.setattr("src.meta.get_base_id", lambda: "appTESTBASE000000")

    dest = type_resolver.write_type_map(tmp_path)
    assert dest == tmp_path / "type_map.json"
    import json

    payload = json.loads(dest.read_text())
    assert payload["base_id"] == "appTESTBASE000000"
    assert "generated_at" in payload
    assert payload["fields"]["fldLookup"]["result_type"] == "currency"

    # load by folder and by direct file path
    by_folder = type_resolver.load_type_map(tmp_path)
    assert by_folder["fldRollup"]["result_type"] == "number"
    assert type_resolver.load_type_map(dest) == by_folder


def test_load_type_map_absent_returns_empty(tmp_path):
    assert type_resolver.load_type_map(tmp_path) == {}
    assert type_resolver.load_type_map(tmp_path / "nope.json") == {}

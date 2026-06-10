"""Tests for src/internal_api/result_store.py — schema inference + offload.

No network; offload is exercised against synthetic results with the threshold
and OUTPUT_DIR redirected to a tmp dir.
"""

import json

import pytest

from src.internal_api import result_store


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(result_store, "OUTPUT_DIR", tmp_path)
    monkeypatch.setenv("MYAIRTABLE_INLINE_MAX_BYTES", "200")  # tiny so we trip easily
    return tmp_path


# --- infer_schema -----------------------------------------------------------


def test_infer_schema_scalars_and_sorted_keys():
    schema = result_store.infer_schema({"b": 1, "a": "x", "c": True, "d": None, "e": 1.5})
    assert list(schema.keys()) == ["a", "b", "c", "d", "e"]  # sorted
    assert schema == {"a": "str", "b": "int", "c": "bool", "d": "null", "e": "float"}


def test_infer_schema_list_merges_elements():
    data = {"rows": [{"a": 1}, {"a": 2, "b": "x"}]}
    schema = result_store.infer_schema(data)
    tag, meta = schema["rows"]
    assert tag == "<obj>"
    assert meta["len"] == 2
    assert meta["items"] == {"a": "int", "b": "str"}  # union of keys, sorted


def test_infer_schema_empty_list():
    assert result_store.infer_schema({"xs": []}) == {"xs": []}


def test_infer_schema_depth_cap_fires():
    deep = {"a": {"b": {"c": {"d": {"e": 1}}}}}
    schema = result_store.infer_schema(deep, max_depth=3)
    # a(1) -> b(2) -> c(3) -> stop at depth 3
    assert schema["a"]["b"]["c"] == "...(depth>3)"
    assert schema["_truncated"] is True


def test_infer_schema_breadth_cap():
    wide = {f"k{i}": i for i in range(10)}
    schema = result_store.infer_schema(wide, max_keys=3)
    assert schema["_truncated"] is True
    assert any(k.startswith("...(+7 keys)") for k in schema)


def test_infer_schema_node_budget():
    big = {"items": [{"x": i} for i in range(50)]}
    schema = result_store.infer_schema(big, node_budget=5)
    assert schema.get("_truncated") is True


# --- helpers ----------------------------------------------------------------


def test_safe_filename():
    assert result_store.safe_filename("My Table/Name:1") == "My_Table_Name-1"
    assert result_store.safe_filename("../etc") == ".._etc"  # slash -> _, no traversal


def test_arg_slug():
    assert result_store.arg_slug(None) == "all"
    assert result_store.arg_slug({}) == "all"
    assert result_store.arg_slug({"table_name": "Jobs"}) == "Jobs"
    assert result_store.arg_slug({"table_name": "", "min_signals": 3}) == "min_signals3"
    assert result_store.arg_slug({"include_config": True}) == "include_config"
    assert result_store.arg_slug({"include_config": False}) == "all"


def test_record_count():
    assert result_store.record_count({"summary": {}, "fields": [1, 2, 3]}) == 3
    assert result_store.record_count([1, 2]) == 2
    assert result_store.record_count({"summary": {}}) is None


# --- offload ----------------------------------------------------------------


def test_offload_small_returns_inline(tmp_store):
    value = {"summary": {"n": 1}, "fields": [1, 2]}
    assert result_store.offload("find_unused_fields", {"table_name": "X"}, value) is value


def test_offload_large_writes_file_and_envelope(tmp_store):
    value = {"summary": {"fields_reported": 100}, "fields": [{"id": f"fld{i}", "name": "n"} for i in range(100)]}
    env = result_store.offload("find_unused_fields", {"table_name": "Jobs"}, value)

    assert env["saved_to"].endswith("find_unused_fields__Jobs.json")
    assert env["summary"] == {"fields_reported": 100}
    assert env["record_count"] == 100
    assert env["bytes"] > 200
    # schema is over the heavy arrays, not the summary
    assert "fields" in env["schema"] and "summary" not in env["schema"]
    # file round-trips to the full value
    saved = json.loads((tmp_store / "find_unused_fields__Jobs.json").read_text())
    assert saved == value


def test_offload_bare_list_synthesizes_summary(tmp_store):
    value = [{"table_name": f"T{i}", "sections": []} for i in range(50)]
    env = result_store.offload("get_view_sections", None, value)
    assert env["summary"] == {"count": 50}
    assert env["saved_to"].endswith("get_view_sections__all.json")


def test_offload_string_saves_markdown(tmp_store):
    value = "erDiagram\n" + ("A ||--o{ B : x\n" * 100)
    env = result_store.offload("generate_schema_diagram", None, value)
    assert env["saved_to"].endswith(".md")
    assert env["schema"] == "str"
    assert "summary" not in env
    assert (tmp_store / "generate_schema_diagram__all.md").read_text() == value


def test_offload_error_payload_never_offloaded(tmp_store):
    err = {"error": "NotAuthenticatedError", "message": "x" * 500}
    assert result_store.offload("get_view", {"table_name": "X"}, err) is err

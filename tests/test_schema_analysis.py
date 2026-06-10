"""Tests for the base-wide analysis tools in src/schema_tools.py
(table_connectivity, formula_function_usage, base_health_report)."""

from typing import cast

from src import schema_tools
from src.meta import Base


class _Opts:
    def __init__(self, linked_table_id=None, single=None, inverse_id=None, formula=None):
        self.linked_table_id = linked_table_id
        self.prefers_single_record_link = single
        self.inverse_link_field_id = inverse_id
        self.formula = formula


class _Tbl:
    def __init__(self, id, name, primary_field_id):
        self.id = id
        self.name = name
        self.primary_field_id = primary_field_id
        self.fields: list = []


class _Fld:
    def __init__(self, id, name, type, table, opts=None, computed=False):
        self.id = id
        self.name = name
        self.type = type
        self.table = table
        self.options = opts
        self._computed = computed

    def is_computed(self):
        return self._computed

    def linked_table(self):
        if self.options and self.options.linked_table_id:
            return _CONN_BASE.table_by_id(self.options.linked_table_id)
        return None


class _ConnBase:
    """A -< (m:m) >- B, junction J linking A&B, isolated ISO."""

    def __init__(self):
        t_a = _Tbl("tA", "A", "fA0")
        t_b = _Tbl("tB", "B", "fB0")
        t_j = _Tbl("tJ", "J", "fJ0")
        t_iso = _Tbl("tISO", "ISO", "fI0")
        self._tables = [t_a, t_b, t_j, t_iso]
        self._by_tid = {t.id: t for t in self._tables}

        # primaries (plain text)
        p_a = _Fld("fA0", "A Name", "singleLineText", t_a)
        p_b = _Fld("fB0", "B Name", "singleLineText", t_b)
        p_j = _Fld("fJ0", "J Name", "singleLineText", t_j)
        p_iso = _Fld("fI0", "ISO Name", "singleLineText", t_iso)
        # A <-> B many-to-many (mutual inverses)
        link_a_b = _Fld("laB", "Bs", "multipleRecordLinks", t_a, _Opts(linked_table_id="tB", single=False, inverse_id="lbA"))
        link_b_a = _Fld("lbA", "As", "multipleRecordLinks", t_b, _Opts(linked_table_id="tA", single=False, inverse_id="laB"))
        # junction J -> A and J -> B (single on J side, no inverse modeled)
        link_j_a = _Fld("jA", "A", "multipleRecordLinks", t_j, _Opts(linked_table_id="tA", single=True))
        link_j_b = _Fld("jB", "B", "multipleRecordLinks", t_j, _Opts(linked_table_id="tB", single=True))
        t_a.fields = [p_a, link_a_b]
        t_b.fields = [p_b, link_b_a]
        t_j.fields = [p_j, link_j_a, link_j_b]
        t_iso.fields = [p_iso]
        self._fields = [p_a, p_b, p_j, p_iso, link_a_b, link_b_a, link_j_a, link_j_b]
        self._by_fid = {f.id: f for f in self._fields}

    @property
    def tables(self):
        return self._tables

    def fields(self):
        return self._fields

    def table_by_id(self, tid):
        return self._by_tid.get(tid)

    def field_by_id(self, fid):
        return self._by_fid.get(fid)


_CONN_BASE = _ConnBase()  # module-level so _Fld.linked_table can resolve


def test_table_connectivity(monkeypatch):
    monkeypatch.setattr(schema_tools, "_get_base", lambda: cast(Base, _CONN_BASE))

    result = schema_tools.table_connectivity()
    s = result["summary"]
    assert s["table_count"] == 4
    assert s["isolated_count"] == 1
    assert s["junction_count"] == 1

    assert result["isolated_tables"] == ["ISO"]
    assert result["junction_tables"][0]["name"] == "J"
    assert result["junction_tables"][0]["links_between"] == ["A", "B"]

    cards = {(r["from_table"], r["to_table"]): r["cardinality"] for r in result["relationships"]}
    assert cards[("A", "B")] == "many-to-many"
    # J's links have no inverse modeled -> cardinality can't be inferred
    assert cards[("J", "A")] == "unknown"

    degrees = {t["name"]: t["degree"] for t in result["tables"]}
    assert degrees["A"] == 2 and degrees["B"] == 2  # each connects to the other + J
    assert degrees["ISO"] == 0


def test_cardinality():
    assert schema_tools._cardinality(True, True, True) == "one-to-one"
    assert schema_tools._cardinality(True, False, True) == "one-to-many"
    assert schema_tools._cardinality(False, True, True) == "one-to-many"
    assert schema_tools._cardinality(False, False, True) == "many-to-many"
    assert schema_tools._cardinality(True, True, False) == "unknown"

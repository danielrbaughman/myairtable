"""Tests for the base-wide analysis tools in src/myairtable/schema_tools.py
(table_connectivity, formula_function_usage, base_health_report)."""

from typing import cast

from myairtable import schema_tools
from myairtable.meta import Base


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


class _FormulaField:
    def __init__(self, name, formula):
        self.name = name
        self.type = "formula"
        self.options = _Opts(formula=formula)

    def is_formula(self):
        return True


class _PlainField:
    def __init__(self, name):
        self.name = name
        self.type = "singleLineText"
        self.options = None

    def is_formula(self):
        return False


class _FormulaBase:
    def __init__(self):
        t = _Tbl("tF", "T", "fp")
        t.fields = [
            _PlainField("Raw"),
            _FormulaField("A", "IF({x}, 1, IF({y}, 2, 3))"),  # IF x2
            _FormulaField("B", "AND(IF({z}, TRUE(), FALSE()), {w})"),  # IF x1, AND x1, TRUE/FALSE
        ]
        self._tables = [t]

    @property
    def tables(self):
        return self._tables


def test_formula_function_usage(monkeypatch):
    monkeypatch.setattr(schema_tools, "_get_base", lambda: cast(Base, _FormulaBase()))

    result = schema_tools.formula_function_usage()
    assert result["summary"]["formula_fields"] == 2  # plain field excluded
    by_fn = {f["name"]: f for f in result["functions"]}
    assert by_fn["IF"]["count"] == 3  # 2 in A, 1 in B
    assert by_fn["IF"]["field_count"] == 2  # both A and B use IF
    assert by_fn["AND"]["count"] == 1
    # most_common ordering: IF first
    assert result["functions"][0]["name"] == "IF"


def _stub_public_finders(monkeypatch):
    """Make base_health_report's public aggregations return small canned data."""
    monkeypatch.setattr(schema_tools, "find_dead_fields", lambda: [{"name": "X"}])
    monkeypatch.setattr(schema_tools, "find_invalid_fields", lambda: [])
    monkeypatch.setattr(
        schema_tools, "find_circular_references", lambda: {"formula_circular_references": [{"f": 1}], "bidirectional_link_pairs": [1, 2]}
    )
    monkeypatch.setattr(schema_tools, "check_link_symmetry", lambda: [{"issue": 1}])
    monkeypatch.setattr(schema_tools, "find_type_ambiguities", lambda: [])
    monkeypatch.setattr(schema_tools, "analyze_type_consistency", lambda: [])
    monkeypatch.setattr(
        schema_tools,
        "dependency_graph_metrics",
        lambda top_n=25: {"rankings": {"most_central": [{"field": "T.A", "blast_radius": 99}, {"field": "T.B", "blast_radius": 3}]}},
    )
    monkeypatch.setattr(schema_tools, "table_connectivity", lambda: {"isolated_tables": ["Lonely"]})

    class _T:
        def __init__(self, name, n):
            self.name = name
            self.fields = list(range(n))

    monkeypatch.setattr(schema_tools, "_get_base", lambda: cast(Base, type("B", (), {"tables": [_T("Big", 150), _T("Small", 5)]})()))


def test_base_health_report_public_only(monkeypatch):
    _stub_public_finders(monkeypatch)

    result = schema_tools.base_health_report()
    cats = {c["category"]: c for c in result["findings"]}
    assert cats["dead_fields"]["count"] == 1
    # only formula cycles, not the (normal) bidirectional link pairs
    assert cats["formula_circular_references"]["count"] == 1
    # only blast radius >= threshold (25)
    assert cats["high_blast_radius_fields"]["count"] == 1
    assert cats["isolated_tables"]["items"] == [{"table": "Lonely"}]
    assert cats["god_tables"]["items"] == [{"table": "Big", "field_count": 150}]

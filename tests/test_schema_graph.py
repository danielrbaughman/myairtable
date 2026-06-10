"""Tests for the FieldDependencyGraph cycle-safe builder in src/schema_tools.py."""

from typing import cast

from src.meta import Base
from src.schema_tools import FieldDependencyGraph


class _FakeField:
    def __init__(self, id, refs):
        self.id = id
        self._refs = refs  # list of _FakeField it references (depends on)

    def referenced_fields(self):
        return self._refs


class _FakeBase:
    """A graph: A->B->C (A depends on B depends on C); D depends on B; E<->F cycle."""

    def __init__(self):
        c = _FakeField("C", [])
        b = _FakeField("B", [c])
        a = _FakeField("A", [b])
        d = _FakeField("D", [b])
        e = _FakeField("E", [])
        f = _FakeField("F", [e])
        e._refs = [f]  # close the cycle E<->F
        self._fields = [a, b, c, d, e, f]

    def fields(self):
        return self._fields


def _graph():
    return FieldDependencyGraph(cast(Base, _FakeBase()))


def test_direct_edges():
    g = _graph()
    assert g.deps["A"] == {"B"}
    assert g.deps["B"] == {"C"}
    assert g.dependents["B"] == {"A", "D"}  # both A and D depend on B
    assert g.dependents["C"] == {"B"}


def test_transitive_dependents_is_blast_radius():
    g = _graph()
    # changing C affects B, and transitively A and D
    assert g.transitive_dependents("C") == {"B", "A", "D"}
    assert g.transitive_dependents("B") == {"A", "D"}
    assert g.transitive_dependents("A") == set()  # nothing depends on A


def test_transitive_dependencies():
    g = _graph()
    assert g.transitive_dependencies("A") == {"B", "C"}
    assert g.transitive_dependencies("C") == set()


def test_depth():
    g = _graph()
    assert g.depth("A") == 2  # A->B->C
    assert g.depth("B") == 1
    assert g.depth("C") == 0


def test_longest_chain():
    g = _graph()
    assert g.longest_chain("A") == ["A", "B", "C"]


def test_cycle_detection_is_safe():
    g = _graph()
    # E and F are in a cycle; traversals must terminate
    assert g.cycle_members == {"E", "F"}
    assert "A" not in g.cycle_members
    assert g.transitive_dependencies("E") == {"F"}  # start excluded from its own closure
    assert g.depth("E") in (0, 1)  # finite, cycle edge contributes nothing
    assert "F" in g.longest_chain("E")  # terminates

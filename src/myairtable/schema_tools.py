"""Public-API schema introspection & analysis tools.

The logic behind myAirtable's public MCP tools and their `myairtable tools ...`
CLI mirrors. Pure functions over the public Airtable meta API (src.meta.Base) —
no MCP/FastMCP dependency, so both the MCP server (mcp_server.py) and the CLI
(src/myairtable/schema_tools_cli.py) import and register them without booting each other.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from myairtable.formulas.formula_formatter import _count_nesting_depth
from myairtable.formulas.formula_tokenizer import TokenType, tokenize_formula
from myairtable.formulas.formula_transpiler import transpile_formula
from myairtable.generators.mermaid import mermaid_base
from myairtable.meta import Base, Field

_base: Base | None = None


def _get_base() -> Base:
    """Get or lazily initialize the Base singleton."""
    global _base
    if _base is None:
        _base = Base()
    return _base


def _find_table(name: str):
    """Find a table by name (case-insensitive) or ID."""
    base = _get_base()
    # Try ID first
    table = base.table_by_id(name)
    if table:
        return table
    # Case-insensitive name match
    name_lower = name.lower()
    for t in base.tables:
        if t.name.lower() == name_lower:
            return t
    raise ValueError(f"Table not found: {name}")


def _find_field(table_name: str, field_name: str) -> Field:
    """Find a field by table and field name/ID."""
    table = _find_table(table_name)
    # Try ID first
    field = table.field_by_id(field_name)
    if field:
        return field
    # Case-insensitive name match
    name_lower = field_name.lower()
    for f in table.fields:
        if f.name.lower() == name_lower:
            return f
    raise ValueError(f"Field '{field_name}' not found in table '{table.name}'")


def _field_summary(field: Field) -> dict:
    """Build a summary dict for a field."""
    info: dict = {
        "id": field.id,
        "name": field.name,
        "type": field.type,
        "table": field.table.name,
    }
    if field.description:
        info["description"] = field.description
    return info


def _field_detail(field: Field) -> dict:
    """Build a detailed dict for a field."""
    info = _field_summary(field)

    if field.is_computed():
        info["computed"] = True

    # Select options
    if opts := field.select_options():
        info["options"] = opts

    # Link info
    if field.type == "multipleRecordLinks" and field.options:
        linked = field.linked_table()
        if linked:
            info["linked_table"] = linked.name
        if field.options.prefers_single_record_link:
            info["single_record_link"] = True
        if field.options.inverse_link_field_id:
            inverse = field.base.field_by_id(field.options.inverse_link_field_id)
            if inverse:
                info["inverse_field"] = inverse.name

    # Lookup / rollup info
    if field.is_lookup_rollup():
        link_field = field.record_link_field()
        target_field = field.field_in_linked_table()
        if link_field:
            info["via_link_field"] = link_field.name
        if target_field:
            info["source_field"] = f"{target_field.table.name}.{target_field.name}"

    # Formula
    if field.is_formula() and field.options and field.options.formula:
        info["formula"] = field.formula(sanitized=True)

    # Result type for calculated fields
    if field.is_calculated():
        info["result_type"] = field.result_type()

    # Count
    if field.type == "count":
        counted = field.counted_field()
        if counted:
            info["counts"] = counted.name

    return info


# ---------------------------------------------------------------------------
# Field dependency graph (shared substrate for the base-wide analysis tools).
# ---------------------------------------------------------------------------


class FieldDependencyGraph:
    """The base-wide directed field dependency graph.

    Node = field id. Edge X -> Y means X depends on Y (X references Y in a
    formula, or X is a lookup/rollup/count over Y via a link). Edges come from
    the canonical `Field.referenced_fields()` accessor (the same one
    reverse_dependencies / trace_field_dependencies use), so they span tables
    wherever a lookup/rollup reaches into a linked table.

    The graph can contain cycles (that's what find_circular_references detects),
    so every traversal here is cycle-safe.
    """

    def __init__(self, base: Base):
        self.base = base
        self.deps: dict[str, set[str]] = {}  # field id -> ids it depends on
        self.dependents: dict[str, set[str]] = {}  # field id -> ids that depend on it
        self.fields_by_id: dict[str, Field] = {}

        for field in base.fields():
            self.fields_by_id[field.id] = field
            self.deps.setdefault(field.id, set())
            self.dependents.setdefault(field.id, set())

        for field in base.fields():
            for ref in field.referenced_fields():
                if ref.id == field.id or ref.id not in self.fields_by_id:
                    continue
                self.deps[field.id].add(ref.id)
                self.dependents[ref.id].add(field.id)

        self._closure_cache: dict[tuple[str, bool], set[str]] = {}
        self._cycle_members: set[str] | None = None

    def _transitive(self, start: str, adjacency: dict[str, set[str]], downstream: bool) -> set[str]:
        key = (start, downstream)
        if key in self._closure_cache:
            return self._closure_cache[key]
        seen: set[str] = set()
        stack = list(adjacency.get(start, ()))
        while stack:
            nid = stack.pop()
            if nid in seen or nid == start:
                continue
            seen.add(nid)
            stack.extend(adjacency.get(nid, ()))
        self._closure_cache[key] = seen
        return seen

    def transitive_dependents(self, field_id: str) -> set[str]:
        """All fields affected (directly or transitively) if `field_id` changes — blast radius."""
        return self._transitive(field_id, self.dependents, downstream=False)

    def transitive_dependencies(self, field_id: str) -> set[str]:
        """All fields `field_id` derives from, directly or transitively."""
        return self._transitive(field_id, self.deps, downstream=True)

    def _reaches_self(self, field_id: str) -> bool:
        stack = list(self.deps.get(field_id, ()))
        seen: set[str] = set()
        while stack:
            nid = stack.pop()
            if nid == field_id:
                return True
            if nid in seen:
                continue
            seen.add(nid)
            stack.extend(self.deps.get(nid, ()))
        return False

    @property
    def cycle_members(self) -> set[str]:
        """Fields that participate in a dependency cycle (reachable from themselves)."""
        if self._cycle_members is None:
            self._cycle_members = {fid for fid in self.fields_by_id if self._reaches_self(fid)}
        return self._cycle_members

    def depth(self, field_id: str) -> int:
        """Longest dependency chain below `field_id` (edges to raw inputs).

        Path-guarded so cycles terminate; the cycle-closing edge contributes no
        depth. For fields inside a cycle this is a lower-bound heuristic — use
        `cycle_members` to know which those are.
        """

        def walk(fid: str, on_path: frozenset[str]) -> int:
            extended = on_path | {fid}
            best = 0
            for dep in self.deps.get(fid, ()):
                if dep in extended:  # cycle-closing edge contributes nothing
                    continue
                best = max(best, 1 + walk(dep, extended))
            return best

        return walk(field_id, frozenset())

    def longest_chain(self, field_id: str) -> list[str]:
        """The actual longest dependency path (field ids) below `field_id`."""

        def walk(fid: str, on_path: tuple[str, ...]) -> list[str]:
            extended = on_path + (fid,)
            longest: list[str] = []
            for dep in self.deps.get(fid, ()):
                if dep in extended:  # cycle-closing edge — stop
                    continue
                sub = walk(dep, extended)
                if len(sub) > len(longest):
                    longest = sub
            return [fid, *longest]

        return walk(field_id, ())


def _field_label(field: Field) -> str:
    return f"{field.table.name}.{field.name}"


def dependency_graph_metrics(table_name: str = "", top_n: int = 20) -> dict:
    """Base-wide field dependency-graph metrics: blast radius, depth, centrality.

    For each field that participates in the dependency graph: fan_in (direct
    dependents), fan_out (direct dependencies), blast_radius (transitive
    dependents — everything that breaks if it changes), dependency_depth
    (longest chain down to raw inputs), and in_cycle. Plus base-level rankings:
    the most central fields (largest blast radius), the deepest dependency
    chains, and the widest fan-out formulas.

    Edges span tables (lookups/rollups reach into linked tables), so blast
    radius is cross-table. Optionally scope the per-field list to one table
    (rankings still consider the whole base).

    Args:
        table_name: Optional table name or ID to scope the field list.
        top_n: How many entries to include in each ranking.
    """
    graph = FieldDependencyGraph(_get_base())
    scoped_table = _find_table(table_name) if table_name else None
    cycle_members = graph.cycle_members

    def metrics(fid: str) -> dict:
        field = graph.fields_by_id[fid]
        return {
            "id": fid,
            "name": field.name,
            "table": field.table.name,
            "type": field.type,
            "fan_in": len(graph.dependents[fid]),
            "fan_out": len(graph.deps[fid]),
            "blast_radius": len(graph.transitive_dependents(fid)),
            "dependency_depth": graph.depth(fid),
            "in_cycle": fid in cycle_members,
        }

    # Only fields that participate in the graph (have a dependency or a dependent).
    participating = [fid for fid in graph.fields_by_id if graph.deps[fid] or graph.dependents[fid]]
    all_metrics = [metrics(fid) for fid in participating]

    def top(key: str) -> list[dict]:
        return sorted(all_metrics, key=lambda m: m[key], reverse=True)[:top_n]

    deepest = sorted(all_metrics, key=lambda m: m["dependency_depth"], reverse=True)[:top_n]
    deepest_chains = [
        {
            "field": _field_label(graph.fields_by_id[m["id"]]),
            "depth": m["dependency_depth"],
            "chain": [_field_label(graph.fields_by_id[c]) for c in graph.longest_chain(m["id"])],
        }
        for m in deepest
        if m["dependency_depth"] > 0
    ]

    in_scope = [m for m in all_metrics if scoped_table is None or m["table"] == scoped_table.name]
    in_scope.sort(key=lambda m: m["blast_radius"], reverse=True)

    return {
        "summary": {
            "fields_in_graph": len(all_metrics),
            "fields_in_cycles": sum(1 for m in all_metrics if m["in_cycle"]),
            "max_depth": max((m["dependency_depth"] for m in all_metrics), default=0),
            "scoped_to": scoped_table.name if scoped_table else None,
        },
        "rankings": {
            "most_central": [
                {"field": _field_label(graph.fields_by_id[m["id"]]), "blast_radius": m["blast_radius"], "fan_in": m["fan_in"]}
                for m in top("blast_radius")
                if m["blast_radius"] > 0
            ],
            "deepest_chains": deepest_chains,
            "widest_fan_out": [
                {"field": _field_label(graph.fields_by_id[m["id"]]), "fan_out": m["fan_out"], "type": m["type"]}
                for m in top("fan_out")
                if m["fan_out"] > 0
            ],
        },
        "fields": in_scope,
    }


def _cardinality(field_single: bool, inverse_single: bool, has_inverse: bool) -> str:
    if not has_inverse:
        return "unknown"
    if field_single and inverse_single:
        return "one-to-one"
    if field_single or inverse_single:
        return "one-to-many"
    return "many-to-many"


def table_connectivity() -> dict:
    """Analyze the table link graph: connectivity, hubs, isolated and junction tables.

    Per table: how many link fields it has, how many distinct tables it
    connects to (degree), and inbound link count. Base-level: hub tables (most
    connected), isolated tables (no links in or out), junction tables (a
    two-link table with little else — a many-to-many join), and every
    relationship with its inferred cardinality (one-to-one / one-to-many /
    many-to-many). Quantifies what generate_schema_diagram only draws.
    """
    base = _get_base()

    # Per-table aggregates
    link_fields_by_table: dict[str, list] = {t.id: [] for t in base.tables}
    connected: dict[str, set[str]] = {t.id: set() for t in base.tables}
    inbound: dict[str, int] = {t.id: 0 for t in base.tables}

    relationships: list[dict] = []
    seen: set[str] = set()

    for field in base.fields():
        if field.type != "multipleRecordLinks":
            continue
        linked = field.linked_table()
        if not linked:
            continue
        link_fields_by_table[field.table.id].append(field)
        connected[field.table.id].add(linked.id)
        if linked.id in connected:
            connected[linked.id].add(field.table.id)
            inbound[linked.id] += 1

        if field.id in seen:
            continue
        seen.add(field.id)
        inverse = None
        if field.options and field.options.inverse_link_field_id:
            inverse = base.field_by_id(field.options.inverse_link_field_id)
            if inverse:
                seen.add(inverse.id)
        field_single = bool(field.options and field.options.prefers_single_record_link)
        inverse_single = bool(inverse and inverse.options and inverse.options.prefers_single_record_link)
        relationships.append(
            {
                "from_table": field.table.name,
                "to_table": linked.name,
                "from_field": field.name,
                "to_field": inverse.name if inverse else None,
                "cardinality": _cardinality(field_single, inverse_single, inverse is not None),
            }
        )

    def _is_junction(table) -> bool:
        links = link_fields_by_table[table.id]
        if len(links) != 2 or len({lf.linked_table().id for lf in links if lf.linked_table()}) != 2:
            return False
        # few other fields: nothing but the primary + the two links + maybe a computed helper
        others = [f for f in table.fields if f.id != table.primary_field_id and f.type != "multipleRecordLinks" and not f.is_computed()]
        return len(others) <= 2

    def _table_names(tids: set[str]) -> list[str]:
        names = [base.table_by_id(tid) for tid in tids]
        return sorted(t.name for t in names if t is not None)

    tables: list[dict[str, Any]] = []
    isolated = []
    junctions = []
    for t in base.tables:
        degree = len(connected[t.id])
        entry: dict[str, Any] = {
            "name": t.name,
            "id": t.id,
            "link_field_count": len(link_fields_by_table[t.id]),
            "inbound_link_count": inbound[t.id],
            "degree": degree,
            "connected_tables": _table_names(connected[t.id]),
        }
        tables.append(entry)
        if degree == 0:
            isolated.append(t.name)
        if _is_junction(t):
            junctions.append({"name": t.name, "links_between": entry["connected_tables"]})

    tables.sort(key=lambda e: e["degree"], reverse=True)

    return {
        "summary": {
            "table_count": len(base.tables),
            "total_link_fields": sum(len(v) for v in link_fields_by_table.values()),
            "relationship_count": len(relationships),
            "isolated_count": len(isolated),
            "junction_count": len(junctions),
        },
        "hubs": [{"name": e["name"], "degree": e["degree"]} for e in tables[:10] if e["degree"] > 0],
        "isolated_tables": sorted(isolated),
        "junction_tables": junctions,
        "relationships": relationships,
        "tables": tables,
    }


def formula_function_usage(table_name: str = "") -> dict:
    """Base-wide histogram of which functions formulas use, and where.

    For each function: total call count, how many formula fields use it, and
    the fields. Reveals the formula vocabulary, rare/risky functions, and
    transpile-migration surface. analyze_formula_complexity gives per-field
    detail; this is the aggregate.

    Args:
        table_name: Optional table name or ID; all tables if empty.
    """
    base = _get_base()
    tables = [_find_table(table_name)] if table_name else base.tables

    counts: Counter = Counter()
    fields_by_function: dict[str, list[dict]] = {}
    formula_field_count = 0

    for table in tables:
        for field in table.fields:
            if not field.is_formula() or not field.options or not field.options.formula:
                continue
            formula_field_count += 1
            tokens = tokenize_formula(field.options.formula)
            funcs = [t.value for t in tokens if t.type == TokenType.FUNCTION]
            counts.update(funcs)
            for fn in set(funcs):
                fields_by_function.setdefault(fn, []).append({"table": table.name, "field": field.name})

    functions = [
        {"name": fn, "count": count, "field_count": len(fields_by_function[fn]), "fields": fields_by_function[fn]}
        for fn, count in counts.most_common()
    ]

    return {
        "summary": {
            "formula_fields": formula_field_count,
            "distinct_functions": len(counts),
            "total_function_calls": sum(counts.values()),
        },
        "functions": functions,
    }


_GOD_TABLE_FIELD_THRESHOLD = 100
_HIGH_BLAST_RADIUS_THRESHOLD = 25


def base_health_report() -> dict:
    """Information-only roll-up of everything notable about the base, in one call.

    Categorized findings (counts + items, no severity — the caller prioritizes),
    aggregating the public analysis tools plus the graph signals:
    dead/invalid fields, formula circular references, link asymmetry, type
    ambiguities/inconsistencies, high-blast-radius fields, isolated tables, and
    god tables.
    """
    base = _get_base()
    categories: list[dict] = []

    def add(category: str, items: list, note: str | None = None) -> None:
        entry: dict = {"category": category, "count": len(items), "items": items}
        if note:
            entry["note"] = note
        categories.append(entry)

    # --- public meta-API signals ---
    add("dead_fields", find_dead_fields(), "Not referenced by any formula/lookup/rollup (metadata only).")
    add("invalid_fields", find_invalid_fields())
    add("formula_circular_references", find_circular_references()["formula_circular_references"])
    add("link_asymmetry", check_link_symmetry())
    add("type_ambiguities", find_type_ambiguities())
    add("type_inconsistencies", analyze_type_consistency())

    metrics = dependency_graph_metrics(top_n=25)
    high_blast = [m for m in metrics["rankings"]["most_central"] if m["blast_radius"] >= _HIGH_BLAST_RADIUS_THRESHOLD]
    add("high_blast_radius_fields", high_blast, f"Fields whose change affects >= {_HIGH_BLAST_RADIUS_THRESHOLD} others.")

    connectivity = table_connectivity()
    add("isolated_tables", [{"table": n} for n in connectivity["isolated_tables"]], "No links in or out.")
    god_tables = [{"table": t.name, "field_count": len(t.fields)} for t in base.tables if len(t.fields) > _GOD_TABLE_FIELD_THRESHOLD]
    add("god_tables", sorted(god_tables, key=lambda g: g["field_count"], reverse=True), f"More than {_GOD_TABLE_FIELD_THRESHOLD} fields.")

    return {
        "summary": {
            "categories": len(categories),
            "total_findings": sum(c["count"] for c in categories),
        },
        "findings": categories,
    }


def get_schema() -> dict:
    """Return the full base schema: all tables with their fields and views."""
    base = _get_base()
    tables = []
    for table in base.tables:
        fields = []
        for f in table.fields:
            field_info: dict = {"id": f.id, "name": f.name, "type": f.type}
            if f.description:
                field_info["description"] = f.description
            fields.append(field_info)
        views = [{"id": v.id, "name": v.name, "type": v.type} for v in table.views]
        tables.append(
            {
                "id": table.id,
                "name": table.name,
                "primary_field_id": table.primary_field_id,
                "field_count": len(table.fields),
                "fields": fields,
                "views": views,
            }
        )
    return {"base_id": base.id, "tables": tables}


def list_tables() -> list[dict]:
    """List all tables with their name, field count, and primary field."""
    base = _get_base()
    result = []
    for table in base.tables:
        primary = table.field_by_id(table.primary_field_id)
        result.append(
            {
                "id": table.id,
                "name": table.name,
                "field_count": len(table.fields),
                "primary_field": primary.name if primary else table.primary_field_id,
            }
        )
    return result


def describe_table(table_name: str) -> dict:
    """Describe a table: all fields with types, descriptions, and options.

    Args:
        table_name: Table name or ID.
    """
    table = _find_table(table_name)
    fields = [_field_detail(f) for f in table.fields]
    views = [{"id": v.id, "name": v.name, "type": v.type} for v in table.views]
    linked = [t.name for t in table.linked_tables()]
    return {
        "id": table.id,
        "name": table.name,
        "primary_field_id": table.primary_field_id,
        "fields": fields,
        "views": views,
        "linked_tables": linked,
    }


def describe_field(table_name: str, field_name: str) -> dict:
    """Deep dive on a single field: type, options, linked table, formula, dependencies.

    Args:
        table_name: Table name or ID.
        field_name: Field name or ID.
    """
    field = _find_field(table_name, field_name)
    info = _field_detail(field)

    # Add referenced fields
    refs = field.referenced_fields()
    if refs:
        info["referenced_fields"] = [{"name": r.name, "table": r.table.name, "type": r.type} for r in refs]

    # Add dependency flags
    if field.is_calculated():
        info["involves_lookup"] = field.involves_lookup()
        info["involves_rollup"] = field.involves_rollup()

    return info


def search_fields(query: str = "", field_type: str = "") -> list[dict]:
    """Search fields by name or type across all tables.

    Args:
        query: Substring to match against field names (case-insensitive). Leave empty to match all.
        field_type: Filter by Airtable field type (e.g. 'formula', 'multipleRecordLinks', 'singleSelect').
    """
    base = _get_base()
    query_lower = query.lower()
    results = []
    for field in base.fields():
        if query_lower and query_lower not in field.name.lower():
            continue
        if field_type and field.type != field_type:
            continue
        results.append(_field_summary(field))
    return results


def get_links() -> list[dict]:
    """Get all link fields between tables, including their inverse fields."""
    base = _get_base()
    links = []
    seen: set[str] = set()
    for field in base.fields():
        if field.type != "multipleRecordLinks":
            continue
        if field.id in seen:
            continue
        linked_table = field.linked_table()
        if not linked_table:
            continue

        link: dict = {
            "field": field.name,
            "field_id": field.id,
            "from_table": field.table.name,
            "to_table": linked_table.name,
            "single": bool(field.options and field.options.prefers_single_record_link),
        }

        # Find inverse
        if field.options and field.options.inverse_link_field_id:
            inverse = base.field_by_id(field.options.inverse_link_field_id)
            if inverse:
                link["inverse_field"] = inverse.name
                link["inverse_field_id"] = inverse.id
                seen.add(inverse.id)

        seen.add(field.id)
        links.append(link)
    return links


def get_lookups_and_rollups(table_name: str) -> list[dict]:
    """Get all lookup and rollup fields for a table, showing what they derive from.

    Args:
        table_name: Table name or ID.
    """
    table = _find_table(table_name)
    results = []
    for field in table.fields:
        if not field.is_lookup_rollup():
            continue
        info: dict = {
            "name": field.name,
            "id": field.id,
            "type": field.type,
        }
        link_field = field.record_link_field()
        target_field = field.field_in_linked_table()
        if link_field:
            info["via_link_field"] = link_field.name
        if target_field:
            info["source_field"] = target_field.name
            info["source_table"] = target_field.table.name
        info["result_type"] = field.result_type()
        results.append(info)
    return results


def trace_field_dependencies(table_name: str, field_name: str) -> dict:
    """Walk the full dependency chain for a field (formulas, lookups, rollups).

    Args:
        table_name: Table name or ID.
        field_name: Field name or ID.
    """
    field = _find_field(table_name, field_name)

    def _trace(f: Field, visited: set[str] | None = None) -> dict:
        if visited is None:
            visited = set()
        if f.id in visited:
            return {"name": f.name, "type": f.type, "circular": True}
        visited.add(f.id)

        node: dict = {
            "name": f.name,
            "type": f.type,
            "table": f.table.name,
        }

        if f.is_formula() and f.options and f.options.formula:
            node["formula"] = f.formula(sanitized=True)

        if f.is_lookup_rollup():
            link_field = f.record_link_field()
            target_field = f.field_in_linked_table()
            if link_field:
                node["via_link"] = link_field.name
            if target_field:
                node["source"] = _trace(target_field, visited.copy())

        deps = []
        for ref in f.referenced_fields():
            if ref.id != f.id:
                deps.append(_trace(ref, visited.copy()))
        if deps:
            node["depends_on"] = deps

        return node

    return _trace(field)


def get_formula(table_name: str, field_name: str, flatten: bool = False) -> dict:
    """Get a formula field's expression with human-readable field names instead of IDs.

    Args:
        table_name: Table name or ID.
        field_name: Field name or ID.
        flatten: If True, expand nested formula references inline.
    """
    field = _find_field(table_name, field_name)
    if not field.is_formula():
        raise ValueError(f"'{field.name}' is not a formula field (type: {field.type})")

    result: dict = {
        "name": field.name,
        "table": field.table.name,
        "formula": field.formula(sanitized=True),
        "result_type": field.result_type(),
    }
    if flatten:
        result["formula_flattened"] = field.formula(sanitized=True, flatten=True)

    # Show referenced fields
    refs = field.referenced_fields()
    if refs:
        result["referenced_fields"] = [{"name": r.name, "type": r.type} for r in refs]
    return result


# ---------------------------------------------------------------------------
# Group 1: Already-tracked tools
# ---------------------------------------------------------------------------


def list_formula_fields(table_name: str = "") -> list[dict]:
    """List all formula fields with their expressions and result types.

    Args:
        table_name: Optional table name or ID. If empty, returns formulas across all tables.
    """
    base = _get_base()
    if table_name:
        tables = [_find_table(table_name)]
    else:
        tables = base.tables
    results = []
    for table in tables:
        for field in table.fields:
            if not field.is_formula():
                continue
            info: dict = {
                "name": field.name,
                "id": field.id,
                "table": table.name,
                "result_type": field.result_type(),
            }
            if field.options and field.options.formula:
                info["formula"] = field.formula(sanitized=True)
            results.append(info)
    return results


def flatten_formula(table_name: str, field_name: str) -> dict:
    """Expand nested formula references inline, showing the fully resolved expression.

    Args:
        table_name: Table name or ID.
        field_name: Field name or ID.
    """
    field = _find_field(table_name, field_name)
    if not field.is_formula():
        raise ValueError(f"'{field.name}' is not a formula field (type: {field.type})")
    return {
        "name": field.name,
        "table": field.table.name,
        "formula": field.formula(sanitized=True),
        "formula_flattened": field.formula(sanitized=True, flatten=True),
        "result_type": field.result_type(),
    }


def check_link_symmetry() -> list[dict]:
    """Check all link fields for symmetry issues: missing inverses or broken inverse references."""
    base = _get_base()
    issues = []
    for field in base.fields():
        if field.type != "multipleRecordLinks":
            continue
        if not field.options:
            issues.append(
                {
                    "field": field.name,
                    "field_id": field.id,
                    "table": field.table.name,
                    "issue": "no options defined",
                }
            )
            continue

        # Check linked table exists
        linked_table = field.linked_table()
        if not linked_table:
            issues.append(
                {
                    "field": field.name,
                    "field_id": field.id,
                    "table": field.table.name,
                    "issue": f"linked table not found: {field.options.linked_table_id}",
                }
            )
            continue

        # Check inverse
        if not field.options.inverse_link_field_id:
            issues.append(
                {
                    "field": field.name,
                    "field_id": field.id,
                    "table": field.table.name,
                    "to_table": linked_table.name,
                    "issue": "no inverse link field",
                }
            )
            continue

        inverse = base.field_by_id(field.options.inverse_link_field_id)
        if not inverse:
            issues.append(
                {
                    "field": field.name,
                    "field_id": field.id,
                    "table": field.table.name,
                    "to_table": linked_table.name,
                    "issue": f"inverse field not found: {field.options.inverse_link_field_id}",
                }
            )
        elif inverse.type != "multipleRecordLinks":
            issues.append(
                {
                    "field": field.name,
                    "field_id": field.id,
                    "table": field.table.name,
                    "to_table": linked_table.name,
                    "inverse_field": inverse.name,
                    "issue": f"inverse field is not a link field (type: {inverse.type})",
                }
            )
    return issues


def find_invalid_fields() -> list[dict]:
    """Find fields marked as invalid by Airtable or with broken references."""
    base = _get_base()
    issues = []
    for field in base.fields():
        # Airtable validity flag
        if not field.is_valid():
            issues.append(
                {
                    "name": field.name,
                    "id": field.id,
                    "table": field.table.name,
                    "type": field.type,
                    "issue": "marked invalid by Airtable",
                }
            )

        # Broken lookup/rollup references
        if field.is_lookup_rollup():
            link_field = field.record_link_field()
            target_field = field.field_in_linked_table()
            if not link_field:
                issues.append(
                    {
                        "name": field.name,
                        "id": field.id,
                        "table": field.table.name,
                        "type": field.type,
                        "issue": "link field not found for lookup/rollup",
                    }
                )
            if not target_field:
                issues.append(
                    {
                        "name": field.name,
                        "id": field.id,
                        "table": field.table.name,
                        "type": field.type,
                        "issue": "target field in linked table not found",
                    }
                )

        # Broken formula field references
        if field.is_formula() and field.options and field.options.referenced_field_ids:
            for ref_id in field.options.referenced_field_ids:
                if not base.field_by_id(ref_id):
                    issues.append(
                        {
                            "name": field.name,
                            "id": field.id,
                            "table": field.table.name,
                            "type": field.type,
                            "issue": f"references missing field: {ref_id}",
                        }
                    )
    return issues


# ---------------------------------------------------------------------------
# Group 2: Formula & Complexity Analysis
# ---------------------------------------------------------------------------


def analyze_formula_complexity(table_name: str = "") -> list[dict]:
    """Analyze complexity of formula fields: nesting depth, function usage, field reference count.

    Args:
        table_name: Optional table name or ID. If empty, analyzes all tables.
    """
    base = _get_base()
    if table_name:
        tables = [_find_table(table_name)]
    else:
        tables = base.tables
    results = []
    for table in tables:
        for field in table.fields:
            if not field.is_formula() or not field.options or not field.options.formula:
                continue
            raw = field.options.formula
            tokens = tokenize_formula(raw)
            functions_used = sorted({t.value for t in tokens if t.type == TokenType.FUNCTION})
            field_refs = [t.value for t in tokens if t.type == TokenType.FIELD_REF]
            results.append(
                {
                    "name": field.name,
                    "table": table.name,
                    "nesting_depth": _count_nesting_depth(raw),
                    "field_reference_count": len(field_refs),
                    "unique_field_references": len(set(field_refs)),
                    "functions_used": functions_used,
                    "function_count": len(functions_used),
                    "formula_length": len(raw),
                }
            )
    results.sort(key=lambda x: x["nesting_depth"], reverse=True)
    return results


def transpile(
    table_name: str,
    field_name: str,
    language: Literal["typescript", "javascript", "python"] = "typescript",
) -> dict:
    """Convert an Airtable formula to Python, TypeScript, or JavaScript code.

    Args:
        table_name: Table name or ID.
        field_name: Field name or ID.
        language: Target language: 'typescript', 'javascript', or 'python'.
    """
    field = _find_field(table_name, field_name)
    if not field.is_formula() or not field.options or not field.options.formula:
        raise ValueError(f"'{field.name}' is not a formula field or has no formula")

    table = field.table
    field_name_map = {f.id: f.name_snake() for f in table.fields}
    formula_field_ids = table.formula_field_ids()
    linked_record_field_ids = table.linked_record_field_ids()
    single_linked_record_field_ids = table.single_linked_record_field_ids()

    code = transpile_formula(
        formula=field.options.formula,
        language=language,
        field_name_map=field_name_map,
        formula_field_ids=formula_field_ids,
        linked_record_field_ids=linked_record_field_ids,
        single_linked_record_field_ids=single_linked_record_field_ids,
    )
    return {
        "name": field.name,
        "table": table.name,
        "language": language,
        "code": code,
        "original_formula": field.formula(sanitized=True),
    }


# ---------------------------------------------------------------------------
# Group 3: Cross-Table & Dependency Analysis
# ---------------------------------------------------------------------------


def reverse_dependencies(table_name: str, field_name: str) -> list[dict]:
    """Find all fields that depend on a given field (what breaks if this field changes).

    Args:
        table_name: Table name or ID.
        field_name: Field name or ID.
    """
    target = _find_field(table_name, field_name)
    base = _get_base()
    dependents = []
    for field in base.fields():
        if field.id == target.id:
            continue
        refs = field.referenced_fields()
        for ref in refs:
            if ref.id == target.id:
                dependents.append(
                    {
                        "name": field.name,
                        "id": field.id,
                        "table": field.table.name,
                        "type": field.type,
                        "relationship": "references directly",
                    }
                )
                break
    return dependents


def find_circular_references() -> dict:
    """Detect circular references in formula fields and link chains."""
    base = _get_base()

    # Formula circular references
    formula_circles: list[dict] = []
    for field in base.fields():
        if not field.is_formula() or not field.options or not field.options.formula:
            continue
        visited: set[str] = set()
        stack = [field]
        while stack:
            current = stack.pop()
            if current.id in visited:
                formula_circles.append(
                    {
                        "field": field.name,
                        "table": field.table.name,
                        "circular_at": current.name,
                    }
                )
                break
            visited.add(current.id)
            for ref in current.referenced_fields():
                if ref.is_formula():
                    stack.append(ref)

    # Link circular references (A -> B -> A)
    link_circles: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for field in base.fields():
        if field.type != "multipleRecordLinks" or not field.options:
            continue
        linked_table = field.linked_table()
        if not linked_table:
            continue
        # Check if linked table links back to this table
        for other_field in linked_table.fields:
            if other_field.type != "multipleRecordLinks" or not other_field.options:
                continue
            other_linked = other_field.linked_table()
            if other_linked and other_linked.id == field.table.id:
                lo, hi = sorted([field.table.id, linked_table.id])
                pair = (lo, hi)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    link_circles.append(
                        {
                            "table_a": field.table.name,
                            "field_a": field.name,
                            "table_b": linked_table.name,
                            "field_b": other_field.name,
                        }
                    )

    return {
        "formula_circular_references": formula_circles,
        "bidirectional_link_pairs": link_circles,
    }


def generate_schema_diagram() -> str:
    """Generate a Mermaid ER diagram showing all tables and their link relationships."""
    base = _get_base()
    return mermaid_base(base)


# ---------------------------------------------------------------------------
# Group 4: Statistics & Reporting
# ---------------------------------------------------------------------------


def base_stats() -> dict:
    """Get aggregate statistics about the base: table count, field counts by type, most connected tables."""
    base = _get_base()
    all_fields = base.fields()

    # Field type distribution
    type_counts: dict[str, int] = Counter(f.type for f in all_fields)

    # Per-table stats
    table_stats = []
    for table in base.tables:
        link_count = sum(1 for f in table.fields if f.type == "multipleRecordLinks")
        formula_count = sum(1 for f in table.fields if f.is_formula())
        computed_count = sum(1 for f in table.fields if f.is_computed())
        table_stats.append(
            {
                "name": table.name,
                "field_count": len(table.fields),
                "link_count": link_count,
                "formula_count": formula_count,
                "computed_count": computed_count,
                "linked_tables": len(table.linked_tables()),
            }
        )
    table_stats.sort(key=lambda x: x["field_count"], reverse=True)

    return {
        "table_count": len(base.tables),
        "total_fields": len(all_fields),
        "field_type_distribution": dict(sorted(type_counts.items(), key=lambda x: -x[1])),
        "formula_field_count": sum(1 for f in all_fields if f.is_formula()),
        "computed_field_count": sum(1 for f in all_fields if f.is_computed()),
        "link_field_count": sum(1 for f in all_fields if f.type == "multipleRecordLinks"),
        "tables_by_field_count": table_stats,
    }


def find_dead_fields() -> list[dict]:
    """Find fields that are not referenced by any formula, lookup, or rollup."""
    base = _get_base()

    # Build set of all referenced field IDs
    referenced_ids: set[str] = set()
    for field in base.fields():
        if field.options and field.options.referenced_field_ids:
            referenced_ids.update(field.options.referenced_field_ids)
        if field.options and field.options.field_id_in_linked_table:
            referenced_ids.add(field.options.field_id_in_linked_table)
        if field.options and field.options.record_link_field_id:
            referenced_ids.add(field.options.record_link_field_id)
        # Formula field references via {fldXXX} syntax
        if field.is_formula():
            for ref_id in field.get_field_ids_from_formula():
                referenced_ids.add(ref_id)

    # Find unreferenced non-computed fields (computed fields are expected to be leaf consumers)
    dead = []
    for field in base.fields():
        if field.id in referenced_ids:
            continue
        if field.is_computed():
            continue  # formulas/rollups/lookups are consumers, not sources
        if field.type == "multipleRecordLinks":
            continue  # links are structural, not "dead"
        dead.append(
            {
                "name": field.name,
                "id": field.id,
                "table": field.table.name,
                "type": field.type,
            }
        )
    return dead


def compare_tables(table_a: str, table_b: str) -> dict:
    """Compare field structures between two tables, showing shared and unique fields.

    Args:
        table_a: First table name or ID.
        table_b: Second table name or ID.
    """
    ta = _find_table(table_a)
    tb = _find_table(table_b)

    fields_a = {f.name.lower(): f for f in ta.fields}
    fields_b = {f.name.lower(): f for f in tb.fields}

    shared = []
    for name_lower in fields_a:
        if name_lower in fields_b:
            fa, fb = fields_a[name_lower], fields_b[name_lower]
            entry: dict = {"name": fa.name, "type_a": fa.type, "type_b": fb.type}
            if fa.type != fb.type:
                entry["type_mismatch"] = True
            shared.append(entry)

    only_a = [{"name": f.name, "type": f.type} for name_lower, f in fields_a.items() if name_lower not in fields_b]
    only_b = [{"name": f.name, "type": f.type} for name_lower, f in fields_b.items() if name_lower not in fields_a]

    return {
        "table_a": ta.name,
        "table_b": tb.name,
        "shared_fields": shared,
        "only_in_a": only_a,
        "only_in_b": only_b,
    }


# ---------------------------------------------------------------------------
# Group 5: Type & Select Analysis
# ---------------------------------------------------------------------------


def get_select_options(table_name: str = "") -> dict:
    """Get all select field options across tables. Shows option values and finds duplicates.

    Args:
        table_name: Optional table name or ID. If empty, returns options across all tables.
    """
    base = _get_base()
    if table_name:
        select_fields = [f for f in _find_table(table_name).fields if f.select_options()]
    else:
        select_fields = base.select_fields()

    # Collect all options
    results = []
    option_usage: dict[str, list[str]] = {}  # option_value -> list of field names
    for field in select_fields:
        opts = field.select_options()
        results.append(
            {
                "name": field.name,
                "table": field.table.name,
                "type": field.type,
                "options": opts,
                "option_count": len(opts),
            }
        )
        for opt in opts:
            option_usage.setdefault(opt, []).append(f"{field.table.name}.{field.name}")

    # Find duplicate options (same value in multiple fields)
    duplicates = {k: v for k, v in option_usage.items() if len(v) > 1}

    return {
        "fields": results,
        "total_select_fields": len(results),
        "duplicate_options": duplicates,
    }


def analyze_type_consistency() -> list[dict]:
    """Find calculated fields where the result type may not match expectations."""
    base = _get_base()
    issues = []
    for field in base.fields():
        if not field.is_calculated():
            continue
        result_type = field.result_type()

        # Lookup/rollup pointing to a link field but result type is unexpected
        if field.is_lookup_rollup():
            target = field.field_in_linked_table()
            if target and target.type != result_type and result_type != "singleLineText":
                issues.append(
                    {
                        "name": field.name,
                        "table": field.table.name,
                        "type": field.type,
                        "result_type": result_type,
                        "source_field": target.name,
                        "source_type": target.type,
                        "note": "result type differs from source field type",
                    }
                )

        # Formula with no result type info
        if field.is_formula() and result_type == "singleLineText":
            # Check if formula references numeric fields predominantly
            refs = field.referenced_fields()
            numeric_refs = [r for r in refs if r.type in ("number", "currency", "percent", "count", "autoNumber")]
            if len(numeric_refs) > 0 and len(numeric_refs) == len(refs):
                issues.append(
                    {
                        "name": field.name,
                        "table": field.table.name,
                        "type": field.type,
                        "result_type": result_type,
                        "note": "all referenced fields are numeric but result type is text",
                        "referenced_types": [r.type for r in refs],
                    }
                )
    return issues


def find_type_ambiguities() -> list[dict]:
    """Find computed fields with ambiguous or unknown result types."""
    base = _get_base()
    ambiguous = []
    for field in base.fields():
        if not field.is_calculated():
            continue
        result_type = field.result_type()
        if result_type in ("singleLineText", ""):
            # Might be ambiguous - check if it's a multipleLookupValues that could be anything
            info: dict = {
                "name": field.name,
                "table": field.table.name,
                "type": field.type,
                "result_type": result_type or "(empty)",
            }
            if field.is_lookup_rollup():
                target = field.field_in_linked_table()
                if target:
                    info["source_field"] = target.name
                    info["source_type"] = target.type
            ambiguous.append(info)
    return ambiguous


PUBLIC_TOOLS = [
    get_schema,
    list_tables,
    describe_table,
    describe_field,
    search_fields,
    get_links,
    get_lookups_and_rollups,
    trace_field_dependencies,
    get_formula,
    list_formula_fields,
    flatten_formula,
    check_link_symmetry,
    find_invalid_fields,
    analyze_formula_complexity,
    transpile,
    reverse_dependencies,
    find_circular_references,
    generate_schema_diagram,
    base_stats,
    find_dead_fields,
    compare_tables,
    get_select_options,
    analyze_type_consistency,
    find_type_ambiguities,
    dependency_graph_metrics,
    table_connectivity,
    formula_function_usage,
    base_health_report,
]

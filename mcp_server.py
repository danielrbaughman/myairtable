from __future__ import annotations

from collections import Counter
from typing import Literal

import dotenv

dotenv.load_dotenv()

from fastmcp import FastMCP  # noqa: E402

from src.formulas.formula_formatter import _count_nesting_depth  # noqa: E402
from src.formulas.formula_tokenizer import TokenType, tokenize_formula  # noqa: E402
from src.formulas.formula_transpiler import transpile_formula  # noqa: E402
from src.generators.mermaid import mermaid_base  # noqa: E402
from src.meta import Base, Field  # noqa: E402

mcp = FastMCP(
    "myairtable",
    instructions="""\
Read-only Airtable schema introspection and analysis tools.

Provides 24 tools for exploring an Airtable base without modifying it:

- **Schema browsing**: get_schema, list_tables, describe_table, describe_field, search_fields
- **Relationships**: get_links, get_lookups_and_rollups, check_link_symmetry
- **Formulas**: get_formula, list_formula_fields, flatten_formula, analyze_formula_complexity, transpile
- **Dependencies**: trace_field_dependencies, reverse_dependencies, find_circular_references
- **Validation**: find_invalid_fields, analyze_type_consistency, find_type_ambiguities
- **Statistics**: base_stats, find_dead_fields, compare_tables, get_select_options
- **Visualization**: generate_schema_diagram (Mermaid ER diagram)

Tables and fields can be referenced by name (case-insensitive) or Airtable ID.\
""",
)

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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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
                pair = tuple(sorted([field.table.id, linked_table.id]))
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


@mcp.tool()
def generate_schema_diagram() -> str:
    """Generate a Mermaid ER diagram showing all tables and their link relationships."""
    base = _get_base()
    return mermaid_base(base)


# ---------------------------------------------------------------------------
# Group 4: Statistics & Reporting
# ---------------------------------------------------------------------------


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


if __name__ == "__main__":
    mcp.run()

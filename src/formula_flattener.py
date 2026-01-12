"""Formula flattener - recursively expands nested formula field references.

This module provides functionality to flatten Airtable formulas by recursively
expanding references to formula fields into their underlying formula definitions.

Example:
    formula_map = {"fldB": "{fldC} + 1", "fldC": "10"}
    flatten_formula("{fldB} * 2", "fldA", formula_map)
    # Returns: "((10) + 1) * 2"
"""

import re
from functools import lru_cache

FIELD_REF_PATTERN = re.compile(r"\{(fld[A-Za-z0-9]+)\}")


@lru_cache(maxsize=1024)
def _flatten_cached(
    formula: str,
    current_field_id: str,
    formula_mapping: tuple[tuple[str, str], ...],
    visited: frozenset[str],
) -> str:
    """Cached implementation of formula flattening. Takes tuples for hashability."""
    formula_map = dict(formula_mapping)

    # Find all field references in formula
    referenced_field_ids = FIELD_REF_PATTERN.findall(formula)

    # Build replacements for formula fields only
    replacements: dict[str, str] = {}
    for field_id in referenced_field_ids:
        # Skip if this reference would create a cycle
        if field_id in visited:
            continue

        nested_formula = formula_map.get(field_id)

        # Skip if not a formula field or empty formula
        if not nested_formula:
            continue

        # Mark this field as visited before recursing to prevent cycles
        new_visited = visited | {field_id}

        # Recursively flatten (uses cache)
        flattened = _flatten_cached(
            nested_formula,
            field_id,
            formula_mapping,
            new_visited,
        )

        # Only add replacement if result is non-empty
        if flattened:
            replacements[field_id] = f"({flattened})"

    # Apply all replacements in single pass
    if replacements:

        def replace_callback(match: re.Match[str]) -> str:
            field_id = match.group(1)
            return replacements.get(field_id, match.group(0))

        formula = FIELD_REF_PATTERN.sub(replace_callback, formula)

    return formula


def flatten_formula(
    formula: str,
    current_field_id: str,
    formula_map: dict[str, str],
    visited: frozenset[str] | None = None,
) -> str:
    """Recursively flatten formula by expanding nested formula field references.

    Circular references are detected and preserved as field ID references.

    Args:
        formula: The formula string to flatten
        current_field_id: ID of the field being flattened (for cycle detection)
        formula_map: Dict mapping field IDs to their formula strings (only formula fields)
        visited: Set of field IDs already visited (for cycle detection)

    Returns:
        Flattened formula string with nested formulas expanded

    Example:
        >>> formula_map = {"fldA": "{fldB} + 1", "fldB": "10"}
        >>> flatten_formula("{fldA} * 2", "fldC", formula_map)
        '(((10) + 1)) * 2'
    """
    # Convert dict to hashable tuple for caching
    formula_mapping = tuple(sorted(formula_map.items()))
    if visited is None:
        visited = frozenset()
    return _flatten_cached(formula, current_field_id, formula_mapping, visited)

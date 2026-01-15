import re
from functools import lru_cache

from .formula_tokenizer import TokenType, tokenize_formula

# Pattern to validate field IDs (fldXXX format) - used for validation, not searching
FIELD_REF_PATTERN = re.compile(r"^fld[A-Za-z0-9]+$")


@lru_cache(maxsize=1024)
def _flatten_cached(
    formula: str,
    current_field_id: str,
    formula_mapping: tuple[tuple[str, str], ...],
    visited: frozenset[str],
) -> str:
    """Cached implementation of formula flattening. Takes tuples for hashability."""
    formula_map = dict(formula_mapping)

    # Tokenize the formula to properly handle strings and field references
    tokens = tokenize_formula(formula)

    # Build result by processing each token
    result_parts: list[str] = []

    for token in tokens:
        # Non-field-ref tokens pass through unchanged
        if token.type != TokenType.FIELD_REF:
            result_parts.append(token.value)
            continue

        # Extract field ID from {fldXXX} format
        field_id = token.value[1:-1]  # Strip braces

        # Only process valid field IDs in fldXXX format
        if not FIELD_REF_PATTERN.match(field_id):
            result_parts.append(token.value)
            continue

        # Skip if this reference would create a cycle
        if field_id in visited:
            result_parts.append(token.value)
            continue

        nested_formula = formula_map.get(field_id)

        # Skip if not a formula field or empty formula
        if not nested_formula:
            result_parts.append(token.value)
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

        # Replace with flattened formula wrapped in parentheses
        if flattened:
            result_parts.append(f"({flattened})")
        else:
            result_parts.append(token.value)

    return "".join(result_parts)


def flatten_formula(
    formula: str,
    current_field_id: str,
    formula_map: dict[str, str] | None = None,
    visited: frozenset[str] | None = None,
    *,
    formula_map_tuple: tuple[tuple[str, str], ...] | None = None,
) -> str:
    """Recursively flatten formula by expanding nested formula field references.

    Circular references are detected and preserved as field ID references.

    Args:
        formula: The formula string to flatten
        current_field_id: ID of the field being flattened (for cycle detection)
        formula_map: Dict mapping field IDs to their formula strings (only formula fields)
        visited: Set of field IDs already visited (for cycle detection)
        formula_map_tuple: Pre-computed tuple of (field_id, formula) pairs. If provided,
            this is used directly instead of converting formula_map, avoiding repeated
            dict-to-tuple conversion when flattening multiple formulas.

    Returns:
        Flattened formula string with nested formulas expanded

    Example:
        >>> formula_map = {"fldA": "{fldB} + 1", "fldB": "10"}
        >>> flatten_formula("{fldA} * 2", "fldC", formula_map)
        '(((10) + 1)) * 2'
    """
    # Use pre-computed tuple if provided, otherwise convert dict
    if formula_map_tuple is not None:
        formula_mapping = formula_map_tuple
    elif formula_map is not None:
        formula_mapping = tuple(sorted(formula_map.items()))
    else:
        raise ValueError("Either formula_map or formula_map_tuple must be provided")

    if visited is None:
        visited = frozenset()
    return _flatten_cached(formula, current_field_id, formula_mapping, visited)

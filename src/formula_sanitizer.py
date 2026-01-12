"""Formula sanitizer - replaces field IDs with field names for readability."""

import re
from functools import lru_cache

from .formula_tokenizer import TokenType, tokenize_formula

# Pattern to validate field IDs (fldXXX format) - used for validation, not searching
FIELD_REF_PATTERN = re.compile(r"^fld[A-Za-z0-9]+$")


@lru_cache(maxsize=1024)
def _sanitize_cached(formula: str, field_mapping: tuple[tuple[str, str], ...]) -> str:
    """Sanitize formula with caching. Takes tuple for hashability."""
    field_id_to_name = dict(field_mapping)

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

        # Replace with field name if found, otherwise keep original
        field_name = field_id_to_name.get(field_id)
        if field_name:
            result_parts.append(f"{{{field_name}}}")
        else:
            result_parts.append(token.value)

    return "".join(result_parts)


def sanitize_formula(formula: str, field_id_to_name: dict[str, str]) -> str:
    """Replace field IDs with field names for readability.

    Args:
        formula: The formula string containing field ID references like {fldXXX}
        field_id_to_name: Mapping from field IDs to field names

    Returns:
        The formula with field IDs replaced by field names
    """
    # Convert dict to hashable tuple for caching
    field_mapping = tuple(sorted(field_id_to_name.items()))
    return _sanitize_cached(formula, field_mapping)

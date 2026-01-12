"""Formula sanitizer - replaces field IDs with field names for readability."""

import re
from functools import lru_cache

FIELD_REF_PATTERN = re.compile(r"\{(fld[A-Za-z0-9]+)\}")


@lru_cache(maxsize=1024)
def _sanitize_cached(formula: str, field_mapping: tuple[tuple[str, str], ...]) -> str:
    """Sanitize formula with caching. Takes tuple for hashability."""
    field_id_to_name = dict(field_mapping)

    def replace_field_ref(match: re.Match[str]) -> str:
        field_id = match.group(1)
        field_name = field_id_to_name.get(field_id)
        if field_name:
            return f"{{{field_name}}}"
        return match.group(0)  # Keep original if field not found

    return FIELD_REF_PATTERN.sub(replace_field_ref, formula)


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

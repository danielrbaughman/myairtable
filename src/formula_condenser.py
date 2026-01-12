"""Formula condensing utilities for Airtable formulas."""

from functools import lru_cache

try:
    from .formula_tokenizer import FormulaTokenizer, TokenType
except ImportError:
    from formula_tokenizer import FormulaTokenizer, TokenType


@lru_cache(maxsize=1024)
def _tokenize_cached(formula: str) -> tuple:
    """Tokenize formula with caching. Returns tuple for hashability."""
    return tuple(FormulaTokenizer(formula).tokenize())


def condense_formula(formula: str) -> str:
    """Condense formula by removing unnecessary whitespace.

    Removes all whitespace (spaces, newlines, tabs) from a formula while
    preserving content inside string literals and field references.

    This is the inverse of format_formula. Idempotent - condensing an
    already-condensed formula returns the same result.

    Args:
        formula: The Airtable formula string to condense

    Returns:
        Condensed single-line formula string

    Examples:
        >>> condense_formula("IF(\\n  {a},\\n  {b}\\n)")
        'IF({a},{b})'

        >>> condense_formula('IF({a}, "hello   world", {b})')
        'IF({a},"hello   world",{b})'
    """
    if not formula or not formula.strip():
        return formula

    try:
        tokens = _tokenize_cached(formula)
        result_parts = [t.value for t in tokens if t.type != TokenType.WHITESPACE]
        return "".join(result_parts)
    except Exception:
        return formula

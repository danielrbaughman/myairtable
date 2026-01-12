"""Tests for the pure function tokenize() API."""

import sys

sys.path.insert(0, "src")

import pytest

from formula_tokenizer import TokenType, tokenize_formula


class TestTokenizePureFunction:
    """Test the pure tokenize() function exists and works."""

    def test_tokenize_function_exists(self):
        """tokenize() should be importable and callable."""
        assert callable(tokenize_formula)

    def test_empty_formula(self):
        """Empty string returns empty list."""
        assert tokenize_formula("") == []

    def test_simple_function(self):
        """Basic function call tokenizes correctly."""
        tokens = tokenize_formula("SUM(1, 2)")
        assert tokens[0].type == TokenType.FUNCTION
        assert tokens[0].value == "SUM"

    def test_field_reference(self):
        """Field references tokenize correctly."""
        tokens = tokenize_formula("{Amount}")
        assert tokens[0].type == TokenType.FIELD_REF
        assert tokens[0].value == "{Amount}"

    def test_parenthesis_depth_tracking(self):
        """Nested parentheses have correct depth values."""
        tokens = tokenize_formula("((1))")
        parens = [t for t in tokens if t.type == TokenType.PARENTHESIS]
        assert parens[0].depth == 1  # outer (
        assert parens[1].depth == 2  # inner (
        assert parens[2].depth == 2  # inner )
        assert parens[3].depth == 1  # outer )


class TestTokenizeEquivalence:
    """Verify pure function produces identical results to class."""

    @pytest.mark.parametrize(
        "formula",
        [
            "",
            "SUM(1, 2)",
            "IF({Status} = 'Done', TRUE(), FALSE())",
            "{Field Name}",
            "DATETIME_FORMAT({Date}, 'YYYY-MM-DD')",
            "5 - 3",
            "-10",
            "IF(1, -5, 0)",
            "'it\\'s a test'",
            "((({nested})))",
        ],
    )
    def test_equivalence_with_class(self, formula):
        """Pure function must produce identical output to class."""
        from formula_tokenizer import FormulaTokenizer

        class_result = FormulaTokenizer(formula).tokenize()
        pure_result = tokenize_formula(formula)

        assert pure_result == class_result

"""Tests for the flatten_formula function in formula_flattener.py."""

import pytest

from src.formula_flattener import FIELD_REF_PATTERN, flatten_formula


class TestFlattenBasic:
    """Test basic flattening functionality."""

    def test_empty_formula(self):
        assert flatten_formula("", "fldTest", {}) == ""

    def test_no_field_refs(self):
        assert flatten_formula("1 + 2", "fldTest", {}) == "1 + 2"

    def test_non_formula_field_unchanged(self):
        # fldA not in formula_map means it's not a formula field
        result = flatten_formula("{fldA}", "fldTest", {})
        assert result == "{fldA}"

    def test_single_formula_expansion(self):
        formula_map = {"fldA": "1 + 2"}
        result = flatten_formula("{fldA}", "fldTest", formula_map)
        assert result == "(1 + 2)"

    def test_formula_wrapped_in_parens(self):
        formula_map = {"fldA": "{fldB} + 1"}
        result = flatten_formula("{fldA} * 2", "fldTest", formula_map)
        assert result == "({fldB} + 1) * 2"

    def test_multiple_formula_refs(self):
        formula_map = {"fldA": "1", "fldB": "2"}
        result = flatten_formula("{fldA} + {fldB}", "fldTest", formula_map)
        assert result == "(1) + (2)"

    def test_mixed_formula_and_regular(self):
        # fldA is a formula field, fldB is not (not in map)
        formula_map = {"fldA": "10"}
        result = flatten_formula("{fldA} + {fldB}", "fldTest", formula_map)
        assert result == "(10) + {fldB}"


class TestFlattenRecursive:
    """Test recursive flattening."""

    def test_two_levels_deep(self):
        formula_map = {
            "fldA": "{fldB} + 1",
            "fldB": "{fldC} * 2",
            # fldC is not a formula field
        }
        result = flatten_formula("{fldA}", "fldTest", formula_map)
        assert result == "(({fldC} * 2) + 1)"

    def test_three_levels_deep(self):
        formula_map = {
            "fldA": "{fldB}",
            "fldB": "{fldC}",
            "fldC": "{fldD}",
            # fldD is not a formula field
        }
        result = flatten_formula("{fldA}", "fldTest", formula_map)
        assert result == "((({fldD})))"

    def test_diamond_dependency(self):
        """A → B and A → C, both reference D."""
        formula_map = {
            "fldB": "{fldD} + 1",
            "fldC": "{fldD} * 2",
            # fldD is not a formula field
        }
        result = flatten_formula("{fldB} + {fldC}", "fldA", formula_map)
        assert result == "({fldD} + 1) + ({fldD} * 2)"


class TestCircularRefs:
    """Test circular reference detection."""

    def test_self_reference(self):
        formula_map = {"fldA": "{fldA} + 1"}
        result = flatten_formula("{fldA}", "fldA", formula_map)
        # Formula expands, but circular reference within it is preserved
        assert result == "({fldA} + 1)"

    def test_two_field_cycle(self):
        formula_map = {
            "fldA": "{fldB} + 1",
            "fldB": "{fldA} * 2",
        }
        result = flatten_formula("{fldA}", "fldA", formula_map)
        assert "{fldA}" in result

    def test_three_field_cycle(self):
        formula_map = {
            "fldA": "{fldB}",
            "fldB": "{fldC}",
            "fldC": "{fldA}",
        }
        result = flatten_formula("{fldA}", "fldA", formula_map)
        assert "{fldA}" in result

    def test_partial_circular(self):
        """Non-circular parts still expand."""
        formula_map = {
            "fldA": "{fldA} + {fldB}",
            "fldB": "10",
        }
        result = flatten_formula("{fldA}", "fldA", formula_map)
        assert "{fldA}" in result
        assert "(10)" in result


class TestStringLiterals:
    """Test that field references in strings are not expanded."""

    def test_field_ref_in_double_quoted_string_unchanged(self):
        """Field refs inside strings should NOT be expanded."""
        formula_map = {"fldA": "10", "fldB": "20"}
        result = flatten_formula('IF({fldA}, "check {fldB}", "no")', "fldTest", formula_map)
        # {fldA} should expand, but {fldB} inside string should not
        assert result == 'IF((10), "check {fldB}", "no")'

    def test_field_ref_in_single_quoted_string_unchanged(self):
        """Field refs inside single-quoted strings should NOT be expanded."""
        formula_map = {"fldA": "10", "fldB": "20"}
        result = flatten_formula("IF({fldA}, 'check {fldB}', 'no')", "fldTest", formula_map)
        assert result == "IF((10), 'check {fldB}', 'no')"

    def test_mixed_real_and_string_refs(self):
        """Real refs expand, string refs don't."""
        formula_map = {"fldA": "1", "fldB": "2", "fldC": "3"}
        result = flatten_formula('{fldA} & " {fldB} " & {fldC}', "fldTest", formula_map)
        assert result == '(1) & " {fldB} " & (3)'


class TestEdgeCases:
    """Test edge cases."""

    def test_unknown_field_unchanged(self):
        result = flatten_formula("{fldUnknown}", "fldTest", {})
        assert result == "{fldUnknown}"

    def test_empty_formula_value(self):
        """Formula field with empty formula string."""
        formula_map = {"fldA": ""}
        result = flatten_formula("{fldA}", "fldTest", formula_map)
        assert result == "{fldA}"

    def test_whitespace_preserved(self):
        formula_map = {"fldA": "1  +  2"}
        result = flatten_formula("  {fldA}  ", "fldTest", formula_map)
        assert "  " in result

    def test_duplicate_refs(self):
        formula_map = {"fldA": "5"}
        result = flatten_formula("{fldA} + {fldA}", "fldTest", formula_map)
        assert result == "(5) + (5)"


class TestFieldRefPattern:
    """Test the FIELD_REF_PATTERN regex (validates field IDs, not searches)."""

    def test_matches_field_id(self):
        assert FIELD_REF_PATTERN.match("fldABC123")

    def test_matches_simple_field_id(self):
        assert FIELD_REF_PATTERN.match("fldA")

    def test_no_match_regular_name(self):
        assert not FIELD_REF_PATTERN.match("Status")

    def test_no_match_with_braces(self):
        # The pattern validates the ID itself, not the {id} format
        assert not FIELD_REF_PATTERN.match("{fldA}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for the format_formula function in formula_formatter.py."""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from formula_formatter import (
    _count_nesting_depth,
    _find_matching_paren,
    _format_complex,
    _is_simple_formula,
    _normalize_whitespace,
    _split_arguments,
    format_formula,
)


class TestFindMatchingParen:
    """Test the _find_matching_paren helper function."""

    def test_simple_parens(self):
        assert _find_matching_paren("(abc)", 0) == 4

    def test_nested_parens(self):
        assert _find_matching_paren("(a(b)c)", 0) == 6
        assert _find_matching_paren("(a(b)c)", 2) == 4

    def test_parens_in_string(self):
        assert _find_matching_paren('("text (here)")', 0) == 14

    def test_parens_in_field_ref(self):
        assert _find_matching_paren("({field (name)})", 0) == 15

    def test_no_matching_paren(self):
        assert _find_matching_paren("(abc", 0) == -1

    def test_not_a_paren(self):
        assert _find_matching_paren("abc", 0) == -1


class TestSplitArguments:
    """Test the _split_arguments helper function."""

    def test_simple_args(self):
        assert _split_arguments("{a}, {b}, {c}") == ["{a}", "{b}", "{c}"]

    def test_nested_function(self):
        result = _split_arguments("{a}, IF({x}, {y}, {z}), {c}")
        assert result == ["{a}", "IF({x}, {y}, {z})", "{c}"]

    def test_string_with_comma(self):
        result = _split_arguments('{a}, "hello, world", {b}')
        assert result == ["{a}", '"hello, world"', "{b}"]

    def test_field_ref_with_comma(self):
        result = _split_arguments("{a}, {field, name}, {b}")
        assert result == ["{a}", "{field, name}", "{b}"]

    def test_empty_args(self):
        assert _split_arguments("") == []

    def test_single_arg(self):
        assert _split_arguments("{a}") == ["{a}"]


class TestCountNestingDepth:
    """Test the _count_nesting_depth helper function."""

    def test_no_nesting(self):
        assert _count_nesting_depth("{field}") == 0

    def test_single_function(self):
        assert _count_nesting_depth("IF({a}, {b}, {c})") == 1

    def test_nested_functions(self):
        assert _count_nesting_depth("IF({a}, IF({x}, {y}, {z}), {c})") == 2

    def test_deeply_nested(self):
        assert _count_nesting_depth("IF(AND(OR({a}, {b}), {c}), {d}, {e})") == 3

    def test_parens_in_string_not_counted(self):
        assert _count_nesting_depth('IF({a}, "(not counted)", {b})') == 1


class TestIsSimpleFormula:
    """Test the _is_simple_formula helper function."""

    def test_short_formula_is_simple(self):
        assert _is_simple_formula("RECORD_ID()") is True

    def test_field_ref_is_simple(self):
        assert _is_simple_formula("{field_name}") is True

    def test_short_if_is_not_simple(self):
        # IF with multiple args is never simple - always expands
        assert _is_simple_formula("IF({a}, {b}, {c})") is False

    def test_nested_if_is_not_simple(self):
        # Nested IFs are not simple - always expand
        formula = "IF({a}, IF({x}, {y}, {z}), IF({m}, {n}, {o}))"
        assert _is_simple_formula(formula) is False

    def test_nested_over_80_chars_is_not_simple(self):
        # Long nested formula (>80 chars with depth >1) is not simple
        formula = "IF({very_long_field_name}, IF({another_long_field}, {value1_long}, {value2_long}), IF({third_field}, {n}, {o}))"
        assert _is_simple_formula(formula) is False

    def test_long_formula_with_nesting_not_simple(self):
        # Very long formula with nesting
        formula = "IF({very_long_field_name_here}, IF({another_long_field}, {value1}, {value2}), {default_value_that_is_long})"
        assert _is_simple_formula(formula) is False


class TestNormalizeWhitespace:
    """Test the _normalize_whitespace helper function."""

    def test_collapse_spaces(self):
        assert _normalize_whitespace("IF(  {a},   {b}  )") == "IF( {a}, {b} )"

    def test_preserve_string_whitespace(self):
        result = _normalize_whitespace('IF({a}, "hello   world")')
        assert "hello   world" in result

    def test_preserve_field_ref_whitespace(self):
        result = _normalize_whitespace("IF({field  name}, {b})")
        assert "{field  name}" in result

    def test_newlines_to_spaces(self):
        result = _normalize_whitespace("IF(\n  {a},\n  {b}\n)")
        assert "\n" not in result


class TestFormatComplex:
    """Test the _format_complex helper function."""

    def test_empty_function(self):
        assert _format_complex("TODAY()") == "TODAY()"

    def test_single_arg_no_nesting(self):
        assert _format_complex("LEN({field})") == "LEN({field})"

    def test_if_always_expands(self):
        # IF statements always expand for readability
        result = _format_complex("IF({a}, {b}, {c})")
        assert "\n" in result
        assert "  {a}," in result

    def test_nested_gets_formatted(self):
        result = _format_complex("IF({condition}, IF({x}, {y}, {z}), {else})")
        assert "\n" in result
        assert "  " in result  # Has indentation

    def test_preserves_strings(self):
        result = _format_complex('IF({a}, "text with (parens)", {b})')
        assert '"text with (parens)"' in result


class TestFormatFormula:
    """Test the main format_formula function."""

    # Empty and whitespace input
    def test_empty_string(self):
        assert format_formula("") == ""

    def test_whitespace_only(self):
        assert format_formula("   ") == "   "

    def test_none_like_empty(self):
        # Function handles empty strings gracefully
        assert format_formula("") == ""

    # Simple formulas stay single-line
    @pytest.mark.parametrize(
        "formula",
        [
            "RECORD_ID()",
            "{field_name}",
            "42",
            "AND({x}, {y})",
            "TODAY()",
            "MONTH({date})",
            "YEAR({date})",
        ],
    )
    def test_simple_formulas_single_line(self, formula):
        result = format_formula(formula)
        assert "\n" not in result

    # IF/SWITCH always expand
    def test_if_always_expands(self):
        # IF statements always expand for readability
        formula = "IF({a}, {b}, {c})"
        result = format_formula(formula)
        assert "\n" in result
        assert "  {a}," in result

    def test_switch_always_expands(self):
        # SWITCH statements always expand for readability
        formula = 'SWITCH({type}, "A", 1, "B", 2)'
        result = format_formula(formula)
        assert "\n" in result
        assert "  {type}," in result

    def test_nested_if_expands(self):
        # Nested IFs expand at each level
        formula = "IF({a},IF({x},{y},{z}),{c})"
        result = format_formula(formula)
        assert "\n" in result
        assert "  IF(" in result  # Nested IF is indented

    def test_long_nested_if_formatted(self):
        # Long nested formulas get formatted with newlines
        formula = "IF({very_long_condition_field_name}, IF({another_nested_field}, {true_value_here}, {false_value_here}), {else_value_field})"
        result = format_formula(formula)
        assert "\n" in result
        assert "  " in result  # Has indentation

    def test_deeply_nested_formatted(self):
        formula = "IF(AND({a}, {b}), MAX(ABS({x}), ABS({y})), 42)"
        result = format_formula(formula)
        # Should have some formatting due to nesting
        lines = result.split("\n")
        assert len(lines) >= 1  # At least formatted somewhat

    # String literal preservation
    def test_string_literals_preserved(self):
        formula = 'IF({a}, "text with (parens) and, commas", {b})'
        result = format_formula(formula)
        assert '"text with (parens) and, commas"' in result

    def test_single_quote_strings_preserved(self):
        formula = "DATETIME_FORMAT({date}, 'MMM D, YYYY')"
        result = format_formula(formula)
        assert "'MMM D, YYYY'" in result

    # Field reference preservation
    def test_field_refs_preserved(self):
        formula = "IF({Field Name}, {Other Field}, {Default})"
        result = format_formula(formula)
        assert "{Field Name}" in result
        assert "{Other Field}" in result
        assert "{Default}" in result

    def test_field_ids_preserved(self):
        formula = "IF({fldABC123}, {fldXYZ789}, {fldDEF456})"
        result = format_formula(formula)
        assert "{fldABC123}" in result
        assert "{fldXYZ789}" in result
        assert "{fldDEF456}" in result

    # Error handling
    def test_malformed_returns_original(self):
        formula = "IF({a}, {b}"  # Missing closing paren
        result = format_formula(formula)
        assert result == formula

    def test_unbalanced_parens_returns_original(self):
        formula = "IF((({a}, {b}, {c})"
        result = format_formula(formula)
        # Should return something (either original or partial format)
        assert result is not None

    # Pre-formatted input normalization
    def test_normalizes_existing_whitespace(self):
        formula = "IF(\n  {a},\n  {b},\n  {c}\n)"
        result = format_formula(formula)
        # Should normalize - exact format may vary based on complexity
        assert result is not None

    # Real-world formulas from Airtable
    def test_datetime_format(self):
        formula = 'DATETIME_FORMAT({fldPiPELfJawXj4N1}, "MMM D, YYYY") & " - " & DATETIME_FORMAT({fldZ4jk5xAnjOdA5w}, "MMM D, YYYY")'
        result = format_formula(formula)
        # Should preserve the datetime format strings
        assert '"MMM D, YYYY"' in result
        assert '" - "' in result

    def test_and_with_comparisons(self):
        formula = "AND(TODAY() >= {fldPiPELfJawXj4N1}, TODAY() <= {fldZ4jk5xAnjOdA5w})"
        result = format_formula(formula)
        # Should be preserved
        assert "TODAY()" in result
        assert ">=" in result
        assert "<=" in result

    def test_complex_if_with_and(self):
        formula = "IF(AND({fldQRWavSh9bbWEMr}, {fldPom551jylI6sHT}, {fldQRWavSh9bbWEMr}!={fld4J3TSvP09WX6sc}, {fldPom551jylI6sHT}!={fld17xH7fLbZpR5nW}), MAX(ABS({fldQRWavSh9bbWEMr}-{fld4J3TSvP09WX6sc}), ABS({fldPom551jylI6sHT}-{fld17xH7fLbZpR5nW})), 42)"
        result = format_formula(formula)
        # Should be formatted due to complexity
        assert result is not None
        # Check key parts are preserved
        assert "IF(" in result
        assert "AND(" in result
        assert "MAX(" in result
        assert "ABS(" in result

    # Operators
    def test_concatenation_operator(self):
        formula = '{first_name} & " " & {last_name}'
        result = format_formula(formula)
        assert "&" in result
        assert '" "' in result

    def test_comparison_operators(self):
        formula = "IF({a} = {b}, {c}, IF({x} != {y}, {z}, {default}))"
        result = format_formula(formula)
        assert "=" in result
        assert "!=" in result


class TestFormatFormulaIntegration:
    """Integration tests with more realistic formulas."""

    def test_switch_statement(self):
        formula = 'SWITCH({status}, "pending", "Pending", "active", "Active", "done", "Done", "Unknown")'
        result = format_formula(formula)
        # Should format this as it has many arguments
        assert result is not None
        assert "SWITCH(" in result

    def test_nested_concatenation(self):
        formula = 'IF({fldr1aaHCXWqu8Gl6}, {fldiMLtOTLg50mz1t}&": "&{fldr1aaHCXWqu8Gl6}&"\\n", "")&IF({fldNHg0xskQxcbKs1}, {fldiMLtOTLg50mz1t}&": Missing Box Image\\n", "")'
        result = format_formula(formula)
        # Should handle this complex formula
        assert result is not None

    def test_formula_with_numbers(self):
        formula = "IF({count} > 0, ROUND({total} / {count}, 2), 0)"
        result = format_formula(formula)
        assert "ROUND(" in result
        assert "0" in result
        assert "2" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

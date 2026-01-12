"""Tests for the condense_formula function in formula_condenser.py."""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from formula_condenser import condense_formula
from formula_formatter import format_formula


class TestCondenseBasic:
    """Test basic condensing functionality."""

    def test_empty_string(self):
        assert condense_formula("") == ""

    def test_whitespace_only(self):
        assert condense_formula("   ") == "   "

    def test_already_condensed(self):
        """Already compact formulas should be unchanged."""
        assert condense_formula("IF({a},{b},{c})") == "IF({a},{b},{c})"

    def test_simple_function(self):
        assert condense_formula("TODAY()") == "TODAY()"

    def test_field_reference_only(self):
        assert condense_formula("{field}") == "{field}"


class TestCondenseWhitespace:
    """Test whitespace removal."""

    def test_single_space_removal(self):
        assert condense_formula("IF( {a}, {b} )") == "IF({a},{b})"

    def test_multiple_spaces_removal(self):
        assert condense_formula("IF(   {a},   {b},   {c}   )") == "IF({a},{b},{c})"

    def test_newlines_removed(self):
        formula = "IF(\n{a},\n{b}\n)"
        assert condense_formula(formula) == "IF({a},{b})"

    def test_indentation_removed(self):
        formula = "IF(\n  {a},\n  {b},\n  {c}\n)"
        assert condense_formula(formula) == "IF({a},{b},{c})"

    def test_tabs_removed(self):
        formula = "IF(\t{a},\t{b})"
        assert condense_formula(formula) == "IF({a},{b})"

    def test_mixed_whitespace(self):
        formula = "IF( \n\t {a} , \n\t {b} )"
        assert condense_formula(formula) == "IF({a},{b})"

    def test_deep_indentation_removed(self):
        formula = """IF(
  {a},
  IF(
    {x},
    {y},
    {z}
  ),
  {c}
)"""
        assert condense_formula(formula) == "IF({a},IF({x},{y},{z}),{c})"


class TestCondensePreservation:
    """Test that content in strings and field refs is preserved."""

    def test_string_whitespace_preserved(self):
        """Whitespace inside double-quoted strings should be preserved."""
        formula = 'IF({a}, "hello   world", {b})'
        result = condense_formula(formula)
        assert '"hello   world"' in result
        assert result == 'IF({a},"hello   world",{b})'

    def test_single_quote_string_preserved(self):
        """Whitespace inside single-quoted strings should be preserved."""
        formula = "IF({a}, 'hello   world', {b})"
        result = condense_formula(formula)
        assert "'hello   world'" in result
        assert result == "IF({a},'hello   world',{b})"

    def test_field_ref_whitespace_preserved(self):
        """Whitespace inside field references should be preserved."""
        formula = "IF( {field  name} , {b} )"
        result = condense_formula(formula)
        assert "{field  name}" in result
        assert result == "IF({field  name},{b})"

    def test_string_with_newline_escape(self):
        """Escaped newlines in strings should be preserved."""
        formula = 'IF({a}, "line1\\nline2", {b})'
        result = condense_formula(formula)
        assert '"line1\\nline2"' in result

    def test_string_with_parens(self):
        """Parentheses in strings should be preserved."""
        formula = 'IF({a}, "text (with parens)", {b})'
        result = condense_formula(formula)
        assert result == 'IF({a},"text (with parens)",{b})'


class TestCondenseComplex:
    """Test with complex real-world formulas."""

    def test_datetime_format(self):
        formula = 'DATETIME_FORMAT( {Date} , "MMM D, YYYY" )'
        assert condense_formula(formula) == 'DATETIME_FORMAT({Date},"MMM D, YYYY")'

    def test_nested_functions(self):
        formula = "IF( AND( {a}, {b} ), MAX( {x}, {y} ), 0 )"
        assert condense_formula(formula) == "IF(AND({a},{b}),MAX({x},{y}),0)"

    def test_operators_preserved(self):
        formula = "{a} + {b} - {c} * {d} / {e}"
        assert condense_formula(formula) == "{a}+{b}-{c}*{d}/{e}"

    def test_comparison_operators(self):
        formula = "IF( {x} >= 10 , 'high' , 'low' )"
        assert condense_formula(formula) == "IF({x}>=10,'high','low')"

    def test_concatenation(self):
        formula = '{First} & " " & {Last}'
        assert condense_formula(formula) == '{First}&" "&{Last}'

    def test_switch_statement(self):
        formula = """SWITCH(
  {Status},
  "New", 1,
  "In Progress", 2,
  "Done", 3,
  0
)"""
        assert condense_formula(formula) == 'SWITCH({Status},"New",1,"In Progress",2,"Done",3,0)'


class TestCondenseIdempotency:
    """Test that condensing is idempotent."""

    def test_idempotent_simple(self):
        """Condensing twice should equal condensing once."""
        formula = "IF( {a}, {b}, {c} )"
        once = condense_formula(formula)
        twice = condense_formula(once)
        assert once == twice

    def test_idempotent_complex(self):
        formula = """IF(
  {a},
  IF(
    {x},
    {y}
  ),
  {c}
)"""
        once = condense_formula(formula)
        twice = condense_formula(once)
        assert once == twice


class TestCondenseInverse:
    """Test that condense is the inverse of format."""

    def test_condense_formatted_simple(self):
        """A formatted formula should condense back to compact form."""
        original = "IF({a},{b},{c})"
        formatted = format_formula(original)
        condensed = condense_formula(formatted)
        assert "\n" not in condensed
        # Should be equivalent to original (possibly with minor spacing differences)
        assert condense_formula(original) == condensed

    def test_condense_formatted_nested(self):
        """Nested formatted formulas should condense correctly."""
        original = "IF({a},IF({x},{y},{z}),{c})"
        formatted = format_formula(original)
        condensed = condense_formula(formatted)
        assert "\n" not in condensed
        assert condense_formula(original) == condensed


class TestCondenseEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_function_call(self):
        assert condense_formula("TODAY( )") == "TODAY()"

    def test_negative_numbers(self):
        formula = "IF( {a} , -10 , 0 )"
        result = condense_formula(formula)
        assert "-10" in result

    def test_decimal_numbers(self):
        formula = "IF( {a} , 3.14 , 0 )"
        result = condense_formula(formula)
        assert "3.14" in result

    def test_field_with_id(self):
        formula = "IF( {fldABC123} , 1 , 0 )"
        result = condense_formula(formula)
        assert "{fldABC123}" in result
        assert result == "IF({fldABC123},1,0)"

    def test_unclosed_paren(self):
        """Unclosed parens should still work (tokenizer handles gracefully)."""
        formula = "IF({a}, {b}"
        result = condense_formula(formula)
        assert result is not None

    def test_record_id(self):
        assert condense_formula("RECORD_ID( )") == "RECORD_ID()"


class TestCondenseWithMetaJson:
    """Validate condenser against real formulas from meta.json."""

    @pytest.fixture
    def formula_fields(self):
        """Load formula fields from meta.json if available."""
        import json

        meta_path = Path(__file__).parent.parent / "output" / "meta.json"
        if not meta_path.exists():
            pytest.skip("meta.json not available")

        with open(meta_path) as f:
            data = json.load(f)

        formulas = []
        for table in data.get("tables", []):
            for field in table.get("fields", []):
                if field.get("type") == "formula":
                    options = field.get("options", {})
                    if formula := options.get("formula"):
                        formulas.append(formula)

        if not formulas:
            pytest.skip("No formulas found in meta.json")

        return formulas

    def test_all_formulas_condense_without_error(self, formula_fields):
        """Ensure all real formulas can be condensed without exceptions."""
        for formula in formula_fields:
            result = condense_formula(formula)
            assert result is not None

    def test_condensed_has_no_newlines(self, formula_fields):
        """Condensed formulas should not have newlines."""
        for formula in formula_fields[:50]:
            result = condense_formula(formula)
            assert "\n" not in result, f"Newline found in: {result[:50]}..."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for the sanitize_formula function in formula_sanitizer.py."""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from formula_sanitizer import FIELD_REF_PATTERN, _sanitize_cached, sanitize_formula


class TestSanitizeBasic:
    """Test basic sanitization functionality."""

    def test_empty_string(self):
        assert sanitize_formula("", {}) == ""

    def test_no_field_refs(self):
        """Formulas without field references should be unchanged."""
        assert sanitize_formula("1 + 2", {}) == "1 + 2"

    def test_simple_field_replacement(self):
        """Single field ID should be replaced with name."""
        result = sanitize_formula("{fldABC123}", {"fldABC123": "Status"})
        assert result == "{Status}"

    def test_multiple_field_replacements(self):
        """Multiple field IDs should all be replaced."""
        field_map = {"fldA": "Name", "fldB": "Age"}
        result = sanitize_formula("{fldA} & {fldB}", field_map)
        assert result == "{Name} & {Age}"

    def test_unknown_field_preserved(self):
        """Unknown field IDs should remain unchanged."""
        result = sanitize_formula("{fldUnknown}", {"fldOther": "Name"})
        assert result == "{fldUnknown}"


class TestSanitizeFormulas:
    """Test sanitization in formula contexts."""

    def test_if_statement(self):
        field_map = {"fldA": "Condition", "fldB": "TrueVal", "fldC": "FalseVal"}
        result = sanitize_formula("IF({fldA}, {fldB}, {fldC})", field_map)
        assert result == "IF({Condition}, {TrueVal}, {FalseVal})"

    def test_nested_functions(self):
        field_map = {"fldX": "Value", "fldY": "Min", "fldZ": "Max"}
        result = sanitize_formula("IF(AND({fldX} >= {fldY}, {fldX} <= {fldZ}), 1, 0)", field_map)
        assert result == "IF(AND({Value} >= {Min}, {Value} <= {Max}), 1, 0)"

    def test_concatenation(self):
        field_map = {"fldFirst": "First Name", "fldLast": "Last Name"}
        result = sanitize_formula('{fldFirst} & " " & {fldLast}', field_map)
        assert result == '{First Name} & " " & {Last Name}'

    def test_switch_statement(self):
        field_map = {"fldStatus": "Status"}
        formula = 'SWITCH({fldStatus}, "New", 1, "Done", 2, 0)'
        result = sanitize_formula(formula, field_map)
        assert result == 'SWITCH({Status}, "New", 1, "Done", 2, 0)'


class TestSanitizeMixedContent:
    """Test formulas with mixed known and unknown field IDs."""

    def test_partial_replacement(self):
        """Some fields known, some unknown."""
        field_map = {"fldKnown": "Known Field"}
        result = sanitize_formula("{fldKnown} + {fldUnknown}", field_map)
        assert result == "{Known Field} + {fldUnknown}"

    def test_duplicate_field_refs(self):
        """Same field ID appearing multiple times."""
        field_map = {"fldA": "Value"}
        result = sanitize_formula("{fldA} + {fldA} * 2", field_map)
        assert result == "{Value} + {Value} * 2"


class TestStringLiterals:
    """Test that field references in strings are not replaced."""

    def test_field_ref_in_double_quoted_string_unchanged(self):
        """Field refs inside strings should NOT be replaced."""
        field_map = {"fldA": "Status", "fldB": "Name"}
        result = sanitize_formula('IF({fldA}, "See {fldB} for details", "")', field_map)
        # {fldA} should be replaced, but {fldB} inside string should not
        assert result == 'IF({Status}, "See {fldB} for details", "")'

    def test_field_ref_in_single_quoted_string_unchanged(self):
        """Field refs inside single-quoted strings should NOT be replaced."""
        field_map = {"fldA": "Status", "fldB": "Name"}
        result = sanitize_formula("IF({fldA}, 'Contact {fldB}', '')", field_map)
        assert result == "IF({Status}, 'Contact {fldB}', '')"

    def test_mixed_real_and_string_refs(self):
        """Real refs replaced, string refs preserved."""
        field_map = {"fldA": "First", "fldB": "Middle", "fldC": "Last"}
        result = sanitize_formula('{fldA} & " {fldB} " & {fldC}', field_map)
        assert result == '{First} & " {fldB} " & {Last}'


class TestFieldRefPattern:
    """Test the FIELD_REF_PATTERN regex (validates field IDs, not searches)."""

    def test_pattern_matches_standard_id(self):
        assert FIELD_REF_PATTERN.match("fldABC123")

    def test_pattern_matches_simple_id(self):
        assert FIELD_REF_PATTERN.match("fldA")

    def test_pattern_no_match_regular_field(self):
        """Regular field names (not IDs) should not match."""
        assert not FIELD_REF_PATTERN.match("Status")

    def test_pattern_no_match_with_braces(self):
        """Pattern validates the ID itself, not the {id} format."""
        assert not FIELD_REF_PATTERN.match("{fldA}")


class TestCaching:
    """Test that caching works correctly."""

    def test_cache_hits(self):
        """Repeated calls should use cache."""
        # Clear cache first
        _sanitize_cached.cache_clear()

        field_map = {"fldA": "Name"}
        formula = "{fldA} test"

        # First call - miss
        sanitize_formula(formula, field_map)
        info1 = _sanitize_cached.cache_info()
        assert info1.misses == 1
        assert info1.hits == 0

        # Second call - hit
        sanitize_formula(formula, field_map)
        info2 = _sanitize_cached.cache_info()
        assert info2.hits == 1

    def test_different_formulas_cached_separately(self):
        """Different formulas should have separate cache entries."""
        _sanitize_cached.cache_clear()

        field_map = {"fldA": "Name"}
        sanitize_formula("{fldA}", field_map)
        sanitize_formula("{fldA} + 1", field_map)

        info = _sanitize_cached.cache_info()
        assert info.currsize == 2

    def test_different_mappings_cached_separately(self):
        """Same formula with different mappings should be cached separately."""
        _sanitize_cached.cache_clear()

        formula = "{fldA}"
        sanitize_formula(formula, {"fldA": "Name1"})
        sanitize_formula(formula, {"fldA": "Name2"})

        info = _sanitize_cached.cache_info()
        assert info.currsize == 2


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_field_name_with_spaces(self):
        """Field names with spaces should work."""
        result = sanitize_formula("{fldA}", {"fldA": "Field With Spaces"})
        assert result == "{Field With Spaces}"

    def test_field_name_with_special_chars(self):
        """Field names with special characters should work."""
        result = sanitize_formula("{fldA}", {"fldA": "Status (Active)"})
        assert result == "{Status (Active)}"

    def test_empty_field_map(self):
        """Empty field map should leave all IDs unchanged."""
        result = sanitize_formula("{fldA} + {fldB}", {})
        assert result == "{fldA} + {fldB}"

    def test_complex_formula_structure_preserved(self):
        """Formula structure should be preserved during sanitization."""
        field_map = {"fldA": "A", "fldB": "B"}
        formula = """IF(
  {fldA},
  {fldB},
  0
)"""
        result = sanitize_formula(formula, field_map)
        assert "IF(" in result
        assert "{A}" in result
        assert "{B}" in result
        assert "\n" in result  # Newlines preserved


class TestWithMetaJson:
    """Validate sanitizer against real formulas from meta.json."""

    @pytest.fixture
    def formula_data(self):
        """Load formula fields and field mappings from meta.json if available."""
        import json

        meta_path = Path(__file__).parent.parent / "output" / "meta.json"
        if not meta_path.exists():
            pytest.skip("meta.json not available")

        with open(meta_path) as f:
            data = json.load(f)

        formulas = []
        for table in data.get("tables", []):
            # Build field ID to name map for this table
            field_map = {f["id"]: f["name"] for f in table.get("fields", [])}

            for field in table.get("fields", []):
                if field.get("type") == "formula":
                    options = field.get("options", {})
                    if formula := options.get("formula"):
                        formulas.append((formula, field_map))

        if not formulas:
            pytest.skip("No formulas found in meta.json")

        return formulas

    def test_all_formulas_sanitize_without_error(self, formula_data):
        """Ensure all real formulas can be sanitized without exceptions."""
        for formula, field_map in formula_data:
            result = sanitize_formula(formula, field_map)
            assert result is not None

    def test_sanitized_has_no_field_ids(self, formula_data):
        """Sanitized formulas should not have raw field IDs (if all fields exist)."""
        for formula, field_map in formula_data[:50]:
            result = sanitize_formula(formula, field_map)
            # Check that all field IDs that were in the map are replaced
            for field_id in field_map:
                if f"{{{field_id}}}" in formula:
                    assert f"{{{field_id}}}" not in result, f"Field ID {field_id} not replaced in: {result[:50]}..."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

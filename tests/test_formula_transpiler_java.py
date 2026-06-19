"""Tests for Java code emission in the formula transpiler.

Parity with test_formula_transpiler_kotlin.py. Java's emission style mirrors
Kotlin (typed, routes through AirtableRuntime) but produces Jackson
`JsonNode` values via the QUALIFIED AirtableRuntime.V/N/S/A/isTruthy statics
(Java has no top-level functions) and NullNode.getInstance() for null.
Object equality goes through .equals() — never ==.
"""

from src.formulas.formula_transpiler import transpile_formula


class TestJavaEmitter:
    """Java code emission via the transpiler."""

    def _transpile(
        self,
        formula: str,
        field_map: dict | None = None,
        formula_ids: set | None = None,
    ) -> str:
        field_map = field_map or {"fld1": "myField", "fld2": "otherField"}
        formula_ids = formula_ids or set()
        result = transpile_formula(formula, "java", field_map, formula_ids)
        assert result is not None
        return result

    # --- Literals ---

    def test_int_literal(self):
        assert self._transpile("42") == "AirtableRuntime.V(42)"

    def test_negative_int(self):
        assert self._transpile("-5") == "AirtableRuntime.V(-5)"

    def test_decimal_literal(self):
        assert self._transpile("3.14") == "AirtableRuntime.V(3.14)"

    def test_leading_dot_normalized(self):
        # ".5" becomes "0.5" (so it still parses as a double).
        assert self._transpile(".5") == "AirtableRuntime.V(0.5)"

    def test_string_literal(self):
        assert self._transpile('"hello"') == 'AirtableRuntime.V("hello")'

    def test_string_literal_dollar_not_escaped(self):
        # Unlike Kotlin, Java has no string templates — $ stays literal.
        assert self._transpile('"cost: $5"') == 'AirtableRuntime.V("cost: $5")'

    def test_single_quoted_literal_converted_to_double_quoted(self):
        # Backslash-free single-quoted literals convert without other changes.
        assert self._transpile("'hello'") == 'AirtableRuntime.V("hello")'

    def test_single_quoted_literal_with_backslash_doubles_it(self):
        # 'C:\path' — a bare backslash must be doubled or Java sees an illegal \p escape.
        assert self._transpile("'C:\\path'") == 'AirtableRuntime.V("C:\\\\path")'

    def test_single_quoted_literal_with_backslash_in_string_context(self):
        # Function args get the same single->double quote conversion.
        result = self._transpile("UPPER('C:\\path')")
        assert result is not None
        assert '"C:\\\\path"' in result

    # --- Field refs ---

    def test_field_ref_wraps_in_v(self):
        # Raw fields are typed (String, Double, etc.) and must be converted
        # to JsonNode via the qualified AirtableRuntime.V() static.
        assert self._transpile("{fld1}") == "AirtableRuntime.V(this.myField)"

    def test_formula_field_ref_wraps_in_v(self):
        result = self._transpile("{fld1}", formula_ids={"fld1"})
        assert result == "AirtableRuntime.V(this.myField)"

    # --- Arithmetic ---

    def test_addition_wraps_in_v(self):
        result = self._transpile("{fld1} + 5")
        assert result == "AirtableRuntime.V((AirtableRuntime.N(AirtableRuntime.V(this.myField)) + 5.0))"

    def test_subtraction(self):
        # Whole-number literals get decimal form so Java arithmetic stays
        # floating-point (5/2 would otherwise be integer division).
        result = self._transpile("10 - 3")
        assert result == "AirtableRuntime.V((10.0 - 3.0))"

    def test_unary_negation(self):
        result = self._transpile("-{fld1}")
        assert result == "AirtableRuntime.V((-AirtableRuntime.N(AirtableRuntime.V(this.myField))))"

    # --- Comparisons ---

    def test_numeric_equality(self):
        # Numeric equality compares through N() on BOTH sides — N() returns
        # a primitive double, so == is correct here (myairtable-4929).
        result = self._transpile("{fld1} = 5")
        assert result == "AirtableRuntime.V(AirtableRuntime.N(AirtableRuntime.V(this.myField)) == AirtableRuntime.N(AirtableRuntime.V(5)))"

    def test_string_equality(self):
        # S() returns a String object — Java needs .equals(), never ==.
        result = self._transpile('{fld1} = "hi"')
        assert result == 'AirtableRuntime.V(AirtableRuntime.S(AirtableRuntime.V(this.myField)).equals(AirtableRuntime.S(AirtableRuntime.V("hi"))))'

    def test_string_inequality_negates_equals(self):
        result = self._transpile('{fld1} != "hi"')
        assert result == 'AirtableRuntime.V(!AirtableRuntime.S(AirtableRuntime.V(this.myField)).equals(AirtableRuntime.S(AirtableRuntime.V("hi"))))'

    def test_greater_than(self):
        # Numeric comparisons unwrap both sides to double.
        result = self._transpile("{fld1} > 10")
        assert result == "AirtableRuntime.V(AirtableRuntime.N(AirtableRuntime.V(this.myField)) > 10.0)"

    # --- Concatenation ---

    def test_concat(self):
        result = self._transpile('{fld1} & " items"')
        assert result == 'AirtableRuntime.V(AirtableRuntime.S(AirtableRuntime.V(this.myField)) + " items")'

    # --- Boolean literals & combinators ---

    def test_true(self):
        assert self._transpile("TRUE()") == "AirtableRuntime.V(true)"

    def test_false(self):
        assert self._transpile("FALSE()") == "AirtableRuntime.V(false)"

    def test_blank(self):
        assert self._transpile("BLANK()") == "NullNode.getInstance()"

    def test_blank_with_arg(self):
        result = self._transpile("BLANK({fld1})")
        assert result == "AirtableRuntime.V(AirtableRuntime.V(this.myField).isNull())"

    def test_not(self):
        result = self._transpile("NOT(TRUE())")
        assert result == "AirtableRuntime.V(!AirtableRuntime.isTruthy(AirtableRuntime.V(true)))"

    def test_and_two_args(self):
        result = self._transpile("AND(TRUE(), FALSE())")
        assert result == "AirtableRuntime.V(AirtableRuntime.isTruthy(AirtableRuntime.V(true)) && AirtableRuntime.isTruthy(AirtableRuntime.V(false)))"

    def test_or_two_args(self):
        result = self._transpile("OR(TRUE(), FALSE())")
        assert result == "AirtableRuntime.V(AirtableRuntime.isTruthy(AirtableRuntime.V(true)) || AirtableRuntime.isTruthy(AirtableRuntime.V(false)))"

    def test_xor(self):
        result = self._transpile("XOR(TRUE(), FALSE())")
        assert "AirtableRuntime.isTruthy" in result
        assert " != " in result

    # --- Conditionals ---

    def test_if_basic(self):
        result = self._transpile("IF({fld1}, 1, 0)")
        assert result == "(AirtableRuntime.isTruthy(AirtableRuntime.V(this.myField)) ? AirtableRuntime.V(1) : AirtableRuntime.V(0))"

    def test_if_without_else(self):
        # Missing else branch defaults to NullNode.getInstance().
        result = self._transpile("IF({fld1}, 1)")
        assert result.endswith(": NullNode.getInstance())")

    def test_ifs(self):
        result = self._transpile("IFS({fld1}, 1, {fld2}, 2)")
        assert "AirtableRuntime.isTruthy" in result
        assert "AirtableRuntime.V(1)" in result
        assert "AirtableRuntime.V(2)" in result
        assert "NullNode.getInstance()" in result  # fallback

    def test_switch(self):
        # Java SWITCH(expr, default, flatPairs...) — varargs must come last,
        # so the default precedes the flat pattern/value pairs. The non-literal
        # expr is string-coerced to match the string patterns.
        result = self._transpile('SWITCH({fld1}, "a", 1, "b", 2, 99)')
        assert result == (
            "AirtableRuntime.SWITCH("
            "AirtableRuntime.V(AirtableRuntime.S(AirtableRuntime.V(this.myField))), "
            "AirtableRuntime.V(99), "
            'AirtableRuntime.V("a"), AirtableRuntime.V(1), '
            'AirtableRuntime.V("b"), AirtableRuntime.V(2))'
        )

    # --- Record ID ---

    def test_record_id(self):
        assert self._transpile("RECORD_ID()") == 'AirtableRuntime.V(this.id != null ? this.id : "")'

    # --- Function fall-through (should hit default runtime path) ---

    def test_sum(self):
        result = self._transpile("SUM({fld1}, {fld2})")
        assert result == "AirtableRuntime.SUM(AirtableRuntime.V(this.myField), AirtableRuntime.V(this.otherField))"

    def test_min(self):
        result = self._transpile("MIN({fld1}, 5)")
        assert result.startswith("AirtableRuntime.MIN(")

    def test_average(self):
        result = self._transpile("AVERAGE({fld1}, {fld2})")
        assert result.startswith("AirtableRuntime.AVERAGE(")

    def test_round_with_precision(self):
        result = self._transpile("ROUND({fld1}, 2)")
        assert result == "AirtableRuntime.ROUND(AirtableRuntime.V(this.myField), AirtableRuntime.V(2))"

    def test_round_default_precision(self):
        # ROUND with one arg → Java runtime overload handles precision.
        result = self._transpile("ROUND({fld1})")
        assert result == "AirtableRuntime.ROUND(AirtableRuntime.V(this.myField))"

    def test_len(self):
        result = self._transpile("LEN({fld1})")
        assert result == "AirtableRuntime.LEN(AirtableRuntime.V(this.myField))"

    def test_upper(self):
        result = self._transpile("UPPER({fld1})")
        assert result == "AirtableRuntime.UPPER(AirtableRuntime.V(this.myField))"

    def test_concatenate(self):
        result = self._transpile('CONCATENATE({fld1}, "-", {fld2})')
        assert result.startswith("AirtableRuntime.CONCATENATE(")

    def test_datetime_parse_single_arg(self):
        result = self._transpile('DATETIME_PARSE("2025-01-15")')
        assert result == 'AirtableRuntime.DATETIME_PARSE(AirtableRuntime.V("2025-01-15"))'

    def test_year_falls_through(self):
        result = self._transpile("YEAR({fld1})")
        assert result == "AirtableRuntime.YEAR(AirtableRuntime.V(this.myField))"

    def test_regex_match_falls_through(self):
        result = self._transpile('REGEX_MATCH({fld1}, "\\\\d+")')
        assert result.startswith("AirtableRuntime.REGEX_MATCH(")

    def test_countall(self):
        result = self._transpile("COUNTALL({fld1})")
        assert result == "AirtableRuntime.V(AirtableRuntime.A(java.util.List.of(AirtableRuntime.V(this.myField))).size())"

    def test_log10_maps_to_log(self):
        result = self._transpile("LOG10({fld1})")
        assert result == "AirtableRuntime.LOG(AirtableRuntime.V(this.myField))"

    def test_numeric_inequality_coerces_both_sides(self):
        result = self._transpile("{fld1} != 5")
        assert result == "AirtableRuntime.V(AirtableRuntime.N(AirtableRuntime.V(this.myField)) != AirtableRuntime.N(AirtableRuntime.V(5)))"

    def test_field_vs_field_equality_without_inferable_type_uses_equals(self):
        # Neither side is inferable — falls back to raw JsonNode comparison,
        # which in Java must be .equals() (== would compare references).
        result = self._transpile("{fld1} = {fld2}")
        assert result == "AirtableRuntime.V(AirtableRuntime.V(this.myField).equals(AirtableRuntime.V(this.otherField)))"

    def test_field_vs_field_inequality_without_inferable_type_negates_equals(self):
        result = self._transpile("{fld1} != {fld2}")
        assert result == "AirtableRuntime.V(!AirtableRuntime.V(this.myField).equals(AirtableRuntime.V(this.otherField)))"

    def test_field_vs_numeric_expression_equality_coerces(self):
        # An arithmetic side infers numeric -> both sides N-coerced.
        result = self._transpile("{fld1} = {fld2} + 1")
        assert "AirtableRuntime.V(AirtableRuntime.N(AirtableRuntime.V(this.myField)) == AirtableRuntime.N(" in result

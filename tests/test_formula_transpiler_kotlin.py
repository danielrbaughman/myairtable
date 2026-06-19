"""Tests for Kotlin code emission in the formula transpiler (K8.8).

Parity with test_formula_transpiler_swift.py. Kotlin's emission style mirrors
Swift (typed, routes through AirtableRuntime) but produces kotlinx
`JsonElement` values via JsonPrimitive/JsonNull and uses the top-level
V/N/S/A/isTruthy coercion helpers (flat `myairtable` package — no qualifier).
"""

from src.formulas.formula_transpiler import transpile_formula


class TestKotlinEmitter:
    """Kotlin code emission via the transpiler."""

    def _transpile(
        self,
        formula: str,
        field_map: dict | None = None,
        formula_ids: set | None = None,
    ) -> str:
        field_map = field_map or {"fld1": "myField", "fld2": "otherField"}
        formula_ids = formula_ids or set()
        result = transpile_formula(formula, "kotlin", field_map, formula_ids)
        assert result is not None
        return result

    # --- Literals ---

    def test_int_literal(self):
        assert self._transpile("42") == "JsonPrimitive(42)"

    def test_negative_int(self):
        assert self._transpile("-5") == "JsonPrimitive(-5)"

    def test_decimal_literal(self):
        assert self._transpile("3.14") == "JsonPrimitive(3.14)"

    def test_leading_dot_normalized(self):
        # ".5" becomes "0.5" (so it still parses as a double).
        assert self._transpile(".5") == "JsonPrimitive(0.5)"

    def test_string_literal(self):
        assert self._transpile('"hello"') == 'JsonPrimitive("hello")'

    def test_string_literal_escapes_dollar(self):
        # Kotlin string templates: a raw $ must be escaped.
        assert self._transpile('"cost: $5"') == 'JsonPrimitive("cost: \\$5")'

    def test_single_quoted_literal_converted_to_double_quoted(self):
        # Backslash-free single-quoted literals convert without other changes.
        assert self._transpile("'hello'") == 'JsonPrimitive("hello")'

    def test_single_quoted_literal_with_backslash_doubles_it(self):
        # 'C:\path' — a bare backslash must be doubled or Kotlin sees an illegal \p escape.
        assert self._transpile("'C:\\path'") == 'JsonPrimitive("C:\\\\path")'

    def test_single_quoted_literal_with_backslash_in_string_context(self):
        # _emit_str path (function args in string context) gets the same conversion.
        result = self._transpile("UPPER('C:\\path')")
        assert result is not None
        assert '"C:\\\\path"' in result

    # --- Field refs ---

    def test_field_ref_wraps_in_v(self):
        # Raw fields are typed (String?, Double?, etc.) and must be converted
        # to JsonElement via the top-level V() helper.
        assert self._transpile("{fld1}") == "V(this.myField)"

    def test_formula_field_ref_wraps_in_v(self):
        result = self._transpile("{fld1}", formula_ids={"fld1"})
        assert result == "V(this.myField)"

    # --- Arithmetic ---

    def test_addition_wraps_in_json_primitive(self):
        result = self._transpile("{fld1} + 5")
        assert result == "JsonPrimitive((N(V(this.myField)) + 5.0))"

    def test_subtraction(self):
        result = self._transpile("10 - 3")
        assert result == "JsonPrimitive((10.0 - 3.0))"

    def test_unary_negation(self):
        result = self._transpile("-{fld1}")
        assert result == "JsonPrimitive((-N(V(this.myField))))"

    # --- Comparisons ---

    def test_numeric_equality(self):
        # Numeric equality compares through N() on BOTH sides — JsonPrimitive
        # content equality would make Double "5.0" != Int "5" (myairtable-4929).
        result = self._transpile("{fld1} = 5")
        assert result == "JsonPrimitive(N(V(this.myField)) == N(JsonPrimitive(5)))"

    def test_string_equality(self):
        result = self._transpile('{fld1} = "hi"')
        assert result == 'JsonPrimitive(S(V(this.myField)) == S(JsonPrimitive("hi")))'

    def test_greater_than(self):
        # Numeric comparisons unwrap both sides to Double.
        result = self._transpile("{fld1} > 10")
        assert result == "JsonPrimitive(N(V(this.myField)) > 10.0)"

    # --- Concatenation ---

    def test_concat(self):
        result = self._transpile('{fld1} & " items"')
        assert result == 'JsonPrimitive(S(V(this.myField)) + " items")'

    # --- Boolean literals & combinators ---

    def test_true(self):
        assert self._transpile("TRUE()") == "JsonPrimitive(true)"

    def test_false(self):
        assert self._transpile("FALSE()") == "JsonPrimitive(false)"

    def test_blank(self):
        assert self._transpile("BLANK()") == "JsonNull"

    def test_not(self):
        result = self._transpile("NOT(TRUE())")
        assert result == "JsonPrimitive(!isTruthy(JsonPrimitive(true)))"

    def test_and_two_args(self):
        result = self._transpile("AND(TRUE(), FALSE())")
        assert result == "JsonPrimitive(isTruthy(JsonPrimitive(true)) && isTruthy(JsonPrimitive(false)))"

    def test_or_two_args(self):
        result = self._transpile("OR(TRUE(), FALSE())")
        assert result == "JsonPrimitive(isTruthy(JsonPrimitive(true)) || isTruthy(JsonPrimitive(false)))"

    def test_xor(self):
        result = self._transpile("XOR(TRUE(), FALSE())")
        assert "isTruthy" in result
        assert " != " in result

    # --- Conditionals ---

    def test_if_basic(self):
        result = self._transpile("IF({fld1}, 1, 0)")
        assert result == "(if (isTruthy(V(this.myField))) JsonPrimitive(1) else JsonPrimitive(0))"

    def test_if_without_else(self):
        # Missing else branch defaults to JsonNull.
        result = self._transpile("IF({fld1}, 1)")
        assert result.endswith("else JsonNull)")

    def test_ifs(self):
        result = self._transpile("IFS({fld1}, 1, {fld2}, 2)")
        assert "isTruthy" in result
        assert "JsonPrimitive(1)" in result
        assert "JsonPrimitive(2)" in result
        assert "JsonNull" in result  # fallback

    def test_switch(self):
        result = self._transpile('SWITCH({fld1}, "a", 1, "b", 2, 99)')
        assert "AirtableRuntime.SWITCH" in result
        assert "listOf(" in result
        assert " to " in result

    # --- Record ID ---

    def test_record_id(self):
        assert self._transpile("RECORD_ID()") == 'JsonPrimitive(this.id ?: "")'

    # --- Function fall-through (should hit default runtime path) ---

    def test_sum(self):
        result = self._transpile("SUM({fld1}, {fld2})")
        assert result == "AirtableRuntime.SUM(V(this.myField), V(this.otherField))"

    def test_min(self):
        result = self._transpile("MIN({fld1}, 5)")
        assert result.startswith("AirtableRuntime.MIN(")

    def test_average(self):
        result = self._transpile("AVERAGE({fld1}, {fld2})")
        assert result.startswith("AirtableRuntime.AVERAGE(")

    def test_round_with_precision(self):
        result = self._transpile("ROUND({fld1}, 2)")
        assert result == "AirtableRuntime.ROUND(V(this.myField), JsonPrimitive(2))"

    def test_round_default_precision(self):
        # ROUND with one arg → Kotlin default parameter handles precision.
        result = self._transpile("ROUND({fld1})")
        assert result == "AirtableRuntime.ROUND(V(this.myField))"

    def test_len(self):
        result = self._transpile("LEN({fld1})")
        assert result == "AirtableRuntime.LEN(V(this.myField))"

    def test_upper(self):
        result = self._transpile("UPPER({fld1})")
        assert result == "AirtableRuntime.UPPER(V(this.myField))"

    def test_concatenate(self):
        result = self._transpile('CONCATENATE({fld1}, "-", {fld2})')
        assert result.startswith("AirtableRuntime.CONCATENATE(")

    def test_datetime_parse_single_arg(self):
        result = self._transpile('DATETIME_PARSE("2025-01-15")')
        assert result == 'AirtableRuntime.DATETIME_PARSE(JsonPrimitive("2025-01-15"))'

    def test_year_falls_through(self):
        result = self._transpile("YEAR({fld1})")
        assert result == "AirtableRuntime.YEAR(V(this.myField))"

    def test_regex_match_falls_through(self):
        result = self._transpile('REGEX_MATCH({fld1}, "\\\\d+")')
        assert result.startswith("AirtableRuntime.REGEX_MATCH(")

    def test_countall(self):
        result = self._transpile("COUNTALL({fld1})")
        assert result == "JsonPrimitive(A(listOf(V(this.myField))).size)"

    def test_log10_maps_to_log(self):
        result = self._transpile("LOG10({fld1})")
        assert result == "AirtableRuntime.LOG(V(this.myField))"

    def test_numeric_inequality_coerces_both_sides(self):
        result = self._transpile("{fld1} != 5")
        assert result == "JsonPrimitive(N(V(this.myField)) != N(JsonPrimitive(5)))"

    def test_field_vs_field_equality_without_inferable_type_stays_raw(self):
        # Neither side is inferable — falls back to raw JsonElement equality
        # (cross-target parity with Swift/Rust raw comparisons).
        result = self._transpile("{fld1} = {fld2}")
        assert result == "JsonPrimitive(V(this.myField) == V(this.otherField))"

    def test_field_vs_numeric_expression_equality_coerces(self):
        # An arithmetic side infers numeric -> both sides N-coerced.
        result = self._transpile("{fld1} = {fld2} + 1")
        assert "JsonPrimitive(N(V(this.myField)) == N(" in result

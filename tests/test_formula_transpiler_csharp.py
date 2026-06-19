"""Tests for C# code emission in the formula transpiler (CS8.10).

Parity with test_formula_transpiler_java.py. C#'s emission mirrors Java (typed,
routes through the QUALIFIED AirtableRuntime.V/N/S/A/IsTruthy statics) but:
PascalCase field refs (`this.MyField`), bare `null` for JSON-null (no NullNode),
record id via `this.Id ?? ""`, and equality via C# value `==` + IsEqual (no .equals()).
"""

from src.formulas.formula_transpiler import transpile_formula


class TestCSharpEmitter:
    """C# code emission via the transpiler."""

    def _transpile(
        self,
        formula: str,
        field_map: dict | None = None,
        formula_ids: set | None = None,
    ) -> str:
        field_map = field_map or {"fld1": "MyField", "fld2": "OtherField"}
        formula_ids = formula_ids or set()
        result = transpile_formula(formula, "csharp", field_map, formula_ids)
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
        assert self._transpile(".5") == "AirtableRuntime.V(0.5)"

    def test_string_literal(self):
        assert self._transpile('"hello"') == 'AirtableRuntime.V("hello")'

    def test_string_literal_dollar_not_escaped(self):
        # C# regular strings treat `$` literally (only $"..." interpolates).
        assert self._transpile('"cost: $5"') == 'AirtableRuntime.V("cost: $5")'

    def test_single_quoted_literal_converted_to_double_quoted(self):
        assert self._transpile("'hello'") == 'AirtableRuntime.V("hello")'

    def test_single_quoted_literal_with_backslash_doubles_it(self):
        assert self._transpile("'C:\\path'") == 'AirtableRuntime.V("C:\\\\path")'

    # --- Field references ---

    def test_field_ref_wraps_in_v_pascalcase(self):
        assert self._transpile("{fld1}") == "AirtableRuntime.V(this.MyField)"

    def test_formula_field_ref_wraps_in_v(self):
        result = self._transpile("{fld1}", formula_ids={"fld1"})
        assert result == "AirtableRuntime.V(this.MyField)"

    # --- Arithmetic ---

    def test_addition_wraps_in_v(self):
        result = self._transpile("{fld1} + 5")
        assert result == "AirtableRuntime.V((AirtableRuntime.N(AirtableRuntime.V(this.MyField)) + 5.0))"

    def test_unary_negation(self):
        result = self._transpile("-{fld1}")
        assert result == "AirtableRuntime.V((-AirtableRuntime.N(AirtableRuntime.V(this.MyField))))"

    # --- Comparisons / equality ---

    def test_numeric_equality(self):
        result = self._transpile("{fld1} = 5")
        assert result == "AirtableRuntime.V(AirtableRuntime.N(AirtableRuntime.V(this.MyField)) == AirtableRuntime.N(AirtableRuntime.V(5)))"

    def test_numeric_inequality(self):
        result = self._transpile("{fld1} != 5")
        assert result == "AirtableRuntime.V(AirtableRuntime.N(AirtableRuntime.V(this.MyField)) != AirtableRuntime.N(AirtableRuntime.V(5)))"

    def test_string_equality_uses_value_equals(self):
        result = self._transpile('{fld1} = "hi"')
        assert result == 'AirtableRuntime.V(AirtableRuntime.S(AirtableRuntime.V(this.MyField)) == AirtableRuntime.S(AirtableRuntime.V("hi")))'

    def test_greater_than(self):
        result = self._transpile("{fld1} > 10")
        assert result == "AirtableRuntime.V(AirtableRuntime.N(AirtableRuntime.V(this.MyField)) > 10.0)"

    def test_field_vs_field_equality_uses_isequal(self):
        # Neither side inferable → coercion-aware IsEqual (never reference ==).
        result = self._transpile("{fld1} = {fld2}")
        assert result == "AirtableRuntime.V(AirtableRuntime.IsEqual(AirtableRuntime.V(this.MyField), AirtableRuntime.V(this.OtherField)))"

    def test_field_vs_field_inequality_negates_isequal(self):
        result = self._transpile("{fld1} != {fld2}")
        assert result == "AirtableRuntime.V(!AirtableRuntime.IsEqual(AirtableRuntime.V(this.MyField), AirtableRuntime.V(this.OtherField)))"

    # --- Concatenation ---

    def test_concat(self):
        result = self._transpile('{fld1} & " items"')
        assert result == 'AirtableRuntime.V(AirtableRuntime.S(AirtableRuntime.V(this.MyField)) + " items")'

    # --- Boolean literals & combinators ---

    def test_true(self):
        assert self._transpile("TRUE()") == "AirtableRuntime.V(true)"

    def test_false(self):
        assert self._transpile("FALSE()") == "AirtableRuntime.V(false)"

    def test_blank_bare_null(self):
        assert self._transpile("BLANK()") == "null"

    def test_blank_with_arg(self):
        result = self._transpile("BLANK({fld1})")
        assert result == "AirtableRuntime.V((AirtableRuntime.V(this.MyField)) == null)"

    def test_not(self):
        result = self._transpile("NOT(TRUE())")
        assert result == "AirtableRuntime.V(!AirtableRuntime.IsTruthy(AirtableRuntime.V(true)))"

    def test_and_two_args(self):
        result = self._transpile("AND(TRUE(), FALSE())")
        assert result == "AirtableRuntime.V(AirtableRuntime.IsTruthy(AirtableRuntime.V(true)) && AirtableRuntime.IsTruthy(AirtableRuntime.V(false)))"

    def test_or_two_args(self):
        result = self._transpile("OR(TRUE(), FALSE())")
        assert result == "AirtableRuntime.V(AirtableRuntime.IsTruthy(AirtableRuntime.V(true)) || AirtableRuntime.IsTruthy(AirtableRuntime.V(false)))"

    def test_xor(self):
        result = self._transpile("XOR(TRUE(), FALSE())")
        assert "AirtableRuntime.IsTruthy" in result
        assert " != " in result

    # --- Conditionals ---

    def test_if_basic(self):
        result = self._transpile("IF({fld1}, 1, 0)")
        assert result == "(AirtableRuntime.IsTruthy(AirtableRuntime.V(this.MyField)) ? AirtableRuntime.V(1) : AirtableRuntime.V(0))"

    def test_if_without_else_bare_null(self):
        result = self._transpile("IF({fld1}, 1)")
        assert result.endswith(": null)")

    def test_ifs(self):
        result = self._transpile("IFS({fld1}, 1, {fld2}, 2)")
        assert "AirtableRuntime.IsTruthy" in result
        assert "AirtableRuntime.V(1)" in result
        assert "AirtableRuntime.V(2)" in result
        assert ": null)" in result  # bare-null fallback (no NullNode)

    def test_switch(self):
        result = self._transpile('SWITCH({fld1}, "a", 1, "b", 2, 99)')
        assert result == (
            "AirtableRuntime.SWITCH("
            "AirtableRuntime.V(AirtableRuntime.S(AirtableRuntime.V(this.MyField))), "
            "AirtableRuntime.V(99), "
            'AirtableRuntime.V("a"), AirtableRuntime.V(1), '
            'AirtableRuntime.V("b"), AirtableRuntime.V(2))'
        )

    # --- Record ID ---

    def test_record_id(self):
        assert self._transpile("RECORD_ID()") == 'AirtableRuntime.V(this.Id ?? "")'

    # --- Function fall-through (default runtime path) ---

    def test_sum(self):
        result = self._transpile("SUM({fld1}, {fld2})")
        assert result == "AirtableRuntime.SUM(AirtableRuntime.V(this.MyField), AirtableRuntime.V(this.OtherField))"

    def test_round_with_precision(self):
        result = self._transpile("ROUND({fld1}, 2)")
        assert result == "AirtableRuntime.ROUND(AirtableRuntime.V(this.MyField), AirtableRuntime.V(2))"

    def test_round_default_precision(self):
        result = self._transpile("ROUND({fld1})")
        assert result == "AirtableRuntime.ROUND(AirtableRuntime.V(this.MyField))"

    def test_len(self):
        assert self._transpile("LEN({fld1})") == "AirtableRuntime.LEN(AirtableRuntime.V(this.MyField))"

    def test_upper(self):
        assert self._transpile("UPPER({fld1})") == "AirtableRuntime.UPPER(AirtableRuntime.V(this.MyField))"

    def test_concatenate(self):
        result = self._transpile('CONCATENATE({fld1}, "-", {fld2})')
        assert result.startswith("AirtableRuntime.CONCATENATE(")

    def test_datetime_parse_single_arg(self):
        result = self._transpile('DATETIME_PARSE("2025-01-15")')
        assert result == 'AirtableRuntime.DATETIME_PARSE(AirtableRuntime.V("2025-01-15"))'

    def test_year_falls_through(self):
        assert self._transpile("YEAR({fld1})") == "AirtableRuntime.YEAR(AirtableRuntime.V(this.MyField))"

    def test_regex_match_falls_through(self):
        result = self._transpile('REGEX_MATCH({fld1}, "\\\\d+")')
        assert result.startswith("AirtableRuntime.REGEX_MATCH(")

    def test_countall(self):
        result = self._transpile("COUNTALL({fld1})")
        assert result == "AirtableRuntime.V(AirtableRuntime.A(new JsonNode?[] { AirtableRuntime.V(this.MyField) }).Count)"

    def test_log10_maps_to_log(self):
        assert self._transpile("LOG10({fld1})") == "AirtableRuntime.LOG(AirtableRuntime.V(this.MyField))"

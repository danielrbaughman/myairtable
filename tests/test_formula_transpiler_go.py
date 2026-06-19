"""Tests for Go code emission in the formula transpiler.

Parity with test_formula_transpiler_java/_kotlin/_swift, but Go follows the
NATIVE-value model (like TS/Python): the runtime value is plain `any`, runtime
functions are called BARE (same package — `LOWER(x)`, `S(x)`, `N(x)`, `IF(...)`),
literals are bare native Go (`"x"`, `5.0`, `true`, `nil`), `_self` is the
receiver `m`, and field refs flow through `V(m.Field)`. Go has NO ternary, so
IF/IFS/SWITCH emit runtime FUNCTION calls; AND/OR/NOT/XOR emit inline IsTruthy().
"""

from src.formulas.formula_transpiler import transpile_formula


class TestGoEmitter:
    """Go code emission via the transpiler."""

    def _transpile(
        self,
        formula: str,
        field_map: dict | None = None,
        formula_ids: set | None = None,
    ) -> str | None:
        field_map = field_map or {"fld1": "MyField", "fld2": "OtherField"}
        formula_ids = formula_ids or set()
        return transpile_formula(formula, "go", field_map, formula_ids)

    # --- Literals (bare native Go) ---

    def test_int_literal(self):
        # Whole numbers gain a `.0` so they box as float64 in the `any` runtime.
        assert self._transpile("42") == "42.0"

    def test_negative_int(self):
        assert self._transpile("-5") == "-5.0"

    def test_decimal_literal(self):
        assert self._transpile("3.14") == "3.14"

    def test_leading_dot_normalized(self):
        assert self._transpile(".5") == "0.5"

    def test_string_literal(self):
        assert self._transpile('"hello"') == '"hello"'

    def test_string_literal_dollar_not_escaped(self):
        # Go has no string templates — $ stays literal.
        assert self._transpile('"cost: $5"') == '"cost: $5"'

    def test_single_quoted_literal_converted_to_double_quoted(self):
        assert self._transpile("'hello'") == '"hello"'

    def test_single_quoted_literal_with_backslash_doubles_it(self):
        # 'C:\path' — a bare backslash must be doubled or Go sees an illegal escape.
        assert self._transpile("'C:\\path'") == '"C:\\\\path"'

    def test_single_quoted_literal_with_backslash_in_string_context(self):
        result = self._transpile("UPPER('C:\\path')")
        assert result is not None
        assert '"C:\\\\path"' in result

    # --- Field refs (V(m.Field)) ---

    def test_field_ref_wraps_in_v(self):
        assert self._transpile("{fld1}") == "V(m.MyField)"

    def test_formula_field_ref_wraps_in_v(self):
        result = self._transpile("{fld1}", formula_ids={"fld1"})
        assert result == "V(m.MyField)"

    # --- Arithmetic (over N(), bare float64) ---

    def test_addition(self):
        result = self._transpile("{fld1} + 5")
        assert result == "(N(V(m.MyField)) + 5.0)"

    def test_subtraction(self):
        result = self._transpile("10 - 3")
        assert result == "(10.0 - 3.0)"

    def test_multiplication(self):
        result = self._transpile("{fld1} * 2")
        assert result == "(N(V(m.MyField)) * 2.0)"

    def test_division(self):
        result = self._transpile("{fld1} / {fld2}")
        assert result == "(N(V(m.MyField)) / N(V(m.OtherField)))"

    def test_unary_negation(self):
        result = self._transpile("-{fld1}")
        assert result == "(-N(V(m.MyField)))"

    # --- Comparisons ---

    def test_numeric_equality(self):
        # Numeric equality compares through N() on BOTH sides (float64 ==).
        result = self._transpile("{fld1} = 5")
        assert result == "(N(V(m.MyField)) == N(5.0))"

    def test_numeric_inequality_coerces_both_sides(self):
        result = self._transpile("{fld1} != 5")
        assert result == "(N(V(m.MyField)) != N(5.0))"

    def test_string_equality(self):
        result = self._transpile('{fld1} = "hi"')
        assert result == '(S(V(m.MyField)) == S("hi"))'

    def test_string_inequality(self):
        result = self._transpile('{fld1} != "hi"')
        assert result == '(S(V(m.MyField)) != S("hi"))'

    def test_field_vs_field_equality_uses_isequal(self):
        # Neither side inferable — coercion-aware runtime IsEqual.
        result = self._transpile("{fld1} = {fld2}")
        assert result == "IsEqual(V(m.MyField), V(m.OtherField))"

    def test_field_vs_field_inequality_negates_isequal(self):
        result = self._transpile("{fld1} != {fld2}")
        assert result == "!IsEqual(V(m.MyField), V(m.OtherField))"

    def test_field_vs_numeric_expression_equality_coerces(self):
        result = self._transpile("{fld1} = {fld2} + 1")
        assert result == "(N(V(m.MyField)) == N((N(V(m.OtherField)) + 1.0)))"

    def test_greater_than(self):
        result = self._transpile("{fld1} > 10")
        assert result == "(N(V(m.MyField)) > 10.0)"

    def test_less_than_or_equal(self):
        result = self._transpile("{fld1} <= 10")
        assert result == "(N(V(m.MyField)) <= 10.0)"

    # --- Concatenation (string + over S()) ---

    def test_concat(self):
        result = self._transpile('{fld1} & " items"')
        assert result == '(S(V(m.MyField)) + " items")'

    def test_concat_two_fields(self):
        result = self._transpile("{fld1} & {fld2}")
        assert result == "(S(V(m.MyField)) + S(V(m.OtherField)))"

    # --- Boolean literals & combinators ---

    def test_true(self):
        assert self._transpile("TRUE()") == "true"

    def test_false(self):
        assert self._transpile("FALSE()") == "false"

    def test_blank(self):
        assert self._transpile("BLANK()") == "nil"

    def test_blank_with_arg(self):
        result = self._transpile("BLANK({fld1})")
        assert result == "V((V(m.MyField)) == nil)"

    def test_not(self):
        result = self._transpile("NOT(TRUE())")
        assert result == "!IsTruthy(true)"

    def test_and_two_args(self):
        result = self._transpile("AND(TRUE(), FALSE())")
        assert result == "(IsTruthy(true) && IsTruthy(false))"

    def test_or_two_args(self):
        result = self._transpile("OR(TRUE(), FALSE())")
        assert result == "(IsTruthy(true) || IsTruthy(false))"

    def test_and_single_arg_passthrough(self):
        result = self._transpile("AND({fld1})")
        assert result == "V(m.MyField)"

    def test_xor(self):
        result = self._transpile("XOR(TRUE(), FALSE())")
        assert result == "(IsTruthy(true) != IsTruthy(false))"

    # --- Conditionals (runtime functions — Go has no ternary) ---

    def test_if_basic(self):
        result = self._transpile("IF({fld1}, 1, 0)")
        assert result == "IF(V(m.MyField), 1.0, 0.0)"

    def test_if_without_else(self):
        result = self._transpile("IF({fld1}, 1)")
        assert result == "IF(V(m.MyField), 1.0, nil)"

    def test_ifs(self):
        result = self._transpile("IFS({fld1}, 1, {fld2}, 2)")
        assert result == "IFS(V(m.MyField), 1.0, V(m.OtherField), 2.0)"

    def test_switch(self):
        # Go SWITCH(expr, fallback, flatPairs...) — fallback comes second
        # (varargs last). Non-literal expr is string-coerced to match patterns.
        result = self._transpile('SWITCH({fld1}, "a", 1, "b", 2, 99)')
        assert result == 'SWITCH(S(V(m.MyField)), 99.0, "a", 1.0, "b", 2.0)'

    def test_switch_no_default(self):
        result = self._transpile('SWITCH({fld1}, "a", 1)')
        assert result == 'SWITCH(S(V(m.MyField)), nil, "a", 1.0)'

    # --- Record ID ---

    def test_record_id(self):
        assert self._transpile("RECORD_ID()") == "V(m.ID())"

    # --- Function fall-through (bare runtime calls) ---

    def test_sum(self):
        result = self._transpile("SUM({fld1}, {fld2})")
        assert result == "SUM(V(m.MyField), V(m.OtherField))"

    def test_min(self):
        result = self._transpile("MIN({fld1}, 5)")
        assert result == "MIN(V(m.MyField), 5.0)"

    def test_max(self):
        result = self._transpile("MAX({fld1}, 5)")
        assert result == "MAX(V(m.MyField), 5.0)"

    def test_average(self):
        result = self._transpile("AVERAGE({fld1}, {fld2})")
        assert result == "AVERAGE(V(m.MyField), V(m.OtherField))"

    def test_round_with_precision(self):
        result = self._transpile("ROUND({fld1}, 2)")
        assert result == "ROUND(V(m.MyField), 2.0)"

    def test_round_default_precision(self):
        result = self._transpile("ROUND({fld1})")
        assert result == "ROUND(V(m.MyField))"

    def test_len(self):
        result = self._transpile("LEN({fld1})")
        assert result == "LEN(V(m.MyField))"

    def test_upper(self):
        result = self._transpile("UPPER({fld1})")
        assert result == "UPPER(V(m.MyField))"

    def test_lower(self):
        result = self._transpile("LOWER({fld1})")
        assert result == "LOWER(V(m.MyField))"

    def test_trim(self):
        result = self._transpile("TRIM({fld1})")
        assert result == "TRIM(V(m.MyField))"

    def test_abs(self):
        result = self._transpile("ABS({fld1})")
        assert result == "ABS(V(m.MyField))"

    def test_sqrt(self):
        result = self._transpile("SQRT({fld1})")
        assert result == "SQRT(V(m.MyField))"

    def test_power(self):
        result = self._transpile("POWER({fld1}, 2)")
        assert result == "POWER(V(m.MyField), 2.0)"

    def test_mod(self):
        result = self._transpile("MOD({fld1}, 3)")
        assert result == "MOD(V(m.MyField), 3.0)"

    def test_concatenate(self):
        result = self._transpile('CONCATENATE({fld1}, "-", {fld2})')
        assert result == 'CONCATENATE(V(m.MyField), "-", V(m.OtherField))'

    def test_rept(self):
        result = self._transpile('REPT("ab", 3)')
        assert result == 'REPT("ab", 3.0)'

    def test_encode_url_component(self):
        result = self._transpile("ENCODE_URL_COMPONENT({fld1})")
        assert result == "ENCODE_URL_COMPONENT(V(m.MyField))"

    def test_datetime_parse_single_arg(self):
        result = self._transpile('DATETIME_PARSE("2025-01-15")')
        assert result == 'DATETIME_PARSE("2025-01-15")'

    def test_year_falls_through(self):
        result = self._transpile("YEAR({fld1})")
        assert result == "YEAR(V(m.MyField))"

    def test_datestr_falls_through(self):
        result = self._transpile("DATESTR({fld1})")
        assert result == "DATESTR(V(m.MyField))"

    def test_timestr_falls_through(self):
        result = self._transpile("TIMESTR({fld1})")
        assert result == "TIMESTR(V(m.MyField))"

    def test_regex_match_falls_through(self):
        result = self._transpile('REGEX_MATCH({fld1}, "\\\\d+")')
        assert result is not None
        assert result.startswith("REGEX_MATCH(V(m.MyField), ")

    def test_regex_replace_falls_through(self):
        result = self._transpile('REGEX_REPLACE({fld1}, "a", "b")')
        assert result == 'REGEX_REPLACE(V(m.MyField), "a", "b")'

    def test_countall(self):
        result = self._transpile("COUNTALL({fld1})")
        assert result == "V(float64(len(A(V(m.MyField)))))"

    def test_log10_maps_to_log(self):
        result = self._transpile("LOG10({fld1})")
        assert result == "LOG(V(m.MyField))"

    def test_now_falls_through(self):
        assert self._transpile("NOW()") == "NOW()"

    def test_today_falls_through(self):
        assert self._transpile("TODAY()") == "TODAY()"

    # --- Untranspilable ---

    def test_created_time_untranspilable(self):
        assert self._transpile("CREATED_TIME()") is None

"""Tests for Swift code emission in the formula transpiler (F8.11).

Parity with the TypeScript/JavaScript/Python emitter tests in
test_formula_transpiler.py. Swift's emission style mirrors Rust (typed,
routes through AirtableRuntime) but produces `AirtableJSONValue` values
and Swift syntax.
"""

from src.formulas.formula_transpiler import transpile_formula


class TestSwiftEmitter:
    """Swift code emission via the transpiler."""

    def _transpile(
        self,
        formula: str,
        field_map: dict | None = None,
        formula_ids: set | None = None,
    ) -> str | None:
        field_map = field_map or {"fld1": "myField", "fld2": "otherField"}
        formula_ids = formula_ids or set()
        return transpile_formula(formula, "swift", field_map, formula_ids)

    # --- Literals ---

    def test_int_literal(self):
        assert self._transpile("42") == ".int(42)"

    def test_negative_int(self):
        assert self._transpile("-5") == ".int(-5)"

    def test_decimal_literal(self):
        assert self._transpile("3.14") == ".double(3.14)"

    def test_leading_dot_normalized(self):
        # ".5" becomes "0.5" (so it still parses as a double).
        assert self._transpile(".5") == ".double(0.5)"

    def test_string_literal(self):
        assert self._transpile('"hello"') == '.string("hello")'

    # --- Field refs ---

    def test_field_ref_wraps_in_v(self):
        # Raw fields are typed (String?, Int?, etc.) and must be converted
        # to AirtableJSONValue via the V<T: Encodable>() helper.
        assert self._transpile("{fld1}") == "AirtableRuntime.V(self.myField)"

    def test_formula_field_ref_wraps_in_v(self):
        # Formula fields are typed (String?/Double?/etc.), so they also need
        # V() to convert to AirtableJSONValue for runtime composition.
        result = self._transpile("{fld1}", formula_ids={"fld1"})
        assert result == "AirtableRuntime.V(self.myField)"

    # --- Arithmetic ---

    def test_addition_wraps_in_double(self):
        # Numeric ops produce Double; wrap back into AirtableJSONValue.
        result = self._transpile("{fld1} + 5")
        assert result == ".double((AirtableRuntime.N(AirtableRuntime.V(self.myField)) + Double(5)))"

    def test_subtraction(self):
        result = self._transpile("10 - 3")
        assert result == ".double((Double(10) - Double(3)))"

    def test_unary_negation(self):
        # Binary op '-' with negation in parse tree.
        result = self._transpile("-{fld1}")
        assert result == ".double((-AirtableRuntime.N(AirtableRuntime.V(self.myField))))"

    # --- Comparisons ---

    def test_numeric_equality(self):
        # Both sides wrapped as AirtableJSONValue so the == compares enums.
        result = self._transpile("{fld1} = 5")
        assert result == (".bool(.double(AirtableRuntime.N(AirtableRuntime.V(self.myField))) == .int(5))")

    def test_string_equality(self):
        result = self._transpile('{fld1} = "hi"')
        assert result == ('.bool(.string(AirtableRuntime.S(AirtableRuntime.V(self.myField))) == .string("hi"))')

    def test_greater_than(self):
        # Numeric comparisons unwrap both sides to Double.
        result = self._transpile("{fld1} > 10")
        assert result == ".bool(AirtableRuntime.N(AirtableRuntime.V(self.myField)) > Double(10))"

    # --- Concatenation ---

    def test_concat(self):
        result = self._transpile('{fld1} & " items"')
        assert result == '.string(AirtableRuntime.S(AirtableRuntime.V(self.myField)) + " items")'

    # --- Boolean literals & combinators ---

    def test_true(self):
        assert self._transpile("TRUE()") == ".bool(true)"

    def test_false(self):
        assert self._transpile("FALSE()") == ".bool(false)"

    def test_blank(self):
        assert self._transpile("BLANK()") == ".null"

    def test_not(self):
        result = self._transpile("NOT(TRUE())")
        assert result == ".bool(!AirtableRuntime.isTruthy(.bool(true)))"

    def test_and_two_args(self):
        result = self._transpile("AND(TRUE(), FALSE())")
        assert result == (".bool(AirtableRuntime.isTruthy(.bool(true)) && AirtableRuntime.isTruthy(.bool(false)))")

    def test_or_two_args(self):
        result = self._transpile("OR(TRUE(), FALSE())")
        assert result == (".bool(AirtableRuntime.isTruthy(.bool(true)) || AirtableRuntime.isTruthy(.bool(false)))")

    def test_xor(self):
        result = self._transpile("XOR(TRUE(), FALSE())")
        assert "isTruthy" in result
        assert " != " in result

    # --- Conditionals ---

    def test_if_basic(self):
        result = self._transpile("IF({fld1}, 1, 0)")
        assert result == ("(AirtableRuntime.isTruthy(AirtableRuntime.V(self.myField)) ? .int(1) : .int(0))")

    def test_if_without_else(self):
        # Missing else branch defaults to .null.
        result = self._transpile("IF({fld1}, 1)")
        assert result.endswith(": .null)")

    def test_ifs(self):
        result = self._transpile("IFS({fld1}, 1, {fld2}, 2)")
        assert "AirtableRuntime.isTruthy" in result
        assert ".int(1)" in result
        assert ".int(2)" in result
        assert ".null" in result  # fallback

    def test_switch(self):
        result = self._transpile('SWITCH({fld1}, "a", 1, "b", 2, 99)')
        assert "AirtableRuntime.SWITCH" in result
        assert "cases:" in result
        assert "default:" in result

    # --- Record ID ---

    def test_record_id(self):
        assert self._transpile("RECORD_ID()") == '.string(self.id ?? "")'

    # --- Function fall-through (should hit default runtime path) ---

    def test_sum(self):
        result = self._transpile("SUM({fld1}, {fld2})")
        assert result == ("AirtableRuntime.SUM(AirtableRuntime.V(self.myField), AirtableRuntime.V(self.otherField))")

    def test_min(self):
        result = self._transpile("MIN({fld1}, 5)")
        assert result.startswith("AirtableRuntime.MIN(")

    def test_average(self):
        result = self._transpile("AVERAGE({fld1}, {fld2})")
        assert result.startswith("AirtableRuntime.AVERAGE(")

    def test_round_with_precision(self):
        result = self._transpile("ROUND({fld1}, 2)")
        assert result == "AirtableRuntime.ROUND(AirtableRuntime.V(self.myField), .int(2))"

    def test_round_default_precision(self):
        # ROUND with only one arg → Swift default handles the missing precision.
        result = self._transpile("ROUND({fld1})")
        assert result == "AirtableRuntime.ROUND(AirtableRuntime.V(self.myField))"

    def test_len(self):
        result = self._transpile("LEN({fld1})")
        assert result == "AirtableRuntime.LEN(AirtableRuntime.V(self.myField))"

    def test_upper(self):
        result = self._transpile("UPPER({fld1})")
        assert result == "AirtableRuntime.UPPER(AirtableRuntime.V(self.myField))"

    def test_concatenate(self):
        result = self._transpile('CONCATENATE({fld1}, "-", {fld2})')
        assert result.startswith("AirtableRuntime.CONCATENATE(")

    def test_datetime_parse_single_arg(self):
        result = self._transpile('DATETIME_PARSE("2025-01-15")')
        # Swift DATETIME_PARSE takes 1 arg; format string (2nd) is ignored.
        assert result == 'AirtableRuntime.DATETIME_PARSE(.string("2025-01-15"))'

    def test_year_falls_through(self):
        result = self._transpile("YEAR({fld1})")
        assert result == "AirtableRuntime.YEAR(AirtableRuntime.V(self.myField))"

    def test_regex_match_falls_through(self):
        result = self._transpile('REGEX_MATCH({fld1}, "\\\\d+")')
        assert result.startswith("AirtableRuntime.REGEX_MATCH(")

"""Tests for C++ code emission in the formula transpiler (CPP F1.12, completed in F8.6).

Parity with test_formula_transpiler_csharp.py. C++'s emission mirrors C# (typed,
routes through qualified runtime coercions) but: the runtime is a NAMESPACE, so
the qualifier separator is `::` not `.` (the `_emit_num`/`_emit_str` tails are
the load-bearing sites — plan CRIT-1); snake_case field refs via `this->`;
lowercase coercions (v/n/s/is_equal); string literals wrapped in std::string()
so `+` concatenation never decays to pointer arithmetic.

F1.12 lands the emitter core + these pin tests; the function-call arms (F8.6)
extend this file to the full ~44-case suite.
"""

from myairtable.formulas.formula_transpiler import transpile_formula


class TestCppEmitter:
    """C++ code emission via the transpiler."""

    def _transpile(
        self,
        formula: str,
        field_map: dict | None = None,
        formula_ids: set | None = None,
    ) -> str:
        field_map = field_map or {"fld1": "my_field", "fld2": "other_field"}
        formula_ids = formula_ids or set()
        result = transpile_formula(formula, "cpp", field_map, formula_ids)
        assert result is not None
        return result

    # --- Literals ---

    def test_int_literal(self):
        assert self._transpile("42") == "runtime::v(42)"

    def test_negative_int(self):
        assert self._transpile("-5") == "runtime::v(-5)"

    def test_decimal_literal(self):
        assert self._transpile("3.14") == "runtime::v(3.14)"

    def test_leading_dot_normalized(self):
        assert self._transpile(".5") == "runtime::v(0.5)"

    def test_string_literal(self):
        assert self._transpile('"hello"') == 'runtime::v("hello")'

    def test_single_quoted_literal_converted(self):
        assert self._transpile("'hi'") == 'runtime::v("hi")'

    # --- Field refs ---

    def test_field_ref_wraps_in_v_with_arrow(self):
        assert self._transpile("{fld1}") == "runtime::v(this->my_field)"

    def test_formula_field_ref_also_wraps(self):
        assert self._transpile("{fld1}", formula_ids={"fld1"}) == "runtime::v(this->my_field)"

    # --- CRIT-1 pins: the _emit_num/_emit_str qualified-default tails ---
    # These MUST emit `runtime::n(...)` / `runtime::s(...)` — the shared tails
    # hand-build "{runtime}.N(...)" with a literal dot, which is invalid member
    # access on a C++ namespace and would break EVERY arithmetic/comparison
    # operand and every non-literal concat operand.

    def test_field_plus_literal_routes_n_through_namespace(self):
        assert self._transpile("{fld1} + 1") == "runtime::v((runtime::n(runtime::v(this->my_field)) + 1.0))"

    def test_field_comparison_routes_n_through_namespace(self):
        assert self._transpile("{fld1} > 10") == "runtime::v(runtime::n(runtime::v(this->my_field)) > 10.0)"

    def test_field_concat_routes_s_through_namespace(self):
        result = self._transpile('{fld1} & "x"')
        assert result == 'runtime::v(runtime::s(runtime::v(this->my_field)) + std::string("x"))'

    def test_no_dot_qualified_runtime_ever_emitted(self):
        """Belt-and-braces: `runtime.` (dot) must never appear in cpp output."""
        for formula in ("{fld1} + 1", "{fld1} - 2 * 3", '{fld1} & "x" & {fld2}', "-{fld1}", "{fld1} <= {fld2}"):
            assert "runtime." not in self._transpile(formula)

    # --- Arithmetic / unary ---

    def test_addition_of_literals(self):
        assert self._transpile("1 + 2") == "runtime::v((1.0 + 2.0))"

    def test_unary_negation_of_field(self):
        assert self._transpile("-{fld1}") == "runtime::v((-runtime::n(runtime::v(this->my_field))))"

    # --- Equality (own C++ block: value ==, is_equal fallback) ---

    def test_numeric_equality_coerces_n(self):
        assert self._transpile("{fld1} = 5") == "runtime::v(runtime::n(runtime::v(this->my_field)) == runtime::n(runtime::v(5)))"

    def test_string_equality_coerces_s(self):
        assert self._transpile('{fld1} = "a"') == 'runtime::v(runtime::s(runtime::v(this->my_field)) == runtime::s(runtime::v("a")))'

    def test_field_vs_field_equality_uses_is_equal(self):
        assert self._transpile("{fld1} = {fld2}") == "runtime::v(runtime::is_equal(runtime::v(this->my_field), runtime::v(this->other_field)))"

    def test_field_vs_field_inequality_negates_is_equal(self):
        assert self._transpile("{fld1} != {fld2}") == "runtime::v(!runtime::is_equal(runtime::v(this->my_field), runtime::v(this->other_field)))"

    # --- Concat ---

    def test_concat_two_literals(self):
        assert self._transpile("'a' & 'b'") == 'runtime::v(std::string("a") + std::string("b"))'


class TestCppEmitterFunctions:
    """F8.6 arms: logic, control flow, and runtime function dispatch."""

    def _transpile(self, formula: str, field_map: dict | None = None, formula_ids: set | None = None) -> str:
        field_map = field_map or {"fld1": "my_field", "fld2": "other_field"}
        result = transpile_formula(formula, "cpp", field_map, formula_ids or set())
        assert result is not None
        return result

    # --- record id / booleans / logic ---

    def test_record_id(self):
        assert self._transpile("RECORD_ID()") == 'runtime::v(this->id.value_or(""))'

    def test_true_false(self):
        assert self._transpile("TRUE()") == "runtime::v(true)"
        assert self._transpile("FALSE()") == "runtime::v(false)"

    def test_blank_bare_emits_null_sentinel(self):
        assert self._transpile("BLANK()") == "runtime::v(nullptr)"

    def test_blank_with_arg_uses_is_blank(self):
        assert self._transpile("BLANK({fld1})") == "runtime::v(runtime::is_blank(runtime::v(this->my_field)))"

    def test_not(self):
        assert self._transpile("NOT({fld1})") == "runtime::v(!runtime::is_truthy(runtime::v(this->my_field)))"

    def test_and_joins_is_truthy(self):
        assert (
            self._transpile("AND({fld1}, {fld2})")
            == "runtime::v(runtime::is_truthy(runtime::v(this->my_field)) && runtime::is_truthy(runtime::v(this->other_field)))"
        )

    def test_or_joins_is_truthy(self):
        assert (
            self._transpile("OR({fld1}, {fld2})")
            == "runtime::v(runtime::is_truthy(runtime::v(this->my_field)) || runtime::is_truthy(runtime::v(this->other_field)))"
        )

    def test_xor(self):
        assert (
            self._transpile("XOR({fld1}, {fld2})")
            == "runtime::v(runtime::is_truthy(runtime::v(this->my_field)) != runtime::is_truthy(runtime::v(this->other_field)))"
        )

    # --- control flow ---

    def test_if_ternary(self):
        assert self._transpile('IF({fld1}, "yes", "no")') == '(runtime::is_truthy(runtime::v(this->my_field)) ? runtime::v("yes") : runtime::v("no"))'

    def test_if_without_else_falls_back_to_null(self):
        assert self._transpile('IF({fld1}, "yes")') == '(runtime::is_truthy(runtime::v(this->my_field)) ? runtime::v("yes") : runtime::v(nullptr))'

    def test_ifs_chains_ternaries(self):
        assert (
            self._transpile('IFS({fld1}, "a", {fld2}, "b")') == '(runtime::is_truthy(runtime::v(this->my_field)) ? runtime::v("a") : '
            '(runtime::is_truthy(runtime::v(this->other_field)) ? runtime::v("b") : runtime::v(nullptr)))'
        )

    def test_switch_braced_flat_pairs(self):
        # String patterns coerce the expr through s() (cross-shape match parity).
        assert (
            self._transpile('SWITCH({fld1}, "a", 1, "b", 2)')
            == "runtime::SWITCH(runtime::v(runtime::s(runtime::v(this->my_field))), runtime::v(nullptr), "
            '{runtime::v("a"), runtime::v(1), runtime::v("b"), runtime::v(2)})'
        )

    def test_switch_with_default(self):
        assert (
            self._transpile('SWITCH({fld1}, "a", 1, 99)') == "runtime::SWITCH(runtime::v(runtime::s(runtime::v(this->my_field))), runtime::v(99), "
            '{runtime::v("a"), runtime::v(1)})'
        )

    # --- runtime function dispatch ---

    def test_variadic_functions_brace_their_args(self):
        assert self._transpile("SUM({fld1}, {fld2})") == "runtime::SUM({runtime::v(this->my_field), runtime::v(this->other_field)})"
        assert self._transpile('CONCATENATE({fld1}, "x")') == 'runtime::CONCATENATE({runtime::v(this->my_field), runtime::v("x")})'
        assert self._transpile("MIN(1, 2)") == "runtime::MIN({runtime::v(1), runtime::v(2)})"
        assert self._transpile("MAX(1, 2)") == "runtime::MAX({runtime::v(1), runtime::v(2)})"

    def test_fixed_arity_functions_pass_args_directly(self):
        assert self._transpile("LEN({fld1})") == "runtime::LEN(runtime::v(this->my_field))"
        assert self._transpile("UPPER({fld1})") == "runtime::UPPER(runtime::v(this->my_field))"
        assert self._transpile("ROUND({fld1}, 2)") == "runtime::ROUND(runtime::v(this->my_field), runtime::v(2))"
        assert self._transpile("ROUND({fld1})") == "runtime::ROUND(runtime::v(this->my_field))"

    def test_countall_counts_flattened_args(self):
        assert self._transpile("COUNTALL({fld1})") == "runtime::v(static_cast<int64_t>(runtime::a({runtime::v(this->my_field)}).size()))"

    def test_log10_maps_to_single_arg_log(self):
        assert self._transpile("LOG10({fld1})") == "runtime::LOG(runtime::v(this->my_field))"

    def test_datetime_parse_single_arg(self):
        assert self._transpile('DATETIME_PARSE("2024-01-15")') == 'runtime::DATETIME_PARSE(runtime::v("2024-01-15"))'

    def test_date_part_functions_fall_through(self):
        assert self._transpile("YEAR({fld1})") == "runtime::YEAR(runtime::v(this->my_field))"
        assert self._transpile("WEEKDAY({fld1})") == "runtime::WEEKDAY(runtime::v(this->my_field))"

    def test_regex_functions_fall_through(self):
        assert self._transpile('REGEX_MATCH({fld1}, "a+")') == 'runtime::REGEX_MATCH(runtime::v(this->my_field), runtime::v("a+"))'

    def test_rept_falls_through(self):
        assert self._transpile('REPT("ab", 3)') == 'runtime::REPT(runtime::v("ab"), runtime::v(3))'

    def test_never_emits_dot_qualified_runtime(self):
        for formula in (
            "SUM({fld1}, 1)",
            'IF({fld1}, SUM(1, 2), CONCATENATE("a", {fld2}))',
            'SWITCH({fld1}, "a", LEN({fld2}))',
            "NOT(AND({fld1}, {fld2}))",
        ):
            assert "runtime." not in self._transpile(formula)

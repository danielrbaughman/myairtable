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

from src.formulas.formula_transpiler import transpile_formula


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

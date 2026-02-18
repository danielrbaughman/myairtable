"""Tests for the formula transpiler - parsing and code emission."""

from src.formulas.formula_tokenizer import tokenize_formula
from src.formulas.formula_transpiler import (
    ASTNode,
    BinaryOp,
    FieldRef,
    FormulaParser,
    FunctionCall,
    NumberLiteral,
    StringLiteral,
    transpile_formula,
)


# region Parser Tests
class TestParserBasics:
    """Test basic parsing of different token types."""

    def _parse(self, formula: str) -> ASTNode:
        tokens = tokenize_formula(formula)
        return FormulaParser(tokens).parse()

    def test_number_literal(self):
        ast = self._parse("42")
        assert isinstance(ast, NumberLiteral)
        assert ast.value == "42"

    def test_decimal_literal(self):
        ast = self._parse("3.14")
        assert isinstance(ast, NumberLiteral)
        assert ast.value == "3.14"

    def test_string_literal(self):
        ast = self._parse('"hello"')
        assert isinstance(ast, StringLiteral)
        assert ast.value == '"hello"'

    def test_field_ref(self):
        ast = self._parse("{fld123}")
        assert isinstance(ast, FieldRef)
        assert ast.field_id == "fld123"

    def test_function_no_args(self):
        ast = self._parse("BLANK()")
        assert isinstance(ast, FunctionCall)
        assert ast.name == "BLANK"
        assert len(ast.args) == 0

    def test_function_one_arg(self):
        ast = self._parse("ABS(5)")
        assert isinstance(ast, FunctionCall)
        assert ast.name == "ABS"
        assert len(ast.args) == 1
        assert isinstance(ast.args[0], NumberLiteral)

    def test_function_multiple_args(self):
        ast = self._parse("IF(1, 2, 3)")
        assert isinstance(ast, FunctionCall)
        assert ast.name == "IF"
        assert len(ast.args) == 3

    def test_binary_op(self):
        ast = self._parse("1 + 2")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "+"
        assert isinstance(ast.left, NumberLiteral)
        assert isinstance(ast.right, NumberLiteral)

    def test_comparison_op(self):
        ast = self._parse("{fld1} = 5")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "="

    def test_concat_op(self):
        ast = self._parse('"a" & "b"')
        assert isinstance(ast, BinaryOp)
        assert ast.op == "&"


class TestOperatorPrecedence:
    """Test operator precedence is correctly handled."""

    def _parse(self, formula: str) -> ASTNode:
        tokens = tokenize_formula(formula)
        return FormulaParser(tokens).parse()

    def test_multiplication_before_addition(self):
        """1 + 2 * 3 should parse as 1 + (2 * 3)"""
        ast = self._parse("1 + 2 * 3")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "+"
        assert isinstance(ast.left, NumberLiteral)
        assert isinstance(ast.right, BinaryOp)
        assert ast.right.op == "*"

    def test_parentheses_override_precedence(self):
        """(1 + 2) * 3 should parse as (1 + 2) * 3"""
        ast = self._parse("(1 + 2) * 3")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "*"
        assert isinstance(ast.left, BinaryOp)
        assert ast.left.op == "+"

    def test_comparison_lowest_precedence(self):
        """1 + 2 = 3 should parse as (1 + 2) = 3"""
        ast = self._parse("1 + 2 = 3")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "="
        assert isinstance(ast.left, BinaryOp)
        assert ast.left.op == "+"

    def test_concat_between_comparison_and_additive(self):
        """1 + 2 & 3 should parse as (1 + 2) & 3"""
        ast = self._parse("1 + 2 & 3")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "&"
        assert isinstance(ast.left, BinaryOp)
        assert ast.left.op == "+"


# endregion


# region Emitter Tests
class TestTypeScriptEmitter:
    """Test TypeScript code emission."""

    def _transpile(self, formula: str, field_map: dict | None = None, formula_ids: set | None = None) -> str | None:
        field_map = field_map or {"fld1": "myField", "fld2": "otherField"}
        formula_ids = formula_ids or set()
        return transpile_formula(formula, "typescript", field_map, formula_ids)

    def test_number(self):
        assert self._transpile("42") == "42"

    def test_string(self):
        assert self._transpile('"hello"') == '"hello"'

    def test_field_ref(self):
        assert self._transpile("{fld1}") == "this.myField"

    def test_formula_field_ref(self):
        """Formula field refs should be accessed as properties."""
        result = self._transpile("{fld1}", formula_ids={"fld1"})
        assert result == "this.myField"

    def test_linked_record_field_ref(self):
        """Plural linked record field refs should use .ids for the raw array."""
        result = transpile_formula("{fld1}", "typescript", {"fld1": "myField"}, set(), linked_record_field_ids={"fld1"})
        assert result == "this.myField.ids"

    def test_single_linked_record_field_ref(self):
        """Single linked record field refs should use .id."""
        result = transpile_formula("{fld1}", "typescript", {"fld1": "myField"}, set(), single_linked_record_field_ids={"fld1"})
        assert result == "this.myField.id"

    def test_addition(self):
        result = self._transpile("{fld1} + 5")
        assert result == "(F.N(this.myField) + 5)"

    def test_concat(self):
        result = self._transpile('{fld1} & " items"')
        assert result == '(F.S(this.myField) + " items")'

    def test_equality(self):
        result = self._transpile("{fld1} = 5")
        assert result == "(F.N(this.myField) == 5)"

    def test_function_call(self):
        result = self._transpile("COUNTA({fld1})")
        assert result == "F.COUNTA(this.myField)"

    def test_nested_function(self):
        result = self._transpile("IF({fld1} > 0, {fld1}, 0)")
        assert result == "((F.N(this.myField) > 0) ? this.myField : 0)"

    def test_record_id(self):
        result = self._transpile("RECORD_ID()")
        assert result == "this.id"

    def test_true(self):
        assert self._transpile("TRUE()") == "true"

    def test_false(self):
        assert self._transpile("FALSE()") == "false"

    def test_if_with_true(self):
        result = self._transpile("IF(TRUE(), 1, 2)")
        assert result == "(true ? 1 : 2)"

    def test_not_field(self):
        assert self._transpile("NOT({fld1})") == "!this.myField"

    def test_not_true(self):
        assert self._transpile("NOT(TRUE())") == "!true"

    def test_blank(self):
        result = self._transpile("BLANK()")
        assert result == "null"

    def test_blank_with_arg(self):
        result = self._transpile("BLANK({fld1})")
        assert result == "(this.myField == null)"

    def test_and(self):
        assert self._transpile("AND({fld1}, {fld2})") == "(this.myField && this.otherField)"

    def test_or(self):
        assert self._transpile("OR({fld1}, {fld2})") == "(this.myField || this.otherField)"

    def test_not_and(self):
        assert self._transpile("NOT(AND({fld1}, {fld2}))") == "!(this.myField && this.otherField)"

    def test_xor(self):
        assert self._transpile("XOR({fld1}, {fld2})") == "(!this.myField !== !this.otherField)"

    def test_complex_formula(self):
        """IF(COUNTA({fld1}) > 0, {fld1} + {fld2}, BLANK())"""
        result = self._transpile("IF(COUNTA({fld1}) > 0, {fld1} + {fld2}, BLANK())")
        assert result == "((F.N(F.COUNTA(this.myField)) > 0) ? (F.N(this.myField) + F.N(this.otherField)) : null)"

    def test_ifs_single_pair(self):
        result = self._transpile("IFS({fld1}, 1)")
        assert result == "(this.myField ? 1 : null)"

    def test_ifs_multiple_pairs(self):
        result = self._transpile('IFS({fld1} > 10, "high", {fld1} > 5, "med", TRUE(), "low")')
        assert result == '((F.N(this.myField) > 10) ? "high" : (F.N(this.myField) > 5) ? "med" : true ? "low" : null)'

    def test_switch_no_default(self):
        result = self._transpile('SWITCH({fld1}, "a", 1, "b", 2)')
        assert result == '((F.S(this.myField) == "a") ? 1 : (F.S(this.myField) == "b") ? 2 : null)'

    def test_switch_with_default(self):
        result = self._transpile('SWITCH({fld1}, "a", 1, "b", 2, 99)')
        assert result == '((F.S(this.myField) == "a") ? 1 : (F.S(this.myField) == "b") ? 2 : 99)'


class TestJavaScriptEmitter:
    """Test JavaScript code emission (same as TS but uses 'this')."""

    def _transpile(self, formula: str, field_map: dict | None = None, formula_ids: set | None = None) -> str | None:
        field_map = field_map or {"fld1": "myField"}
        formula_ids = formula_ids or set()
        return transpile_formula(formula, "javascript", field_map, formula_ids)

    def test_field_ref(self):
        assert self._transpile("{fld1}") == "this.myField"

    def test_function_call(self):
        assert self._transpile("ABS({fld1})") == "Math.abs(F.N(this.myField))"


class TestPythonEmitter:
    """Test Python code emission."""

    def _transpile(self, formula: str, field_map: dict | None = None, formula_ids: set | None = None) -> str | None:
        field_map = field_map or {"fld1": "my_field", "fld2": "other_field"}
        formula_ids = formula_ids or set()
        return transpile_formula(formula, "python", field_map, formula_ids)

    def test_field_ref(self):
        assert self._transpile("{fld1}") == "self.my_field"

    def test_formula_field_ref(self):
        result = self._transpile("{fld1}", formula_ids={"fld1"})
        assert result == "self.my_field"

    def test_linked_record_field_ref_python(self):
        """Python linked record fields are plain lists, no .ids needed."""
        result = transpile_formula("{fld1}", "python", {"fld1": "my_field"}, set(), linked_record_field_ids={"fld1"})
        assert result == "self.my_field"

    def test_function_call(self):
        assert self._transpile("LEN({fld1})") == "len(F.S(self.my_field))"

    def test_sum(self):
        assert self._transpile("SUM({fld1}, {fld2})") == "sum(F.AN((self.my_field, self.other_field,)))"

    def test_sum_single_arg(self):
        assert self._transpile("SUM({fld1})") == "sum(F.AN((self.my_field,)))"

    def test_addition(self):
        assert self._transpile("{fld1} + 5") == "(F.N(self.my_field) + 5)"

    def test_record_id(self):
        assert self._transpile("RECORD_ID()") == "self.id"

    def test_true(self):
        assert self._transpile("TRUE()") == "True"

    def test_false(self):
        assert self._transpile("FALSE()") == "False"

    def test_not_field(self):
        assert self._transpile("NOT({fld1})") == "not self.my_field"

    def test_not_true(self):
        assert self._transpile("NOT(TRUE())") == "not True"

    def test_and(self):
        assert self._transpile("AND({fld1}, {fld2})") == "(self.my_field and self.other_field)"

    def test_or(self):
        assert self._transpile("OR({fld1}, {fld2})") == "(self.my_field or self.other_field)"

    def test_not_and(self):
        assert self._transpile("NOT(AND({fld1}, {fld2}))") == "not (self.my_field and self.other_field)"

    def test_xor(self):
        assert self._transpile("XOR({fld1}, {fld2})") == "((not self.my_field) != (not self.other_field))"

    def test_blank(self):
        assert self._transpile("BLANK()") == "None"

    def test_blank_with_arg(self):
        result = self._transpile("BLANK({fld1})")
        assert result == "(self.my_field is None)"

    def test_if_with_false(self):
        result = self._transpile("IF(FALSE(), 1, 2)")
        assert result == "(1 if False else 2)"

    def test_ifs_single_pair(self):
        result = self._transpile("IFS({fld1}, 1)")
        assert result == "(1 if self.my_field else None)"

    def test_ifs_multiple_pairs(self):
        result = self._transpile('IFS({fld1} > 10, "high", {fld1} > 5, "med", TRUE(), "low")')
        assert result == '("high" if (F.N(self.my_field) > 10) else "med" if (F.N(self.my_field) > 5) else "low" if True else None)'

    def test_switch_no_default(self):
        result = self._transpile('SWITCH({fld1}, "a", 1, "b", 2)')
        assert result == '(1 if (F.S(self.my_field) == "a") else 2 if (F.S(self.my_field) == "b") else None)'

    def test_switch_with_default(self):
        result = self._transpile('SWITCH({fld1}, "a", 1, "b", 2, 99)')
        assert result == '(1 if (F.S(self.my_field) == "a") else 2 if (F.S(self.my_field) == "b") else 99)'


# endregion


# region Edge Cases
class TestEdgeCases:
    """Test error handling and edge cases."""

    def test_empty_formula(self):
        assert transpile_formula("", "typescript", {}, set()) is None

    def test_whitespace_only(self):
        assert transpile_formula("   ", "typescript", {}, set()) is None

    def test_unknown_field(self):
        """Unknown field reference should return None (fallback to getter)."""
        result = transpile_formula("{fldUnknown}", "typescript", {"fld1": "field"}, set())
        assert result is None

    def test_unbalanced_parens(self):
        """Unbalanced parentheses should return None."""
        result = transpile_formula("IF(1, 2", "typescript", {}, set())
        assert result is None

    def test_negative_number(self):
        result = transpile_formula("-5", "typescript", {}, set())
        assert result is not None
        # Could be parsed as UnaryOp("-", 5) -> (-5) or as NumberLiteral("-5") -> "-5"
        assert result in ["-5", "(-5)"]

    def test_nested_parens(self):
        result = transpile_formula("((1 + 2))", "typescript", {}, set())
        assert result == "(1 + 2)"

    def test_multiple_comparisons(self):
        """Chained comparisons should work."""
        result = transpile_formula("1 = 1", "typescript", {}, set())
        assert result == "(1 == 1)"

    def test_created_time_returns_none(self):
        """CREATED_TIME() cannot be evaluated at runtime, should return None."""
        result = transpile_formula("CREATED_TIME()", "typescript", {}, set())
        assert result is None

    def test_last_modified_time_returns_none(self):
        """LAST_MODIFIED_TIME() cannot be evaluated at runtime, should return None."""
        result = transpile_formula("LAST_MODIFIED_TIME()", "typescript", {}, set())
        assert result is None

    def test_formula_containing_created_time_returns_none(self):
        """A formula that uses CREATED_TIME() anywhere should return None."""
        field_map = {"fld1": "myField"}
        result = transpile_formula('DATETIME_DIFF(NOW(), CREATED_TIME(), "days")', "typescript", field_map, set())
        assert result is None

    def test_formula_containing_last_modified_time_returns_none(self):
        """A formula that uses LAST_MODIFIED_TIME() anywhere should return None."""
        field_map = {"fld1": "myField"}
        result = transpile_formula('IF(LAST_MODIFIED_TIME() = BLANK(), "never", "modified")', "typescript", field_map, set())
        assert result is None


class TestRealWorldFormulas:
    """Test against patterns commonly found in real Airtable bases."""

    def _transpile(self, formula: str) -> str | None:
        field_map = {
            "fldName": "name",
            "fldAmount": "amount",
            "fldDate": "date",
            "fldStatus": "status",
            "fldJobs": "jobsLink",
        }
        formula_ids: set[str] = set()
        return transpile_formula(formula, "typescript", field_map, formula_ids)

    def test_counta_link(self):
        result = self._transpile("COUNTA({fldJobs})")
        assert result == "F.COUNTA(this.jobsLink)"

    def test_if_blank(self):
        """Field = BLANK() — no coercion since BLANK() is not a literal."""
        result = self._transpile('IF({fldName} = BLANK(), "N/A", {fldName})')
        assert result == '((this.name == null) ? "N/A" : this.name)'

    def test_concatenation(self):
        result = self._transpile('{fldName} & " - " & {fldStatus}')
        assert result == '((F.S(this.name) + " - ") + F.S(this.status))'

    def test_math(self):
        result = self._transpile("{fldAmount} * 1.1")
        assert result == "(F.N(this.amount) * 1.1)"

    def test_datetime_diff(self):
        result = self._transpile('DATETIME_DIFF(NOW(), {fldDate}, "days")')
        assert result == 'F.DATETIME_DIFF(F.NOW(), this.date, "days")'


# endregion

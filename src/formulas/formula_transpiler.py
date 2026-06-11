"""
Formula Translator: Converts tokenized Airtable formulas into native code strings.

Recursive descent parser that builds an AST from Airtable formula tokens,
then emits language-specific code (TypeScript, JavaScript, Python).

All operators and functions route through AirtableRuntime for correct
Airtable semantics (BLANK handling, type coercion).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Literal

from .formula_tokenizer import Token, TokenType, tokenize_formula

logger = logging.getLogger(__name__)

Language = Literal["typescript", "javascript", "python", "rust", "swift"]


# region AST Nodes
@dataclass
class NumberLiteral:
    value: str


@dataclass
class StringLiteral:
    value: str  # includes quotes


@dataclass
class FieldRef:
    field_id: str  # the raw content between { }


@dataclass
class FunctionCall:
    name: str  # uppercase function name
    args: list[ASTNode]


@dataclass
class BinaryOp:
    op: str
    left: ASTNode
    right: ASTNode


@dataclass
class UnaryOp:
    op: str
    operand: ASTNode


ASTNode = NumberLiteral | StringLiteral | FieldRef | FunctionCall | BinaryOp | UnaryOp


# endregion


# region Parser
class ParseError(Exception):
    pass


class FormulaParser:
    """Recursive descent parser with operator precedence.

    Precedence (low to high):
      comparison (=, !=, <, >, <=, >=)
      concat (&)
      additive (+, -)
      multiplicative (*, /)
      unary (-)
      atoms (literals, field refs, function calls, parens)
    """

    def __init__(self, tokens: tuple[Token, ...]):
        # Filter out whitespace tokens
        self.tokens = [t for t in tokens if t.type != TokenType.WHITESPACE]
        self.pos = 0

    def peek(self) -> Token | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, token_type: TokenType, value: str | None = None) -> Token:
        tok = self.peek()
        if tok is None:
            raise ParseError(f"Unexpected end of input, expected {token_type}")
        if tok.type != token_type:
            raise ParseError(f"Expected {token_type}, got {tok.type} ({tok.value!r})")
        if value is not None and tok.value != value:
            raise ParseError(f"Expected {value!r}, got {tok.value!r}")
        return self.advance()

    def parse(self) -> ASTNode:
        node = self.parse_comparison()
        if self.pos < len(self.tokens):
            raise ParseError(f"Unexpected token after expression: {self.tokens[self.pos]}")
        return node

    def parse_comparison(self) -> ASTNode:
        left = self.parse_concat()
        while (tok := self.peek()) and tok.type == TokenType.OPERATOR and tok.value in ("=", "!=", "<", ">", "<=", ">="):
            op = self.advance().value
            right = self.parse_concat()
            left = BinaryOp(op, left, right)
        return left

    def parse_concat(self) -> ASTNode:
        left = self.parse_additive()
        while (tok := self.peek()) and tok.type == TokenType.OPERATOR and tok.value == "&":
            self.advance()
            right = self.parse_additive()
            left = BinaryOp("&", left, right)
        return left

    def parse_additive(self) -> ASTNode:
        left = self.parse_multiplicative()
        while (tok := self.peek()) and tok.type == TokenType.OPERATOR and tok.value in ("+", "-"):
            op = self.advance().value
            right = self.parse_multiplicative()
            left = BinaryOp(op, left, right)
        return left

    def parse_multiplicative(self) -> ASTNode:
        left = self.parse_unary()
        while (tok := self.peek()) and tok.type == TokenType.OPERATOR and tok.value in ("*", "/"):
            op = self.advance().value
            right = self.parse_unary()
            left = BinaryOp(op, left, right)
        return left

    def parse_unary(self) -> ASTNode:
        if (tok := self.peek()) and tok.type == TokenType.OPERATOR and tok.value == "-":
            self.advance()
            operand = self.parse_unary()
            return UnaryOp("-", operand)
        return self.parse_atom()

    def parse_atom(self) -> ASTNode:
        tok = self.peek()
        if tok is None:
            raise ParseError("Unexpected end of input")

        # Number literal (may already include negative sign from tokenizer)
        if tok.type == TokenType.NUMBER:
            self.advance()
            return NumberLiteral(tok.value)

        # String literal
        if tok.type == TokenType.STRING:
            self.advance()
            return StringLiteral(tok.value)

        # Field reference
        if tok.type == TokenType.FIELD_REF:
            self.advance()
            # Strip surrounding { }
            field_id = tok.value[1:-1]
            return FieldRef(field_id)

        # Function call
        if tok.type == TokenType.FUNCTION:
            func_name = self.advance().value.upper()
            self.expect(TokenType.PARENTHESIS, "(")
            args: list[ASTNode] = []
            if self.peek() and not (self.peek().type == TokenType.PARENTHESIS and self.peek().value == ")"):
                args.append(self.parse_comparison())
                while self.peek() and self.peek().type == TokenType.COMMA:
                    self.advance()  # skip comma
                    args.append(self.parse_comparison())
            self.expect(TokenType.PARENTHESIS, ")")
            return FunctionCall(func_name, args)

        # Parenthesized expression
        if tok.type == TokenType.PARENTHESIS and tok.value == "(":
            self.advance()
            node = self.parse_comparison()
            self.expect(TokenType.PARENTHESIS, ")")
            return node

        raise ParseError(f"Unexpected token: {tok.type} ({tok.value!r})")


# Type inference for equality coercion — when one side of == / != has a known
# type, we wrap the other side in F.S() or F.N() to flatten potential arrays.
_STRING_RETURNING_FUNCTIONS: set[str] = {
    "LEFT",
    "RIGHT",
    "MID",
    "LOWER",
    "UPPER",
    "TRIM",
    "SUBSTITUTE",
    "REPLACE",
    "CONCATENATE",
    "REPT",
    "T",
    "ENCODE_URL_COMPONENT",
    "REGEX_EXTRACT",
    "REGEX_REPLACE",
    "ARRAYJOIN",
    "DATESTR",
    "TIMESTR",
    "DATETIME_FORMAT",
}

_NUMBER_RETURNING_FUNCTIONS: set[str] = {
    "LEN",
    "FIND",
    "SEARCH",
    "SUM",
    "AVERAGE",
    "MIN",
    "MAX",
    "COUNT",
    "COUNTA",
    "COUNTALL",
    "ROUND",
    "ROUNDUP",
    "ROUNDDOWN",
    "CEILING",
    "FLOOR",
    "INT",
    "ABS",
    "SQRT",
    "POWER",
    "EXP",
    "LOG",
    "LOG10",
    "MOD",
    "EVEN",
    "ODD",
    "VALUE",
    "YEAR",
    "MONTH",
    "DAY",
    "HOUR",
    "MINUTE",
    "SECOND",
    "WEEKDAY",
    "WEEKNUM",
    "DATETIME_DIFF",
    "TONOW",
    "FROMNOW",
    "WORKDAY_DIFF",
    "N",
}

# endregion


# region Code Emitter
class CodeEmitter:
    """Walks AST and emits language-specific code."""

    def __init__(
        self,
        language: Language,
        field_name_map: dict[str, str],
        formula_field_ids: set[str],
        linked_record_field_ids: set[str] | None = None,
        single_linked_record_field_ids: set[str] | None = None,
    ):
        self.language = language
        self.field_name_map = field_name_map  # field_id -> property name (camelCase or snake_case)
        self.formula_field_ids = formula_field_ids  # set of field IDs that are formula fields
        self.linked_record_field_ids = linked_record_field_ids or set()  # set of field IDs that are linked records (plural, .ids)
        self.single_linked_record_field_ids = single_linked_record_field_ids or set()  # single linked records (.id)
        self._self = "self" if language in ("python", "rust", "swift") else "this"
        # Swift uses the full type name (AirtableRuntime) rather than an alias.
        # Keeping the name verbose avoids a file-level typealias in every generated model.
        self._runtime = "AirtableRuntime" if language == "swift" else "F"

    @staticmethod
    def _normalize_number(value: str) -> str:
        """Ensure a numeric string has a leading zero (e.g. '.05' -> '0.05')."""
        v = value.lstrip("-")
        if v.startswith("."):
            return f"-0{v}" if value.startswith("-") else f"0{v}"
        return value

    def emit(self, node: ASTNode) -> str:
        if isinstance(node, NumberLiteral):
            value = self._normalize_number(node.value)
            if self.language == "rust":
                return f"json!({value})"
            if self.language == "swift":
                # AirtableJSONValue.int for whole numbers, .double otherwise.
                return f".double({value})" if "." in value else f".int({value})"
            return value

        if isinstance(node, StringLiteral):
            if self.language == "rust":
                # Ensure double quotes for Rust json!() macro (Airtable uses single quotes)
                val = node.value
                if val.startswith("'") and val.endswith("'"):
                    val = '"' + val[1:-1].replace('"', '\\"') + '"'
                return f"json!({val})"
            if self.language == "swift":
                val = node.value
                if val.startswith("'") and val.endswith("'"):
                    val = '"' + val[1:-1].replace('"', '\\"') + '"'
                return f".string({val})"
            return node.value

        if isinstance(node, FieldRef):
            return self._emit_field_ref(node)

        if isinstance(node, FunctionCall):
            return self._emit_function_call(node)

        if isinstance(node, BinaryOp):
            return self._emit_binary_op(node)

        if isinstance(node, UnaryOp):
            return self._emit_unary_op(node)

        raise ParseError(f"Unknown AST node: {type(node)}")

    def _emit_field_ref(self, node: FieldRef) -> str:
        field_id = node.field_id
        prop_name = self.field_name_map.get(field_id)
        if prop_name is None:
            raise ParseError(f"Unknown field reference: {{{field_id}}}")

        if self.language == "rust":
            return f"serde_json::to_value(&{self._self}.{prop_name}).unwrap_or(Value::Null)"
        if self.language == "swift":
            # All field accesses flow through V() — raw fields are typed
            # (String?, Double?, [RecordId]?, etc.) and formula fields resolve
            # to their result type. V<T: Encodable>() converts any of them to
            # AirtableJSONValue for runtime composition.
            return f"{self._runtime}.V({self._self}.{prop_name})"

        if field_id in self.formula_field_ids:
            # Formula field -> access as property (getter checks evaluate_formulas_at_runtime)
            return f"{self._self}.{prop_name}"
        elif field_id in self.linked_record_field_ids and self.language != "python":
            # Plural linked record field in TS/JS -> access .ids for the raw array
            return f"{self._self}.{prop_name}.ids"
        elif field_id in self.single_linked_record_field_ids and self.language != "python":
            # Single linked record field in TS/JS -> access .id
            return f"{self._self}.{prop_name}.id"
        else:
            # Non-formula field -> access as property
            return f"{self._self}.{prop_name}"

    # Rust runtime functions that take &[Value] (variadic slice)
    _RUST_VARIADIC_FUNCTIONS: set[str] = {
        "SUM",
        "AVERAGE",
        "COUNT",
        "COUNTA",
        "MIN",
        "MAX",
        "CONCATENATE",
    }

    # Rust runtime functions with Option<&Value> as last parameter: name -> which arg index is optional
    _RUST_OPTIONAL_PARAMS: dict[str, int] = {
        "LOG": 1,
        "FIND": 2,
        "SEARCH": 2,
        "SUBSTITUTE": 3,
        "DATETIME_DIFF": 2,
        "DATETIME_FORMAT": 1,
        "WEEKNUM": 1,
        "TONOW": 1,
        "FROMNOW": 1,
        "IS_SAME": 2,
        "IS_BEFORE": 2,
        "IS_AFTER": 2,
        "ARRAYJOIN": 1,
        "ERROR": 0,
    }

    # Rust runtime functions: (required_count, default_trailing_args)
    # When fewer than required_count args are provided, append defaults
    _RUST_DEFAULT_ARGS: dict[str, tuple[int, list[str]]] = {
        "CEILING": (2, ["&json!(0)"]),  # default significance=0 (runtime treats 0 as 1)
        "FLOOR": (2, ["&json!(0)"]),  # default significance=0 (runtime treats 0 as 1)
        "ROUND": (2, ["&json!(0)"]),  # default precision=0
        "ROUNDUP": (2, ["&json!(0)"]),  # default precision=0
        "ROUNDDOWN": (2, ["&json!(0)"]),  # default precision=0
    }

    def _emit_function_call(self, node: FunctionCall) -> str:
        handler = self._FUNCTION_HANDLERS.get(node.name)
        if handler is not None:
            result = handler(self, node)
            if result is not None:
                return result

        if self.language == "rust":
            return self._emit_rust_function_call(node)

        # Swift's runtime functions have native variadic + default-param signatures,
        # so we can just comma-separate the args directly. SWITCH is the exception:
        # it's a custom handler (see _emit_fn_switch) that emits case-tuples for
        # Swift's labeled `cases:` parameter.
        if self.language == "swift":
            args = ", ".join(self.emit(arg) for arg in node.args)
            return f"{self._runtime}.{node.name}({args})"

        # Default: runtime function call
        args = ", ".join(self.emit(arg) for arg in node.args)
        return f"{self._runtime}.{node.name}({args})"

    def _emit_rust_function_call(self, node: FunctionCall) -> str:
        """Emit a Rust runtime function call with proper reference syntax."""
        name = node.name
        rt = self._runtime

        if name in self._RUST_VARIADIC_FUNCTIONS:
            args = ", ".join(self.emit(arg) for arg in node.args)
            return f"{rt}::{name}(&[{args}])"

        opt_idx = self._RUST_OPTIONAL_PARAMS.get(name)
        if opt_idx is not None:
            parts = []
            for i, arg in enumerate(node.args):
                if i < opt_idx:
                    parts.append(f"&{self.emit(arg)}")
                else:
                    parts.append(f"Some(&{self.emit(arg)})")
            # Fill missing optional params with None
            if len(node.args) <= opt_idx:
                while len(parts) < opt_idx:
                    parts.append(f"&{self.emit(node.args[len(parts)])}" if len(parts) < len(node.args) else "/* missing */")
                parts.append("None")
            return f"{rt}::{name}({', '.join(parts)})"

        # Default: all args as &ref, with default args appended if fewer than required
        parts = [f"&{self.emit(arg)}" for arg in node.args]
        if name in self._RUST_DEFAULT_ARGS:
            required, defaults = self._RUST_DEFAULT_ARGS[name]
            while len(parts) < required:
                parts.append(defaults[len(parts) - (required - len(defaults))])
        return f"{rt}::{name}({', '.join(parts)})"

    # region Function Handlers

    def _emit_fn_record_id(self, node: FunctionCall) -> str:
        if self.language == "rust":
            return f'json!({self._self}.get_id().as_deref().unwrap_or(""))'
        if self.language == "swift":
            return f'.string({self._self}.id ?? "")'
        return f"{self._self}.id"

    def _emit_fn_true(self, node: FunctionCall) -> str:
        if self.language == "rust":
            return "json!(true)"
        if self.language == "swift":
            return ".bool(true)"
        return "True" if self.language == "python" else "true"

    def _emit_fn_false(self, node: FunctionCall) -> str:
        if self.language == "rust":
            return "json!(false)"
        if self.language == "swift":
            return ".bool(false)"
        return "False" if self.language == "python" else "false"

    def _emit_fn_blank(self, node: FunctionCall) -> str:
        if not node.args:
            if self.language == "rust":
                return "json!(null)"
            if self.language == "swift":
                return ".null"
            return "None" if self.language == "python" else "null"
        arg = self.emit(node.args[0])
        if self.language == "rust":
            return f"Value::Bool({arg}.is_null())"
        if self.language == "swift":
            # In Swift, BLANK(x) checks whether x is .null or equivalent empty.
            return f".bool({arg} == .null)"
        if self.language == "python":
            return f"({arg} is None)"
        return f"({arg} == null)"

    def _emit_fn_not(self, node: FunctionCall) -> str:
        arg = self.emit(node.args[0])
        if self.language == "rust":
            return f"Value::Bool(!F::is_truthy(&{arg}))"
        if self.language == "swift":
            return f".bool(!{self._runtime}.isTruthy({arg}))"
        return f"not {arg}" if self.language == "python" else f"!{arg}"

    def _emit_fn_and(self, node: FunctionCall) -> str:
        parts = [self.emit(arg) for arg in node.args]
        if len(parts) == 0:
            if self.language == "rust":
                return "json!(true)"
            if self.language == "swift":
                return ".bool(true)"
            return "True" if self.language == "python" else "true"
        if len(parts) == 1:
            return parts[0]
        if self.language == "rust":
            truthy_parts = [f"F::is_truthy(&{p})" for p in parts]
            return f"Value::Bool({' && '.join(truthy_parts)})"
        if self.language == "swift":
            truthy_parts = [f"{self._runtime}.isTruthy({p})" for p in parts]
            return f".bool({' && '.join(truthy_parts)})"
        op = " and " if self.language == "python" else " && "
        return f"({op.join(parts)})"

    def _emit_fn_or(self, node: FunctionCall) -> str:
        parts = [self.emit(arg) for arg in node.args]
        if len(parts) == 0:
            if self.language == "rust":
                return "json!(false)"
            if self.language == "swift":
                return ".bool(false)"
            return "False" if self.language == "python" else "false"
        if len(parts) == 1:
            return parts[0]
        if self.language == "rust":
            truthy_parts = [f"F::is_truthy(&{p})" for p in parts]
            return f"Value::Bool({' || '.join(truthy_parts)})"
        if self.language == "swift":
            truthy_parts = [f"{self._runtime}.isTruthy({p})" for p in parts]
            return f".bool({' || '.join(truthy_parts)})"
        op = " or " if self.language == "python" else " || "
        return f"({op.join(parts)})"

    def _emit_fn_len(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to F::LEN(&arg) / AirtableRuntime.LEN(arg)
        arg = self._emit_str(node.args[0])
        if self.language == "python":
            return f"len({arg})"
        return f"{arg}.length"

    def _emit_fn_str_method(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to LOWER/UPPER/TRIM in the runtime
        arg = self._emit_str(node.args[0])
        if self.language == "python":
            method = {"LOWER": "lower", "UPPER": "upper", "TRIM": "strip"}[node.name]
        else:
            method = {"LOWER": "toLowerCase", "UPPER": "toUpperCase", "TRIM": "trim"}[node.name]
        return f"{arg}.{method}()"

    def _emit_fn_encode_url_component(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to ENCODE_URL_COMPONENT in the runtime
        arg = self._emit_str(node.args[0])
        if self.language == "python":
            return f'urllib.parse.quote({arg}, safe="")'
        return f"encodeURIComponent({arg})"

    def _emit_fn_int(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime INT
        arg = self._emit_num(node.args[0])
        if self.language == "python":
            return f"math.floor({arg})"
        return f"Math.floor({arg})"

    def _emit_fn_abs(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime ABS
        arg = self._emit_num(node.args[0])
        if self.language == "python":
            return f"abs({arg})"
        return f"Math.abs({arg})"

    def _emit_fn_sqrt(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime SQRT
        arg = self._emit_num(node.args[0])
        if self.language == "python":
            return f"math.sqrt({arg})"
        return f"Math.sqrt({arg})"

    def _emit_fn_exp(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime EXP
        arg = self._emit_num(node.args[0])
        if self.language == "python":
            return f"math.exp({arg})"
        return f"Math.exp({arg})"

    def _emit_fn_log10(self, node: FunctionCall) -> str | None:
        if self.language == "rust":
            return None  # Fall through to F::LOG10(&arg) — note: LOG10 not in runtime yet
        if self.language == "swift":
            # Swift's runtime exposes LOG(v, base?); LOG10 is LOG(v) with default base 10.
            arg = self.emit(node.args[0])
            return f"{self._runtime}.LOG({arg})"
        arg = self._emit_num(node.args[0])
        if self.language == "python":
            return f"math.log10({arg})"
        return f"Math.log10({arg})"

    def _emit_fn_power(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime POWER
        base = self._emit_num(node.args[0])
        exp = self._emit_num(node.args[1])
        if self.language == "python":
            return f"math.pow({base}, {exp})"
        return f"Math.pow({base}, {exp})"

    def _emit_fn_mod(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime MOD
        value = self._emit_num(node.args[0])
        divisor = self._emit_num(node.args[1])
        return f"({value} % {divisor})"

    def _emit_fn_regex_extract(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime REGEX_EXTRACT
        text = self._emit_str(node.args[0])
        regex = self._emit_str(node.args[1])
        if self.language == "python":
            return f"(m.group(0) if (m := re.search({regex}, {text})) else None)"
        return f"({text}.match(new RegExp({regex}))?.[0] ?? null)"

    def _emit_fn_xor(self, node: FunctionCall) -> str:
        left = self.emit(node.args[0])
        right = self.emit(node.args[1])
        if self.language == "rust":
            return f"Value::Bool(F::is_truthy(&{left}) != F::is_truthy(&{right}))"
        if self.language == "swift":
            return f".bool({self._runtime}.isTruthy({left}) != {self._runtime}.isTruthy({right}))"
        if self.language == "python":
            return f"((not {left}) != (not {right}))"
        return f"(!{left} !== !{right})"

    def _emit_fn_if(self, node: FunctionCall) -> str:
        cond = self.emit(node.args[0])
        if_true = self.emit(node.args[1])
        if len(node.args) > 2:
            if_false = self.emit(node.args[2])
        elif self.language == "rust":
            if_false = "json!(null)"
        elif self.language == "swift":
            if_false = ".null"
        elif self.language == "python":
            if_false = "None"
        else:
            if_false = "null"
        if self.language == "rust":
            return f"if F::is_truthy(&{cond}) {{ {if_true} }} else {{ {if_false} }}"
        if self.language == "swift":
            return f"({self._runtime}.isTruthy({cond}) ? {if_true} : {if_false})"
        if self.language == "python":
            return f"({if_true} if {cond} else {if_false})"
        return f"({cond} ? {if_true} : {if_false})"

    def _emit_fn_ifs(self, node: FunctionCall) -> str:
        pairs = []
        for i in range(0, len(node.args) - 1, 2):
            pairs.append((self.emit(node.args[i]), self.emit(node.args[i + 1])))
        if self.language == "rust":
            fallback = "json!(null)"
            result = fallback
            for cond, val in reversed(pairs):
                result = f"if F::is_truthy(&{cond}) {{ {val} }} else {{ {result} }}"
            return result
        if self.language == "swift":
            result = ".null"
            for cond, val in reversed(pairs):
                result = f"({self._runtime}.isTruthy({cond}) ? {val} : {result})"
            return result
        fallback = "None" if self.language == "python" else "null"
        if self.language == "python":
            result = fallback
            for cond, val in reversed(pairs):
                result = f"{val} if {cond} else {result}"
            return f"({result})"
        result = fallback
        for cond, val in reversed(pairs):
            result = f"{cond} ? {val} : {result}"
        return f"({result})"

    def _emit_fn_switch(self, node: FunctionCall) -> str:
        expr_node = node.args[0]
        rest = node.args[1:]
        pairs = []
        for i in range(0, len(rest) - 1, 2):
            pairs.append((self.emit(rest[i]), self.emit(rest[i + 1])))
        if len(rest) % 2 == 1:
            fallback = self.emit(rest[-1])
        elif self.language == "rust":
            fallback = "json!(null)"
        elif self.language == "swift":
            fallback = ".null"
        elif self.language == "python":
            fallback = "None"
        else:
            fallback = "null"
        # Coerce expr to match pattern type when types differ
        first_pattern = rest[0] if rest else None
        expr_type = self._infer_type(expr_node)
        pattern_type = self._infer_type(first_pattern) if first_pattern else None
        if isinstance(expr_node, (StringLiteral, NumberLiteral)):
            expr = self.emit(expr_node)
        elif self.language == "rust":
            if pattern_type == "string" and expr_type != "string":
                expr = f"json!(F::S(&{self.emit(expr_node)}))"
            elif pattern_type == "number" and expr_type != "number":
                expr = f"json!(F::N(&{self.emit(expr_node)}))"
            else:
                expr = self.emit(expr_node)
        elif self.language == "swift":
            # Swift SWITCH is implemented via labeled `cases:` param + default
            # below. Coerce the expr to the pattern type for comparison.
            if pattern_type == "string" and expr_type != "string":
                expr = f".string({self._runtime}.S({self.emit(expr_node)}))"
            elif pattern_type == "number" and expr_type != "number":
                expr = f".double({self._runtime}.N({self.emit(expr_node)}))"
            else:
                expr = self.emit(expr_node)
        elif pattern_type == "string" and expr_type != "string":
            expr = f"{self._runtime}.S({self.emit(expr_node)})"
        elif pattern_type == "number" and expr_type != "number":
            expr = f"{self._runtime}.N({self.emit(expr_node)})"
        else:
            expr = self.emit(expr_node)
        if self.language == "rust":
            result = fallback
            for pattern, val in reversed(pairs):
                result = f"if {expr} == {pattern} {{ {val} }} else {{ {result} }}"
            return result
        if self.language == "swift":
            # Swift's AirtableRuntime.SWITCH signature:
            #   SWITCH(_ expr: AirtableJSONValue?, cases: [(AirtableJSONValue, AirtableJSONValue)], default: AirtableJSONValue?)
            case_tuples = ", ".join(f"({pat}, {val})" for pat, val in pairs)
            return f"{self._runtime}.SWITCH({expr}, cases: [{case_tuples}], default: {fallback})"
        if self.language == "python":
            result = fallback
            for pattern, val in reversed(pairs):
                result = f"{val} if ({expr} == {pattern}) else {result}"
            return f"({result})"
        result = fallback
        for pattern, val in reversed(pairs):
            result = f"({expr} == {pattern}) ? {val} : {result}"
        return f"({result})"

    def _emit_fn_min(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime MIN
        args = ", ".join(self.emit(arg) for arg in node.args)
        if self.language == "python":
            return f"min({self._runtime}.AN(({args},)))"
        an = f"{self._runtime}.AN([{args}])"
        return f"Math.min(...{an})"

    def _emit_fn_max(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime MAX
        args = ", ".join(self.emit(arg) for arg in node.args)
        if self.language == "python":
            return f"max({self._runtime}.AN(({args},)))"
        an = f"{self._runtime}.AN([{args}])"
        return f"Math.max(...{an})"

    def _emit_fn_sum(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift", "typescript", "javascript"):
            return None  # Fall through to F::SUM(&[args]) / F.SUM() / AirtableRuntime.SUM()
        args = ", ".join(self.emit(arg) for arg in node.args)
        return f"sum({self._runtime}.AN(({args},)))"

    def _emit_fn_countall(self, node: FunctionCall) -> str | None:
        if self.language == "rust":
            return None  # Fall through to F::COUNTALL(&[args]) — note: COUNTALL not in runtime
        if self.language == "swift":
            # Swift doesn't have COUNTALL directly; emit A().count.
            args = ", ".join(self.emit(arg) for arg in node.args)
            return f".int({self._runtime}.A([{args}]).count)"
        args = ", ".join(self.emit(arg) for arg in node.args)
        if self.language == "python":
            return f"len({self._runtime}.A(({args},)))"
        return f"{self._runtime}.A([{args}]).length"

    def _emit_fn_round(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift", "typescript", "javascript"):
            return None  # Fall through to runtime ROUND
        val = self._emit_num(node.args[0])
        if len(node.args) > 1 and isinstance(node.args[1], NumberLiteral):
            prec = node.args[1].value
        elif len(node.args) > 1:
            prec = f"int({self._emit_num(node.args[1])})"
        else:
            prec = "0"
        return f"round({val}, {prec})"

    def _emit_fn_concatenate(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime CONCATENATE
        args = ", ".join(self.emit(arg) for arg in node.args)
        if self.language == "python":
            return f'"".join({self._runtime}.AS(({args},)))'
        return f'{self._runtime}.AS([{args}]).join("")'

    def _emit_fn_rept(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime REPT
        text = self._emit_str(node.args[0])
        if self.language == "python":
            if isinstance(node.args[1], NumberLiteral):
                count = node.args[1].value
            else:
                count = f"int({self._emit_num(node.args[1])})"
            return f"({text} * {count})"
        if isinstance(node.args[1], NumberLiteral):
            count = node.args[1].value
        else:
            count = self._emit_num(node.args[1])
        return f"{text}.repeat({count})"

    def _emit_fn_regex_match(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime REGEX_MATCH
        text = self._emit_str(node.args[0])
        regex = self._emit_str(node.args[1])
        if self.language == "python":
            return f"bool(re.search({regex}, {text}))"
        return f"new RegExp({regex}).test({text})"

    def _emit_fn_regex_replace(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime REGEX_REPLACE
        text = self._emit_str(node.args[0])
        regex = self._emit_str(node.args[1])
        repl = self._emit_str(node.args[2])
        if self.language == "python":
            return f"re.sub({regex}, {repl}, {text})"
        return f'{text}.replace(new RegExp({regex}, "g"), {repl})'

    def _emit_fn_today(self, node: FunctionCall) -> str | None:
        if self.language != "python":
            return None  # Fall through to F.TODAY() / AirtableRuntime.TODAY()
        return 'datetime.now().strftime("%Y-%m-%d")'

    def _emit_fn_now(self, node: FunctionCall) -> str | None:
        if self.language != "python":
            return None  # Fall through to F.NOW() / AirtableRuntime.NOW()
        return "datetime.now().isoformat()"

    def _emit_fn_set_locale(self, node: FunctionCall) -> str:
        return self.emit(node.args[0])

    def _emit_fn_datetime_parse(self, node: FunctionCall) -> str | None:
        if self.language == "rust":
            # Rust DATETIME_PARSE only takes 1 arg (ignores format string)
            return f"{self._runtime}::DATETIME_PARSE(&{self.emit(node.args[0])})"
        if self.language == "swift":
            # Swift DATETIME_PARSE takes 1 arg (ignores format string)
            return f"{self._runtime}.DATETIME_PARSE({self.emit(node.args[0])})"
        return f"{self._runtime}.D({self.emit(node.args[0])})"

    _JS_DATE_GETTERS: dict[str, str] = {
        "YEAR": "getUTCFullYear",
        "MONTH": "getUTCMonth",
        "DAY": "getUTCDate",
        "HOUR": "getUTCHours",
        "MINUTE": "getUTCMinutes",
        "SECOND": "getUTCSeconds",
        "WEEKDAY": "getUTCDay",
    }

    _PY_DATE_ATTRS: dict[str, str] = {
        "YEAR": "year",
        "MONTH": "month",
        "DAY": "day",
        "HOUR": "hour",
        "MINUTE": "minute",
        "SECOND": "second",
    }

    def _emit_fn_date_part(self, node: FunctionCall) -> str | None:
        if self.language in ("rust", "swift"):
            return None  # Fall through to runtime YEAR/MONTH/DAY/etc.
        d = f"{self._runtime}.D({self.emit(node.args[0])})"
        if self.language != "python":
            getter = self._JS_DATE_GETTERS.get(node.name)
            if getter is None:
                return None
            if node.name == "MONTH":
                return f"({d}.getUTCMonth() + 1)"
            return f"{d}.{getter}()"
        attr = self._PY_DATE_ATTRS.get(node.name)
        if attr is None:
            return None  # WEEKDAY falls through to F.WEEKDAY()
        return f"{d}.{attr}"

    def _emit_fn_datestr(self, node: FunctionCall) -> str | None:
        if self.language != "python":
            return None  # Fall through to runtime DATESTR
        return f'{self._runtime}.D({self.emit(node.args[0])}).strftime("%Y-%m-%d")'

    def _emit_fn_timestr(self, node: FunctionCall) -> str | None:
        if self.language != "python":
            return None  # Fall through to runtime TIMESTR
        return f'{self._runtime}.D({self.emit(node.args[0])}).strftime("%H:%M:%S")'

    # endregion

    _FUNCTION_HANDLERS: dict[str, Callable] = {
        "RECORD_ID": _emit_fn_record_id,
        "TRUE": _emit_fn_true,
        "FALSE": _emit_fn_false,
        "BLANK": _emit_fn_blank,
        "NOT": _emit_fn_not,
        "AND": _emit_fn_and,
        "OR": _emit_fn_or,
        "LEN": _emit_fn_len,
        "LOWER": _emit_fn_str_method,
        "UPPER": _emit_fn_str_method,
        "TRIM": _emit_fn_str_method,
        "ENCODE_URL_COMPONENT": _emit_fn_encode_url_component,
        "INT": _emit_fn_int,
        "ABS": _emit_fn_abs,
        "SQRT": _emit_fn_sqrt,
        "EXP": _emit_fn_exp,
        "LOG10": _emit_fn_log10,
        "POWER": _emit_fn_power,
        "MOD": _emit_fn_mod,
        "REGEX_EXTRACT": _emit_fn_regex_extract,
        "XOR": _emit_fn_xor,
        "IF": _emit_fn_if,
        "IFS": _emit_fn_ifs,
        "SWITCH": _emit_fn_switch,
        "MIN": _emit_fn_min,
        "MAX": _emit_fn_max,
        "SUM": _emit_fn_sum,
        "COUNTALL": _emit_fn_countall,
        "ROUND": _emit_fn_round,
        "CONCATENATE": _emit_fn_concatenate,
        "REPT": _emit_fn_rept,
        "REGEX_MATCH": _emit_fn_regex_match,
        "REGEX_REPLACE": _emit_fn_regex_replace,
        "TODAY": _emit_fn_today,
        "NOW": _emit_fn_now,
        "SET_LOCALE": _emit_fn_set_locale,
        "DATETIME_PARSE": _emit_fn_datetime_parse,
        "YEAR": _emit_fn_date_part,
        "MONTH": _emit_fn_date_part,
        "DAY": _emit_fn_date_part,
        "HOUR": _emit_fn_date_part,
        "MINUTE": _emit_fn_date_part,
        "SECOND": _emit_fn_date_part,
        "WEEKDAY": _emit_fn_date_part,
        "DATESTR": _emit_fn_datestr,
        "TIMESTR": _emit_fn_timestr,
    }

    def _emit_str(self, node: ASTNode) -> str:
        """Emit node in string context. String literals pass through; concat recurses; others get F.S()."""
        if isinstance(node, StringLiteral):
            if self.language in ("rust", "swift"):
                # Both Rust and Swift use double-quoted string literals.
                val = node.value
                if val.startswith("'") and val.endswith("'"):
                    val = '"' + val[1:-1].replace('"', '\\"') + '"'
                return val
            return node.value
        if isinstance(node, BinaryOp) and node.op == "&":
            left = self._emit_str(node.left)
            right = self._emit_str(node.right)
            if self.language == "rust":
                return f'format!("{{}}{{}}", {left}, {right})'
            if self.language == "swift":
                # Swift: "\(left)\(right)" is cleanest, but concat via + works for String pieces.
                return f"({left} + {right})"
            return f"({left} + {right})"
        if self.language == "rust":
            return f"F::S(&{self.emit(node)})"
        return f"{self._runtime}.S({self.emit(node)})"

    def _emit_num(self, node: ASTNode) -> str:
        """Emit node in numeric context. Literals pass through; arithmetic recurses; others get F.N()."""
        if isinstance(node, NumberLiteral):
            value = self._normalize_number(node.value)
            if self.language == "rust":
                return f"{value}_f64"
            if self.language == "swift":
                # Swift Double literal — ensure decimal form so result is Double.
                return value if "." in value else f"Double({value})"
            return value
        if isinstance(node, BinaryOp) and node.op in ("+", "-", "*", "/"):
            left = self._emit_num(node.left)
            right = self._emit_num(node.right)
            return f"({left} {node.op} {right})"
        if isinstance(node, UnaryOp) and node.op == "-":
            return f"(-{self._emit_num(node.operand)})"
        if self.language == "rust":
            return f"F::N(&{self.emit(node)})"
        return f"{self._runtime}.N({self.emit(node)})"

    @staticmethod
    def _infer_type(node: ASTNode) -> str | None:
        """Infer the result type of a node for equality coercion."""
        if isinstance(node, StringLiteral):
            return "string"
        if isinstance(node, NumberLiteral):
            return "number"
        if isinstance(node, FunctionCall):
            if node.name in _STRING_RETURNING_FUNCTIONS:
                return "string"
            if node.name in _NUMBER_RETURNING_FUNCTIONS:
                return "number"
        if isinstance(node, BinaryOp):
            if node.op in ("+", "-", "*", "/"):
                return "number"
            if node.op == "&":
                return "string"
        if isinstance(node, UnaryOp) and node.op == "-":
            return "number"
        return None

    def _emit_eq_operand(self, node: ASTNode, other: ASTNode) -> str:
        """Emit a node for equality comparison, coercing based on the other operand's type."""
        if isinstance(node, (StringLiteral, NumberLiteral)):
            return self.emit(node)
        node_type = self._infer_type(node)
        other_type = self._infer_type(other)
        if self.language == "rust":
            if other_type == "string" and node_type != "string":
                return f"json!(F::S(&{self.emit(node)}))"
            if other_type == "number" and node_type != "number":
                return f"json!(F::N(&{self.emit(node)}))"
            return self.emit(node)
        if self.language == "swift":
            if other_type == "string" and node_type != "string":
                return f".string({self._runtime}.S({self.emit(node)}))"
            if other_type == "number" and node_type != "number":
                return f".double({self._runtime}.N({self.emit(node)}))"
            return self.emit(node)
        if other_type == "string" and node_type != "string":
            return f"{self._runtime}.S({self.emit(node)})"
        if other_type == "number" and node_type != "number":
            return f"{self._runtime}.N({self.emit(node)})"
        return self.emit(node)

    def _emit_binary_op(self, node: BinaryOp) -> str:
        if node.op in ("+", "-", "*", "/"):
            num_expr = self._emit_num(node)
            if self.language == "rust":
                return f"json!({num_expr})"
            if self.language == "swift":
                # Numeric arithmetic in Swift produces Double → wrap back into AirtableJSONValue.
                return f".double({num_expr})"
            return num_expr
        if node.op in ("<", ">", "<=", ">="):
            left = self._emit_num(node.left)
            right = self._emit_num(node.right)
            if self.language == "rust":
                return f"Value::Bool({left} {node.op} {right})"
            if self.language == "swift":
                return f".bool({left} {node.op} {right})"
            return f"({left} {node.op} {right})"
        if node.op in ("=", "!="):
            left = self._emit_eq_operand(node.left, node.right)
            right = self._emit_eq_operand(node.right, node.left)
            native_op = "==" if node.op == "=" else "!="
            if self.language == "rust":
                return f"Value::Bool({left} {native_op} {right})"
            if self.language == "swift":
                return f".bool({left} {native_op} {right})"
            return f"({left} {native_op} {right})"
        if node.op == "&":
            if self.language == "rust":
                left = self._emit_str(node.left)
                right = self._emit_str(node.right)
                return f'Value::String(format!("{{}}{{}}", {left}, {right}))'
            if self.language == "swift":
                # In a value context, wrap concatenation result in .string(...).
                left = self._emit_str(node.left)
                right = self._emit_str(node.right)
                return f".string({left} + {right})"
            return self._emit_str(node)
        raise ParseError(f"Unknown operator: {node.op}")

    def _emit_unary_op(self, node: UnaryOp) -> str:
        if node.op == "-":
            num_expr = self._emit_num(node)
            if self.language == "rust":
                return f"json!({num_expr})"
            if self.language == "swift":
                return f".double({num_expr})"
            return num_expr
        raise ParseError(f"Unknown unary operator: {node.op}")


# endregion


# Functions that cannot be evaluated at runtime (they need server-side context)
UNTRANSPILABLE_FUNCTIONS: set[str] = {
    "CREATED_TIME",
    "LAST_MODIFIED_TIME",
}


def _contains_untranspilable(node: ASTNode) -> bool:
    """Check if an AST contains any function calls that can't work at runtime."""
    if isinstance(node, FunctionCall):
        if node.name in UNTRANSPILABLE_FUNCTIONS:
            return True
        return any(_contains_untranspilable(arg) for arg in node.args)
    if isinstance(node, BinaryOp):
        return _contains_untranspilable(node.left) or _contains_untranspilable(node.right)
    if isinstance(node, UnaryOp):
        return _contains_untranspilable(node.operand)
    return False


# region Public API


def formula_is_transpilable(formula: str) -> bool:
    """Check if a formula string can be transpiled (contains no untranspilable functions)."""
    if not formula or not formula.strip():
        return True
    try:
        tokens = tokenize_formula(formula)
        parser = FormulaParser(tokens)
        ast = parser.parse()
        return not _contains_untranspilable(ast)
    except Exception:
        return False


def transpile_formula(
    formula: str,
    language: Language,
    field_name_map: dict[str, str],
    formula_field_ids: set[str],
    linked_record_field_ids: set[str] | None = None,
    single_linked_record_field_ids: set[str] | None = None,
) -> str | None:
    """Transpile an Airtable formula to native code.

    Args:
        formula: The raw Airtable formula string.
        language: Target language ("typescript", "javascript", "python").
        field_name_map: Mapping of field_id -> property name in the target language.
        formula_field_ids: Set of field IDs that are formula fields (called as functions).
        linked_record_field_ids: Set of field IDs that are plural linked record fields (.ids).
        single_linked_record_field_ids: Set of field IDs that are single linked record fields (.id).

    Returns:
        The transpiled code string, or None if translation fails.
    """
    if not formula or not formula.strip():
        return None

    try:
        tokens = tokenize_formula(formula)
        parser = FormulaParser(tokens)
        ast = parser.parse()
        if _contains_untranspilable(ast):
            logger.info("Formula %r contains runtime-untranspilable functions, falling back to getter", formula)
            return None
        emitter = CodeEmitter(language, field_name_map, formula_field_ids, linked_record_field_ids, single_linked_record_field_ids)
        return emitter.emit(ast)
    except Exception as e:
        logger.warning("Could not transpile formula %r: %s", formula, e)
        return None


def transpile_table_formulas(
    formulas: dict[str, str],
    language: Language,
    field_name_map: dict[str, str],
    all_formula_field_ids: set[str],
    linked_record_field_ids: set[str] | None = None,
    single_linked_record_field_ids: set[str] | None = None,
) -> dict[str, str]:
    """Transpile all formula fields for a table.

    All formula field IDs are treated as callable (since all formula fields
    are always emitted as functions), so references to any formula field
    will use function-call syntax regardless of whether that field's own
    formula was translatable.

    Args:
        formulas: Mapping of field_id -> raw Airtable formula string.
        language: Target language.
        field_name_map: Mapping of field_id -> property name in the target language.
        all_formula_field_ids: Set of ALL formula field IDs in the table.
        linked_record_field_ids: Set of field IDs that are plural linked record fields (.ids).
        single_linked_record_field_ids: Set of field IDs that are single linked record fields (.id).

    Returns:
        Mapping of field_id -> transpiled code string (only successfully transpiled formulas).
    """
    transpiled: dict[str, str] = {}
    for field_id, formula_str in formulas.items():
        code = transpile_formula(
            formula_str, language, field_name_map, all_formula_field_ids, linked_record_field_ids, single_linked_record_field_ids
        )
        if code is not None:
            transpiled[field_id] = code
    return transpiled


# endregion

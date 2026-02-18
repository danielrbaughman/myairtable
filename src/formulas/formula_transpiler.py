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
from typing import Literal

from .formula_tokenizer import Token, TokenType, tokenize_formula

logger = logging.getLogger(__name__)

Language = Literal["typescript", "javascript", "python"]


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
        while self.peek() and self.peek().type == TokenType.OPERATOR and self.peek().value in ("=", "!=", "<", ">", "<=", ">="):
            op = self.advance().value
            right = self.parse_concat()
            left = BinaryOp(op, left, right)
        return left

    def parse_concat(self) -> ASTNode:
        left = self.parse_additive()
        while self.peek() and self.peek().type == TokenType.OPERATOR and self.peek().value == "&":
            self.advance()
            right = self.parse_additive()
            left = BinaryOp("&", left, right)
        return left

    def parse_additive(self) -> ASTNode:
        left = self.parse_multiplicative()
        while self.peek() and self.peek().type == TokenType.OPERATOR and self.peek().value in ("+", "-"):
            op = self.advance().value
            right = self.parse_multiplicative()
            left = BinaryOp(op, left, right)
        return left

    def parse_multiplicative(self) -> ASTNode:
        left = self.parse_unary()
        while self.peek() and self.peek().type == TokenType.OPERATOR and self.peek().value in ("*", "/"):
            op = self.advance().value
            right = self.parse_unary()
            left = BinaryOp(op, left, right)
        return left

    def parse_unary(self) -> ASTNode:
        if self.peek() and self.peek().type == TokenType.OPERATOR and self.peek().value == "-":
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
        self._self = "self" if language == "python" else "this"
        self._runtime = "F"

    def emit(self, node: ASTNode) -> str:
        if isinstance(node, NumberLiteral):
            return node.value

        if isinstance(node, StringLiteral):
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

    def _emit_function_call(self, node: FunctionCall) -> str:
        name = node.name

        # Special cases that reference model properties
        if name == "RECORD_ID":
            return f"{self._self}.id"

        # Boolean literals - emit native syntax
        if name == "TRUE":
            return "True" if self.language == "python" else "true"
        if name == "FALSE":
            return "False" if self.language == "python" else "false"

        if name == "BLANK":
            if not node.args:
                return "None" if self.language == "python" else "null"
            arg = self.emit(node.args[0])
            if self.language == "python":
                return f"({arg} is None)"
            return f"({arg} == null)"

        if name == "NOT":
            arg = self.emit(node.args[0])
            return f"not {arg}" if self.language == "python" else f"!{arg}"

        if name in ("AND", "OR"):
            parts = [self.emit(arg) for arg in node.args]
            if len(parts) == 0:
                if name == "AND":
                    return "True" if self.language == "python" else "true"
                return "False" if self.language == "python" else "false"
            if len(parts) == 1:
                return parts[0]
            op = " and " if self.language == "python" else " && "
            if name == "OR":
                op = " or " if self.language == "python" else " || "
            return f"({op.join(parts)})"

        if name == "LEN":
            arg = self._emit_str(node.args[0])
            if self.language == "python":
                return f"len({arg})"
            return f"{arg}.length"

        if name in ("LOWER", "UPPER", "TRIM"):
            arg = self._emit_str(node.args[0])
            if self.language == "python":
                method = {"LOWER": "lower", "UPPER": "upper", "TRIM": "strip"}[name]
                return f"{arg}.{method}()"
            method = {"LOWER": "toLowerCase", "UPPER": "toUpperCase", "TRIM": "trim"}[name]
            return f"{arg}.{method}()"

        if name == "ENCODE_URL_COMPONENT":
            arg = self._emit_str(node.args[0])
            if self.language == "python":
                return f'urllib.parse.quote({arg}, safe="")'
            return f"encodeURIComponent({arg})"

        if name == "INT":
            arg = self._emit_num(node.args[0])
            if self.language == "python":
                return f"math.floor({arg})"
            return f"Math.floor({arg})"

        if name == "ABS":
            arg = self._emit_num(node.args[0])
            if self.language == "python":
                return f"abs({arg})"
            return f"Math.abs({arg})"

        if name == "SQRT":
            arg = self._emit_num(node.args[0])
            if self.language == "python":
                return f"math.sqrt({arg})"
            return f"Math.sqrt({arg})"

        if name == "EXP":
            arg = self._emit_num(node.args[0])
            if self.language == "python":
                return f"math.exp({arg})"
            return f"Math.exp({arg})"

        if name == "LOG10":
            arg = self._emit_num(node.args[0])
            if self.language == "python":
                return f"math.log10({arg})"
            return f"Math.log10({arg})"

        if name == "POWER":
            base = self._emit_num(node.args[0])
            exp = self._emit_num(node.args[1])
            if self.language == "python":
                return f"math.pow({base}, {exp})"
            return f"Math.pow({base}, {exp})"

        if name == "MOD":
            value = self._emit_num(node.args[0])
            divisor = self._emit_num(node.args[1])
            return f"({value} % {divisor})"

        if name == "REGEX_EXTRACT":
            text = self._emit_str(node.args[0])
            regex = self._emit_str(node.args[1])
            if self.language == "python":
                return f"(m.group(0) if (m := re.search({regex}, {text})) else None)"
            return f"({text}.match(new RegExp({regex}))?.[0] ?? null)"

        if name == "XOR":
            left = self.emit(node.args[0])
            right = self.emit(node.args[1])
            if self.language == "python":
                return f"((not {left}) != (not {right}))"
            return f"(!{left} !== !{right})"

        if name == "IF":
            cond = self.emit(node.args[0])
            if_true = self.emit(node.args[1])
            if_false = self.emit(node.args[2]) if len(node.args) > 2 else ("None" if self.language == "python" else "null")
            if self.language == "python":
                return f"({if_true} if {cond} else {if_false})"
            return f"({cond} ? {if_true} : {if_false})"

        if name == "IFS":
            pairs = []
            for i in range(0, len(node.args) - 1, 2):
                pairs.append((self.emit(node.args[i]), self.emit(node.args[i + 1])))
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

        if name == "SWITCH":
            expr_node = node.args[0]
            rest = node.args[1:]
            pairs = []
            for i in range(0, len(rest) - 1, 2):
                pairs.append((self.emit(rest[i]), self.emit(rest[i + 1])))
            if len(rest) % 2 == 1:
                fallback = self.emit(rest[-1])
            else:
                fallback = "None" if self.language == "python" else "null"
            # Coerce expr to match pattern type when types differ
            first_pattern = rest[0] if rest else None
            expr_type = self._infer_type(expr_node)
            pattern_type = self._infer_type(first_pattern) if first_pattern else None
            if isinstance(expr_node, (StringLiteral, NumberLiteral)):
                expr = self.emit(expr_node)
            elif pattern_type == "string" and expr_type != "string":
                expr = f"{self._runtime}.S({self.emit(expr_node)})"
            elif pattern_type == "number" and expr_type != "number":
                expr = f"{self._runtime}.N({self.emit(expr_node)})"
            else:
                expr = self.emit(expr_node)
            if self.language == "python":
                result = fallback
                for pattern, val in reversed(pairs):
                    result = f"{val} if ({expr} == {pattern}) else {result}"
                return f"({result})"
            result = fallback
            for pattern, val in reversed(pairs):
                result = f"({expr} == {pattern}) ? {val} : {result}"
            return f"({result})"

        if name in ("SUM", "MIN", "MAX") and self.language == "python":
            args = ", ".join(self.emit(arg) for arg in node.args)
            an = f"{self._runtime}.AN(({args},))"
            if name == "SUM":
                return f"sum({an})"
            if name == "MIN":
                return f"min({an})"
            return f"max({an})"

        if name == "COUNTALL" and self.language == "python":
            args = ", ".join(self.emit(arg) for arg in node.args)
            return f"len({self._runtime}.A(({args},)))"

        if name == "ROUND" and self.language == "python":
            val = self._emit_num(node.args[0])
            if len(node.args) > 1 and isinstance(node.args[1], NumberLiteral):
                prec = node.args[1].value
            elif len(node.args) > 1:
                prec = f"int({self._emit_num(node.args[1])})"
            else:
                prec = "0"
            return f"round({val}, {prec})"

        if name == "CONCATENATE" and self.language == "python":
            args = ", ".join(self.emit(arg) for arg in node.args)
            return f'"".join({self._runtime}.AS(({args},)))'

        if name == "REPT" and self.language == "python":
            text = self._emit_str(node.args[0])
            if isinstance(node.args[1], NumberLiteral):
                count = node.args[1].value
            else:
                count = f"int({self._emit_num(node.args[1])})"
            return f"({text} * {count})"

        if name == "REGEX_MATCH" and self.language == "python":
            text = self._emit_str(node.args[0])
            regex = self._emit_str(node.args[1])
            return f"bool(re.search({regex}, {text}))"

        if name == "REGEX_REPLACE" and self.language == "python":
            text = self._emit_str(node.args[0])
            regex = self._emit_str(node.args[1])
            repl = self._emit_str(node.args[2])
            return f"re.sub({regex}, {repl}, {text})"

        args = ", ".join(self.emit(arg) for arg in node.args)
        return f"{self._runtime}.{name}({args})"

    def _emit_str(self, node: ASTNode) -> str:
        """Emit node in string context. String literals pass through; concat recurses; others get F.S()."""
        if isinstance(node, StringLiteral):
            return node.value
        if isinstance(node, BinaryOp) and node.op == "&":
            left = self._emit_str(node.left)
            right = self._emit_str(node.right)
            return f"({left} + {right})"
        return f"{self._runtime}.S({self.emit(node)})"

    def _emit_num(self, node: ASTNode) -> str:
        """Emit node in numeric context. Literals pass through; arithmetic recurses; others get F.N()."""
        if isinstance(node, NumberLiteral):
            return node.value
        if isinstance(node, BinaryOp) and node.op in ("+", "-", "*", "/"):
            left = self._emit_num(node.left)
            right = self._emit_num(node.right)
            return f"({left} {node.op} {right})"
        if isinstance(node, UnaryOp) and node.op == "-":
            return f"(-{self._emit_num(node.operand)})"
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
        """Emit a node for equality comparison, coercing based on the other operand's type.

        Fields may have array types (e.g. string[] | undefined) due to Airtable's
        return data shape, and function return types may not match the literal on
        the other side (e.g. DATETIME_FORMAT returns string, compared to number 7).
        We coerce with F.S() or F.N() to flatten arrays and align types.
        """
        if isinstance(node, (StringLiteral, NumberLiteral)):
            return self.emit(node)
        node_type = self._infer_type(node)
        other_type = self._infer_type(other)
        if other_type == "string" and node_type != "string":
            return f"{self._runtime}.S({self.emit(node)})"
        if other_type == "number" and node_type != "number":
            return f"{self._runtime}.N({self.emit(node)})"
        return self.emit(node)

    def _emit_binary_op(self, node: BinaryOp) -> str:
        if node.op in ("+", "-", "*", "/"):
            return self._emit_num(node)
        if node.op in ("<", ">", "<=", ">="):
            left = self._emit_num(node.left)
            right = self._emit_num(node.right)
            return f"({left} {node.op} {right})"
        if node.op in ("=", "!="):
            left = self._emit_eq_operand(node.left, node.right)
            right = self._emit_eq_operand(node.right, node.left)
            native_op = "==" if node.op == "=" else "!="
            return f"({left} {native_op} {right})"
        if node.op == "&":
            return self._emit_str(node)
        raise ParseError(f"Unknown operator: {node.op}")

    def _emit_unary_op(self, node: UnaryOp) -> str:
        if node.op == "-":
            return self._emit_num(node)
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
    except (ParseError, Exception) as e:
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

"""
Airtable Formula Tokenizer

Tokenizes Airtable formulas into structured tokens for parsing,
syntax highlighting, or other analysis.

Usage:
    >>> from formula_tokenizer import FormulaTokenizer, TokenType
    >>> tokenizer = FormulaTokenizer("SUM({Amount}, 100)")
    >>> tokens = tokenizer.tokenize()
"""

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    """Token types for Airtable formula syntax."""

    FUNCTION = auto()
    FIELD_REF = auto()
    STRING = auto()
    NUMBER = auto()
    OPERATOR = auto()
    PARENTHESIS = auto()
    COMMA = auto()
    WHITESPACE = auto()
    UNKNOWN = auto()


@dataclass
class Token:
    """A single token from the formula."""

    type: TokenType
    value: str
    depth: int = 0  # Nesting depth for parentheses (1-indexed)


# Complete set of Airtable functions (case-insensitive matching)
AIRTABLE_FUNCTIONS: frozenset[str] = frozenset(
    [
        # Logical
        "IF",
        "SWITCH",
        "IFS",
        "AND",
        "OR",
        "XOR",
        "NOT",
        "TRUE",
        "FALSE",
        "BLANK",
        # Numeric
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
        # String
        "CONCATENATE",
        "LEFT",
        "RIGHT",
        "MID",
        "LEN",
        "FIND",
        "SEARCH",
        "SUBSTITUTE",
        "REPLACE",
        "LOWER",
        "UPPER",
        "TRIM",
        "REPT",
        "T",
        "ENCODE_URL_COMPONENT",
        "REGEX_MATCH",
        "REGEX_EXTRACT",
        "REGEX_REPLACE",
        # Date/Time
        "TODAY",
        "NOW",
        "DATEADD",
        "DATETIME_DIFF",
        "DATETIME_FORMAT",
        "DATETIME_PARSE",
        "SET_LOCALE",
        "SET_TIMEZONE",
        "YEAR",
        "MONTH",
        "DAY",
        "HOUR",
        "MINUTE",
        "SECOND",
        "WEEKDAY",
        "WEEKNUM",
        "TIMESTR",
        "TONOW",
        "FROMNOW",
        "IS_SAME",
        "IS_BEFORE",
        "IS_AFTER",
        "WORKDAY",
        "WORKDAY_DIFF",
        # Array
        "ARRAYJOIN",
        "ARRAYUNIQUE",
        "ARRAYCOMPACT",
        "ARRAYFLATTEN",
        # Record/Special
        "RECORD_ID",
        "CREATED_TIME",
        "LAST_MODIFIED_TIME",
        "ERROR",
        "ISERROR",
    ]
)

# Multi-character operators (must check before single-char)
MULTI_CHAR_OPERATORS: frozenset[str] = frozenset(["!=", "<=", ">="])

# Single-character operators
SINGLE_CHAR_OPERATORS: frozenset[str] = frozenset(["=", "<", ">", "&", "+", "-", "*", "/"])


class FormulaTokenizer:
    """
    Tokenizer for Airtable formulas.

    Handles strings, field references, functions, operators, and numbers
    with proper state tracking for nested structures.
    """

    def __init__(self, formula: str) -> None:
        self.formula = formula
        self.pos = 0
        self.tokens: list[Token] = []
        self.paren_depth = 0  # Track nesting depth for parentheses

    def tokenize(self) -> list[Token]:
        """Tokenize the formula and return list of tokens."""
        while self.pos < len(self.formula):
            # Try each token type in priority order
            if self._try_whitespace():
                continue
            if self._try_string():
                continue
            if self._try_field_ref():
                continue
            if self._try_number():
                continue
            if self._try_operator():
                continue
            if self._try_parenthesis():
                continue
            if self._try_comma():
                continue
            if self._try_function_or_identifier():
                continue

            # Unknown character - add as single token
            self._add_unknown()

        return self.tokens

    def _add_token(self, token_type: TokenType, value: str) -> None:
        """Add a token to the list."""
        self.tokens.append(Token(token_type, value))

    def _try_whitespace(self) -> bool:
        """Tokenize whitespace (spaces, tabs, newlines)."""
        if not self.formula[self.pos].isspace():
            return False

        start = self.pos

        while self.pos < len(self.formula) and self.formula[self.pos].isspace():
            self.pos += 1

        value = self.formula[start : self.pos]
        self._add_token(TokenType.WHITESPACE, value)
        return True

    def _try_string(self) -> bool:
        """Tokenize string literals with escape handling."""
        char = self.formula[self.pos]
        if char not in ('"', "'"):
            return False

        quote_char = char
        start = self.pos
        self.pos += 1  # Skip opening quote

        while self.pos < len(self.formula):
            char = self.formula[self.pos]

            if char == "\\" and self.pos + 1 < len(self.formula):
                # Skip escape sequence
                self.pos += 2
                continue

            if char == quote_char:
                # Found closing quote
                self.pos += 1
                break

            self.pos += 1

        value = self.formula[start : self.pos]
        self._add_token(TokenType.STRING, value)
        return True

    def _try_field_ref(self) -> bool:
        """Tokenize field references {Field Name} or {fldXYZ}."""
        if self.formula[self.pos] != "{":
            return False

        start = self.pos
        self.pos += 1  # Skip opening brace
        depth = 1

        while self.pos < len(self.formula) and depth > 0:
            char = self.formula[self.pos]

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1

            self.pos += 1

        value = self.formula[start : self.pos]
        self._add_token(TokenType.FIELD_REF, value)
        return True

    def _is_negative_number_context(self) -> bool:
        """Check if '-' at current position is a negative sign vs operator."""
        if self.pos == 0:
            return True

        # Look at the last non-whitespace token
        for token in reversed(self.tokens):
            if token.type == TokenType.WHITESPACE:
                continue
            # Negative if after: open paren, comma, or operator
            if token.type in (TokenType.PARENTHESIS, TokenType.COMMA, TokenType.OPERATOR):
                return token.value in ("(", ",") or token.type == TokenType.OPERATOR
            # After number, field ref, close paren, or function - it's subtraction
            return False

        return True

    def _try_number(self) -> bool:
        """Tokenize numeric literals (integers and decimals)."""
        start = self.pos

        # Handle negative numbers
        if self.formula[self.pos] == "-":
            if not self._is_negative_number_context():
                return False
            # Check if followed by digit
            if self.pos + 1 >= len(self.formula) or not self.formula[self.pos + 1].isdigit():
                return False
            self.pos += 1

        # Must start with digit
        if self.pos >= len(self.formula) or not self.formula[self.pos].isdigit():
            self.pos = start
            return False

        # Consume digits
        while self.pos < len(self.formula) and self.formula[self.pos].isdigit():
            self.pos += 1

        # Optional decimal part
        if self.pos < len(self.formula) and self.formula[self.pos] == ".":
            self.pos += 1
            # Consume fractional digits
            while self.pos < len(self.formula) and self.formula[self.pos].isdigit():
                self.pos += 1

        value = self.formula[start : self.pos]
        self._add_token(TokenType.NUMBER, value)
        return True

    def _try_operator(self) -> bool:
        """Tokenize operators."""
        # Check two-character operators first
        if self.pos + 1 < len(self.formula):
            two_char = self.formula[self.pos : self.pos + 2]
            if two_char in MULTI_CHAR_OPERATORS:
                self._add_token(TokenType.OPERATOR, two_char)
                self.pos += 2
                return True

        # Check single-character operators
        char = self.formula[self.pos]
        if char in SINGLE_CHAR_OPERATORS:
            self._add_token(TokenType.OPERATOR, char)
            self.pos += 1
            return True

        return False

    def _try_parenthesis(self) -> bool:
        """Tokenize parentheses with depth tracking for alternating colors."""
        char = self.formula[self.pos]
        if char == "(":
            self.paren_depth += 1
            self.tokens.append(Token(TokenType.PARENTHESIS, char, self.paren_depth))
            self.pos += 1
            return True
        elif char == ")":
            # Use current depth for closing paren, then decrement
            depth = max(1, self.paren_depth)  # Ensure at least 1 for unbalanced
            self.tokens.append(Token(TokenType.PARENTHESIS, char, depth))
            self.paren_depth = max(0, self.paren_depth - 1)
            self.pos += 1
            return True
        return False

    def _try_comma(self) -> bool:
        """Tokenize commas."""
        if self.formula[self.pos] == ",":
            self._add_token(TokenType.COMMA, ",")
            self.pos += 1
            return True
        return False

    def _try_function_or_identifier(self) -> bool:
        """Tokenize function names or identifiers."""
        if not (self.formula[self.pos].isalpha() or self.formula[self.pos] == "_"):
            return False

        start = self.pos

        # Consume alphanumeric and underscore
        while self.pos < len(self.formula):
            char = self.formula[self.pos]
            if char.isalnum() or char == "_":
                self.pos += 1
            else:
                break

        value = self.formula[start : self.pos]

        # Check if it's a known function (case-insensitive)
        if value.upper() in AIRTABLE_FUNCTIONS:
            token_type = TokenType.FUNCTION
        else:
            token_type = TokenType.UNKNOWN

        self._add_token(token_type, value)
        return True

    def _add_unknown(self) -> None:
        """Add single unknown character token."""
        value = self.formula[self.pos]
        self._add_token(TokenType.UNKNOWN, value)
        self.pos += 1

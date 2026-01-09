"""Tests for the formula_highlighter module."""

import json
import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from formula_highlighter import (
    _html_escape,
    _tokens_to_html,
    highlight_formula,
)
from formula_tokenizer import (
    AIRTABLE_FUNCTIONS,
    FormulaTokenizer,
    Token,
    TokenType,
)


class TestHtmlEscape:
    """Test the _html_escape utility function."""

    def test_escapes_ampersand(self):
        assert _html_escape("A & B") == "A &amp; B"

    def test_escapes_less_than(self):
        assert _html_escape("a < b") == "a &lt; b"

    def test_escapes_greater_than(self):
        assert _html_escape("a > b") == "a &gt; b"

    def test_escapes_double_quote(self):
        assert _html_escape('say "hello"') == "say &quot;hello&quot;"

    def test_escapes_single_quote(self):
        # html.escape uses &#x27; (hex) instead of &#39; (decimal) - both are valid
        assert _html_escape("it's") == "it&#x27;s"

    def test_escapes_script_tag(self):
        result = _html_escape("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_empty_string(self):
        assert _html_escape("") == ""

    def test_no_special_chars(self):
        assert _html_escape("plain text") == "plain text"


class TestTokenizerWhitespace:
    """Test whitespace tokenization."""

    def test_single_space(self):
        tokens = FormulaTokenizer(" ").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.WHITESPACE
        assert tokens[0].value == " "

    def test_multiple_spaces(self):
        tokens = FormulaTokenizer("   ").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.WHITESPACE
        assert tokens[0].value == "   "

    def test_newline(self):
        tokens = FormulaTokenizer("\n").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.WHITESPACE

    def test_mixed_whitespace(self):
        tokens = FormulaTokenizer(" \t\n ").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.WHITESPACE


class TestTokenizerStrings:
    """Test string literal tokenization."""

    def test_single_quoted_string(self):
        tokens = FormulaTokenizer("'hello'").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "'hello'"

    def test_double_quoted_string(self):
        tokens = FormulaTokenizer('"hello"').tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == '"hello"'

    def test_escaped_quote_single(self):
        tokens = FormulaTokenizer("'it\\'s'").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "'it\\'s'"

    def test_escaped_quote_double(self):
        tokens = FormulaTokenizer('"say \\"hi\\""').tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.STRING

    def test_empty_string(self):
        tokens = FormulaTokenizer("''").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "''"

    def test_string_with_parens(self):
        tokens = FormulaTokenizer("'text (with) parens'").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.STRING

    def test_unclosed_string(self):
        # Should consume to end without crashing
        tokens = FormulaTokenizer("'unclosed").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.STRING


class TestTokenizerFieldRefs:
    """Test field reference tokenization."""

    def test_simple_field_ref(self):
        tokens = FormulaTokenizer("{Status}").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.FIELD_REF
        assert tokens[0].value == "{Status}"

    def test_field_ref_with_id(self):
        tokens = FormulaTokenizer("{fldABC123}").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.FIELD_REF

    def test_field_ref_with_spaces(self):
        tokens = FormulaTokenizer("{Field Name}").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.FIELD_REF
        assert tokens[0].value == "{Field Name}"

    def test_field_ref_with_special_chars(self):
        tokens = FormulaTokenizer("{Field (with) parens}").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.FIELD_REF

    def test_unclosed_field_ref(self):
        # Should consume to end without crashing
        tokens = FormulaTokenizer("{unclosed").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.FIELD_REF


class TestTokenizerNumbers:
    """Test number tokenization."""

    def test_integer(self):
        tokens = FormulaTokenizer("42").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "42"

    def test_zero(self):
        tokens = FormulaTokenizer("0").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.NUMBER

    def test_decimal(self):
        tokens = FormulaTokenizer("3.14").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "3.14"

    def test_negative_at_start(self):
        tokens = FormulaTokenizer("-10").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "-10"

    def test_negative_after_paren(self):
        tokens = FormulaTokenizer("(-5)").tokenize()
        assert tokens[1].type == TokenType.NUMBER
        assert tokens[1].value == "-5"

    def test_negative_after_comma(self):
        tokens = FormulaTokenizer("IF(1, -5, 0)").tokenize()
        # Find the -5 token
        neg_tokens = [t for t in tokens if t.value == "-5"]
        assert len(neg_tokens) == 1
        assert neg_tokens[0].type == TokenType.NUMBER

    def test_subtraction_not_negative(self):
        tokens = FormulaTokenizer("5 - 3").tokenize()
        # Should be: NUMBER, WHITESPACE, OPERATOR, WHITESPACE, NUMBER
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "5"
        assert tokens[2].type == TokenType.OPERATOR
        assert tokens[2].value == "-"
        assert tokens[4].type == TokenType.NUMBER
        assert tokens[4].value == "3"


class TestTokenizerOperators:
    """Test operator tokenization."""

    def test_equals(self):
        tokens = FormulaTokenizer("=").tokenize()
        assert tokens[0].type == TokenType.OPERATOR
        assert tokens[0].value == "="

    def test_not_equals(self):
        tokens = FormulaTokenizer("!=").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.OPERATOR
        assert tokens[0].value == "!="

    def test_less_than(self):
        tokens = FormulaTokenizer("<").tokenize()
        assert tokens[0].type == TokenType.OPERATOR

    def test_greater_than(self):
        tokens = FormulaTokenizer(">").tokenize()
        assert tokens[0].type == TokenType.OPERATOR

    def test_less_equal(self):
        tokens = FormulaTokenizer("<=").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.OPERATOR
        assert tokens[0].value == "<="

    def test_greater_equal(self):
        tokens = FormulaTokenizer(">=").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.OPERATOR
        assert tokens[0].value == ">="

    def test_ampersand(self):
        tokens = FormulaTokenizer("&").tokenize()
        assert tokens[0].type == TokenType.OPERATOR

    def test_plus(self):
        tokens = FormulaTokenizer("+").tokenize()
        assert tokens[0].type == TokenType.OPERATOR

    def test_minus(self):
        # When not in negative number context
        tokens = FormulaTokenizer("{a} - {b}").tokenize()
        minus_tokens = [t for t in tokens if t.value == "-"]
        assert len(minus_tokens) == 1
        assert minus_tokens[0].type == TokenType.OPERATOR

    def test_multiply(self):
        tokens = FormulaTokenizer("*").tokenize()
        assert tokens[0].type == TokenType.OPERATOR

    def test_divide(self):
        tokens = FormulaTokenizer("/").tokenize()
        assert tokens[0].type == TokenType.OPERATOR


class TestTokenizerParentheses:
    """Test parenthesis tokenization."""

    def test_open_paren(self):
        tokens = FormulaTokenizer("(").tokenize()
        assert tokens[0].type == TokenType.PARENTHESIS
        assert tokens[0].value == "("

    def test_close_paren(self):
        tokens = FormulaTokenizer(")").tokenize()
        assert tokens[0].type == TokenType.PARENTHESIS
        assert tokens[0].value == ")"

    def test_balanced_parens(self):
        tokens = FormulaTokenizer("()").tokenize()
        assert len(tokens) == 2
        assert tokens[0].value == "("
        assert tokens[1].value == ")"


class TestTokenizerComma:
    """Test comma tokenization."""

    def test_comma(self):
        tokens = FormulaTokenizer(",").tokenize()
        assert tokens[0].type == TokenType.COMMA
        assert tokens[0].value == ","


class TestTokenizerFunctions:
    """Test function name tokenization."""

    def test_if_function(self):
        tokens = FormulaTokenizer("IF").tokenize()
        assert tokens[0].type == TokenType.FUNCTION
        assert tokens[0].value == "IF"

    def test_if_lowercase(self):
        tokens = FormulaTokenizer("if").tokenize()
        assert tokens[0].type == TokenType.FUNCTION

    def test_if_mixed_case(self):
        tokens = FormulaTokenizer("If").tokenize()
        assert tokens[0].type == TokenType.FUNCTION

    def test_sum_function(self):
        tokens = FormulaTokenizer("SUM").tokenize()
        assert tokens[0].type == TokenType.FUNCTION

    def test_datetime_format(self):
        tokens = FormulaTokenizer("DATETIME_FORMAT").tokenize()
        assert tokens[0].type == TokenType.FUNCTION

    def test_unknown_identifier(self):
        tokens = FormulaTokenizer("NOTAFUNCTION").tokenize()
        assert tokens[0].type == TokenType.UNKNOWN

    def test_all_airtable_functions_recognized(self):
        for func in AIRTABLE_FUNCTIONS:
            tokens = FormulaTokenizer(func).tokenize()
            assert tokens[0].type == TokenType.FUNCTION, f"{func} not recognized"


class TestTokenizerComplex:
    """Test complex formula tokenization."""

    def test_simple_function_call(self):
        tokens = FormulaTokenizer("SUM(1, 2)").tokenize()
        assert tokens[0].type == TokenType.FUNCTION
        assert tokens[0].value == "SUM"
        assert tokens[1].type == TokenType.PARENTHESIS
        assert tokens[2].type == TokenType.NUMBER
        assert tokens[3].type == TokenType.COMMA
        assert tokens[5].type == TokenType.NUMBER
        assert tokens[6].type == TokenType.PARENTHESIS

    def test_if_with_field_and_string(self):
        formula = "IF({Status} = 'Done', TRUE(), FALSE())"
        tokens = FormulaTokenizer(formula).tokenize()

        # Check key tokens
        func_tokens = [t for t in tokens if t.type == TokenType.FUNCTION]
        assert len(func_tokens) == 3  # IF, TRUE, FALSE

        field_tokens = [t for t in tokens if t.type == TokenType.FIELD_REF]
        assert len(field_tokens) == 1
        assert field_tokens[0].value == "{Status}"

        string_tokens = [t for t in tokens if t.type == TokenType.STRING]
        assert len(string_tokens) == 1
        assert string_tokens[0].value == "'Done'"

    def test_nested_functions(self):
        formula = "IF({a}, SUM({b}, {c}), 0)"
        tokens = FormulaTokenizer(formula).tokenize()

        func_tokens = [t for t in tokens if t.type == TokenType.FUNCTION]
        assert len(func_tokens) == 2  # IF, SUM

    def test_string_concatenation(self):
        formula = '{First} & " " & {Last}'
        tokens = FormulaTokenizer(formula).tokenize()

        amp_tokens = [t for t in tokens if t.value == "&"]
        assert len(amp_tokens) == 2


class TestTokensToHtml:
    """Test the token to HTML conversion."""

    def test_function_gets_color(self):
        tokens = [Token(TokenType.FUNCTION, "IF")]
        html = _tokens_to_html(tokens)
        assert 'style="color:#0066CC"' in html
        assert ">IF<" in html

    def test_field_ref_gets_color(self):
        tokens = [Token(TokenType.FIELD_REF, "{Status}")]
        html = _tokens_to_html(tokens)
        assert 'style="color:#22863A"' in html

    def test_string_no_color(self):
        tokens = [Token(TokenType.STRING, "'text'")]
        html = _tokens_to_html(tokens)
        # Strings are plain text, no color (html.escape uses &#x27; for single quotes)
        assert "&#x27;text&#x27;" in html
        assert "<span" not in html

    def test_whitespace_no_span(self):
        tokens = [Token(TokenType.WHITESPACE, "  ")]
        html = _tokens_to_html(tokens)
        assert "<span" not in html
        assert html == "  "

    def test_html_escaping_in_tokens(self):
        tokens = [Token(TokenType.STRING, "'<script>'")]
        html = _tokens_to_html(tokens)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestHighlightFormula:
    """Test the main highlight_formula function."""

    def test_empty_formula(self):
        assert highlight_formula("") == ""

    def test_none_like_empty(self):
        # Empty string returns empty
        assert highlight_formula("") == ""

    def test_simple_function(self):
        html = highlight_formula("RECORD_ID()")
        assert '<span style="color:#0066CC">RECORD_ID</span>' in html
        assert '<span style="color:#6F42C1">(</span>' in html
        assert '<span style="color:#6F42C1">)</span>' in html

    def test_field_reference(self):
        html = highlight_formula("{Field Name}")
        assert '<span style="color:#22863A">{Field Name}</span>' in html

    def test_string_literal(self):
        html = highlight_formula("'hello'")
        # Strings are not colored, just plain text (html.escape uses &#x27; for single quotes)
        assert "&#x27;hello&#x27;" in html
        assert '<span style="color:#D73A49">' not in html

    def test_number(self):
        html = highlight_formula("42")
        # Numbers are not colored, just plain text
        assert "42" in html
        assert '<span style="color:#E36209">' not in html

    def test_complex_formula(self):
        html = highlight_formula("IF({Status} = 'Done', 1, 0)")
        # Should contain key token types with colors
        assert "#0066CC" in html  # Function
        assert "#22863A" in html  # Field ref
        assert "#D73A49" in html  # Operator (=)
        assert "#6F42C1" in html  # Parentheses
        # Numbers and strings are plain text (no color)
        assert "1" in html and "0" in html
        assert "Done" in html

    def test_preserves_whitespace(self):
        html = highlight_formula("IF(\n  {a},\n  {b}\n)")
        assert "\n" in html

    def test_html_injection_prevented(self):
        html = highlight_formula("<script>alert('xss')</script>")
        # The important check: literal HTML tags should NOT appear
        assert "<script>" not in html
        # The < and > are properly escaped (may be in separate tokens)
        assert "&lt;" in html
        assert "&gt;" in html


class TestRealWorldFormulas:
    """Test with real formula patterns from the codebase."""

    def test_date_formatting(self):
        formula = "DATETIME_FORMAT({Date}, 'MMM D, YYYY')"
        html = highlight_formula(formula)
        assert '<span style="color:#0066CC">DATETIME_FORMAT</span>' in html

    def test_nested_if(self):
        formula = "IF({a}, IF({b}, 1, 2), 3)"
        html = highlight_formula(formula)
        # Should have 2 IF functions highlighted
        assert html.count('<span style="color:#0066CC">IF</span>') == 2

    def test_string_concatenation(self):
        formula = '{First} & " " & {Last}'
        html = highlight_formula(formula)
        # Ampersands should be operators
        assert html.count('<span style="color:#D73A49">&amp;</span>') == 2

    def test_comparison_operators(self):
        formula = "IF({x} >= 10, 'high', IF({x} <= 5, 'low', 'mid'))"
        html = highlight_formula(formula)
        assert '<span style="color:#D73A49">&gt;=</span>' in html
        assert '<span style="color:#D73A49">&lt;=</span>' in html

    def test_multiline_formula(self):
        formula = """IF(
  {Status} = 'Done',
  TRUE(),
  FALSE()
)"""
        html = highlight_formula(formula)
        # Should preserve newlines and indentation
        assert "\n" in html
        assert "  " in html or "&#39;" in html


class TestValidateAgainstMetaJson:
    """Validate highlighter against real formulas from meta.json."""

    @pytest.fixture
    def formula_fields(self):
        """Load formula fields from meta.json if available."""
        meta_path = Path(__file__).parent.parent / "output" / "meta.json"
        if not meta_path.exists():
            pytest.skip("meta.json not available")

        with open(meta_path) as f:
            data = json.load(f)

        formulas = []
        for table in data.get("tables", []):
            for field in table.get("fields", []):
                if field.get("type") == "formula":
                    options = field.get("options", {})
                    if formula := options.get("formula"):
                        formulas.append(formula)

        return formulas

    def test_all_formulas_tokenize_without_error(self, formula_fields):
        """Ensure all real formulas can be highlighted without exceptions."""
        for formula in formula_fields:
            try:
                result = highlight_formula(formula)
                assert result is not None
                assert len(result) > 0
            except Exception as e:
                pytest.fail(f"Failed to highlight formula: {formula[:100]}... Error: {e}")

    def test_output_is_valid_html(self, formula_fields):
        """Check that output contains proper HTML structure."""
        for formula in formula_fields[:50]:  # Test first 50 for performance
            html = highlight_formula(formula)
            # Should have balanced span tags
            open_spans = html.count("<span")
            close_spans = html.count("</span>")
            assert open_spans == close_spans, f"Unbalanced spans in: {formula[:50]}..."

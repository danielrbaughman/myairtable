"""
Airtable Formula Syntax Highlighter

Provides syntax highlighting for Airtable formulas by generating HTML
with inline styles. Compatible with Markdown/Obsidian.

Color Scheme:
    - Functions (IF, SUM, etc.): Blue (#0066CC)
    - Field References {Name}: Green (#22863A)
    - Operators +, -, =: Red (#D73A49)
    - Parentheses (): Purple/Light Blue (alternating by depth)
    - Commas: Pink (#DB2777)

Usage:
    >>> from formula_highlighter import highlight_formula
    >>> html = highlight_formula("SUM({Amount}, 100)")
"""

import html

try:
    from .formula_tokenizer import FormulaTokenizer, Token, TokenType
except ImportError:
    from formula_tokenizer import FormulaTokenizer, Token, TokenType

# Color scheme for syntax highlighting
TOKEN_COLORS: dict[TokenType, str] = {
    TokenType.FUNCTION: "#0066CC",  # Blue
    TokenType.FIELD_REF: "#22863A",  # Green
    TokenType.OPERATOR: "#D73A49",  # Red
    TokenType.PARENTHESIS: "#6F42C1",  # Purple (default, overridden by depth)
    TokenType.COMMA: "#DB2777",  # Pink
}

# Alternating colors for nested parentheses (purple, light blue)
PAREN_COLORS: list[str] = ["#6F42C1", "#0EA5E9"]  # Purple, Light Blue


def _html_escape(text: str) -> str:
    """Escape HTML special characters to prevent injection."""
    return html.escape(text, quote=True)


def _tokens_to_html(tokens: list[Token]) -> str:
    """Convert tokens to HTML with inline styles."""
    parts: list[str] = []

    for token in tokens:
        escaped_value = _html_escape(token.value)

        # Whitespace, numbers, strings, and unknown tokens don't need coloring
        if token.type in (TokenType.WHITESPACE, TokenType.NUMBER, TokenType.STRING, TokenType.UNKNOWN):
            parts.append(escaped_value)
            continue

        # Parentheses use alternating colors based on depth
        if token.type == TokenType.PARENTHESIS:
            # Alternate between colors: depth 1,3,5... = purple, depth 2,4,6... = light blue
            color_index = (token.depth - 1) % len(PAREN_COLORS)
            color = PAREN_COLORS[color_index]
            parts.append(f'<span style="color:{color}">{escaped_value}</span>')
            continue

        # Get color for this token type
        color = TOKEN_COLORS.get(token.type)

        if color:
            parts.append(f'<span style="color:{color}">{escaped_value}</span>')
        else:
            parts.append(escaped_value)

    return "".join(parts)


def highlight_formula(formula: str) -> str:
    """
    Convert Airtable formula to syntax-highlighted HTML.

    Args:
        formula: The Airtable formula string to highlight

    Returns:
        HTML string with inline styles for syntax highlighting

    Example:
        >>> highlight_formula("IF({Status} = 'Done', TRUE(), FALSE())")
        '<span style="color:#0066CC">IF</span>...'
    """
    if not formula:
        return ""

    try:
        tokenizer = FormulaTokenizer(formula)
        tokens = tokenizer.tokenize()
        return _tokens_to_html(tokens)
    except Exception:
        # Fallback: return escaped formula without highlighting
        return _html_escape(formula)

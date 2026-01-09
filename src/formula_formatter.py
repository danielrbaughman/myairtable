"""Formula formatting utilities for Airtable formulas.

This module provides functions to format Airtable formula strings with
proper indentation and newlines for better readability in markdown code blocks.
"""

import re


def _find_matching_paren(formula: str, start: int) -> int:
    """Find the closing paren matching the opening paren at start position.

    Returns -1 if no matching paren found.
    """
    if start >= len(formula) or formula[start] != "(":
        return -1

    depth = 0
    in_single = False
    in_double = False
    in_brace = False

    i = start
    while i < len(formula):
        char = formula[i]

        # Handle escape sequences in strings
        if (in_single or in_double) and char == "\\" and i + 1 < len(formula):
            i += 2
            continue

        # Track string state
        if char == "'" and not in_double and not in_brace:
            in_single = not in_single
        elif char == '"' and not in_single and not in_brace:
            in_double = not in_double
        elif char == "{" and not in_single and not in_double:
            in_brace = True
        elif char == "}" and not in_single and not in_double:
            in_brace = False
        # Track parens only outside strings and braces
        elif char == "(" and not in_single and not in_double and not in_brace:
            depth += 1
        elif char == ")" and not in_single and not in_double and not in_brace:
            depth -= 1
            if depth == 0:
                return i

        i += 1

    return -1  # No matching paren found


def _split_arguments(args_str: str) -> list[str]:
    """Split comma-separated arguments, respecting nesting, strings, and field refs."""
    args: list[str] = []
    current: list[str] = []
    depth = 0
    in_single = False
    in_double = False
    in_brace = False

    i = 0
    while i < len(args_str):
        char = args_str[i]

        # Handle escape sequences
        if (in_single or in_double) and char == "\\" and i + 1 < len(args_str):
            current.append(char)
            current.append(args_str[i + 1])
            i += 2
            continue

        # Track string state
        if char == "'" and not in_double and not in_brace:
            in_single = not in_single
            current.append(char)
        elif char == '"' and not in_single and not in_brace:
            in_double = not in_double
            current.append(char)
        elif char == "{" and not in_single and not in_double:
            in_brace = True
            current.append(char)
        elif char == "}" and not in_single and not in_double:
            in_brace = False
            current.append(char)
        elif char == "(" and not in_single and not in_double and not in_brace:
            depth += 1
            current.append(char)
        elif char == ")" and not in_single and not in_double and not in_brace:
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0 and not in_single and not in_double and not in_brace:
            # Split here
            args.append("".join(current).strip())
            current = []
        else:
            current.append(char)

        i += 1

    # Add last argument
    if current:
        args.append("".join(current).strip())

    return args


def _count_nesting_depth(formula: str) -> int:
    """Count the maximum nesting depth of function calls."""
    max_depth = 0
    current_depth = 0
    in_single = False
    in_double = False
    in_brace = False

    i = 0
    while i < len(formula):
        char = formula[i]

        # Handle escape sequences
        if (in_single or in_double) and char == "\\" and i + 1 < len(formula):
            i += 2
            continue

        if char == "'" and not in_double and not in_brace:
            in_single = not in_single
        elif char == '"' and not in_single and not in_brace:
            in_double = not in_double
        elif char == "{" and not in_single and not in_double:
            in_brace = True
        elif char == "}" and not in_single and not in_double:
            in_brace = False
        elif char == "(" and not in_single and not in_double and not in_brace:
            current_depth += 1
            max_depth = max(max_depth, current_depth)
        elif char == ")" and not in_single and not in_double and not in_brace:
            current_depth -= 1

        i += 1

    return max_depth


def _is_simple_formula(formula: str) -> bool:
    """Check if formula should stay single-line.

    A formula is simple if:
    - Length <= 80 characters AND not IF/SWITCH/IFS
    - Nesting depth <= 1
    """
    # IF, SWITCH, IFS should always be formatted when they have arguments
    always_expand_pattern = re.compile(r"^(IF|SWITCH|IFS)\s*\(", re.IGNORECASE)
    if always_expand_pattern.match(formula):
        # Check if it has more than 1 argument
        match = always_expand_pattern.match(formula)
        if match:
            paren_start = match.end() - 1
            paren_end = _find_matching_paren(formula, paren_start)
            if paren_end > 0:
                args_str = formula[paren_start + 1 : paren_end]
                args = _split_arguments(args_str)
                if len(args) > 1:
                    return False  # Not simple - needs expansion

    # Length check for other formulas
    if len(formula) <= 80:
        return True

    # Check nesting depth
    depth = _count_nesting_depth(formula)
    if depth > 1:
        return False

    return True


def _normalize_whitespace(formula: str) -> str:
    """Normalize whitespace in formula, preserving content inside strings and field refs."""
    result: list[str] = []
    in_single = False
    in_double = False
    in_brace = False
    prev_was_space = False

    i = 0
    while i < len(formula):
        char = formula[i]

        # Handle escape sequences in strings
        if (in_single or in_double) and char == "\\" and i + 1 < len(formula):
            result.append(char)
            result.append(formula[i + 1])
            prev_was_space = False
            i += 2
            continue

        # Track string and brace state
        if char == "'" and not in_double and not in_brace:
            in_single = not in_single
            result.append(char)
            prev_was_space = False
        elif char == '"' and not in_single and not in_brace:
            in_double = not in_double
            result.append(char)
            prev_was_space = False
        elif char == "{" and not in_single and not in_double:
            in_brace = True
            result.append(char)
            prev_was_space = False
        elif char == "}" and not in_single and not in_double:
            in_brace = False
            result.append(char)
            prev_was_space = False
        elif in_single or in_double or in_brace:
            # Preserve content inside strings and field refs
            result.append(char)
            prev_was_space = False
        elif char in " \t\n\r":
            # Collapse whitespace outside strings/braces
            if not prev_was_space:
                result.append(" ")
                prev_was_space = True
        else:
            result.append(char)
            prev_was_space = False

        i += 1

    return "".join(result).strip()


def _format_complex(formula: str, indent: int = 0, indent_str: str = "  ") -> str:
    """Recursively format a complex formula with indentation.

    Args:
        formula: The formula string to format
        indent: Current indentation level
        indent_str: String to use for one level of indentation (default: 2 spaces)
    """
    formula = formula.strip()
    if not formula:
        return formula

    # Don't format string literals - return as-is
    if (formula.startswith('"') and formula.endswith('"')) or (formula.startswith("'") and formula.endswith("'")):
        return formula

    # Don't format field references - return as-is
    if formula.startswith("{") and formula.endswith("}"):
        return formula

    # Handle leading parentheses: (IF(...) or ((expr))
    if formula.startswith("("):
        # Find matching closing paren
        close_idx = _find_matching_paren(formula, 0)
        if close_idx == len(formula) - 1:
            # The whole expression is wrapped in parens
            inner = formula[1:-1]
            formatted_inner = _format_complex(inner, indent, indent_str)
            if "\n" in formatted_inner:
                # Multi-line inner content - format with parens on own lines
                inner_lines = formatted_inner.split("\n")
                result_lines = ["("]
                for line in inner_lines:
                    result_lines.append(f"{indent_str}{line}")
                result_lines.append(")")
                return "\n".join(result_lines)
            else:
                return f"({formatted_inner})"
        elif close_idx > 0:
            # Parens don't wrap the whole thing - format prefix and suffix
            prefix = formula[: close_idx + 1]
            suffix = formula[close_idx + 1 :].strip()
            formatted_prefix = _format_complex(prefix, indent, indent_str)
            if suffix:
                formatted_suffix = _format_complex(suffix, indent, indent_str)
                return f"{formatted_prefix} {formatted_suffix}"
            return formatted_prefix

    # Find function call pattern: NAME(
    match = re.match(r"^([A-Z_][A-Z0-9_]*)\s*\(", formula, re.IGNORECASE)
    if not match:
        # Not a function call at the start - look for embedded function calls
        # This handles cases like: {field}*IF(...) or value+FUNC(...)
        func_match = re.search(r"([A-Z_][A-Z0-9_]*)\s*\(", formula, re.IGNORECASE)
        if func_match:
            # Found a function call embedded in the expression
            func_start = func_match.start()
            prefix = formula[:func_start]
            rest = formula[func_start:]

            # Format the function call part
            formatted_rest = _format_complex(rest, indent, indent_str)

            if "\n" in formatted_rest:
                # Multi-line result - need to indent continuation lines
                rest_lines = formatted_rest.split("\n")
                result_lines = [prefix + rest_lines[0]]
                for line in rest_lines[1:]:
                    result_lines.append(line)
                return "\n".join(result_lines)
            else:
                return prefix + formatted_rest

        return formula

    func_name = match.group(1)
    paren_start = match.end() - 1  # Position of opening paren

    # Find matching closing paren
    paren_end = _find_matching_paren(formula, paren_start)
    if paren_end == -1:
        # Malformed formula, return as-is
        return formula

    # Extract arguments
    args_str = formula[paren_start + 1 : paren_end]
    suffix = formula[paren_end + 1 :].strip()  # Anything after the closing paren

    # Split arguments
    args = _split_arguments(args_str)

    # Check if any argument contains a function call
    has_nested_func = any(re.search(r"[A-Z_][A-Z0-9_]*\s*\(", arg, re.IGNORECASE) for arg in args)

    # Check if this function call should be kept on one line
    inner_content = f"{func_name}({', '.join(args)})"

    # Functions that should ALWAYS be expanded for readability
    always_expand = {"IF", "SWITCH", "IFS"}
    func_upper = func_name.upper()

    # Determine if we should expand this function
    should_expand = (
        (func_upper in always_expand and len(args) > 1)  # IF/SWITCH/IFS always expand
        or has_nested_func  # Has nested function calls
        or len(inner_content) > 50  # Too long for single line
    )

    if len(args) == 0:
        # Empty function call
        result = f"{func_name}()"
    elif not should_expand:
        # Simple, short function call
        result = inner_content
    else:
        # Format with newlines
        lines: list[str] = []
        lines.append(f"{func_name}(")
        for i, arg in enumerate(args):
            # ALWAYS recursively format arguments
            formatted_arg = _format_complex(arg, indent + 1, indent_str)
            comma = "," if i < len(args) - 1 else ""

            # Handle multi-line formatted args
            arg_lines = formatted_arg.split("\n")
            if len(arg_lines) == 1:
                lines.append(f"{indent_str}{formatted_arg}{comma}")
            else:
                # Multi-line argument - indent each line properly
                for j, arg_line in enumerate(arg_lines):
                    if j == len(arg_lines) - 1:
                        lines.append(f"{indent_str}{arg_line}{comma}")
                    else:
                        lines.append(f"{indent_str}{arg_line}")
        lines.append(")")
        result = "\n".join(lines)

    # Append suffix (e.g., operators after the function call)
    if suffix:
        formatted_suffix = _format_complex(suffix, indent, indent_str)
        if "\n" in formatted_suffix:
            result = f"{result}\n{formatted_suffix}"
        else:
            result = f"{result} {formatted_suffix}"

    return result


def format_formula(formula: str) -> str:
    """Format formula string for better readability in markdown.

    Applies newlines and indentation to complex formulas while keeping
    simple formulas on a single line.

    Args:
        formula: The Airtable formula string to format

    Returns:
        Formatted formula string suitable for markdown code blocks

    Examples:
        >>> format_formula("RECORD_ID()")
        'RECORD_ID()'

        >>> format_formula("IF({a}, {b}, {c})")
        'IF({a}, {b}, {c})'

        # Complex formulas get formatted with newlines:
        # IF({a}, IF({x}, {y}, {z}), {c}) becomes:
        # IF(
        #   {a},
        #   IF({x}, {y}, {z}),
        #   {c}
        # )
    """
    if not formula or not formula.strip():
        return formula

    try:
        # Normalize whitespace (preserve inside strings and field refs)
        normalized = _normalize_whitespace(formula)

        # Check if simple - return normalized single-line
        if _is_simple_formula(normalized):
            return normalized

        # Format complex formula
        return _format_complex(normalized)
    except Exception:
        # Fallback: return original on any error
        return formula

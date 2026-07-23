"""Shared assembler for per-field doc comments across every language target.

Each generator's `property_docstring` used to re-implement the same layout
(field name + id + primary-key/read-only tags + optional formula block).
`build_field_doc` centralizes that layout — including the Airtable field
`description` — and returns single-line strings; each writer's `doc_comment`
still owns the language's comment syntax and terminator/CR/newline hardening.

The per-language variation (inline-code markup, comment fences, prose/formula
escaping, tag label, formula truncation) is supplied by a `DocStyle`.
"""

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from .helpers import sanitize_string


class FieldLike(Protocol):
    """The subset of `meta.Field` that `build_field_doc` reads."""

    id: str
    name: str
    description: Optional[str]

    def is_computed(self) -> bool: ...

    def formula(self, *, sanitized: bool = ..., condense: bool = ..., format: bool = ...) -> str: ...


class TableLike(Protocol):
    """The subset of `meta.Table` that `build_field_doc` reads."""

    primary_field_id: str


def _identity(text: str) -> str:
    return text


@dataclass(frozen=True)
class DocStyle:
    """Per-language policy for rendering a field's doc comment.

    Attributes:
        code: Wrap the field id in the language's inline-code markup
            (e.g. `` `x` ``, ``{@code x}``, ``<c>x</c>``, ``(x)``).
        tag_code: Markup for the primary-key / read-only tags; defaults to
            `code` when omitted (Go wants plain, un-wrapped tags).
        tag_sep: Separator between the header and each tag.
        fence_open / fence_close: Delimiters around the embedded formula
            (e.g. ```` ```text ````, ``<pre>``, ``<code>``, ``\\code``); empty
            strings emit the formula with no fence (Go, plain text).
        escape: Prose escaping applied to the field name and description
            (identity, or an HTML/XML entity escaper for Javadoc / C# XML doc).
        escape_formula: Per-line escaping applied to formula lines.
        read_only_label: Label used for the computed-field tag.
        truncate_formula: Cap on embedded formula lines (None disables it).
    """

    code: Callable[[str], str]
    tag_code: Optional[Callable[[str], str]] = None
    tag_sep: str = " - "
    fence_open: str = ""
    fence_close: str = ""
    escape: Callable[[str], str] = _identity
    escape_formula: Callable[[str], str] = _identity
    read_only_label: str = "Read-Only"
    truncate_formula: Optional[int] = 15


def build_field_doc(field: FieldLike, table: TableLike, style: DocStyle) -> list[str]:
    """Build the ordered doc-comment lines for an Airtable field (metadata first).

    Layout (each block emitted only when it has content)::

        <name> <code(id)> [ - <tag_code(Primary Key)>] [ - <tag_code(Read-Only)>]

        <description line 1>
        <description line 2...>

        <fence_open>
        <formula line 1...>
        <fence_close>

    Returned strings are single-line: the description is split on newlines here,
    and the caller's `doc_comment` applies comment syntax plus terminator/CR
    hardening.
    """
    tag_code = style.tag_code or style.code

    header = f"{style.escape(sanitize_string(field.name))} {style.code(field.id)}"

    tags: list[str] = []
    if field.id == table.primary_field_id:
        tags.append(tag_code("Primary Key"))
    if field.is_computed():
        tags.append(tag_code(style.read_only_label))
    if tags:
        header += style.tag_sep + style.tag_sep.join(tags)

    lines: list[str] = [header]

    description = (field.description or "").strip()
    if description:
        lines.append("")
        lines.extend(style.escape(description).split("\n"))

    formula = field.formula(sanitized=True, condense=True)
    if formula:
        formula_lines = field.formula(sanitized=True, format=True).splitlines()
        if style.truncate_formula is not None and len(formula_lines) > style.truncate_formula:
            formula_lines = formula_lines[: style.truncate_formula] + ["… (truncated)"]
        lines.append("")
        if style.fence_open:
            lines.append(style.fence_open)
        lines.extend(style.escape_formula(line) for line in formula_lines)
        if style.fence_close:
            lines.append(style.fence_close)

    return lines

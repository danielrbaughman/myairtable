"""C#-specific writer helpers.

Modeled after WriteToJavaFile, but emits C# syntax: file-scoped `namespace`
declarations, `using` directives, `/// <summary>` XML doc comments, `[Attribute]`
lines, and class/record/enum declarations. One public type per file is a C#
convention (not a hard requirement, but matches the other one-type-per-file
targets), so each generated file opens exactly one top-level type.

Unlike Java (which has no identifier-escape mechanism and renames reserved words
with a `_` suffix), C# supports verbatim identifiers: a reserved word is escaped
by prefixing `@` (`class` -> `@class`), which keeps the logical name intact.
Because generated members are PascalCase (and C# keywords are lowercase), the
escape rarely triggers in practice; it is a safety net for lowercase positions.
"""

import re
from pathlib import Path
from typing import ClassVar

from pydantic.alias_generators import to_pascal

from ..meta import Field, Table
from .field_doc import DocStyle, build_field_doc
from .helpers import sanitize_property_name
from .write_to_file import WriteToFile

# C# reserved keywords (ECMA-334 §6.4.4). These can never be bare identifiers and
# are escaped with a leading `@` (verbatim identifier). Contextual keywords
# (`add`, `async`, `await`, `get`, `set`, `value`, `var`, `record`, `nameof`, ...)
# are legal identifiers and are deliberately NOT included.
_CSHARP_KEYWORDS = frozenset(
    {
        "abstract",
        "as",
        "base",
        "bool",
        "break",
        "byte",
        "case",
        "catch",
        "char",
        "checked",
        "class",
        "const",
        "continue",
        "decimal",
        "default",
        "delegate",
        "do",
        "double",
        "else",
        "enum",
        "event",
        "explicit",
        "extern",
        "false",
        "finally",
        "fixed",
        "float",
        "for",
        "foreach",
        "goto",
        "if",
        "implicit",
        "in",
        "int",
        "interface",
        "internal",
        "is",
        "lock",
        "long",
        "namespace",
        "new",
        "null",
        "object",
        "operator",
        "out",
        "override",
        "params",
        "private",
        "protected",
        "public",
        "readonly",
        "ref",
        "return",
        "sbyte",
        "sealed",
        "short",
        "sizeof",
        "stackalloc",
        "static",
        "string",
        "struct",
        "switch",
        "this",
        "throw",
        "true",
        "try",
        "typeof",
        "uint",
        "ulong",
        "unchecked",
        "unsafe",
        "ushort",
        "using",
        "virtual",
        "void",
        "volatile",
        "while",
    }
)


def _csharp_ident(name: str) -> str:
    """Ensure a name is a valid C# identifier.

    Reserved keywords are escaped with a leading `@` (verbatim identifier:
    `class` -> `@class`). Wire-format correctness is unaffected: the Airtable
    field ID always travels in `[JsonPropertyName(...)]`.
    """
    if name in _CSHARP_KEYWORDS:
        return f"@{name}"
    return name


def _csharp_string_literal(text: str) -> str:
    """Escape text for inclusion in a regular double-quoted C# string literal.

    Escapes the backslash FIRST (so later escapes aren't double-escaped), then
    the quote and the control characters Airtable names/descriptions can carry.
    A regular `"..."` literal does not interpret `$` or `{`, so those are left
    alone (only interpolated `$"..."` strings would need brace doubling).
    """
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def _xmldoc_escape(text: str) -> str:
    """Escape text for safe inclusion in a C# XML doc comment.

    XML doc comments are parsed as XML, so `&`, `<`, and `>` in Airtable names,
    descriptions, and formulas must be entity-escaped. A literal `--` is illegal
    inside an XML comment body and would break the doc, so it is neutralised to
    `- -`. The `&` replacement runs first so the entities it introduces aren't
    re-escaped.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("--", "- -")


def _choice_to_entry(choice: str) -> str:
    """Convert an Airtable select choice to a C# enum member name (PascalCase).

    C# enum members are conventionally PascalCase. Falls back to `Empty` for
    names that sanitize to nothing; collisions (including multiple `Empty`
    fallbacks) are disambiguated later by the generator's dedup pass. The raw
    choice string is carried by the generated per-enum JsonConverter, not by the
    member itself.
    """
    text = sanitize_property_name(choice)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "Empty"
    text = text.replace(" ", "_")
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return "Empty"
    # C# identifiers cannot start with a digit.
    if text[0].isdigit():
        text = f"N_{text}"
    pascal = to_pascal(text)
    return pascal or "Empty"


class WriteToCSharpFile(WriteToFile):
    """C#-aware writer with `#region` markers, `/// <summary>` XML doc comments,
    and helpers for emitting namespace/using/class/record/enum declarations.

    Usage mirrors WriteToJavaFile (context manager; buffer-then-write).
    """

    def __init__(self, path: Path):
        super().__init__(path=path, language="csharp")

    # ---- namespace / usings -------------------------------------------------
    def namespace_decl(self, name: str = "MyAirtable"):
        """Write a file-scoped `namespace <name>;` — all files share one namespace.

        C# decouples namespace from directory, so every generated and static file
        declares the same `MyAirtable` namespace regardless of folder.
        """
        self.line(f"namespace {name};")

    def using_stmt(self, namespace: str):
        """Write `using <namespace>;`."""
        self.line(f"using {namespace};")

    # ---- regions / markers --------------------------------------------------
    def region(self, text: str, indent: int = 0):
        """Emit `#region text` — C# native folding directive."""
        self.line_indented(f"#region {text}", indent)

    def endregion(self, indent: int = 0):
        """Emit `#endregion`."""
        self.line_indented("#endregion", indent)

    # ---- comments -----------------------------------------------------------
    def doc_comment(self, text: str | list[str], indent: int = 0):
        """Write a `/// <summary> ... </summary>` XML doc block.

        Each line is `///`-prefixed. Embedded newlines split into separate doc
        lines. Callers that embed raw Airtable text escape it with
        `_xmldoc_escape()` first; this method does not re-escape (so `<c>`/`<code>`
        markup passes through), but it does neutralise a literal `--` and strip
        bare carriage returns so the block can't be broken by hostile content.
        """
        raw_lines = text if isinstance(text, list) else [text]
        lines: list[str] = []
        for raw in raw_lines:
            cleaned = raw.replace(chr(13), "").replace("--", "- -")
            lines.extend(cleaned.split("\n"))
        if len(lines) == 1:
            self.line_indented(f"/// <summary>{lines[0]}</summary>", indent)
            return
        self.line_indented("/// <summary>", indent)
        for line in lines:
            self.line_indented(f"/// {line}".rstrip(), indent)
        self.line_indented("/// </summary>", indent)

    def comment(self, text: str, indent: int = 0):
        """Write `// text`."""
        self.line_indented(f"// {text}", indent)

    # ---- attributes ---------------------------------------------------------
    def attribute(self, attr: str, indent: int = 0):
        """Write an attribute line like `[JsonIgnore]` or `[JsonInclude]`."""
        if not attr.startswith("["):
            attr = f"[{attr}]"
        self.line_indented(attr, indent)

    def json_property_name(self, raw: str, indent: int = 0):
        """Write `[JsonPropertyName("raw")]`, escaping the raw value as a C# string literal."""
        escaped = _csharp_string_literal(raw)
        self.line_indented(f'[JsonPropertyName("{escaped}")]', indent)

    # ---- declarations -------------------------------------------------------
    def class_open(
        self,
        name: str,
        base: str | None = None,
        interfaces: list[str] | None = None,
        modifiers: list[str] | None = None,
        indent: int = 0,
    ):
        """Open a class declaration. Caller must emit close().

        `modifiers` defaults to ["public", "sealed"] for top-level generated types.
        `base` (a base class) is emitted before any interfaces in the base list.
        """
        self._type_open("class", name, base, interfaces, modifiers if modifiers is not None else ["public", "sealed"], indent)

    def record_open(
        self,
        name: str,
        base: str | None = None,
        interfaces: list[str] | None = None,
        modifiers: list[str] | None = None,
        indent: int = 0,
    ):
        """Open a record declaration (immutable carrier / sum-type case)."""
        self._type_open("record", name, base, interfaces, modifiers if modifiers is not None else ["public", "sealed"], indent)

    def enum_open(self, name: str, indent: int = 0):
        """Open an enum declaration."""
        self._type_open("enum", name, None, None, ["public"], indent)

    def _type_open(
        self,
        kind: str,
        name: str,
        base: str | None,
        interfaces: list[str] | None,
        modifiers: list[str],
        indent: int,
    ):
        prefix = " ".join(modifiers + [kind]) if modifiers else kind
        bases = ([base] if base else []) + (interfaces or [])
        inherit = f" : {', '.join(bases)}" if bases else ""
        self.line_indented(f"{prefix} {_csharp_ident(name)}{inherit}", indent)
        self.line_indented("{", indent)

    def close(self, indent: int = 0):
        """Close a brace at the given indent level."""
        self.line_indented("}", indent)

    # ---- enum entries -------------------------------------------------------
    def enum_entry(self, name: str, indent: int = 1, last: bool = False):
        """Emit an enum member. C# permits a trailing comma, so every member is
        terminated with `,` (the raw Airtable string is mapped by the generated
        per-enum JsonConverter, not an attribute on the member)."""
        del last  # C# allows a trailing comma; terminator is uniform.
        self.line_indented(f"{_csharp_ident(name)},", indent)

    # ---- property doc comments ----------------------------------------------
    DOC_STYLE: ClassVar[DocStyle] = DocStyle(
        code=lambda text: f"<c>{text}</c>",
        fence_open="<code>",
        fence_close="</code>",
        escape=_xmldoc_escape,
        escape_formula=_xmldoc_escape,
    )

    def property_docstring(self, field: Field, table: Table, indent_level: int = 1):
        """Write an XML doc comment describing an Airtable field: name, ID,
        primary-key / read-only tags, the field description, and (if present)
        the formula in a <code> block. All embedded Airtable text is
        XML-entity-escaped via `_xmldoc_escape`."""
        self.doc_comment(build_field_doc(field, table, self.DOC_STYLE), indent=indent_level)

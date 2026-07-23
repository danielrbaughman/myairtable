"""C++-specific writer helpers.

Modeled after WriteToCSharpFile, but emits C++20 syntax: `#pragma once`,
`#include` directives, a braced `namespace myairtable { ... }` block, `///`
Doxygen doc comments, and struct/class/enum-class declarations. One public type
per header matches the other one-type-per-file targets.

C++ has no identifier-escape mechanism (unlike C#'s `@`-verbatim identifiers),
so reserved words are renamed with a trailing `_` (Java-style). The reserved set
must include the alternative tokens (`and`, `or`, `not`, `xor`, ...) — they are
operators, not keywords, but are equally illegal as identifiers. Identifiers
that would collide with names reserved for the implementation (leading
underscore followed by an uppercase letter, or any double underscore) are also
normalised, since generated members land at namespace/class scope where those
patterns are UB to declare.
"""

import re
from pathlib import Path
from typing import ClassVar

from pydantic.alias_generators import to_pascal

from ..meta import Field, Table
from .field_doc import DocStyle, build_field_doc
from .helpers import sanitize_property_name
from .write_to_file import WriteToFile

# C++20 keywords (ISO/IEC 14882:2020 [lex.key]) plus the alternative tokens
# ([lex.digraph]) which are reserved in all positions. Contextual identifiers
# (`final`, `override`, `import`, `module`) are technically legal as names but
# are included defensively — a generated field named `final` would compile yet
# read as a bug to any C++ reader.
_CPP_KEYWORDS = frozenset(
    {
        # keywords
        "alignas",
        "alignof",
        "asm",
        "auto",
        "bool",
        "break",
        "case",
        "catch",
        "char",
        "char8_t",
        "char16_t",
        "char32_t",
        "class",
        "concept",
        "const",
        "consteval",
        "constexpr",
        "constinit",
        "const_cast",
        "continue",
        "co_await",
        "co_return",
        "co_yield",
        "decltype",
        "default",
        "delete",
        "do",
        "double",
        "dynamic_cast",
        "else",
        "enum",
        "explicit",
        "export",
        "extern",
        "false",
        "float",
        "for",
        "friend",
        "goto",
        "if",
        "inline",
        "int",
        "long",
        "mutable",
        "namespace",
        "new",
        "noexcept",
        "nullptr",
        "operator",
        "private",
        "protected",
        "public",
        "register",
        "reinterpret_cast",
        "requires",
        "return",
        "short",
        "signed",
        "sizeof",
        "static",
        "static_assert",
        "static_cast",
        "struct",
        "switch",
        "template",
        "this",
        "thread_local",
        "throw",
        "true",
        "try",
        "typedef",
        "typeid",
        "typename",
        "union",
        "unsigned",
        "using",
        "virtual",
        "void",
        "volatile",
        "wchar_t",
        "while",
        # alternative tokens — operators spelled as words; illegal as identifiers
        "and",
        "and_eq",
        "bitand",
        "bitor",
        "compl",
        "not",
        "not_eq",
        "or",
        "or_eq",
        "xor",
        "xor_eq",
        # contextual identifiers, escaped defensively
        "final",
        "override",
        "import",
        "module",
    }
)


def _cpp_ident(name: str) -> str:
    """Ensure a name is a valid, non-reserved C++ identifier.

    Reserved words (keywords + alternative tokens) get a trailing `_` (C++ has
    no verbatim-identifier escape). Implementation-reserved patterns are
    normalised: runs of `__` collapse to `_`, and a leading underscore is
    stripped (with an `n` prefix restoring validity if that exposes a digit or
    empties the name). Wire-format correctness is unaffected: the Airtable field
    ID always travels in the generated serialization code, not the identifier.
    """
    # Collapse double underscores (reserved anywhere in the identifier).
    name = re.sub(r"__+", "_", name)
    # A leading underscore is reserved at global scope (and `_X` everywhere).
    name = name.lstrip("_")
    if not name or name[0].isdigit():
        name = f"n_{name}" if name else "n"
    if name in _CPP_KEYWORDS:
        return f"{name}_"
    return name


def _cpp_string_literal(text: str) -> str:
    """Escape text for inclusion in a double-quoted C++ string literal.

    Escapes the backslash FIRST (so later escapes aren't double-escaped), then
    the quote and the control characters Airtable names/descriptions can carry.
    Trigraphs were removed in C++17, so `??` sequences need no special care.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def _cppdoc_escape(text: str) -> str:
    """Sanitise text for a `///` Doxygen line comment.

    Line comments end only at a newline, so the single hazard is an embedded
    newline or carriage return breaking out of the comment; both are handled by
    the writer splitting on `\\n` and this helper dropping bare `\\r`.
    """
    return text.replace(chr(13), "")


def _choice_to_entry(choice: str) -> str:
    """Convert an Airtable select choice to a C++ enum-class member (PascalCase).

    Mirrors the C#/Java `_choice_to_entry` port: PascalCase entries, `Empty`
    fallback for names that sanitize to nothing, `N_` prefix when the name would
    start with a digit. Collisions are disambiguated by the generator's dedup
    pass; the raw choice string is carried by the generated per-enum
    `to_json`/`from_json`, not by the member itself.
    """
    text = sanitize_property_name(choice)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "Empty"
    text = text.replace(" ", "_")
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return "Empty"
    # C++ identifiers cannot start with a digit.
    if text[0].isdigit():
        text = f"N_{text}"
    pascal = to_pascal(text)
    return _cpp_ident(pascal or "Empty")


class WriteToCppFile(WriteToFile):
    """C++-aware writer with `#pragma once`, `#include` helpers, a braced
    namespace block, `///` Doxygen doc comments, and struct/class/enum-class
    declaration helpers.

    Usage mirrors WriteToCSharpFile (context manager; buffer-then-write).
    """

    def __init__(self, path: Path):
        super().__init__(path=path, language="cpp")

    # ---- preamble -------------------------------------------------------------
    def pragma_once(self):
        """Write `#pragma once` — universally supported, terser than guards."""
        self.line("#pragma once")

    def include_system(self, header: str):
        """Write `#include <header>`."""
        self.line(f"#include <{header}>")

    def include_local(self, path: str):
        """Write `#include "path"` (relative to the including file / output root)."""
        self.line(f'#include "{path}"')

    # ---- namespace ------------------------------------------------------------
    def namespace_open(self, name: str = "myairtable"):
        """Open `namespace <name> {` — all files share one flat namespace.

        C++ decouples namespace from directory, so every generated and static
        file declares the same `myairtable` namespace regardless of folder.
        """
        self.line(f"namespace {name} {{")

    def namespace_close(self, name: str = "myairtable"):
        """Close the namespace block with a trailing identifying comment."""
        self.line(f"}}  // namespace {name}")

    # ---- comments -------------------------------------------------------------
    def doc_comment(self, text: str | list[str], indent: int = 0):
        """Write a `///` Doxygen doc block (one `///` line per input line)."""
        raw_lines = text if isinstance(text, list) else [text]
        lines: list[str] = []
        for raw in raw_lines:
            lines.extend(_cppdoc_escape(raw).split("\n"))
        for line in lines:
            self.line_indented(f"/// {line}".rstrip(), indent)

    def comment(self, text: str, indent: int = 0):
        """Write `// text`."""
        self.line_indented(f"// {text}", indent)

    # ---- declarations ----------------------------------------------------------
    def struct_open(self, name: str, base: str | None = None, indent: int = 0):
        """Open `struct Name : Base {` (public inheritance is the struct default)."""
        inherit = f" : {base}" if base else ""
        self.line_indented(f"struct {_cpp_ident(name)}{inherit} {{", indent)

    def class_open(self, name: str, base: str | None = None, indent: int = 0):
        """Open `class Name : public Base {`."""
        inherit = f" : public {base}" if base else ""
        self.line_indented(f"class {_cpp_ident(name)}{inherit} {{", indent)

    def enum_class_open(self, name: str, indent: int = 0):
        """Open `enum class Name {`."""
        self.line_indented(f"enum class {_cpp_ident(name)} {{", indent)

    def close(self, indent: int = 0, semicolon: bool = True):
        """Close a brace; type declarations need the trailing `;`."""
        self.line_indented("};" if semicolon else "}", indent)

    # ---- enum entries -----------------------------------------------------------
    def enum_entry(self, name: str, indent: int = 1, last: bool = False):
        """Emit an enum-class member. C++ permits a trailing comma, so every
        member is terminated with `,` (the raw Airtable string is mapped by the
        generated per-enum `to_json`/`from_json`, not by the member)."""
        del last  # C++ allows a trailing comma; terminator is uniform.
        self.line_indented(f"{_cpp_ident(name)},", indent)

    # ---- property doc comments -----------------------------------------------------
    DOC_STYLE: ClassVar[DocStyle] = DocStyle(
        code=lambda text: f"`{text}`",
        fence_open="\\code",
        fence_close="\\endcode",
    )

    def property_docstring(self, field: Field, table: Table, indent_level: int = 1):
        """Write a Doxygen doc comment describing an Airtable field: name, ID,
        primary-key / read-only tags, the field description, and (if present)
        the formula in a ``\\code ... \\endcode`` block."""
        self.doc_comment(build_field_doc(field, table, self.DOC_STYLE), indent=indent_level)

"""Swift-specific writer helpers.

Modeled after WriteToRustFile, but emits Swift syntax (// MARK: regions,
/// doc comments, @Attribute annotations, struct/class/enum declarations).
"""

import re
from pathlib import Path

from pydantic.alias_generators import to_pascal

from ..meta import Field, Table
from .helpers import sanitize_property_name, sanitize_string
from .write_to_file import WriteToFile

# Swift reserved words that need backtick-quoting when used as identifiers.
# Source: Swift Language Reference — "Keywords and Punctuation".
_SWIFT_KEYWORDS = frozenset(
    {
        # Declarations
        "associatedtype",
        "class",
        "deinit",
        "enum",
        "extension",
        "fileprivate",
        "func",
        "import",
        "init",
        "inout",
        "internal",
        "let",
        "open",
        "operator",
        "private",
        "precedencegroup",
        "protocol",
        "public",
        "rethrows",
        "static",
        "struct",
        "subscript",
        "typealias",
        "var",
        # Statements
        "break",
        "case",
        "catch",
        "continue",
        "default",
        "defer",
        "do",
        "else",
        "fallthrough",
        "for",
        "guard",
        "if",
        "in",
        "repeat",
        "return",
        "throw",
        "switch",
        "where",
        "while",
        # Expressions and types
        "Any",
        "as",
        "false",
        "is",
        "nil",
        "self",
        "Self",
        "super",
        "throws",
        "true",
        "try",
        # Contextual but commonly problematic
        "async",
        "await",
        "actor",
        "some",
        "any",
    }
)


def _swift_ident(name: str) -> str:
    """Ensure a name is a valid Swift identifier, using `backtick` escape for keywords."""
    if name in _SWIFT_KEYWORDS:
        return f"`{name}`"
    return name


def _choice_to_case(choice: str) -> str:
    """Convert an Airtable select choice to a Swift enum case name (lowerCamelCase).

    Swift enum cases are lowerCamelCase by convention (SE-0006). Falls back to
    `case1`, `case2`... for names that sanitize to empty.
    """
    text = sanitize_property_name(choice)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "empty"
    text = text.replace(" ", "_").lower()
    text = re.sub(r"_+", "_", text)
    text = text.lstrip("_").rstrip("_")
    if not text:
        return "empty"
    # Swift identifiers can start with underscores but not digits.
    if text[0].isdigit():
        text = f"n_{text}"
    # to_pascal then lowercase the first letter for lowerCamelCase.
    pascal = to_pascal(text)
    camel = pascal[0].lower() + pascal[1:] if pascal else "empty"
    return _swift_ident(camel)


class WriteToSwiftFile(WriteToFile):
    """Swift-aware writer with // MARK: regions, /// doc comments, and
    helpers for emitting struct/class/enum/func declarations.

    Usage mirrors WriteToRustFile (context manager; buffer-then-write).
    """

    def __init__(self, path: Path):
        super().__init__(path=path, language="swift")

    # ---- regions / markers ------------------------------------------------
    def mark(self, text: str, indent: int = 0):
        """Emit `// MARK: text` — Xcode navigator landmark."""
        self.line_indented(f"// MARK: {text}", indent)

    def mark_section(self, text: str, indent: int = 0):
        """Emit `// MARK: - text` — Xcode navigator landmark with separator."""
        self.line_indented(f"// MARK: - {text}", indent)

    # Alias the region/endregion API from WriteToRustFile for parity with
    # existing generator call sites. In Swift these collapse to MARK comments;
    # endregion is a no-op blank line since Swift has no explicit terminator.
    def region(self, text: str, indent: int = 0):
        self.mark_section(text, indent)

    def endregion(self):
        self.line_empty()

    # ---- comments ---------------------------------------------------------
    def doc_comment(self, text: str | list[str], indent: int = 0):
        """Write /// doc comment(s). Strips bare \\r that Airtable descriptions may contain."""
        lines = text if isinstance(text, list) else [text]
        for line in lines:
            self.line_indented(f"/// {line.replace(chr(13), '')}", indent)

    def comment(self, text: str, indent: int = 0):
        """Write `// text`."""
        self.line_indented(f"// {text}", indent)

    # ---- attributes / annotations ----------------------------------------
    def attribute(self, attr: str, indent: int = 0):
        """Write an attribute line like `@Observable` or `@available(iOS 17, *)`."""
        if not attr.startswith("@"):
            attr = f"@{attr}"
        self.line_indented(attr, indent)

    # ---- declarations -----------------------------------------------------
    def import_stmt(self, module: str):
        """Write `import <module>`."""
        self.line(f"import {module}")

    def struct_open(self, name: str, conformances: list[str] | None = None, public: bool = True, indent: int = 0):
        """Open a struct declaration. Caller must emit struct_close."""
        self._type_open("struct", name, conformances, public, indent)

    def class_open(
        self,
        name: str,
        conformances: list[str] | None = None,
        public: bool = True,
        final: bool = True,
        indent: int = 0,
    ):
        """Open a class declaration. Caller must emit struct_close (or close)."""
        prefix_parts: list[str] = []
        if public:
            prefix_parts.append("public")
        if final:
            prefix_parts.append("final")
        prefix_parts.append("class")
        prefix = " ".join(prefix_parts)
        conf = f": {', '.join(conformances)}" if conformances else ""
        self.line_indented(f"{prefix} {_swift_ident(name)}{conf} {{", indent)

    def enum_open(
        self,
        name: str,
        raw_type: str | None = None,
        conformances: list[str] | None = None,
        public: bool = True,
        indent: int = 0,
    ):
        """Open an enum declaration with an optional raw type and conformances."""
        conf_list: list[str] = []
        if raw_type:
            conf_list.append(raw_type)
        if conformances:
            conf_list.extend(conformances)
        self._type_open("enum", name, conf_list or None, public, indent)

    def actor_open(self, name: str, conformances: list[str] | None = None, public: bool = True, indent: int = 0):
        """Open an actor declaration."""
        self._type_open("actor", name, conformances, public, indent)

    def protocol_open(self, name: str, conformances: list[str] | None = None, public: bool = True, indent: int = 0):
        """Open a protocol declaration."""
        self._type_open("protocol", name, conformances, public, indent)

    def _type_open(self, kind: str, name: str, conformances: list[str] | None, public: bool, indent: int):
        prefix = "public " if public else ""
        conf = f": {', '.join(conformances)}" if conformances else ""
        self.line_indented(f"{prefix}{kind} {_swift_ident(name)}{conf} {{", indent)

    def close(self, indent: int = 0):
        """Close a brace at the given indent level."""
        self.line_indented("}", indent)

    # ---- properties -------------------------------------------------------
    def let_property(self, name: str, type: str, default: str | None = None, public: bool = True, indent: int = 1):
        """Emit `public let name: type [= default]`."""
        prefix = "public " if public else ""
        suffix = f" = {default}" if default is not None else ""
        self.line_indented(f"{prefix}let {_swift_ident(name)}: {type}{suffix}", indent)

    def var_property(self, name: str, type: str, default: str | None = None, public: bool = True, indent: int = 1):
        """Emit `public var name: type [= default]`."""
        prefix = "public " if public else ""
        suffix = f" = {default}" if default is not None else ""
        self.line_indented(f"{prefix}var {_swift_ident(name)}: {type}{suffix}", indent)

    def static_let(self, name: str, type: str, value: str, public: bool = True, indent: int = 1):
        """Emit `public static let name: type = value`."""
        prefix = "public " if public else ""
        self.line_indented(f"{prefix}static let {_swift_ident(name)}: {type} = {value}", indent)

    # ---- enum cases -------------------------------------------------------
    def enum_case(self, name: str, raw_value: str | None = None, indent: int = 1):
        """Emit `case name [= "raw"]`."""
        suffix = f' = "{raw_value}"' if raw_value is not None else ""
        self.line_indented(f"case {_swift_ident(name)}{suffix}", indent)

    # ---- property doc comments -------------------------------------------
    def property_docstring(self, field: Field, table: Table, indent_level: int = 1):
        """Write a /// doc comment describing an Airtable field.

        Matches the style of WriteToRustFile.property_docstring: includes the
        field's Airtable name and ID, primary-key / read-only tags, and (if
        present) the field's formula as a fenced code block.
        """
        base_info = f"{sanitize_string(field.name)} `{field.id}`"

        tags: list[str] = []
        if field.id == table.primary_field_id:
            tags.append("`Primary Key`")
        if field.is_computed():
            tags.append("`Read-Only`")
        if tags:
            base_info += " - " + " - ".join(tags)

        formula = field.formula(sanitized=True, condense=True)
        if formula:
            lines: list[str] = [base_info, ""]
            lines.append("```text")
            for line in field.formula(sanitized=True, format=True).splitlines():
                lines.append(line)
            lines.append("```")
            self.doc_comment(lines, indent=indent_level)
        else:
            self.doc_comment(base_info, indent=indent_level)

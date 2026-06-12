"""Kotlin-specific writer helpers.

Modeled after WriteToSwiftFile, but emits Kotlin syntax (// region markers,
/** KDoc */ comments, @Annotation lines, class/object/enum/interface declarations).
"""

import re
from pathlib import Path

from pydantic.alias_generators import to_pascal

from ..meta import Field, Table
from .helpers import sanitize_property_name, sanitize_string
from .write_to_file import WriteToFile

# Kotlin HARD keywords that need backtick-quoting when used as identifiers.
# Soft/modifier keywords (get, set, by, where, field, ...) are valid identifiers
# and must NOT be escaped — backticking them is unidiomatic.
# Source: Kotlin Language Reference — "Keywords and operators".
_KOTLIN_KEYWORDS = frozenset(
    {
        "as",
        "break",
        "class",
        "continue",
        "do",
        "else",
        "false",
        "for",
        "fun",
        "if",
        "in",
        "interface",
        "is",
        "null",
        "object",
        "package",
        "return",
        "super",
        "this",
        "throw",
        "true",
        "try",
        "typealias",
        "typeof",
        "val",
        "var",
        "when",
        "while",
    }
)


def _kotlin_ident(name: str) -> str:
    """Ensure a name is a valid Kotlin identifier, using `backtick` escape for hard keywords."""
    if name in _KOTLIN_KEYWORDS:
        return f"`{name}`"
    return name


def _kotlin_string_literal(text: str) -> str:
    """Escape text for inclusion in a double-quoted Kotlin string literal.

    The single shared Kotlin escaper — used for @SerialName values here and for
    every generated string literal in the Kotlin generator. Escapes the
    backslash FIRST (so later escapes aren't double-escaped), then the quote,
    the `$` template marker, and the control characters Airtable names and
    descriptions can carry.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def _choice_to_entry(choice: str) -> str:
    """Convert an Airtable select choice to a Kotlin enum entry name (SCREAMING_SNAKE_CASE).

    Kotlin enum entries are conventionally SCREAMING_SNAKE_CASE (official style
    guide). Falls back to `EMPTY` for names that sanitize to nothing; collisions
    (including multiple `EMPTY` fallbacks) are disambiguated later by the
    generator's dedup pass. The raw choice string is carried by @SerialName.
    """
    text = sanitize_property_name(choice)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "EMPTY"
    text = text.replace(" ", "_")
    # Split camelCase boundaries before uppercasing so "openInvoices" -> OPEN_INVOICES.
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = re.sub(r"_+", "_", text).strip("_").upper()
    if not text:
        return "EMPTY"
    # Kotlin identifiers cannot start with a digit.
    if text[0].isdigit():
        text = f"N_{text}"
    return text


def _choice_to_camel(choice: str) -> str:
    """Convert an Airtable name to lowerCamelCase (for properties derived from names)."""
    text = sanitize_property_name(choice)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "empty"
    text = re.sub(r"_+", "_", text.replace(" ", "_")).strip("_")
    if not text:
        return "empty"
    if text[0].isdigit():
        text = f"n_{text}"
    pascal = to_pascal(text)
    camel = pascal[0].lower() + pascal[1:] if pascal else "empty"
    return _kotlin_ident(camel)


class WriteToKotlinFile(WriteToFile):
    """Kotlin-aware writer with // region markers, /** KDoc */ comments, and
    helpers for emitting class/object/enum/interface/fun declarations.

    Usage mirrors WriteToSwiftFile (context manager; buffer-then-write).
    """

    def __init__(self, path: Path):
        super().__init__(path=path, language="kotlin")

    # ---- package / imports --------------------------------------------------
    def package_decl(self, name: str = "myairtable"):
        """Write `package <name>` — all static + generated files share one flat package."""
        self.line(f"package {name}")

    def import_stmt(self, fqname: str):
        """Write `import <fully.qualified.Name>`."""
        self.line(f"import {fqname}")

    # ---- regions / markers --------------------------------------------------
    def region(self, text: str, indent: int = 0):
        """Emit `// region text` — IntelliJ folding landmark."""
        self.line_indented(f"// region {text}", indent)

    def endregion(self, indent: int = 0):
        """Emit `// endregion`."""
        self.line_indented("// endregion", indent)

    # ---- comments -----------------------------------------------------------
    def doc_comment(self, text: str | list[str], indent: int = 0):
        """Write a /** KDoc */ block.

        Sanitizes each line so the block can't be broken by hostile content:
        strips bare \\r (Airtable descriptions may contain them), neutralizes
        `*/` (which would terminate the KDoc early), and splits embedded
        newlines into separate comment lines.
        """
        raw_lines = text if isinstance(text, list) else [text]
        lines: list[str] = []
        for raw in raw_lines:
            cleaned = raw.replace(chr(13), "").replace("*/", "* /")
            lines.extend(cleaned.split("\n"))
        if len(lines) == 1:
            self.line_indented(f"/** {lines[0]} */", indent)
            return
        self.line_indented("/**", indent)
        for line in lines:
            self.line_indented(f" * {line}".rstrip(), indent)
        self.line_indented(" */", indent)

    def comment(self, text: str, indent: int = 0):
        """Write `// text`."""
        self.line_indented(f"// {text}", indent)

    # ---- annotations ----------------------------------------------------------
    def annotation(self, ann: str, indent: int = 0):
        """Write an annotation line like `@Serializable` or `@SerialName("fld...")`."""
        if not ann.startswith("@"):
            ann = f"@{ann}"
        self.line_indented(ann, indent)

    def serial_name(self, raw: str, indent: int = 0):
        """Write `@SerialName("raw")`, escaping the raw value as a Kotlin string literal."""
        escaped = _kotlin_string_literal(raw)
        self.line_indented(f'@SerialName("{escaped}")', indent)

    # ---- declarations ---------------------------------------------------------
    def class_open(self, name: str, supertypes: list[str] | None = None, modifiers: list[str] | None = None, indent: int = 0):
        """Open a class declaration (no primary constructor). Caller must emit close()."""
        self._type_open("class", name, supertypes, modifiers, indent)

    def data_class_header(self, name: str, modifiers: list[str] | None = None, indent: int = 0):
        """Emit `data class Name(` — caller writes constructor params then closes with `)`."""
        prefix = " ".join((modifiers or []) + ["data class"])
        self.line_indented(f"{prefix} {_kotlin_ident(name)}(", indent)

    def object_open(self, name: str, supertypes: list[str] | None = None, indent: int = 0):
        """Open an `object` declaration."""
        self._type_open("object", name, supertypes, None, indent)

    def companion_object_open(self, indent: int = 1):
        """Open a `companion object {` block."""
        self.line_indented("companion object {", indent)

    def interface_open(self, name: str, supertypes: list[str] | None = None, indent: int = 0):
        """Open an interface declaration."""
        self._type_open("interface", name, supertypes, None, indent)

    def enum_class_open(self, name: str, supertypes: list[str] | None = None, indent: int = 0):
        """Open an enum class declaration."""
        self._type_open("enum class", name, supertypes, None, indent)

    def _type_open(self, kind: str, name: str, supertypes: list[str] | None, modifiers: list[str] | None, indent: int):
        prefix = " ".join((modifiers or []) + [kind])
        conf = f" : {', '.join(supertypes)}" if supertypes else ""
        self.line_indented(f"{prefix} {_kotlin_ident(name)}{conf} {{", indent)

    def close(self, indent: int = 0):
        """Close a brace at the given indent level."""
        self.line_indented("}", indent)

    # ---- properties -----------------------------------------------------------
    def val_property(self, name: str, type: str, default: str | None = None, modifiers: list[str] | None = None, indent: int = 1):
        """Emit `val name: type [= default]` (public by default in Kotlin)."""
        prefix = " ".join((modifiers or []) + ["val"])
        suffix = f" = {default}" if default is not None else ""
        self.line_indented(f"{prefix} {_kotlin_ident(name)}: {type}{suffix}", indent)

    def var_property(self, name: str, type: str, default: str | None = None, modifiers: list[str] | None = None, indent: int = 1):
        """Emit `var name: type [= default]`."""
        prefix = " ".join((modifiers or []) + ["var"])
        suffix = f" = {default}" if default is not None else ""
        self.line_indented(f"{prefix} {_kotlin_ident(name)}: {type}{suffix}", indent)

    def const_val(self, name: str, type: str, value: str, indent: int = 1):
        """Emit `const val name: type = value` (compile-time constant inside an object)."""
        self.line_indented(f"const val {_kotlin_ident(name)}: {type} = {value}", indent)

    # ---- constructor parameters (for class headers spanning multiple lines) ----
    def ctor_param(self, name: str, type: str, keyword: str, default: str | None = None, indent: int = 1, last: bool = False):
        """Emit a primary-constructor property param: `[val|var] name: type [= default],`."""
        suffix = f" = {default}" if default is not None else ""
        comma = "" if last else ","
        self.line_indented(f"{keyword} {_kotlin_ident(name)}: {type}{suffix}{comma}", indent)

    # ---- functions --------------------------------------------------------------
    def fun_def(self, signature: str, indent: int = 1):
        """Emit a function header `fun signature {` — caller provides body + close()."""
        self.line_indented(f"fun {signature} {{", indent)

    # ---- enum entries ------------------------------------------------------------
    def enum_entry(self, name: str, serial_name: str | None = None, indent: int = 1, last: bool = False):
        """Emit an enum entry, optionally preceded by @SerialName("raw")."""
        if serial_name is not None:
            self.serial_name(serial_name, indent)
        self.line_indented(f"{_kotlin_ident(name)}{';' if last else ','}", indent)

    # ---- property doc comments -----------------------------------------------------
    def property_docstring(self, field: Field, table: Table, indent_level: int = 1):
        """Write a KDoc comment describing an Airtable field.

        Matches the style of WriteToSwiftFile.property_docstring: includes the
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

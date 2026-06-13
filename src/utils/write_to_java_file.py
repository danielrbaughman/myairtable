"""Java-specific writer helpers.

Modeled after WriteToKotlinFile, but emits Java syntax (semicolon-terminated
package/import statements, /** Javadoc */ comments, @Annotation lines,
class/interface/enum declarations). One public type per file is a Java
language requirement, so each generated file opens exactly one top-level type.
"""

import re
from pathlib import Path

from ..meta import Field, Table
from .helpers import sanitize_property_name, sanitize_string
from .write_to_file import WriteToFile

# Java reserved words that can NEVER be identifiers, plus the boolean/null
# literals and `_` (a keyword since Java 9). Unlike Kotlin/Swift, Java has no
# escape mechanism (no backticks) — colliding names are renamed with a `_`
# suffix instead. `var` and `yield` are restricted identifiers (illegal as
# type names / unqualified method invocations respectively) and are included
# defensively. Contextual keywords (record, sealed, permits, ...) are legal
# identifiers and are NOT renamed.
# Source: JLS §3.9 (Java SE 21).
_JAVA_KEYWORDS = frozenset(
    {
        "abstract",
        "assert",
        "boolean",
        "break",
        "byte",
        "case",
        "catch",
        "char",
        "class",
        "const",
        "continue",
        "default",
        "do",
        "double",
        "else",
        "enum",
        "extends",
        "final",
        "finally",
        "float",
        "for",
        "goto",
        "if",
        "implements",
        "import",
        "instanceof",
        "int",
        "interface",
        "long",
        "native",
        "new",
        "package",
        "private",
        "protected",
        "public",
        "return",
        "short",
        "static",
        "strictfp",
        "super",
        "switch",
        "synchronized",
        "this",
        "throw",
        "throws",
        "transient",
        "try",
        "void",
        "volatile",
        "while",
        # literals — reserved, not keywords, but equally illegal as identifiers
        "true",
        "false",
        "null",
        # keyword since Java 9
        "_",
        # restricted identifiers — legal in some positions but footguns
        "var",
        "yield",
    }
)


def _java_ident(name: str) -> str:
    """Ensure a name is a valid Java identifier.

    Java has no identifier-escape mechanism, so reserved words are renamed
    with a `_` suffix (`class` -> `class_`). Wire-format correctness is
    unaffected: the Airtable field ID always travels in @JsonProperty.
    """
    if name in _JAVA_KEYWORDS:
        return f"{name}_"
    return name


def _java_string_literal(text: str) -> str:
    """Escape text for inclusion in a double-quoted Java string literal.

    The single shared Java escaper — used for @JsonProperty values and every
    generated string literal in the Java generator. Escapes the backslash
    FIRST (so later escapes aren't double-escaped), then the quote and the
    control characters Airtable names and descriptions can carry. Java has no
    `$` template marker, so unlike Kotlin `$` is left alone.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def _javadoc_escape(text: str) -> str:
    """Escape HTML-significant characters for safe inclusion in Javadoc prose.

    Javadoc is interpreted as HTML, so `<`, `>`, and `&` in Airtable names,
    descriptions, and formulas must be entity-escaped ({@code ...} is NOT used
    for formula bodies because Airtable `{Field}` references can carry
    unbalanced braces, which break the inline tag).
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _choice_to_entry(choice: str) -> str:
    """Convert an Airtable select choice to a Java enum constant name (SCREAMING_SNAKE_CASE).

    Java enum constants are conventionally SCREAMING_SNAKE_CASE. Falls back to
    `EMPTY` for names that sanitize to nothing; collisions (including multiple
    `EMPTY` fallbacks) are disambiguated later by the generator's dedup pass.
    The raw choice string is carried by the enum's value field (@JsonValue).
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
    # Java identifiers cannot start with a digit.
    if text[0].isdigit():
        text = f"N_{text}"
    return text


class WriteToJavaFile(WriteToFile):
    """Java-aware writer with // region markers, /** Javadoc */ comments, and
    helpers for emitting class/interface/enum declarations.

    Usage mirrors WriteToKotlinFile (context manager; buffer-then-write).
    """

    def __init__(self, path: Path):
        super().__init__(path=path, language="java")

    # ---- package / imports --------------------------------------------------
    def package_decl(self, name: str = "myairtable"):
        """Write `package <name>;` — all static + generated files share one flat package."""
        self.line(f"package {name};")

    def import_stmt(self, fqname: str):
        """Write `import <fully.qualified.Name>;`."""
        self.line(f"import {fqname};")

    def import_static(self, fqname: str):
        """Write `import static <fully.qualified.member>;`."""
        self.line(f"import static {fqname};")

    # ---- regions / markers --------------------------------------------------
    def region(self, text: str, indent: int = 0):
        """Emit `// region text` — IDE folding landmark."""
        self.line_indented(f"// region {text}", indent)

    def endregion(self, indent: int = 0):
        """Emit `// endregion`."""
        self.line_indented("// endregion", indent)

    # ---- comments -----------------------------------------------------------
    def doc_comment(self, text: str | list[str], indent: int = 0):
        r"""Write a /** Javadoc */ block.

        Sanitizes each line so the block can't be broken by hostile content:

        1. Doubles every backslash FIRST. `javac` runs unicode-escape
           translation (`\\uXXXX`) over the *entire* source — comments included —
           before lexing (JLS 3.3), so a name containing the literal characters
           `\\u002a\\u002f` would otherwise be reconstituted into `*/` and close
           the comment, injecting whatever follows as live source. Doubling
           turns any run of N backslashes into 2N, so the backslash before any
           `u` is always preceded by an even count and is never escape-eligible.
           (It also neutralises an innocent `\\u`-not-followed-by-hex, which is a
           hard compile error inside comments.) String literals are immune via
           `_java_string_literal`, which already doubles backslashes.
        2. Strips bare `\\r` (Airtable descriptions may contain them).
        3. Neutralises a literal `*/` (which would terminate the comment early).
        4. Splits embedded newlines into separate comment lines.

        Lines are NOT HTML-escaped here — callers that embed raw Airtable text
        use `_javadoc_escape()` first.
        """
        raw_lines = text if isinstance(text, list) else [text]
        lines: list[str] = []
        for raw in raw_lines:
            cleaned = raw.replace("\\", "\\\\").replace(chr(13), "").replace("*/", "* /")
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
        """Write an annotation line like `@JsonIgnore` or `@JsonProperty("fld...")`."""
        if not ann.startswith("@"):
            ann = f"@{ann}"
        self.line_indented(ann, indent)

    def json_property(self, raw: str, indent: int = 0):
        """Write `@JsonProperty("raw")`, escaping the raw value as a Java string literal."""
        escaped = _java_string_literal(raw)
        self.line_indented(f'@JsonProperty("{escaped}")', indent)

    # ---- declarations ---------------------------------------------------------
    def class_open(
        self,
        name: str,
        extends: str | None = None,
        implements: list[str] | None = None,
        modifiers: list[str] | None = None,
        indent: int = 0,
    ):
        """Open a class declaration. Caller must emit close().

        `modifiers` defaults to ["public", "final"] for top-level generated types.
        """
        self._type_open("class", name, extends, implements, modifiers if modifiers is not None else ["public", "final"], indent)

    def interface_open(self, name: str, extends: list[str] | None = None, modifiers: list[str] | None = None, indent: int = 0):
        """Open an interface declaration (interfaces use `extends` for supertypes)."""
        prefix = " ".join((modifiers if modifiers is not None else ["public"]) + ["interface"])
        conf = f" extends {', '.join(extends)}" if extends else ""
        self.line_indented(f"{prefix} {_java_ident(name)}{conf} {{", indent)

    def enum_open(self, name: str, implements: list[str] | None = None, indent: int = 0):
        """Open an enum declaration."""
        self._type_open("enum", name, None, implements, ["public"], indent)

    def _type_open(
        self,
        kind: str,
        name: str,
        extends: str | None,
        implements: list[str] | None,
        modifiers: list[str],
        indent: int,
    ):
        prefix = " ".join(modifiers + [kind]) if modifiers else kind
        ext = f" extends {extends}" if extends else ""
        impl = f" implements {', '.join(implements)}" if implements else ""
        self.line_indented(f"{prefix} {_java_ident(name)}{ext}{impl} {{", indent)

    def close(self, indent: int = 0):
        """Close a brace at the given indent level."""
        self.line_indented("}", indent)

    # ---- enum entries ------------------------------------------------------------
    def enum_entry(self, name: str, raw_value: str | None = None, indent: int = 1, last: bool = False):
        """Emit an enum constant, optionally with a raw-value constructor argument.

        With `raw_value`, emits `NAME("raw"),` — the generated enum carries the
        raw Airtable choice string in a constructor parameter exposed via
        @JsonValue. The final constant is terminated with `;` so the value
        field/constructor/factory can follow.
        """
        terminator = ";" if last else ","
        if raw_value is not None:
            escaped = _java_string_literal(raw_value)
            self.line_indented(f'{_java_ident(name)}("{escaped}"){terminator}', indent)
        else:
            self.line_indented(f"{_java_ident(name)}{terminator}", indent)

    # ---- property doc comments -----------------------------------------------------
    def property_docstring(self, field: Field, table: Table, indent_level: int = 1):
        """Write a Javadoc comment describing an Airtable field.

        Matches the style of WriteToKotlinFile.property_docstring: includes the
        field's Airtable name and ID, primary-key / read-only tags, and (if
        present) the field's formula in a <pre> block. Formula text is
        HTML-entity-escaped rather than wrapped in {@code} because Airtable
        `{Field}` references can carry unbalanced braces.
        """
        base_info = f"{_javadoc_escape(sanitize_string(field.name))} {{@code {field.id}}}"

        tags: list[str] = []
        if field.id == table.primary_field_id:
            tags.append("{@code Primary Key}")
        if field.is_computed():
            tags.append("{@code Read-Only}")
        if tags:
            base_info += " - " + " - ".join(tags)

        formula = field.formula(sanitized=True, condense=True)
        if formula:
            lines: list[str] = [base_info, ""]
            lines.append("<pre>")
            # Cap the embedded formula so IDE hovers stay readable; the full
            # text lives in the generated Markdown/HTML docs (myairtable-dmiw).
            formula_lines = field.formula(sanitized=True, format=True).splitlines()
            if len(formula_lines) > 15:
                formula_lines = formula_lines[:15] + ["… (truncated)"]
            lines.extend(_javadoc_escape(formula_line) for formula_line in formula_lines)
            lines.append("</pre>")
            self.doc_comment(lines, indent=indent_level)
        else:
            self.doc_comment(base_info, indent=indent_level)

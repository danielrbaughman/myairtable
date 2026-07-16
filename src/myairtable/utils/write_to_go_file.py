"""Go-specific writer helpers.

Emits idiomatic Go: `package airtable` (no semicolon), a single sorted
`import ( ... )` block, `//` line comments (Go has no block-doc HTML hazard),
struct declarations with `json:"..."` struct tags, interfaces, and typed-string
constant groups (Go has no enums).

Unlike Java/Kotlin there are no annotations: JSON field mapping is a struct tag
appended to the field line, so the central emitter here is `struct_field`. Unused
imports are a *compile error* in Go and gofmt sorts the import block, so imports
are resolved against actual body usage and emitted alphabetically (see
`resolve_imports`).
"""

import re
from pathlib import Path

from ..meta import Field, Table
from .helpers import sanitize_property_name, sanitize_string
from .write_to_file import WriteToFile

# Go's 25 reserved keywords (spec: "Keywords") plus the predeclared identifiers
# that would shadow built-in types/values if reused. Go has no identifier-escape
# mechanism, so colliding names are renamed with a trailing `_`. Exported
# (PascalCase) identifiers never collide with these lowercase names; the rename
# matters mainly for receivers, unexported fields, and the package name.
_GO_KEYWORDS = frozenset(
    {
        # keywords
        "break",
        "case",
        "chan",
        "const",
        "continue",
        "default",
        "defer",
        "else",
        "fallthrough",
        "for",
        "func",
        "go",
        "goto",
        "if",
        "import",
        "interface",
        "map",
        "package",
        "range",
        "return",
        "select",
        "struct",
        "switch",
        "type",
        "var",
        # predeclared type names
        "any",
        "bool",
        "byte",
        "comparable",
        "complex64",
        "complex128",
        "error",
        "float32",
        "float64",
        "int",
        "int8",
        "int16",
        "int32",
        "int64",
        "rune",
        "string",
        "uint",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "uintptr",
        # predeclared constants / zero value
        "true",
        "false",
        "iota",
        "nil",
        # predeclared builtins
        "append",
        "cap",
        "clear",
        "close",
        "complex",
        "copy",
        "delete",
        "imag",
        "len",
        "make",
        "max",
        "min",
        "new",
        "panic",
        "print",
        "println",
        "real",
        "recover",
    }
)


def _go_ident(name: str) -> str:
    """Ensure a name is a valid Go identifier.

    Go has no identifier-escape mechanism, so reserved/predeclared words are
    renamed with a trailing `_` (`type` -> `type_`). Wire-format correctness is
    unaffected: the Airtable field ID always travels in the `json:"..."` tag.
    """
    if name in _GO_KEYWORDS:
        return f"{name}_"
    return name


def _go_string_literal(text: str) -> str:
    r"""Escape text for a double-quoted Go string literal.

    Go double-quoted (interpreted) string literals use the same escapes as Java:
    backslash FIRST (so later escapes aren't double-escaped), then the quote and
    the control characters Airtable names/descriptions can carry. Go has no `$`
    template marker.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def _choice_to_const(choice: str) -> str:
    """Convert an Airtable select choice to a PascalCase Go constant suffix.

    Go has no enums; select options become typed-string constants named
    `{TypeName}{Suffix}`. This produces the PascalCase `Suffix`. Falls back to
    `Empty` for names that sanitize to nothing; collisions are disambiguated
    later by the generator's dedup pass. The raw choice string is the constant's
    value, so wire correctness is independent of the identifier.
    """
    text = sanitize_property_name(choice)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "Empty"
    # Split camelCase boundaries so "openInvoices" -> "open Invoices" before title-casing.
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    words = re.split(r"[\s_]+", text)
    pascal = "".join(word[:1].upper() + word[1:] for word in words if word)
    if not pascal:
        return "Empty"
    # Go identifiers cannot start with a digit.
    if pascal[0].isdigit():
        pascal = f"N{pascal}"
    return pascal


class WriteToGoFile(WriteToFile):
    """Go-aware writer: package decl, sorted import block, // comments, struct /
    interface / typed-const emitters, and struct-field-with-json-tag output.

    Usage mirrors WriteToJavaFile (context manager; buffer-then-write). Many
    files share one flat `package airtable` (Go forbids package != directory).
    """

    def __init__(self, path: Path):
        super().__init__(path=path, language="go")

    # ---- package / imports --------------------------------------------------
    def package_decl(self, name: str = "airtable"):
        """Write `package <name>` — all static + generated files share one flat package."""
        self.line(f"package {_go_ident(name)}")

    def add_go_import(self, path: str, alias: str | None = None) -> None:
        """Register a candidate stdlib import path (e.g. "encoding/json").

        The package selector token used for usage detection defaults to the last
        path segment ("encoding/json" -> "json"), which is the actual package
        name for every stdlib package this generator uses. Pass `alias` when the
        package name differs from the last path segment.
        """
        local = alias if alias is not None else path.rsplit("/", 1)[-1]
        # Reuse the base candidate machinery; render/sort happens in resolve_imports.
        self.add_import(path, [(path, local)])

    def resolve_imports(self) -> None:
        """Splice a single alphabetically-sorted `import ( ... )` block.

        Overrides the base (which renders per-group, unsorted) to satisfy gofmt:
        one block, sorted by path, only paths whose package selector is actually
        used in the body. Unused imports are a Go compile error, so usage is
        scanned exactly like the base does.
        """
        if self._resolved:
            return
        self._resolved = True
        if not self._import_groups:
            return

        marker = self._import_marker if self._import_marker is not None else 0
        body = "\n".join(self.lines[marker:])

        used_paths: set[str] = set()
        for group in self._import_groups:
            for sym in group.symbols:
                # `sym.local` is the package selector token (e.g. "json"); match `json.`
                if sym.always or re.search(rf"\b{re.escape(sym.local)}\.", body):
                    used_paths.add(group.module)

        if not used_paths:
            return

        paths = sorted(used_paths)
        if len(paths) == 1:
            rendered = [f'import "{paths[0]}"', ""]
        else:
            rendered = ["import ("]
            rendered.extend(f'\t"{path}"' for path in paths)
            rendered.extend([")", ""])

        self.lines[marker:marker] = rendered

    # ---- comments -----------------------------------------------------------
    def doc_comment(self, text: str | list[str], indent: int = 0):
        """Write `// ...` doc-comment line(s). Splits embedded newlines, strips CR.

        Go doc comments are plain text (no HTML interpretation, no `*/` hazard),
        so this is far simpler than the Java/Kotlin Javadoc emitters.
        """
        raw_lines = text if isinstance(text, list) else [text]
        for raw in raw_lines:
            cleaned = raw.replace(chr(13), "")
            for line in cleaned.split("\n"):
                self.line_indented(f"// {line}".rstrip(), indent)

    def comment(self, text: str, indent: int = 0):
        """Write `// text`."""
        self.line_indented(f"// {text}", indent)

    # ---- declarations -------------------------------------------------------
    def struct_open(self, name: str, indent: int = 0):
        """Open `type <Name> struct {`. Caller must emit close()."""
        self.line_indented(f"type {_go_ident(name)} struct {{", indent)

    def interface_open(self, name: str, indent: int = 0):
        """Open `type <Name> interface {`. Caller must emit close()."""
        self.line_indented(f"type {_go_ident(name)} interface {{", indent)

    def close(self, indent: int = 0):
        """Close a brace at the given indent level."""
        self.line_indented("}", indent)

    def struct_field(
        self,
        name: str,
        go_type: str,
        json_tag: str | None = None,
        inline_comment: str | None = None,
        indent: int = 1,
    ):
        """Emit a struct field line, optionally with a `json:"..."` tag and trailing comment.

        The Go analog of the Java `@JsonProperty` + field pair: the JSON field ID
        is a struct tag on the same line. `json_tag` is the raw tag *contents*
        (e.g. `fldXXX,omitempty`); it is wrapped in backticks here.
        """
        line = f"{_go_ident(name)} {go_type}"
        if json_tag is not None:
            line += f' `json:"{json_tag}"`'
        if inline_comment is not None:
            line += f" // {inline_comment}"
        self.line_indented(line, indent)

    # ---- typed-string constants (the Go "enum") -----------------------------
    def string_type_decl(self, name: str, indent: int = 0):
        """Emit `type <Name> string` — the underlying type for a select-option group."""
        self.line_indented(f"type {_go_ident(name)} string", indent)

    def const_block(self, entries: list[tuple[str, str]], type_name: str, indent: int = 0):
        """Emit a `const ( ... )` block of typed-string constants.

        `entries` is a list of `(const_name, raw_value)`; each renders as
        `ConstName TypeName = "raw"`. The raw value is escaped as a Go string
        literal; the const name is assumed already deduped/valid.
        """
        if not entries:
            return
        self.line_indented("const (", indent)
        for const_name, raw in entries:
            escaped = _go_string_literal(raw)
            self.line_indented(f'{_go_ident(const_name)} {_go_ident(type_name)} = "{escaped}"', indent + 1)
        self.line_indented(")", indent)

    # ---- property doc comments ----------------------------------------------
    def property_docstring(self, field: Field, table: Table, indent_level: int = 1):
        """Write a `//` doc comment describing an Airtable field.

        Includes the field's name and ID, primary-key / read-only tags, and (if
        present) the field's condensed formula. No HTML escaping or `<pre>` (Go
        doc comments are plain text).
        """
        base_info = f"{sanitize_string(field.name)} ({field.id})"

        tags: list[str] = []
        if field.id == table.primary_field_id:
            tags.append("Primary Key")
        if field.is_computed():
            tags.append("Read-Only")
        if tags:
            base_info += " — " + " — ".join(tags)

        formula = field.formula(sanitized=True, condense=True)
        if formula:
            lines: list[str] = [base_info, ""]
            formula_lines = field.formula(sanitized=True, format=True).splitlines()
            if len(formula_lines) > 15:
                formula_lines = formula_lines[:15] + ["… (truncated)"]
            lines.extend(formula_lines)
            self.doc_comment(lines, indent=indent_level)
        else:
            self.doc_comment(base_info, indent=indent_level)

"""Tests for Airtable field descriptions in generated per-field doc comments.

Two layers:

1. `build_field_doc` logic (language-agnostic) via lightweight stubs — metadata
   line first, then description, then formula; tags; truncation; empty/whitespace
   descriptions skipped.
2. Per-language escaping via the real writers — a deliberately hostile
   description (comment terminators, HTML/XML markup, triple quotes, trailing
   backslash, embedded newline, Unicode) must never break the generated comment
   syntax, and the description text must survive.
"""

import ast
from pathlib import Path

from myairtable.generators.javascript import WriteToJavaScriptFile
from myairtable.generators.python import WriteToPythonFile
from myairtable.generators.rust import WriteToRustFile
from myairtable.generators.typescript import WriteToTypeScriptFile
from myairtable.meta_types import FieldType
from myairtable.utils.field_doc import DocStyle, build_field_doc
from myairtable.utils.write_to_cpp_file import WriteToCppFile
from myairtable.utils.write_to_csharp_file import WriteToCSharpFile
from myairtable.utils.write_to_go_file import WriteToGoFile
from myairtable.utils.write_to_java_file import WriteToJavaFile
from myairtable.utils.write_to_kotlin_file import WriteToKotlinFile
from myairtable.utils.write_to_swift_file import WriteToSwiftFile
from tests.test_generators import make_test_base

# A description crafted to break every target's comment syntax if unescaped:
# block-comment terminator (*/), nested open (/*), Python triple-quote ("""),
# HTML/XML markup (< & > and a literal </summary>), JSDoc/KDoc/Javadoc tag (@param),
# Doxygen command (\brief), a trailing backslash, an embedded newline, and Unicode.
HOSTILE_DESCRIPTION = (
    "Closes */ then opens /* a comment. "
    'Has a """ triple-quote. '
    "Markup < & > and a literal </summary> tag. "
    "JSDoc @param and Doxygen \\brief, ending with a backslash \\\n"
    "Second line: café ☕ 日本語 — em-dash."
)


# --------------------------------------------------------------------------- #
# build_field_doc — language-agnostic assembly logic (via stubs)
# --------------------------------------------------------------------------- #


class _StubField:
    def __init__(self, id, name, description, computed=False, formula_lines=None):
        self.id = id
        self.name = name
        self.description = description
        self._computed = computed
        self._formula_lines = formula_lines or []

    def is_computed(self):
        return self._computed

    def formula(self, sanitized=False, condense=False, format=False):
        if not self._formula_lines:
            return ""
        return "\n".join(self._formula_lines) if format else "condensed"


class _StubTable:
    def __init__(self, primary_field_id):
        self.primary_field_id = primary_field_id


# A plain style: backtick code, backtick fences, identity escaping.
_PLAIN = DocStyle(code=lambda t: f"`{t}`", fence_open="```", fence_close="```")


def test_metadata_line_precedes_description():
    field = _StubField("fld001", "My Field", "The description.")
    lines = build_field_doc(field, _StubTable("fld000"), _PLAIN)
    assert lines[0] == "My Field `fld001`"
    assert lines[1] == ""
    assert lines[2] == "The description."


def test_primary_key_and_read_only_tags_on_header():
    field = _StubField("fld000", "Name", None, computed=True)
    lines = build_field_doc(field, _StubTable("fld000"), _PLAIN)
    assert lines[0] == "Name `fld000` - `Primary Key` - `Read-Only`"


def test_empty_and_whitespace_descriptions_are_skipped():
    for desc in (None, "", "   \n\t  "):
        field = _StubField("fld001", "F", desc)
        lines = build_field_doc(field, _StubTable("fld000"), _PLAIN)
        assert lines == ["F `fld001`"]


def test_multiline_description_is_split_into_separate_lines():
    field = _StubField("fld001", "F", "line one\nline two\nline three")
    lines = build_field_doc(field, _StubTable("fld000"), _PLAIN)
    assert lines == ["F `fld001`", "", "line one", "line two", "line three"]


def test_description_precedes_formula_block():
    field = _StubField("fld001", "F", "desc", formula_lines=["1 + 2"])
    lines = build_field_doc(field, _StubTable("fld000"), _PLAIN)
    assert lines == ["F `fld001`", "", "desc", "", "```", "1 + 2", "```"]


def test_formula_is_truncated_at_the_style_cap():
    field = _StubField("fld001", "F", None, formula_lines=[f"line{i}" for i in range(30)])
    lines = build_field_doc(field, _StubTable("fld000"), _PLAIN)
    assert "line14" in lines
    assert "line15" not in lines
    assert "… (truncated)" in lines


def test_truncation_disabled_keeps_all_formula_lines():
    style = DocStyle(code=lambda t: f"`{t}`", fence_open="```", fence_close="```", truncate_formula=None)
    field = _StubField("fld001", "F", None, formula_lines=[f"line{i}" for i in range(30)])
    lines = build_field_doc(field, _StubTable("fld000"), style)
    assert "line29" in lines
    assert "… (truncated)" not in lines


# --------------------------------------------------------------------------- #
# Per-language escaping — the real writers must not break on hostile input
# --------------------------------------------------------------------------- #


def _field_with_description(field_id: str, field_type: FieldType, description: str | None):
    """Build a single field (id/type) carrying `description`, plus its table."""
    base = make_test_base([("Hostile Field", field_id, field_type)])
    table = base.tables[0]
    field = table.fields[0]
    field.description = description
    return field, table


def _render(writer_cls, field, table) -> list[str]:
    writer = writer_cls(path=Path("/tmp/unused-field-doc-test"))
    writer.lines = []
    writer.property_docstring(field, table, 0)
    return writer.lines


def test_python_docstring_stays_parseable():
    import warnings

    # createdTime is computed (Read-Only tag) but carries no formula.
    field, table = _field_with_description("fld001", "createdTime", HOSTILE_DESCRIPTION)
    lines = _render(WriteToPythonFile, field, table)
    src = "\n".join(lines)
    # A bare triple-quoted docstring is a valid module; raises if """ leaked.
    ast.parse(src)
    # compile() (unlike ast.parse) surfaces invalid-escape SyntaxWarnings, e.g.
    # from a raw `\brief` in the description — promote them to errors.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        compile(src, "<generated>", "exec")
    assert "café" in src
    assert "Read-Only" in src and "Read-Only Field" not in src
    assert '"""' in lines[0] or lines[0] == '"""'  # opens with the delimiter


def test_rust_lines_all_stay_inside_the_comment():
    field, table = _field_with_description("fld001", "createdTime", HOSTILE_DESCRIPTION)
    lines = _render(WriteToRustFile, field, table)
    assert lines, "expected doc lines"
    assert all(line.startswith("///") for line in lines)
    # The embedded newline produced a distinct comment line for the second half.
    assert any("café" in line for line in lines)
    assert any("Closes */" in line for line in lines)  # harmless inside a // comment


def test_swift_lines_all_stay_inside_the_comment():
    field, table = _field_with_description("fld001", "createdTime", HOSTILE_DESCRIPTION)
    lines = _render(WriteToSwiftFile, field, table)
    assert all(line.startswith("///") for line in lines)
    assert any("café" in line for line in lines)


def test_cpp_lines_all_stay_inside_the_comment():
    field, table = _field_with_description("fld001", "createdTime", HOSTILE_DESCRIPTION)
    lines = _render(WriteToCppFile, field, table)
    assert all(line.startswith("///") for line in lines)
    # No line may end in a backslash followed by only whitespace: in C/C++ that
    # splices the next source line into the `//` comment (clang/gcc treat even
    # backslash-then-space-then-newline as a continuation), swallowing the
    # following declaration.
    import re as _re

    for line in lines:
        assert not _re.search(r"\\\s*$", line)
    assert any("café" in line for line in lines)


def test_go_lines_all_stay_inside_the_comment():
    field, table = _field_with_description("fld001", "createdTime", HOSTILE_DESCRIPTION)
    lines = _render(WriteToGoFile, field, table)
    assert all(line.startswith("//") for line in lines)
    assert any("café" in line for line in lines)


def _assert_block_comment_safe(lines: list[str]):
    """A /** ... */ block: only the final line may carry the `*/` terminator."""
    assert lines[0].strip() == "/**"
    assert lines[-1].strip() == "*/"
    for interior in lines[1:-1]:
        assert "*/" not in interior


def test_typescript_block_comment_not_terminated_early():
    field, table = _field_with_description("fld001", "createdTime", HOSTILE_DESCRIPTION)
    lines = _render(WriteToTypeScriptFile, field, table)
    _assert_block_comment_safe(lines)
    src = "\n".join(lines)
    assert "Closes * /" in src  # the hostile */ was neutralized
    assert "café" in src


def test_javascript_block_comment_not_terminated_early():
    field, table = _field_with_description("fld001", "createdTime", HOSTILE_DESCRIPTION)
    lines = _render(WriteToJavaScriptFile, field, table)
    _assert_block_comment_safe(lines)
    assert "Closes * /" in "\n".join(lines)


def test_kotlin_block_comment_not_terminated_early():
    field, table = _field_with_description("fld001", "createdTime", HOSTILE_DESCRIPTION)
    lines = _render(WriteToKotlinFile, field, table)
    _assert_block_comment_safe(lines)
    src = "\n".join(lines)
    # Kotlin block comments NEST, so an interior `/*` opens an inner comment whose
    # close eats the KDoc terminator — it must be neutralized too, not just `*/`.
    for interior in lines[1:-1]:
        assert "/*" not in interior
    assert "café" in src


def test_java_escapes_html_and_does_not_terminate_early():
    field, table = _field_with_description("fld001", "createdTime", HOSTILE_DESCRIPTION)
    lines = _render(WriteToJavaFile, field, table)
    _assert_block_comment_safe(lines)
    src = "\n".join(lines)
    assert "&lt;" in src and "&amp;" in src and "&gt;" in src
    assert "</summary>" not in src  # entity-escaped, not a live tag
    assert "café" in src


def test_csharp_escapes_xml_markup():
    field, table = _field_with_description("fld001", "createdTime", HOSTILE_DESCRIPTION)
    lines = _render(WriteToCSharpFile, field, table)
    src = "\n".join(lines)
    assert any("<summary>" in line for line in lines)
    assert "&lt;" in src and "&amp;" in src
    assert "&lt;/summary&gt;" in src  # the literal </summary> in the description
    assert all(line.startswith("///") for line in lines)


def test_metadata_precedes_description_in_generated_output():
    """Across a representative target, the id line comes before the description."""
    field, table = _field_with_description("fld001", "createdTime", HOSTILE_DESCRIPTION)
    lines = _render(WriteToRustFile, field, table)
    id_idx = next(i for i, line in enumerate(lines) if "fld001" in line)
    desc_idx = next(i for i, line in enumerate(lines) if "café" in line)
    assert id_idx < desc_idx


def test_field_without_description_emits_no_description_block():
    field, table = _field_with_description("fld001", "singleLineText", None)
    lines = _render(WriteToRustFile, field, table)
    assert lines == ["/// Hostile Field `fld001`"]

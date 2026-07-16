"""C++ code generator.

Mirrors the structure of the C# generator (the closest structural template):
one public type per header, a flat ``myairtable`` namespace, and a
``dynamic/{options,types,formulas,models,tables}`` output layout beside a
verbatim copy of the hand-written ``static/cpp`` runtime.

Idiom targets (plan .beads/cpp-plan-v2.md): C++20 aggregate-struct models with
``std::optional<T>`` members and designated-initializer creation, value-semantic
``nlohmann::json``, header-only distribution (consumers add the output folder to
their include path and link libcurl).

Output structure:
    <output>/
    ├── dynamic/
    │   ├── options/    {options_name}.hpp enums (+ to_json/from_json)
    │   ├── types/      {table}_fields.hpp, {table}_view.hpp, create_{table}_fields.hpp
    │   ├── formulas/   {table}_filters.hpp                     (F7)
    │   ├── models/     {table}_model.hpp                       (F4)
    │   └── tables/     {table}_table.hpp
    ├── static/         copied verbatim from static/cpp/ (incl. vendor/)
    └── airtable.hpp    entry point
"""

from pathlib import Path

from pydantic.alias_generators import to_snake

from ..meta import Base
from ..utils.helpers import Paths, copy_static_files, deduplicate_identifiers, reset_folder, sanitize_string
from ..utils.write_to_cpp_file import WriteToCppFile, _choice_to_entry, _cpp_string_literal, _cppdoc_escape

_DIR_DYNAMIC = Paths.DYNAMIC
_DIR_OPTIONS = "options"
_DIR_TYPES = "types"
_DIR_TABLES = "tables"
_DIR_MODELS = "models"
_DIR_FORMULAS = "formulas"

# Static formula-DSL headers excluded from the copy when formulas=False.
_FORMULA_STATIC_FILES: list[str] = [
    "formulas.hpp",
    "formula_field.hpp",
    "formula_text_ops.hpp",
    "formula_text_field.hpp",
    "formula_single_select_field.hpp",
    "formula_multi_select_field.hpp",
    "formula_lookup_field.hpp",
    "formula_number_field.hpp",
    "formula_boolean_field.hpp",
    "formula_attachments_field.hpp",
    "formula_date_field.hpp",
    "formula_id.hpp",
]


def _create_dynamic_subdir(output_folder: Path, name: str) -> Path:
    path = output_folder / _DIR_DYNAMIC / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deduplicate_entries(entries: list[str]) -> list[str]:
    """Ensure enum-member names are unique by appending _V2, _V3, etc."""
    return deduplicate_identifiers(entries, suffix="_V")


def _header_name(type_name: str) -> str:
    """snake_case header filename for a generated PascalCase type."""
    return f"{to_snake(type_name)}.hpp"


def _doc(write: WriteToCppFile, text: str, indent: int = 0) -> None:
    write.doc_comment(_cppdoc_escape(text), indent=indent)


# =============================================================================
# WRITERS
# =============================================================================


def write_options(base: Base, output_folder: Path) -> None:
    """Generate one C++ enum class + adl_serializer per select field.

    NLOHMANN_JSON_SERIALIZE_ENUM maps an unknown wire value to the FIRST pair
    (silent corruption), so each enum gets a hand-shaped serializer keyed on the
    raw choice strings that throws DecodingError on an unknown value instead.
    """
    options_dir = _create_dynamic_subdir(output_folder, _DIR_OPTIONS)

    for table in base.tables:
        for field in table.select_fields():
            choices = field.select_options()
            if not choices:
                continue

            enum_name = field.options_name()
            entries = _deduplicate_entries([_choice_to_entry(c) for c in choices])
            pairs = list(zip(entries, choices))
            qualified = f"myairtable::{enum_name}"

            with WriteToCppFile(path=options_dir / _header_name(enum_name)) as write:
                write.pragma_once()
                write.line_empty()
                write.include_system("string")
                write.line_empty()
                write.include_local("static/airtable_exception.hpp")
                write.include_local("static/airtable_json.hpp")
                write.line_empty()
                write.namespace_open()
                write.line_empty()
                _doc(write, f"Options for {sanitize_string(field.name)}.")
                write.enum_class_open(enum_name)
                for member, _ in pairs:
                    write.enum_entry(member, indent=1)
                write.close()
                write.line_empty()
                write.namespace_close()
                write.line_empty()

                # Per-enum serializer mapping members ↔ raw Airtable strings.
                write.namespace_open("nlohmann")
                write.line_empty()
                _doc(write, f"Maps {enum_name} members to/from their raw Airtable strings.")
                write.line("template <>")
                write.line(f"struct adl_serializer<{qualified}> {{")
                write.line_indented(f"static {qualified} from_json(const json& j) {{")
                write.line_indented("const auto raw = j.get<std::string>();", indent=2)
                # Last-wins on duplicate raw strings (mirrors nameToId collapse).
                seen: dict[str, str] = {}
                for member, choice in pairs:
                    seen[_cpp_string_literal(choice)] = member
                for choice_lit, member in seen.items():
                    write.line_indented(f'if (raw == "{choice_lit}") {{', indent=2)
                    write.line_indented(f"return {qualified}::{member};", indent=3)
                    write.line_indented("}", indent=2)
                write.line_indented(
                    f'throw myairtable::DecodingError("Unknown {enum_name}: " + raw);',
                    indent=2,
                )
                write.line_indented("}")
                write.line_indented(f"static void to_json(json& j, {qualified} value) {{")
                write.line_indented("switch (value) {", indent=2)
                for member, choice in pairs:
                    write.line_indented(f"case {qualified}::{member}:", indent=3)
                    write.line_indented(f'j = "{_cpp_string_literal(choice)}";', indent=4)
                    write.line_indented("return;", indent=4)
                write.line_indented("}", indent=2)
                write.line_indented("}")
                write.line("};")
                write.line_empty()
                write.namespace_close("nlohmann")


def generate_cpp(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    wrappers: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate C++ code for the given base into ``output_folder``.

    F3 so far: static copy + options. Field types/tables/entry point land with
    the remaining F3 tasks; models (F4), formula helpers (F7), and runtime
    transpilation (F8) with their features.
    """
    del wrappers, runtime, flatten  # consumed by later features (F3/F4/F8)

    output_folder = reset_folder(output_folder)

    exclude_static: list[str] = []
    if not formulas:
        exclude_static.extend(_FORMULA_STATIC_FILES)
    copy_static_files(output_folder, "cpp", exclude=exclude_static or None)

    write_options(base, output_folder)

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

from ..meta import Base, Table
from ..utils.helpers import (
    Paths,
    copy_static_files,
    deduplicate_identifiers,
    deduplicated_table_prefix_map,
    reset_folder,
    sanitize_string,
)
from ..utils.write_to_cpp_file import WriteToCppFile, _choice_to_entry, _cpp_ident, _cpp_string_literal, _cppdoc_escape

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


def _table_type_prefix(table: Table) -> str:
    """PascalCase prefix used for generated types (e.g. `Primary`), deduplicated per base."""
    return deduplicated_table_prefix_map(table.base)[table.id] or "Table"


def _field_constant_map(table: Table) -> dict[str, str]:
    """`{field_id: deduplicated PascalCase constant stem}` for one table.

    Constants are emitted as `k{Stem}Id` / `k{Stem}Name`, so the `k` prefix
    already rules out keyword collisions; only emptiness and duplicates need
    handling.
    """
    raw = [field.name_pascal() or "Field" for field in table.fields]
    deduped = deduplicate_identifiers(raw, suffix="V")
    return {field.id: name for field, name in zip(table.fields, deduped)}


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


def write_field_types(base: Base, output_folder: Path) -> None:
    """Generate `{table}_fields.hpp` + `{table}_view.hpp` + `create_{table}_fields.hpp`."""
    types_dir = _create_dynamic_subdir(output_folder, _DIR_TYPES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        stems = _field_constant_map(table)
        fields_name = f"{prefix}Fields"

        with WriteToCppFile(path=types_dir / _header_name(fields_name)) as write:
            write.pragma_once()
            write.line_empty()
            write.include_system("map")
            write.include_system("optional")
            write.include_system("string")
            write.include_system("string_view")
            write.include_system("vector")
            write.line_empty()
            write.namespace_open()
            write.line_empty()
            _doc(write, f"Field id + name constants for {sanitize_string(table.name)}.")
            write.struct_open(fields_name)
            for field in table.fields:
                name_lit = _cpp_string_literal(sanitize_string(field.name))
                stem = stems[field.id]
                write.line_indented(f'static constexpr std::string_view k{stem}Id = "{field.id}";')
                write.line_indented(f'static constexpr std::string_view k{stem}Name = "{name_lit}";')
            write.line_empty()

            ids = ", ".join(f'"{f.id}"' for f in table.fields)
            write.line_indented(f"inline static const std::vector<std::string> kAllIds = {{{ids}}};")
            write.line_empty()

            # name → id, last-wins on collision (distinct names can collapse after sanitize).
            name_to_id: dict[str, str] = {}
            for field in table.fields:
                name_to_id[_cpp_string_literal(sanitize_string(field.name))] = field.id
            write.line_indented("inline static const std::map<std::string, std::string> kNameToId = {")
            for name_lit, fid in name_to_id.items():
                write.line_indented(f'{{"{name_lit}", "{fid}"}},', indent=2)
            write.line_indented("};")
            write.line_empty()
            write.line_indented("inline static const std::map<std::string, std::string> kIdToName = {")
            for field in table.fields:
                name_lit = _cpp_string_literal(sanitize_string(field.name))
                write.line_indented(f'{{"{field.id}", "{name_lit}"}},', indent=2)
            write.line_indented("};")
            write.line_empty()

            write.line_indented("static std::optional<std::string> id_by_name(const std::string& name) {")
            write.line_indented("const auto it = kNameToId.find(name);", indent=2)
            write.line_indented("return it == kNameToId.end() ? std::nullopt : std::optional(it->second);", indent=2)
            write.line_indented("}")
            write.line_indented("static std::optional<std::string> name_by_id(const std::string& id) {")
            write.line_indented("const auto it = kIdToName.find(id);", indent=2)
            write.line_indented("return it == kIdToName.end() ? std::nullopt : std::optional(it->second);", indent=2)
            write.line_indented("}")
            write.close()
            write.line_empty()
            write.namespace_close()

        # ---------- Views ----------
        if table.views:
            view_name = f"{prefix}View"
            view_entries = _deduplicate_entries([_choice_to_entry(v.name) for v in table.views])
            with WriteToCppFile(path=types_dir / _header_name(view_name)) as write:
                write.pragma_once()
                write.line_empty()
                write.include_system("string")
                write.include_system("utility")
                write.line_empty()
                write.namespace_open()
                write.line_empty()
                _doc(write, f"Views for {sanitize_string(table.name)}.")
                write.class_open(view_name)
                write.line_indented("public:", indent=0)
                for view, member in zip(table.views, view_entries):
                    _doc(write, f"{sanitize_string(view.name)} ({view.type})", indent=1)
                    write.line_indented(f"static const {view_name} {_cpp_ident(member)};")
                write.line_empty()
                write.line_indented("const std::string& id() const { return id_; }")
                write.line_empty()
                write.line_indented("private:", indent=0)
                write.line_indented(f"explicit {view_name}(std::string id) : id_(std::move(id)) {{}}")
                write.line_indented("std::string id_;")
                write.close()
                write.line_empty()
                for view, member in zip(table.views, view_entries):
                    write.line(f'inline const {view_name} {view_name}::{_cpp_ident(member)}{{"{view.id}"}};')
                write.line_empty()
                write.namespace_close()

        # ---------- Writable (create) fields ----------
        writable_fields = [f for f in table.fields if not f.is_computed()]
        if writable_fields:
            create_name = f"Create{prefix}Fields"
            with WriteToCppFile(path=types_dir / _header_name(create_name)) as write:
                write.pragma_once()
                write.line_empty()
                write.include_system("string_view")
                write.line_empty()
                write.namespace_open()
                write.line_empty()
                _doc(write, f"Writable field id + name constants for {sanitize_string(table.name)}.")
                write.struct_open(create_name)
                for field in writable_fields:
                    name_lit = _cpp_string_literal(sanitize_string(field.name))
                    stem = stems[field.id]
                    write.line_indented(f'static constexpr std::string_view k{stem}Id = "{field.id}";')
                    write.line_indented(f'static constexpr std::string_view k{stem}Name = "{name_lit}";')
                write.close()
                write.line_empty()
                write.namespace_close()


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
    write_field_types(base, output_folder)

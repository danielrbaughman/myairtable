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
    ├── static/         copied verbatim from src/myairtable/static/cpp/ (incl. vendor/)
    └── airtable.hpp    entry point
"""

from pathlib import Path

from pydantic.alias_generators import to_snake

from ..formulas.formula_flattener import flatten_formula_for_transpilation
from ..formulas.formula_transpiler import transpile_table_formulas
from ..meta import Base, Table
from ..utils.helpers import (
    Paths,
    copy_static_files,
    deduplicate_identifiers,
    deduplicated_field_property_map_snake,
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

# Accessor-method names on the generated Airtable class that would collide with
# its own members; colliding table names get a `_table` suffix.
_CPP_RESERVED_TABLE_METHODS = frozenset({"client", "invalidate_all_caches", "base_id"})

# Member names a generated model may not use: aggregate state members, the CRTP
# base's methods, the generated hooks, and the F filter accessor. Colliding
# field names get a `_field` suffix (then re-deduplicate).
_CPP_RESERVED_MODEL_MEMBERS = frozenset(
    {
        "id",
        "created_time",
        "client_",
        "snapshot_",
        "is_new",
        "take_snapshot",
        "dirty_fields",
        "to_record",
        "to_create_fields",
        "require_id",
        "require_client",
        "save",
        "fetch",
        "remove",
        "copy",
        "collect_writable_fields",
        "collect_computed_fields",
        "detach_attachments_for_copy",
        "F",
        "k_table_id",
    }
)

# WRITABLE cell types `AirtableModel::copy()` must project down to {url, filename}
# (airtable_attachment.hpp `project_attachment_cell`). Everything else the copy carries
# verbatim: the models are aggregates of value-semantic members, so the implicit copy
# constructor already deep-copies them. COMPUTED attachment-shaped cells are excluded on
# purpose — a lookup can hold the identical shape, it is never written back, and stripping
# its metadata would lose fidelity for nothing (epic contract item 6).
_CPP_ATTACHMENT_CELL_TYPES = frozenset({"AirtableAttachment", "std::vector<AirtableAttachment>"})

# Airtable field class -> static DSL filter type (formula_class() keys).
_CPP_FORMULA_CLASS_MAP = {
    "TextField": "FormulaTextField",
    "BooleanField": "FormulaBooleanField",
    "DateField": "FormulaDateField",
    "NumberField": "FormulaNumberField",
    "AttachmentsField": "FormulaAttachmentsField",
    "LookupField": "FormulaLookupField",
    "SingleSelectField": "FormulaSingleSelectField",
    "MultiSelectField": "FormulaMultiSelectField",
}

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


def _field_property_map(table: Table) -> dict[str, str]:
    """`{field_id: deduplicated snake_case member name}` for one table.

    snake_case via the shared helper, then keyword-escaped, reserved-member
    suffixed, and re-deduplicated (escaping/suffixing can re-collide).
    """
    raw = deduplicated_field_property_map_snake(table)
    adjusted = [f"{_cpp_ident(name)}_field" if _cpp_ident(name) in _CPP_RESERVED_MODEL_MEMBERS else _cpp_ident(name) for name in raw.values()]
    deduped = deduplicate_identifiers(adjusted, suffix="_v")
    return {field_id: name for field_id, name in zip(raw.keys(), deduped)}


def _model_option_includes(table: Table) -> list[str]:
    """Option-enum headers referenced by this table's select fields, sorted."""
    headers = {f"dynamic/options/{_header_name(field.options_name())}" for field in table.select_fields() if field.select_options()}
    return sorted(headers)


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
            write.line_indented("inline static const std::map<std::string, std::string, std::less<>> kNameToId = {")
            for name_lit, fid in name_to_id.items():
                write.line_indented(f'{{"{name_lit}", "{fid}"}},', indent=2)
            write.line_indented("};")
            write.line_empty()
            write.line_indented("inline static const std::map<std::string, std::string, std::less<>> kIdToName = {")
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


def write_formula_helpers(base: Base, output_folder: Path) -> None:
    """Generate per-table `{table}_filters.hpp`, accessed via `{Table}Model::F`.

    One const filter member per field typed to the appropriate Formula*Field
    class, plus an `id` FormulaId for record-ID filters. Shape:
    `PrimaryModel::F.primary_key.eq("x")`.
    """
    formulas_dir = _create_dynamic_subdir(output_folder, _DIR_FORMULAS)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        props = _field_property_map(table)
        filters_name = f"{prefix}Filters"

        with WriteToCppFile(path=formulas_dir / _header_name(filters_name)) as write:
            write.pragma_once()
            write.line_empty()
            write.include_local("static/formula_attachments_field.hpp")
            write.include_local("static/formula_boolean_field.hpp")
            write.include_local("static/formula_date_field.hpp")
            write.include_local("static/formula_id.hpp")
            write.include_local("static/formula_lookup_field.hpp")
            write.include_local("static/formula_multi_select_field.hpp")
            write.include_local("static/formula_number_field.hpp")
            write.include_local("static/formula_single_select_field.hpp")
            write.include_local("static/formula_text_field.hpp")
            write.line_empty()
            write.namespace_open()
            write.line_empty()
            _doc(write, f"Formula builder for {sanitize_string(table.name)}.")
            write.struct_open(filters_name)
            _doc(write, "Record ID formula.", indent=1)
            write.line_indented("FormulaId id{};")
            write.line_empty()
            for field in table.fields:
                formula_class = _CPP_FORMULA_CLASS_MAP.get(field.formula_class(), "FormulaTextField")
                _doc(write, sanitize_string(field.name), indent=1)
                write.line_indented(f'{formula_class} {props[field.id]}{{"{field.id}"}};')
            write.close()
            write.line_empty()
            write.namespace_close()


def write_models(base: Base, output_folder: Path, formulas: bool = True, runtime: bool = True, flatten: bool = False) -> None:
    """Generate `{table}_model.hpp` ORM aggregates.

    Aggregate struct over the CRTP `AirtableModel` behavior base: public
    `std::optional<T>` members in schema order (designated-initializer
    creation), the two collect hooks, and an ADL `from_json` over the full
    record envelope. The `F` filter accessor (F7) and transpiled `evaluate_*`
    methods (F8) land with their features.
    """
    models_dir = _create_dynamic_subdir(output_folder, _DIR_MODELS)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        model_name = f"{prefix}Model"
        props = _field_property_map(table)
        writable = [f for f in table.fields if not f.is_computed()]
        computed = [f for f in table.fields if f.is_computed()]
        attachment_cells = [f for f in writable if f.cpp_type() in _CPP_ATTACHMENT_CELL_TYPES]

        # Pre-transpile this table's formula fields into `evaluate_*` bodies (F8).
        transpiled_formulas: dict[str, str] = {}
        raw_formulas: dict[str, str] = {}
        if runtime:
            formula_field_ids = table.formula_field_ids()
            # field_name_map uses the snake_case member names -> `this->my_field`.
            field_name_map = {f.id: props[f.id] for f in table.fields}
            raw_formulas = {f.id: f.options.formula for f in table.fields if f.is_formula() and f.options and f.options.formula}
            if flatten and raw_formulas:
                formula_map_tuple = table.base.get_formula_field_map_tuple()
                raw_formulas = {fid: flatten_formula_for_transpilation(f, fid, formula_map_tuple) for fid, f in raw_formulas.items()}
            if raw_formulas:
                transpiled_formulas = transpile_table_formulas(raw_formulas, "cpp", field_name_map, formula_field_ids)

        with WriteToCppFile(path=models_dir / _header_name(model_name)) as write:
            write.pragma_once()
            write.line_empty()
            write.include_system("cstdint")
            write.include_system("memory")
            write.include_system("optional")
            write.include_system("string")
            write.include_system("string_view")
            write.include_system("vector")
            write.line_empty()
            if formulas:
                write.include_local(f"dynamic/formulas/{_header_name(f'{prefix}Filters')}")
            for header in _model_option_includes(table):
                write.include_local(header)
            write.include_local("static/airtable_attachment.hpp")
            write.include_local("static/airtable_button.hpp")
            write.include_local("static/airtable_collaborator.hpp")
            write.include_local("static/airtable_date.hpp")
            write.include_local("static/airtable_model.hpp")
            write.include_local("static/maybe_special_or_error.hpp")
            if transpiled_formulas:
                write.include_local("static/runtime_array.hpp")
                write.include_local("static/runtime_date.hpp")
                write.include_local("static/runtime_logic.hpp")
                write.include_local("static/runtime_math.hpp")
                write.include_local("static/runtime_regex.hpp")
                write.include_local("static/runtime_string.hpp")
            write.include_local("static/vec_or_value.hpp")
            write.line_empty()
            write.namespace_open()
            write.line_empty()
            first_writable = props[writable[0].id] if writable else "..."
            _doc(
                write,
                f"ORM model for {sanitize_string(table.name)}.\n"
                f"\n"
                f"Create with a designated initializer — `{model_name}{{.{first_writable} = ...}}` —\n"
                f"and pass to the table's create_one(). Computed members are public but never\n"
                f"serialized on write: mutating one and calling save() sends nothing for it.",
            )
            write.struct_open(model_name, base=f"AirtableModel<{model_name}>")
            write.line_indented(f'static constexpr std::string_view kTableId = "{table.id}";')
            write.line_empty()
            if formulas:
                _doc(write, f"Filter builder: `{model_name}::F.field.eq(...)` -> filterByFormula.", indent=1)
                write.line_indented(f"inline static const {prefix}Filters F{{}};")
                write.line_empty()
            write.comment("record meta (the CRTP base holds no data)", indent=1)
            write.line_indented("std::optional<std::string> id{};")
            write.line_indented("std::optional<DateTime> created_time{};")
            write.line_indented("std::shared_ptr<AirtableClient> client_{};  // internal: attached by tables")
            write.line_indented("json snapshot_{};                           // internal: dirty-tracking baseline")
            write.line_empty()
            for field in table.fields:
                write.property_docstring(field, table)
                write.line_indented(f"std::optional<{field.cpp_type()}> {props[field.id]}{{}};")
            write.line_empty()

            write.comment("generated hooks consumed by the AirtableModel behavior base", indent=1)
            write.line_indented("json collect_writable_fields() const {")
            write.line_indented("json fields = json::object();", indent=2)
            for field in writable:
                write.line_indented(f'write_field(fields, "{field.id}", {props[field.id]});', indent=2)
            write.line_indented("return fields;", indent=2)
            write.line_indented("}")
            write.line_indented("json collect_computed_fields() const {")
            write.line_indented("json fields = json::object();", indent=2)
            for field in computed:
                write.line_indented(f'write_field(fields, "{field.id}", {props[field.id]});', indent=2)
            write.line_indented("return fields;", indent=2)
            write.line_indented("}")
            # copy() lives on the CRTP base, but the base cannot enumerate members: this
            # hook is the one part of the detach that needs generated knowledge — which
            # cells are WRITABLE attachments. Emitted even when empty so the base's call
            # always resolves.
            write.line_indented("void detach_attachments_for_copy() {")
            for field in attachment_cells:
                write.line_indented(f"project_attachment_cell({props[field.id]});", indent=2)
            write.line_indented("}")
            if transpiled_formulas:
                write.line_empty()
                write.comment("runtime formula evaluation (transpiled from the Airtable formulas)", indent=1)
                for field in table.fields:
                    if field.id not in transpiled_formulas:
                        continue
                    raw = raw_formulas.get(field.id, "")
                    preview = sanitize_string(raw).replace("\n", " ")[:80]
                    write.line_empty()
                    _doc(write, f"Evaluate this formula locally: `{preview}`", indent=1)
                    write.line_indented(f"json evaluate_{props[field.id]}() const {{")
                    write.line_indented(f"return {transpiled_formulas[field.id]};", indent=2)
                    write.line_indented("}")
            write.close()
            write.line_empty()

            _doc(write, f"Decode one {{id, createdTime, fields}} envelope into a {model_name}.")
            write.line(f"inline void from_json(const json& record, {model_name}& model) {{")
            write.line_indented('if (record.contains("id")) {')
            write.line_indented('model.id = record.at("id").get<std::string>();', indent=2)
            write.line_indented("}")
            write.line_indented('if (record.contains("createdTime")) {')
            write.line_indented('model.created_time = record.at("createdTime").get<DateTime>();', indent=2)
            write.line_indented("}")
            write.line_indented('const json fields = record.contains("fields") ? record.at("fields") : json::object();')
            for field in table.fields:
                write.line_indented(f'model.{props[field.id]} = read_field<{field.cpp_type()}>(fields, "{field.id}");')
            write.line("}")
            write.line_empty()
            write.namespace_close()


def _table_accessor(table: Table) -> str:
    """snake_case accessor-method name on the Airtable class (e.g. `primary`)."""
    accessor = _cpp_ident(to_snake(_table_type_prefix(table)))
    if accessor in _CPP_RESERVED_TABLE_METHODS:
        accessor = f"{accessor}_table"
    return accessor


def write_tables(base: Base, output_folder: Path) -> None:
    """Generate `{table}_table.hpp` facades.

    The ORM surface is the DEFAULT (inherits `OrmTable<{Table}Model>`, the
    cross-target post-C# decision); `.dict()` keeps raw field-bag access.
    """
    tables_dir = _create_dynamic_subdir(output_folder, _DIR_TABLES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        table_name = f"{prefix}Table"
        fields_name = f"{prefix}Fields"
        model_name = f"{prefix}Model"

        with WriteToCppFile(path=tables_dir / _header_name(table_name)) as write:
            write.pragma_once()
            write.line_empty()
            write.include_system("map")
            write.include_system("memory")
            write.include_system("string")
            write.include_system("string_view")
            write.include_system("utility")
            write.line_empty()
            write.include_local(f"dynamic/models/{_header_name(model_name)}")
            write.include_local(f"dynamic/types/{_header_name(fields_name)}")
            write.include_local("static/airtable_client.hpp")
            write.include_local("static/dict_table.hpp")
            write.include_local("static/orm_table.hpp")
            write.line_empty()
            write.namespace_open()
            write.line_empty()
            _doc(
                write,
                f"Table accessor for {sanitize_string(table.name)}: the typed ORM surface\n"
                f"(get_one/get_many/create_one/create_many/update_one/update_many/\n"
                f"duplicate_one/duplicate_many/upsert/delete_one/delete_many over\n"
                f"{model_name}) is the default;\n"
                f".dict() is the raw field-bag escape hatch.",
            )
            write.class_open(table_name, base=f"OrmTable<{model_name}>")
            write.line_indented("public:", indent=0)
            write.line_indented(f'static constexpr std::string_view kTableId = "{table.id}";')
            write.line_empty()
            write.line_indented(f"explicit {table_name}(std::shared_ptr<AirtableClient> client)")
            write.line_indented(f": OrmTable<{model_name}>(client),", indent=2)
            write.line_indented(f"dict_(std::move(client), std::string(kTableId), {fields_name}::kNameToId) {{}}", indent=3)
            write.line_empty()
            _doc(write, "Raw field-bag access (records travel as Fields, dual id/name keyed).", indent=1)
            write.line_indented("DictTable& dict() { return dict_; }")
            write.line_indented("const DictTable& dict() const { return dict_; }")
            write.line_empty()
            write.line_indented("private:", indent=0)
            write.line_indented("DictTable dict_;")
            write.close()
            write.line_empty()
            write.namespace_close()


def write_main(base: Base, output_folder: Path) -> None:
    """Generate the `airtable.hpp` entry point at the output root."""
    tables = list(base.tables)

    with WriteToCppFile(path=output_folder / "airtable.hpp") as write:
        write.pragma_once()
        write.line_empty()
        write.include_system("memory")
        write.include_system("string")
        write.include_system("string_view")
        write.include_system("utility")
        write.line_empty()
        for table in tables:
            write.include_local(f"dynamic/tables/{_header_name(f'{_table_type_prefix(table)}Table')}")
        write.include_local("static/airtable_client.hpp")
        write.line_empty()
        write.namespace_open()
        write.line_empty()
        _doc(write, f"Entry point for base {base.id}: one accessor per table.")
        write.class_open("Airtable")
        write.line_indented("public:", indent=0)
        write.line_indented(f'static constexpr std::string_view kBaseId = "{base.id}";')
        write.line_empty()
        _doc(write, "Connect with an API key; cache_seconds > 0 enables the read cache.", indent=1)
        write.line_indented("explicit Airtable(const std::string& api_key, double cache_seconds = 0.0)")
        write.line_indented(": client_(std::make_shared<AirtableClient>(std::string(kBaseId), api_key, cache_seconds)) {}", indent=2)
        _doc(write, "Adopt an existing client (custom transport, shared cache).", indent=1)
        write.line_indented("explicit Airtable(std::shared_ptr<AirtableClient> client) : client_(std::move(client)) {}")
        write.line_empty()
        for table in tables:
            prefix = _table_type_prefix(table)
            _doc(write, f"{sanitize_string(table.name)}", indent=1)
            write.line_indented(f"{prefix}Table {_table_accessor(table)}() const {{ return {prefix}Table(client_); }}")
        write.line_empty()
        write.line_indented("const std::shared_ptr<AirtableClient>& client() const { return client_; }")
        write.line_indented("void invalidate_all_caches() { client_->invalidate_all_caches(); }")
        write.line_empty()
        write.line_indented("private:", indent=0)
        write.line_indented("std::shared_ptr<AirtableClient> client_;")
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

    F3: static copy, options, field types, dict-table facades, entry point.
    Models (F4), formula helpers (F7), and runtime transpilation (F8) land
    with their features.
    """

    output_folder = reset_folder(output_folder)

    exclude_static: list[str] = []
    if not formulas:
        exclude_static.extend(_FORMULA_STATIC_FILES)
    copy_static_files(output_folder, "cpp", exclude=exclude_static or None)

    write_options(base, output_folder)
    write_field_types(base, output_folder)
    if formulas:
        write_formula_helpers(base, output_folder)
    write_models(base, output_folder, formulas=formulas, runtime=runtime, flatten=flatten)
    if wrappers:
        write_tables(base, output_folder)
        write_main(base, output_folder)

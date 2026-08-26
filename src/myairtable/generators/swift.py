"""Swift code generator.

Generates an SPM-consumable source tree:

  <output>/
  ├── Dynamic/
  │   ├── Options/{Table}Options.swift       — per-table select-option enums
  │   ├── Types/{Table}Fields.swift          — per-table field ID/name constants
  │   └── Tables/{Table}Table.swift          — per-table DictTable accessors
  ├── Static/                                — copied verbatim from static/swift/
  └── Airtable.swift                         — top-level actor + table accessors

F3 scope (this file): dict-only path. ORM models + linked records + formula
helpers land in F4–F7.

Note: The generator does NOT emit a Package.swift — matches the other
languages (the user configures their own SPM manifest).
"""

from pathlib import Path

from rich import print

from ..formulas.formula_flattener import flatten_formula_for_transpilation
from ..formulas.formula_transpiler import transpile_table_formulas
from ..meta import Base, Table
from ..utils.helpers import (
    Paths,
    copy_static_files,
    deduplicate_identifiers,
    deduplicated_field_property_map,
    deduplicated_table_prefix_map,
    reset_folder,
    sanitize_string,
)
from ..utils.write_to_swift_file import WriteToSwiftFile, _choice_to_case, _swift_ident
from ..verbosity import verbose

# =============================================================================
# Swift layout
# =============================================================================

# Subdirectory names inside the output folder. Swift doesn't care about
# directory casing when compiling (`swift build` globs recursively), so we
# keep lowercase here to match the other language generators and to stay
# safe on case-sensitive filesystems (Linux CI).
_DIR_DYNAMIC = Paths.DYNAMIC  # "dynamic"
_DIR_STATIC = Paths.STATIC  # "static"
_DIR_OPTIONS = "options"
_DIR_TYPES = Paths.TYPES  # "types"
_DIR_TABLES = Paths.TABLES  # "tables"
_DIR_MODELS = Paths.MODELS  # "models"
_DIR_FORMULAS = Paths.FORMULAS  # "formulas"


def _create_swift_dynamic_subdir(output_folder: Path, subdir: str) -> Path:
    path = output_folder / _DIR_DYNAMIC / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


# =============================================================================
# Naming helpers
# =============================================================================


def _deduplicate_cases(cases: list[str]) -> list[str]:
    """Ensure enum case names are unique by appending V2, V3, etc."""
    return deduplicate_identifiers(cases, suffix="V")


def _view_case(view_name: str) -> str:
    """Convert a view name to a Swift enum case (lowerCamelCase)."""
    return _choice_to_case(view_name)


def _escape_string_literal(text: str) -> str:
    """Escape a string for inclusion in a Swift string literal (" delimiter).

    Backslash FIRST (so later escapes aren't double-escaped), then the quote
    and the control characters Airtable names/descriptions can carry.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


# Member names a generated model may not use. Swift puts stored properties and
# methods in ONE namespace, so a field named "Copy" against the local `copy()`
# verb is `error: invalid redeclaration of 'copy()'` -- a hard build break, in
# both a plain `final class` and the `@Observable` one the generator emits.
# `copy()` must be an inherent class member (only an initializer can seed the
# computed `let`s it carries), so it cannot be moved to a protocol extension to
# dodge this. Colliding field names get a `Field` suffix, then re-deduplicate.
#
# `id` / `createdTime` are not listed: they are pre-renamed upstream by
# `sanitize_reserved_names`.
#
# `projectAttachmentsForCopy` is a module-scope function in Types.swift that the
# emitted `copy()` initializer calls UNQUALIFIED. Swift resolves an unqualified
# name to a member of the enclosing type before a module-scope one, and there is
# no way to qualify the call (the free function lives in whatever module the user
# drops the generated code into, whose name the generator does not know). So a
# field named "Project Attachments For Copy" would resolve the call to a
# `[AirtableAttachment]?` property and fail with "not callable".
_SWIFT_RESERVED_MODEL_MEMBERS = frozenset({"copy", "projectAttachmentsForCopy"})


def _field_property_map(table: Table) -> dict[str, str]:
    """`{field_id: deduplicated lowerCamelCase property name}` for one table.

    Every writer (models, Fields consts, Create*Fields, Filters, evaluate*
    methods, and the transpiler's field_name_map) consumes this same map so
    colliding field names ("My Field" / "my field") deduplicate consistently
    to `myField` / `myFieldV2`. Names colliding with a generated model member
    are suffixed. Keyword backticking is applied at call sites.
    """
    raw = deduplicated_field_property_map(table)
    adjusted = [f"{name}Field" if name in _SWIFT_RESERVED_MODEL_MEMBERS else name for name in raw.values()]
    deduped = deduplicate_identifiers(adjusted, suffix="V")
    return {field_id: name for field_id, name in zip(raw.keys(), deduped)}


def _table_type_prefix(table: Table) -> str:
    """PascalCase prefix used for generated types (e.g. `Primary`), deduplicated per base.

    Recomputed from the base's table list on each call (cheap and deterministic),
    so every writer — file names, type names, and `Airtable` accessors — agrees.
    """
    return deduplicated_table_prefix_map(table.base)[table.id]


def _table_property(table: Table) -> str:
    """lowerCamelCase property used on the Airtable actor (e.g. `primary`)."""
    pascal = _table_type_prefix(table)
    if not pascal:
        return "table"
    return _swift_ident(pascal[0].lower() + pascal[1:])


# =============================================================================
# region WRITERS
# =============================================================================


def write_options(base: Base, output_folder: Path) -> None:
    """Generate one Swift enum per select field per table.

    Layout: `Dynamic/Options/{Table}Options.swift`. Emits:
        enum {OptionsName}: String, Codable, Sendable, CaseIterable {
            case foo = "Foo"
            case bar = "Bar"
        }
    One file per table so per-table imports remain tight.
    """
    options_dir = _create_swift_dynamic_subdir(output_folder, _DIR_OPTIONS)

    for table in base.tables:
        select_fields = table.select_fields()
        if not select_fields:
            continue

        file_name = f"{_table_type_prefix(table)}Options.swift"
        with WriteToSwiftFile(path=options_dir / file_name) as write:
            write.import_stmt("Foundation")
            write.line_empty()

            for field in select_fields:
                choices = field.select_options()
                if not choices:
                    continue

                enum_name = field.options_name()
                raw_cases = [_choice_to_case(c) for c in choices]
                cases = _deduplicate_cases(raw_cases)

                write.doc_comment(f"Options for `{sanitize_string(field.name)}`")
                write.enum_open(
                    enum_name,
                    raw_type="String",
                    conformances=["Codable", "Sendable", "CaseIterable"],
                )
                for choice, case in zip(choices, cases):
                    write.enum_case(case, raw_value=_escape_string_literal(choice))
                write.close()
                write.line_empty()


def write_field_types(base: Base, output_folder: Path) -> None:
    """Generate `{Table}Fields` + `{Table}View` types.

    Layout: `Dynamic/Types/{Table}Fields.swift`. Each table gets:
        enum {Table}Fields {
            static let primaryKeyId = "fld..."        // field ID
            static let primaryKeyName = "Primary"     // field name
            static let allIds: [String] = [...]
            static let nameToId: [String: String] = [...]
            static func idByName(_ name: String) -> String?
            static func nameById(_ id: String) -> String?
        }
        enum {Table}View: String, Codable, Sendable { ... }        // if views
        enum Create{Table}Fields { ... }                           // writable only
    """
    types_dir = _create_swift_dynamic_subdir(output_folder, _DIR_TYPES)

    for table in base.tables:
        prop_names = _field_property_map(table)
        fields_name = f"{_table_type_prefix(table)}Fields"
        file_name = f"{fields_name}.swift"
        with WriteToSwiftFile(path=types_dir / file_name) as write:
            write.import_stmt("Foundation")
            write.line_empty()

            # ---------- All-fields enum ----------
            write.doc_comment(f"Field ID + name constants for `{sanitize_string(table.name)}`.")
            write.enum_open(fields_name)

            # Per-field id + name constants
            for field in table.fields:
                escaped_name = _escape_string_literal(sanitize_string(field.name))
                camel = prop_names[field.id]
                prop = _swift_ident(camel)
                id_name = _swift_ident(f"{camel}Id")
                name_name = _swift_ident(f"{camel}Name")
                write.doc_comment(f"`{sanitize_string(field.name)}` (field ID)", indent=1)
                write.line_indented(f'public static let {id_name}: String = "{field.id}"')
                write.doc_comment(f"`{sanitize_string(field.name)}` (field name)", indent=1)
                write.line_indented(f'public static let {name_name}: String = "{escaped_name}"')
                # Silence the unused-var lint when the loop doesn't reference prop.
                _ = prop
            write.line_empty()

            # allIds
            ids_list = ", ".join(f'"{f.id}"' for f in table.fields)
            write.doc_comment("All field IDs, in schema order.", indent=1)
            write.line_indented(f"public static let allIds: [String] = [{ids_list}]")
            write.line_empty()

            # nameToId dictionary — used by Fields for dual ID/name access.
            write.doc_comment("Mapping from Airtable field name → field ID.", indent=1)
            write.line_indented("public static let nameToId: [String: String] = [")
            for field in table.fields:
                escaped_name = _escape_string_literal(sanitize_string(field.name))
                write.line_indented(f'"{escaped_name}": "{field.id}",', indent=2)
            write.line_indented("]")
            write.line_empty()

            # idToName dictionary (inverse of nameToId)
            write.doc_comment("Mapping from field ID → Airtable field name.", indent=1)
            write.line_indented("public static let idToName: [String: String] = [")
            for field in table.fields:
                escaped_name = _escape_string_literal(sanitize_string(field.name))
                write.line_indented(f'"{field.id}": "{escaped_name}",', indent=2)
            write.line_indented("]")
            write.line_empty()

            # idByName / nameById helpers
            write.doc_comment("Look up a field ID by Airtable field name.", indent=1)
            write.line_indented("public static func idByName(_ name: String) -> String? {")
            write.line_indented("return nameToId[name]", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment("Look up an Airtable field name by field ID.", indent=1)
            write.line_indented("public static func nameById(_ id: String) -> String? {")
            write.line_indented("return idToName[id]", indent=2)
            write.line_indented("}")
            write.close()  # enum {Table}Fields
            write.line_empty()

            # ---------- Views ----------
            if table.views:
                view_name = f"{_table_type_prefix(table)}View"
                raw_cases = [_view_case(v.name) for v in table.views]
                view_cases = _deduplicate_cases(raw_cases)
                write.doc_comment(f"Views for `{sanitize_string(table.name)}`.")
                write.enum_open(
                    view_name,
                    raw_type="String",
                    conformances=["Codable", "Sendable", "CaseIterable"],
                )
                for view, case in zip(table.views, view_cases):
                    write.doc_comment(f"`{sanitize_string(view.name)}` ({view.type})", indent=1)
                    write.enum_case(case, raw_value=view.id)
                write.close()
                write.line_empty()

            # ---------- Writable (create) fields ----------
            writable_fields = [f for f in table.fields if not f.is_computed()]
            if writable_fields:
                create_name = f"Create{_table_type_prefix(table)}Fields"
                write.doc_comment(f"Writable field ID + name constants for `{sanitize_string(table.name)}`.")
                write.enum_open(create_name)
                for field in writable_fields:
                    escaped_name = _escape_string_literal(sanitize_string(field.name))
                    camel = prop_names[field.id]
                    id_name = _swift_ident(f"{camel}Id")
                    name_name = _swift_ident(f"{camel}Name")
                    write.doc_comment(f"`{sanitize_string(field.name)}` (field ID)", indent=1)
                    write.line_indented(f'public static let {id_name}: String = "{field.id}"')
                    write.doc_comment(f"`{sanitize_string(field.name)}` (field name)", indent=1)
                    write.line_indented(f'public static let {name_name}: String = "{escaped_name}"')
                write.close()
                write.line_empty()


def write_models(base: Base, output_folder: Path, formulas: bool = True, runtime: bool = True, flatten: bool = False) -> None:
    """Generate per-table `@Observable final class {Table}Model`.

    Layout: `dynamic/models/{Table}Model.swift`. Each file contains a single
    class:
      - `let` for computed fields (server-owned; decoded, never encoded)
      - `var` for writable fields (user-settable)
      - designated `init(writableField: Type? = nil, ...)` for constructing
        unsaved records — hand these to `airtable.<table>.create(_:)`
      - manual `CodingKeys` + `init(from:)` + `encode(to:)` (writable-only)
      - `@ObservationIgnored _snapshot` for dirty tracking
      - protocol impls: `toRecord()`, `takeSnapshot()`, `dirtyFields()`

    `@Observable`'s macro-generated observation tracking breaks automatic
    `Codable` synthesis — hence the manual `init(from:)`/`encode(to:)`.
    Phase 0 gate (`TestCodableObservableModel.swift`) validates this pattern.
    """
    models_dir = _create_swift_dynamic_subdir(output_folder, _DIR_MODELS)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        prop_names = _field_property_map(table)
        model_name = f"{prefix}Model"
        file_name = f"{model_name}.swift"

        # Split fields into computed (read-only) and writable (read-write).
        computed_fields = [f for f in table.fields if f.is_computed()]
        writable_fields = [f for f in table.fields if not f.is_computed()]

        # Pre-transpile formula fields for this table (F8.10).
        transpiled_formulas: dict[str, str] = {}
        raw_formulas: dict[str, str] = {}
        if runtime:
            formula_field_ids = table.formula_field_ids()
            # Same deduplicated names as the emitted properties, so formula
            # references resolve to declarations that actually exist.
            field_name_map = {f.id: _swift_ident(prop_names[f.id]) for f in table.fields}
            raw_formulas = {f.id: f.options.formula for f in table.fields if f.is_formula() and f.options and f.options.formula}
            if flatten and raw_formulas:
                formula_map_tuple = table.base.get_formula_field_map_tuple()
                raw_formulas = {fid: flatten_formula_for_transpilation(f, fid, formula_map_tuple) for fid, f in raw_formulas.items()}
            if raw_formulas:
                transpiled_formulas = transpile_table_formulas(raw_formulas, "swift", field_name_map, formula_field_ids)

        with WriteToSwiftFile(path=models_dir / file_name) as write:
            write.import_stmt("Foundation")
            write.import_stmt("Observation")
            write.line_empty()

            # ================================================================
            # {Table}Model — @Observable class
            # ================================================================
            write.doc_comment(f"`@Observable` model for the `{sanitize_string(table.name)}` Airtable table.")
            write.attribute("Observable")
            write.class_open(model_name, conformances=["AirtableModel"])

            # Static: tableId + formula filters
            write.line_indented(f'public static let tableId: String = "{table.id}"')
            if formulas:
                filters_name = f"{prefix}Filters"
                write.doc_comment(
                    f'Formula builder for filtering. Usage: `{model_name}.f.primaryKey.equals("x")`.',
                    indent=1,
                )
                write.line_indented(f"public static let f = {filters_name}()")
            write.line_empty()

            # ---------- Identity properties ----------
            write.mark_section("Identity", indent=1)
            write.doc_comment("Airtable record ID. `nil` for unsaved models.", indent=1)
            write.line_indented("public let id: RecordId?")
            write.doc_comment("Server-assigned creation timestamp.", indent=1)
            write.line_indented("public let createdTime: Date?")
            write.line_empty()

            # ---------- Computed fields (let) ----------
            if computed_fields:
                write.mark_section("Computed fields (server-owned)", indent=1)
                for field in computed_fields:
                    write.property_docstring(field, table, indent_level=1)
                    prop = _swift_ident(prop_names[field.id])
                    ty = field.swift_type()
                    # Every field is optional — Airtable responses are sparse.
                    write.line_indented(f"public let {prop}: {ty}?")
                write.line_empty()

            # ---------- Writable fields (var) ----------
            if writable_fields:
                write.mark_section("Writable fields", indent=1)
                for field in writable_fields:
                    write.property_docstring(field, table, indent_level=1)
                    prop = _swift_ident(prop_names[field.id])
                    ty = field.swift_type()
                    write.line_indented(f"public var {prop}: {ty}?")
                write.line_empty()

            # ---------- Snapshot for dirty tracking ----------
            write.mark_section("Dirty tracking", indent=1)
            write.doc_comment(
                "Snapshot of field values at last save/decode. Used by `dirtyFields()` to compute partial updates. NOT observation-tracked.",
                indent=1,
            )
            write.line_indented("@ObservationIgnored")
            write.line_indented("private var _snapshot: [String: AirtableJSONValue] = [:]")
            write.line_empty()

            # ---------- Attached client (for model-side save/fetch/delete) ----------
            write.doc_comment(
                "Client attached by the table that produced this model. Set by "
                "`OrmTable` after decode so `save()`/`fetch()`/`delete()` can "
                "call back without a table argument. `nil` when the model was "
                "decoded directly from JSON (no table).",
                indent=1,
            )
            write.line_indented("@ObservationIgnored")
            write.line_indented("public var _attachedClient: AirtableClient?")
            write.line_empty()

            # ---------- Designated initializer (for unsaved models) ----------
            write.mark_section("Construction", indent=1)
            write.doc_comment(
                "Construct an unsaved model. All writable fields are optional "
                "with `nil` defaults. Pass to `airtable.<table>.create(_:)` to "
                "insert. `id`, `createdTime`, and computed fields are "
                "server-owned and initialized to nil.",
                indent=1,
            )
            if writable_fields:
                write.line_indented("public init(")
                init_params: list[str] = []
                for field in writable_fields:
                    prop = _swift_ident(prop_names[field.id])
                    ty = field.swift_type()
                    init_params.append(f"{prop}: {ty}? = nil")
                for i, param in enumerate(init_params):
                    suffix = "," if i < len(init_params) - 1 else ""
                    write.line_indented(f"{param}{suffix}", indent=2)
                write.line_indented(") {")
            else:
                write.line_indented("public init() {")
            # Identity + computed fields: server-owned, initialized to nil.
            write.line_indented("self.id = nil", indent=2)
            write.line_indented("self.createdTime = nil", indent=2)
            for field in computed_fields:
                prop = _swift_ident(prop_names[field.id])
                write.line_indented(f"self.{prop} = nil", indent=2)
            # Writable fields pulled from init params.
            for field in writable_fields:
                prop = _swift_ident(prop_names[field.id])
                write.line_indented(f"self.{prop} = {prop}", indent=2)
            write.line_indented("}")
            write.line_empty()

            # ---------- CodingKeys ----------
            write.mark_section("Codable", indent=1)
            write.line_indented("private enum CodingKeys: String, CodingKey {")
            write.line_indented("case id", indent=2)
            write.line_indented("case createdTime", indent=2)
            write.line_indented("case fields", indent=2)
            write.line_indented("}")
            write.line_empty()

            # FieldsCodingKeys — maps Swift property → Airtable field ID.
            write.line_indented("private enum FieldsCodingKeys: String, CodingKey {")
            for field in table.fields:
                prop = _swift_ident(prop_names[field.id])
                write.line_indented(f'case {prop} = "{field.id}"', indent=2)
            write.line_indented("}")
            write.line_empty()

            # ---------- init(from decoder:) ----------
            write.line_indented("public required init(from decoder: any Decoder) throws {")
            write.line_indented("let c = try decoder.container(keyedBy: CodingKeys.self)", indent=2)
            write.line_indented("self.id = try c.decodeIfPresent(String.self, forKey: .id)", indent=2)
            write.line_indented(
                "self.createdTime = try c.decodeIfPresent(Date.self, forKey: .createdTime)",
                indent=2,
            )
            # Try nested container; fall back to all-nil if missing.
            write.line_indented(
                "if let fields = try? c.nestedContainer(keyedBy: FieldsCodingKeys.self, forKey: .fields) {",
                indent=2,
            )
            for field in table.fields:
                prop = _swift_ident(prop_names[field.id])
                ty = field.swift_type()
                write.line_indented(
                    f"self.{prop} = try fields.decodeIfPresent({ty}.self, forKey: .{prop})",
                    indent=3,
                )
            write.line_indented("} else {", indent=2)
            for field in table.fields:
                prop = _swift_ident(prop_names[field.id])
                write.line_indented(f"self.{prop} = nil", indent=3)
            write.line_indented("}", indent=2)
            write.line_indented("self.takeSnapshot()", indent=2)
            write.line_indented("}")
            write.line_empty()

            # ---------- encode(to:) ----------
            # We encode only writable fields in the `fields` container — these
            # are what Airtable will accept on create/update. Computed fields
            # are server-owned and rejected on write. id/createdTime go at the
            # top level for informational round-tripping.
            write.line_indented("public func encode(to encoder: any Encoder) throws {")
            write.line_indented("var c = encoder.container(keyedBy: CodingKeys.self)", indent=2)
            write.line_indented("try c.encodeIfPresent(id, forKey: .id)", indent=2)
            write.line_indented("try c.encodeIfPresent(createdTime, forKey: .createdTime)", indent=2)
            # Always emit the nested fields container — toRecord() round-trips
            # via JSONEncoder and relies on it.
            write.line_indented(
                "var fields = c.nestedContainer(keyedBy: FieldsCodingKeys.self, forKey: .fields)",
                indent=2,
            )
            for field in writable_fields:
                prop = _swift_ident(prop_names[field.id])
                write.line_indented(f"try fields.encodeIfPresent({prop}, forKey: .{prop})", indent=2)
            write.line_indented("}")
            write.line_empty()

            # ---------- AirtableModel protocol methods ----------
            write.mark_section("AirtableModel", indent=1)

            # toRecord() — round-trip through JSON to produce a dict keyed by field ID.
            write.doc_comment("All current field values as a dict keyed by field ID.", indent=1)
            write.line_indented("public func toRecord() -> [String: AirtableJSONValue] {")
            write.line_indented("let encoder = JSONEncoder()", indent=2)
            write.line_indented("encoder.dateEncodingStrategy = .iso8601", indent=2)
            write.line_indented("guard let data = try? encoder.encode(self) else { return [:] }", indent=2)
            write.line_indented(
                "struct Envelope: Decodable { let fields: [String: AirtableJSONValue] }",
                indent=2,
            )
            write.line_indented("let decoder = JSONDecoder()", indent=2)
            write.line_indented("decoder.dateDecodingStrategy = .iso8601", indent=2)
            write.line_indented(
                "guard let env = try? decoder.decode(Envelope.self, from: data) else { return [:] }",
                indent=2,
            )
            write.line_indented("return env.fields", indent=2)
            write.line_indented("}")
            write.line_empty()

            # takeSnapshot()
            write.doc_comment(
                "Record a snapshot of all field values. Called after decode/save.",
                indent=1,
            )
            write.line_indented("public func takeSnapshot() {")
            write.line_indented("self._snapshot = toRecord()", indent=2)
            write.line_indented("}")
            write.line_empty()

            # dirtyFields()
            write.doc_comment(
                "Writable fields whose values differ from the last snapshot. Used by `OrmTable.updateOne` for partial-update payloads.",
                indent=1,
            )
            write.line_indented("public func dirtyFields() -> [String: AirtableJSONValue] {")
            write.line_indented("let current = toRecord()", indent=2)
            # Writable field IDs — computed ones are never sent on update.
            writable_ids = ", ".join(f'"{f.id}"' for f in writable_fields)
            write.line_indented(f"let writableIds: Set<String> = [{writable_ids}]", indent=2)
            write.line_indented("var dirty: [String: AirtableJSONValue] = [:]", indent=2)
            write.line_indented("for id in writableIds {", indent=2)
            write.line_indented(
                "if current[id] != _snapshot[id] { dirty[id] = current[id] ?? .null }",
                indent=3,
            )
            write.line_indented("}", indent=2)
            write.line_indented("return dirty", indent=2)
            write.line_indented("}")

            # ---------- Local copy verb ----------
            #
            # An INHERENT member, not a protocol extension next to save/fetch/delete.
            # Two reasons, and both are forced:
            #   1. Computed fields are `public let`, and only an initializer can seed a
            #      `let` — so carrying them (contract item 5) needs an initializer that
            #      knows the concrete stored properties, which only this class has.
            #   2. `copy()` has to return `{Table}Model`, not `Self`, to read the way
            #      save()/fetch() already do at a call site.
            # The `Field`-suffix rename in _SWIFT_RESERVED_MODEL_MEMBERS is what keeps a
            # field named "Copy" from becoming `invalid redeclaration of 'copy()'`.
            write.line_empty()
            write.mark_section("copy", indent=1)
            write.doc_comment(
                [
                    "A detached, unsaved copy of this record — mutate it and hand it to",
                    "`airtable.<table>.create(_:)`. Performs **no I/O**.",
                    "",
                    "That is the whole difference from the table's `duplicate(_:)`, which re-reads",
                    "the source from Airtable before POSTing it. A copy is only as fresh as the",
                    "model in hand, which matters most for attachments: their signed URLs expire.",
                    "",
                    "The copy carries every cell value, computed ones included, so it reads like",
                    "its source. Those values never reach the wire — `create(_:)` sends",
                    "`toRecord()`, and `encode(to:)` only ever writes the writable fields. The",
                    "cost is that a carried computed value is semantically stale on the copy: a",
                    "formula over `RECORD_ID()` shows the SOURCE's id until the copy is saved and",
                    "re-read.",
                    "",
                    "It carries no record identity. `id` and `createdTime` are `nil` and no",
                    "snapshot is taken, so `isNew` is true and the copy inserts. Getting this",
                    "wrong is silent in both directions — a carried `id` makes `save()` PATCH the",
                    "source row, and a carried snapshot makes `dirtyFields()` diff to empty.",
                    "`_attachedClient` is deliberately the one thing kept, so `create(_:)` /",
                    "`save()` on the copy work without re-threading a table.",
                    "",
                    "Writable attachment cells are projected to `{url, filename}` here, because",
                    "`create(_:)` does not project and Airtable rejects a server-returned",
                    "attachment object on insert. A computed attachment-shaped cell keeps its full",
                    "metadata: it is never written back.",
                    "",
                    "Linked records are copied as-is. Airtable links are many-to-many, so the copy",
                    "is added alongside the original on the far side; the source's links are",
                    "untouched.",
                ],
                indent=1,
            )
            write.line_indented(f"public func copy() -> {model_name} {{")
            write.line_indented(f"return {model_name}(_copyOf: self)", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment(
                [
                    "Seeds a fresh instance from `source`, including the computed `let`s that no",
                    "other initializer can reach. `private` so no caller gains a way to forge a",
                    "computed value — the server-owned invariant survives.",
                    "",
                    "Every cell is assigned by value. Swift's field carriers are all value types",
                    "(`String`, the numerics, `Date`, arrays, `AirtableAttachment`,",
                    "`AirtableJSONValue`, `MaybeSpecialOrError`, `VecOrValue`), so contract item 7",
                    "— no shared mutable state with the source — falls out of assignment itself;",
                    "there is nothing here to deep-copy by hand.",
                    "",
                    "`_snapshot` is deliberately not assigned and `takeSnapshot()` deliberately not",
                    "called: its `[:]` default IS the fully-dirty state a to-be-inserted record",
                    "needs.",
                ],
                indent=1,
            )
            write.line_indented(f"private init(_copyOf source: {model_name}) {{")
            # Identity: cleared, exactly as the designated initializer does it.
            write.line_indented("self.id = nil", indent=2)
            write.line_indented("self.createdTime = nil", indent=2)
            for field in computed_fields:
                prop = _swift_ident(prop_names[field.id])
                write.line_indented(f"self.{prop} = source.{prop}", indent=2)
            for field in writable_fields:
                prop = _swift_ident(prop_names[field.id])
                # Attachment-typed WRITABLE cells only. A computed lookup of an
                # attachment field renders as VecOrValue<MaybeSpecialOrError<
                # AirtableAttachment>> and is handled by the loop above, unprojected.
                if "AirtableAttachment" in field.swift_type():
                    write.line_indented(f"self.{prop} = projectAttachmentsForCopy(source.{prop})", indent=2)
                else:
                    write.line_indented(f"self.{prop} = source.{prop}", indent=2)
            write.line_indented("self._attachedClient = source._attachedClient", indent=2)
            write.line_indented("}")

            # ---------- Runtime formula evaluation methods (F8.10) ----------
            if transpiled_formulas:
                write.line_empty()
                write.mark_section("Runtime formula evaluation", indent=1)
                for field in table.fields:
                    if field.id not in transpiled_formulas:
                        continue
                    prop = _swift_ident(prop_names[field.id])
                    formula_code = transpiled_formulas[field.id]
                    raw = raw_formulas.get(field.id, "")
                    preview = sanitize_string(raw).replace("\n", " ")[:80]
                    write.doc_comment(f"Evaluate formula locally: `{preview}...`", indent=1)
                    # Method name derived from the deduplicated property name so
                    # colliding fields get evaluateMyField / evaluateMyFieldV2.
                    camel = prop_names[field.id]
                    method_pascal = camel[0].upper() + camel[1:] if camel else field.name_pascal()
                    write.line_indented(f"public func evaluate{method_pascal}() -> AirtableJSONValue {{")
                    write.line_indented(f"return {formula_code}", indent=2)
                    write.line_indented("}")

            write.close()  # end class


_SWIFT_FORMULA_CLASS_MAP = {
    "TextField": "FormulaTextField",
    "BooleanField": "FormulaBooleanField",
    "DateField": "FormulaDateField",
    "NumberField": "FormulaNumberField",
    "AttachmentsField": "FormulaAttachmentsField",
    "LookupField": "FormulaLookupField",
    "SingleSelectField": "FormulaSingleSelectField",
    "MultiSelectField": "FormulaMultiSelectField",
}


def write_formula_helpers(base: Base, output_folder: Path) -> None:
    """Generate per-table `{Table}Filters` struct accessed via `{Table}Model.f`.

    Layout: `dynamic/formulas/{Table}Filters.swift`. Each struct has one
    stored property per field, typed to the appropriate Formula*Field struct,
    plus an `id: FormulaId` for record-ID filters. A static `let f` on the
    model class is wired up separately (in write_models — TODO: emit later
    via a follow-up or inline the static property here).

    Shape matches the user's approved API:
        `PrimaryModel.f.primaryKey.equals("x")`
    """
    formulas_dir = _create_swift_dynamic_subdir(output_folder, _DIR_FORMULAS)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        prop_names = _field_property_map(table)
        filters_name = f"{prefix}Filters"
        file_name = f"{filters_name}.swift"

        with WriteToSwiftFile(path=formulas_dir / file_name) as write:
            write.import_stmt("Foundation")
            write.line_empty()

            write.doc_comment(f"Formula builder for `{sanitize_string(table.name)}`.")
            write.struct_open(filters_name, conformances=["Sendable"])

            # Record ID formula
            write.doc_comment("Record ID formula.", indent=1)
            write.line_indented("public let id: FormulaId")

            for field in table.fields:
                prop = _swift_ident(prop_names[field.id])
                formula_class = field.formula_class()
                swift_type = _SWIFT_FORMULA_CLASS_MAP.get(formula_class, "FormulaTextField")
                write.doc_comment(f"`{sanitize_string(field.name)}`", indent=1)
                write.line_indented(f"public let {prop}: {swift_type}")

            write.line_empty()

            # Init
            write.line_indented("public init() {")
            write.line_indented("self.id = FormulaId()", indent=2)
            for field in table.fields:
                prop = _swift_ident(prop_names[field.id])
                formula_class = field.formula_class()
                swift_type = _SWIFT_FORMULA_CLASS_MAP.get(formula_class, "FormulaTextField")
                write.line_indented(f'self.{prop} = {swift_type}("{field.id}")', indent=2)
            write.line_indented("}")

            write.close()


def write_tables(base: Base, output_folder: Path) -> None:
    """Generate per-table `{Table}Table` struct.

    The ORM is the default — `airtable.primary.getOne(id)` calls through to
    the typed `OrmTable<PrimaryModel>`. Raw-dict access lives under `.dict`
    for parity with the Rust target.

    Matches the Rust / TS / Py API shape (no `.orm` property).
    """
    tables_dir = _create_swift_dynamic_subdir(output_folder, _DIR_TABLES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        type_name = f"{prefix}Table"
        fields_name = f"{prefix}Fields"
        model_name = f"{prefix}Model"
        file_name = f"{type_name}.swift"
        with WriteToSwiftFile(path=tables_dir / file_name) as write:
            write.import_stmt("Foundation")
            write.line_empty()

            write.doc_comment(f"Accessor for the `{sanitize_string(table.name)}` Airtable table.")
            write.struct_open(type_name, conformances=["Sendable"])
            write.line_indented(f'public static let tableId: String = "{table.id}"')
            write.line_empty()

            # Stored properties: dict accessor + internal typed ORM that all
            # forwarded methods below delegate to.
            write.doc_comment("Raw (dict-style) access — decoded fields keyed by ID.", indent=1)
            write.line_indented("public let dict: DictTable")
            write.line_empty()
            write.line_indented("@usableFromInline")
            write.line_indented(f"internal let orm: OrmTable<{model_name}>")
            write.line_empty()

            write.line_indented("public init(client: AirtableClient) {")
            write.line_indented("self.dict = DictTable(", indent=2)
            write.line_indented("tableId: Self.tableId,", indent=3)
            write.line_indented(f"nameToId: {fields_name}.nameToId,", indent=3)
            write.line_indented("client: client", indent=3)
            write.line_indented(")", indent=2)
            write.line_indented("self.orm = OrmTable(", indent=2)
            write.line_indented("tableId: Self.tableId,", indent=3)
            write.line_indented("client: client", indent=3)
            write.line_indented(")", indent=2)
            write.line_indented("}")
            write.line_empty()

            # ---------- Forwarded ORM methods ----------
            write.mark_section("ORM access (default)", indent=1)

            # ----- get overloads -----
            write.doc_comment("Fetch one record by ID.", indent=1)
            write.line_indented("@inlinable")
            write.line_indented(f"public func get(_ recordId: String) async throws -> {model_name} {{")
            write.line_indented("try await orm.get(recordId)", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment("Fetch many records by ID (parallel, order preserved).", indent=1)
            write.line_indented("@inlinable")
            write.line_indented(f"public func get(_ recordIds: [String]) async throws -> [{model_name}] {{")
            write.line_indented("try await orm.get(recordIds)", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment(
                "Fetch records matching the query (paginates internally). Pass the default `AirtableQuery()` to fetch all.",
                indent=1,
            )
            write.line_indented("@inlinable")
            write.line_indented(f"public func get(_ query: AirtableQuery = AirtableQuery()) async throws -> [{model_name}] {{")
            write.line_indented("try await orm.get(query)", indent=2)
            write.line_indented("}")
            write.line_empty()

            # ----- create overloads -----
            write.doc_comment(
                f"Create one record. Pass a fresh model built with its initializer (e.g. `{model_name}(...)`); only writable fields are sent.",
                indent=1,
            )
            write.line_indented("@inlinable")
            write.line_indented(f"public func create(_ model: {model_name}) async throws -> {model_name} {{")
            write.line_indented("try await orm.create(model)", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment(
                "Create many records. Chunks into Airtable's 10-per-call batch limit.",
                indent=1,
            )
            write.line_indented("@inlinable")
            write.line_indented(f"public func create(_ models: [{model_name}]) async throws -> [{model_name}] {{")
            write.line_indented("try await orm.create(models)", indent=2)
            write.line_indented("}")
            write.line_empty()

            # ----- duplicate overloads -----
            # Unlike the create/update forwarders above, these thread `typecast` through:
            # `orm` is internal, so a flag the forwarder drops is unreachable from generated
            # code entirely. (Backfilling the other verbs is tracked separately.)
            write.doc_comment(
                "Copy a record into a brand-new record. Writable fields are copied verbatim, "
                "computed fields are recalculated by Airtable, and the source is left untouched.",
                indent=1,
            )
            write.line_indented("@inlinable")
            write.line_indented(f"public func duplicate(_ model: {model_name}, typecast: Bool = false) async throws -> {model_name} {{")
            write.line_indented("try await orm.duplicate(model, typecast: typecast)", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment(
                "Copy many records into brand-new records. Chunks into Airtable's 10-per-call batch limit.",
                indent=1,
            )
            write.line_indented("@inlinable")
            write.line_indented(f"public func duplicate(_ models: [{model_name}], typecast: Bool = false) async throws -> [{model_name}] {{")
            write.line_indented("try await orm.duplicate(models, typecast: typecast)", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment("Read the record with this ID and copy it (one extra GET).", indent=1)
            write.line_indented("@inlinable")
            write.line_indented(f"public func duplicate(_ recordId: String, typecast: Bool = false) async throws -> {model_name} {{")
            write.line_indented("try await orm.duplicate(recordId, typecast: typecast)", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment("Read the records with these IDs and copy them, preserving order.", indent=1)
            write.line_indented("@inlinable")
            write.line_indented(f"public func duplicate(_ recordIds: [String], typecast: Bool = false) async throws -> [{model_name}] {{")
            write.line_indented("try await orm.duplicate(recordIds, typecast: typecast)", indent=2)
            write.line_indented("}")
            write.line_empty()

            # ----- update overloads -----
            write.doc_comment(
                "Update one model. Sends only fields that changed since last snapshot.",
                indent=1,
            )
            write.line_indented("@inlinable")
            write.line_indented(f"public func update(_ model: {model_name}) async throws -> {model_name} {{")
            write.line_indented("try await orm.update(model)", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment(
                "Update many models. Each model's dirty-field diff is used; chunks into Airtable's 10-per-call batch limit.",
                indent=1,
            )
            write.line_indented("@inlinable")
            write.line_indented(f"public func update(_ models: [{model_name}]) async throws -> [{model_name}] {{")
            write.line_indented("try await orm.update(models)", indent=2)
            write.line_indented("}")
            write.line_empty()

            # ----- updateFields (explicit id + field dict) -----
            write.doc_comment(
                "Update a record with an explicit field dict (bypasses dirty tracking).",
                indent=1,
            )
            write.line_indented("@inlinable")
            write.line_indented(
                "public func updateFields(\n"
                "        _ recordId: String,\n"
                "        _ fields: [String: AirtableJSONValue]\n"
                f"    ) async throws -> {model_name} {{"
            )
            write.line_indented("try await orm.updateFields(recordId, fields)", indent=2)
            write.line_indented("}")
            write.line_empty()

            # ----- upsert -----
            write.doc_comment(
                "Upsert a record, matching on the supplied field IDs. Returns the model plus `wasCreated` indicating insert vs update.",
                indent=1,
            )
            write.line_indented("@inlinable")
            write.line_indented(
                "public func upsert(\n"
                f"        _ model: {model_name},\n"
                "        matchFieldsToMerge: [String]\n"
                f"    ) async throws -> (model: {model_name}, wasCreated: Bool) {{"
            )
            write.line_indented(
                "try await orm.upsert(model, matchFieldsToMerge: matchFieldsToMerge)",
                indent=2,
            )
            write.line_indented("}")
            write.line_empty()

            # ----- delete overloads -----
            write.doc_comment("Delete one record by ID.", indent=1)
            write.line_indented("@inlinable")
            write.line_indented("public func delete(_ recordId: String) async throws {")
            write.line_indented("try await orm.delete(recordId)", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment(
                "Delete many records by ID. Chunks into Airtable's 10-per-call batch limit.",
                indent=1,
            )
            write.line_indented("@inlinable")
            write.line_indented("public func delete(_ recordIds: [String]) async throws {")
            write.line_indented("try await orm.delete(recordIds)", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment("Delete the record referenced by this model's `id`.", indent=1)
            write.line_indented("@inlinable")
            write.line_indented(f"public func delete(_ model: {model_name}) async throws {{")
            write.line_indented("try await orm.delete(model)", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment("Delete many records by passing their models. Chunks by ID.", indent=1)
            write.line_indented("@inlinable")
            write.line_indented(f"public func delete(_ models: [{model_name}]) async throws {{")
            write.line_indented("try await orm.delete(models)", indent=2)
            write.line_indented("}")
            write.line_empty()

            # ----- Cache control -----
            # Not @inlinable: OrmTable.client is `internal` (not
            # @usableFromInline), and cache invalidation isn't hot-path.
            write.doc_comment("Drop cached reads for this table.", indent=1)
            write.line_indented("public func invalidateCache() async {")
            write.line_indented("await orm.client.invalidateCache(tableId: Self.tableId)", indent=2)
            write.line_indented("}")

            write.close()


def write_main(base: Base, output_folder: Path) -> None:
    """Generate `Airtable.swift` — top-level actor exposing one table accessor per table.

    Shape:
        public struct Airtable: Sendable {
            public let client: AirtableClient
            public let primary: PrimaryTable
            public let secondary: SecondaryTable
            ...
            public init(baseId: String, apiKey: String) { ... }
        }
    """
    main_path = output_folder / "Airtable.swift"
    with WriteToSwiftFile(path=main_path) as write:
        write.import_stmt("Foundation")
        write.line_empty()

        write.doc_comment(f"Entry point for Airtable base `{base.id}`.")
        write.doc_comment("Construct with an API key + base ID; access tables as properties.")
        write.struct_open("Airtable", conformances=["Sendable"])
        write.line_indented("public let client: AirtableClient")
        write.line_empty()

        for table in base.tables:
            prop = _table_property(table)
            type_name = f"{_table_type_prefix(table)}Table"
            write.doc_comment(
                f"`{sanitize_string(table.name)}` — table ID `{table.id}`",
                indent=1,
            )
            write.line_indented(f"public let {prop}: {type_name}")
        write.line_empty()

        # init(baseId:apiKey:cacheSeconds:)
        write.doc_comment(
            "Construct with an API key and optional TTL caching. `cacheSeconds: 0` "
            "(the default) disables caching; any positive value enables it across "
            "all table reads.",
            indent=1,
        )
        write.line_indented('public init(baseId: String = "' + base.id + '", apiKey: String, cacheSeconds: TimeInterval = 0) {')
        write.line_indented(
            "self.client = AirtableClient(baseId: baseId, apiKey: apiKey, cacheSeconds: cacheSeconds)",
            indent=2,
        )
        for table in base.tables:
            prop = _table_property(table)
            type_name = f"{_table_type_prefix(table)}Table"
            write.line_indented(f"self.{prop} = {type_name}(client: self.client)", indent=2)
        write.line_indented("}")

        # init(client:) — inject a pre-configured actor.
        write.line_empty()
        write.doc_comment("Dependency-injection constructor for tests + advanced setups.", indent=1)
        write.line_indented("public init(client: AirtableClient) {")
        write.line_indented("self.client = client", indent=2)
        for table in base.tables:
            prop = _table_property(table)
            type_name = f"{_table_type_prefix(table)}Table"
            write.line_indented(f"self.{prop} = {type_name}(client: client)", indent=2)
        write.line_indented("}")

        # Public cache-invalidation passthroughs
        write.line_empty()
        write.doc_comment("Drop every cached payload across every table.", indent=1)
        write.line_indented("public func invalidateAllCaches() async {")
        write.line_indented("await client.invalidateAllCaches()", indent=2)
        write.line_indented("}")

        write.close()


# endregion


# =============================================================================
# MAIN
# =============================================================================


def generate_swift(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    wrappers: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate Swift code from Airtable base metadata."""
    print("Generating Swift code")

    # Reset the two top-level subdirectories the generator owns. Leaving
    # everything else (if any) alone keeps user-added files safe.
    reset_folder(output_folder / _DIR_DYNAMIC)
    reset_folder(output_folder / _DIR_STATIC)

    exclude_static: list[str] = []
    if not runtime:
        exclude_static.append("AirtableRuntime.swift")
    if not formulas:
        exclude_static.append("Formula.swift")

    copy_static_files(output_folder, "swift", exclude=exclude_static or None)
    if verbose:
        print("[dim] - Swift static files copied.[/]")

    write_options(base, output_folder)
    if verbose:
        print("[dim] - Swift options generated.[/]")

    write_field_types(base, output_folder)
    if verbose:
        print("[dim] - Swift field types generated.[/]")

    if formulas:
        write_formula_helpers(base, output_folder)
        if verbose:
            print("[dim] - Swift formula helpers generated.[/]")

    write_models(base, output_folder, formulas=formulas, runtime=runtime, flatten=flatten)
    if verbose:
        print("[dim] - Swift models generated.[/]")

    if wrappers:
        write_tables(base, output_folder)
        if verbose:
            print("[dim] - Swift table wrappers generated.[/]")

        write_main(base, output_folder)
        if verbose:
            print("[dim] - Swift main Airtable.swift generated.[/]")

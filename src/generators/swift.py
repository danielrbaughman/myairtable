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

from ..meta import Base, Table
from ..utils import timer
from ..utils.helpers import (
    Paths,
    copy_static_files,
    reset_folder,
    sanitize_string,
)
from ..utils.verbose import verbose
from ..utils.write_to_swift_file import WriteToSwiftFile, _choice_to_case, _swift_ident

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
    """Ensure enum case names are unique by appending v2, v3, etc."""
    counts: dict[str, int] = {}
    out: list[str] = []
    for name in cases:
        counts[name] = counts.get(name, 0) + 1
        if counts[name] > 1:
            out.append(f"{name}V{counts[name]}")
        else:
            out.append(name)
    return out


def _view_case(view_name: str) -> str:
    """Convert a view name to a Swift enum case (lowerCamelCase)."""
    return _choice_to_case(view_name)


def _escape_string_literal(text: str) -> str:
    """Escape a string for inclusion in a Swift string literal (" delimiter)."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _table_type_prefix(table: Table) -> str:
    """PascalCase prefix used for generated types (e.g. `Primary`)."""
    return table.name_pascal()


def _table_property(table: Table) -> str:
    """lowerCamelCase property used on the Airtable actor (e.g. `primary`)."""
    pascal = table.name_pascal()
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
                camel = field.name_camel()
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
                    camel = field.name_camel()
                    id_name = _swift_ident(f"{camel}Id")
                    name_name = _swift_ident(f"{camel}Name")
                    write.doc_comment(f"`{sanitize_string(field.name)}` (field ID)", indent=1)
                    write.line_indented(f'public static let {id_name}: String = "{field.id}"')
                    write.doc_comment(f"`{sanitize_string(field.name)}` (field name)", indent=1)
                    write.line_indented(f'public static let {name_name}: String = "{escaped_name}"')
                write.close()
                write.line_empty()


def write_tables(base: Base, output_folder: Path) -> None:
    """Generate per-table `{Table}Table` struct exposing a `DictTable` accessor.

    F3 emits dict-only tables. F4 adds the `.orm` accessor.
    """
    tables_dir = _create_swift_dynamic_subdir(output_folder, _DIR_TABLES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        type_name = f"{prefix}Table"
        fields_name = f"{prefix}Fields"
        file_name = f"{type_name}.swift"
        with WriteToSwiftFile(path=tables_dir / file_name) as write:
            write.import_stmt("Foundation")
            write.line_empty()

            write.doc_comment(f"Accessor for the `{sanitize_string(table.name)}` Airtable table.")
            write.struct_open(type_name, conformances=["Sendable"])
            write.line_indented(f'public static let tableId: String = "{table.id}"')
            write.line_empty()

            # The raw-dict accessor — the only shape in F3. Typed .orm lands in F4.
            write.doc_comment("Raw (dict-style) access — decoded fields keyed by ID.", indent=1)
            write.line_indented("public let dict: DictTable")
            write.line_empty()

            write.line_indented("public init(client: AirtableClient) {")
            write.line_indented(
                "self.dict = DictTable(",
                indent=2,
            )
            write.line_indented("tableId: Self.tableId,", indent=3)
            write.line_indented(f"nameToId: {fields_name}.nameToId,", indent=3)
            write.line_indented("client: client", indent=3)
            write.line_indented(")", indent=2)
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

        # init(baseId:apiKey:)
        write.line_indented('public init(baseId: String = "' + base.id + '", apiKey: String) {')
        write.line_indented(
            "self.client = AirtableClient(baseId: baseId, apiKey: apiKey)",
            indent=2,
        )
        for table in base.tables:
            prop = _table_property(table)
            type_name = f"{_table_type_prefix(table)}Table"
            write.line_indented(f"self.{prop} = {type_name}(client: self.client)", indent=2)
        write.line_indented("}")

        # init(client:) — inject a pre-configured actor.
        write.line_empty()
        write.line_indented("public init(client: AirtableClient) {")
        write.line_indented("self.client = client", indent=2)
        for table in base.tables:
            prop = _table_property(table)
            type_name = f"{_table_type_prefix(table)}Table"
            write.line_indented(f"self.{prop} = {type_name}(client: client)", indent=2)
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
    # Formulas/wrappers/runtime/flatten are accepted for parity with other
    # generators; F3 doesn't act on them yet (F4–F8 introduce the wiring).
    _ = formulas, wrappers, runtime, flatten

    print("Generating Swift code")

    # Reset the two top-level subdirectories the generator owns. Leaving
    # everything else (if any) alone keeps user-added files safe.
    reset_folder(output_folder / _DIR_DYNAMIC)
    reset_folder(output_folder / _DIR_STATIC)

    exclude_static: list[str] = []
    if not runtime:
        # AirtableRuntime.swift will land in F8; kept here so the flag plumbing
        # is in place on day one.
        exclude_static.append("AirtableRuntime.swift")

    with timer.timer("Swift: copy_static_files"):
        copy_static_files(output_folder, "swift", exclude=exclude_static or None)
        if verbose:
            print("[dim] - Swift static files copied.[/]")

    with timer.timer("Swift: write_options"):
        write_options(base, output_folder)
        if verbose:
            print("[dim] - Swift options generated.[/]")

    with timer.timer("Swift: write_field_types"):
        write_field_types(base, output_folder)
        if verbose:
            print("[dim] - Swift field types generated.[/]")

    with timer.timer("Swift: write_tables"):
        write_tables(base, output_folder)
        if verbose:
            print("[dim] - Swift table wrappers generated.[/]")

    with timer.timer("Swift: write_main"):
        write_main(base, output_folder)
        if verbose:
            print("[dim] - Swift main Airtable.swift generated.[/]")

"""Kotlin code generator.

Generates an idiomatic Kotlin/JVM source tree (flat `myairtable` package):

  <output>/
  ├── dynamic/
  │   ├── options/{Table}Options.kt        — per-table select-option enum classes
  │   ├── types/{Table}Fields.kt           — per-table field ID/name constants
  │   └── tables/{Table}Table.kt           — per-table DictTable accessors
  ├── static/                              — copied verbatim from static/kotlin/
  └── Airtable.kt                          — top-level class + table accessors

K-F3 scope (this file): dict-only path. ORM models + linked records + formula
helpers land in K-F4..K-F8.

Note: the generator does NOT emit build files — matches the other languages
(the consumer configures their own Gradle build with the kotlinx.serialization
plugin applied).

Design reference: .beads/kotlin-plan-v2.md
"""

from pathlib import Path

from rich import print

from ..meta import Base, Table
from ..utils.helpers import (
    Paths,
    copy_static_files,
    reset_folder,
    sanitize_string,
)
from ..utils.verbose import verbose
from ..utils.write_to_kotlin_file import WriteToKotlinFile, _choice_to_entry, _kotlin_ident

# =============================================================================
# Kotlin layout
# =============================================================================

_DIR_DYNAMIC = Paths.DYNAMIC  # "dynamic"
_DIR_STATIC = Paths.STATIC  # "static"
_DIR_OPTIONS = Paths.OPTIONS  # "options"
_DIR_TYPES = Paths.TYPES  # "types"
_DIR_TABLES = Paths.TABLES  # "tables"
_DIR_MODELS = Paths.MODELS  # "models"
_DIR_FORMULAS = Paths.FORMULAS  # "formulas"


def _create_kotlin_dynamic_subdir(output_folder: Path, name: str) -> Path:
    path = output_folder / _DIR_DYNAMIC / name
    path.mkdir(parents=True, exist_ok=True)
    return path


# =============================================================================
# Naming helpers
# =============================================================================


def _deduplicate_entries(entries: list[str]) -> list[str]:
    """Ensure enum entry names are unique by appending _V2, _V3, etc."""
    counts: dict[str, int] = {}
    out: list[str] = []
    for name in entries:
        counts[name] = counts.get(name, 0) + 1
        if counts[name] > 1:
            out.append(f"{name}_V{counts[name]}")
        else:
            out.append(name)
    return out


def _escape_string_literal(text: str) -> str:
    """Escape a string for inclusion in a Kotlin string literal (" delimiter)."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("\n", "\\n")


def _table_type_prefix(table: Table) -> str:
    """PascalCase prefix used for generated types (e.g. `Primary`)."""
    return table.name_pascal()


def _table_property(table: Table) -> str:
    """lowerCamelCase property used on the Airtable class (e.g. `primary`)."""
    pascal = table.name_pascal()
    if not pascal:
        return "table"
    return _kotlin_ident(pascal[0].lower() + pascal[1:])


# =============================================================================
# region WRITERS
# =============================================================================


def write_options(base: Base, output_folder: Path) -> None:
    """Generate one Kotlin enum class per select field per table.

    Layout: `dynamic/options/{Table}Options.kt`. Emits:
        @Serializable
        enum class {OptionsName} {
            @SerialName("Foo")
            FOO,
            ...
        }
    One file per table so regeneration stays per-table localized.
    """
    options_dir = _create_kotlin_dynamic_subdir(output_folder, _DIR_OPTIONS)

    for table in base.tables:
        select_fields = table.select_fields()
        if not select_fields:
            continue

        file_name = f"{_table_type_prefix(table)}Options.kt"
        with WriteToKotlinFile(path=options_dir / file_name) as write:
            write.package_decl()
            write.line_empty()
            write.import_stmt("kotlinx.serialization.SerialName")
            write.import_stmt("kotlinx.serialization.Serializable")
            write.line_empty()

            for field in select_fields:
                choices = field.select_options()
                if not choices:
                    continue

                enum_name = field.options_name()
                raw_entries = [_choice_to_entry(c) for c in choices]
                entries = _deduplicate_entries(raw_entries)

                write.doc_comment(f"Options for `{sanitize_string(field.name)}`")
                write.annotation("Serializable")
                write.enum_class_open(enum_name)
                for index, (choice, entry) in enumerate(zip(choices, entries)):
                    write.enum_entry(
                        entry,
                        serial_name=choice,
                        indent=1,
                        last=index == len(entries) - 1,
                    )
                write.close()
                write.line_empty()


def write_field_types(base: Base, output_folder: Path) -> None:
    """Generate `{Table}Fields` + `{Table}View` + `Create{Table}Fields` types.

    Layout: `dynamic/types/{Table}Fields.kt`. Each table gets:
        object {Table}Fields {
            const val primaryKeyId: String = "fld..."
            const val primaryKeyName: String = "Primary"
            val allIds: List<String> = listOf(...)
            val nameToId: Map<String, String> = mapOf(...)
            val idToName: Map<String, String> = mapOf(...)
            fun idByName(name: String): String? = ...
            fun nameById(id: String): String? = ...
        }
        enum class {Table}View(val id: String) { ... }     // if views
        object Create{Table}Fields { ... }                 // writable only
    """
    types_dir = _create_kotlin_dynamic_subdir(output_folder, _DIR_TYPES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        fields_name = f"{prefix}Fields"
        file_name = f"{fields_name}.kt"
        with WriteToKotlinFile(path=types_dir / file_name) as write:
            write.package_decl()
            write.line_empty()

            # ---------- All-fields object ----------
            write.doc_comment(f"Field ID + name constants for `{sanitize_string(table.name)}`.")
            write.object_open(fields_name)

            for field in table.fields:
                escaped_name = _escape_string_literal(sanitize_string(field.name))
                camel = field.name_camel()
                id_name = _kotlin_ident(f"{camel}Id")
                name_name = _kotlin_ident(f"{camel}Name")
                write.doc_comment(f"`{sanitize_string(field.name)}` (field ID)", indent=1)
                write.line_indented(f'const val {id_name}: String = "{field.id}"')
                write.doc_comment(f"`{sanitize_string(field.name)}` (field name)", indent=1)
                write.line_indented(f'const val {name_name}: String = "{escaped_name}"')
            write.line_empty()

            ids_list = ", ".join(f'"{f.id}"' for f in table.fields)
            write.doc_comment("All field IDs, in schema order.", indent=1)
            write.line_indented(f"val allIds: List<String> = listOf({ids_list})")
            write.line_empty()

            write.doc_comment("Mapping from Airtable field name → field ID.", indent=1)
            write.line_indented("val nameToId: Map<String, String> =")
            write.line_indented("mapOf(", indent=2)
            for field in table.fields:
                escaped_name = _escape_string_literal(sanitize_string(field.name))
                write.line_indented(f'"{escaped_name}" to "{field.id}",', indent=3)
            write.line_indented(")", indent=2)
            write.line_empty()

            write.doc_comment("Mapping from field ID → Airtable field name.", indent=1)
            write.line_indented("val idToName: Map<String, String> =")
            write.line_indented("mapOf(", indent=2)
            for field in table.fields:
                escaped_name = _escape_string_literal(sanitize_string(field.name))
                write.line_indented(f'"{field.id}" to "{escaped_name}",', indent=3)
            write.line_indented(")", indent=2)
            write.line_empty()

            write.doc_comment("Look up a field ID by Airtable field name.", indent=1)
            write.line_indented("fun idByName(name: String): String? = nameToId[name]")
            write.line_empty()
            write.doc_comment("Look up an Airtable field name by field ID.", indent=1)
            write.line_indented("fun nameById(id: String): String? = idToName[id]")
            write.close()
            write.line_empty()

            # ---------- Views ----------
            if table.views:
                view_name = f"{prefix}View"
                raw_entries = [_choice_to_entry(v.name) for v in table.views]
                view_entries = _deduplicate_entries(raw_entries)
                write.doc_comment(f"Views for `{sanitize_string(table.name)}`.")
                write.line(f"enum class {view_name}(")
                write.line_indented("val id: String,")
                write.line(") {")
                for index, (view, entry) in enumerate(zip(table.views, view_entries)):
                    write.doc_comment(f"`{sanitize_string(view.name)}` ({view.type})", indent=1)
                    terminator = ";" if index == len(view_entries) - 1 else ","
                    write.line_indented(f'{entry}("{view.id}"){terminator}')
                write.close()
                write.line_empty()

            # ---------- Writable (create) fields ----------
            writable_fields = [f for f in table.fields if not f.is_computed()]
            if writable_fields:
                create_name = f"Create{prefix}Fields"
                write.doc_comment(f"Writable field ID + name constants for `{sanitize_string(table.name)}`.")
                write.object_open(create_name)
                for field in writable_fields:
                    escaped_name = _escape_string_literal(sanitize_string(field.name))
                    camel = field.name_camel()
                    id_name = _kotlin_ident(f"{camel}Id")
                    name_name = _kotlin_ident(f"{camel}Name")
                    write.doc_comment(f"`{sanitize_string(field.name)}` (field ID)", indent=1)
                    write.line_indented(f'const val {id_name}: String = "{field.id}"')
                    write.doc_comment(f"`{sanitize_string(field.name)}` (field name)", indent=1)
                    write.line_indented(f'const val {name_name}: String = "{escaped_name}"')
                write.close()
                write.line_empty()


def write_tables(base: Base, output_folder: Path) -> None:
    """Generate per-table `{Table}Table` class (K-F3: dict accessor only).

    The typed ORM forwarding methods land with K-F4; raw-dict access lives
    under `.dict` for parity with the Rust target.
    """
    tables_dir = _create_kotlin_dynamic_subdir(output_folder, _DIR_TABLES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        type_name = f"{prefix}Table"
        fields_name = f"{prefix}Fields"
        file_name = f"{type_name}.kt"
        with WriteToKotlinFile(path=tables_dir / file_name) as write:
            write.package_decl()
            write.line_empty()

            write.doc_comment(f"Accessor for the `{sanitize_string(table.name)}` Airtable table.")
            write.line(f"class {type_name}(")
            write.line_indented("client: AirtableClient,")
            write.line(") {")
            write.companion_object_open()
            write.line_indented(f'const val TABLE_ID: String = "{table.id}"', indent=2)
            write.close(indent=1)
            write.line_empty()

            write.doc_comment("Raw (dict-style) access — decoded fields keyed by ID.", indent=1)
            write.line_indented(f"val dict: DictTable = DictTable(tableId = TABLE_ID, nameToId = {fields_name}.nameToId, client = client)")
            write.close()


def write_main(base: Base, output_folder: Path) -> None:
    """Generate `Airtable.kt` — top-level class exposing one accessor per table.

    Shape:
        class Airtable(val client: AirtableClient) {
            val primary: PrimaryTable = PrimaryTable(client)
            ...
            constructor(baseId: String = "app...", apiKey: String, cacheSeconds: Double = 0.0)
            suspend fun invalidateAllCaches()
        }
    """
    main_path = output_folder / "Airtable.kt"
    with WriteToKotlinFile(path=main_path) as write:
        write.package_decl()
        write.line_empty()

        write.doc_comment(
            [
                f"Entry point for Airtable base `{base.id}`.",
                "",
                "Construct with an API key + base ID; access tables as properties.",
            ]
        )
        write.line("class Airtable(")
        write.line_indented("val client: AirtableClient,")
        write.line(") {")

        for table in base.tables:
            prop = _table_property(table)
            type_name = f"{_table_type_prefix(table)}Table"
            write.doc_comment(f"`{sanitize_string(table.name)}` — table ID `{table.id}`", indent=1)
            write.line_indented(f"val {prop}: {type_name} = {type_name}(client)")
        write.line_empty()

        write.doc_comment(
            [
                "Construct with an API key and optional TTL caching. `cacheSeconds = 0.0`",
                "(the default) disables caching; any positive value enables it across",
                "all table reads.",
            ],
            indent=1,
        )
        write.line_indented("constructor(")
        write.line_indented(f'baseId: String = "{base.id}",', indent=2)
        write.line_indented("apiKey: String,", indent=2)
        write.line_indented("cacheSeconds: Double = 0.0,", indent=2)
        write.line_indented(") : this(AirtableClient(baseId = baseId, apiKey = apiKey, cacheSeconds = cacheSeconds))")
        write.line_empty()

        write.doc_comment("Drop every cached payload across every table.", indent=1)
        write.line_indented("suspend fun invalidateAllCaches() = client.invalidateAllCaches()")

        write.close()


# endregion


# =============================================================================
# region MAIN
# =============================================================================


def generate_kotlin(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    wrappers: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate Kotlin code from Airtable base metadata."""
    print("Generating Kotlin code")

    # Reset the two top-level subdirectories the generator owns. Leaving
    # everything else (if any) alone keeps user-added files safe.
    reset_folder(output_folder / _DIR_DYNAMIC)
    reset_folder(output_folder / _DIR_STATIC)

    exclude_static: list[str] = []
    if not runtime:
        exclude_static.append("AirtableRuntime.kt")
    if not formulas:
        exclude_static.append("Formula.kt")

    copy_static_files(output_folder, "kotlin", exclude=exclude_static or None)
    if verbose:
        print("[dim] - Kotlin static files copied.[/]")

    write_options(base, output_folder)
    if verbose:
        print("[dim] - Kotlin options generated.[/]")

    write_field_types(base, output_folder)
    if verbose:
        print("[dim] - Kotlin field types generated.[/]")

    if wrappers:
        write_tables(base, output_folder)
        if verbose:
            print("[dim] - Kotlin table wrappers generated.[/]")

        write_main(base, output_folder)
        if verbose:
            print("[dim] - Kotlin main Airtable.kt generated.[/]")

    print("[dim] - Kotlin generation complete.[/]")


# endregion

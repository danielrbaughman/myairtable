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


def write_models(base: Base, output_folder: Path, formulas: bool = True, runtime: bool = True, flatten: bool = False) -> None:
    """Generate per-table `{Table}Model` class.

    Layout: `dynamic/models/{Table}Model.kt`. Shape (plan §2.3.1, validated by
    the Phase 0 gate TestSerializableModel.kt):

        @file:UseSerializers(AirtableInstantSerializer::class, AirtableDurationSerializer::class)
        @Serializable
        class {Table}Model(
            @SerialName("fldX") val computedField: T? = null,   // computed: val
            @SerialName("fldY") var writableField: T? = null,   // writable: var
        ) : AirtableModel {
            @Transient override var id / createdTime / attachedClient
            @Transient private var snapshot
            toCreateFields() / toRecord() / takeSnapshot() / dirtyFields()
        }

    The kotlinx plugin serializer decodes only the record's `fields` object;
    create/update payloads come from the hand-rolled writable-only builders.
    """
    _ = formulas, runtime, flatten  # evaluate-method emission lands in K-F8
    models_dir = _create_kotlin_dynamic_subdir(output_folder, _DIR_MODELS)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        model_name = f"{prefix}Model"
        file_name = f"{model_name}.kt"
        writable_fields = [f for f in table.fields if not f.is_computed()]

        with WriteToKotlinFile(path=models_dir / file_name) as write:
            write.comment("ktlint-disable — generated code is exempt from lint by design")
            write.line("@file:UseSerializers(AirtableInstantSerializer::class, AirtableDurationSerializer::class)")
            write.line_empty()
            write.package_decl()
            write.line_empty()
            write.import_stmt("kotlinx.serialization.SerialName")
            write.import_stmt("kotlinx.serialization.Serializable")
            write.import_stmt("kotlinx.serialization.Transient")
            write.import_stmt("kotlinx.serialization.UseSerializers")
            write.import_stmt("kotlinx.serialization.json.JsonElement")
            write.import_stmt("kotlinx.serialization.json.JsonNull")
            write.import_stmt("java.time.Instant")
            write.import_stmt("kotlin.time.Duration")
            write.line_empty()

            write.doc_comment(
                [
                    f"Typed model for the `{sanitize_string(table.name)}` Airtable table.",
                    "",
                    "Computed fields are `val` (server-owned, decode-only); writable fields",
                    "are `var`. All default to `null`, so creation reads naturally with",
                    f"named arguments: `{model_name}(...)`.",
                ]
            )
            write.annotation("Serializable")
            write.line(f"class {model_name}(")
            for field in table.fields:
                write.property_docstring(field, table, indent_level=1)
                write.serial_name(field.id, indent=1)
                keyword = "var" if not field.is_computed() else "val"
                prop = _kotlin_ident(field.name_camel())
                write.line_indented(f"{keyword} {prop}: {field.kotlin_type()}? = null,")
            write.line(") : AirtableModel {")

            write.companion_object_open()
            write.line_indented(f'const val TABLE_ID: String = "{table.id}"', indent=2)
            write.close(indent=1)
            write.line_empty()

            write.line_indented("@Transient")
            write.line_indented("override var id: RecordId? = null")
            write.line_empty()
            write.line_indented("@Transient")
            write.line_indented("override var createdTime: Instant? = null")
            write.line_empty()
            write.line_indented("@Transient")
            write.line_indented("override var attachedClient: AirtableClient? = null")
            write.line_empty()
            write.line_indented("@Transient")
            write.line_indented("private var snapshot: Map<String, JsonElement> = emptyMap()")
            write.line_empty()

            write.line_indented("override val tableId: String get() = TABLE_ID")
            write.line_empty()

            # toCreateFields — writable only
            write.doc_comment("Non-null writable field values keyed by field ID (create payloads).", indent=1)
            write.line_indented("override fun toCreateFields(): Map<String, JsonElement> =")
            write.line_indented("buildMap {", indent=2)
            for field in writable_fields:
                prop = _kotlin_ident(field.name_camel())
                write.line_indented(f'{prop}?.let {{ put("{field.id}", V(it)) }}', indent=3)
            write.line_indented("}", indent=2)
            write.line_empty()

            # toRecord — all fields
            write.doc_comment("All non-null field values keyed by field ID.", indent=1)
            write.line_indented("override fun toRecord(): Map<String, JsonElement> =")
            write.line_indented("buildMap {", indent=2)
            for field in table.fields:
                prop = _kotlin_ident(field.name_camel())
                write.line_indented(f'{prop}?.let {{ put("{field.id}", V(it)) }}', indent=3)
            write.line_indented("}", indent=2)
            write.line_empty()

            # snapshot + dirty
            write.line_indented("override fun takeSnapshot() {")
            write.line_indented("snapshot = toCreateFields()", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment(
                [
                    "Changed-or-cleared writable fields since the last snapshot.",
                    "Cleared fields are emitted as JsonNull so the API clears them server-side.",
                ],
                indent=1,
            )
            write.line_indented("override fun dirtyFields(): Map<String, JsonElement> {")
            write.line_indented("val current = toCreateFields()", indent=2)
            write.line_indented("val dirty = mutableMapOf<String, JsonElement>()", indent=2)
            write.line_indented("for ((key, value) in current) if (snapshot[key] != value) dirty[key] = value", indent=2)
            write.line_indented("for (key in snapshot.keys) if (key !in current) dirty[key] = JsonNull", indent=2)
            write.line_indented("return dirty", indent=2)
            write.line_indented("}")

            write.close()


def write_tables(base: Base, output_folder: Path) -> None:
    """Generate per-table `{Table}Table` class.

    The ORM is the default — `airtable.primary.get(id)` calls through to the
    typed `OrmTable<PrimaryModel>`. Raw-dict access lives under `.dict` for
    parity with the Rust target. Matches the Rust / TS / Py API shape.
    """
    tables_dir = _create_kotlin_dynamic_subdir(output_folder, _DIR_TABLES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        type_name = f"{prefix}Table"
        fields_name = f"{prefix}Fields"
        model_name = f"{prefix}Model"
        file_name = f"{type_name}.kt"
        with WriteToKotlinFile(path=tables_dir / file_name) as write:
            write.package_decl()
            write.line_empty()
            write.import_stmt("kotlinx.serialization.json.JsonElement")
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
            write.line_empty()
            write.line_indented(f"private val orm: OrmTable<{model_name}> = OrmTable(TABLE_ID, {model_name}.serializer(), client)")
            write.line_empty()

            write.region("ORM access (default)", indent=1)
            write.line_empty()

            write.doc_comment("Fetch one record by ID.", indent=1)
            write.line_indented(f"suspend fun get(recordId: String): {model_name} = orm.get(recordId)")
            write.line_empty()
            write.doc_comment("Fetch many records by ID, in order.", indent=1)
            write.line_indented(f"suspend fun get(recordIds: List<String>): List<{model_name}> = orm.get(recordIds)")
            write.line_empty()
            write.doc_comment("Fetch records matching the query (paginates internally). Default fetches all.", indent=1)
            write.line_indented(f"suspend fun get(query: AirtableQuery = AirtableQuery()): List<{model_name}> = orm.get(query)")
            write.line_empty()

            write.doc_comment("Create one record from a fresh model (writable fields only).", indent=1)
            write.line_indented(f"suspend fun create(model: {model_name}): {model_name} = orm.create(model)")
            write.line_empty()
            write.doc_comment("Create many records. Chunks into Airtable's 10-per-call batch limit.", indent=1)
            write.line_indented(f"suspend fun create(models: List<{model_name}>): List<{model_name}> = orm.create(models)")
            write.line_empty()

            write.doc_comment("Update a model's dirty fields (diffed against its snapshot).", indent=1)
            write.line_indented(f"suspend fun update(model: {model_name}): {model_name} = orm.update(model)")
            write.line_empty()
            write.doc_comment("Update many models (dirty fields only). Chunked.", indent=1)
            write.line_indented(f"suspend fun update(models: List<{model_name}>): List<{model_name}> = orm.update(models)")
            write.line_empty()
            write.doc_comment("Update a record's fields directly by ID (no model required).", indent=1)
            write.line_indented(
                f"suspend fun updateFields(recordId: String, fields: Map<String, JsonElement>): {model_name} = orm.updateFields(recordId, fields)"
            )
            write.line_empty()

            write.doc_comment("Upsert a record, matching on the supplied field IDs.", indent=1)
            write.line_indented(
                f"suspend fun upsert(model: {model_name}, fieldsToMergeOn: List<String>): OrmTable.UpsertResult<{model_name}> = "
                "orm.upsert(model, fieldsToMergeOn)"
            )
            write.line_empty()

            write.doc_comment("Delete one record by ID.", indent=1)
            write.line_indented("suspend fun delete(recordId: String) = orm.delete(recordId)")
            write.line_empty()
            write.doc_comment("Delete many records by ID. Chunked.", indent=1)
            write.line_indented("suspend fun delete(recordIds: List<String>) = orm.delete(recordIds)")
            write.line_empty()
            write.doc_comment("Delete the record referenced by this model's id.", indent=1)
            write.line_indented(f"suspend fun delete(model: {model_name}) = orm.delete(model)")
            write.line_empty()
            write.doc_comment("Delete many records by passing their models.", indent=1)
            write.line_indented('@JvmName("deleteModels")')
            write.line_indented(f"suspend fun delete(models: List<{model_name}>) = orm.delete(models)")
            write.line_empty()

            write.endregion(indent=1)
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

    write_models(base, output_folder, formulas=formulas, runtime=runtime, flatten=flatten)
    if verbose:
        print("[dim] - Kotlin models generated.[/]")

    if wrappers:
        write_tables(base, output_folder)
        if verbose:
            print("[dim] - Kotlin table wrappers generated.[/]")

        write_main(base, output_folder)
        if verbose:
            print("[dim] - Kotlin main Airtable.kt generated.[/]")

    print("[dim] - Kotlin generation complete.[/]")


# endregion

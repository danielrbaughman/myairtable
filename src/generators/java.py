"""Java code generator.

Generates an idiomatic Java 21 source tree (flat `myairtable` package):

  <output>/
  ├── dynamic/
  │   ├── options/{Table}Options.java      — per-table select-option enums
  │   ├── types/{Table}Fields.java         — per-table field ID/name constants
  │   └── tables/{Table}Table.java         — per-table DictTable accessors
  ├── static/                              — copied verbatim from static/java/
  └── Airtable.java                        — top-level class + table accessors

J-F3 scope: dict-only path. ORM models + linked records + formula helpers
land in J-F4..J-F8.

Note: the generator does NOT emit build files — matches the other languages
(the consumer configures their own Gradle/Maven build with Jackson databind
on the classpath).

Design reference: .beads/java-plan-v2.md
"""

from pathlib import Path

from rich import print

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
from ..utils.verbose import verbose
from ..utils.write_to_java_file import (
    WriteToJavaFile,
    _choice_to_entry,
    _java_ident,
    _java_string_literal,
    _javadoc_escape,
)

# =============================================================================
# Java layout
# =============================================================================

_DIR_DYNAMIC = Paths.DYNAMIC  # "dynamic"
_DIR_STATIC = Paths.STATIC  # "static"
_DIR_OPTIONS = Paths.OPTIONS  # "options"
_DIR_TYPES = Paths.TYPES  # "types"
_DIR_TABLES = Paths.TABLES  # "tables"
_DIR_MODELS = Paths.MODELS  # "models"
_DIR_FORMULAS = Paths.FORMULAS  # "formulas"


def _create_java_dynamic_subdir(output_folder: Path, name: str) -> Path:
    path = output_folder / _DIR_DYNAMIC / name
    path.mkdir(parents=True, exist_ok=True)
    return path


# =============================================================================
# Naming helpers
# =============================================================================


def _deduplicate_entries(entries: list[str]) -> list[str]:
    """Ensure enum constant names are unique by appending _V2, _V3, etc."""
    return deduplicate_identifiers(entries, suffix="_V")


# Single shared Java string-literal escaper (also backs @JsonProperty values).
_escape_string_literal = _java_string_literal


def _field_property_map(table: Table) -> dict[str, str]:
    """`{field_id: deduplicated lowerCamelCase property name}` for one table.

    Every writer (models, Fields consts, Filters, evaluate* methods, and the
    transpiler's field_name_map) consumes this same map so colliding field
    names ("My Field" / "my field") deduplicate consistently to `myField` /
    `myFieldV2`. Keyword renaming (`_java_ident`) is applied at call sites.
    """
    return deduplicated_field_property_map(table)


def _table_type_prefix(table: Table) -> str:
    """PascalCase prefix used for generated types (e.g. `Primary`), deduplicated per base."""
    return deduplicated_table_prefix_map(table.base)[table.id]


def _table_property(table: Table) -> str:
    """lowerCamelCase accessor-method name on the Airtable class (e.g. `primary`)."""
    pascal = _table_type_prefix(table)
    if not pascal:
        return "table"
    return _java_ident(pascal[0].lower() + pascal[1:])


# =============================================================================
# region WRITERS
# =============================================================================


def write_options(base: Base, output_folder: Path) -> None:
    """Generate one Java enum per select field.

    Layout: `dynamic/options/{OptionsName}.java` — one FILE per enum (Java
    requires one public type per file, unlike the Kotlin per-table grouping).
    Emits:
        public enum {OptionsName} {
            FOO("Foo"),
            ...;
            @JsonValue value / @JsonCreator fromValue
        }
    """
    options_dir = _create_java_dynamic_subdir(output_folder, _DIR_OPTIONS)

    for table in base.tables:
        for field in table.select_fields():
            choices = field.select_options()
            if not choices:
                continue

            enum_name = field.options_name()
            raw_entries = [_choice_to_entry(c) for c in choices]
            entries = _deduplicate_entries(raw_entries)

            with WriteToJavaFile(path=options_dir / f"{enum_name}.java") as write:
                write.package_decl()
                write.line_empty()
                write.import_stmt("com.fasterxml.jackson.annotation.JsonCreator")
                write.import_stmt("com.fasterxml.jackson.annotation.JsonValue")
                write.line_empty()
                write.doc_comment(f"Options for {{@code {_javadoc_escape(sanitize_string(field.name))}}}")
                write.enum_open(enum_name)
                for index, (choice, entry) in enumerate(zip(choices, entries)):
                    write.enum_entry(entry, raw_value=choice, indent=1, last=index == len(entries) - 1)
                write.line_empty()
                write.line_indented("private final String value;")
                write.line_empty()
                write.line_indented(f"{enum_name}(String value) {{")
                write.line_indented("this.value = value;", indent=2)
                write.line_indented("}")
                write.line_empty()
                write.doc_comment("The raw Airtable choice string.", indent=1)
                write.annotation("JsonValue", indent=1)
                write.line_indented("public String value() {")
                write.line_indented("return value;", indent=2)
                write.line_indented("}")
                write.line_empty()
                write.doc_comment("Resolve an enum constant from its raw Airtable choice string.", indent=1)
                write.annotation("JsonCreator", indent=1)
                write.line_indented(f"public static {enum_name} fromValue(String value) {{")
                write.line_indented(f"for ({enum_name} option : values()) {{", indent=2)
                write.line_indented("if (option.value.equals(value)) {", indent=3)
                write.line_indented("return option;", indent=4)
                write.line_indented("}", indent=3)
                write.line_indented("}", indent=2)
                write.line_indented('throw new IllegalArgumentException("Unknown option: " + value);', indent=2)
                write.line_indented("}")
                write.close()


def write_field_types(base: Base, output_folder: Path) -> None:
    """Generate `{Table}Fields` + `{Table}View` + `Create{Table}Fields` types.

    Layout: `dynamic/types/` — one file per public type (Java requirement):
        {Table}Fields.java        — ID/name constants + nameToId/idToName maps
        {Table}View.java          — enum implementing AirtableView (if views)
        Create{Table}Fields.java  — writable-only constants
    Member names (camelCase `allIds`, `nameToId`, `idByName`...) deliberately
    match the Kotlin/Swift targets for cross-language parity.
    """
    types_dir = _create_java_dynamic_subdir(output_folder, _DIR_TYPES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        prop_names = _field_property_map(table)
        fields_name = f"{prefix}Fields"

        with WriteToJavaFile(path=types_dir / f"{fields_name}.java") as write:
            write.package_decl()
            write.line_empty()
            write.import_stmt("java.util.List")
            write.import_stmt("java.util.Map")
            write.line_empty()
            write.doc_comment(f"Field ID + name constants for {{@code {_javadoc_escape(sanitize_string(table.name))}}}.")
            write.class_open(fields_name)
            write.line_empty()
            write.line_indented(f"private {fields_name}() {{}}")
            write.line_empty()

            for field in table.fields:
                escaped_name = _escape_string_literal(sanitize_string(field.name))
                camel = prop_names[field.id]
                write.doc_comment(f"{{@code {_javadoc_escape(sanitize_string(field.name))}}} (field ID)", indent=1)
                write.line_indented(f'public static final String {_java_ident(f"{camel}Id")} = "{field.id}";')
                write.doc_comment(f"{{@code {_javadoc_escape(sanitize_string(field.name))}}} (field name)", indent=1)
                write.line_indented(f'public static final String {_java_ident(f"{camel}Name")} = "{escaped_name}";')
            write.line_empty()

            ids_list = ", ".join(f'"{f.id}"' for f in table.fields)
            write.doc_comment("All field IDs, in schema order.", indent=1)
            write.line_indented(f"public static final List<String> allIds = List.of({ids_list});")
            write.line_empty()

            write.doc_comment("Mapping from Airtable field name → field ID.", indent=1)
            write.line_indented("public static final Map<String, String> nameToId =")
            write.line_indented("Map.ofEntries(", indent=2)
            for index, field in enumerate(table.fields):
                escaped_name = _escape_string_literal(sanitize_string(field.name))
                comma = "" if index == len(table.fields) - 1 else ","
                write.line_indented(f'Map.entry("{escaped_name}", "{field.id}"){comma}', indent=3)
            write.line_indented(");", indent=2)
            write.line_empty()

            write.doc_comment("Mapping from field ID → Airtable field name.", indent=1)
            write.line_indented("public static final Map<String, String> idToName =")
            write.line_indented("Map.ofEntries(", indent=2)
            for index, field in enumerate(table.fields):
                escaped_name = _escape_string_literal(sanitize_string(field.name))
                comma = "" if index == len(table.fields) - 1 else ","
                write.line_indented(f'Map.entry("{field.id}", "{escaped_name}"){comma}', indent=3)
            write.line_indented(");", indent=2)
            write.line_empty()

            write.doc_comment("Look up a field ID by Airtable field name.", indent=1)
            write.line_indented("public static String idByName(String name) {")
            write.line_indented("return nameToId.get(name);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Look up an Airtable field name by field ID.", indent=1)
            write.line_indented("public static String nameById(String id) {")
            write.line_indented("return idToName.get(id);", indent=2)
            write.line_indented("}")
            write.close()

        # ---------- Views ----------
        if table.views:
            view_name = f"{prefix}View"
            raw_entries = [_choice_to_entry(v.name) for v in table.views]
            view_entries = _deduplicate_entries(raw_entries)
            with WriteToJavaFile(path=types_dir / f"{view_name}.java") as write:
                write.package_decl()
                write.line_empty()
                write.doc_comment(f"Views for {{@code {_javadoc_escape(sanitize_string(table.name))}}}.")
                write.enum_open(view_name, implements=["AirtableView"])
                for index, (view, entry) in enumerate(zip(table.views, view_entries)):
                    write.doc_comment(f"{{@code {_javadoc_escape(sanitize_string(view.name))}}} ({view.type})", indent=1)
                    write.enum_entry(entry, raw_value=view.id, indent=1, last=index == len(view_entries) - 1)
                write.line_empty()
                write.line_indented("private final String id;")
                write.line_empty()
                write.line_indented(f"{view_name}(String id) {{")
                write.line_indented("this.id = id;", indent=2)
                write.line_indented("}")
                write.line_empty()
                write.doc_comment("The Airtable view ID.", indent=1)
                write.annotation("Override", indent=1)
                write.line_indented("public String getId() {")
                write.line_indented("return id;", indent=2)
                write.line_indented("}")
                write.close()

        # ---------- Writable (create) fields ----------
        writable_fields = [f for f in table.fields if not f.is_computed()]
        if writable_fields:
            create_name = f"Create{prefix}Fields"
            with WriteToJavaFile(path=types_dir / f"{create_name}.java") as write:
                write.package_decl()
                write.line_empty()
                write.doc_comment(f"Writable field ID + name constants for {{@code {_javadoc_escape(sanitize_string(table.name))}}}.")
                write.class_open(create_name)
                write.line_empty()
                write.line_indented(f"private {create_name}() {{}}")
                write.line_empty()
                for field in writable_fields:
                    escaped_name = _escape_string_literal(sanitize_string(field.name))
                    camel = prop_names[field.id]
                    write.doc_comment(f"{{@code {_javadoc_escape(sanitize_string(field.name))}}} (field ID)", indent=1)
                    write.line_indented(f'public static final String {_java_ident(f"{camel}Id")} = "{field.id}";')
                    write.doc_comment(f"{{@code {_javadoc_escape(sanitize_string(field.name))}}} (field name)", indent=1)
                    write.line_indented(f'public static final String {_java_ident(f"{camel}Name")} = "{escaped_name}";')
                write.close()


def write_tables(base: Base, output_folder: Path) -> None:
    """Generate per-table `{Table}Table` class (J-F3: dict accessor only).

    Raw-dict access lives under `.dict()` for parity with the other targets;
    the typed ORM surface is added in J-F4.
    """
    tables_dir = _create_java_dynamic_subdir(output_folder, _DIR_TABLES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        type_name = f"{prefix}Table"
        fields_name = f"{prefix}Fields"
        with WriteToJavaFile(path=tables_dir / f"{type_name}.java") as write:
            write.package_decl()
            write.line_empty()
            write.doc_comment(f"Accessor for the {{@code {_javadoc_escape(sanitize_string(table.name))}}} Airtable table.")
            write.class_open(type_name)
            write.line_empty()
            write.line_indented(f'public static final String TABLE_ID = "{table.id}";')
            write.line_empty()
            write.line_indented("private final DictTable dict;")
            write.line_empty()
            write.line_indented(f"public {type_name}(AirtableClient client) {{")
            write.line_indented(f"this.dict = new DictTable(TABLE_ID, {fields_name}.nameToId, client);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Raw (dict-style) access — decoded fields keyed by ID.", indent=1)
            write.line_indented("public DictTable dict() {")
            write.line_indented("return dict;", indent=2)
            write.line_indented("}")
            write.close()


def write_main(base: Base, output_folder: Path) -> None:
    """Generate `Airtable.java` — top-level class exposing one accessor per table."""
    with WriteToJavaFile(path=output_folder / "Airtable.java") as write:
        write.package_decl()
        write.line_empty()
        write.doc_comment(
            [
                f"Entry point for Airtable base {{@code {base.id}}}.",
                "",
                "Construct with an API key + base ID; access tables via accessor methods.",
                "Requires Jackson databind on the classpath (jackson-datatype-jsr310 must",
                "NOT be registered — the runtime's AirtableJacksonModule owns Instant and",
                "Duration encoding).",
            ]
        )
        write.class_open("Airtable", implements=["AutoCloseable"])
        write.line_empty()
        write.doc_comment("The Airtable base ID this client was generated for.", indent=1)
        write.line_indented(f'public static final String BASE_ID = "{base.id}";')
        write.line_empty()
        write.line_indented("private final AirtableClient client;")
        for table in base.tables:
            prop = _table_property(table)
            type_name = f"{_table_type_prefix(table)}Table"
            write.line_indented(f"private final {type_name} {prop};")
        write.line_empty()

        write.doc_comment("Construct over an existing client.", indent=1)
        write.line_indented("public Airtable(AirtableClient client) {")
        write.line_indented("this.client = client;", indent=2)
        for table in base.tables:
            prop = _table_property(table)
            type_name = f"{_table_type_prefix(table)}Table"
            write.line_indented(f"this.{prop} = new {type_name}(client);", indent=2)
        write.line_indented("}")
        write.line_empty()

        write.doc_comment("Construct with an API key against the generated base, caching disabled.", indent=1)
        write.line_indented("public Airtable(String baseId, String apiKey) {")
        write.line_indented("this(new AirtableClient(baseId, apiKey));", indent=2)
        write.line_indented("}")
        write.line_empty()

        write.doc_comment(
            [
                "Construct with TTL caching. {@code cacheSeconds = 0.0} disables caching;",
                "any positive value enables it across all table reads.",
            ],
            indent=1,
        )
        write.line_indented("public Airtable(String baseId, String apiKey, double cacheSeconds) {")
        write.line_indented("this(new AirtableClient(baseId, apiKey, cacheSeconds));", indent=2)
        write.line_indented("}")
        write.line_empty()

        write.doc_comment("The underlying HTTP client.", indent=1)
        write.line_indented("public AirtableClient client() {")
        write.line_indented("return client;", indent=2)
        write.line_indented("}")
        write.line_empty()

        for table in base.tables:
            prop = _table_property(table)
            type_name = f"{_table_type_prefix(table)}Table"
            write.doc_comment(
                f"{{@code {_javadoc_escape(sanitize_string(table.name))}}} — table ID {{@code {table.id}}}",
                indent=1,
            )
            write.line_indented(f"public {type_name} {prop}() {{")
            write.line_indented(f"return {prop};", indent=2)
            write.line_indented("}")
            write.line_empty()

        write.doc_comment("Drop every cached payload across every table.", indent=1)
        write.line_indented("public void invalidateAllCaches() {")
        write.line_indented("client.invalidateAllCaches();", indent=2)
        write.line_indented("}")
        write.line_empty()

        write.doc_comment("Close the underlying client (if it owns its HTTP resources).", indent=1)
        write.annotation("Override", indent=1)
        write.line_indented("public void close() {")
        write.line_indented("client.close();", indent=2)
        write.line_indented("}")
        write.close()


# endregion


# =============================================================================
# region MAIN
# =============================================================================


def generate_java(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    wrappers: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate Java code from Airtable base metadata."""
    print("Generating Java code")

    # Reset the two top-level subdirectories the generator owns. Leaving
    # everything else (if any) alone keeps user-added files safe.
    reset_folder(output_folder / _DIR_DYNAMIC)
    reset_folder(output_folder / _DIR_STATIC)

    exclude_static: list[str] = []
    if not runtime:
        exclude_static.append("AirtableRuntime.java")

    copy_static_files(output_folder, "java", exclude=exclude_static or None)
    if verbose:
        print("[dim] - Java static files copied.[/]")

    write_options(base, output_folder)
    if verbose:
        print("[dim] - Java options generated.[/]")

    write_field_types(base, output_folder)
    if verbose:
        print("[dim] - Java field types generated.[/]")

    if wrappers:
        write_tables(base, output_folder)
        if verbose:
            print("[dim] - Java table wrappers generated.[/]")

        write_main(base, output_folder)
        if verbose:
            print("[dim] - Java main Airtable.java generated.[/]")

    # J-F4+: write_models; J-F7+: write_formula_helpers

    print("[dim] - Java generation complete.[/]")


# endregion

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

# Flipped in J-F7 when write_formula_helpers lands — until then models must not
# reference the (not yet generated) {Table}Filters classes.
_FORMULA_HELPERS_IMPLEMENTED = False


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


def write_models(base: Base, output_folder: Path, formulas: bool = True, runtime: bool = True, flatten: bool = False) -> None:
    """Generate per-table `{Table}Model` class.

    Layout: `dynamic/models/{Table}Model.java`. Shape (plan §2.3.1, validated
    by the Phase 0 gate TestPojoModel.java):

        public final class {Table}Model implements AirtableModel {
            @JsonProperty("fldX") [@JsonDeserialize(using=...)] private T computedField;  // getter only
            @JsonProperty("fldY") private T writableField;                                // getter + setter
            public {Table}Model() {}            // REQUIRED: Jackson creator
            // builder() + Builder over writable fields; fluent save()/fetch()/delete();
            // toCreateFields()/toRecord()/takeSnapshot()/dirtyFields()
        }

    Jackson decodes only the record's `fields` object (field-access mode);
    create/update payloads come from the hand-rolled writable-only builders.
    """
    models_dir = _create_java_dynamic_subdir(output_folder, _DIR_MODELS)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        prop_names = _field_property_map(table)
        model_name = f"{prefix}Model"
        writable_fields = [f for f in table.fields if not f.is_computed()]

        # Pre-transpile formula fields for this table (J8.8 wires the Java
        # transpiler arms; until then transpile_table_formulas has no "java"
        # support and this stays empty).
        transpiled_formulas: dict[str, str] = {}
        raw_formulas: dict[str, str] = {}
        if runtime and _transpiler_supports_java():
            formula_field_ids = table.formula_field_ids()
            field_name_map = {f.id: _java_ident(prop_names[f.id]) for f in table.fields}
            raw_formulas = {f.id: f.options.formula for f in table.fields if f.is_formula() and f.options and f.options.formula}
            if flatten and raw_formulas:
                formula_map_tuple = table.base.get_formula_field_map_tuple()
                raw_formulas = {fid: flatten_formula_for_transpilation(f, fid, formula_map_tuple) for fid, f in raw_formulas.items()}
            if raw_formulas:
                transpiled_formulas = transpile_table_formulas(raw_formulas, "java", field_name_map, formula_field_ids)

        with WriteToJavaFile(path=models_dir / f"{model_name}.java") as write:
            write.package_decl()
            write.line_empty()
            write.import_stmt("com.fasterxml.jackson.annotation.JsonIgnore")
            write.import_stmt("com.fasterxml.jackson.annotation.JsonProperty")
            needs_deser = any(f.java_type().startswith(("VecOrValue<", "MaybeSpecialOrError<")) for f in table.fields)
            if needs_deser:
                write.import_stmt("com.fasterxml.jackson.databind.annotation.JsonDeserialize")
            write.import_stmt("com.fasterxml.jackson.databind.JsonNode")
            write.import_stmt("com.fasterxml.jackson.databind.node.NullNode")
            write.import_stmt("java.time.Instant")
            if any("Duration" in f.java_type() for f in table.fields):
                write.import_stmt("java.time.Duration")
            write.import_stmt("java.util.LinkedHashMap")
            if any("List<" in f.java_type() for f in table.fields):
                write.import_stmt("java.util.List")
            write.import_stmt("java.util.Map")
            write.line_empty()

            write.doc_comment(
                [
                    f"Typed model for the {{@code {_javadoc_escape(sanitize_string(table.name))}}} Airtable table.",
                    "",
                    "Computed fields are decode-only (no setter, absent from the Builder);",
                    "writable fields have setters. Create records with the Builder:",
                    f"{{@code {model_name}.builder()...build()}}.",
                ]
            )
            write.class_open(model_name, implements=["AirtableModel"])
            write.line_empty()
            write.line_indented(f'public static final String TABLE_ID = "{table.id}";')
            if formulas and _FORMULA_HELPERS_IMPLEMENTED:
                filters_name = f"{prefix}Filters"
                write.line_empty()
                write.doc_comment(f'Formula builder for filtering. Usage: {{@code {model_name}.f.primaryKey.eq("x")}}.', indent=1)
                write.line_indented(f"public static final {filters_name} f = new {filters_name}();")
            write.line_empty()

            # ---------- fields ----------
            for field in table.fields:
                write.property_docstring(field, table, indent_level=1)
                write.json_property(field.id, indent=1)
                java_type = field.java_type()
                if java_type.startswith("VecOrValue<"):
                    write.annotation("JsonDeserialize(using = VecOrValueDeserializer.class)", indent=1)
                elif java_type.startswith("MaybeSpecialOrError<"):
                    write.annotation("JsonDeserialize(using = MaybeSpecialOrErrorDeserializer.class)", indent=1)
                prop = _java_ident(prop_names[field.id])
                write.line_indented(f"private {java_type} {prop};")
                write.line_empty()

            write.line_indented("@JsonIgnore private String id;")
            write.line_indented("@JsonIgnore private Instant createdTime;")
            write.line_indented("@JsonIgnore private AirtableClient attachedClient;")
            write.line_indented("@JsonIgnore private Map<String, JsonNode> snapshot = Map.of();")
            write.line_empty()

            write.doc_comment("Jackson creator — decode populates fields directly (field-access mode).", indent=1)
            write.line_indented(f"public {model_name}() {{}}")
            write.line_empty()

            # ---------- accessors ----------
            for field in table.fields:
                prop = _java_ident(prop_names[field.id])
                pascal = _accessor_pascal(prop_names[field.id])
                java_type = field.java_type()
                write.property_docstring(field, table, indent_level=1)
                write.line_indented(f"public {java_type} get{pascal}() {{")
                write.line_indented(f"return {prop};", indent=2)
                write.line_indented("}")
                write.line_empty()
                if not field.is_computed():
                    write.line_indented(f"public void set{pascal}({java_type} value) {{")
                    write.line_indented(f"this.{prop} = value;", indent=2)
                    write.line_indented("}")
                    write.line_empty()

            # ---------- AirtableModel plumbing ----------
            write.annotation("Override", indent=1)
            write.line_indented("public String getTableId() {")
            write.line_indented("return TABLE_ID;", indent=2)
            write.line_indented("}")
            write.line_empty()
            for prop_type, prop, pascal in (
                ("String", "id", "Id"),
                ("Instant", "createdTime", "CreatedTime"),
                ("AirtableClient", "attachedClient", "AttachedClient"),
            ):
                write.annotation("Override", indent=1)
                write.line_indented(f"public {prop_type} get{pascal}() {{")
                write.line_indented(f"return {prop};", indent=2)
                write.line_indented("}")
                write.line_empty()
                write.annotation("Override", indent=1)
                write.line_indented(f"public void set{pascal}({prop_type} value) {{")
                write.line_indented(f"this.{prop} = value;", indent=2)
                write.line_indented("}")
                write.line_empty()

            # ---------- payload builders ----------
            write.doc_comment("Non-null writable field values keyed by field ID (create payloads).", indent=1)
            write.annotation("Override", indent=1)
            write.line_indented("public Map<String, JsonNode> toCreateFields() {")
            write.line_indented("Map<String, JsonNode> fields = new LinkedHashMap<>();", indent=2)
            for field in writable_fields:
                prop = _java_ident(prop_names[field.id])
                write.line_indented(f"if ({prop} != null) {{", indent=2)
                write.line_indented(f'fields.put("{field.id}", AirtableRuntime.V({prop}));', indent=3)
                write.line_indented("}", indent=2)
            write.line_indented("return fields;", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment("All non-null field values keyed by field ID.", indent=1)
            write.annotation("Override", indent=1)
            write.line_indented("public Map<String, JsonNode> toRecord() {")
            write.line_indented("Map<String, JsonNode> fields = new LinkedHashMap<>();", indent=2)
            for field in table.fields:
                prop = _java_ident(prop_names[field.id])
                write.line_indented(f"if ({prop} != null) {{", indent=2)
                write.line_indented(f'fields.put("{field.id}", AirtableRuntime.V({prop}));', indent=3)
                write.line_indented("}", indent=2)
            write.line_indented("return fields;", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.annotation("Override", indent=1)
            write.line_indented("public void takeSnapshot() {")
            write.line_indented("snapshot = toCreateFields();", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment(
                [
                    "Changed-or-cleared writable fields since the last snapshot.",
                    "Cleared fields are emitted as JSON null so the API clears them server-side.",
                ],
                indent=1,
            )
            write.annotation("Override", indent=1)
            write.line_indented("public Map<String, JsonNode> dirtyFields() {")
            write.line_indented("Map<String, JsonNode> current = toCreateFields();", indent=2)
            write.line_indented("Map<String, JsonNode> dirty = new LinkedHashMap<>();", indent=2)
            write.line_indented("for (Map.Entry<String, JsonNode> entry : current.entrySet()) {", indent=2)
            write.line_indented("if (!entry.getValue().equals(snapshot.get(entry.getKey()))) {", indent=3)
            write.line_indented("dirty.put(entry.getKey(), entry.getValue());", indent=4)
            write.line_indented("}", indent=3)
            write.line_indented("}", indent=2)
            write.line_indented("for (String key : snapshot.keySet()) {", indent=2)
            write.line_indented("if (!current.containsKey(key)) {", indent=3)
            write.line_indented("dirty.put(key, NullNode.getInstance());", indent=4)
            write.line_indented("}", indent=3)
            write.line_indented("}", indent=2)
            write.line_indented("return dirty;", indent=2)
            write.line_indented("}")
            write.line_empty()

            # ---------- fluent CRUD ----------
            write.doc_comment("Persist this model's dirty fields back to Airtable (requires a saved record).", indent=1)
            write.line_indented(f"public {model_name} save() {{")
            write.line_indented(f"return ModelOps.save(this, {model_name}.class);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Re-fetch this model from the server. Returns a fresh instance.", indent=1)
            write.line_indented(f"public {model_name} fetch() {{")
            write.line_indented(f"return ModelOps.fetch(this, {model_name}.class);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Delete the record referenced by this model's id.", indent=1)
            write.line_indented("public void delete() {")
            write.line_indented("ModelOps.delete(this);", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.doc_comment("Debug-friendly rendering; field values stay out of logs by default.", indent=1)
            write.annotation("Override", indent=1)
            write.line_indented("public String toString() {")
            write.line_indented(f'return "{model_name}(id=" + id + ", " + toRecord().size() + " fields)";', indent=2)
            write.line_indented("}")
            write.line_empty()

            # ---------- runtime formula evaluation (J8.8) ----------
            if transpiled_formulas:
                write.region("Runtime formula evaluation", indent=1)
                for field in table.fields:
                    if field.id not in transpiled_formulas:
                        continue
                    formula_code = transpiled_formulas[field.id]
                    raw = raw_formulas.get(field.id, "")
                    preview = _javadoc_escape(sanitize_string(raw).replace("\n", " ")[:80])
                    write.line_empty()
                    write.doc_comment(f"Evaluate formula locally: {{@code {preview}}}", indent=1)
                    pascal = _accessor_pascal(prop_names[field.id])
                    write.line_indented(f"public JsonNode evaluate{pascal}() {{")
                    write.line_indented(f"return {formula_code};", indent=2)
                    write.line_indented("}")
                write.line_empty()
                write.endregion(indent=1)
                write.line_empty()

            # ---------- Builder ----------
            write.doc_comment("New builder over the writable fields.", indent=1)
            write.line_indented("public static Builder builder() {")
            write.line_indented("return new Builder();", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment(
                [
                    f"Builder for fresh {{@code {model_name}}} instances — writable fields only",
                    "(computed fields are server-owned). The Java analog of the other targets'",
                    "named-argument construction.",
                ],
                indent=1,
            )
            write.line_indented("public static final class Builder {")
            write.line_indented(f"private final {model_name} model = new {model_name}();", indent=2)
            write.line_empty()
            write.line_indented("private Builder() {}", indent=2)
            for field in writable_fields:
                prop = _java_ident(prop_names[field.id])
                write.line_empty()
                write.property_docstring(field, table, indent_level=2)
                write.line_indented(f"public Builder {prop}({field.java_type()} value) {{", indent=2)
                write.line_indented(f"model.{prop} = value;", indent=3)
                write.line_indented("return this;", indent=3)
                write.line_indented("}", indent=2)
            write.line_empty()
            write.line_indented(f"public {model_name} build() {{", indent=2)
            write.line_indented("return model;", indent=3)
            write.line_indented("}", indent=2)
            write.line_indented("}", indent=1)
            write.close()


def _accessor_pascal(camel: str) -> str:
    """PascalCase accessor suffix from a deduplicated camelCase property name."""
    if not camel:
        return camel
    return camel[0].upper() + camel[1:]


def _transpiler_supports_java() -> bool:
    """True once the formula transpiler has Java emitter arms (J-F8)."""
    from typing import get_args

    from ..formulas.formula_transpiler import Language as TranspilerLanguage

    return "java" in get_args(TranspilerLanguage)


def write_tables(base: Base, output_folder: Path) -> None:
    """Generate per-table `{Table}Table` class.

    The ORM is the default — `airtable.primary().get(id)` calls through to the
    typed `OrmTable<PrimaryModel>`. Raw-dict access lives under `.dict()` for
    parity with the other targets.
    """
    tables_dir = _create_java_dynamic_subdir(output_folder, _DIR_TABLES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        type_name = f"{prefix}Table"
        fields_name = f"{prefix}Fields"
        model_name = f"{prefix}Model"
        with WriteToJavaFile(path=tables_dir / f"{type_name}.java") as write:
            write.package_decl()
            write.line_empty()
            write.import_stmt("com.fasterxml.jackson.databind.JsonNode")
            write.import_stmt("java.util.List")
            write.import_stmt("java.util.Map")
            write.line_empty()
            write.doc_comment(f"Accessor for the {{@code {_javadoc_escape(sanitize_string(table.name))}}} Airtable table.")
            write.class_open(type_name)
            write.line_empty()
            write.line_indented(f'public static final String TABLE_ID = "{table.id}";')
            write.line_empty()
            write.line_indented("private final DictTable dict;")
            write.line_indented(f"private final OrmTable<{model_name}> orm;")
            write.line_empty()
            write.line_indented(f"public {type_name}(AirtableClient client) {{")
            write.line_indented(f"this.dict = new DictTable(TABLE_ID, {fields_name}.nameToId, client);", indent=2)
            write.line_indented(f"this.orm = new OrmTable<>(TABLE_ID, {model_name}.class, client);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Raw (dict-style) access — decoded fields keyed by ID.", indent=1)
            write.line_indented("public DictTable dict() {")
            write.line_indented("return dict;", indent=2)
            write.line_indented("}")
            write.line_empty()

            write.region("ORM access (default)", indent=1)
            write.line_empty()
            write.doc_comment("Fetch one record by ID.", indent=1)
            write.line_indented(f"public {model_name} get(String recordId) {{")
            write.line_indented("return orm.get(recordId);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Fetch many records by ID, in order.", indent=1)
            write.line_indented(f"public List<{model_name}> get(List<String> recordIds) {{")
            write.line_indented("return orm.get(recordIds);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Fetch all records (paginates internally).", indent=1)
            write.line_indented(f"public List<{model_name}> get() {{")
            write.line_indented("return orm.get();", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Fetch records matching the query (paginates internally).", indent=1)
            write.line_indented(f"public List<{model_name}> get(AirtableQuery query) {{")
            write.line_indented("return orm.get(query);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Create one record from a fresh model (writable fields only).", indent=1)
            write.line_indented(f"public {model_name} create({model_name} model) {{")
            write.line_indented("return orm.create(model);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Create many records. Chunks into Airtable's 10-per-call batch limit.", indent=1)
            write.line_indented(f"public List<{model_name}> create(List<{model_name}> models) {{")
            write.line_indented("return orm.create(models);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Update a model's dirty fields (diffed against its snapshot).", indent=1)
            write.line_indented(f"public {model_name} update({model_name} model) {{")
            write.line_indented("return orm.update(model);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Update many models (dirty fields only). Chunked.", indent=1)
            write.line_indented(f"public List<{model_name}> update(List<{model_name}> models) {{")
            write.line_indented("return orm.update(models);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Update a record's fields directly by ID (no model required).", indent=1)
            write.line_indented(f"public {model_name} updateFields(String recordId, Map<String, JsonNode> fields) {{")
            write.line_indented("return orm.updateFields(recordId, fields);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Upsert a record, matching on the supplied field IDs.", indent=1)
            write.line_indented(f"public OrmTable.UpsertResult<{model_name}> upsert({model_name} model, List<String> fieldsToMergeOn) {{")
            write.line_indented("return orm.upsert(model, fieldsToMergeOn);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Delete one record by ID.", indent=1)
            write.line_indented("public void delete(String recordId) {")
            write.line_indented("orm.delete(recordId);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Delete the record referenced by this model's id.", indent=1)
            write.line_indented(f"public void delete({model_name} model) {{")
            write.line_indented("orm.delete(model);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment(
                "Delete many records by ID. Chunked. (deleteAll because erasure forbids overloading List<String> vs List<Model>.)",
                indent=1,
            )
            write.line_indented("public void deleteAll(List<String> recordIds) {")
            write.line_indented("orm.deleteAll(recordIds);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Delete many records by passing their models.", indent=1)
            write.line_indented(f"public void deleteModels(List<{model_name}> models) {{")
            write.line_indented("orm.deleteModels(models);", indent=2)
            write.line_indented("}")
            write.line_empty()
            write.endregion(indent=1)
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

    write_models(base, output_folder, formulas=formulas, runtime=runtime, flatten=flatten)
    if verbose:
        print("[dim] - Java models generated.[/]")

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

"""C# code generator.

Emits an idiomatic .NET 8 / C# 12 Airtable client (async/await, System.Text.Json,
object-initializer models, single `MyAirtable` namespace). Mirrors the structure of the
Java generator (`src/generators/java.py`) but in C# idioms.

Output layout (under <output>/):
    dynamic/Options/{OptionsName}.cs   — one enum + per-enum JsonConverter per select field
    dynamic/Types/{Table}Fields.cs     — field id/name constants + name↔id maps
    dynamic/Types/{Table}View.cs       — sealed IAirtableView class (static instances) if views
    dynamic/Types/Create{Table}Fields.cs — writable-only constants
    dynamic/Tables/{Table}Table.cs     — table facade (dict access; ORM added in F4)
    dynamic/Models/{Table}Model.cs     — ORM model (F4)
    dynamic/Formulas/{Table}Filters.cs — filter DSL (F7)
    static/                            — copied from static/csharp/
    Airtable.cs                        — entry point with per-table accessor properties
"""

from pathlib import Path

from ..meta import Base, Table
from ..utils.helpers import (
    Paths,
    copy_static_files,
    deduplicate_identifiers,
    deduplicated_table_prefix_map,
    reset_folder,
    sanitize_string,
)
from ..utils.write_to_csharp_file import (
    WriteToCSharpFile,
    _choice_to_entry,
    _csharp_ident,
    _csharp_string_literal,
    _xmldoc_escape,
)

_DIR_DYNAMIC = Paths.DYNAMIC
_DIR_OPTIONS = "Options"
_DIR_TYPES = "Types"
_DIR_TABLES = "Tables"
_DIR_MODELS = "Models"

# Static formula-DSL files excluded from the copy when formulas=False (F7 populates these).
_FORMULA_STATIC_FILES: list[str] = []

# Generated-model / table member names a field/table property must not collide with.
# Covers the AirtableModel base surface (TableId/Id/CreatedTime/AttachedClient property
# names a same-named generated property would clash with) plus the generated `F` filter
# accessor. Methods (ToRecord/SaveAsync/…) are left out: a property can't share a name with
# them either, but Airtable field names producing those PascalCase forms are vanishingly rare.
_CSHARP_RESERVED_MODEL_MEMBERS = frozenset({"F", "Id", "TableId", "CreatedTime", "AttachedClient", "Snapshot"})
_CSHARP_RESERVED_TABLE_PROPS = frozenset({"Client", "BaseId"})


def _create_dynamic_subdir(output_folder: Path, name: str) -> Path:
    path = output_folder / _DIR_DYNAMIC / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deduplicate_entries(entries: list[str]) -> list[str]:
    """Ensure enum-member / static-instance names are unique by appending _V2, _V3, etc."""
    return deduplicate_identifiers(entries, suffix="_V")


def _field_property_map(table: Table) -> dict[str, str]:
    """`{field_id: deduplicated PascalCase property name}` for one table.

    C# members are PascalCase. Names colliding with generated model members (Id, F, ...)
    are suffixed; names that pascal to empty fall back to `Field`, then re-deduplicate.
    """
    raw = [field.name_pascal() or "Field" for field in table.fields]
    adjusted = [f"{p}Field" if p in _CSHARP_RESERVED_MODEL_MEMBERS else p for p in raw]
    deduped = deduplicate_identifiers(adjusted, suffix="V")
    return {field.id: name for field, name in zip(table.fields, deduped)}


def _table_type_prefix(table: Table) -> str:
    """PascalCase prefix used for generated types (e.g. `Primary`), deduplicated per base."""
    return deduplicated_table_prefix_map(table.base)[table.id] or "Table"


def _table_property(table: Table) -> str:
    """PascalCase accessor-property name on the Airtable class (e.g. `Primary`)."""
    prop = _table_type_prefix(table)
    if prop in _CSHARP_RESERVED_TABLE_PROPS:
        prop = f"{prop}Table"
    return _csharp_ident(prop)


def _doc(write: WriteToCSharpFile, text: str, indent: int = 0) -> None:
    write.doc_comment(_xmldoc_escape(text), indent=indent)


# =============================================================================
# WRITERS
# =============================================================================


def write_options(base: Base, output_folder: Path) -> None:
    """Generate one C# enum + per-enum JsonConverter per select field.

    .NET 8's JsonStringEnumConverter can't map arbitrary Airtable strings to PascalCase
    members, so each enum gets a generated JsonConverter keyed on the raw choice strings.
    """
    options_dir = _create_dynamic_subdir(output_folder, _DIR_OPTIONS)

    for table in base.tables:
        for field in table.select_fields():
            choices = field.select_options()
            if not choices:
                continue

            enum_name = field.options_name()
            converter_name = f"{enum_name}Converter"
            entries = _deduplicate_entries([_choice_to_entry(c) for c in choices])
            pairs = list(zip(entries, choices))

            with WriteToCSharpFile(path=options_dir / f"{enum_name}.cs") as write:
                write.using_stmt("System.Text.Json")
                write.using_stmt("System.Text.Json.Serialization")
                write.line_empty()
                write.namespace_decl()
                write.line_empty()
                _doc(write, f"Options for {sanitize_string(field.name)}.")
                write.attribute(f"JsonConverter(typeof({converter_name}))")
                write.enum_open(enum_name)
                for member, _ in pairs:
                    write.enum_entry(member, indent=1)
                write.close()
                write.line_empty()

                # Per-enum converter mapping members ↔ raw Airtable strings.
                _doc(write, f"Maps {enum_name} members to/from their raw Airtable strings.")
                write.line(f"public sealed class {converter_name} : JsonConverter<{enum_name}>")
                write.line("{")
                write.line_indented(f"private static readonly Dictionary<{enum_name}, string> ToWire = new()")
                write.line_indented("{", indent=1)
                for member, choice in pairs:
                    write.line_indented(f'[{enum_name}.{_csharp_ident(member)}] = "{_csharp_string_literal(choice)}",', indent=2)
                write.line_indented("};", indent=1)
                write.line_empty()
                write.line_indented(f"private static readonly Dictionary<string, {enum_name}> FromWire = new()")
                write.line_indented("{", indent=1)
                # Last-wins on duplicate raw strings (mirrors nameToId collapse).
                seen: dict[str, str] = {}
                for member, choice in pairs:
                    seen[_csharp_string_literal(choice)] = member
                for choice_lit, member in seen.items():
                    write.line_indented(f'["{choice_lit}"] = {enum_name}.{_csharp_ident(member)},', indent=2)
                write.line_indented("};", indent=1)
                write.line_empty()
                write.line_indented(
                    f"public override {enum_name} Read(ref Utf8JsonReader reader, Type t, JsonSerializerOptions o) =>",
                    indent=1,
                )
                write.line_indented(
                    'FromWire.TryGetValue(reader.GetString() ?? "", out var v)',
                    indent=2,
                )
                write.line_indented("? v", indent=3)
                write.line_indented(
                    f': throw new AirtableException.DecodingError($"Unknown {enum_name}: {{reader.GetString()}}");',
                    indent=3,
                )
                write.line_empty()
                write.line_indented(
                    f"public override void Write(Utf8JsonWriter w, {enum_name} value, JsonSerializerOptions o) =>",
                    indent=1,
                )
                write.line_indented("w.WriteStringValue(ToWire[value]);", indent=2)
                write.line("}")


def write_field_types(base: Base, output_folder: Path) -> None:
    """Generate `{Table}Fields` + `{Table}View` + `Create{Table}Fields`."""
    types_dir = _create_dynamic_subdir(output_folder, _DIR_TYPES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        prop_names = _field_property_map(table)
        fields_name = f"{prefix}Fields"

        with WriteToCSharpFile(path=types_dir / f"{fields_name}.cs") as write:
            write.namespace_decl()
            write.line_empty()
            _doc(write, f"Field id + name constants for {sanitize_string(table.name)}.")
            write.class_open(fields_name, modifiers=["public", "static"])
            for field in table.fields:
                name_lit = _csharp_string_literal(sanitize_string(field.name))
                pascal = prop_names[field.id]
                write.line_indented(f'public const string {_csharp_ident(f"{pascal}Id")} = "{field.id}";')
                write.line_indented(f'public const string {_csharp_ident(f"{pascal}Name")} = "{name_lit}";')
            write.line_empty()

            ids = ", ".join(f'"{f.id}"' for f in table.fields)
            write.line_indented(f"public static readonly IReadOnlyList<string> AllIds = new[] {{ {ids} }};")
            write.line_empty()

            # name → id, last-wins on collision (distinct names can collapse after sanitize).
            name_to_id: dict[str, str] = {}
            for field in table.fields:
                name_to_id[_csharp_string_literal(sanitize_string(field.name))] = field.id
            write.line_indented("public static readonly IReadOnlyDictionary<string, string> NameToId = new Dictionary<string, string>")
            write.line_indented("{", indent=1)
            for name_lit, fid in name_to_id.items():
                write.line_indented(f'["{name_lit}"] = "{fid}",', indent=2)
            write.line_indented("};", indent=1)
            write.line_empty()

            write.line_indented("public static readonly IReadOnlyDictionary<string, string> IdToName = new Dictionary<string, string>")
            write.line_indented("{", indent=1)
            for field in table.fields:
                name_lit = _csharp_string_literal(sanitize_string(field.name))
                write.line_indented(f'["{field.id}"] = "{name_lit}",', indent=2)
            write.line_indented("};", indent=1)
            write.line_empty()

            write.line_indented("public static string? IdByName(string name) => NameToId.GetValueOrDefault(name);")
            write.line_indented("public static string? NameById(string id) => IdToName.GetValueOrDefault(id);")
            write.close()

        # ---------- Views ----------
        if table.views:
            view_name = f"{prefix}View"
            view_entries = _deduplicate_entries([_choice_to_entry(v.name) for v in table.views])
            with WriteToCSharpFile(path=types_dir / f"{view_name}.cs") as write:
                write.namespace_decl()
                write.line_empty()
                _doc(write, f"Views for {sanitize_string(table.name)}.")
                write.class_open(view_name, interfaces=["IAirtableView"])
                write.line_indented("public string Id { get; }")
                write.line_indented(f"private {view_name}(string id) => Id = id;")
                write.line_empty()
                for view, member in zip(table.views, view_entries):
                    _doc(write, f"{sanitize_string(view.name)} ({view.type})", indent=1)
                    write.line_indented(f'public static readonly {view_name} {_csharp_ident(member)} = new("{view.id}");')
                write.close()

        # ---------- Writable (create) fields ----------
        writable_fields = [f for f in table.fields if not f.is_computed()]
        if writable_fields:
            create_name = f"Create{prefix}Fields"
            with WriteToCSharpFile(path=types_dir / f"{create_name}.cs") as write:
                write.namespace_decl()
                write.line_empty()
                _doc(write, f"Writable field id + name constants for {sanitize_string(table.name)}.")
                write.class_open(create_name, modifiers=["public", "static"])
                for field in writable_fields:
                    name_lit = _csharp_string_literal(sanitize_string(field.name))
                    pascal = prop_names[field.id]
                    write.line_indented(f'public const string {_csharp_ident(f"{pascal}Id")} = "{field.id}";')
                    write.line_indented(f'public const string {_csharp_ident(f"{pascal}Name")} = "{name_lit}";')
                write.close()


def write_models(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate per-table `{Table}Model` ORM class.

    Layout: `dynamic/Models/{Table}Model.cs`. Shape (plan §2.3.1, proven by the Phase 0
    gate `TestPocoModel.cs`):

        public sealed class {Table}Model : AirtableModel {
            [JsonPropertyName("fldX")] public T? Writable { get; set; }
            [JsonPropertyName("fldY")] [JsonInclude] public T? Computed { get; private set; }
            // override TableId; CollectWritableFields/CollectComputedFields feed the base's
            // snapshot/dirty/payload machinery; fluent SaveAsync/FetchAsync/DeleteAsync.
        }

    All properties are nullable (every Airtable field is optional). STJ decodes the typed
    auto-properties wholesale via the global converters; create/update payloads are built
    from the writable-only `CollectWritableFields` map. Creation is by object initializer —
    computed fields have a private setter, so they're excluded from it.

    The `F` formula accessor (needs `{Table}Filters`, F7) and the runtime `evaluate*` methods
    (need the C# formula transpiler, F8) are added by those later features.
    """
    del formulas, runtime, flatten  # F7 adds the `F` accessor; F8 adds evaluate* methods.
    models_dir = _create_dynamic_subdir(output_folder, _DIR_MODELS)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        prop_names = _field_property_map(table)
        model_name = f"{prefix}Model"
        writable_fields = [f for f in table.fields if not f.is_computed()]
        computed_fields = [f for f in table.fields if f.is_computed()]

        with WriteToCSharpFile(path=models_dir / f"{model_name}.cs") as write:
            write.using_stmt("System.Text.Json.Nodes")
            write.using_stmt("System.Text.Json.Serialization")
            write.line_empty()
            write.namespace_decl()
            write.line_empty()

            write.doc_comment(
                [
                    f"Typed model for the {_xmldoc_escape(sanitize_string(table.name))} Airtable table.",
                    "",
                    "Computed fields are decode-only (private setter, excluded from create payloads);",
                    "writable fields have public setters. Create records with an object initializer:",
                    f"<c>new {model_name} {{ ... }}</c>.",
                ]
            )
            write.class_open(model_name, base="AirtableModel")

            _doc(write, "Airtable id of this model's table.", indent=1)
            write.line_indented(f'public override string TableId => "{table.id}";')
            write.line_empty()

            # ---------- fields ----------
            for field in table.fields:
                cs_type = f"{field.csharp_type()}?"
                prop = _csharp_ident(prop_names[field.id])
                write.property_docstring(field, table, indent_level=1)
                write.json_property_name(field.id, indent=1)
                if field.is_computed():
                    write.attribute("JsonInclude", indent=1)
                    write.line_indented(f"public {cs_type} {prop} {{ get; private set; }}")
                else:
                    write.line_indented(f"public {cs_type} {prop} {{ get; set; }}")
                write.line_empty()

            # ---------- AirtableModel plumbing ----------
            _doc(write, "Current writable field values keyed by field id (every writable field, for dirty diffing).", indent=1)
            _write_collect_method(write, "CollectWritableFields", writable_fields, prop_names)
            write.line_empty()
            _doc(write, "Current computed (read-only) field values keyed by field id.", indent=1)
            _write_collect_method(write, "CollectComputedFields", computed_fields, prop_names)
            write.line_empty()

            # ---------- fluent CRUD ----------
            write.doc_comment(
                [
                    "Persist this model's dirty fields back to Airtable (requires a saved record).",
                    "Returns a FRESH instance with a reset snapshot; this receiver keeps its",
                    "pre-save snapshot, so continue with the returned model.",
                ],
                indent=1,
            )
            write.line_indented(f"public Task<{model_name}> SaveAsync(CancellationToken ct = default) => ModelOps.SaveAsync(this, ct);")
            write.line_empty()
            _doc(write, "Re-fetch this model from the server. Returns a fresh instance.", indent=1)
            write.line_indented(f"public Task<{model_name}> FetchAsync(CancellationToken ct = default) => ModelOps.FetchAsync(this, ct);")
            write.line_empty()
            _doc(write, "Delete the record referenced by this model's Id.", indent=1)
            write.line_indented("public Task DeleteAsync(CancellationToken ct = default) => ModelOps.DeleteAsync(this, ct);")
            write.close()


def _write_collect_method(
    write: WriteToCSharpFile,
    method: str,
    fields: list,
    prop_names: dict[str, str],
) -> None:
    """Emit a `CollectWritableFields`/`CollectComputedFields` override.

    Returns a `Dictionary<string, JsonNode?>` mapping every field's id to `AirtableRuntime.V(prop)`
    (null when the property is unset). The base class filters/diffs these for payloads.
    """
    write.line_indented(f"protected override IReadOnlyDictionary<string, JsonNode?> {method}() =>", indent=1)
    if not fields:
        write.line_indented("new Dictionary<string, JsonNode?>();", indent=2)
        return
    write.line_indented("new Dictionary<string, JsonNode?>", indent=2)
    write.line_indented("{", indent=2)
    for field in fields:
        prop = _csharp_ident(prop_names[field.id])
        write.line_indented(f'["{field.id}"] = AirtableRuntime.V({prop}),', indent=3)
    write.line_indented("};", indent=2)


def write_tables(base: Base, output_folder: Path) -> None:
    """Generate per-table `{Table}Table` facade. F3: dict access only (ORM added in F4)."""
    tables_dir = _create_dynamic_subdir(output_folder, _DIR_TABLES)

    for table in base.tables:
        prefix = _table_type_prefix(table)
        type_name = f"{prefix}Table"
        fields_name = f"{prefix}Fields"
        with WriteToCSharpFile(path=tables_dir / f"{type_name}.cs") as write:
            write.namespace_decl()
            write.line_empty()
            _doc(write, f"Accessor for the {sanitize_string(table.name)} Airtable table.")
            write.class_open(type_name)
            write.line_indented(f'public const string TableId = "{table.id}";')
            write.line_empty()
            write.line_indented(f"public {type_name}(AirtableClient client)")
            write.line_indented("{", indent=1)
            write.line_indented(f"Dict = new DictTable(TableId, {fields_name}.NameToId, client);", indent=2)
            write.line_indented("}", indent=1)
            write.line_empty()
            _doc(write, "Raw (dict-style) access — decoded fields keyed by id.", indent=1)
            write.line_indented("public DictTable Dict { get; }")
            write.close()


def write_main(base: Base, output_folder: Path) -> None:
    """Generate `Airtable.cs` — entry point with one accessor property per table."""
    with WriteToCSharpFile(path=output_folder / "Airtable.cs") as write:
        write.namespace_decl()
        write.line_empty()
        write.doc_comment(
            [
                _xmldoc_escape(f"Entry point for Airtable base {base.id}."),
                "",
                "Construct with an API key + base id; access tables via the accessor properties.",
            ]
        )
        write.class_open("Airtable")
        write.line_indented(f'public const string BaseId = "{base.id}";')
        write.line_empty()
        write.line_indented("public AirtableClient Client { get; }")
        for table in base.tables:
            prop = _table_property(table)
            type_name = f"{_table_type_prefix(table)}Table"
            write.line_indented(f"public {type_name} {prop} {{ get; }}")
        write.line_empty()

        _doc(write, "Construct over an existing client.", indent=1)
        write.line_indented("public Airtable(AirtableClient client)")
        write.line_indented("{", indent=1)
        write.line_indented("Client = client;", indent=2)
        for table in base.tables:
            prop = _table_property(table)
            type_name = f"{_table_type_prefix(table)}Table"
            write.line_indented(f"{prop} = new {type_name}(client);", indent=2)
        write.line_indented("}", indent=1)
        write.line_empty()

        _doc(write, "Construct with an API key (optional TTL cache via cacheSeconds > 0).", indent=1)
        write.line_indented("public Airtable(string baseId, string apiKey, double cacheSeconds = 0)")
        write.line_indented(": this(new AirtableClient(baseId, apiKey, cacheSeconds)) { }", indent=2)
        write.line_empty()

        _doc(write, "Drop every cached payload across every table.", indent=1)
        write.line_indented("public void InvalidateAllCaches() => Client.InvalidateAllCaches();")
        write.close()


# =============================================================================
# MAIN
# =============================================================================


def generate_csharp(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    wrappers: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate C# code for the given base into ``output_folder``.

    F3: options, field types, dict-only table facades, and the entry point. ORM models
    (F4) and formula helpers (F7) are emitted by later features.
    """
    output_folder = reset_folder(output_folder)

    exclude_static: list[str] = []
    if not formulas:
        exclude_static.extend(_FORMULA_STATIC_FILES)
    copy_static_files(output_folder, "csharp", exclude=exclude_static or None)

    write_options(base, output_folder)
    write_field_types(base, output_folder)
    write_models(base, output_folder, formulas=formulas, runtime=runtime, flatten=flatten)
    if wrappers:
        write_tables(base, output_folder)
        write_main(base, output_folder)

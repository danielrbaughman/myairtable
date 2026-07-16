"""Go code generator.

Generates an idiomatic Go `package airtable` from Airtable metadata. Unlike the
other targets, Go forbids `package != directory`, so ALL files — the static
runtime and every generated file — live FLAT in the output directory as one
package. Generated files are name-prefixed by concern to avoid colliding with
the static runtime:

  <output>/
  ├── <static runtime *.go>      — copied flat from static/go/ (excl. go.mod, *_test.go)
  ├── options_{table}.go         — per-table select-option typed-string consts
  ├── fields_{table}.go          — per-table field ID/name consts, maps, View consts
  ├── model_{table}.go           — ORM model structs (F4)
  ├── filters_{table}.go         — formula-filter builders (F7)
  └── airtable.go                — Airtable entry point + per-table accessors

The generator emits NO go.mod (the consumer owns their module).

Design reference: .beads/go-plan-v2.md
"""

import shutil
import subprocess
from pathlib import Path

from ..formulas.formula_flattener import flatten_formula_for_transpilation
from ..formulas.formula_transpiler import transpile_table_formulas
from ..meta import Base, Table
from ..utils.helpers import (
    deduplicate_identifiers,
    deduplicated_table_prefix_map,
    reset_folder,
    sanitize_string,
    static_dir,
)
from ..utils.write_to_go_file import (
    WriteToGoFile,
    _choice_to_const,
    _go_ident,
    _go_string_literal,
)

# Excluded from the flat static copy: the standalone module file (the consuming
# project owns its go.mod) and the in-place static-runtime unit tests.
_GO_STATIC_COPY_EXCLUDE = ("go.mod", "go.sum", "*_test.go")

# Maps the field.formula_class() name to the Go formula-builder type + its
# constructor. Mirrors java.py's _JAVA_FORMULA_CLASS_MAP but for the Go DSL.
_GO_FORMULA_CLASS_MAP = {
    "TextField": "TextField",
    "BooleanField": "BooleanField",
    "DateField": "DateField",
    "NumberField": "NumberField",
    "AttachmentsField": "AttachmentsField",
    "LookupField": "LookupField",
    "SingleSelectField": "SingleSelectField",
    "MultiSelectField": "MultiSelectField",
}

# Static formula-DSL files excluded from the flat copy when formulas=False
# (mirror runtime.go's conditional exclusion).
_GO_FORMULA_STATIC_FILES = ("formula.go", "formula_fields.go", "formula_date.go")

# Exported model member names a field property must not collide with. Generated
# models expose ID()/CreatedTime()/Save/Fetch/Delete methods; a field whose
# Pascal name equals one of these would shadow the method, so it is suffixed.
_GO_RESERVED_MODEL_MEMBERS = frozenset({"ID", "CreatedTime", "Save", "Fetch", "Delete", "TableID"})


def _go_model_field_type(field) -> str:
    """The Go struct-field type for a model field: pointer for optional scalars/
    wrappers, slice as-is (already nil-able)."""
    go_type = field.go_type()
    if go_type.startswith("[]"):
        return go_type
    return f"*{go_type}"


def _copy_static_go(output_folder: Path, exclude: list[str]) -> None:
    """Flat-copy static/go/*.go into the output directory (single package)."""
    source = static_dir("go")
    ignore = shutil.ignore_patterns(*_GO_STATIC_COPY_EXCLUDE, *exclude)
    shutil.copytree(source, output_folder, dirs_exist_ok=True, ignore=ignore)


# =============================================================================
# Naming helpers
# =============================================================================


def _table_prefix(table: Table) -> str:
    """PascalCase prefix used for generated types (e.g. `Primary`), deduped per base."""
    return deduplicated_table_prefix_map(table.base)[table.id] or "Table"


def _field_property_map(table: Table) -> dict[str, str]:
    """`{field_id: deduplicated PascalCase exported field name}` for one table.

    Every writer (models, field consts, filters) consumes this same map so
    colliding field names deduplicate consistently. Names colliding with
    generated model members are suffixed; an empty camel falls back to `Field`.
    """
    raw = [field.name_pascal() or "Field" for field in table.fields]
    adjusted = [f"{n}Field" if n in _GO_RESERVED_MODEL_MEMBERS else n for n in raw]
    deduped = deduplicate_identifiers(adjusted, suffix="V")
    return {field.id: name for field, name in zip(table.fields, deduped)}


# =============================================================================
# region WRITERS
# =============================================================================


def write_options(base: Base, output_folder: Path) -> None:
    """Generate per-table select-option typed-string constants.

    Go has no enums: each select field becomes `type {Name} string` plus a const
    block of `{Name}{Choice} {Name} = "raw"`. All of a table's option types are
    grouped into one `options_{table}.go` file.
    """
    for table in base.tables:
        select_fields = [f for f in table.select_fields() if f.select_options()]
        if not select_fields:
            continue
        prefix = _table_prefix(table)
        with WriteToGoFile(path=output_folder / f"options_{prefix.lower()}.go") as write:
            write.package_decl()
            write.line_empty()
            write.comment(f"Select-option constants for {sanitize_string(table.name)}.")
            for field in select_fields:
                choices = field.select_options()
                type_name = field.options_name()
                suffixes = deduplicate_identifiers([_choice_to_const(c) for c in choices], suffix="V")
                write.line_empty()
                write.comment(f"{type_name} — options for {sanitize_string(field.name)}.")
                write.string_type_decl(type_name)
                entries = [(f"{type_name}{suffix}", choice) for suffix, choice in zip(suffixes, choices)]
                write.const_block(entries, type_name)


def write_field_types(base: Base, output_folder: Path) -> None:
    """Generate `fields_{table}.go`: field ID/name consts, lookup maps, View consts.

    Member names mirror the other targets for cross-language parity (allIds,
    nameToId, idToName). The dict-table accessor consumes `{Prefix}NameToID`.
    """
    for table in base.tables:
        prefix = _table_prefix(table)
        props = _field_property_map(table)
        with WriteToGoFile(path=output_folder / f"fields_{prefix.lower()}.go") as write:
            write.package_decl()
            write.line_empty()
            write.comment(f"Field ID/name constants and maps for {sanitize_string(table.name)}.")
            write.line_empty()

            # Per-field ID + name constants.
            write.line("const (")
            for field in table.fields:
                name = props[field.id]
                escaped = _go_string_literal(sanitize_string(field.name))
                write.line_indented(f'{prefix}{name}FieldID = "{field.id}"', 1)
                write.line_indented(f'{prefix}{name}FieldName = "{escaped}"', 1)
            write.line(")")
            write.line_empty()

            # allIds slice.
            ids = ", ".join(f'"{f.id}"' for f in table.fields)
            write.line(f"// {prefix}AllFieldIDs lists all field IDs in schema order.")
            write.line(f"var {prefix}AllFieldIDs = []string{{{ids}}}")
            write.line_empty()

            # nameToID map (last-wins on sanitized-name collisions).
            name_to_id: dict[str, str] = {}
            for field in table.fields:
                name_to_id[_go_string_literal(sanitize_string(field.name))] = field.id
            write.line(f"// {prefix}NameToID maps Airtable field name -> field ID.")
            write.line(f"var {prefix}NameToID = map[string]string{{")
            for nm, fid in name_to_id.items():
                write.line_indented(f'"{nm}": "{fid}",', 1)
            write.line("}")
            write.line_empty()

            # idToName map.
            write.line(f"// {prefix}IDToName maps field ID -> Airtable field name.")
            write.line(f"var {prefix}IDToName = map[string]string{{")
            for field in table.fields:
                nm = _go_string_literal(sanitize_string(field.name))
                write.line_indented(f'"{field.id}": "{nm}",', 1)
            write.line("}")

        # View constants.
        if table.views:
            with WriteToGoFile(path=output_folder / f"views_{prefix.lower()}.go") as write:
                view_name = f"{prefix}View"
                suffixes = deduplicate_identifiers([_choice_to_const(v.name) for v in table.views], suffix="V")
                write.package_decl()
                write.line_empty()
                write.comment(f"Views for {sanitize_string(table.name)}.")
                write.string_type_decl(view_name)
                entries = [(f"{view_name}{suffix}", view.id) for suffix, view in zip(suffixes, table.views)]
                write.const_block(entries, view_name)
                write.line_empty()
                write.comment("ViewID returns the Airtable view ID (implements View).")
                write.line(f"func (v {view_name}) ViewID() string {{ return string(v) }}")


def write_models(base: Base, output_folder: Path, runtime: bool = True, flatten: bool = False) -> None:
    """Generate `model_{table}.go`: the ORM model struct + Model-interface methods
    + fluent Save/Fetch/Delete + (when runtime) transpiled Evaluate* methods.

    Writable fields are pointer optionals (or slices); computed fields decode-only
    (pointer to wrapper) and are excluded from writableFields(). The read-only
    contract is enforced by writableFields(), not the type system.
    """
    for table in base.tables:
        prefix = _table_prefix(table)
        model = f"{prefix}Model"
        props = _field_property_map(table)
        writable = [f for f in table.fields if not f.is_computed()]

        # Pre-transpile this table's formula fields into Go Evaluate* bodies.
        # The transpiler's field_name_map maps field_id -> the Go struct field name
        # so `m.FieldName` (via the V() helper) resolves correctly.
        transpiled_formulas: dict[str, str] = {}
        raw_formulas: dict[str, str] = {}
        if runtime:
            formula_field_ids = table.formula_field_ids()
            field_name_map = {f.id: _go_ident(props[f.id]) for f in table.fields}
            raw_formulas = {f.id: f.options.formula for f in table.fields if f.is_formula() and f.options and f.options.formula}
            if flatten and raw_formulas:
                formula_map_tuple = table.base.get_formula_field_map_tuple()
                raw_formulas = {fid: flatten_formula_for_transpilation(f, fid, formula_map_tuple) for fid, f in raw_formulas.items()}
            if raw_formulas:
                transpiled_formulas = transpile_table_formulas(raw_formulas, "go", field_name_map, formula_field_ids)

        with WriteToGoFile(path=output_folder / f"model_{prefix.lower()}.go") as write:
            write.package_decl()
            write.line_empty()
            write.add_go_import("context")
            write.add_go_import("encoding/json")
            write.mark_imports()
            write.line_empty()
            write.comment(f"{model} is the ORM model for {sanitize_string(table.name)}.")
            write.struct_open(model)
            for field in table.fields:
                name = props[field.id]
                write.property_docstring(field, table, indent_level=1)
                write.struct_field(name, _go_model_field_type(field), json_tag=f"{field.id},omitempty", indent=1)
            write.line_empty()
            write.line_indented("id          string", 1)
            write.line_indented("createdTime *AirtableTime", 1)
            write.line_indented("client      *Client", 1)
            write.line_indented("snapshot    map[string]json.RawMessage", 1)
            write.close()
            write.line_empty()

            # Model-interface methods.
            write.line(f'func (m *{model}) TableID() string {{ return "{table.id}" }}')
            write.line(f"func (m *{model}) ID() string {{ return m.id }}")
            write.line(f"func (m *{model}) CreatedTime() *AirtableTime {{ return m.createdTime }}")
            write.line(f"func (m *{model}) setID(id string) {{ m.id = id }}")
            write.line(f"func (m *{model}) setCreatedTime(t *AirtableTime) {{ m.createdTime = t }}")
            write.line(f"func (m *{model}) setClient(c *Client) {{ m.client = c }}")
            write.line(f"func (m *{model}) getClient() *Client {{ return m.client }}")
            write.line(f"func (m *{model}) setSnapshot(s map[string]json.RawMessage) {{ m.snapshot = s }}")
            write.line(f"func (m *{model}) snapshotFields() map[string]json.RawMessage {{ return m.snapshot }}")
            write.line_empty()

            # writableFields(): every writable field keyed by field ID.
            write.comment("writableFields returns the writable fields keyed by field ID.")
            write.line(f"func (m *{model}) writableFields() map[string]json.RawMessage {{")
            write.line_indented("out := map[string]json.RawMessage{}", 1)
            for field in writable:
                name = props[field.id]
                write.line_indented(f'out["{field.id}"] = mustMarshal(m.{name})', 1)
            write.line_indented("return out", 1)
            write.line("}")
            write.line_empty()

            # Fluent CRUD.
            write.comment("Save creates (if new) or updates this record.")
            write.line(f"func (m *{model}) Save(ctx context.Context) error {{ return modelSave[{model}](ctx, m) }}")
            write.comment("Fetch refreshes this record from the server.")
            write.line(f"func (m *{model}) Fetch(ctx context.Context) error {{ return modelFetch[{model}](ctx, m) }}")
            write.comment("Delete removes this record.")
            write.line(f"func (m *{model}) Delete(ctx context.Context) error {{ return modelDelete[{model}](ctx, m) }}")

            # Runtime formula evaluation (G8.9): one Evaluate{Field}() per formula
            # field whose formula transpiled. Returns the native `any` runtime value.
            if transpiled_formulas:
                for field in table.fields:
                    if field.id not in transpiled_formulas:
                        continue
                    name = props[field.id]
                    raw = sanitize_string(raw_formulas.get(field.id, "")).replace("\n", " ")[:80]
                    write.line_empty()
                    write.comment(f"Evaluate{name} evaluates the formula locally: {raw}")
                    write.line(f"func (m *{model}) Evaluate{name}() any {{")
                    write.line_indented(f"return {transpiled_formulas[field.id]}", 1)
                    write.line("}")


def write_main(base: Base, output_folder: Path) -> None:
    """Generate `airtable.go`: the Airtable entry point + per-table dict accessors.

    F3 (dict-only): each table gets a `{Prefix}Dict *DictTable` field. F4 adds the
    typed ORM `{Prefix} *Table[...]` accessors alongside.
    """
    base_id = base.tables[0].base.id if base.tables else ""
    with WriteToGoFile(path=output_folder / "airtable.go") as write:
        write.package_decl()
        write.line_empty()
        write.comment("BaseID is the Airtable base this client was generated for.")
        write.line(f'const BaseID = "{base_id}"')
        write.line_empty()
        write.comment("Airtable is the generated entry point exposing per-table accessors.")
        write.struct_open("Airtable")
        write.struct_field("client", "*Client", indent=1)
        for table in base.tables:
            prefix = _table_prefix(table)
            write.struct_field(prefix, f"*Table[{prefix}Model, *{prefix}Model]", indent=1)
            write.struct_field(f"{prefix}Dict", "*DictTable", indent=1)
        write.close()
        write.line_empty()

        # Constructors.
        write.comment("NewWithBase builds an Airtable client for an explicit base ID.")
        write.comment("cacheSeconds <= 0 disables read caching.")
        write.line("func NewWithBase(apiKey, baseID string, cacheSeconds float64) *Airtable {")
        write.line_indented("c := NewClient(apiKey, baseID, cacheSeconds)", 1)
        write.line_indented("return &Airtable{", 1)
        write.line_indented("client: c,", 2)
        for table in base.tables:
            prefix = _table_prefix(table)
            write.line_indented(f'{prefix}: NewTable[{prefix}Model, *{prefix}Model](c, "{table.id}", {prefix}NameToID),', 2)
            write.line_indented(f'{prefix}Dict: NewDictTable(c, "{table.id}", {prefix}NameToID),', 2)
        write.line_indented("}", 1)
        write.line("}")
        write.line_empty()
        write.comment("New builds an Airtable client for the generated BaseID.")
        write.line("func New(apiKey string, cacheSeconds float64) *Airtable {")
        write.line_indented("return NewWithBase(apiKey, BaseID, cacheSeconds)", 1)
        write.line("}")
        write.line_empty()
        write.comment("Client returns the underlying low-level client.")
        write.line("func (a *Airtable) Client() *Client { return a.client }")
        write.line_empty()
        write.comment("InvalidateAllCaches clears all cached reads.")
        write.line("func (a *Airtable) InvalidateAllCaches() { a.client.InvalidateAllCaches() }")


def write_formula_helpers(base: Base, output_folder: Path) -> None:
    """Generate `filters_{table}.go`: a `{prefix}Filters` struct with one builder
    per field plus a record-ID builder, and a package-level `{Prefix}F` instance.

    Shape (cross-language parity, PascalCase per Go convention):
        type primaryFilters struct { PrimaryKey TextField; ...; ID IDField }
        var PrimaryF = primaryFilters{ PrimaryKey: NewTextField("Primary Key"), ..., ID: NewIDField() }

    Usage: `airtable.PrimaryF.PrimaryKey.Eq("x", true, false)`. Filter strings
    reference field NAMES, so each builder is constructed from the field's name.
    """
    for table in base.tables:
        prefix = _table_prefix(table)
        props = _field_property_map(table)
        struct_name = f"{prefix.lower()}Filters"
        with WriteToGoFile(path=output_folder / f"filters_{prefix.lower()}.go") as write:
            write.package_decl()
            write.line_empty()
            write.comment(f"Formula-filter builders for {sanitize_string(table.name)}.")
            write.line_empty()

            # The filters struct: one builder field per Airtable field + record ID.
            write.struct_open(struct_name)
            for field in table.fields:
                name = props[field.id]
                go_type = _GO_FORMULA_CLASS_MAP.get(field.formula_class(), "TextField")
                write.struct_field(name, go_type, indent=1)
            write.line_indented("ID IDField", 1)
            write.close()
            write.line_empty()

            # Package-level instance the caller uses: {Prefix}F.
            write.comment(f"{prefix}F builds filter formulas for {sanitize_string(table.name)} fields.")
            write.line(f"var {prefix}F = {struct_name}{{")
            for field in table.fields:
                name = props[field.id]
                go_type = _GO_FORMULA_CLASS_MAP.get(field.formula_class(), "TextField")
                field_name = _go_string_literal(sanitize_string(field.name))
                write.line_indented(f'{name}: New{go_type}("{field_name}"),', 1)
            write.line_indented("ID: NewIDField(),", 1)
            write.line("}")


# endregion


def generate_go(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    wrappers: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate Go code for the given base into ``output_folder`` (flat package)."""
    output_folder = reset_folder(output_folder)

    exclude: list[str] = []
    if not runtime:
        exclude.append("runtime.go")
    if not formulas:
        exclude.extend(_GO_FORMULA_STATIC_FILES)
    _copy_static_go(output_folder, exclude)

    write_options(base, output_folder)
    write_field_types(base, output_folder)
    write_models(base, output_folder, runtime=runtime, flatten=flatten)
    if formulas:
        write_formula_helpers(base, output_folder)
    if wrappers:
        write_main(base, output_folder)

    _gofmt(output_folder)


def _gofmt(output_folder: Path) -> None:
    """Run gofmt -w over the generated output (gofmt is Go's canonical formatter
    and codegen tools apply it deterministically). No-op if gofmt is unavailable.
    """
    if shutil.which("gofmt") is None:
        return
    subprocess.run(["gofmt", "-w", str(output_folder)], check=False)

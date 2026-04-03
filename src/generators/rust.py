import re
from pathlib import Path

from pydantic.alias_generators import to_pascal
from rich import print

from ..formulas.formula_transpiler import transpile_table_formulas
from ..meta import Base, Field, Table
from ..utils import timer
from ..utils.helpers import (
    Paths,
    copy_static_files,
    create_dynamic_subdir,
    reset_folder,
    sanitize_property_name,
    sanitize_string,
)
from ..utils.verbose import verbose
from ..utils.write_to_file import WriteToFile


def _choice_to_variant(choice: str) -> str:
    """Convert an Airtable select choice name to a valid Rust enum variant name (PascalCase)."""
    # Sanitize then convert to PascalCase via the same pipeline as property names
    text = sanitize_property_name(choice)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "Empty"
    # to_pascal expects snake_case input
    text = text.replace(" ", "_").lower()
    text = text.lstrip("_").rstrip("_")
    if not text:
        return "Empty"
    # Handle leading digits
    if text[0].isdigit():
        text = f"n_{text}"
    return to_pascal(text)


# Rust keywords that need r# prefix when used as identifiers
_RUST_KEYWORDS = frozenset(
    {
        "as",
        "break",
        "const",
        "continue",
        "crate",
        "else",
        "enum",
        "extern",
        "false",
        "fn",
        "for",
        "if",
        "impl",
        "in",
        "let",
        "loop",
        "match",
        "mod",
        "move",
        "mut",
        "pub",
        "ref",
        "return",
        "self",
        "Self",
        "static",
        "struct",
        "super",
        "trait",
        "true",
        "type",
        "unsafe",
        "use",
        "where",
        "while",
        "async",
        "await",
        "dyn",
        "abstract",
        "become",
        "box",
        "do",
        "final",
        "macro",
        "override",
        "priv",
        "typeof",
        "unsized",
        "virtual",
        "yield",
        "try",
    }
)


def _rust_ident(name: str) -> str:
    """Ensure a name is a valid Rust identifier, using r# prefix for keywords."""
    if name in _RUST_KEYWORDS:
        return f"r#{name}"
    return name


# Static types from the runtime crate that may appear in ORM model field types
_STATIC_TYPES = frozenset({"RecordId", "Attachment", "Collaborator", "AirtableButton", "VecOrValue"})


def _collect_static_imports(table: Table) -> set[str]:
    """Collect static type imports needed by a table's fields."""
    imports: set[str] = set()
    for field in table.fields:
        rust_type = field.rust_type()
        for type_name in _STATIC_TYPES:
            if type_name in rust_type:
                imports.add(type_name)
    return imports


def _collect_option_imports(table: Table) -> set[str]:
    """Collect option enum imports needed by a table's fields."""
    imports: set[str] = set()
    for field in table.select_fields():
        if field.select_options():
            imports.add(field.options_name())
    return imports


def _deduplicate_variants(variants: list[str]) -> list[str]:
    """Ensure all variant names are unique by appending V2, V3, etc."""
    counts: dict[str, int] = {}
    result: list[str] = []
    for name in variants:
        counts[name] = counts.get(name, 0) + 1
        if counts[name] > 1:
            result.append(f"{name}V{counts[name]}")
        else:
            result.append(name)
    return result


class WriteToRustFile(WriteToFile):
    def __init__(self, path: Path):
        super().__init__(path=path, language="rust")

    def region(self, text: str):
        self.lines.append(f"// region {text}")

    def endregion(self):
        self.lines.append("// endregion")
        self.line_empty()

    def doc_comment(self, text: str | list[str], indent: int = 0):
        """Write a /// doc comment."""
        if isinstance(text, list):
            for line in text:
                self.line_indented(f"/// {line}", indent)
        else:
            self.line_indented(f"/// {text}", indent)

    def derive(self, *traits: str, indent: int = 0):
        """Write a #[derive(...)] attribute."""
        self.line_indented(f"#[derive({', '.join(traits)})]", indent)

    def serde_rename(self, name: str, indent: int = 0):
        """Write a #[serde(rename = "...")] attribute."""
        self.line_indented(f'#[serde(rename = "{name}")]', indent)

    def pub_field(self, name: str, type: str, indent: int = 1):
        """Write a pub field: `pub name: type,`"""
        self.line_indented(f"pub {name}: {type},", indent)

    def pub_field_optional(self, name: str, type: str, indent: int = 1):
        """Write an optional pub field: `pub name: Option<type>,`"""
        self.line_indented(f"pub {name}: Option<{type}>,", indent)

    def mod_decl(self, name: str, public: bool = True):
        """Write a module declaration. Automatically escapes Rust keywords."""
        prefix = "pub " if public else ""
        self.line(f"{prefix}mod {_rust_ident(name)};")

    def use_decl(self, path: str, public: bool = False):
        """Write a use declaration."""
        prefix = "pub " if public else ""
        self.line(f"{prefix}use {path};")

    def property_docstring(self, field: Field, table: Table, indent_level: int = 1):
        """Write a doc comment for a struct field."""
        base_info = f"{sanitize_string(field.name)} `{field.id}`"

        tags = []
        if field.id == table.primary_field_id:
            tags.append("`Primary Key`")
        if field.is_computed():
            tags.append("`Read-Only`")

        if tags:
            base_info += " - " + " - ".join(tags)

        formula = field.formula(sanitized=True, condense=True)
        if formula:
            lines = [base_info, ""]
            lines.append("```text")
            for line in field.formula(sanitized=True, format=True).splitlines():
                lines.append(line)
            lines.append("```")
            self.doc_comment(lines, indent=indent_level)
        else:
            self.doc_comment(base_info, indent=indent_level)


# region MAIN
def generate_rust(base: Base, output_folder: Path) -> None:
    """Generate Rust code from Airtable base metadata."""
    print("Generating Rust code")
    for table in base.tables:
        table.detect_duplicate_property_names()

    reset_folder(output_folder / Paths.DYNAMIC)
    reset_folder(output_folder / Paths.STATIC)

    with timer.timer("Rust: copy_static_files"):
        copy_static_files(output_folder, "rust")
        if verbose:
            print("[dim] - Rust static files copied.[/]")

    with timer.timer("Rust: write_options"):
        write_options(base, output_folder)
        if verbose:
            print("[dim] - Rust options generated.[/]")

    with timer.timer("Rust: write_field_types"):
        write_field_types(base, output_folder)
        if verbose:
            print("[dim] - Rust field types generated.[/]")

    with timer.timer("Rust: write_models"):
        write_models(base, output_folder)
        if verbose:
            print("[dim] - Rust ORM models generated.[/]")

    with timer.timer("Rust: write_formulas"):
        write_formula_helpers(base, output_folder)
        if verbose:
            print("[dim] - Rust formula helpers generated.[/]")

    with timer.timer("Rust: write_lib"):
        write_lib(base, output_folder)
        if verbose:
            print("[dim] - Rust lib.rs generated.[/]")

    if verbose:
        print("[green] - Rust code generation complete.[/]")


# endregion


# region STUBS


def write_options(base: Base, output_folder: Path) -> None:
    """Generate Rust enums for select field options."""
    options_dir = create_dynamic_subdir(output_folder, "options")

    mod_names: list[str] = []

    for table in base.tables:
        select_fields = table.select_fields()
        if not select_fields:
            continue

        mod_name = table.name_snake()
        mod_names.append(mod_name)

        with WriteToRustFile(path=options_dir / f"{mod_name}.rs") as write:
            write.use_decl("serde::{Deserialize, Serialize}")
            write.line_empty()

            for field in select_fields:
                choices = field.select_options()
                if not choices:
                    continue

                enum_name = field.options_name()

                # Convert choices to variant names and deduplicate
                raw_variants = [_choice_to_variant(c) for c in choices]
                variants = _deduplicate_variants(raw_variants)

                write.doc_comment(f"Options for `{sanitize_string(field.name)}`")
                write.derive("Debug", "Clone", "PartialEq", "Eq", "Serialize", "Deserialize")
                write.line(f"pub enum {enum_name} {{")

                for choice, variant in zip(choices, variants):
                    escaped = choice.replace("\\", "\\\\").replace('"', '\\"')
                    write.serde_rename(escaped, indent=1)
                    write.line_indented(f"{variant},")

                # Unknown fallback for forward compatibility
                write.line_indented("#[serde(other)]")
                write.line_indented("Unknown,")
                write.line("}")
                write.line_empty()

            # Options struct — provides const arrays of valid options per field
            options_name = f"{table.name_pascal()}Options"
            write.doc_comment(f"Select field options for `{sanitize_string(table.name)}`")
            write.line(f"pub struct {options_name} {{")
            for field in select_fields:
                choices = field.select_options()
                if not choices:
                    continue
                enum_name = field.options_name()
                write.doc_comment(f"Valid options for `{sanitize_string(field.name)}`", indent=1)
                write.pub_field(_rust_ident(field.name_snake()), f"&'static [{enum_name}]")
            write.line("}")
            write.line_empty()

            write.line(f"impl {options_name} {{")
            write.line_indented("pub const fn new() -> Self {")
            write.line_indented("Self {", 2)
            for field in select_fields:
                choices = field.select_options()
                if not choices:
                    continue
                enum_name = field.options_name()
                raw_variants = [_choice_to_variant(c) for c in choices]
                variants = _deduplicate_variants(raw_variants)
                variant_list = ", ".join(f"{enum_name}::{v}" for v in variants)
                write.line_indented(f"{_rust_ident(field.name_snake())}: &[{variant_list}],", 3)
            write.line_indented("}", 2)
            write.line_indented("}")
            write.line("}")
            write.line_empty()

    # Write mod.rs
    with WriteToRustFile(path=options_dir / "mod.rs") as write:
        for mod_name in sorted(mod_names):
            write.mod_decl(mod_name)
        if mod_names:
            write.line_empty()
            for mod_name in sorted(mod_names):
                write.use_decl(f"{_rust_ident(mod_name)}::*", public=True)


def write_field_types(base: Base, output_folder: Path) -> None:
    """Generate Rust field constant structs for table records."""
    types_dir = create_dynamic_subdir(output_folder, Paths.TYPES)

    for table in base.tables:
        mod_name = table.name_snake()
        fields_name = f"{table.name_pascal()}Fields"

        with WriteToRustFile(path=types_dir / f"{mod_name}.rs") as write:
            if table.views:
                write.use_decl("serde::{Deserialize, Serialize}")
                write.line_empty()

            # All fields — field name and field ID constants
            write.doc_comment(f"Field constants for `{sanitize_string(table.name)}`")
            write.line(f"pub struct {fields_name};")
            write.line_empty()

            write.line(f"impl {fields_name} {{")
            for field in table.fields:
                const_name = field.name_snake().upper()
                escaped_name = sanitize_string(field.name)
                write.doc_comment(f"`{escaped_name}`", indent=1)
                write.line_indented(f'pub const {const_name}: &\'static str = "{escaped_name}";')
                write.doc_comment(f"`{escaped_name}` (field ID)", indent=1)
                write.line_indented(f'pub const {const_name}_ID: &\'static str = "{field.id}";')
            write.line("}")
            write.line_empty()

            # View enum — variants map to view IDs via serde
            if table.views:
                view_name = f"{table.name_pascal()}View"
                write.doc_comment(f"Views for `{sanitize_string(table.name)}`")
                write.derive("Debug", "Clone", "PartialEq", "Eq", "Serialize", "Deserialize")
                write.line(f"pub enum {view_name} {{")
                for view in table.views:
                    variant = to_pascal(view.name.replace(" ", "_").lower())
                    escaped = sanitize_string(view.name)
                    write.doc_comment(f"`{escaped}` ({view.type})", indent=1)
                    write.serde_rename(view.id, indent=1)
                    write.line_indented(f"{variant},")
                write.line("}")
                write.line_empty()

                # AsRef<str> so the enum resolves to its view ID string
                write.line(f"impl AsRef<str> for {view_name} {{")
                write.line_indented("fn as_ref(&self) -> &str {")
                write.line_indented("match self {", 2)
                for view in table.views:
                    variant = to_pascal(view.name.replace(" ", "_").lower())
                    write.line_indented(f'Self::{variant} => "{view.id}",', 3)
                write.line_indented("}", 2)
                write.line_indented("}")
                write.line("}")
                write.line_empty()

                write.line(f"impl From<{view_name}> for String {{")
                write.line_indented(f"fn from(v: {view_name}) -> String {{")
                write.line_indented("v.as_ref().to_string()", 2)
                write.line_indented("}")
                write.line("}")
                write.line_empty()

            # Writable fields only — for create/update
            writable_fields = [f for f in table.fields if not f.is_computed()]
            create_name = f"Create{table.name_pascal()}Fields"

            write.doc_comment(f"Writable field constants for `{sanitize_string(table.name)}`")
            write.line(f"pub struct {create_name};")
            write.line_empty()

            write.line(f"impl {create_name} {{")
            for field in writable_fields:
                const_name = field.name_snake().upper()
                escaped_name = sanitize_string(field.name)
                write.doc_comment(f"`{escaped_name}`", indent=1)
                write.line_indented(f'pub const {const_name}: &\'static str = "{escaped_name}";')
                write.doc_comment(f"`{escaped_name}` (field ID)", indent=1)
                write.line_indented(f'pub const {const_name}_ID: &\'static str = "{field.id}";')
            write.line("}")
            write.line_empty()

    # Write mod.rs
    with WriteToRustFile(path=types_dir / "mod.rs") as write:
        for table in base.tables:
            write.mod_decl(table.name_snake())
        write.line_empty()
        for table in base.tables:
            write.use_decl(f"{_rust_ident(table.name_snake())}::*", public=True)


def write_models(base: Base, output_folder: Path) -> None:
    """Generate Rust ORM model structs for table records."""
    models_dir = create_dynamic_subdir(output_folder, Paths.MODELS)

    for table in base.tables:
        mod_name = table.name_snake()
        model_name = f"{table.name_pascal()}Model"
        create_name = f"Create{table.name_pascal()}Model"

        # Pre-transpile formula fields for this table
        formula_field_ids = table.formula_field_ids()
        field_name_map = {f.id: _rust_ident(f.name_snake()) for f in table.fields}
        raw_formulas = {f.id: f.options.formula for f in table.fields if f.is_formula() and f.options and f.options.formula}
        transpiled_formulas = transpile_table_formulas(raw_formulas, "rust", field_name_map, formula_field_ids) if raw_formulas else {}

        with WriteToRustFile(path=models_dir / f"{mod_name}.rs") as write:
            # Imports
            write.use_decl("serde::{Deserialize, Serialize}")
            static_imports = _collect_static_imports(table)
            static_imports.add("RecordId")
            write.use_decl(f"crate::types::{{{', '.join(sorted(static_imports))}}}")
            write.use_decl("crate::airtable_model::{ModelMeta, OrmModel}")
            option_imports = _collect_option_imports(table)
            if option_imports:
                write.use_decl(f"crate::options::{{{', '.join(sorted(option_imports))}}}")
            if transpiled_formulas:
                write.use_decl("crate::airtable_runtime as F")
                write.use_decl("serde_json::{json, Value}")
            write.line_empty()

            # Model struct — id, created_time, internal state, and all fields
            write.doc_comment(f"ORM model for `{sanitize_string(table.name)}`")
            write.derive("Debug", "Clone", "Serialize", "Deserialize", "Default")
            write.line(f"pub struct {model_name} {{")

            # Record metadata (not serialized)
            write.line_indented("#[serde(skip)]")
            write.pub_field_optional("id", "RecordId")
            write.line_indented("#[serde(skip)]")
            write.pub_field_optional("created_time", "String")

            # Internal state (not serialized)
            write.line_indented("#[serde(skip)]")
            write.line_indented("pub _meta: ModelMeta,")

            # Field properties
            for field in table.fields:
                field_name = _rust_ident(field.name_snake())
                rust_type = field.rust_type()

                write.property_docstring(field, table)
                write.serde_rename(field.id, indent=1)
                write.line_indented("#[serde(default)]", indent=1)
                write.line_indented('#[serde(skip_serializing_if = "Option::is_none")]', indent=1)
                write.pub_field_optional(field_name, rust_type)

            write.line("}")
            write.line_empty()

            # F constant, from_id, url
            formulas_name = f"{table.name_pascal()}Formulas"
            has_url_field = any(field.name_snake() == "url" for field in table.fields)
            url_method_name = "record_url" if has_url_field else "url"

            write.line(f"impl {model_name} {{")
            write.doc_comment("Formula builder for this table.", indent=1)
            write.line_indented(f"pub const F: crate::formulas::{formulas_name} = crate::formulas::{formulas_name}::new();")
            if table.select_fields():
                options_struct = f"{table.name_pascal()}Options"
                write.doc_comment("Select field options for this table.", indent=1)
                write.line_indented(
                    f"pub const O: crate::options::{_rust_ident(table.name_snake())}::{options_struct} = crate::options::{_rust_ident(table.name_snake())}::{options_struct}::new();"
                )
            write.doc_comment("Create a model from just a record ID (for later fetch).", indent=1)
            write.line_indented("pub fn from_id(client: std::sync::Arc<crate::client::AirtableClient>, table_id: &'static str, id: &str) -> Self {")
            write.line_indented("let mut model = Self::default();", 2)
            write.line_indented("model.id = Some(id.to_string());", 2)
            write.line_indented("model._meta.client = Some(client);", 2)
            write.line_indented("model._meta.table_id = Some(table_id);", 2)
            write.line_indented("model", 2)
            write.line_indented("}")
            write.line_empty()
            write.doc_comment("Get the Airtable web URL for this record.", indent=1)
            write.line_indented(f"pub fn {url_method_name}(&self, view_id: impl AsRef<str>) -> String {{")
            write.line_indented('let base_id = self._meta.client.as_ref().map(|c| c.base_id()).unwrap_or("");', 2)
            write.line_indented('let record_id = self.id.as_deref().unwrap_or("");', 2)
            write.line_indented(f'crate::types::build_url(base_id, "{table.id}", view_id.as_ref(), record_id)', 2)
            write.line_indented("}")

            # Runtime formula evaluation methods
            for field in table.fields:
                if field.id not in transpiled_formulas:
                    continue
                field_name = _rust_ident(field.name_snake())
                formula_code = transpiled_formulas[field.id]
                raw_formula = raw_formulas.get(field.id, "")
                write.line_empty()
                # Truncate long formulas in doc comment (avoid multi-line raw formula in Rust doc)
                formula_preview = sanitize_string(raw_formula).replace("\n", " ")[:80]
                write.doc_comment(f"Evaluate formula: `{formula_preview}...`", indent=1)
                write.line_indented("#[allow(unused_parens)]")
                write.line_indented(f"pub fn evaluate_{field_name}(&self) -> Value {{")
                write.line_indented(f"{formula_code}", 2)
                write.line_indented("}")

            write.line("}")
            write.line_empty()

            # OrmModel trait impl
            write.line(f"impl OrmModel for {model_name} {{")
            write.line_indented("fn meta(&self) -> &ModelMeta { &self._meta }")
            write.line_indented("fn meta_mut(&mut self) -> &mut ModelMeta { &mut self._meta }")
            write.line_indented("fn get_id(&self) -> &Option<RecordId> { &self.id }")
            write.line_indented("fn set_id(&mut self, id: Option<RecordId>) { self.id = id; }")
            write.line_indented("fn get_created_time(&self) -> &Option<String> { &self.created_time }")
            write.line_indented("fn set_created_time(&mut self, ct: Option<String>) { self.created_time = ct; }")
            write.line("}")
            write.line_empty()

            # Create model — writable fields only
            writable_fields = [f for f in table.fields if not f.is_computed()]

            write.doc_comment(f"Writable fields for creating/updating `{sanitize_string(table.name)}` records.")
            write.derive("Debug", "Clone", "Serialize", "Deserialize", "Default")
            write.line(f"pub struct {create_name} {{")

            for field in writable_fields:
                field_name = _rust_ident(field.name_snake())
                rust_type = field.rust_type()

                write.serde_rename(field.id, indent=1)
                write.line_indented("#[serde(default)]", indent=1)
                write.line_indented('#[serde(skip_serializing_if = "Option::is_none")]', indent=1)
                write.pub_field_optional(field_name, rust_type)

            write.line("}")
            write.line_empty()

    # Write mod.rs
    with WriteToRustFile(path=models_dir / "mod.rs") as write:
        for table in base.tables:
            write.mod_decl(table.name_snake())
        write.line_empty()
        for table in base.tables:
            write.use_decl(f"{_rust_ident(table.name_snake())}::*", public=True)


# Maps formula_class() return values to Rust formula types
_FORMULA_CLASS_MAP = {
    "TextField": "FormulaTextField",
    "BooleanField": "FormulaBooleanField",
    "DateField": "FormulaDateField",
    "NumberField": "FormulaNumberField",
    "AttachmentsField": "FormulaAttachmentsField",
    "SingleSelectField": "FormulaSingleSelectField",
    "MultiSelectField": "FormulaMultiSelectField",
}


def write_formula_helpers(base: Base, output_folder: Path) -> None:
    """Generate Rust formula builder structs per table."""
    formulas_dir = create_dynamic_subdir(output_folder, Paths.FORMULAS)

    for table in base.tables:
        mod_name = table.name_snake()
        formulas_name = f"{table.name_pascal()}Formulas"

        with WriteToRustFile(path=formulas_dir / f"{mod_name}.rs") as write:
            write.use_decl("crate::formula::*")
            write.line_empty()

            write.doc_comment(f"Formula builder for `{sanitize_string(table.name)}`")
            write.line(f"pub struct {formulas_name} {{")
            write.doc_comment("Record ID formula.", indent=1)
            write.pub_field("id", "FormulaId")
            for field in table.fields:
                property_name = field.name_snake()
                formula_class = field.formula_class()
                rust_formula_type = _FORMULA_CLASS_MAP.get(formula_class, "FormulaTextField")
                write.doc_comment(f"`{sanitize_string(field.name)}`", indent=1)
                write.pub_field(_rust_ident(property_name), rust_formula_type)
            write.line("}")
            write.line_empty()

            # Const constructor
            write.line(f"impl {formulas_name} {{")
            write.line_indented("pub const fn new() -> Self {")
            write.line_indented("Self {", 2)
            write.line_indented("id: FormulaId,", 3)
            for field in table.fields:
                property_name = field.name_snake()
                formula_class = field.formula_class()
                rust_formula_type = _FORMULA_CLASS_MAP.get(formula_class, "FormulaTextField")
                write.line_indented(f'{_rust_ident(property_name)}: {rust_formula_type}::new("{field.id}"),', 3)
            write.line_indented("}", 2)
            write.line_indented("}")
            write.line("}")
            write.line_empty()

    # Write mod.rs
    with WriteToRustFile(path=formulas_dir / "mod.rs") as write:
        for table in base.tables:
            write.mod_decl(table.name_snake())
        write.line_empty()
        for table in base.tables:
            write.use_decl(f"{_rust_ident(table.name_snake())}::*", public=True)


def write_lib(base: Base, output_folder: Path) -> None:
    """Generate the main lib.rs that re-exports all modules."""
    dynamic_dir = output_folder / Paths.DYNAMIC

    # Write per-table wrapper structs and the main Airtable struct
    with WriteToRustFile(path=dynamic_dir / "airtable.rs") as write:
        write.use_decl("std::sync::Arc")
        write.line_empty()
        write.use_decl("crate::client::AirtableClient")
        write.use_decl("crate::error::AirtableError")
        write.use_decl("crate::orm_table::OrmTable")
        write.use_decl("crate::table::StructTable")
        write.use_decl("crate::types::{AirtableQuery, RecordId, build_url}")
        write.use_decl("crate::airtable_model::OrmModel")
        for table in base.tables:
            pascal = table.name_pascal()
            write.use_decl(f"crate::models::{{{pascal}Model, Create{pascal}Model}}")
        write.line_empty()

        # Per-table wrapper structs
        for table in base.tables:
            pascal = table.name_pascal()
            table_struct = f"{pascal}Table"
            model = f"{pascal}Model"
            create = f"Create{pascal}Model"

            write.doc_comment(f"Table accessor for `{sanitize_string(table.name)}`. ORM by default, `.dict` for raw records.")
            write.line(f"pub struct {table_struct} {{")
            write.doc_comment("Raw record (dict) access.", indent=1)
            write.pub_field("dict", "StructTable")
            write.line_indented(f"orm: OrmTable<{model}, {create}>,")
            write.line("}")
            write.line_empty()

            write.line(f"impl {table_struct} {{")

            # Delegated ORM methods
            write.doc_comment("Get a single record by ID.", indent=1)
            write.line_indented(
                f"pub async fn get_one(&self, record_id: &RecordId) -> Result<{model}, AirtableError> {{ self.orm.get_one(record_id).await }}"
            )
            write.doc_comment("Get multiple records.", indent=1)
            write.line_indented(
                f"pub async fn get_many(&self, params: &AirtableQuery) -> Result<Vec<{model}>, AirtableError> {{ self.orm.get_many(params).await }}"
            )
            write.doc_comment("Create a new record.", indent=1)
            write.line_indented(
                f"pub async fn create_one(&self, fields: &{create}) -> Result<{model}, AirtableError> {{ self.orm.create_one(fields).await }}"
            )
            write.doc_comment("Create multiple records.", indent=1)
            write.line_indented(
                f"pub async fn create_many(&self, records: &[{create}]) -> Result<Vec<{model}>, AirtableError> {{ self.orm.create_many(records).await }}"
            )
            write.doc_comment("Update an existing record.", indent=1)
            write.line_indented(
                f"pub async fn update_one(&self, record_id: &RecordId, fields: &{create}) -> Result<{model}, AirtableError> {{ self.orm.update_one(record_id, fields).await }}"
            )
            write.doc_comment("Update multiple records.", indent=1)
            write.line_indented(
                f"pub async fn update_many(&self, records: &[(&RecordId, &{create})]) -> Result<Vec<{model}>, AirtableError> {{ self.orm.update_many(records).await }}"
            )
            write.doc_comment("Upsert a model. Creates if no ID, updates if ID exists.", indent=1)
            write.line_indented(f"pub async fn upsert(&self, model: &mut {model}) -> Result<(), AirtableError> {{ self.orm.upsert(model).await }}")
            write.doc_comment("Delete a record.", indent=1)
            write.line_indented(
                "pub async fn delete_one(&self, record_id: &RecordId) -> Result<(), AirtableError> { self.orm.delete_one(record_id).await }"
            )
            write.doc_comment("Delete multiple records.", indent=1)
            write.line_indented(
                "pub async fn delete_many(&self, record_ids: &[RecordId]) -> Result<(), AirtableError> { self.orm.delete_many(record_ids).await }"
            )
            write.doc_comment("Get the Airtable web URL for this table.", indent=1)
            write.line_indented("pub fn url(&self) -> String { self.orm.url() }")
            write.doc_comment("Set cache TTL in seconds for both ORM and dict layers. 0 = disabled.", indent=1)
            write.line_indented(
                "pub fn set_cache_seconds(&mut self, seconds: u64) { self.orm.set_cache_seconds(seconds); self.dict.set_cache_seconds(seconds); }"
            )
            write.doc_comment("Clear the response cache for both ORM and dict layers.", indent=1)
            write.line_indented("pub fn invalidate_cache(&self) { self.orm.invalidate_cache(); self.dict.invalidate_cache(); }")

            write.line("}")
            write.line_empty()

        # Main Airtable struct
        write.doc_comment("Main entry point for the Airtable base.")
        write.line("pub struct Airtable {")
        write.line_indented("client: Arc<AirtableClient>,")
        for table in base.tables:
            write.doc_comment(f"`{sanitize_string(table.name)}`", indent=1)
            write.pub_field(_rust_ident(table.name_snake()), f"{table.name_pascal()}Table")
        write.line("}")
        write.line_empty()

        write.line("impl Airtable {")

        # new()
        write.doc_comment("Create a new Airtable instance.", indent=1)
        write.line_indented("pub fn new(api_key: &str, base_id: &str) -> Self {")
        write.line_indented("Self::with_cache(api_key, base_id, 0)", 2)
        write.line_indented("}")
        write.line_empty()

        # with_cache()
        write.doc_comment("Create a new Airtable instance with response caching.", indent=1)
        write.line_indented("pub fn with_cache(api_key: &str, base_id: &str, cache_seconds: u64) -> Self {")
        write.line_indented("let client = Arc::new(AirtableClient::new(api_key, base_id));", 2)
        write.line_indented("let mut instance = Self {", 2)
        write.line_indented("client: Arc::clone(&client),", 3)
        for table in base.tables:
            escaped_name = sanitize_string(table.name)
            snake = _rust_ident(table.name_snake())
            write.line_indented(f"{snake}: {table.name_pascal()}Table {{", 3)
            write.line_indented(f'dict: StructTable::new(Arc::clone(&client), "{table.id}", "{escaped_name}"),', 4)
            write.line_indented(f'orm: OrmTable::new(Arc::clone(&client), "{table.id}", "{escaped_name}"),', 4)
            write.line_indented("},", 3)
        write.line_indented("};", 2)
        write.line_indented("if cache_seconds > 0 {", 2)
        for table in base.tables:
            snake = _rust_ident(table.name_snake())
            write.line_indented(f"instance.{snake}.set_cache_seconds(cache_seconds);", 3)
        write.line_indented("}", 2)
        write.line_indented("instance", 2)
        write.line_indented("}")
        write.line_empty()

        # url()
        write.doc_comment("Get the Airtable web URL for this base.", indent=1)
        write.line_indented("pub fn url(&self) -> String {")
        write.line_indented('build_url(self.client.base_id(), "", "", "")', 2)
        write.line_indented("}")
        write.line_empty()

        write.doc_comment("Fetch a live version of the schema from Airtable's metadata API.", indent=1)
        write.line_indented("pub async fn get_schema(&self) -> Result<serde_json::Value, AirtableError> {")
        write.line_indented("self.client.get_schema().await", 2)
        write.line_indented("}")

        write.line("}")
        write.line_empty()

    # Write dynamic lib.rs
    with WriteToRustFile(path=dynamic_dir / "lib.rs") as write:
        write.doc_comment("Auto-generated Airtable SDK.")
        write.line_empty()

        # Static runtime modules (path-based since they live in ../static/)
        write.line('#[path = "../static/types.rs"]')
        write.mod_decl("types")
        write.line('#[path = "../static/error.rs"]')
        write.mod_decl("error")
        write.line('#[path = "../static/pagination.rs"]')
        write.mod_decl("pagination")
        write.line('#[path = "../static/client.rs"]')
        write.mod_decl("client")
        write.line('#[path = "../static/struct_table.rs"]')
        write.mod_decl("table")
        write.line('#[path = "../static/airtable_model.rs"]')
        write.mod_decl("airtable_model")
        write.line('#[path = "../static/orm_table.rs"]')
        write.mod_decl("orm_table")
        write.line('#[path = "../static/formula.rs"]')
        write.line("pub mod formula;")
        write.line('#[path = "../static/airtable_runtime.rs"]')
        write.line("pub mod airtable_runtime;")
        write.line_empty()

        # Generated dynamic modules
        write.line('#[path = "types/mod.rs"]')
        write.mod_decl("field_types")
        write.mod_decl("options")
        write.mod_decl("models")
        write.mod_decl("formulas")
        write.mod_decl("airtable")
        write.line_empty()

        # Re-exports for convenience
        write.use_decl("airtable::Airtable", public=True)
        for table in base.tables:
            write.use_decl(f"airtable::{table.name_pascal()}Table", public=True)
        write.use_decl("client::AirtableClient", public=True)
        write.use_decl("error::AirtableError", public=True)
        write.use_decl("airtable_model::{ModelMeta, OrmModel}", public=True)
        write.use_decl("orm_table::OrmTable", public=True)
        write.use_decl("pagination::PaginatedResponse", public=True)
        write.use_decl("table::StructTable", public=True)
        write.use_decl("types::*", public=True)
        # Re-export field type constants
        for table in base.tables:
            pascal = table.name_pascal()
            exports = [f"{pascal}Fields", f"Create{pascal}Fields"]
            if table.views:
                exports.append(f"{pascal}View")
            write.use_decl(f"field_types::{{{', '.join(exports)}}}", public=True)
        # Re-export ORM model types
        for table in base.tables:
            pascal = table.name_pascal()
            write.use_decl(f"models::{{{pascal}Model, Create{pascal}Model}}", public=True)
        # Re-export formula helpers
        for table in base.tables:
            pascal = table.name_pascal()
            write.use_decl(f"formulas::{pascal}Formulas", public=True)
        # Re-export option enums
        for table in base.tables:
            if table.select_fields():
                write.use_decl(f"options::{_rust_ident(table.name_snake())}::*", public=True)


# endregion

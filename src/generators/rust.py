import re
from pathlib import Path

from pydantic.alias_generators import to_pascal
from rich import print

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

            # from_id helper
            write.line(f"impl {model_name} {{")
            write.doc_comment("Create a model from just a record ID (for later fetch).", indent=1)
            write.line_indented("pub fn from_id(client: std::sync::Arc<crate::client::AirtableClient>, table_id: &'static str, id: &str) -> Self {")
            write.line_indented("let mut model = Self::default();", 2)
            write.line_indented("model.id = Some(id.to_string());", 2)
            write.line_indented("model._meta.client = Some(client);", 2)
            write.line_indented("model._meta.table_id = Some(table_id);", 2)
            write.line_indented("model", 2)
            write.line_indented("}")
            write.line("}")
            write.line_empty()

            # OrmModel trait impl
            write.line(f"impl OrmModel for {model_name} {{")
            write.line_indented("fn meta(&self) -> &ModelMeta { &self._meta }")
            write.line_indented("fn meta_mut(&mut self) -> &mut ModelMeta { &mut self._meta }")
            write.line_indented("fn get_id(&self) -> &Option<RecordId> { &self.id }")
            write.line_indented("fn set_id(&mut self, id: Option<RecordId>) { self.id = id; }")
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


def write_lib(base: Base, output_folder: Path) -> None:
    """Generate the main lib.rs that re-exports all modules."""
    dynamic_dir = output_folder / Paths.DYNAMIC

    # Write the main Airtable struct
    with WriteToRustFile(path=dynamic_dir / "airtable.rs") as write:
        write.use_decl("std::sync::Arc")
        write.line_empty()
        write.use_decl("crate::client::AirtableClient")
        write.use_decl("crate::orm_table::OrmTable")
        write.use_decl("crate::table::StructTable")
        for table in base.tables:
            pascal = table.name_pascal()
            write.use_decl(f"crate::models::{{{pascal}Model, Create{pascal}Model}}")
        write.line_empty()

        write.doc_comment("Main entry point for the Airtable base.")
        write.line("pub struct Airtable {")
        for table in base.tables:
            escaped_name = sanitize_string(table.name)
            pascal = table.name_pascal()
            write.doc_comment(f"`{escaped_name}` (dict)", indent=1)
            write.pub_field(_rust_ident(table.name_snake()), "StructTable")
            write.doc_comment(f"`{escaped_name}` (ORM)", indent=1)
            write.pub_field(f"{_rust_ident(table.name_snake())}_orm", f"OrmTable<{pascal}Model, Create{pascal}Model>")
        write.line("}")
        write.line_empty()

        write.line("impl Airtable {")

        # new()
        write.doc_comment("Create a new Airtable instance.", indent=1)
        write.line_indented("pub fn new(api_key: &str, base_id: &str) -> Self {")
        write.line_indented("let client = Arc::new(AirtableClient::new(api_key, base_id));", 2)
        write.line_indented("Self {", 2)
        for table in base.tables:
            escaped_name = sanitize_string(table.name)
            snake = _rust_ident(table.name_snake())
            write.line_indented(f'{snake}: StructTable::new(Arc::clone(&client), "{table.id}", "{escaped_name}"),', 3)
            write.line_indented(f'{snake}_orm: OrmTable::new(Arc::clone(&client), "{table.id}", "{escaped_name}"),', 3)
        write.line_indented("}", 2)
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
        write.line_empty()

        # Generated dynamic modules
        write.line('#[path = "types/mod.rs"]')
        write.mod_decl("field_types")
        write.mod_decl("options")
        write.mod_decl("models")
        write.mod_decl("airtable")
        write.line_empty()

        # Re-exports for convenience
        write.use_decl("airtable::Airtable", public=True)
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
            write.use_decl(f"field_types::{{{pascal}Fields, Create{pascal}Fields}}", public=True)
        # Re-export ORM model types
        for table in base.tables:
            pascal = table.name_pascal()
            write.use_decl(f"models::{{{pascal}Model, Create{pascal}Model}}", public=True)
        # Re-export option enums
        for table in base.tables:
            if table.select_fields():
                write.use_decl(f"options::{_rust_ident(table.name_snake())}::*", public=True)


# endregion

from pathlib import Path

from rich import print

from ..meta import Base, Field, Table
from ..utils import timer
from ..utils.helpers import (
    Paths,
    copy_static_files,
    create_dynamic_subdir,
    reset_folder,
    sanitize_string,
)
from ..utils.verbose import verbose
from ..utils.write_to_file import WriteToFile


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
        """Write a module declaration."""
        prefix = "pub " if public else ""
        self.line(f"{prefix}mod {name};")

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
            lines.append("```")
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

    with timer.timer("Rust: write_models"):
        write_models(base, output_folder)
        if verbose:
            print("[dim] - Rust models generated.[/]")

    with timer.timer("Rust: write_tables"):
        write_tables(base, output_folder)
        if verbose:
            print("[dim] - Rust tables generated.[/]")

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
    print(options_dir)  # placeholder
    # TODO: Implement in myairtable-7i9


def write_models(base: Base, output_folder: Path) -> None:
    """Generate Rust structs for table records."""
    models_dir = create_dynamic_subdir(output_folder, "models")
    print(models_dir)  # placeholder
    # TODO: Implement in myairtable-c40


def write_tables(base: Base, output_folder: Path) -> None:
    """Generate Rust table wrapper modules."""
    tables_dir = create_dynamic_subdir(output_folder, "tables")
    print(tables_dir)  # placeholder
    # TODO: Implement in myairtable-xiv


def write_lib(base: Base, output_folder: Path) -> None:
    """Generate the main lib.rs that re-exports all modules."""
    # TODO: Implement in myairtable-wgc


# endregion

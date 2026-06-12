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
)
from ..utils.verbose import verbose
from ..utils.write_to_java_file import _java_ident, _java_string_literal

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

    # J-F3+: write_options / write_field_types / write_tables / write_main
    # J-F4+: write_models; J-F7+: write_formula_helpers

    print("[dim] - Java generation complete.[/]")


# endregion

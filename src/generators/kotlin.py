"""Kotlin code generator.

Generates an idiomatic Kotlin/JVM Airtable client: suspend functions, Ktor HTTP
client, kotlinx.serialization models, sealed types for sums. Mirrors the Swift
generator's structure (dynamic/ + static/ output split, flat `myairtable` package).

Design reference: .beads/kotlin-plan-v2.md
"""

from pathlib import Path

from rich import print

from ..meta import Base
from ..utils.helpers import Paths, copy_static_files, reset_folder
from ..utils.verbose import verbose

# =============================================================================
# Kotlin layout
# =============================================================================

# Subdirectory names inside the output folder. Kotlin compilation does not
# require directories to match packages, so we keep the lowercase layout shared
# by the other language generators (safe on case-sensitive filesystems).
_DIR_DYNAMIC = Paths.DYNAMIC  # "dynamic"
_DIR_STATIC = Paths.STATIC  # "static"
_DIR_OPTIONS = "options"
_DIR_TYPES = Paths.TYPES  # "types"
_DIR_TABLES = Paths.TABLES  # "tables"
_DIR_MODELS = Paths.MODELS  # "models"
_DIR_FORMULAS = Paths.FORMULAS  # "formulas"


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
    """Generate Kotlin code from Airtable base metadata.

    Currently a scaffolding stub (K-F1): resets the owned subdirectories and
    copies the static runtime. Per-table writers land with K-F3/K-F4.
    """
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

    print("[dim] - Kotlin generation complete.[/]")


# endregion

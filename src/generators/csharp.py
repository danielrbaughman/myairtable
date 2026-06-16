"""C# code generator.

Emits an idiomatic .NET 8 / C# 12 Airtable client (async/await, System.Text.Json,
object-initializer models, `MyAirtable` namespace). Mirrors the structure of the
Java generator (`src/generators/java.py`).

This is the F1 scaffolding stub: `generate_csharp` resets the output folder and
copies the static runtime (a no-op until `static/csharp/` lands in F2). The
dynamic writers (options/types/models/formulas/tables/main) are filled in by F3+.
"""

from pathlib import Path

from ..meta import Base
from ..utils.helpers import copy_static_files, reset_folder


def generate_csharp(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    wrappers: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate C# code for the given base into ``output_folder``.

    F1 stub: resets the folder and copies the static runtime. Full dynamic
    generation (options, types, models, formula helpers, tables, entrypoint)
    is implemented in F3+.
    """
    del base, formulas, wrappers, runtime, flatten  # consumed by the F3+ writers
    output_folder = reset_folder(output_folder)
    copy_static_files(output_folder, "csharp")

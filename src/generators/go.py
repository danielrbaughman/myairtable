"""Go code generator.

Generates an idiomatic Go `package airtable` (single flat directory) from
Airtable metadata: structs with `json:"fldID"` tags, pointer optionals, typed
generic table layer, errors-as-values, native-any formula runtime. Mirrors the
Java generator's structure (see src/generators/java.py) adapted to Go idioms.

NOTE: this is the F1 scaffolding stub — the real artifact writers (options,
field types, models, tables, main, formula helpers) land in F3+. The signature
and entry point are stable so the CLI wiring (main.py) compiles now.
"""

from pathlib import Path

from ..meta import Base
from ..utils.helpers import reset_folder


def generate_go(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    wrappers: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate Go code for the given base into ``output_folder``.

    F1 stub: resets the output folder so the command is runnable end-to-end and
    exits 0. The static-runtime copy and dynamic writers are filled in by F3+.
    """
    reset_folder(output_folder)

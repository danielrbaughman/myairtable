"""Go code generator.

Generates an idiomatic Go `package airtable` (single flat directory) from
Airtable metadata: structs with `json:"fldID"` tags, pointer optionals, typed
generic table layer, errors-as-values, native-any formula runtime. Mirrors the
Java generator's structure (see src/generators/java.py) adapted to Go idioms.

Unlike the other targets, Go forbids `package != directory`, so static runtime
files and generated files all live FLAT in the output directory (one package) —
`copy_static_files` (which nests under `static/`) is intentionally NOT used.

NOTE: this is the F1 scaffolding stub for the dynamic writers — the real
artifact writers (options, field types, models, tables, main, formula helpers)
land in F3+. The static-file flat copy and CLI entry point are stable now.
"""

import shutil
from pathlib import Path

from ..meta import Base
from ..utils.helpers import reset_folder

# Excluded from the flat static copy: the standalone module file (the consuming
# project owns its go.mod) and the in-place static-runtime unit tests.
_GO_STATIC_COPY_EXCLUDE = ("go.mod", "go.sum", "*_test.go")


def _copy_static_go(output_folder: Path, exclude: list[str]) -> None:
    """Flat-copy static/go/*.go into the output directory (single package).

    Skips `exclude` (glob patterns) plus the always-excluded module/test files.
    """
    source = Path("./static/go")
    if not source.exists():
        return
    ignore = shutil.ignore_patterns(*_GO_STATIC_COPY_EXCLUDE, *exclude)
    shutil.copytree(source, output_folder, dirs_exist_ok=True, ignore=ignore)


def generate_go(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    wrappers: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate Go code for the given base into ``output_folder``.

    F1 stub: resets the output folder and flat-copies the static runtime so the
    command is runnable end-to-end and produces a compilable package once the
    static runtime exists (F2). The dynamic writers are filled in by F3+.
    """
    output_folder = reset_folder(output_folder)

    # Static runtime files to drop when the corresponding feature is disabled.
    # (Filenames finalized in F2/F7/F8; this keeps the flag contract in place.)
    exclude: list[str] = []
    if not runtime:
        exclude.append("runtime.go")

    _copy_static_go(output_folder, exclude)

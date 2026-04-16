"""Swift code generator.

Scaffolding stub — full implementation lands in F3 (myairtable-62a onward).
At present, `generate_swift` only copies the hand-written static runtime to
the output folder and creates an empty Dynamic subdirectory. The CLI command
in main.py wires this up so the entire pipeline can be exercised end-to-end
while the write_* functions are still being built.
"""

from pathlib import Path

from rich import print

from ..meta import Base
from ..utils import timer
from ..utils.helpers import Paths, copy_static_files, reset_folder
from ..utils.verbose import verbose


def generate_swift(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    wrappers: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate Swift code from Airtable base metadata.

    STUB: only copies static files for now. write_options / write_field_types /
    write_models / write_tables / write_main will be added by the F3 tasks
    tracked under beads feature myairtable-02u.
    """
    # Silence unused-argument warnings until the real generator is built.
    _ = base, formulas, wrappers, runtime, flatten

    print("Generating Swift code")

    reset_folder(output_folder / Paths.DYNAMIC)
    reset_folder(output_folder / Paths.STATIC)

    exclude_static: list[str] = []
    if not runtime:
        # AirtableRuntime.swift holds the formula-evaluation helpers.
        # It's safe to skip when the caller opted out of runtime support.
        exclude_static.append("AirtableRuntime.swift")

    with timer.timer("Swift: copy_static_files"):
        copy_static_files(output_folder, "swift", exclude=exclude_static or None)
        if verbose:
            print("[dim] - Swift static files copied.[/]")

    print("[yellow] - Swift generator is stubbed; dynamic files not emitted yet (F3).[/]")

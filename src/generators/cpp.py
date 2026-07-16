"""C++ code generator.

Mirrors the structure of the C# generator (the closest structural template):
one public type per header, a flat ``myairtable`` namespace, and a
``dynamic/{options,types,formulas,models,tables}`` output layout beside a
verbatim copy of the hand-written ``static/cpp`` runtime.

Idiom targets (plan .beads/cpp-plan-v2.md): C++20 aggregate-struct models with
``std::optional<T>`` members and designated-initializer creation, value-semantic
``nlohmann::json``, header-only distribution (consumers add the output folder to
their include path and link libcurl).

Output structure:
    <output>/
    ├── dynamic/
    │   ├── options/    {options_name}.hpp enums (+ to_json/from_json)
    │   ├── types/      {table}_fields.hpp, {table}_view.hpp, create_{table}_fields.hpp
    │   ├── formulas/   {table}_filters.hpp                     (F7)
    │   ├── models/     {table}_model.hpp                       (F4)
    │   └── tables/     {table}_table.hpp
    ├── static/         copied verbatim from static/cpp/ (incl. vendor/)
    └── airtable.hpp    entry point
"""

from pathlib import Path

from ..meta import Base
from ..utils.helpers import Paths, copy_static_files, reset_folder

_DIR_DYNAMIC = Paths.DYNAMIC
_DIR_OPTIONS = "options"
_DIR_TYPES = "types"
_DIR_TABLES = "tables"
_DIR_MODELS = "models"
_DIR_FORMULAS = "formulas"

# Static formula-DSL headers excluded from the copy when formulas=False.
_FORMULA_STATIC_FILES: list[str] = [
    "formulas.hpp",
    "formula_field.hpp",
    "formula_text_ops.hpp",
    "formula_text_field.hpp",
    "formula_single_select_field.hpp",
    "formula_multi_select_field.hpp",
    "formula_lookup_field.hpp",
    "formula_number_field.hpp",
    "formula_boolean_field.hpp",
    "formula_attachments_field.hpp",
    "formula_date_field.hpp",
    "formula_id.hpp",
]


def generate_cpp(
    base: Base,
    output_folder: Path,
    formulas: bool = True,
    wrappers: bool = True,
    runtime: bool = True,
    flatten: bool = False,
) -> None:
    """Generate C++ code for the given base into ``output_folder``.

    F1 skeleton: copies the static runtime only. The dynamic writers
    (options/field types/tables in F3, models in F4, formula helpers in F7,
    runtime transpilation in F8) land with their features.
    """
    del wrappers, runtime, flatten  # consumed by later features (F3/F4/F8)

    output_folder = reset_folder(output_folder)

    exclude_static: list[str] = []
    if not formulas:
        exclude_static.extend(_FORMULA_STATIC_FILES)
    copy_static_files(output_folder, "cpp", exclude=exclude_static or None)

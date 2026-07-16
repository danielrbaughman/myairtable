import re
import shutil
from pathlib import Path

# Compile regex patterns once at module level for performance
_MULTI_SPACE_PATTERN = re.compile(r" {2,}")
_CHARS_TO_SPACE_PATTERN = re.compile(r"[()[\]{}<>'\"`|\\.:,]")
_MARKDOWN_SPECIAL_CHARS = re.compile(r"([\\`*_\[\]#|<>!{}()+\-.])")

# Multi-character replacements (order matters for some)
_MULTI_CHAR_REPLACEMENTS: list[tuple[str, str]] = [
    ("<<", " "),
    (">>", " "),
    ("< ", " less than "),
    (" <", " less than "),
    ("> ", " greater than "),
    (" >", " greater than "),
    ("$/", " dollars per "),
    ("$ ", "dollar "),
    ("w/o", " without "),
    ("w/", " with "),
    ("# ", " number "),
]

# Single character to word replacements
_SINGLE_CHAR_REPLACEMENTS: dict[str, str] = {
    "+": " plus ",
    "-": " dash ",
    "&": " and ",
    "=": " equals ",
    "%": " percent ",
    "$": " d ",
    "#": " h ",
    "@": " at ",
    "!": " e ",
    "?": " q ",
    "^": " power ",
    "*": " star ",
    "/": " slash ",
    "~": " tilde ",
}

# Ordinal number mappings for sanitize_leading_trailing_characters
_ORDINAL_REPLACEMENTS: dict[str, tuple[str, int]] = {
    "1st": ("first", 3),
    "2nd": ("second", 3),
    "3rd": ("third", 3),
    "4th": ("fourth", 3),
    "5th": ("fifth", 3),
    "6th": ("sixth", 3),
    "7th": ("seventh", 3),
    "8th": ("eighth", 3),
    "9th": ("ninth", 3),
    "10th": ("tenth", 4),
}


def sanitize_property_name(text: str) -> str:
    """Sanitizes the property name to remove any characters that are not allowed in property names."""
    # Handle special suffixes
    if text.endswith("?"):
        text = "is_" + text[:-1]
    if text.endswith(" #"):
        text = text[:-1] + "number"

    # Apply multi-character replacements (order-dependent)
    for old, new in _MULTI_CHAR_REPLACEMENTS:
        if old in text:
            text = text.replace(old, new)

    # Apply single character to word replacements
    for char, replacement in _SINGLE_CHAR_REPLACEMENTS.items():
        if char in text:
            text = text.replace(char, replacement)

    # Replace brackets and punctuation with spaces using single regex
    text = _CHARS_TO_SPACE_PATTERN.sub(" ", text)

    return text


def remove_extra_spaces(text: str) -> str:
    """Removes extra spaces from the text using a single regex substitution."""
    return _MULTI_SPACE_PATTERN.sub(" ", text)


def sanitize_leading_trailing_characters(text: str) -> str:
    """Sanitizes leading and trailing characters, to deal with characters that are not allowed and/or desired in property names."""
    # Strip leading/trailing spaces and underscores
    text = text.lstrip(" _").rstrip(" _")

    if text and text[0].isdigit():
        # Check for ordinal numbers using dictionary lookup
        for ordinal, (word, length) in _ORDINAL_REPLACEMENTS.items():
            if text.startswith(ordinal):
                return word + text[length:]
        # Default: prefix with n_
        return f"n_{text}"

    return text


PYTHON_BUILTINS = {
    "list",
    "dict",
    "set",
    "tuple",
    "type",
    "int",
    "float",
    "str",
    "bool",
    "bytes",
    "object",
    "map",
    "filter",
    "range",
    "zip",
    "len",
    "print",
    "input",
    "open",
    "format",
    "hash",
    "iter",
    "next",
    "super",
}


def sanitize_reserved_names(text: str) -> str:
    """Some names are reserved by the pyairtable library or Python builtins and cannot be used as property names."""

    if text == "id":
        text = "identifier"
    if text == "created_time":
        text = "created_at_time"
    if text in PYTHON_BUILTINS:
        text = f"{text}_"

    return text


def sanitize_string(text: str) -> str:
    return text.replace('"', "'")


def escape_for_double_quoted_string(text: str) -> str:
    """Escape text so it can be safely embedded between double-quote characters
    when emitting Python, TypeScript, or JavaScript source code.

    Escapes backslashes and double quotes (and a few control characters that
    would otherwise break the line). The output is intentionally compatible
    across all three target languages.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def deduplicate_identifiers(names: list[str], suffix: str = "V") -> list[str]:
    """Ensure identifier uniqueness by appending `{suffix}2`, `{suffix}3`, ... to duplicates.

    Shared by the Kotlin (`suffix="_V"` for SCREAMING_SNAKE enum entries, `"V"` for
    camelCase properties) and Swift (`suffix="V"`) generators. Unlike a naive
    occurrence counter, every name in the input and every name already emitted is
    tracked, so a pre-existing suffixed name can't be re-assigned: with
    `["A", "A", "A_V2"]` and `suffix="_V"`, the second "A" becomes "A_V3" (not a
    second "A_V2"). Deterministic: output depends only on input order.
    """
    taken: set[str] = set(names)
    emitted: set[str] = set()
    out: list[str] = []
    for name in names:
        if name not in emitted:
            emitted.add(name)
            out.append(name)
            continue
        n = 2
        while (candidate := f"{name}{suffix}{n}") in taken or candidate in emitted:
            n += 1
        emitted.add(candidate)
        out.append(candidate)
    return out


def deduplicated_field_property_map(table) -> dict[str, str]:
    """Per-table `{field_id: deduplicated lowerCamelCase property name}`.

    Distinct Airtable field names can collapse to the same camelCase identifier
    ("My Field" / "my field" -> `myField`), which would emit duplicate
    declarations. Computed ONCE per table (deterministically, in schema order)
    and consumed by every writer — model properties, `{Table}Fields` constants,
    `Create{Table}Fields`, `{Table}Filters`, `evaluate*` methods, and the
    formula transpiler's `field_name_map` — so all sites agree on the
    deduplicated names (`myField`, `myFieldV2`, ...).

    Keyword escaping (backticks) is NOT applied here; call sites wrap with
    their language's identifier escaper.

    A fully-symbolic name (e.g. `_`, `.`, `(`) camels to the empty string, which
    would emit an invalid identifier; it falls back to `field` (then deduplicates
    like any other collision). No effect on bases without such names.
    """
    deduped = deduplicate_identifiers([field.name_camel() or "field" for field in table.fields], suffix="V")
    return {field.id: name for field, name in zip(table.fields, deduped)}


def deduplicated_field_property_map_snake(table) -> dict[str, str]:
    """Per-table `{field_id: deduplicated snake_case property name}`.

    The snake_case analog of `deduplicated_field_property_map`, for the Python
    and Rust generators. Distinct Airtable field names — or a custom property
    name that duplicates another field's — can collapse to the same snake_case
    identifier, which would emit duplicate dict keys / struct fields. Computed
    ONCE per table (deterministically, in schema order) and consumed by every
    writer so all sites agree on the deduplicated names.

    Uses suffix `_v` so `quantity_total` / `quantity_total` -> `quantity_total`
    / `quantity_total_v2`, i.e. the snake_case of the camelCase `V2` convention.

    Identifier escaping (e.g. Rust keyword raw-idents) is NOT applied here; call
    sites wrap with their language's identifier escaper. An empty snake name
    falls back to `field` (then deduplicates like any other collision).
    """
    deduped = deduplicate_identifiers([field.name_snake() or "field" for field in table.fields], suffix="_v")
    return {field.id: name for field, name in zip(table.fields, deduped)}


def deduplicated_table_prefix_map(base) -> dict[str, str]:
    """Per-base `{table_id: deduplicated PascalCase type prefix}`.

    Mirrors `deduplicated_field_property_map` for table-level names: two tables
    whose names collapse to the same PascalCase prefix would otherwise generate
    colliding type/file names and `Airtable` accessor properties.
    """
    deduped = deduplicate_identifiers([table.name_pascal() for table in base.tables], suffix="V")
    return {table.id: name for table, name in zip(base.tables, deduped)}


def deduplicate_names(names: list[str]) -> list[str]:
    """Append ' (2)', ' (3)', etc. to duplicate names to ensure uniqueness."""
    counts: dict[str, int] = {}
    result: list[str] = []
    for name in names:
        counts[name] = counts.get(name, 0) + 1
        if counts[name] > 1:
            result.append(f"{name} ({counts[name]})")
        else:
            result.append(name)
    return result


# static/ is bundled data, so it is anchored to this module's location and never
# to the caller's cwd — codegen must emit identical output from any directory.
# src/myairtable/utils/helpers.py -> parents[3] == repo root, where static/ still
# lives. Becomes parents[1] once static/ moves into the package (myairtable-1mcd).
STATIC_ROOT = Path(__file__).resolve().parents[3] / "static"


def static_dir(name: str) -> Path:
    """Locate a bundled static runtime directory, e.g. static_dir("python").

    Raises FileNotFoundError rather than returning a missing path: the generated
    code imports these files, so skipping the copy yields a package that fails
    to import later, far from the cause.
    """
    source = STATIC_ROOT / name
    if not source.is_dir():
        raise FileNotFoundError(f"Bundled static runtime '{name}' not found at {source}. The myairtable installation is incomplete.")
    return source


def copy_static_files(output_folder: Path, type: str, exclude: list[str] | None = None):
    """Copy static template files to output folder. Uses optimized copytree."""
    source = static_dir(type)
    destination = output_folder / "static"

    ignore = shutil.ignore_patterns(*exclude) if exclude else None
    shutil.copytree(source, destination, dirs_exist_ok=True, ignore=ignore)


def reset_folder(folder: Path | str, preserve: list[str] | None = None) -> Path:
    """Remove and recreate a folder if it exists.

    Args:
        folder: The folder to reset.
        preserve: List of subfolder names to preserve (e.g., [".svg_cache"]).
    """
    folder = Path(folder)
    if folder.exists():
        if preserve:
            # Move preserved folders to temp location
            import tempfile

            temp_dir = Path(tempfile.mkdtemp())
            preserved_paths: list[tuple[Path, Path]] = []
            for name in preserve:
                src = folder / name
                if src.exists():
                    dst = temp_dir / name
                    shutil.move(str(src), str(dst))
                    preserved_paths.append((dst, src))

            # Remove the folder
            shutil.rmtree(folder)

            # Recreate and restore preserved folders
            folder.mkdir(parents=True, exist_ok=True)
            for dst, src in preserved_paths:
                shutil.move(str(dst), str(src))

            # Clean up temp dir
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            shutil.rmtree(folder)
            folder.mkdir(parents=True, exist_ok=True)
    else:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def create_folder(folder: Path | str) -> Path:
    """Create a folder if it does not exist."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class Paths:
    """Constants for generated folder/file paths."""

    DYNAMIC = "dynamic"
    STATIC = "static"
    TYPES = "types"
    DICTS = "dicts"
    MODELS = "models"
    TABLES = "tables"
    FORMULAS = "formulas"
    OPTIONS = "options"
    DOCS = "docs"
    ZOD = "zod"


def create_dynamic_subdir(output_folder: Path, subdir: str) -> Path:
    """Create a subdirectory under dynamic/ and return its path."""
    path = output_folder / Paths.DYNAMIC / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_for_markdown(text: str) -> str:
    """Sanitizes text for use in Markdown by escaping special characters."""
    return _MARKDOWN_SPECIAL_CHARS.sub(r"\\\1", text)

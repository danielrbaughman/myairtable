import re
import shutil
from pathlib import Path

# Compile regex patterns once at module level for performance
_MULTI_SPACE_PATTERN = re.compile(r" {2,}")
_CHARS_TO_SPACE_PATTERN = re.compile(r"[()[\]{}<>'`|\\.:,]")

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


def sanitize_reserved_names(text: str) -> str:
    """Some names are reserved by the pyairtable library and cannot be used as property names."""

    if text == "id":
        text = "identifier"
    if text == "created_time":
        text = "created_at_time"

    return text


def sanitize_string(text: str) -> str:
    return text.replace('"', "'")


def copy_static_files(output_folder: Path, type: str):
    source = Path(f"./static/{type}")
    destination = output_folder / "static"
    destination.mkdir(parents=True, exist_ok=True)

    if source.exists():
        for file in source.iterdir():
            if file.is_file():
                shutil.copy2(file, destination / file.name)


def reset_folder(folder: Path | str) -> Path:
    """Remove and recreate a folder if it exists."""
    folder = Path(folder)
    if folder.exists():
        shutil.rmtree(folder)
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


def create_dynamic_subdir(output_folder: Path, subdir: str) -> Path:
    """Create a subdirectory under dynamic/ and return its path."""
    path = output_folder / Paths.DYNAMIC / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path

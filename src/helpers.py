import shutil
from pathlib import Path


def options_name(table_name: str, field_name: str) -> str:
    return f"{table_name}{field_name}Option"


def upper_case(text: str) -> str:
    """Formats as UPPERCASE"""

    def alpha_only(text: str) -> str:
        return "".join(c for c in text if c.isalpha())

    return alpha_only(text).upper()


def sanitize_property_name(text: str) -> str:
    """Sanitizes the property name to remove any characters that are not allowed in property names"""

    if text.endswith("?"):
        text = text[:-1]
        text = "is_" + text
    if text.endswith(" #"):
        text = text[:-1]
        text = text + "number"

    text = text.replace("<<", " ")
    text = text.replace(">>", " ")
    text = text.replace("< ", " less than ")
    text = text.replace(" <", " less than ")
    text = text.replace("> ", " greater than ")
    text = text.replace(" >", " greater than ")

    text = text.replace("+", " plus ")
    text = text.replace("-", " dash ")
    text = text.replace("&", " and ")
    text = text.replace("=", " equals ")
    text = text.replace("%", " percent ")
    text = text.replace("$/", " dollars per ")
    text = text.replace("$ ", "dollar ")
    text = text.replace("$", " d ")
    text = text.replace("w/o", " without ")
    text = text.replace("w/", " with ")
    text = text.replace("# ", " number ")
    text = text.replace("#", " h ")
    text = text.replace("@", " at ")
    text = text.replace("!", " e ")
    text = text.replace("?", " q ")
    text = text.replace("^", " power ")
    text = text.replace("*", " star ")
    text = text.replace("/", " slash ")
    text = text.replace("~", " tilde ")

    text = text.replace("(", " ").replace(")", " ")
    text = text.replace("[", " ").replace("]", " ")
    text = text.replace("{", " ").replace("}", " ")
    text = text.replace("<", " ").replace(">", " ")

    text = text.replace("'", " ")
    text = text.replace("`", " ")
    text = text.replace("|", " ")
    text = text.replace("\\", " ")
    text = text.replace(".", " ")
    text = text.replace(":", " ")
    text = text.replace(",", " ")

    return text


def remove_extra_spaces(text: str) -> str:
    """Removes extra spaces from the text"""

    while "  " in text:
        text = text.replace("  ", " ")

    return text


def sanitize_leading_trailing_characters(text: str) -> str:
    """Sanitizes leading and trailing characters, to deal with characters that are not allowed and/or desired in property names"""

    if text.startswith(" ") or text.startswith("_"):
        text = text[1:]
    if text.endswith(" ") or text.endswith("_"):
        text = text[:-1]
    if text and text[0].isdigit():
        if text.startswith("1st"):
            text = "first" + text[3:]
        elif text.startswith("2nd"):
            text = "second" + text[3:]
        elif text.startswith("3rd"):
            text = "third" + text[3:]
        elif text.startswith("4th"):
            text = "fourth" + text[3:]
        elif text.startswith("5th"):
            text = "fifth" + text[3:]
        elif text.startswith("6th"):
            text = "sixth" + text[3:]
        elif text.startswith("7th"):
            text = "seventh" + text[3:]
        elif text.startswith("8th"):
            text = "eighth" + text[3:]
        elif text.startswith("9th"):
            text = "ninth" + text[3:]
        elif text.startswith("10th"):
            text = "tenth" + text[4:]
        else:
            text = f"n_{text}"

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

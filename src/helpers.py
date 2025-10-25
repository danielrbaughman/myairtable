import os
import shutil
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from pydantic import BaseModel
from pydantic.alias_generators import to_camel
from rich import print
from rich.console import Console
from rich.table import Table

from src.airtable_meta_types import FIELD_TYPE, AirTableFieldMetadata, TableMetadata


class WriteToFile(BaseModel):
    """Abstracts file writing operations."""

    path: Path
    file: Optional[object] = None
    lines: list[str] = []
    language: Literal["python", "typescript"] = "python"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            if self.path.exists():
                os.remove(self.path)
            os.makedirs(self.path.parent, exist_ok=True)
            self.file = open(self.path, "a")
            match self.language:
                case "python":
                    self.file.write("# ==========================================\n")
                    self.file.write("# Auto-generated file. Do not edit directly.\n")
                    self.file.write("# ==========================================\n")
                    self.file.write("\n")
                case "typescript":
                    self.file.write("// ==========================================\n")
                    self.file.write("// Auto-generated file. Do not edit directly.\n")
                    self.file.write("// ==========================================\n")
                    self.file.write("\n")
            for line in self.lines:
                self.file.write(line + "\n")
            self.file.close()

    def line(self, text: str):
        self.lines.append(text)

    def line_empty(self):
        self.lines.append("")

    def line_indented(self, text: str, indent: int = 1):
        self.lines.append("    " * indent + text)


class WriteToPythonFile(WriteToFile):
    def __init__(self, path: Path):
        super().__init__(path=path, language="python")

    def types(self, name: str, list: list[str], docstring: str = ""):
        literal_name = f"{name}"
        self.literal(literal_name, list)
        if docstring:
            self.line(f'"""{docstring}"""')
        self.str_list(f"{name}s", list, type=literal_name)
        if docstring:
            self.line(f'"""{docstring}"""')
        self.line_empty()

    def property_docstring(self, field: AirTableFieldMetadata, table: TableMetadata):
        if field["id"] == table["primaryFieldId"]:
            if is_computed_field(field):
                self.line_indented(f'"""{sanitize_string(field["name"])} `{field["id"]}` - `Primary Key` - `Read-Only Field`"""')
            else:
                self.line_indented(f'"""{sanitize_string(field["name"])} `{field["id"]}` - `Primary Key`"""')
        elif is_computed_field(field):
            self.line_indented(f'"""{sanitize_string(field["name"])} `{field["id"]}` - `Read-Only Field`"""')
        else:
            self.line_indented(f'"""{sanitize_string(field["name"])} `{field["id"]}`"""')

    def dict_class(self, name: str, pairs: list[tuple[str, str]], first_type: str = "str", second_type: str = "str"):
        self.line(f"{name}: dict[{first_type}, {second_type}] = {{")
        for k, v in pairs:
            self.dict_row(k, v)
        self.line("}")
        self.line_empty()

    def literal(self, name: str, list: list[str]):
        self.line(f"{name} = Literal[{', '.join(f'"{item}"' for item in list)}]")

    def str_list(self, name: str, list: list[str], type: str = "str"):
        self.line(f"{name}: list[{type}] = [{', '.join(f'"{item}"' for item in list)}]")

    def dict_row(self, key: str, value: str):
        self.line_indented(f'"{key}": "{value}",')

    def property_row(self, name: str, type: str):
        self.line_indented(f"{name}: {type}")

    def region(self, text: str):
        self.lines.append(f"# region {text}")

    def endregion(self):
        self.lines.append("# endregion")
        self.line_empty()


class WriteToTypeScriptFile(WriteToFile):
    def __init__(self, path: Path):
        super().__init__(path=path, language="typescript")

    def region(self, text: str):
        self.lines.append(f"// #region {text}")

    def endregion(self):
        self.lines.append("// #endregion")
        self.line_empty()

    def literal(self, name: str, list: list[str]):
        self.line(f"export type {name} = {' | '.join(f'"{item}"' for item in list)}")

    def str_list(self, name: str, list: list[str], type: str = "string"):
        self.line(f"export const {name}: {type}[] = [{', '.join(f'"{item}"' for item in list)}]")

    def docstring(self, text: str):
        self.line(f"/** {text} */")

    def types(self, name: str, list: list[str], docstring: str = ""):
        literal_name = f"{name}"
        if docstring:
            self.docstring(docstring)
        self.literal(literal_name, list)
        if docstring:
            self.docstring(docstring)
        self.str_list(f"{name}s", list, type=literal_name)
        self.line_empty()

    def dict_class(
        self, name: str, pairs: list[tuple[str, str]], first_type: str = "string", second_type: str = "string", is_value_string: bool = False
    ):
        self.line(f"export const {name}: Record<{first_type}, {second_type}> = {{")
        for k, v in pairs:
            self.dict_row(k, v, is_value_string)
        self.line("}")
        self.line_empty()

    def dict_row(self, key: str, value: str, is_value_string: bool = False, optional: bool = False):
        if is_value_string:
            self.line_indented(f'"{key}"{"?" if optional else ""}: "{value}",')
        else:
            self.line_indented(f'"{key}"{"?" if optional else ""}: {value},')

    def property_row(self, name: str, type: str, is_name_string: bool = False, optional: bool = False):
        if is_name_string:
            self.line_indented(f'"{name}"{"?" if optional else ""}: {type},')
        else:
            self.line_indented(f"{name}{'?' if optional else ''}: {type}")


def is_calculated_field(field: AirTableFieldMetadata) -> bool:
    return field["type"] == "formula" or field["type"] == "rollup" or field["type"] == "lookup" or field["type"] == "multipleLookupValues"


def is_computed_field(field: AirTableFieldMetadata) -> bool:
    return (
        is_calculated_field(field)
        or field["type"] == "createdTime"
        or field["type"] == "lastModifiedTime"
        or field["type"] == "createdBy"
        or field["type"] == "count"
    )


def get_select_options(field: AirTableFieldMetadata) -> list[str]:
    """Get the options of a select field"""

    airtable_type = field["type"]

    if (
        airtable_type == "singleSelect"
        or airtable_type == "multipleSelects"
        or airtable_type == "singleCollaborator"
        or airtable_type == "multipleLookupValues"
        or airtable_type == "formula"
    ):
        if "options" in field and field["options"]:
            if "choices" in field["options"] and field["options"]["choices"]:
                options = [choice["name"] for choice in field["options"]["choices"]]
                options.sort()
                return options
            elif "result" in field["options"] and field["options"]["result"]:
                if "options" in field["options"]["result"] and field["options"]["result"]["options"]:
                    if "choices" in field["options"]["result"]["options"]:
                        options = [choice["name"] for choice in field["options"]["result"]["options"]["choices"]]
                        options.sort()
                        return options

    return []


def options_name(table_name: str, field_name: str) -> str:
    return f"{table_name}{field_name}Option"


def upper_case(text: str) -> str:
    """Formats as UPPERCASE"""

    def alpha_only(text: str) -> str:
        return "".join(c for c in text if c.isalpha())

    return alpha_only(text).upper()


def camel_case(text: str) -> str:
    """Formats as CamelCase"""

    def non_alpha_to_space(text: str) -> str:
        return "".join(c if c.isalpha() else " " for c in text)

    def capitalize_words(text: str) -> list[str]:
        return [word.capitalize() for word in text.split()]

    text = non_alpha_to_space(text)
    return "".join(capitalize_words(text))


def python_property_name(field_or_table: AirTableFieldMetadata | TableMetadata, folder: Path, use_custom: bool = True) -> str:
    """Formats as snake_case, and sanitizes the name to remove any characters that are not allowed in property names"""

    if use_custom:
        text = get_custom_property_name(field_or_table, folder)
        if text:
            return text

    text = field_or_table["name"]

    text = sanitize_property_name(text)
    text = snake_case(text)
    text = sanitize_leading_trailing_characters(text)
    text = sanitize_reserved_names(text)

    return text


def property_name(field_or_table: AirTableFieldMetadata | TableMetadata, folder: Path, use_custom: bool = True) -> str:
    """Formats as camelCase, and sanitizes the name to remove any characters that are not allowed in property names"""
    python_name = python_property_name(field_or_table, folder, use_custom)
    return to_camel(python_name)


def sanitize_property_name(text: str) -> str:
    """Sanitizes the property name to remove any characters that are not allowed in property names"""

    if text.endswith("?"):
        text = text[:-1]
        text = "is_" + text
    if text.endswith(" #"):
        text = text[:-1]
        text = text + "number"

    text = text.replace("+", " and ")
    text = text.replace("&", " and ")
    text = text.replace("=", " is ")
    text = text.replace("%", " percent ")
    text = text.replace("<", " less than ")
    text = text.replace(">", " greater than ")
    text = text.replace("$/", " dollars per ")
    text = text.replace("$ ", "dollar ")
    text = text.replace("w/", " with ")
    text = text.replace("# ", " number ")

    text = text.replace("(", "").replace(")", "")
    text = text.replace("?", "").replace("$", "")
    text = text.replace("#", "").replace("'", "")

    text = text.replace("/", "_")
    text = text.replace("\\", "_")
    text = text.replace("-", "_")
    text = text.replace(".", "_")
    text = text.replace(":", "_")

    return text


def snake_case(text: str) -> str:
    """Formats as snake_case"""

    text = text.replace(" ", "_")
    text = text.replace("__", "_").replace("__", "_").replace("__", "_").replace("__", "_").replace("__", "_")
    text = text.lower()

    return text


def sanitize_leading_trailing_characters(text: str) -> str:
    """Sanitizes leading and trailing characters, to deal with characters that are not allowed and/or desired in property names"""

    if text.startswith("_"):
        text = text[1:]
    if text.endswith("_"):
        text = text[:-1]
    if text and text[0].isdigit():
        text = f"n_{text}"

    return text


def sanitize_reserved_names(text: str) -> str:
    """Some names are reserved by the pyairtable library and cannot be used as property names."""

    if text == "id":
        text = "identifier"
    if text == "created_time":
        text = "created_at"

    return text


fields_dataframe: pd.DataFrame = None  # type: ignore
tables_dataframe: pd.DataFrame = None  # type: ignore


def get_custom_property_name(field_or_table: AirTableFieldMetadata | TableMetadata, folder: Path) -> str | None:
    """Gets the custom property name for a field or table, if it exists."""

    global fields_dataframe
    if fields_dataframe is None:
        fields_dataframe = pd.read_csv(folder / "fields.csv")

    global tables_dataframe
    if tables_dataframe is None:
        tables_dataframe = pd.read_csv(folder / "tables.csv")

    id = "Table ID" if "primaryFieldId" in field_or_table else "Field ID"
    match = fields_dataframe[fields_dataframe[id] == field_or_table["id"]]
    if not match.empty:
        if "Property Name" in match.columns:
            custom_property_name = match.iloc[0]["Property Name"]
            if isinstance(custom_property_name, str) and custom_property_name.strip():
                name = snake_case(custom_property_name.strip())
                if name:
                    return name

    return None


def get_result_type(field: AirTableFieldMetadata, airtable_type: FIELD_TYPE = "") -> FIELD_TYPE:
    if "options" in field and field["options"]:
        if "result" in field["options"] and field["options"]["result"]:
            if "type" in field["options"]["result"]:
                airtable_type = field["options"]["result"]["type"]

    return airtable_type


def warn_unhandled_airtable_type(field: AirTableFieldMetadata, airtable_type: FIELD_TYPE, verbose: bool):
    if is_valid_field(field):
        print(
            "[yellow]Unhandled Airtable type. This results in generic types in the output.[/]",
            "use --verbose for more details" if not verbose else "",
        )
    else:
        print(
            "[yellow]Invalid Airtable field[/]",
            field["id"],
            "[yellow]This results in generic types in the output.[/]",
            "use --verbose for more details" if not verbose else "",
        )
    if verbose:
        table = Table()
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("ID", str(field["id"]))
        table.add_row("Name", str(field["name"]))
        table.add_row("Type", str(field["type"]))
        table.add_row("Interpreted Type", str(airtable_type))
        is_valid = is_valid_field(field)
        color = "green" if is_valid else "red"
        table.add_row("Is Valid", f"[{color}]{is_valid}[/{color}]")
        console = Console()
        console.print(table)
        print("")


def sanitize_string(text: str) -> str:
    return text.replace('"', "'")


def is_valid_field(field: AirTableFieldMetadata) -> bool:
    """Check if the field is `valid` according to Airtable."""
    if "options" in field and "isValid" in field["options"]:
        return bool(field["options"]["isValid"])
    return True


def involves_lookup_field(field: AirTableFieldMetadata, all_fields: dict[str, AirTableFieldMetadata]) -> bool:
    """Check if a field involves multipleLookupValues, either directly or through any referenced fields."""
    if field["type"] == "multipleLookupValues" or field["type"] == "lookup":
        return True

    # Check if field has referencedFieldIds and recursively check each one
    options = field.get("options", {})
    referenced_field_ids = options.get("referencedFieldIds", [])

    if referenced_field_ids:
        for referenced_field_id in referenced_field_ids:
            if referenced_field_id in all_fields:
                referenced_field = all_fields[referenced_field_id]
                if involves_lookup_field(referenced_field, all_fields):
                    return True
    return False


def involves_rollup_field(field: AirTableFieldMetadata, all_fields: dict[str, AirTableFieldMetadata]) -> bool:
    """Check if a field involves rollup, either directly or through any referenced fields."""
    if field["type"] == "rollup":
        return True

    # Check if field has referencedFieldIds and recursively check each one
    options = field.get("options", {})
    referenced_field_ids = options.get("referencedFieldIds", [])

    if referenced_field_ids:
        for referenced_field_id in referenced_field_ids:
            if referenced_field_id in all_fields:
                referenced_field = all_fields[referenced_field_id]
                if involves_rollup_field(referenced_field, all_fields):
                    return True
    return False


def get_referenced_field(field: AirTableFieldMetadata, all_fields: dict[str, AirTableFieldMetadata]) -> AirTableFieldMetadata | None:
    options = field.get("options", {})
    referenced_field_id = options.get("fieldIdInLinkedTable")
    if referenced_field_id and referenced_field_id in all_fields:
        return all_fields[referenced_field_id]

    return None

def copy_static_files(folder: Path, type: str):
    source = Path(f"./src/static/{type}")
    destination = folder / "static"

    if source.exists():
        for file in source.iterdir():
            if file.is_file():
                shutil.copy2(file, destination / file.name)
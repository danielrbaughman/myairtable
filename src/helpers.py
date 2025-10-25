import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from pydantic import BaseModel
from pydantic.alias_generators import to_camel, to_pascal
from rich import print

from .meta_types import FieldMetadata, FieldType, TableMetadata


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
                    self.file.write(f"# Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {datetime.now().astimezone().tzinfo}\n")
                    self.file.write("# ==========================================\n")
                    self.file.write("\n")
                case "typescript":
                    self.file.write("// ==========================================\n")
                    self.file.write("// Auto-generated file. Do not edit directly.\n")
                    self.file.write(f"// Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {datetime.now().astimezone().tzinfo}\n")
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

    def property_docstring(self, field: FieldMetadata, table: TableMetadata):
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
        self.line(f"{name} = Literal[")
        for item in list:
            self.line_indented(f'"{item}",')
        self.line("]")

    def str_list(self, name: str, list: list[str], type: str = "str"):
        self.line(f"{name}: list[{type}] = [")
        for item in list:
            self.line_indented(f'"{item}",')
        self.line("]")

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


def is_calculated_field(field: FieldMetadata) -> bool:
    return field["type"] == "formula" or field["type"] == "rollup" or field["type"] == "lookup" or field["type"] == "multipleLookupValues"


def is_computed_field(field: FieldMetadata) -> bool:
    return (
        is_calculated_field(field)
        or field["type"] == "createdTime"
        or field["type"] == "lastModifiedTime"
        or field["type"] == "createdBy"
        or field["type"] == "count"
    )


def get_select_options(field: FieldMetadata) -> list[str]:
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


def detect_duplicate_property_names(table: TableMetadata, folder: Path) -> None:
    """Detect duplicate property names in a table's fields."""
    property_names: list[str] = []
    for field in table["fields"]:
        property_name = property_name_snake(field, folder)
        property_names.append(property_name)
    for name in set(property_names):
        count = property_names.count(name)
        if count > 1:
            print(f"[red]Warning: Duplicate property name detected:[/] '{name}' in table '{table['name']}'")


def property_name_snake(field_or_table: FieldMetadata | TableMetadata, folder: Path, use_custom: bool = True) -> str:
    """Formats as snake_case, and sanitizes the name to remove any characters that are not allowed in property names"""

    if use_custom and folder:
        text = get_custom_property_name(field_or_table, folder)
        if text:
            return text

    text = field_or_table["name"]

    text = sanitize_property_name(text)
    text = space_to_snake_case(text)
    text = sanitize_leading_trailing_characters(text)
    text = sanitize_reserved_names(text)

    return text


def property_name_camel(field_or_table: FieldMetadata | TableMetadata, folder: Path, use_custom: bool = True) -> str:
    """Formats as camelCase, and sanitizes the name to remove any characters that are not allowed in property names"""
    python_name = property_name_snake(field_or_table, folder, use_custom)
    return to_camel(python_name)


def property_name_pascal(field_or_table: FieldMetadata | TableMetadata, folder: Path, use_custom: bool = True) -> str:
    """Formats as PascalCase, and sanitizes the name to remove any characters that are not allowed in property names"""
    python_name = property_name_snake(field_or_table, folder, use_custom)
    return to_pascal(python_name)


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

    return text


def space_to_snake_case(text: str) -> str:
    """Formats as snake_case"""

    text = text.replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    text = text.lower()

    return text


def sanitize_leading_trailing_characters(text: str) -> str:
    """Sanitizes leading and trailing characters, to deal with characters that are not allowed and/or desired in property names"""

    if text.startswith("_"):
        text = text[1:]
    if text.endswith("_"):
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


fields_dataframe: pd.DataFrame = None  # type: ignore
tables_dataframe: pd.DataFrame = None  # type: ignore


def get_custom_property_name(field_or_table: FieldMetadata | TableMetadata, folder: Path) -> str | None:
    """Gets the custom property name for a field or table, if it exists."""

    is_table = "primaryFieldId" in field_or_table

    if is_table:
        global tables_dataframe
        if tables_dataframe is None:
            tables_path = folder / "tables.csv"
            if not tables_path.exists():
                return None
            tables_dataframe = pd.read_csv(tables_path)

        match = tables_dataframe[tables_dataframe["Table ID"] == field_or_table["id"]]
        if not match.empty:
            if "Property Name (snake_case)" in match.columns:
                custom_property_name = match.iloc[0]["Property Name (snake_case)"]
                if isinstance(custom_property_name, str) and custom_property_name.strip():
                    name = space_to_snake_case(custom_property_name.strip())
                    if name:
                        return name
    else:
        global fields_dataframe
        if fields_dataframe is None:
            fields_path = folder / "fields.csv"
            if not fields_path.exists():
                return None
            fields_dataframe = pd.read_csv(fields_path)

        id = "Table ID" if "primaryFieldId" in field_or_table else "Field ID"
        match = fields_dataframe[fields_dataframe[id] == field_or_table["id"]]
        if not match.empty:
            if "Property Name (snake_case)" in match.columns:
                custom_property_name = match.iloc[0]["Property Name (snake_case)"]
                if isinstance(custom_property_name, str) and custom_property_name.strip():
                    name = space_to_snake_case(custom_property_name.strip())
                    if name:
                        return name

    return None


def get_result_type(field: FieldMetadata, airtable_type: FieldType = "") -> FieldType:
    if "options" in field and field["options"]:  # type: ignore
        if "result" in field["options"] and field["options"]["result"]:  # type: ignore
            if "type" in field["options"]["result"]:  # type: ignore
                airtable_type = field["options"]["result"]["type"]  # type: ignore

    return airtable_type


def warn_unhandled_airtable_type(table_name: str, field: FieldMetadata, airtable_type: FieldType):
    if is_valid_field(field):
        print(
            "[yellow]Warning: Unhandled Airtable type. This results in generic types in the output.[/]",
        )
    else:
        print(
            "[yellow]Warning: Invalid Airtable field. This results in generic types in the output.[/]",
            "Field:",
            f"'{field['name']}'",
            f"({field['id']})",
            "in Table:",
            f"'{table_name}'",
        )


def sanitize_string(text: str) -> str:
    return text.replace('"', "'")


def is_valid_field(field: FieldMetadata) -> bool:
    """Check if the field is `valid` according to Airtable."""
    if "options" in field and "isValid" in field["options"]:  # type: ignore
        return bool(field["options"]["isValid"])  # type: ignore
    return True


def involves_lookup_field(field: FieldMetadata, all_fields: dict[str, FieldMetadata]) -> bool:
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


def involves_rollup_field(field: FieldMetadata, all_fields: dict[str, FieldMetadata]) -> bool:
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


def get_referenced_field(field: FieldMetadata, all_fields: dict[str, FieldMetadata]) -> FieldMetadata | None:
    options = field.get("options", {})
    referenced_field_id = options.get("fieldIdInLinkedTable")
    if referenced_field_id and referenced_field_id in all_fields:
        return all_fields[referenced_field_id]

    return None


def copy_static_files(folder: Path, type: str):
    source = Path(f"./static/{type}")
    destination = folder / "static"
    destination.mkdir(parents=True, exist_ok=True)

    if source.exists():
        for file in source.iterdir():
            if file.is_file():
                shutil.copy2(file, destination / file.name)

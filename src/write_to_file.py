import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from src.helpers import sanitize_string

from .meta import Field, Table

PROPERTY_NAME = "Property Name (snake_case)"
MODEL_NAME = "Model Name (snake_case)"


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

    def property_docstring(self, field: Field, table: Table):
        if field.id == table.primary_field_id:
            if field.is_computed():
                self.line_indented(f'"""{sanitize_string(field.name)} `{field.id}` - `Primary Key` - `Read-Only Field`"""')
            else:
                self.line_indented(f'"""{sanitize_string(field.name)} `{field.id}` - `Primary Key`"""')
        elif field.is_computed():
            self.line_indented(f'"""{sanitize_string(field.name)} `{field.id}` - `Read-Only Field`"""')
        else:
            self.line_indented(f'"""{sanitize_string(field.name)} `{field.id}`"""')

    def dict_class(self, name: str, pairs: list[tuple[str, str]], first_type: str = "str", second_type: str = "str", value_is_string: bool = True):
        self.line(f"{name}: dict[{first_type}, {second_type}] = {{")
        for k, v in pairs:
            self.dict_row(k, v, value_is_string=value_is_string)
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

    def dict_row(self, key: str, value: str, value_is_string: bool = True):
        if value_is_string:
            self.line_indented(f'"{key}": "{value}",')
        else:
            self.line_indented(f'"{key}": {value},')

    def property_row(self, name: str, type: str):
        self.line_indented(f"{name}: {type}")

    def region(self, text: str):
        self.lines.append(f"# region {text}")

    def endregion(self):
        self.lines.append("# endregion")
        self.line_empty()

    def multiline_import(self, module: str, items: list[str]) -> None:
        """Write a multi-line import statement."""
        self.line(f"from {module} import (")
        for item in items:
            self.line_indented(f"{item},")
        self.line(")")

    def select_options_import(self, table: Table) -> None:
        """Import select field option types if the table has any select fields."""
        select_fields = table.select_fields()
        if len(select_fields) > 0:
            self.multiline_import("..types", [field.options_name() for field in select_fields])


class WriteToTypeScriptFile(WriteToFile):
    def __init__(self, path: Path):
        super().__init__(path=path, language="typescript")

    def region(self, text: str):
        self.lines.append(f"// #region {text}")

    def endregion(self):
        self.lines.append("// #endregion")
        self.line_empty()

    def literal(self, name: str, list: list[str]):
        self.line(f"export type {name} = ")
        for item in list:
            if item != list[-1]:
                self.line_indented(f'"{item}" |')
            else:
                self.line_indented(f'"{item}"')

    def str_list(self, name: str, list: list[str], type: str = "string"):
        self.line(f"export const {name}: {type}[] = [")
        for item in list:
            self.line_indented(f'"{item}",')
        self.line("]")

    def docstring(self, text: str, indent: int = 1):
        self.line_indented(f"/** {text} */", indent=indent)

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

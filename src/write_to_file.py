import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

PROPERTY_NAME = "Property Name (snake_case)"
MODEL_NAME = "Model Name (snake_case)"


class WriteToFile(BaseModel):
    """Abstracts file writing operations with buffered single-write output."""

    path: Path
    lines: list[str] = []
    language: Literal["python", "typescript", "markdown"]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            os.makedirs(self.path.parent, exist_ok=True)

            # Build header based on language
            match self.language:
                case "python":
                    header: str = (
                        "# ==========================================\n"
                        "# Auto-generated file. Do not edit directly.\n"
                        "# ==========================================\n\n"
                    )
                case "typescript":
                    header: str = (
                        "// ==========================================\n"
                        "// Auto-generated file. Do not edit directly.\n"
                        "// ==========================================\n\n"
                    )
                case _:
                    header: str = ""

            # Single write operation: header + all lines joined
            content = header + "\n".join(self.lines) + ("\n" if self.lines else "")

            # Write mode truncates/creates file (no need to delete first)
            with open(self.path, "w") as f:
                f.write(content)

    def line(self, text: str):
        self.lines.append(text)

    def line_empty(self):
        self.lines.append("")

    def line_indented(self, text: str, indent: int = 1):
        self.lines.append("    " * indent + text)
